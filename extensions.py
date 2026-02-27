from flask_login import LoginManager
import firebase_admin
from firebase_admin import firestore

class _FirestoreExtension:
    def __init__(self):
        self.db = None

    def init_app(self, app):
        # Ensure Firebase app is initialized before getting the client
        if not firebase_admin._apps:
            raise RuntimeError("Firebase Admin SDK not initialized. Call firebase_admin.initialize_app() first.")
        self.db = firestore.client()
        app.extensions['firestore'] = self.db

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

# Create an instance of the Firestore extension
firestore_extension = _FirestoreExtension()
