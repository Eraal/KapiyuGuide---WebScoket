// admin_socket.js - Admin-specific WebSocket event handlers
console.log("Connected to admin socket JS")

class AdminSocketManager {
    constructor(socketManager) {
        this.socketManager = socketManager;
    }
    

    initialize() {
        if (!this.socketManager) {
            console.error('Base socket manager required');
            return;
        }
        
        // Listen for socket connection
        document.addEventListener('socket:connected', () => {
            console.log('Admin socket connected and ready');
            this.socketManager.emit('join_admin_room');
        });
        
        // Initialize admin-specific handlers
        this._setupEventHandlers();
        
        // Initialize page-specific handlers based on current page
        if (document.getElementById('admin-dashboard')) {
            this._initializeAdminDashboard();
        }
        
        if (document.getElementById('audit-logs')) {
            this._initializeAuditLogs();
        }

        if (document.getElementById('adminmanage') || document.location.href.includes('adminmanage')) {
            this._initializeAdminManage();
        }
        
        // Initialize announcement handlers
        this._setupAnnouncementHandlers();
    }

    _setupEventHandlers() {
        // System alerts
        this.socketManager.on('system_alert', (data) => {
            this._showSystemAlert(data);
        });
        
        // User activity
        this.socketManager.on('user_activity', (data) => {
            this._updateUserActivity(data);
        });
    }

    _initializeAdminDashboard() {
        // Real-time system stats updates
        this.socketManager.on('system_stats_update', (data) => {
            this._updateSystemStats(data);
        });
        
        // User login/logout events
        this.socketManager.on('user_status_change', (data) => {
            this._updateActiveUsersList(data);
        });
    }

    _initializeAuditLogs() {
        // Real-time audit log updates
        this.socketManager.on('new_audit_log', (data) => {
            this._prependAuditLog(data);
        });
    }

