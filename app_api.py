"""
FRIZZLY Admin Dashboard - API Version
Uses API server instead of direct Firebase access
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import requests
from datetime import datetime
import os
import time
import json
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
from api_client import FrizzlyAPIClient

# Import configuration
try:
    from config import API_BASE_URL, SECRET_KEY
except ImportError:
    API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5000')
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')

# Initialize API client
api_client = FrizzlyAPIClient(base_url=API_BASE_URL)

# Helper function to normalize order data
def normalize_order_data(order_dict):
    """Ensure order data has proper types for template rendering"""
    if 'items' in order_dict and not isinstance(order_dict['items'], list):
        order_dict['items'] = []
    
    # Convert timestamp to createdAt string for display
    if 'timestamp' in order_dict and order_dict['timestamp']:
        try:
            # Handle Firestore Timestamp object
            if hasattr(order_dict['timestamp'], 'timestamp'):
                ts = order_dict['timestamp'].timestamp()
            else:
                ts = order_dict['timestamp'] / 1000 if order_dict['timestamp'] > 1e12 else order_dict['timestamp']
            order_dict['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            order_dict['createdAt'] = 'N/A'
    elif 'createdAt' not in order_dict:
        order_dict['createdAt'] = 'N/A'
    
    return order_dict

def log_activity(action, details, user_id=None):
    """Helper function to log admin activities via API"""
    try:
        # current_user and request.remote_addr are available in app_api.py
        api_client.log_activity(
            action,
            details,
            user_id or (current_user.id if current_user.is_authenticated else 'system'),
            current_user.name if current_user.is_authenticated else 'System',
            request.remote_addr
        )
    except Exception as e:
        app.logger.error(f"Error logging activity via API: {e}")

# In-memory cache for categories
_category_cache = {'data': [], 'timestamp': 0}
_CATEGORY_CACHE_TTL = 300 # Cache for 5 minutes (300 seconds)

def get_cached_categories():
    global _category_cache
    current_time = datetime.now().timestamp()
    if (current_time - _category_cache['timestamp']) > _CATEGORY_CACHE_TTL:
        app.logger.info("Refreshing category cache from API.")
        try:
            categories = api_client.get_product_categories()
            if categories:
                _category_cache['data'] = sorted(list(set(categories))) # Ensure unique and sorted
            else:
                _category_cache['data'] = ['Fruits', 'Vegetables', 'Organic', 'Others'] # Fallback
            _category_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing category cache from API.")
            # Return defaults on error or existing cache if available
            if not _category_cache['data']:
                _category_cache['data'] = ['Fruits', 'Vegetables', 'Organic', 'Others']
    
    return _category_cache['data']

# In-memory cache for drivers (optional, but good for frequently accessed lists)
_driver_cache = {'data': [], 'timestamp': 0}
_DRIVER_CACHE_TTL = 60 # Cache for 1 minute

def get_available_drivers():
    global _driver_cache
    current_time = datetime.now().timestamp()
    if (current_time - _driver_cache['timestamp']) > _DRIVER_CACHE_TTL:
        app.logger.info("Refreshing driver cache from API.")
        try:
            drivers = api_client.get_available_drivers()
            _driver_cache['data'] = [d for d in drivers if d.get('status') == 'available']
            _driver_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing driver cache from API.")
            if not _driver_cache['data']:
                _driver_cache['data'] = [] # Ensure it's an empty list on error
    return _driver_cache['data']

# Constants
VALID_ORDER_STATUSES = [
    'PENDING', 'CONFIRMED', 'PREPARING_ORDER', 'READY_FOR_PICKUP',
    'ON_WAY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERY_ATTEMPT_FAILED',
    'CANCELLED', 'RETURNED'
]

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Configure logging
log_file = os.path.join(os.path.dirname(__file__), 'app.log')
handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email, name, token, role='admin'):
        self.id = id
        self.email = email
        self.name = name
        self.token = token
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    # Load user from session
    if 'user_data' in session:
        data = session['user_data']
        return User(data['id'], data['email'], data['name'], data['token'], data.get('role', 'admin'))
    return None

def role_required(roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                app.logger.warning(f"Unauthorized access attempt by user {current_user.id} (role: {current_user.role}) to a role-restricted resource: {request.path}")
                abort(403) # Forbidden
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

# API Helper Functions
def api_request(method, endpoint, data=None, params=None):
    """Make API request with authentication"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    if current_user.is_authenticated:
        headers['Authorization'] = f'Bearer {current_user.token}'
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            return None
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            app.logger.error(f"API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        app.logger.error(f"API request failed: {e}")
        return None

def paginate_list(items, page=1, per_page=20):
    """Simple pagination for lists"""
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    
    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.total_pages = max(1, (total + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = end < total
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if end < total else None
    
    return Pagination(items[start:end], page, per_page, total)

# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Call API login endpoint
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/admin/login",
                json={'email': email, 'password': password},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Use the token (admin ID) for authentication
                user = User(
                    data['adminId'],
                    data['email'],
                    data['name'],
                    data['token']  # This is the admin ID
                )
                
                # Store user data in session
                session['user_data'] = {
                    'id': data['adminId'],
                    'email': data['email'],
                    'name': data['name'],
                    'token': data['token'],
                    'role': 'admin'
                }
                
                login_user(user)
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                error_msg = response.json().get('error', 'Invalid credentials')
                flash(f'Login failed: {error_msg}', 'danger')
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash('Login failed. Please try again.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_data', None)
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    dashboard_stats = api_client.get_dashboard_stats()
    
    # Ensure all expected keys are present, with defaults
    stats = {
        'total_orders': dashboard_stats.get('total_orders', 0),
        'total_revenue': dashboard_stats.get('total_revenue', 0),
        'total_products': dashboard_stats.get('total_products', 0),
        'total_users': dashboard_stats.get('total_users', 0),
        'pending_orders': dashboard_stats.get('pending_orders', 0),
        'low_stock_products': dashboard_stats.get('low_stock_products', 0)
    }
    
    recent_orders_data = []
    # Normalize recent orders if they come from the API
    for order in dashboard_stats.get('recent_orders', []):
        order['id'] = order.get('id', order.get('orderId')) # Ensure 'id' is present for url_for
        recent_orders_data.append(normalize_order_data(order))

    return render_template('dashboard.html',
                         stats=stats,
                         recent_orders=recent_orders_data)

# ==================== NOTIFICATION POLLING ====================

@app.route('/api/stream-orders')
@login_required
def stream_orders():
    """Server-Sent Events endpoint - proxies from API server"""
    # Get token BEFORE generator (inside request context)
    token = session.get('user_data', {}).get('token')
    
    if not token:
        return jsonify({'error': 'No authentication token'}), 401
    
    def generate():
        try:
            print(f"🔴 Dashboard SSE: Connecting to API with token: {token[:10]}...")
            
            # Connect to API SSE endpoint
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(
                f"{API_BASE_URL}/api/admin/stream/orders",
                headers=headers,
                stream=True,
                timeout=None
            )
            
            print(f"🔴 Dashboard SSE: Connected to API, status: {response.status_code}")
            
            # Stream events from API
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    print(f"🔴 Dashboard SSE: Received: {decoded[:100]}")
                    yield decoded + '\n'
                else:
                    yield '\n'
                    
        except Exception as e:
            print(f"🔴 Dashboard SSE: Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

# DEPRECATED: Polling replaced with real-time Firestore listeners
# @app.route('/api/poll-orders')
# @login_required
# def poll_orders():
#     """Endpoint for polling new orders"""
#     result = api_request('GET', '/api/admin/orders')
#     if result:
#         # Return only recent orders (last 50) to reduce data transfer
#         orders = sorted(
#             result.get('orders', []),
#             key=lambda x: x.get('timestamp', 0),
#             reverse=True
#         )[:50]
#         return jsonify({'orders': orders})
#     return jsonify({'orders': []})

@app.route('/api/save-fcm-token', methods=['POST'])
@login_required
def save_fcm_token():
    """Save FCM token for admin"""
    try:
        data = request.json
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Token required'}), 400
        
        # Save token via API
        result = api_request('POST', '/api/admin/fcm-token', data={'token': token})
        
        if result:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save token'}), 500
    except Exception as e:
        app.logger.error(f"Error saving FCM token: {e}")
        return jsonify({'error': 'Failed to save token'}), 500

# ==================== ORDERS ====================

@app.route('/orders')
@login_required
def orders():
    result = api_request('GET', '/api/admin/orders')
    orders_list = result.get('orders', []) if result else []
    
    # Format timestamps for all orders
    for order in orders_list:
        if 'timestamp' in order and order['timestamp']:
            try:
                ts = order['timestamp']
                if ts > 1e12:  # Milliseconds
                    ts = ts / 1000
                from datetime import datetime
                order['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            except:
                order['createdAt'] = 'N/A'
        elif 'createdAt' not in order:
            order['createdAt'] = 'N/A'
    
    # Sort by timestamp
    orders_list = sorted(orders_list, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    pagination = paginate_list(orders_list, page=page, per_page=20)
    
    return render_template('orders.html', 
                         orders=pagination.items,
                         pagination=pagination,
                         valid_statuses=VALID_ORDER_STATUSES)

@app.route('/orders/<order_id>')
@login_required
def order_detail(order_id):
    result = api_request('GET', f'/api/admin/orders/{order_id}')
    order = result.get('order') if result else None
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('orders'))
    
    # Format timestamp to readable date
    if 'timestamp' in order and order['timestamp']:
        try:
            # Handle milliseconds timestamp
            ts = order['timestamp']
            if ts > 1e12:  # Milliseconds
                ts = ts / 1000
            from datetime import datetime
            order['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            order['createdAt'] = 'N/A'
    elif 'createdAt' not in order:
        order['createdAt'] = 'N/A'
    
    return render_template('order_detail.html', 
                         order=order,
                         valid_statuses=VALID_ORDER_STATUSES,
                         available_drivers=get_available_drivers())

@app.route('/orders/<order_id>/update', methods=['POST'])
@login_required
def update_order_status(order_id):
    status = request.form.get('status')
    
    result = api_request('PUT', f'/api/admin/orders/{order_id}', data={'status': status})
    
    if result:
        flash('Order status updated successfully', 'success')
    else:
        flash('Failed to update order status', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/orders/<order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    result = api_request('DELETE', f'/api/admin/orders/{order_id}')
    
    if result:
        flash('Order deleted successfully', 'success')
    else:
        flash('Failed to delete order', 'danger')
    
    return redirect(url_for('orders'))

# ==================== PRODUCTS ====================

@app.route('/products')
@login_required
def products():
    result = api_request('GET', '/api/products', params={'active': 'false', 'limit': 1000})
    products_list = result.get('products', []) if result else []
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    pagination = paginate_list(products_list, page=page, per_page=20)
    
    return render_template('products.html', 
                         products=pagination.items,
                         pagination=pagination)

@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    categories = get_cached_categories()
    if request.method == 'POST':
        product_data = {
            'name': request.form.get('name'),
            'price': float(request.form.get('price', 0)),
            'category': request.form.get('category'),
            'description': request.form.get('description', ''),
            'imageUrl': request.form.get('imageUrl', ''),
            'inStock': request.form.get('inStock') == 'on',
            'isActive': request.form.get('isActive') == 'on'
        }
        
        result = api_client.create_product(product_data)
        
        if result:
            flash('Product added successfully', 'success')
            return redirect(url_for('products'))
        else:
            flash('Failed to add product', 'danger')
    
    return render_template('add_product.html', categories=categories)

@app.route('/products/<product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    categories = get_cached_categories()
    if request.method == 'POST':
        product_data = {
            'name': request.form.get('name'),
            'price': float(request.form.get('price', 0)),
            'category': request.form.get('category'),
            'description': request.form.get('description', ''),
            'imageUrl': request.form.get('imageUrl', ''),
            'inStock': request.form.get('inStock') == 'on',
            'isActive': request.form.get('isActive') == 'on'
        }
        
        result = api_client.update_product(product_id, product_data)
        
        if result:
            flash('Product updated successfully', 'success')
            return redirect(url_for('products'))
        else:
            flash('Failed to update product', 'danger')
    
    # Get product details
    result = api_request('GET', '/api/products')
    products_list = result.get('products', []) if result else []
    product = next((p for p in products_list if p.get('id') == product_id), None)
    
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('products'))
    
    return render_template('edit_product.html', 
                         product=product,
                         categories=categories)

@app.route('/products/<product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    result = api_request('DELETE', f'/api/products/{product_id}')
    
    if result:
        flash('Product deleted successfully', 'success')
    else:
        flash('Failed to delete product', 'danger')
    
    return redirect(url_for('products'))

# ==================== USERS ====================

@app.route('/users')
@login_required
def users():
    result = api_request('GET', '/api/admin/users')
    print(f"DEBUG: Users API result: {result}")
    users_list = result.get('users', []) if result else []
    print(f"DEBUG: Users list length: {len(users_list)}")
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    pagination = paginate_list(users_list, page=page, per_page=20)
    
    return render_template('users.html', 
                         users=pagination.items,
                         pagination=pagination)

# ==================== ANALYTICS ====================

@app.route('/analytics')
@login_required
def analytics():
    result = api_request('GET', '/api/admin/analytics')
    data = {
        'total_orders': result.get('totalOrders', 0) if result else 0,
        'total_revenue': result.get('totalRevenue', 0) if result else 0,
        'status_counts': result.get('statusCounts', {}) if result else {}
    }
    return render_template('analytics.html', data=data)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# ==================== STUB ROUTES (Not Implemented Yet) ====================

@app.route('/delivery')
@login_required
def delivery_logistics():
    flash('Delivery logistics not yet implemented in API version', 'info')
    return redirect(url_for('orders'))

@app.route('/stock')
@login_required
def stock_management():
    try:
        products = api_client.get_product_stock()
        # The API should ideally return them sorted, but we can sort here as a fallback
        products.sort(key=lambda x: x.get('stock', 0))
        return render_template('stock.html', products=products)
    except Exception as e:
        app.logger.exception("Error loading stock data from API")
        flash('Error loading stock data', 'danger')
        return render_template('stock.html', products=[])

# ==================== DRIVERS ====================

@app.route('/drivers')
@login_required
@role_required(['admin', 'order_manager', 'viewer'])
def drivers():
    try:
        all_drivers = api_client.get_all_drivers()
        
        # Calculate stats
        total_drivers = len(all_drivers)
        available = len([d for d in all_drivers if d.get('status') == 'available'])
        on_delivery = len([d for d in all_drivers if d.get('status') == 'on_delivery'])
        offline = len([d for d in all_drivers if d.get('status') == 'offline'])
        
        stats = {
            'total': total_drivers,
            'available': available,
            'on_delivery': on_delivery,
            'offline': offline
        }
        
        return render_template('drivers.html', drivers=all_drivers, stats=stats)
    except Exception as e:
        app.logger.exception("Error loading drivers from API")
        flash('Error loading drivers. Please try again.', 'danger')
        return render_template('drivers.html', drivers=[], stats={})

@app.route('/drivers/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_driver():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        vehicle_type = request.form.get('vehicle_type')
        vehicle_number = request.form.get('vehicle_number')
        
        if not name or not phone:
            flash('Name and phone are required', 'danger')
            return render_template('add_driver.html')
        
        driver_data = {
            'name': name,
            'phone': phone,
            'email': email or '',
            'vehicleType': vehicle_type or 'bike',
            'vehicleNumber': vehicle_number or '',
            'status': 'available',
            'totalDeliveries': 0,
            'rating': 5.0,
            # 'createdAt': firestore.SERVER_TIMESTAMP # API should handle timestamp
        }
        
        try:
            driver_id = api_client.create_driver(driver_data)
            if driver_id:
                log_activity('ADD_DRIVER', f'Added driver: {name}')
                flash(f'Driver {name} added successfully', 'success')
                return redirect(url_for('drivers'))
            else:
                flash('Failed to add driver via API', 'danger')
        except Exception as e:
            app.logger.exception("Error adding driver via API")
            flash(f'Error adding driver: {str(e)}', 'danger')
    
    return render_template('add_driver.html')

@app.route('/drivers/<driver_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_driver(driver_id):
    driver = api_client.get_driver(driver_id)
    if not driver:
        flash('Driver not found', 'danger')
        return redirect(url_for('drivers'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        vehicle_type = request.form.get('vehicle_type')
        vehicle_number = request.form.get('vehicle_number')
        status = request.form.get('status')
        
        if not name or not phone:
            flash('Name and phone are required', 'danger')
            return render_template('edit_driver.html', driver=driver)
        
        updates = {
            'name': name,
            'phone': phone,
            'email': email or '',
            'vehicleType': vehicle_type or 'bike',
            'vehicleNumber': vehicle_number or '',
            'status': status or 'available',
            # 'updatedAt': firestore.SERVER_TIMESTAMP # API should handle timestamp
        }
        
        try:
            if api_client.update_driver(driver_id, updates):
                flash('Driver updated successfully', 'success')
                return redirect(url_for('drivers'))
            else:
                flash('Failed to update driver via API', 'danger')
        except Exception as e:
            app.logger.exception("Error updating driver via API")
            flash(f'Error updating driver: {str(e)}', 'danger')
    
    return render_template('edit_driver.html', driver=driver)

@app.route('/drivers/<driver_id>/delete', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_driver(driver_id):
    try:
        if api_client.delete_driver(driver_id):
            log_activity('DELETE_DRIVER', f'Deleted driver: {driver_id}')
            flash('Driver deleted successfully', 'success')
        else:
            flash('Failed to delete driver via API', 'danger')
    except Exception as e:
        app.logger.exception("Error deleting driver via API")
        flash(f'Error deleting driver: {str(e)}', 'danger')
    
    return redirect(url_for('drivers'))

@app.route('/drivers/<driver_id>')
@login_required
@role_required(['admin', 'order_manager', 'viewer'])
def driver_detail(driver_id):
    driver = api_client.get_driver(driver_id)
    if not driver:
        flash('Driver not found', 'danger')
        return redirect(url_for('drivers'))
    
    # Get driver's delivery history via API
    deliveries = []
    try:
        api_deliveries = api_client.get_orders_by_driver(driver_id)
        for order_data in api_deliveries:
            # Ensure order_data has an 'id' field, which the API should provide
            if 'id' not in order_data and 'orderId' in order_data:
                order_data['id'] = order_data['orderId'] # Use orderId as id if id is missing
            deliveries.append(normalize_order_data(order_data))
    except Exception as e:
        app.logger.exception("Error loading driver deliveries from API")
        flash('Error loading driver deliveries.', 'danger')
    
    return render_template('driver_detail.html', driver=driver, deliveries=deliveries)

@app.route('/revenue')
@login_required
def revenue():
    try:
        data = api_client.get_revenue_data()
        return render_template('revenue.html', data=data)
    except Exception as e:
        app.logger.exception("Error loading revenue data from API")
        flash('Error loading revenue data', 'danger')
        return render_template('revenue.html', data={})

@app.route('/notifications')
@login_required
def notifications():
    try:
        all_notifications = api_client.get_notifications()
        
        # Format timestamps for display if needed (assuming API returns raw timestamps)
        for notif in all_notifications:
            if 'timestamp' in notif and notif['timestamp']:
                try:
                    # Assuming timestamp is in milliseconds
                    ts = notif['timestamp'] / 1000
                    notif['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    notif['createdAt'] = 'N/A'
            elif 'createdAt' not in notif:
                notif['createdAt'] = 'N/A'

        return render_template('notifications.html', notifications=all_notifications)
    except Exception as e:
        app.logger.exception("Error loading notifications from API")
        flash('Error loading notifications. Please try again.', 'danger')
        return render_template('notifications.html', notifications=[])

@app.route('/notifications/send-bulk', methods=['GET', 'POST'])
@login_required
def send_bulk_notification():
    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')
        
        if not title or not message:
            flash('Title and message are required', 'danger')
            return redirect(url_for('send_bulk_notification'))
        
        try:
            success = api_client.send_bulk_notification(title, message)
            if success:
                log_activity('SEND_BULK_NOTIFICATION', f'Sent bulk notification: "{title}"')
                flash(f'Bulk notification sent successfully', 'success')
            else:
                flash('Failed to send bulk notification via API', 'danger')
        except Exception as e:
            app.logger.exception("Error sending bulk notification via API")
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('send_bulk_notification.html')

@app.route('/activity-logs')
@login_required
def activity_logs():
    try:
        logs = api_client.get_activity_logs()
        
        # Format timestamps for display if needed (assuming API returns raw timestamps)
        for log_entry in logs:
            if 'timestamp' in log_entry and log_entry['timestamp']:
                try:
                    # Assuming timestamp is in milliseconds
                    ts = log_entry['timestamp'] / 1000
                    log_entry['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    log_entry['createdAt'] = 'N/A'
            elif 'createdAt' not in log_entry:
                log_entry['createdAt'] = 'N/A'

        return render_template('activity_logs.html', logs=logs)
    except Exception as e:
        app.logger.exception("Error loading activity logs from API")
        flash('Error loading activity logs. Please try again.', 'danger')
        return render_template('activity_logs.html', logs=[])

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    admin_profile = api_client.get_admin_profile()
    if not admin_profile:
        flash('Failed to load admin profile.', 'danger')
        admin_profile = {'name': current_user.name, 'email': current_user.email} # Fallback
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        
        if name and email:
            profile_data = {'name': name, 'email': email}
            try:
                success = api_client.update_admin_profile(profile_data)
                if success:
                    log_activity('UPDATE_PROFILE', f'Updated admin profile: {name}')
                    flash('Settings updated successfully', 'success')
                    # Update current_user in session if needed
                    current_user.name = name
                    current_user.email = email
                else:
                    flash('Failed to update settings via API', 'danger')
            except Exception as e:
                app.logger.exception("Error updating settings via API")
                flash(f'Error updating settings: {str(e)}', 'danger')
        else:
            flash('Name and Email are required.', 'danger')
    
    return render_template('settings.html', admin_profile=admin_profile)

@app.route('/users/<user_id>')
@login_required
def user_detail(user_id):
    result = api_request('GET', f'/api/admin/users/{user_id}')
    
    if not result or 'user' not in result:
        flash('User not found', 'danger')
        return redirect(url_for('users'))
    
    user = result['user']
    orders = result.get('orders', [])
    
    # Format createdAt timestamp
    if 'createdAt' in user and user['createdAt']:
        try:
            ts = user['createdAt']
            if ts > 1e12:  # Milliseconds
                ts = ts / 1000
            user['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            user['createdAt'] = 'N/A'
    else:
        user['createdAt'] = 'N/A'
    
    # Format lastLogin timestamp
    if 'lastLogin' in user and user['lastLogin']:
        try:
            # Handle Firestore Timestamp object
            if isinstance(user['lastLogin'], dict) and '_seconds' in user['lastLogin']:
                ts = user['lastLogin']['_seconds']
            else:
                ts = user['lastLogin']
            if ts > 1e12:
                ts = ts / 1000
            user['lastLogin'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    # Format lastSignIn timestamp
    if 'lastSignIn' in user and user['lastSignIn']:
        try:
            ts = user['lastSignIn']
            if ts > 1e12:
                ts = ts / 1000
            user['lastSignIn'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    # Ensure phone is available
    if 'phone' not in user or not user['phone']:
        user['phone'] = user.get('phoneNumber', 'N/A')
    
    return render_template('user_detail.html', user=user, orders=orders)

@app.route('/orders/export')
@login_required
def export_orders():
    try:
        csv_data = api_client.export_orders()
        if csv_data:
            log_activity('EXPORT_ORDERS', 'Exported orders CSV')
            from flask import make_response
            output = make_response(csv_data)
            output.headers["Content-Disposition"] = "attachment; filename=orders.csv"
            output.headers["Content-type"] = "text/csv"
            return output
        else:
            flash('Failed to export orders via API', 'danger')
    except Exception as e:
        app.logger.exception("Error exporting orders via API")
        flash('Error exporting orders', 'danger')
    
    return redirect(url_for('orders'))

@app.route('/export/revenue')
@login_required
def export_revenue():
    try:
        csv_data = api_client.export_revenue()
        if csv_data:
            log_activity('EXPORT_REVENUE', 'Exported revenue CSV')
            from flask import make_response
            output = make_response(csv_data)
            output.headers["Content-Disposition"] = "attachment; filename=revenue_report.csv"
            output.headers["Content-type"] = "text/csv"
            return output
        else:
            flash('Failed to export revenue via API', 'danger')
    except Exception as e:
        app.logger.exception("Error exporting revenue via API")
        flash('Error exporting revenue', 'danger')
    
    return redirect(url_for('revenue'))

@app.route('/orders/filter', methods=['GET'])
@login_required
def filter_orders():
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    
    try:
        orders_list = api_client.get_all_orders(
            status=status,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount
        )
        
        # Format timestamps for all orders
        for order in orders_list:
            if 'timestamp' in order and order['timestamp']:
                try:
                    ts = order['timestamp']
                    if ts > 1e12:  # Milliseconds
                        ts = ts / 1000
                    from datetime import datetime
                    order['createdAt'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    order['createdAt'] = 'N/A'
            elif 'createdAt' not in order:
                order['createdAt'] = 'N/A'
        
        # Pagination (client-side for filtered results, or API should handle)
        page = request.args.get('page', 1, type=int)
        pagination = paginate_list(orders_list, page=page, per_page=20)

        return render_template('orders.html', orders=pagination.items, pagination=pagination, valid_statuses=VALID_ORDER_STATUSES)
    except Exception as e:
        app.logger.exception("Error filtering orders via API")
        flash('Error filtering orders', 'danger')
        return redirect(url_for('orders'))

@app.route('/orders/bulk-update', methods=['POST'])
@login_required
def bulk_update_status():
    new_status = request.form.get('status')
    order_ids = request.form.getlist('order_ids')
    
    if not new_status or not order_ids:
        flash('Please select orders and status', 'warning')
        return redirect(url_for('orders'))
    
    if new_status not in VALID_ORDER_STATUSES:
        flash('Invalid status', 'danger')
        return redirect(url_for('orders'))
    
    # Update each order
    updated = 0
    for order_id in order_ids:
        result = api_request('PUT', f'/api/admin/orders/{order_id}', 
                           data={'status': new_status})
        if result:
            updated += 1
    
    flash(f'Updated {updated} order(s) to {new_status}', 'success')
    return redirect(url_for('orders'))

@app.route('/bulk/delete-products', methods=['POST'])
@login_required
def bulk_delete_products():
    product_ids = request.form.getlist('product_ids')
    
    if not product_ids:
        flash('Please select products', 'danger')
        return redirect(url_for('products'))
    
    try:
        success = api_client.bulk_delete_products(product_ids)
        if success:
            log_activity('BULK_DELETE_PRODUCTS', f'Deleted {len(product_ids)} products')
            flash(f'Deleted {len(product_ids)} products', 'success')
        else:
            flash('Failed to bulk delete products via API', 'danger')
    except Exception as e:
        app.logger.exception("Error in bulk delete via API")
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('products'))

@app.route('/orders/<order_id>/assign-driver', methods=['POST'])
@login_required
def assign_driver(order_id):
    driver_id = request.form.get('driver_id')
    
    if not driver_id:
        flash('No driver selected.', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))

    try:
        success = api_client.assign_driver_to_order(order_id, driver_id)
        if success:
            log_activity('ASSIGN_DRIVER', f'Assigned driver {driver_id} to order {order_id}')
            flash(f'Order assigned to driver {driver_id} and marked as Out For Delivery', 'success')
        else:
            flash('Failed to assign driver via API', 'danger')
    except Exception as e:
        app.logger.exception(f"Error assigning driver {driver_id} to order {order_id} via API")
        flash(f'Error assigning driver: {str(e)}', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/stock/<product_id>/update', methods=['POST'])
@login_required
def update_stock(product_id):
    new_stock = request.form.get('stock', type=int)

    if new_stock is None or new_stock < 0:
        flash('Stock must be a non-negative integer.', 'danger')
        return redirect(url_for('stock_management'))
    
    try:
        success = api_client.update_product_stock(product_id, new_stock)
        if success:
            log_activity('UPDATE_STOCK', f'Updated stock for product {product_id} to {new_stock}')
            flash('Stock updated successfully!', 'success')
        else:
            flash('Failed to update stock via API', 'danger')
    except Exception as e:
        app.logger.exception(f"Error updating stock for product {product_id} via API")
        flash(f'Error updating stock: {str(e)}', 'danger')
    
    return redirect(url_for('stock_management'))

@app.route('/users/send-test-notification', methods=['POST'])
@login_required
def send_test_notification():
    user_id = request.form.get('user_id')
    title = request.form.get('title')
    message = request.form.get('message')
    
    try:
        success = api_client.send_test_notification(user_id, title, message)
        if success:
            flash(f'Test notification sent successfully to user {user_id}!', 'success')
        else:
            flash(f'Failed to send test notification to user {user_id}.', 'danger')
    except Exception as e:
        app.logger.exception(f"Error sending test notification via API for user {user_id}")
        flash(f'Error sending notification: {str(e)}', 'danger')
    
    return redirect(url_for('users'))

@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not all([current_password, new_password, confirm_password]):
        flash('All password fields are required', 'danger')
        return redirect(url_for('settings'))
    
    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('settings'))
    
    try:
        success = api_client.change_admin_password(current_password, new_password)
        if success:
            log_activity('CHANGE_PASSWORD', 'Admin password changed')
            flash('Password changed successfully', 'success')
        else:
            flash('Failed to change password via API. Current password might be incorrect.', 'danger')
    except Exception as e:
        app.logger.exception("Error changing password via API")
        flash(f'Error changing password: {str(e)}', 'danger')
    
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5001)