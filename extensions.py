from flask_login import LoginManager
import firebase_admin
from firebase_admin import firestore

# Initialize Firebase Admin SDK
# This is done in app.py, so we just need the client
db = firestore.client()

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
