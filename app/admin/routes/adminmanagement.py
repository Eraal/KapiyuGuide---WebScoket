from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from flask_socketio import emit
from app import socketio
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp

############################################## ADMIN MANAGE #############################################

@admin_bp.route('/adminmanage')
@login_required
def adminmanage():
    if current_user.role != 'super_admin':
        flash('Unauthorized access', 'error')
        return redirect(url_for('main.index'))
        
    offices = Office.query.all()
    office_admins = User.query.filter_by(role='office_admin').all()
    
    total_offices = len(offices)
    active_office_admins = User.query.filter_by(role='office_admin', is_active=True).count()
    unassigned_offices = Office.query.filter(~Office.office_admins.any()).count()
    unassigned_admins = User.query.filter_by(role='office_admin').filter(~User.office_admin.has()).count()
    
    # Log super admin activity
    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action="View Admin Management",
        target_type="system",
        details="Accessed admin management interface"
    )
    db.session.commit()
    
    return render_template(
        'admin/adminmanage.html',
        offices=offices,
        office_admins=office_admins,
        total_offices=total_offices,
        active_office_admins=active_office_admins,
        unassigned_offices=unassigned_offices,
        unassigned_admins=unassigned_admins
    )

@admin_bp.route('/api/office/<int:office_id>/admins')
@login_required
def get_office_admins(office_id):
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403

    office = Office.query.get_or_404(office_id)
    
    office_admins = office.office_admins
    admins_data = []
    
    for office_admin in office_admins:
        user = office_admin.user
        if user:
            admins_data.append({
                'id': user.id,
                'first_name': user.first_name,
                'middle_name': user.middle_name,
                'last_name': user.last_name,
                'full_name': f"{user.first_name} {user.middle_name + ' ' if user.middle_name else ''}{user.last_name}",
                'email': user.email,
                'is_active': user.is_active,
                'created_at': user.created_at.strftime('%B %d, %I:%M %p')
            })
    
    return jsonify({'admins': admins_data})

@admin_bp.route('/remove_office_admin', methods=['POST'])
@login_required
def remove_office_admin():
    if not current_user.role == 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized. Only super admins can remove office admins'}), 403
    
    try:
        data = request.json
        office_id = data.get('office_id')
        admin_id = data.get('admin_id')  
        
        if not office_id or not admin_id:
            return jsonify({'success': False, 'message': 'Missing required parameters'}), 400
        
        office = Office.query.get(office_id)
        if not office:
            return jsonify({'success': False, 'message': 'Office not found'}), 404
        
        admin = User.query.get(admin_id)
        if not admin or admin.role not in ['office_admin', 'super_admin']:
            return jsonify({'success': False, 'message': 'Admin not found'}), 404
        
        office_admin = OfficeAdmin.query.filter_by(office_id=office_id, user_id=admin_id).first()
        if not office_admin:
            return jsonify({'success': False, 'message': 'Admin not associated with this office'}), 404
        
        db.session.delete(office_admin)
        
        # Log action
        SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action="Remove Office Admin",
            target_type="user",
            details=f"Removed admin {admin.id} from office {office.id}"
        )
        
        db.session.commit()
        
        # Get updated stats
        unassigned_admins = User.query.filter_by(role='office_admin').filter(~User.office_admin.has()).count()
        
        # Emit WebSocket event for office assignment removal
        socketio.emit('office_admin_removed', {
            'admin_id': admin_id,
            'admin_name': f"{admin.first_name} {admin.last_name}",
            'office_id': office_id,
            'office_name': office.name
        }, room='super_admin_room')
        
        # Update the dashboard stats
        socketio.emit('dashboard_stats_update', {
            'unassigned_admins': unassigned_admins
        }, room='super_admin_room')
        
        return jsonify({
            'success': True, 
            'message': f'Admin {admin.first_name} {admin.last_name} has been removed from {office.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/add_admin', methods=['POST'])
@login_required
def add_admin():
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    try:
        first_name = request.form.get('first_name', '').strip()
        middle_name = request.form.get('middle_name', '')  # Optional
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        office_id = request.form.get('office_id')
        is_active = request.form.get('is_active') == 'true'
        
        # Form validation
        if not first_name:
            return jsonify({'success': False, 'message': 'First name is required'}), 400
        if not last_name:
            return jsonify({'success': False, 'message': 'Last name is required'}), 400
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        if not password:
            return jsonify({'success': False, 'message': 'Password is required'}), 400
        
        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'Email already exists'}), 400
        
        # Process profile picture if uploaded
        profile_pic_path = None
        if 'profile_pic' in request.files:
            profile_pic = request.files['profile_pic']
            if profile_pic and profile_pic.filename != '':
                filename = secure_filename(profile_pic.filename)
                upload_folder = os.path.join(current_app.root_path, 'static/uploads/profiles')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                
                profile_pic_path = os.path.join('uploads/profiles', filename)
                profile_pic.save(os.path.join(current_app.root_path, 'static', profile_pic_path))
        
        # Create the new admin user
        new_user = User(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            email=email,
            password_hash=generate_password_hash(password),
            role='office_admin',
            is_active=is_active,
            profile_pic=profile_pic_path
        )
        
        db.session.add(new_user)
        db.session.flush()  # Flush to get the new user ID before committing
        
        # Associate with office if specified
        office_name = None
        if office_id and office_id != '':
            office = Office.query.get(office_id)
            if office:
                office_admin = OfficeAdmin(
                    user_id=new_user.id,
                    office_id=int(office_id)
                )
                db.session.add(office_admin)
                office_name = office.name
        
        # Log action
        SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action="Create Office Admin",
            target_type="user",
            details=f"Created new office admin {new_user.email}"
        )
        
        db.session.commit()
        
        # Get updated stats to reflect the new admin
        total_offices = Office.query.count()
        active_office_admins = User.query.filter_by(role='office_admin', is_active=True).count()
        unassigned_offices = Office.query.filter(~Office.office_admins.any()).count()
        unassigned_admins = User.query.filter_by(role='office_admin').filter(~User.office_admin.has()).count()
        
        # Emit stats update via WebSocket
        socketio.emit('dashboard_stats_update', {
            'total_offices': total_offices,
            'active_office_admins': active_office_admins,
            'unassigned_offices': unassigned_offices,
            'unassigned_admins': unassigned_admins
        }, room='super_admin_room')
        
        # Emit WebSocket event for admin table update
        socketio.emit('admin_added', {
            'id': new_user.id,
            'first_name': new_user.first_name,
            'middle_name': new_user.middle_name,
            'last_name': new_user.last_name,
            'email': new_user.email,
            'is_active': new_user.is_active,
            'profile_pic': new_user.profile_pic,
            'office_id': office_id if office_id and office_id != '' else None,
            'office_name': office_name
        }, room='super_admin_room')
        
        return jsonify({'success': True, 'message': 'Office admin added successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error adding office admin: {str(e)}'}), 500



