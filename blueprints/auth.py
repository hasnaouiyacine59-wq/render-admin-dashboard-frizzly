from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from ..app import db, login_manager
from ..utils import User # New import for User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard')) # Redirect if already logged in

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            admins = db.collection('admins').where('email', '==', email).limit(1).stream()
            admin_doc = next(admins, None)
            
            if admin_doc and check_password_hash(admin_doc.to_dict().get('password', ''), password):
                user = User(admin_doc.id, email, admin_doc.to_dict().get('role', 'admin'))
                login_user(user)
                return redirect(url_for('dashboard.dashboard'))
            
            flash('Invalid credentials', 'error')
        except Exception as e:
            # app.logger.error(f"Login error: {e}") # Logger not directly accessible here yet
            flash('Login failed', 'error')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# User loader for Flask-Login (needs to be in app.py or accessible globally)
# @login_manager.user_loader
# def load_user(user_id):
#     try:
#         doc = db.collection('admins').document(user_id).get()
#         if doc.exists:
#             data = doc.to_dict()
#             return User(user_id, data.get('email'), data.get('role', 'admin'))
#     except:
#         pass
#     return None
