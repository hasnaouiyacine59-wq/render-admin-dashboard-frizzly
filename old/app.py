import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime
import os
from functools import wraps
import threading
import logging
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO, emit # Import SocketIO and emit
from flask_limiter import Limiter # Import Limiter
from flask_limiter.util import get_remote_address # Import get_remote_address

# Define all valid order statuses
VALID_ORDER_STATUSES = [
    'PENDING', 'CONFIRMED', 'PREPARING_ORDER', 'READY_FOR_PICKUP',
    'ON_WAY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERY_ATTEMPT_FAILED',
    'CANCELLED', 'RETURNED'
]

LOW_STOCK_THRESHOLD = 10 # Define a low stock threshold

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-very-secret-key-that-should-be-changed') # Get from env, provide a dev fallback
app.config['FIREBASE_API_KEY'] = os.environ.get('FIREBASE_API_KEY', 'AIzaSyCoTZoQRtiTATNY5JCWqTMCKDxoTcIok3E') # Get from env, provide a dev fallback

# Ensure essential environment variables are set
# if not app.secret_key:
#     raise ValueError("FLASK_SECRET_KEY environment variable not set.")
# if not app.config['FIREBASE_API_KEY']:
#     raise ValueError("FIREBASE_API_KEY environment variable not set.")

socketio = SocketIO(app, message_queue=None) # Initialize SocketIO with message queue

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"], # Default limits for all routes
    storage_uri=None # Use Redis for Limiter storage
)

# Configure logging
log_file = os.path.join(os.path.dirname(__file__), 'app.log')
handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO) # Set default logging level

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

# Custom template filter for timestamp
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    try:
        return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M')
    except:
        return 'N/A'

# Initialize Firebase
# try:
#     # Check for Render Secret File path first
#     render_cred_path = '/etc/secrets/serviceAccountKey.json'
#     if os.path.exists(render_cred_path):
#         cred_path = render_cred_path
#         app.logger.info("Using serviceAccountKey.json from Render Secret Files.")
#     else:
#         # Fallback to local path for development
#         cred_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
#         app.logger.info("Using serviceAccountKey.json from local file system.")

#     if not firebase_admin._apps:
#         cred = credentials.Certificate(cred_path)
#         firebase_admin.initialize_app(cred, {
#             'storageBucket': 'frizzly-9a65f.firebasestorage.app'
#         })
#     db = firestore.client()
# except Exception as e:
#     app.logger.exception("Firebase initialization error")
#     db = None

_firestore_client = None

def get_firestore_client():
    global _firestore_client
    if _firestore_client is None:
        try:
            # Check for Render Secret File path first
            render_cred_path = '/etc/secrets/serviceAccountKey.json'
            if os.path.exists(render_cred_path):
                cred_path = render_cred_path
                app.logger.info("Using serviceAccountKey.json from Render Secret Files.")
            else:
                # Fallback to local path for development
                cred_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
                app.logger.info("Using serviceAccountKey.json from local file system.")

            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': 'frizzly-9a65f.firebasestorage.app'
                })
            
            # Create client with custom timeout settings
            from google.api_core.client_options import ClientOptions
            client_options = ClientOptions(
                api_endpoint='firestore.googleapis.com:443'
            )
            _firestore_client = firestore.client()
            
            # Set default timeout for all operations (30 seconds instead of 300)
            _firestore_client._client_options = client_options
            
        except Exception as e:
            app.logger.exception("Firebase initialization error in get_firestore_client()")
            _firestore_client = None # Ensure it's None on error
    return _firestore_client

# In-memory cache for categories
_category_cache = {'data': [], 'timestamp': 0}
_CATEGORY_CACHE_TTL = 300 # Cache for 5 minutes (300 seconds)

def get_cached_categories():
    global _category_cache
    if not get_firestore_client():
        app.logger.error("Database not initialized, cannot fetch categories.")
        return ['Fruits', 'Vegetables', 'Organic', 'Others']

    current_time = datetime.now().timestamp()
    if (current_time - _category_cache['timestamp']) > _CATEGORY_CACHE_TTL:
        app.logger.info("Refreshing category cache.")
        try:
            # Try to get categories from products collection
            products_docs = get_firestore_client().collection('products').stream()
            categories_set = set()
            for doc in products_docs:
                data = doc.to_dict()
                if 'category' in data and data['category']:
                    categories_set.add(data['category'])
            
            # If no categories found, use defaults
            if categories_set:
                _category_cache['data'] = sorted(list(categories_set))
            else:
                _category_cache['data'] = ['Fruits', 'Vegetables', 'Organic', 'Others']
            
            _category_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing category cache from Firestore.")
            # Return defaults on error
            return ['Fruits', 'Vegetables', 'Organic', 'Others']
    
    return _category_cache['data'] if _category_cache['data'] else ['Fruits', 'Vegetables', 'Organic', 'Others']

# In-memory cache for drivers (optional, but good for frequently accessed lists)
_driver_cache = {'data': [], 'timestamp': 0}
_DRIVER_CACHE_TTL = 60 # Cache for 1 minute

