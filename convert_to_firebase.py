#!/usr/bin/env python3
"""
Convert app_api.py to app.py with direct Firebase connection
Replaces all API calls with direct Firestore operations
"""

import re

def convert_api_to_firebase():
    with open('app_api.py', 'r') as f:
        content = f.read()
    
    # 1. Replace imports
    content = content.replace(
        'from api_client import FrizzlyAPIClient',
        'import firebase_admin\nfrom firebase_admin import credentials, firestore, messaging'
    )
    content = content.replace(
        'import requests',
        '# requests not needed for direct Firebase'
    )
    content = content.replace(
        'from config import API_BASE_URL, SECRET_KEY',
        'from config import SECRET_KEY, SERVICE_ACCOUNT_PATH'
    )
    content = content.replace(
        'from werkzeug.security import generate_password_hash, check_password_hash',
        'from werkzeug.security import check_password_hash'
    )
    
    # 2. Remove API client initialization
    content = re.sub(
        r'# Initialize API client\napi_client = FrizzlyAPIClient\(base_url=API_BASE_URL\)',
        '''# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()''',
        content
    )
    
    # 3. Replace User class to not need token
    content = re.sub(
        r'class User\(UserMixin\):.*?self\.token = token',
        '''class User(UserMixin):
    def __init__(self, uid, email, name, role='admin'):
        self.id = uid
        self.email = email
        self.name = name
        self.role = role''',
        content,
        flags=re.DOTALL
    )
    
    # 4. Replace user_loader
    content = re.sub(
        r'@login_manager\.user_loader\ndef load_user\(user_id\):.*?return None',
        '''@login_manager.user_loader
def load_user(user_id):
    try:
        doc = db.collection('admins').document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return User(user_id, data.get('email'), data.get('name', 'Admin'), data.get('role', 'admin'))
    except Exception as e:
        app.logger.error(f"Error loading user: {e}")
    return None''',
        content,
        flags=re.DOTALL
    )
    
    # 5. Replace login route
    login_replacement = '''@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            admins = db.collection('admins').where('email', '==', email).limit(1).stream()
            admin_doc = next(admins, None)
            
            if admin_doc and check_password_hash(admin_doc.to_dict().get('password', ''), password):
                data = admin_doc.to_dict()
                user = User(admin_doc.id, email, data.get('name', 'Admin'), data.get('role', 'admin'))
                
                session['user_data'] = {
                    'id': admin_doc.id,
                    'email': email,
                    'name': data.get('name', 'Admin'),
                    'role': data.get('role', 'admin')
                }
                
                login_user(user)
                flash('Login successful!', 'success')
                log_activity('login', f'Admin {email} logged in')
                return redirect(url_for('dashboard'))
            
            flash('Invalid credentials', 'danger')
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash('Login failed. Please try again.', 'danger')
    
    return render_template('login.html')'''
    
    content = re.sub(
        r'@app\.route\(\'/login\'.*?return render_template\(\'login\.html\'\)',
        login_replacement,
        content,
        flags=re.DOTALL
    )
    
    # 6. Fix log_activity function
    content = re.sub(
        r'def log_activity\(action, details, user_id=None\):.*?app\.logger\.error\(f"Error logging activity.*?\n',
        '''def log_activity(action, details, user_id=None):
    """Helper function to log admin activities to Firebase"""
    try:
        activity_data = {
            'action': action,
            'details': details,
            'userId': user_id or (current_user.id if current_user.is_authenticated else 'system'),
            'userName': current_user.name if current_user.is_authenticated else 'System',
            'ipAddress': request.remote_addr,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        db.collection('activity_logs').add(activity_data)
    except Exception as e:
        app.logger.error(f"Error logging activity: {e}")
''',
        content,
        flags=re.DOTALL
    )
    
    # 7. Fix get_cached_categories
    content = re.sub(
        r'def get_cached_categories\(\):.*?return _category_cache\[\'data\'\]',
        '''def get_cached_categories():
    global _category_cache
    current_time = datetime.now().timestamp()
    if (current_time - _category_cache['timestamp']) > _CATEGORY_CACHE_TTL:
        app.logger.info("Refreshing category cache from Firebase.")
        try:
            products = db.collection('products').stream()
            categories = set()
            for doc in products:
                cat = doc.to_dict().get('category')
                if cat:
                    categories.add(cat)
            _category_cache['data'] = sorted(list(categories)) if categories else ['Fruits', 'Vegetables', 'Organic', 'Others']
            _category_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing category cache.")
            if not _category_cache['data']:
                _category_cache['data'] = ['Fruits', 'Vegetables', 'Organic', 'Others']
    
    return _category_cache['data']''',
        content,
        flags=re.DOTALL
    )
    
    # 8. Fix get_available_drivers
    content = re.sub(
        r'def get_available_drivers\(\):.*?return _driver_cache\[\'data\'\]',
        '''def get_available_drivers():
    global _driver_cache
    current_time = datetime.now().timestamp()
    if (current_time - _driver_cache['timestamp']) > _DRIVER_CACHE_TTL:
        app.logger.info("Refreshing driver cache from Firebase.")
        try:
            drivers = db.collection('drivers').where('status', '==', 'available').stream()
            _driver_cache['data'] = [{'id': d.id, **d.to_dict()} for d in drivers]
            _driver_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing driver cache.")
            _driver_cache['data'] = []
    
    return _driver_cache['data']''',
        content,
        flags=re.DOTALL
    )
    
    # Save to new file
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("✅ Phase 1 complete: Basic structure converted")
    print("⚠️  Phase 2 needed: Replace all api_client calls with Firebase calls")
    print(f"   Total lines: {len(content.splitlines())}")

if __name__ == '__main__':
    convert_api_to_firebase()
