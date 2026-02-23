# Configuration for Admin Dashboard - Direct Firebase

# Flask Configuration
SECRET_KEY = "your-secret-key-change-in-production"

# Firebase Service Account
SERVICE_ACCOUNT_PATH = "/etc/secrets/serviceAccountKey.json"

# Session Configuration
SESSION_COOKIE_SECURE = True  # HTTPS on Render
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