def get_available_drivers():
    global _driver_cache
    if not get_firestore_client():
        app.logger.error("Database not initialized, cannot fetch drivers.")
        return []

    current_time = datetime.now().timestamp()
    if (current_time - _driver_cache['timestamp']) > _DRIVER_CACHE_TTL:
        app.logger.info("Refreshing driver cache.")
        try:
            # Simplified query - just get all drivers and filter in Python
            drivers_docs = get_firestore_client().collection('drivers').stream()
            all_drivers = [{'id': doc.id, **doc.to_dict()} for doc in drivers_docs]
            # Filter available drivers in Python to avoid index requirement
            _driver_cache['data'] = [d for d in all_drivers if d.get('status') == 'available']
            _driver_cache['timestamp'] = current_time
        except Exception as e:
            app.logger.exception("Error refreshing driver cache from Firestore.")
            if _driver_cache['data']:
                return _driver_cache['data']
            return []
    return _driver_cache['data']

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email, name, role='admin'):
        self.id = id
        self.email = email
        self.name = name
        self.role = role

# In-memory cache for admin users
_admin_cache = {}
_ADMIN_CACHE_TTL = 300  # 5 minutes

@login_manager.user_loader
def load_user(user_id):
    if not get_firestore_client():
        return None
    
    # Check cache first
    current_time = datetime.now().timestamp()
    if user_id in _admin_cache:
        cached_user, timestamp = _admin_cache[user_id]
        if (current_time - timestamp) < _ADMIN_CACHE_TTL:
            return cached_user
    
    try:
        user_doc = get_firestore_client().collection('admins').document(user_id).get(timeout=10.0)
        if user_doc.exists:
            data = user_doc.to_dict()
            user = User(user_id, data['email'], data['name'], data.get('role', 'admin'))
            # Cache the user
            _admin_cache[user_id] = (user, current_time)
            return user
    except Exception as e:
        app.logger.error(f"Error loading user {user_id}: {e}")
        # Return cached user if available, even if expired
        if user_id in _admin_cache:
            return _admin_cache[user_id][0]
    
    return None

from functools import wraps
from flask import abort

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

# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") # Limit login attempts
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not get_firestore_client():
            flash('Database connection error', 'danger')
            return render_template('login.html')
        
        # Query admin by email
        admins = get_firestore_client().collection('admins').where('email', '==', email).limit(1).stream()
        admin_doc = next(admins, None)
        
        if admin_doc and check_password_hash(admin_doc.to_dict()['password'], password):
            data = admin_doc.to_dict()
            user = User(admin_doc.id, data['email'], data['name'], data.get('role', 'admin'))
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

# In-memory cache for dashboard stats
_stats_cache = {'data': {}, 'timestamp': 0}
_STATS_CACHE_TTL = 60  # 1 minute

@app.route('/')
@login_required
@role_required(['admin', 'order_manager', 'product_manager', 'viewer'])
def dashboard():
    if not get_firestore_client():
        app.logger.error("Database not initialized for dashboard route.")
        return render_template('dashboard.html', stats={})
    
    # Check cache first
    current_time = datetime.now().timestamp()
    if (current_time - _stats_cache['timestamp']) < _STATS_CACHE_TTL and _stats_cache['data']:
        app.logger.info("Using cached dashboard stats")
        stats = _stats_cache['data']
        # Still fetch recent orders
        try:
            recent_orders_stream = get_firestore_client().collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
            recent_orders_data = []
            for doc in recent_orders_stream:
                data = normalize_order_data(doc.to_dict())
                data['id'] = doc.id
                recent_orders_data.append(data)
            return render_template('dashboard.html', stats=stats, recent_orders=recent_orders_data)
        except Exception as e:
            app.logger.exception("Error loading recent orders")
            return render_template('dashboard.html', stats=stats, recent_orders=[])
    
    try:
        # Try aggregation queries with short timeout
        try:
            from google.cloud.firestore_v1 import aggregation
            
            total_orders = get_firestore_client().collection('orders').count().get(timeout=15.0)[0][0].value
            total_products = get_firestore_client().collection('products').count().get(timeout=15.0)[0][0].value
            total_users = get_firestore_client().collection('users').count().get(timeout=15.0)[0][0].value
            pending_orders = get_firestore_client().collection('orders').where('status', '==', 'PENDING').count().get(timeout=15.0)[0][0].value
            low_stock_products = get_firestore_client().collection('products').where('stock', '<', 10).count().get(timeout=15.0)[0][0].value
            
            revenue_agg = get_firestore_client().collection('orders').aggregate([aggregation.Sum('totalAmount')]).get(timeout=15.0)
            total_revenue = revenue_agg[0][0].value or 0
        except Exception as agg_error:
            app.logger.warning(f"Aggregation failed, using fallback: {agg_error}")
            # Fallback: use limited queries
            total_orders = len(list(get_firestore_client().collection('orders').limit(1000).stream()))
            total_products = len(list(get_firestore_client().collection('products').limit(1000).stream()))
            total_users = len(list(get_firestore_client().collection('users').limit(1000).stream()))
            pending_orders = len(list(get_firestore_client().collection('orders').where('status', '==', 'PENDING').limit(100).stream()))
            low_stock_products = len(list(get_firestore_client().collection('products').where('stock', '<', 10).limit(100).stream()))
            
            # Estimate revenue from limited sample
            orders_sample = list(get_firestore_client().collection('orders').limit(100).stream())
            total_revenue = sum(doc.to_dict().get('totalAmount', 0) for doc in orders_sample)
            if len(orders_sample) == 100:
                total_revenue = total_revenue * (total_orders / 100)  # Extrapolate

        stats = {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'total_products': total_products,
            'total_users': total_users,
            'pending_orders': pending_orders,
            'low_stock_products': low_stock_products
        }
        
        # Cache the stats
        _stats_cache['data'] = stats
        _stats_cache['timestamp'] = current_time
        
        # Recent orders - Optimized to fetch only 5 most recent
        recent_orders_stream = get_firestore_client().collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
        recent_orders_data = []
        for doc in recent_orders_stream:
            data = normalize_order_data(doc.to_dict())
            data['id'] = doc.id
            recent_orders_data.append(data)
        
        return render_template('dashboard.html', stats=stats, recent_orders=recent_orders_data)
    except Exception as e:
        app.logger.exception("Error loading dashboard data")
        # Return cached data if available
        if _stats_cache['data']:
            flash('Using cached data due to connection issues', 'warning')
            return render_template('dashboard.html', stats=_stats_cache['data'], recent_orders=[])
        flash('Error loading dashboard data. Please try again.', 'danger')
        return render_template('dashboard.html', stats={}, recent_orders=[])
        return render_template('dashboard.html', stats={}, recent_orders=[])

