from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from firebase_admin import firestore
from google.api_core.exceptions import ResourceExhausted, DeadlineExceeded
from extensions import login_manager, firestore_extension
from utils import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Set timeout to prevent hanging
            admins = firestore_extension.db.collection('admins').where(
                filter=firestore.FieldFilter('email', '==', email)
            ).limit(1).get(timeout=5.0)
            
            if admins:
                admin_doc = admins[0]
                stored_password = admin_doc.to_dict().get('password', '')
                
                if stored_password and check_password_hash(stored_password, password):
                    user = User(admin_doc.id, email, admin_doc.to_dict().get('role', 'admin'))
                    login_user(user, remember=True)
                    current_app.logger.info(f"User {email} logged in successfully")
                    return redirect(url_for('dashboard.dashboard'))
            
            current_app.logger.warning(f"Failed login attempt for {email}")
            flash('Invalid email or password', 'error')
            
        except ResourceExhausted:
            current_app.logger.error("Firebase quota exceeded")
            flash('Service temporarily unavailable. Please try again later.', 'error')
        except DeadlineExceeded:
            current_app.logger.error("Firebase timeout")
            flash('Connection timeout. Please try again.', 'error')
        except Exception as e:
            current_app.logger.error(f"Login error: {type(e).__name__}: {e}")
            flash('Login failed. Please try again.', 'error')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    # Clear all session cache
    session.clear()
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login'))
