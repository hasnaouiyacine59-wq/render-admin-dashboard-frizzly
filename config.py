# Configuration for Admin Dashboard

# API Configuration
# Local development:
# API_BASE_URL = "http://localhost:5000"

# Production (Railway):
API_BASE_URL = "https://apifrizzly-production.up.railway.app"

# Flask Configuration
SECRET_KEY = "your-secret-key-change-in-production"

# Session Configuration
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