# ==================== ORDERS ====================

@app.route('/orders')
@login_required
@role_required(['admin', 'order_manager', 'viewer'])
def orders():
    if not get_firestore_client():
        app.logger.error("Database not initialized for orders route.")
        return render_template('orders.html', orders=[], pagination={'total_pages': 0, 'current_page': 1})
    
    page = request.args.get('page', 1, type=int)
    per_page = 10 # Number of orders per page
    
    orders_query = get_firestore_client().collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING)
    
    # Use aggregation for count instead of fetching all documents
    total_orders_count = get_firestore_client().collection('orders').count().get()[0][0].value
    
    start_at_index = (page - 1) * per_page
    
    orders_stream = orders_query.offset(start_at_index).limit(per_page).stream()
    
    orders_list = []
    for doc in orders_stream:
        data = normalize_order_data(doc.to_dict())
        data['id'] = doc.id
        orders_list.append(data)
    
    total_pages = (total_orders_count + per_page - 1) // per_page
    
    pagination = {
        'total_count': total_orders_count,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template('orders.html', orders=orders_list, pagination=pagination, valid_statuses=VALID_ORDER_STATUSES)

@app.route('/orders/<order_id>')
@login_required
@role_required(['admin', 'order_manager', 'viewer'])
def order_detail(order_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('orders'))
    
    doc = get_firestore_client().collection('orders').document(order_id).get()
    if not doc.exists:
        flash('Order not found', 'danger')
        return redirect(url_for('orders'))
    
    order = normalize_order_data(doc.to_dict())
    order['id'] = doc.id
    
    available_drivers = get_available_drivers() # Fetch available drivers

    return render_template('order_detail.html', order=order, valid_statuses=VALID_ORDER_STATUSES, available_drivers=available_drivers) # Pass available_drivers

@app.route('/orders/<order_id>/update-status', methods=['POST'])
@login_required
@role_required(['admin', 'order_manager'])
def update_order_status(order_id):
    if not get_firestore_client():
        return jsonify({'success': False, 'error': 'Database error'}), 500
    
    new_status = request.form.get('status')

    # Validate new_status
    if new_status not in VALID_ORDER_STATUSES:
        flash(f'Invalid status: {new_status}', 'danger')
        app.logger.warning(f"Invalid status '{new_status}' attempted for order {order_id}")
        return redirect(url_for('order_detail', order_id=order_id))
    
    try:
        # Get order to find user and current items
        order_doc = get_firestore_client().collection('orders').document(order_id).get()
        if not order_doc.exists:
            flash('Order not found', 'danger')
            app.logger.warning(f"Attempted to update status for non-existent order {order_id}")
            return redirect(url_for('orders'))

        order_data = order_doc.to_dict()
        user_id = order_data.get('userId')
        current_status = order_data.get('status')
        
        # Update order status
        get_firestore_client().collection('orders').document(order_id).update({
            'status': new_status,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })

        # Adjust stock if status changes to CANCELLED or RETURNED
        if new_status in ['CANCELLED', 'RETURNED'] and current_status not in ['CANCELLED', 'RETURNED']:
            for item in order_data.get('items', []):
                product_id = item.get('productId')
                quantity = item.get('quantity')
                if product_id and quantity:
                    product_ref = get_firestore_client().collection('products').document(product_id)
                    product_ref.update({'stock': firestore.Increment(quantity)}) # Atomically increment stock
                    app.logger.info(f"Incremented stock for product {product_id} by {quantity} due to order {order_id} {new_status}")
        
        # Send FCM notification to user
        if user_id:
            send_notification(user_id, new_status, order_id)
            app.logger.info(f"Sent notification to user {user_id} for order {order_id} status {new_status}")
        
        # Emit WebSocket event for real-time update
        socketio.emit('order_status_update', {'order_id': order_id, 'new_status': new_status}, namespace='/')

        flash(f'Order status updated to {new_status}', 'success')
        return redirect(url_for('order_detail', order_id=order_id))
    except Exception as e:
        flash(f'Error updating order: {str(e)}', 'danger')
        app.logger.exception(f"Error updating order {order_id} status to {new_status}")
        return redirect(url_for('order_detail', order_id=order_id))


def send_notification(user_id, status, order_id):
    """Send FCM notification to user"""
    try:
        # Get user's FCM token
        user_doc = get_firestore_client().collection('users').document(user_id).get()
        if not user_doc.exists:
            app.logger.warning(f"User {user_id} not found for notification")
            return
        
        user_data = user_doc.to_dict()
        fcm_token = user_data.get('fcmToken')
        
        if not fcm_token:
            app.logger.warning(f"No FCM token for user {user_id}")
            return
        
        # Create notification message
        status_messages = {
            'PENDING': '⏳ Your order is pending confirmation.',
            'CONFIRMED': '✅ Your order has been confirmed!',
            'PREPARING_ORDER': '👨‍🍳 Your order is being prepared!',
            'READY_FOR_PICKUP': '📦 Your order is ready for pickup!',
            'ON_WAY': '🚚 Your order is on the way!',
            'OUT_FOR_DELIVERY': '🚚 Your order is out for delivery!',
            'DELIVERED': '✨ Your order has been delivered!',
            'DELIVERY_ATTEMPT_FAILED': '⚠️ Delivery attempt failed. We will try again soon.',
            'CANCELLED': '❌ Your order has been cancelled.',
            'RETURNED': '↩️ Your order has been returned.'
        }
        
        
        title = 'FRIZZLY Order Update'
        body = status_messages.get(status, f'Order status: {status}')
        
        # Save notification to Firestore for real-time updates
        notification_data = {
            'userId': user_id,
            'title': title,
            'body': body,
            'type': 'order',
            'orderId': order_id,
            'status': status,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'isRead': False
        }
        get_firestore_client().collection('notifications').add(notification_data)
        app.logger.info(f"💾 Notification saved to Firestore for user {user_id}")
        
        message = messaging.Message(
            notification=messaging.Notification(
                title='FRIZZLY Order Update',
                body=status_messages.get(status, f'Order status: {status}')
            ),
            data={
                'notification_type': 'order',
                'order_id': order_id,
                'status': status
            },
            token=fcm_token
        )
        
        response = messaging.send(message)
        app.logger.info(f"✅ Notification sent to user {user_id} for order {order_id}: {response}")
    except Exception as e:
        app.logger.exception(f"❌ Error sending notification for user {user_id}, order {order_id}")








































@app.route('/orders/<order_id>/assign-driver', methods=['POST'])
@login_required
@role_required(['admin', 'order_manager'])
def assign_driver(order_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        app.logger.error("Database not initialized for assign_driver.")
        return redirect(url_for('order_detail', order_id=order_id))
    
    driver_id = request.form.get('driver_id')
    
    if not driver_id:
        flash('No driver selected.', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))

    try:
        driver_doc = get_firestore_client().collection('drivers').document(driver_id).get()
        if not driver_doc.exists:
            flash('Selected driver not found.', 'danger')
            app.logger.warning(f"Attempted to assign non-existent driver with ID: {driver_id} to order {order_id}")
            return redirect(url_for('order_detail', order_id=order_id))
        
        driver_data = driver_doc.to_dict()
        driver_name = driver_data.get('name', 'Unknown Driver')
        driver_phone = driver_data.get('phone', 'N/A')

        get_firestore_client().collection('orders').document(order_id).update({
            'status': 'OUT_FOR_DELIVERY', # Changed from ON_WAY to OUT_FOR_DELIVERY
            'driverId': driver_id,
            'driverName': driver_name,
            'driverPhone': driver_phone,
            'shippedAt': firestore.SERVER_TIMESTAMP
        })
        
        # Optionally, update driver status
        get_firestore_client().collection('drivers').document(driver_id).update({
            'status': 'on_delivery',
            'currentOrderId': order_id
        })

        flash(f'Order assigned to {driver_name} and marked as Out For Delivery', 'success')
        app.logger.info(f"Order {order_id} assigned to driver {driver_id} ({driver_name})")
        return redirect(url_for('order_detail', order_id=order_id))
    except Exception as e:
        app.logger.exception(f"Error assigning driver {driver_id} to order {order_id}")
        flash(f'Error assigning driver: {str(e)}', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))

