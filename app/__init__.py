from flask import Flask 
from .extensions import db, socketio  # Import socketio from extensions
from pathlib import Path
from flask_login import LoginManager, current_user
from flask import g
from flask_wtf.csrf import CSRFProtect

# Don't put monkey_patch here, as it should be in run.py BEFORE any imports

login_manager = LoginManager() 

def create_app():
    root_path = Path(__file__).parent.parent

    app = Flask(__name__,
                template_folder=str(root_path / "templates"),
                static_folder=str(root_path / "static"))
                
    app.config.from_object('config.Config')

    # Set file upload folder and allowed extensions
    app.config['UPLOAD_FOLDER'] = str(root_path / 'static' / 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # max file size 16MB

    db.init_app(app)
    login_manager.init_app(app)
    csrf = CSRFProtect(app)
    login_manager.login_view = 'auth.login' 
    
    socketio.init_app(app)
    
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .admin import admin_bp
    from .office.routes import office_bp
    from .student.routes import student_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(office_bp)
    app.register_blueprint(student_bp)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @app.context_processor
    def inject_user():
        return dict(current_user=current_user)
    
    # Initialize websockets within the app context
    with app.app_context():
        from app.websockets import init_app as init_websocket
        init_websocket()
    
    return app