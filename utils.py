from flask import redirect, url_for, flash
from flask_login import current_user, login_required, UserMixin
from functools import wraps
import firebase_admin
from firebase_admin import firestore, messaging
from datetime import datetime
import time

# Assuming db is initialized in app.py and passed or accessed globally
# For now, we'll assume db is accessible via current_app or similar context in Flask
# Or, we can pass it during blueprint registration if needed.
# For simplicity, let's assume db is imported from app.py for now.

# Constants
VALID_ORDER_STATUSES = [
    'PENDING', 'CONFIRMED', 'PREPARING_ORDER', 'READY_FOR_PICKUP',
    'ON_WAY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERY_ATTEMPT_FAILED',
    'CANCELLED', 'RETURNED'
]

class User(UserMixin):
    def __init__(self, uid, email, role='admin'):
        self.id = uid
        self.email = email
        self.role = role

# Placeholder for db until it's properly imported/passed
# from app import db 

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.role == 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def send_notification(user_id, title, body):
    """Send FCM notification to user"""
    try:
        # Assuming db is accessible here, e.g., from current_app.db or passed in
        # For now, we'll assume firebase_admin.firestore.client() can be called
        db_client = firestore.client() 
        user_doc = db_client.collection('users').document(user_id).get()
        if user_doc.exists:
            fcm_token = user_doc.to_dict().get('fcmToken')
            if fcm_token:
                message = messaging.Message(
                    data={
                        'title': title,
                        'body': body,
                        'type': 'order',
                        'timestamp': str(int(time.time() * 1000))
                    },
                    token=fcm_token
                )
                messaging.send(message)
    except Exception as e:
        # app.logger.error(f"Send notification error: {e}") # Logger not directly accessible here yet
        print(f"Error sending notification: {e}") # Temporary print for debugging