# ==================== PRODUCTS ====================

@app.route('/products')
@login_required
@role_required(['admin', 'product_manager', 'viewer'])
def products():
    if not get_firestore_client():
        app.logger.error("Database not initialized for products route.")
        return render_template('products.html', products=[], pagination={'total_pages': 0, 'current_page': 1})
    
    page = request.args.get('page', 1, type=int)
    per_page = 10 # Number of products per page
    
    products_query = get_firestore_client().collection('products').order_by('createdAt', direction=firestore.Query.DESCENDING)
    
    # Use aggregation for count
    total_products_count = get_firestore_client().collection('products').count().get()[0][0].value
    
    start_at_index = (page - 1) * per_page
    
    products_stream = products_query.offset(start_at_index).limit(per_page).stream()
    
    products_list = []
    for doc in products_stream:
        data = doc.to_dict()
        data['id'] = doc.id
        products_list.append(data)
    
    total_pages = (total_products_count + per_page - 1) // per_page
    
    pagination = {
        'total_count': total_products_count,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template('products.html', products=products_list, pagination=pagination)

@app.route('/products/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_manager'])
def add_product():
    categories = get_cached_categories()

    if request.method == 'POST':
        if not get_firestore_client():
            flash('Database error', 'danger')
            app.logger.error("Database not initialized when adding product.")
            return redirect(url_for('products'))
        
        name = request.form.get('name')
        price_str = request.form.get('price')
        category = request.form.get('category')
        description = request.form.get('description', '')
        imageUrl = request.form.get('imageUrl', '')
        inStock = request.form.get('inStock') == 'on'
        
        # Handle image upload to ImgBB
        uploaded_file = request.files.get('imageFile')
        if uploaded_file and uploaded_file.filename:
            try:
                import requests
                import base64
                
                # Read and encode image
                image_data = base64.b64encode(uploaded_file.read()).decode('utf-8')
                
                # Upload to ImgBB (free, no API key needed for basic use)
                imgbb_url = "https://api.imgbb.com/1/upload"
                payload = {
                    'key': '8a4a9a6f8e8c8f8e8c8f8e8c8f8e8c8f',  # Public demo key (replace with yours)
                    'image': image_data
                }
                
                response = requests.post(imgbb_url, data=payload, timeout=30)
                result = response.json()
                
                if result.get('success'):
                    imageUrl = result['data']['url']
                    app.logger.info(f"Image uploaded to ImgBB: {imageUrl}")
                else:
                    flash('Image upload failed. Please use image URL instead.', 'warning')
                    
            except Exception as e:
                app.logger.exception("Error uploading to ImgBB")
                flash(f'Image upload failed: {str(e)}. Please use image URL instead.', 'warning')

        errors = []

        if not name or not name.strip():
            errors.append('Product name is required.')
        if not category or not category.strip():
            errors.append('Category is required.')
        elif category not in categories:
            errors.append('Invalid category selected.')
        
        try:
            price = float(price_str)
            if price <= 0:
                errors.append('Price must be a positive number.')
        except (ValueError, TypeError):
            errors.append('Price must be a valid number.')
        
        if not imageUrl:
            errors.append('Image URL or file upload is required.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('add_product.html', product=request.form, categories=categories)

        product = {
            'name': name,
            'price': price,
            'category': category,
            'description': description,
            'imageUrl': imageUrl,
            'inStock': inStock,
            'isActive': True,
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        
        try:
            get_firestore_client().collection('products').add(product)
            flash('Product added successfully', 'success')
            app.logger.info(f"Product '{name}' added by {current_user.id}")
            return redirect(url_for('products'))
        except Exception as e:
            app.logger.exception(f"Error adding product '{name}'")
            flash(f'Error adding product: {str(e)}', 'danger')
    
    return render_template('add_product.html', categories=categories) # Pass categories here

@app.route('/products/<product_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_manager'])
def edit_product(product_id):
    categories = get_cached_categories() # Fetch categories

    if not get_firestore_client():
        flash('Database error', 'danger')
        app.logger.error("Database not initialized when editing product.")
        return redirect(url_for('products'))
    
    doc = get_firestore_client().collection('products').document(product_id).get()
    if not doc.exists:
        flash('Product not found', 'danger')
        app.logger.warning(f"Attempted to edit non-existent product with ID: {product_id}")
        return redirect(url_for('products'))
    
    product = doc.to_dict()
    product['id'] = doc.id

    if request.method == 'POST':
        name = request.form.get('name')
        price_str = request.form.get('price')
        category = request.form.get('category')
        description = request.form.get('description', '')
        imageUrl = request.form.get('imageUrl', '')
        inStock = request.form.get('inStock') == 'on'
        
        # Handle image upload to Firebase Storage
        uploaded_file = request.files.get('imageFile')
        if uploaded_file and uploaded_file.filename:
            try:
                from firebase_admin import storage
                from werkzeug.utils import secure_filename
                import time
                
                filename = secure_filename(uploaded_file.filename)
                filename = f"{int(time.time())}_{filename}"
                
                bucket = storage.bucket()
                blob = bucket.blob(f'products/{filename}')
                blob.upload_from_file(uploaded_file, content_type=uploaded_file.content_type)
                blob.make_public()
                
                imageUrl = blob.public_url
                app.logger.info(f"Image uploaded to Firebase Storage: {imageUrl}")
                
            except Exception as e:
                app.logger.exception("Error uploading to Firebase Storage")
                flash(f'Error uploading image: {str(e)}', 'danger')
                product.update({
                    'name': name,
                    'price': price_str,
                    'category': category,
                    'description': description,
                    'imageUrl': imageUrl,
                    'inStock': inStock
                })
                return render_template('edit_product.html', product=product, categories=categories)

        errors = []
        
        if not name or not name.strip():
            errors.append('Product name is required.')
        if not category or not category.strip():
            errors.append('Category is required.')
        elif category not in categories:
            errors.append('Invalid category selected.')
        
        try:
            price = float(price_str)
            if price <= 0:
                errors.append('Price must be a positive number.')
        except (ValueError, TypeError):
            errors.append('Price must be a valid number.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            product.update({
                'name': name,
                'price': price_str,
                'category': category,
                'description': description,
                'imageUrl': imageUrl,
                'inStock': inStock
            })
            return render_template('edit_product.html', product=product, categories=categories)

        updates = {
            'name': name,
            'price': price,
            'category': category,
            'description': description,
            'imageUrl': imageUrl,
            'inStock': inStock,
            'updatedAt': firestore.SERVER_TIMESTAMP
        }
        
        try:
            get_firestore_client().collection('products').document(product_id).update(updates)
            flash('Product updated successfully', 'success')
            app.logger.info(f"Product '{name}' (ID: {product_id}) updated by {current_user.id}")
            return redirect(url_for('products'))
        except Exception as e:
            app.logger.exception(f"Error updating product '{name}' (ID: {product_id})")
            flash(f'Error updating product: {str(e)}', 'danger')
    
    return render_template('edit_product.html', product=product, categories=categories) # Pass categories here