    _setupAnnouncementHandlers() {
        const announcementForm = document.getElementById('create-announcement-form');
        if (!announcementForm) return;
        
        announcementForm.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const formData = new FormData(announcementForm);
            const announcementData = {
                title: formData.get('title'),
                content: formData.get('content'),
                target_office_id: formData.get('target_office_id') || null,
                is_public: formData.get('is_public') === 'on'
            };
            
            // First submit via AJAX
            fetch(announcementForm.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': formData.get('csrf_token')
                },
                body: JSON.stringify(announcementData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Emit socket event for real-time update
                    this.socketManager.emit('admin_announcement_created', {
                        id: data.announcement_id,
                        title: announcementData.title,
                        content: announcementData.content,
                        target_office_id: announcementData.target_office_id,
                        is_public: announcementData.is_public,
                        author_name: document.body.dataset.userName
                    });
                    
                    // Reset form
                    announcementForm.reset();
                    
                    // Show success message
                    this._showNotification('Announcement created successfully');
                } else {
                    this._showNotification('Error creating announcement: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this._showNotification('Error creating announcement');
            });
        });
    }

    _updateSystemStats(data) {
        // Update all system stats on dashboard
        Object.keys(data).forEach(key => {
            const element = document.getElementById(`stat-${key}`);
            if (element) {
                element.textContent = data[key];
            }
        });
    }

    _updateActiveUsersList(data) {
        const activeUsersList = document.getElementById('active-users-list');
        if (!activeUsersList) return;
        
        if (data.action === 'login') {
            // Check if user already exists in the list
            const existingUser = document.getElementById(`user-${data.user_id}`);
            if (!existingUser) {
                const userItem = document.createElement('div');
                userItem.id = `user-${data.user_id}`;
                userItem.className = 'flex items-center p-2 border-b';
                userItem.innerHTML = `
                    <div class="w-3 h-3 bg-green-500 rounded-full mr-2"></div>
                    <div>${data.user_name}</div>
                    <div class="text-xs text-gray-500 ml-2">${data.role}</div>
                    <div class="text-xs text-gray-500 ml-auto">${this._formatDateTime(data.timestamp)}</div>
                `;
                activeUsersList.prepend(userItem);
            }
        } else if (data.action === 'logout') {
            const userItem = document.getElementById(`user-${data.user_id}`);
            if (userItem) {
                userItem.remove();
            }
        }
    }

    _prependAuditLog(log) {
        const auditLogsList = document.getElementById('audit-logs-list');
        if (!auditLogsList) return;
        
        const logItem = document.createElement('tr');
        logItem.className = 'bg-yellow-50'; // Highlight new logs
        logItem.innerHTML = `
            <td class="px-4 py-2 border">${log.id}</td>
            <td class="px-4 py-2 border">${log.action}</td>
            <td class="px-4 py-2 border">${log.actor_name || 'System'}</td>
            <td class="px-4 py-2 border">${log.target_type || '-'}</td>
            <td class="px-4 py-2 border">${this._formatDateTime(log.timestamp)}</td>
            <td class="px-4 py-2 border">
                <span class="${log.is_success ? 'text-green-600' : 'text-red-600'}">
                ${log.is_success ? 'Success' : 'Failed'}
                </span>
            </td>
        `;
        
        // Add to beginning of the list
        auditLogsList.insertBefore(logItem, auditLogsList.firstChild);
        
        // Remove highlight after 5 seconds
        setTimeout(() => {
            logItem.classList.remove('bg-yellow-50');
        }, 5000);
    }

    _showSystemAlert(data) {
        // Create alert element
        const alertDiv = document.createElement('div');
        alertDiv.className = `fixed bottom-5 right-5 p-4 rounded shadow-lg z-50 ${data.level === 'error' ? 'bg-red-600' : data.level === 'warning' ? 'bg-yellow-600' : 'bg-green-600'} text-white`;
        
        // Set alert content
        alertDiv.innerHTML = `
            <div class="flex items-center">
                <div class="mr-3">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${data.level === 'error' ? 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' : data.level === 'warning' ? 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' : 'M5 13l4 4L19 7'}"></path>
                    </svg>
                </div>
                <div>
                    <h4 class="font-bold">${data.title}</h4>
                    <p>${data.message}</p>
                </div>
                <button class="ml-auto" onclick="this.parentNode.parentNode.remove()">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
        
        // Add to DOM
        document.body.appendChild(alertDiv);
        
        // Auto-remove after timeout
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, data.timeout || 5000);
    }
    
    _updateUserActivity(data) {
        const activityLog = document.getElementById('user-activity-log');
        if (!activityLog) return;
        
        // Create activity item
        const activityItem = document.createElement('div');
        activityItem.className = 'p-3 border-b border-gray-200 flex items-center';
        
        // Set activity icon based on action type
        let iconHtml = '';
        if (data.action_type === 'login') {
            iconHtml = `<div class="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center mr-3">
                <svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                </svg>
            </div>`;
        } else if (data.action_type === 'logout') {
            iconHtml = `<div class="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center mr-3">
                <svg class="w-4 h-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
                </svg>
            </div>`;
        } else {
            iconHtml = `<div class="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center mr-3">
                <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
            </div>`;
        }
        
        // Fill activity content
        activityItem.innerHTML = `
            ${iconHtml}
            <div class="flex-grow">
                <p class="text-sm">
                    <span class="font-medium">${data.user_name}</span> 
                    ${data.action_type} - ${data.details || ''}
                </p>
                <p class="text-xs text-gray-500">${this._formatDateTime(data.timestamp)}</p>
            </div>
        `;
        
        // Add to activity log
        activityLog.insertBefore(activityItem, activityLog.firstChild);
        
        // Limit to 50 entries
        while (activityLog.children.length > 50) {
            activityLog.removeChild(activityLog.lastChild);
        }
    }
    
    _showNotification(message, type = 'success') {
        const notificationContainer = document.getElementById('notification-container');
        if (!notificationContainer) return;
        
        const notification = document.createElement('div');
        notification.className = `p-3 rounded shadow-md mb-2 ${
            type === 'success' ? 'bg-green-600' : 
            type === 'error' ? 'bg-red-600' : 
            type === 'warning' ? 'bg-yellow-600' : 'bg-blue-600'
        } text-white`;
        
        notification.textContent = message;
        
        notificationContainer.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
    
    _formatDateTime(timestamp) {
        if (!timestamp) return 'unknown time';
        
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    }

    _initializeAdminManage() {
        console.log('Initializing admin management page socket handlers');
        
        // Handle dashboard stats updates
        this.socketManager.on('dashboard_stats_update', (data) => {
            console.log('Received dashboard stats update:', data);
            
            // Update office admin stats
            if (data.active_office_admins !== undefined) {
                const activeAdminsElement = document.getElementById('active-admins-count');
                if (activeAdminsElement) {
                    activeAdminsElement.textContent = data.active_office_admins;
                }
            }
            
            if (data.unassigned_admins !== undefined) {
                const unassignedAdminsElement = document.getElementById('unassigned-admins-count');
                if (unassignedAdminsElement) {
                    unassignedAdminsElement.textContent = data.unassigned_admins;
                }
            }
            
            if (data.total_offices !== undefined) {
                const totalOfficesElement = document.getElementById('total-offices-count');
                if (totalOfficesElement) {
                    totalOfficesElement.textContent = data.total_offices;
                }
            }
            
            if (data.unassigned_offices !== undefined) {
                const unassignedOfficesElement = document.getElementById('unassigned-offices-count');
                if (unassignedOfficesElement) {
                    unassignedOfficesElement.textContent = data.unassigned_offices;
                }
            }
        });
        
        // Handle admin added event
        this.socketManager.on('admin_added', (data) => {
            console.log('Admin added:', data);
            this._updateAdminTable(data, 'add');
        });
        
        // Handle admin updated event
        this.socketManager.on('admin_updated', (data) => {
            console.log('Admin updated:', data);
            this._updateAdminTable(data, 'update');
        });
        
        // Handle admin deleted event
        this.socketManager.on('admin_deleted', (data) => {
            console.log('Admin deleted:', data);
            this._updateAdminTable(data, 'delete');
        });
        
        // Handle office admin removed from office
        this.socketManager.on('office_admin_removed', (data) => {
            console.log('Office admin removed:', data);
            this._updateAdminOfficeAssignment(data.admin_id, null);
        });
        
        // Handle admin password reset
        this.socketManager.on('admin_password_reset', (data) => {
            console.log('Admin password reset:', data);
            this._showNotification(`Password reset successfully for ${data.admin_name}`, 'success');
        });
    }

    // Add this helper method to update the admin table
_updateAdminTable(adminData, action) {
    const adminTable = document.getElementById('admin-table');
    if (!adminTable) return;
    
    const adminTableBody = adminTable.querySelector('tbody') || adminTable;
    
    if (action === 'add') {
        // Create new row for the admin
        const newRow = document.createElement('tr');
        newRow.id = `admin-row-${adminData.id}`;
        newRow.innerHTML = this._generateAdminRowHTML(adminData);
        adminTableBody.prepend(newRow);
        
        // Highlight the new row
        newRow.classList.add('bg-green-50');
        setTimeout(() => {
            newRow.classList.remove('bg-green-50');
        }, 5000);
        
        this._showNotification(`Added new admin: ${adminData.first_name} ${adminData.last_name}`, 'success');
    } 
    else if (action === 'update') {
        // Find existing row
        const existingRow = document.getElementById(`admin-row-${adminData.id}`);
        if (existingRow) {
            existingRow.innerHTML = this._generateAdminRowHTML(adminData);
            
            // Highlight the updated row
            existingRow.classList.add('bg-yellow-50');
            setTimeout(() => {
                existingRow.classList.remove('bg-yellow-50');
            }, 5000);
            
            this._showNotification(`Updated admin: ${adminData.first_name} ${adminData.last_name}`, 'success');
        }
    }
    else if (action === 'delete') {
        // Find and remove the row
        const existingRow = document.getElementById(`admin-row-${adminData.id}`);
        if (existingRow) {
            // Fade out effect
            existingRow.style.transition = 'opacity 0.5s';
            existingRow.style.opacity = '0';
            
            setTimeout(() => {
                existingRow.remove();
            }, 500);
            
            this._showNotification(`Deleted admin: ${adminData.name}`, 'success');
        }
    }
}

// Helper to generate admin row HTML
_generateAdminRowHTML(admin) {
    return `
        <td class="px-4 py-2 border">${admin.id}</td>
        <td class="px-4 py-2 border">
            <div class="flex items-center">
                ${admin.profile_pic ? 
                    `<img src="/static/${admin.profile_pic}" class="w-8 h-8 rounded-full mr-2">` : 
                    `<div class="w-8 h-8 bg-gray-200 rounded-full mr-2 flex items-center justify-center">
                        <span class="text-gray-500 text-xs">${admin.first_name[0]}${admin.last_name[0]}</span>
                    </div>`
                }
                <span>${admin.first_name} ${admin.middle_name ? admin.middle_name + ' ' : ''}${admin.last_name}</span>
            </div>
        </td>
        <td class="px-4 py-2 border">${admin.email}</td>
        <td class="px-4 py-2 border">${admin.office_name || 'Not Assigned'}</td>
        <td class="px-4 py-2 border">
            <span class="px-2 py-1 rounded-full ${admin.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                ${admin.is_active ? 'Active' : 'Inactive'}
            </span>
        </td>
        <td class="px-4 py-2 border">
            <div class="flex space-x-2">
                <button class="bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600" 
                        onclick="editAdmin(${admin.id})">
                    Edit
                </button>
                <button class="bg-red-500 text-white px-2 py-1 rounded hover:bg-red-600"
                        onclick="deleteAdmin(${admin.id})">
                    Delete
                </button>
            </div>
        </td>
    `;
}

// Helper to update office assignment display
_updateAdminOfficeAssignment(adminId, officeName) {
    const adminRow = document.getElementById(`admin-row-${adminId}`);
    if (adminRow) {
        const officeCell = adminRow.querySelector('td:nth-child(4)');
        if (officeCell) {
            officeCell.textContent = officeName || 'Not Assigned';
            
            // Highlight the cell
            officeCell.classList.add('bg-yellow-100');
            setTimeout(() => {
                officeCell.classList.remove('bg-yellow-100');
            }, 5000);
        }
    }
}


    }
    
    
    // Export the AdminSocketManager class for usage
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = AdminSocketManager;
    } else {
        // Create global instance when in browser
        window.adminSocketManager = new AdminSocketManager(window.socketManager);
        
        // Initialize when DOM is ready
        document.addEventListener('DOMContentLoaded', () => {
            window.adminSocketManager.initialize();
        });
    }