@admin_bp.route('/api/admin/<int:admin_id>', methods=['GET'])
@login_required
def get_admin_data(admin_id):
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    try:
        admin = User.query.filter_by(id=admin_id, role='office_admin').first()
        
        if not admin:
            return jsonify({'success': False, 'message': 'Admin not found'}), 404
        
        office_admin = OfficeAdmin.query.filter_by(user_id=admin_id).first()
        office_id = office_admin.office_id if office_admin else None
        
        return jsonify({
            'success': True,
            'admin': {
                'id': admin.id,
                'first_name': admin.first_name,
                'middle_name': admin.middle_name,
                'last_name': admin.last_name,
                'email': admin.email,
                'is_active': admin.is_active,
                'office_id': office_id,
                'profile_pic': admin.profile_pic
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching admin data: {str(e)}'}), 500

@admin_bp.route('/delete_admin', methods=['POST'])
@login_required
def delete_admin():
    if current_user.role != 'super_admin':
        flash('Unauthorized access', 'error')
        return redirect(url_for('admin.adminmanage'))
        
    try:
        admin_id = request.form.get('admin_id')
        
        if not admin_id:
            flash('Admin ID is required', 'error')
            return redirect(url_for('admin.adminmanage'))
        
        admin = User.query.filter_by(id=admin_id, role='office_admin').first()
        
        if not admin:
            flash('Admin not found', 'error')
            return redirect(url_for('admin.adminmanage'))
        
        # Get office info before deletion
        office_admin = OfficeAdmin.query.filter_by(user_id=admin_id).first()
        office_id = None
        office_name = None
        if office_admin:
            office_id = office_admin.office_id
            office = Office.query.get(office_id)
            office_name = office.name if office else None
            
        # Store admin info for later use in WebSocket event
        admin_info = {
            'id': admin.id,
            'name': f"{admin.first_name} {admin.last_name}",
            'email': admin.email,
            'office_id': office_id,
            'office_name': office_name
        }
        
        # Log action before deletion
        SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action="Delete Office Admin",
            target_type="user",
            details=f"Deleted office admin {admin.email} (ID: {admin.id})"
        )
        
        db.session.delete(admin)
        db.session.commit()
        
        # Get updated stats
        total_offices = Office.query.count()
        active_office_admins = User.query.filter_by(role='office_admin', is_active=True).count()
        unassigned_offices = Office.query.filter(~Office.office_admins.any()).count()
        unassigned_admins = User.query.filter_by(role='office_admin').filter(~User.office_admin.has()).count()
        
        # Emit WebSocket event for admin deletion
        socketio.emit('admin_deleted', admin_info, room='super_admin_room')
        
        # Update the dashboard stats
        socketio.emit('dashboard_stats_update', {
            'total_offices': total_offices,
            'active_office_admins': active_office_admins,
            'unassigned_offices': unassigned_offices,
            'unassigned_admins': unassigned_admins
        }, room='super_admin_room')
        
        flash('Admin deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting admin: {str(e)}', 'error')
    
    return redirect(url_for('admin.adminmanage'))


@admin_bp.route('/update_admin', methods=['POST'])
@login_required
def update_admin():
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    try:
        admin_id = request.form.get('admin_id')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name', '')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        office_id = request.form.get('office_id')
        is_active = request.form.get('is_active') == 'true'
        
        if not all([admin_id, first_name, last_name, email]):
            return jsonify({'success': False, 'message': 'Please fill all required fields'}), 400
        
        admin = User.query.filter_by(id=admin_id, role='office_admin').first()
        if not admin:
            return jsonify({'success': False, 'message': 'Admin not found'}), 404
        
        existing_user = User.query.filter(User.email == email, User.id != admin_id).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'Email already exists for another user'}), 400
        
        # Track changes for logging and WebSocket events
        changes = {}
        if admin.first_name != first_name:
            changes['first_name'] = {'old': admin.first_name, 'new': first_name}
        if admin.middle_name != middle_name:
            changes['middle_name'] = {'old': admin.middle_name, 'new': middle_name}
        if admin.last_name != last_name:
            changes['last_name'] = {'old': admin.last_name, 'new': last_name}
        if admin.email != email:
            changes['email'] = {'old': admin.email, 'new': email}
        if admin.is_active != is_active:
            changes['is_active'] = {'old': admin.is_active, 'new': is_active}
        
        # Process profile picture if uploaded
        if 'profile_pic' in request.files:
            profile_pic = request.files['profile_pic']
            if profile_pic and profile_pic.filename != '':
                filename = secure_filename(profile_pic.filename)
                upload_folder = os.path.join(current_app.root_path, 'static/uploads/profiles')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                
                profile_pic_path = os.path.join('uploads/profiles', filename).replace("\\", "/")
                profile_pic.save(os.path.join(current_app.root_path, 'static', profile_pic_path))
                
                changes['profile_pic'] = {'old': admin.profile_pic, 'new': profile_pic_path}
                admin.profile_pic = profile_pic_path
        
        # Update basic user info
        admin.first_name = first_name
        admin.middle_name = middle_name
        admin.last_name = last_name
        admin.email = email
        admin.is_active = is_active
        
        # Handle office assignment
        old_office_id = None
        old_office_name = None
        new_office_name = None
        
        # Check if admin already has an office assignment
        existing_office_admin = OfficeAdmin.query.filter_by(user_id=admin_id).first()
        
        if office_id and office_id != '':
            new_office = Office.query.get(int(office_id))
            new_office_name = new_office.name if new_office else None
            
            if existing_office_admin:
                old_office_id = existing_office_admin.office_id
                old_office = Office.query.get(old_office_id)
                old_office_name = old_office.name if old_office else None
                
                if old_office_id != int(office_id):
                    changes['office'] = {'old': old_office_name, 'new': new_office_name}
                    existing_office_admin.office_id = int(office_id)
            else:
                changes['office'] = {'old': None, 'new': new_office_name}
                new_office_admin = OfficeAdmin(
                    user_id=admin_id,
                    office_id=int(office_id)
                )
                db.session.add(new_office_admin)
        elif existing_office_admin:
            old_office_id = existing_office_admin.office_id
            old_office = Office.query.get(old_office_id)
            old_office_name = old_office.name if old_office else None
            changes['office'] = {'old': old_office_name, 'new': None}
            db.session.delete(existing_office_admin)
        
        # Log the update action
        if changes:
            change_details = []
            for field, value in changes.items():
                change_details.append(f"{field}: {value['old']} -> {value['new']}")
            
            SuperAdminActivityLog.log_action(
                super_admin=current_user,
                action="Update Office Admin",
                target_type="user",
                details=f"Updated office admin {admin.id}: {', '.join(change_details)}"
            )
        
        db.session.commit()
        
        # Get updated stats
        active_office_admins = User.query.filter_by(role='office_admin', is_active=True).count()
        unassigned_admins = User.query.filter_by(role='office_admin').filter(~User.office_admin.has()).count()
        
        # Send a single comprehensive update event
        socketio.emit('admin_updated', {
            'id': admin.id,
            'first_name': admin.first_name,
            'middle_name': admin.middle_name,
            'last_name': admin.last_name,
            'email': admin.email,
            'is_active': admin.is_active,
            'profile_pic': admin.profile_pic,
            'office_id': office_id if office_id and office_id != '' else None,
            'office_name': new_office_name,
            'changes': changes
        }, room='super_admin_room')
        
        # Update the dashboard stats
        socketio.emit('dashboard_stats_update', {
            'active_office_admins': active_office_admins,
            'unassigned_admins': unassigned_admins
        }, room='super_admin_room')
        
        return jsonify({'success': True, 'message': 'Admin updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating admin: {str(e)}'}), 500

    