@app.route('/products/<product_id>/delete', methods=['POST'])
@login_required
@role_required(['admin', 'product_manager'])
def delete_product(product_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('products'))
    
    try:
        get_firestore_client().collection('products').document(product_id).delete()
        flash('Product deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting product: {str(e)}', 'danger')
    
    return redirect(url_for('products'))

# ==================== USERS ====================

@app.route('/users')
@login_required
@role_required(['admin', 'viewer'])
def users():
    if not get_firestore_client():
        app.logger.error("Database not initialized for users route.")
        return render_template('users.html', users=[], pagination={'total_pages': 0, 'current_page': 1})
    
    page = request.args.get('page', 1, type=int)
    per_page = 10 # Number of users per page
    
    # Use lastLogin instead of createdAt since that's what the Android app saves
    users_query = get_firestore_client().collection('users').order_by('lastLogin', direction=firestore.Query.DESCENDING)
    
    # Use aggregation for count
    total_users_count = get_firestore_client().collection('users').count().get()[0][0].value
    
    start_at_index = (page - 1) * per_page
    
    users_stream = users_query.offset(start_at_index).limit(per_page).stream()
    
    users_list = []
    for doc in users_stream:
        data = doc.to_dict()
        data['id'] = doc.id
        # Convert lastLogin timestamp to string format for display
        if 'lastLogin' in data:
            try:
                timestamp = data['lastLogin']
                if hasattr(timestamp, 'strftime'):
                    data['createdAt'] = timestamp.strftime('%Y-%m-%d')
                else:
                    data['createdAt'] = str(timestamp)[:10]
            except:
                data['createdAt'] = 'N/A'
        users_list.append(data)
    
    total_pages = (total_users_count + per_page - 1) // per_page
    
    pagination = {
        'total_count': total_users_count,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template('users.html', users=users_list, pagination=pagination)

@app.route('/users/<user_id>')
@login_required
@role_required(['admin', 'viewer'])
def user_detail(user_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('users'))
    
    doc = get_firestore_client().collection('users').document(user_id).get()
    if not doc.exists:
        flash('User not found', 'danger')
        return redirect(url_for('users'))
    
    user = doc.to_dict()
    user['id'] = doc.id
    
    # Get user's orders
    orders = []
    for order_doc in get_firestore_client().collection('orders').where('userId', '==', user_id).stream():
        order_data = normalize_order_data(order_doc.to_dict())
        order_data['id'] = order_doc.id
        orders.append(order_data)
    
    return render_template('user_detail.html', user=user, orders=orders)

@app.route('/users/send-test-notification', methods=['POST'])
@login_required
@role_required(['admin']) # Only admin can send test notifications
def send_test_notification():
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('users'))
    
    user_id = request.form.get('user_id')
    title = request.form.get('title')
    message = request.form.get('message')
    
    try:
        # Get user's FCM token
        user_doc = get_firestore_client().collection('users').document(user_id).get()
        if not user_doc.exists:
            flash('User not found', 'danger')
            return redirect(url_for('users'))
        
        user_data = user_doc.to_dict()
        fcm_token = user_data.get('fcmToken')
        
        if not fcm_token:
            flash('User does not have a notification token. Ask them to open the app.', 'warning')
            return redirect(url_for('users'))
        
        # Send notification
        notification = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=message
            ),
            token=fcm_token
        )
        
        messaging.send(notification)
        flash(f'Test notification sent successfully to {user_data.get("displayName", "user")}!', 'success')
        
    except Exception as e:
        flash(f'Error sending notification: {str(e)}', 'danger')
    
    return redirect(url_for('users'))

# ==================== ANALYTICS ====================

@app.route('/analytics')
@login_required
@role_required(['admin', 'viewer'])
def analytics():
    if not get_firestore_client():
        return render_template('analytics.html', data={})
    
    orders = list(get_firestore_client().collection('orders').stream())
    
    # Status breakdown
    status_counts = {}
    for doc in orders:
        status = doc.to_dict().get('status', 'UNKNOWN')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Revenue by month (last 6 months)
    monthly_revenue = {}
    for doc in orders:
        data = doc.to_dict()
        created_at = data.get('createdAt', '')
        if created_at:
            month = created_at[:7]  # YYYY-MM
            monthly_revenue[month] = monthly_revenue.get(month, 0) + data.get('totalAmount', 0)
    
    data = {
        'status_counts': status_counts,
        'monthly_revenue': dict(sorted(monthly_revenue.items())[-6:])
    }
    
    return render_template('analytics.html', data=data)

# ==================== STOCK MANAGEMENT ====================

@app.route('/stock')
@login_required
@role_required(['admin', 'product_manager', 'viewer'])
def stock_management():
    if not get_firestore_client():
        return render_template('stock.html', products=[])
    
    products = []
    for doc in get_firestore_client().collection('products').stream():
        data = doc.to_dict()
        data['id'] = doc.id
        products.append(data)
    
    # Sort by stock level (low stock first)
    products.sort(key=lambda x: x.get('stock', 0))
    
    return render_template('stock.html', products=products)