@admin_bp.route('/reset_admin_password', methods=['POST'])
@login_required
def reset_admin_password():
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    try:
        admin_id = request.form.get('admin_id')
        
        if not admin_id:
            return jsonify({'success': False, 'message': 'Admin ID is required'}), 400
        
        admin = User.query.filter_by(id=admin_id, role='office_admin').first()
        if not admin:
            return jsonify({'success': False, 'message': 'Admin not found'}), 404
        
        # Reset to a simple default password
        default_password = 'kapiyuadmin'  # Or generate a random one as in your original code
        
        admin.password_hash = generate_password_hash(default_password)
        
        # Log action
        SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action="Reset Admin Password",
            target_type="user",
            details=f"Reset password for admin {admin.id}"
        )
        
        db.session.commit()
        
        # Emit WebSocket event for password reset
        socketio.emit('admin_password_reset', {
            'admin_id': admin_id,
            'admin_name': f"{admin.first_name} {admin.last_name}"
        }, room='super_admin_room')
        
        return jsonify({
            'success': True, 
            'message': 'Password has been reset to default (kapiyuadmin)'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error resetting password: {str(e)}'}), 500

@admin_bp.route('/api/offices', methods=['GET'])
@login_required
def get_offices():
    if current_user.role not in ['super_admin', 'office_admin']:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    try:
        offices = Office.query.all()
        
        return jsonify({
            'success': True,
            'offices': [{'id': office.id, 'name': office.name} for office in offices]
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching offices: {str(e)}'}), 500

@admin_bp.route('/api/admin-dashboard/stats', methods=['GET'])
@login_required
def get_admin_dashboard_stats():
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
    
    try:
        # Get real-time statistics
        active_users = User.query.filter_by(is_active=True).count()
        pending_inquiries = Inquiry.query.filter_by(status='pending').count()
        upcoming_sessions = CounselingSession.query.filter(
            CounselingSession.scheduled_at > datetime.utcnow(),
            CounselingSession.status == 'scheduled'
        ).count()
        
        # Get office activity
        offices = Office.query.all()
        office_activity = []
        for office in offices:
            inquiries_count = Inquiry.query.filter_by(office_id=office.id).count()
            sessions_count = CounselingSession.query.filter_by(office_id=office.id).count()
            office_activity.append({
                'office_id': office.id,
                'office_name': office.name,
                'inquiries_count': inquiries_count,
                'sessions_count': sessions_count
            })
        
        # Get recent activities
        recent_admin_logs = SuperAdminActivityLog.query.order_by(
            SuperAdminActivityLog.timestamp.desc()
        ).limit(10).all()
        
        recent_activities = []
        for log in recent_admin_logs:
            admin = User.query.get(log.super_admin_id)
            admin_name = f"{admin.first_name} {admin.last_name}" if admin else "Unknown Admin"
            
            recent_activities.append({
                'admin_name': admin_name,
                'action': log.action,
                'target_type': log.target_type,
                'details': log.details,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({
            'success': True,
            'stats': {
                'active_users': active_users,
                'pending_inquiries': pending_inquiries,
                'upcoming_sessions': upcoming_sessions,
                'office_activity': office_activity,
                'recent_activities': recent_activities,
                'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching dashboard stats: {str(e)}'}), 500

# WebSocket route for admin room joining
@socketio.on('join_admin_room')
def handle_join_admin_room():
    if current_user.is_authenticated and current_user.role in ['super_admin', 'office_admin']:
        from flask_socketio import join_room
        join_room('admin_room')
        
        if current_user.role == 'super_admin':
            join_room('super_admin_room')
            print(f"Super Admin {current_user.email} joined super_admin_room")
            
            # Log the WebSocket connection
            SuperAdminActivityLog.log_action(
                super_admin=current_user,
                action="WebSocket Connect",
                target_type="system",
                details="Super admin real-time dashboard connection"
            )
            db.session.commit()
            
        print(f"Admin {current_user.email} joined admin_room")
        
        emit('connection_success', {
            'status': 'connected', 
            'user': current_user.email,
            'role': current_user.role
        })