@app.route('/stock/<product_id>/update', methods=['POST'])
@login_required
@role_required(['admin', 'product_manager'])
def update_stock(product_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('stock_management'))
    
    new_stock = request.form.get('stock', type=int)

    if new_stock is None or new_stock < 0:
        flash('Stock must be a non-negative integer.', 'danger')
        return redirect(url_for('stock_management'))
    
    try:
        get_firestore_client().collection('products').document(product_id).update({
            'stock': new_stock,
            'updatedAt': datetime.now().isoformat()
        })
        
        # Check for low stock after update
        if new_stock <= LOW_STOCK_THRESHOLD:
            app.logger.warning(f"Product {product_id} is low on stock: {new_stock} remaining after manual update.")
            # send_low_stock_alert_task.delay(product_id, new_stock)

        flash('Stock updated successfully!', 'success')
        return redirect(url_for('stock_management'))
    except Exception as e:
        app.logger.exception(f"Error updating stock for product {product_id}")
        flash(f'Error updating stock: {str(e)}', 'danger')
        return redirect(url_for('stock_management'))

# ==================== DELIVERY LOGISTICS ====================

@app.route('/delivery')
@login_required
@role_required(['admin', 'order_manager', 'viewer'])
def delivery_logistics():
    if not get_firestore_client():
        return render_template('delivery.html', deliveries=[])
    
    # Get orders that are ON_WAY or CONFIRMED
    orders = []
    for doc in get_firestore_client().collection('orders').where('status', 'in', ['CONFIRMED', 'ON_WAY']).stream():
        data = normalize_order_data(doc.to_dict())
        data['id'] = doc.id
        orders.append(data)
    
    # Sort by timestamp (handle both int and datetime types)
    orders.sort(key=lambda x: x.get('timestamp') or 0 if isinstance(x.get('timestamp'), int) else x.get('timestamp').timestamp() if x.get('timestamp') else 0, reverse=True)
    
    return render_template('delivery.html', deliveries=orders)

@app.route('/delivery/<order_id>/assign', methods=['POST'])
@login_required
@role_required(['admin', 'order_manager'])
def assign_driver_delivery(order_id):
    if not get_firestore_client():
        flash('Database error', 'danger')
        return redirect(url_for('delivery_logistics'))
    
    driver_name = request.form.get('driver_name')
    driver_phone = request.form.get('driver_phone')
    
    get_firestore_client().collection('orders').document(order_id).update({
        'driverName': driver_name,
        'driverPhone': driver_phone,
        'status': 'ON_WAY',
        'updatedAt': datetime.now().isoformat()
    })
    
    flash(f'Driver {driver_name} assigned successfully!', 'success')
    return redirect(url_for('delivery_logistics'))

# ==================== API ENDPOINTS ====================

@app.route('/api/order/submit', methods=['POST'])
@limiter.limit("10 per minute") # Limit order submission attempts
def submit_order():
    """API endpoint to submit order and get assigned order number"""
    if not get_firestore_client():
        app.logger.error("Database not initialized for order submission.")
        return jsonify({'success': False, 'error': 'Database error'}), 500
    
    try:
        data = request.get_json()
        
        # --- Validation ---
        errors = []

        user_id = data.get('userId')
        if not user_id or not isinstance(user_id, str) or not user_id.strip():
            errors.append('User ID is required and must be a non-empty string.')
        
        order_data = data.get('order')
        if not order_data or not isinstance(order_data, dict):
            errors.append('Order data is required and must be a dictionary.')
        else:
            items = order_data.get('items')
            if not items or not isinstance(items, list) or not items:
                errors.append('Order must contain a non-empty list of items.')
            else:
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        errors.append(f'Order item at index {i} must be a dictionary.')
                        continue
                    if not item.get('productId') or not isinstance(item['productId'], str) or not item['productId'].strip():
                        errors.append(f'Order item at index {i} requires a non-empty product ID.')
                    if not item.get('name') or not isinstance(item['name'], str) or not item['name'].strip():
                        errors.append(f'Order item at index {i} requires a non-empty name.')
                    
                    try:
                        quantity = int(item.get('quantity', 0))
                        if quantity <= 0:
                            errors.append(f'Order item at index {i} quantity must be a positive integer.')
                        item['quantity'] = quantity # Cast to int
                    except (ValueError, TypeError):
                        errors.append(f'Order item at index {i} quantity must be a valid integer.')
                    
                    try:
                        price = float(item.get('price', 0.0))
                        if price <= 0:
                            errors.append(f'Order item at index {i} price must be a positive number.')
                        item['price'] = price # Cast to float
                    except (ValueError, TypeError):
                        errors.append(f'Order item at index {i} price must be a valid number.')
            
            try:
                total_amount = float(order_data.get('totalAmount', 0.0))
                if total_amount <= 0:
                    errors.append('Total amount must be a positive number.')
                order_data['totalAmount'] = total_amount # Cast to float
            except (ValueError, TypeError):
                errors.append('Total amount must be a valid number.')
            
            if not order_data.get('deliveryAddress') or not isinstance(order_data['deliveryAddress'], str) or not order_data['deliveryAddress'].strip():
                errors.append('Delivery address is required and must be a non-empty string.')

        if errors:
            app.logger.warning(f"Order submission validation failed for user {user_id}: {errors}")
            return jsonify({'success': False, 'error': 'Validation failed', 'details': errors}), 400
        # --- End Validation ---
        
        # Get and increment order counter from Firestore
        counter_ref = get_firestore_client().collection('system').document('counters')
        counter_doc = counter_ref.get()
        
        if counter_doc.exists:
            current_count = counter_doc.to_dict().get('orderCounter', 0)
        else:
            current_count = 0
            counter_ref.set({'orderCounter': 0})
        
        # Increment counter
        new_count = current_count + 1
        counter_ref.update({'orderCounter': new_count})
        
        # Generate order ID (digits only)
        order_id = str(new_count)
        
        # Replace temp ID with real order ID
        order_data['orderId'] = order_id
        order_data['userId'] = user_id
        order_data['timestamp'] = datetime.now().timestamp() * 1000
        order_data['status'] = 'PENDING'
        
        # Save to Firestore
        get_firestore_client().collection('orders').document(order_id).set(order_data)

        # Decrement product stock
        for item in order_data.get('items', []):
            product_id = item.get('productId')
            quantity = item.get('quantity')
            if product_id and quantity:
                product_ref = get_firestore_client().collection('products').document(product_id)
                product_ref.update({'stock': firestore.Increment(-quantity)}) # Atomically decrement stock
                app.logger.info(f"Decremented stock for product {product_id} by {quantity} for order {order_id}")

                # Check for low stock
                updated_product_doc = product_ref.get()
                if updated_product_doc.exists:
                    current_stock = updated_product_doc.to_dict().get('stock', 0)
                    if current_stock <= LOW_STOCK_THRESHOLD:
                        app.logger.warning(f"Product {product_id} is low on stock: {current_stock} remaining.")
                        # In a real app, you might dispatch a Celery task here to send an email to admin
                        # send_low_stock_alert_task.delay(product_id, current_stock)

        # Emit WebSocket event for new order
        socketio.emit('new_order', {'order_id': order_id, 'total_amount': order_data.get('totalAmount', 0)}, namespace='/')
        app.logger.info(f"Emitted new_order WebSocket event for order {order_id}")

        app.logger.info(f"Order {order_id} submitted successfully by user {user_id}.")
        return jsonify({
            'success': True,
            'orderId': order_id,
            'orderNumber': new_count
        })
        
    except Exception as e:
        app.logger.exception("Error submitting order")
        return jsonify({'success': False, 'error': 'An unexpected error occurred during order submission.'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for load balancers/orchestrators."""
    return jsonify({'status': 'ok'}), 200



if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
