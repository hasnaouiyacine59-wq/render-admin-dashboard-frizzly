"""
FRIZZLY Admin Dashboard - Direct Firebase Version for Render
Uses /etc/secrets/serviceAccountKey.json for Firebase connection
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime
import os
import json
import time
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')

# Setup logging
if not app.debug:
    handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

# Initialize Firebase Admin SDK
SERVICE_ACCOUNT_PATH = '/etc/secrets/serviceAccountKey.json'
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Constants
VALID_ORDER_STATUSES = [
    'PENDING', 'CONFIRMED', 'PREPARING_ORDER', 'READY_FOR_PICKUP',
    'ON_WAY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERY_ATTEMPT_FAILED',
    'CANCELLED', 'RETURNED'
]

# Custom Jinja2 filters
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert timestamp to readable date"""
    try:
        if timestamp:
            ts = timestamp / 1000 if timestamp > 1e12 else timestamp
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        pass
    return 'N/A'

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, uid, email, role='admin'):
        self.id = uid
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    try:
        doc = db.collection('admins').document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return User(user_id, data.get('email'), data.get('role', 'admin'))
    except:
        pass
    return None

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.role == 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ============= CONTEXT PROCESSOR =============

@app.context_processor
def inject_stats():
    """Inject order stats into all templates"""
    if current_user.is_authenticated:
        try:
            orders = list(db.collection('orders').stream())
            stats = {
                'total_orders': len(orders),
                'pending_orders': sum(1 for o in orders if o.to_dict().get('status') == 'PENDING'),
                'in_progress_orders': sum(1 for o in orders if o.to_dict().get('status') in ['CONFIRMED', 'PREPARING_ORDER', 'ON_WAY', 'OUT_FOR_DELIVERY']),
                'delivered_orders': sum(1 for o in orders if o.to_dict().get('status') == 'DELIVERED')
            }
            return {'stats': stats}
        except:
            pass
    return {'stats': {'total_orders': 0, 'pending_orders': 0, 'in_progress_orders': 0, 'delivered_orders': 0}}

# ============= AUTHENTICATION =============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            admins = db.collection('admins').where('email', '==', email).limit(1).stream()
            admin_doc = next(admins, None)
            
            if admin_doc and check_password_hash(admin_doc.to_dict().get('password', ''), password):
                user = User(admin_doc.id, email, admin_doc.to_dict().get('role', 'admin'))
                login_user(user)
                return redirect(url_for('dashboard'))
            
            flash('Invalid credentials', 'error')
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash('Login failed', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ============= FCM TOKEN =============

@app.route('/firebase-messaging-sw.js')
def firebase_messaging_sw():
    """Serve Firebase messaging service worker from root"""
    return app.send_static_file('firebase-messaging-sw.js')

@app.route('/api/save-fcm-token', methods=['POST'])
@login_required
def save_fcm_token():
    """Save FCM token for admin push notifications"""
    try:
        data = request.get_json()
        token = data.get('token')
        
        if token:
            db.collection('admins').document(current_user.id).update({
                'fcmToken': token,
                'fcmTokenUpdated': firestore.SERVER_TIMESTAMP
            })
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'No token provided'}), 400
    except Exception as e:
        app.logger.error(f"Save FCM token error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= SSE FOR REAL-TIME ORDERS =============

@app.route('/api/stream-orders')
@login_required
def stream_orders():
    """Server-Sent Events for real-time order updates"""
    import queue
    
    app.logger.info(f"SSE: New connection from user {current_user.id}")
    
    message_queue = queue.Queue(maxsize=100)
    first_snapshot = True
    
    def on_snapshot(col_snapshot, changes, read_time):
        """Firestore snapshot callback"""
        nonlocal first_snapshot
        
        app.logger.info(f"SSE: Snapshot received with {len(changes)} changes, first={first_snapshot}")
        
        # Skip initial snapshot (all existing orders)
        if first_snapshot:
            first_snapshot = False
            app.logger.info("SSE: Skipping initial snapshot")
            return
        
        for change in changes:
            app.logger.info(f"SSE: Change type={change.type.name}, doc={change.document.id}")
            if change.type.name in ['ADDED', 'MODIFIED']:
                doc = change.document
                data = doc.to_dict()
                event_data = {
                    'id': doc.id,
                    'orderId': data.get('orderId', doc.id),
                    'totalAmount': data.get('totalAmount', 0),
                    'status': data.get('status', 'PENDING'),
                    'timestamp': data.get('timestamp', 0),
                    'customerName': data.get('customerName', 'Unknown'),
                    'type': 'new_order' if change.type.name == 'ADDED' else 'order_update'
                }
                try:
                    message_queue.put_nowait(event_data)
                    app.logger.info(f"SSE: Queued event for order {event_data['orderId']}")
                except queue.Full:
                    app.logger.warning("SSE: Queue full, dropping event")
    
    # Start Firestore listener - order by timestamp to catch new orders
    app.logger.info("SSE: Starting Firestore listener")
    col_query = db.collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50)
    doc_watch = col_query.on_snapshot(on_snapshot)
    
    def generate():
        try:
            app.logger.info("SSE: Sending connected message")
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            
            timeout_count = 0
            max_timeouts = 120  # 60 minutes (120 * 30s)
            
            while timeout_count < max_timeouts:
                try:
                    event_data = message_queue.get(timeout=30)
                    event_type = event_data.pop('type', 'message')
                    app.logger.info(f"SSE: Sending {event_type} event")
                    yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
                    timeout_count = 0
                except queue.Empty:
                    yield f": heartbeat\n\n"
                    timeout_count += 1
        except GeneratorExit:
            app.logger.info("SSE: Client disconnected")
        finally:
            app.logger.info("SSE: Unsubscribing from Firestore")
            doc_watch.unsubscribe()
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """API endpoint for dashboard stats (for real-time updates)"""
    try:
        orders = list(db.collection('orders').stream())
        pending_orders = [o for o in orders if o.to_dict().get('status') == 'PENDING']
        
        return jsonify({
            'total_orders': len(orders),
            'pending_orders': len(pending_orders),
            'success': True
        })
    except Exception as e:
        app.logger.error(f"Dashboard stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= DASHBOARD =============

@app.route('/')
@login_required
def dashboard():
    try:
        # Get counts
        orders = list(db.collection('orders').stream())
        products = list(db.collection('products').stream())
        users = list(db.collection('users').stream())
        
        pending_orders = [o for o in orders if o.to_dict().get('status') == 'PENDING']
        low_stock = [p for p in products if p.to_dict().get('stock', 0) < 10]
        total_revenue = sum(o.to_dict().get('totalAmount', 0) for o in orders if o.to_dict().get('status') == 'DELIVERED')
        
        stats = {
            'total_orders': len(orders),
            'pending_orders': len(pending_orders),
            'total_products': len(products),
            'total_users': len(users),
            'low_stock_products': len(low_stock),
            'total_revenue': total_revenue
        }
        
        # Recent orders
        recent_orders = sorted(orders, key=lambda x: x.to_dict().get('timestamp', 0), reverse=True)[:10]
        orders_data = []
        for order in recent_orders:
            data = order.to_dict()
            data['id'] = order.id
            orders_data.append(data)
        
        return render_template('dashboard.html', stats=stats, recent_orders=orders_data)
    except Exception as e:
        app.logger.error(f"Dashboard error: {e}")
        return render_template('dashboard.html', stats={'total_orders': 0, 'pending_orders': 0, 'total_products': 0, 'total_users': 0, 'low_stock_products': 0, 'total_revenue': 0}, recent_orders=[])

# ============= ORDERS =============

@app.route('/orders')
@login_required
def orders():
    try:
        status_filter = request.args.get('status', 'all')
        
        orders_ref = db.collection('orders')
        if status_filter != 'all':
            orders_query = orders_ref.where('status', '==', status_filter)
        else:
            orders_query = orders_ref
        
        orders_list = []
        for doc in orders_query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            orders_list.append(data)
        
        orders_list.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return render_template('orders.html', orders=orders_list, status_filter=status_filter, valid_statuses=VALID_ORDER_STATUSES)
    except Exception as e:
        app.logger.error(f"Orders error: {e}")
        return render_template('orders.html', orders=[], status_filter='all', valid_statuses=VALID_ORDER_STATUSES)

@app.route('/orders/<order_id>')
@login_required
def order_detail(order_id):
    try:
        doc = db.collection('orders').document(order_id).get()
        if not doc.exists:
            flash('Order not found', 'error')
            return redirect(url_for('orders'))
        
        order = doc.to_dict()
        order['id'] = doc.id
        
        # Get available drivers
        drivers = []
        for d in db.collection('drivers').where('status', '==', 'available').stream():
            driver_data = d.to_dict()
            driver_data['id'] = d.id
            drivers.append(driver_data)
        
        return render_template('order_detail.html', order=order, drivers=drivers, valid_statuses=VALID_ORDER_STATUSES)
    except Exception as e:
        app.logger.error(f"Order detail error: {e}")
        flash('Error loading order', 'error')
        return redirect(url_for('orders'))

@app.route('/orders/<order_id>/update-status', methods=['POST'])
@login_required
def update_order_status(order_id):
    try:
        new_status = request.form.get('status')
        
        db.collection('orders').document(order_id).update({
            'status': new_status,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        # Send notification to user
        order_doc = db.collection('orders').document(order_id).get()
        if order_doc.exists:
            user_id = order_doc.to_dict().get('userId')
            if user_id:
                send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash('Order status updated', 'success')
    except Exception as e:
        app.logger.error(f"Update status error: {e}")
        flash('Failed to update status', 'error')
    
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/orders/export')
@login_required
def export_orders():
    """Export orders to CSV"""
    try:
        import csv
        from io import StringIO
        
        orders = [doc.to_dict() for doc in db.collection('orders').stream()]
        
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=['id', 'orderId', 'status', 'totalAmount', 'timestamp'])
        writer.writeheader()
        for order in orders:
            writer.writerow({
                'id': order.get('id', ''),
                'orderId': order.get('orderId', ''),
                'status': order.get('status', ''),
                'totalAmount': order.get('totalAmount', 0),
                'timestamp': order.get('timestamp', '')
            })
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=orders.csv'
        return response
    except Exception as e:
        app.logger.error(f"Export orders error: {e}")
        flash('Failed to export orders', 'error')
        return redirect(url_for('orders'))

# ============= PRODUCTS =============

@app.route('/products')
@login_required
def products():
    try:
        products_list = []
        for doc in db.collection('products').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            products_list.append(data)
        
        pagination = {'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('products.html', products=products_list, pagination=pagination)
    except Exception as e:
        app.logger.error(f"Products error: {e}")
        pagination = {'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('products.html', products=[], pagination=pagination)

@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        try:
            product_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': float(request.form.get('price', 0)),
                'category': request.form.get('category'),
                'stock': int(request.form.get('stock', 0)),
                'imageUrl': request.form.get('imageUrl', ''),
                'isActive': request.form.get('isActive') == 'on',
                'createdAt': firestore.SERVER_TIMESTAMP
            }
            
            db.collection('products').add(product_data)
            flash('Product added successfully', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            app.logger.error(f"Add product error: {e}")
            flash('Failed to add product', 'error')
    
    return render_template('add_product.html')

@app.route('/products/<product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if request.method == 'POST':
        try:
            product_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': float(request.form.get('price', 0)),
                'category': request.form.get('category'),
                'stock': int(request.form.get('stock', 0)),
                'imageUrl': request.form.get('imageUrl', ''),
                'isActive': request.form.get('isActive') == 'on',
                'updatedAt': firestore.SERVER_TIMESTAMP
            }
            
            db.collection('products').document(product_id).update(product_data)
            flash('Product updated successfully', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            app.logger.error(f"Edit product error: {e}")
            flash('Failed to update product', 'error')
    
    try:
        doc = db.collection('products').document(product_id).get()
        if not doc.exists:
            flash('Product not found', 'error')
            return redirect(url_for('products'))
        
        product = doc.to_dict()
        product['id'] = doc.id
        return render_template('edit_product.html', product=product)
    except Exception as e:
        app.logger.error(f"Load product error: {e}")
        flash('Error loading product', 'error')
        return redirect(url_for('products'))

@app.route('/products/<product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    try:
        db.collection('products').document(product_id).delete()
        flash('Product deleted successfully', 'success')
    except Exception as e:
        app.logger.error(f"Delete product error: {e}")
        flash('Failed to delete product', 'error')
    
    return redirect(url_for('products'))

# ============= USERS =============

@app.route('/users')
@login_required
def users():
    try:
        users_list = []
        for doc in db.collection('users').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            users_list.append(data)
        
        pagination = {'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('users.html', users=users_list, pagination=pagination)
    except Exception as e:
        app.logger.error(f"Users error: {e}")
        pagination = {'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('users.html', users=[], pagination=pagination)

@app.route('/users/<user_id>')
@login_required
def user_detail(user_id):
    try:
        doc = db.collection('users').document(user_id).get()
        if not doc.exists:
            flash('User not found', 'error')
            return redirect(url_for('users'))
        
        user = doc.to_dict()
        user['id'] = doc.id
        
        # Fetch user's orders
        orders = []
        for order_doc in db.collection('orders').where('userId', '==', user_id).stream():
            order_data = order_doc.to_dict()
            order_data['id'] = order_doc.id
            orders.append(order_data)
        
        # Sort by timestamp (newest first)
        orders.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return render_template('user_detail.html', user=user, orders=orders)
    except Exception as e:
        app.logger.error(f"User detail error: {e}")
        flash('Error loading user', 'error')
        return redirect(url_for('users'))

# ============= DELIVERY & DRIVERS =============

@app.route('/delivery-logistics')
@login_required
def delivery_logistics():
    try:
        orders = []
        for doc in db.collection('orders').where('status', 'in', ['ON_WAY', 'OUT_FOR_DELIVERY']).stream():
            data = doc.to_dict()
            data['id'] = doc.id
            orders.append(data)
        
        return render_template('delivery.html', orders=orders)
    except Exception as e:
        app.logger.error(f"Delivery logistics error: {e}")
        return render_template('delivery.html', orders=[])

@app.route('/drivers')
@login_required
def drivers():
    try:
        drivers_list = []
        for doc in db.collection('drivers').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            drivers_list.append(data)
        
        # Calculate stats
        stats = {
            'total': len(drivers_list),
            'available': len([d for d in drivers_list if d.get('status') == 'available']),
            'on_delivery': len([d for d in drivers_list if d.get('status') == 'on_delivery']),
            'offline': len([d for d in drivers_list if d.get('status') == 'offline'])
        }
        
        return render_template('drivers.html', drivers=drivers_list, stats=stats)
    except Exception as e:
        app.logger.error(f"Drivers error: {e}")
        return render_template('drivers.html', drivers=[], stats={'total': 0, 'available': 0, 'on_delivery': 0, 'offline': 0})

@app.route('/drivers/add', methods=['GET', 'POST'])
@login_required
def add_driver():
    if request.method == 'POST':
        try:
            driver_data = {
                'name': request.form.get('name'),
                'phone': request.form.get('phone'),
                'email': request.form.get('email'),
                'vehicleType': request.form.get('vehicleType'),
                'status': 'available',
                'createdAt': firestore.SERVER_TIMESTAMP
            }
            db.collection('drivers').add(driver_data)
            flash('Driver added successfully', 'success')
            return redirect(url_for('drivers'))
        except Exception as e:
            app.logger.error(f"Add driver error: {e}")
            flash('Failed to add driver', 'error')
    
    return render_template('add_driver.html')

@app.route('/drivers/<driver_id>')
@login_required
def driver_detail(driver_id):
    try:
        doc = db.collection('drivers').document(driver_id).get()
        if not doc.exists:
            flash('Driver not found', 'error')
            return redirect(url_for('drivers'))
        driver = doc.to_dict()
        driver['id'] = doc.id
        return render_template('driver_detail.html', driver=driver)
    except Exception as e:
        app.logger.error(f"Driver detail error: {e}")
        flash('Error loading driver', 'error')
        return redirect(url_for('drivers'))

@app.route('/drivers/<driver_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_driver(driver_id):
    if request.method == 'POST':
        try:
            driver_data = {
                'name': request.form.get('name'),
                'phone': request.form.get('phone'),
                'email': request.form.get('email'),
                'vehicleType': request.form.get('vehicleType'),
                'status': request.form.get('status'),
                'updatedAt': firestore.SERVER_TIMESTAMP
            }
            db.collection('drivers').document(driver_id).update(driver_data)
            flash('Driver updated successfully', 'success')
            return redirect(url_for('drivers'))
        except Exception as e:
            app.logger.error(f"Edit driver error: {e}")
            flash('Failed to update driver', 'error')
    
    try:
        doc = db.collection('drivers').document(driver_id).get()
        if not doc.exists:
            flash('Driver not found', 'error')
            return redirect(url_for('drivers'))
        driver = doc.to_dict()
        driver['id'] = doc.id
        return render_template('edit_driver.html', driver=driver)
    except Exception as e:
        app.logger.error(f"Load driver error: {e}")
        flash('Error loading driver', 'error')
        return redirect(url_for('drivers'))

@app.route('/drivers/<driver_id>/delete', methods=['POST'])
@login_required
def delete_driver(driver_id):
    try:
        db.collection('drivers').document(driver_id).delete()
        flash('Driver deleted successfully', 'success')
    except Exception as e:
        app.logger.error(f"Delete driver error: {e}")
        flash('Failed to delete driver', 'error')
    return redirect(url_for('drivers'))

@app.route('/orders/<order_id>/assign-driver', methods=['POST'])
@login_required
def assign_driver(order_id):
    try:
        driver_id = request.form.get('driver_id')
        db.collection('orders').document(order_id).update({
            'driverId': driver_id,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        flash('Driver assigned successfully', 'success')
    except Exception as e:
        app.logger.error(f"Assign driver error: {e}")
        flash('Failed to assign driver', 'error')
    return redirect(url_for('order_detail', order_id=order_id))

@app.route('/stock-management')
@login_required
def stock_management():
    try:
        products = []
        for doc in db.collection('products').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            products.append(data)
        
        return render_template('stock.html', products=products)
    except Exception as e:
        app.logger.error(f"Stock management error: {e}")
        return render_template('stock.html', products=[])

@app.route('/products/<product_id>/update-stock', methods=['POST'])
@login_required
def update_stock(product_id):
    try:
        new_stock = int(request.form.get('stock', 0))
        db.collection('products').document(product_id).update({
            'stock': new_stock,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        flash('Stock updated successfully', 'success')
    except Exception as e:
        app.logger.error(f"Update stock error: {e}")
        flash('Failed to update stock', 'error')
    return redirect(url_for('stock_management'))

# ============= ANALYTICS & REPORTS =============

@app.route('/revenue')
@login_required
def revenue():
    try:
        orders = [{'id': d.id, **d.to_dict()} for d in db.collection('orders').stream()]
        total_revenue = sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED')
        
        data = {
            'total_revenue': total_revenue,
            'orders': orders,
            'delivered_count': len([o for o in orders if o.get('status') == 'DELIVERED'])
        }
        
        return render_template('revenue.html', data=data, orders=orders)
    except Exception as e:
        app.logger.error(f"Revenue error: {e}")
        return render_template('revenue.html', data={'total_revenue': 0, 'orders': [], 'delivered_count': 0}, orders=[])

@app.route('/analytics')
@login_required
def analytics():
    try:
        orders = [{'id': d.id, **d.to_dict()} for d in db.collection('orders').stream()]
        
        # Calculate analytics
        status_counts = {}
        for order in orders:
            status = order.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        data = {
            'status_counts': status_counts,
            'total_orders': len(orders),
            'total_revenue': sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED')
        }
        
        return render_template('analytics.html', data=data)
    except Exception as e:
        app.logger.error(f"Analytics error: {e}")
        return render_template('analytics.html', data={'status_counts': {}, 'total_orders': 0, 'total_revenue': 0})

@app.route('/notifications')
@login_required
def notifications():
    return render_template('notifications.html')

@app.route('/notifications/test', methods=['POST'])
@login_required
def send_test_notification():
    try:
        user_id = request.form.get('user_id')
        title = request.form.get('title', 'Test Notification')
        body = request.form.get('body', 'This is a test notification')
        
        # Get user and send notification
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists and user_doc.to_dict().get('fcmToken'):
            fcm_token = user_doc.to_dict()['fcmToken']
            # Use data-only message to trigger onMessageReceived in background
            message = messaging.Message(
                data={
                    'title': title,
                    'body': body,
                    'type': 'test',
                    'timestamp': str(int(time.time() * 1000))
                },
                token=fcm_token
            )
            messaging.send(message)
            return jsonify({'success': True, 'message': 'Notification sent successfully'})
        else:
            return jsonify({'success': False, 'error': 'User has no FCM token'}), 400
            
    except Exception as e:
        app.logger.error(f"Test notification error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/activity-logs')
@login_required
def activity_logs():
    try:
        logs = []
        for doc in db.collection('activity_logs').limit(100).stream():
            data = doc.to_dict()
            data['id'] = doc.id
            logs.append(data)
        return render_template('activity_logs.html', logs=logs)
    except Exception as e:
        app.logger.error(f"Activity logs error: {e}")
        return render_template('activity_logs.html', logs=[])

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/sse-test')
@login_required
def sse_test():
    """Test page for SSE connection"""
    return render_template('sse_test.html')

@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        # Password change logic here
        flash('Password changed successfully', 'success')
    except Exception as e:
        app.logger.error(f"Change password error: {e}")
        flash('Failed to change password', 'error')
    return redirect(url_for('settings'))

@app.route('/orders/bulk-update', methods=['POST'])
@login_required
def bulk_update_status():
    try:
        order_ids = request.form.getlist('order_ids')
        new_status = request.form.get('status')
        
        for order_id in order_ids:
            # Update order status
            db.collection('orders').document(order_id).update({'status': new_status})
            
            # Send notification to user
            order_doc = db.collection('orders').document(order_id).get()
            if order_doc.exists:
                user_id = order_doc.to_dict().get('userId')
                if user_id:
                    send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash(f'Updated {len(order_ids)} orders', 'success')
    except Exception as e:
        app.logger.error(f"Bulk update error: {e}")
        flash('Failed to update orders', 'error')
    return redirect(url_for('orders'))

@app.route('/notifications/send-bulk', methods=['POST'])
@login_required
def send_bulk_notification():
    try:
        title = request.form.get('title')
        body = request.form.get('body')
        users = db.collection('users').stream()
        count = 0
        for user_doc in users:
            user_data = user_doc.to_dict()
            if user_data.get('fcmToken'):
                send_notification(user_doc.id, title, body)
                count += 1
        flash(f'Sent notification to {count} users', 'success')
    except Exception as e:
        app.logger.error(f"Bulk notification error: {e}")
        flash('Failed to send notifications', 'error')
    return redirect(url_for('notifications'))

# ============= NOTIFICATIONS =============

def send_notification(user_id, title, body):
    """Send FCM notification to user"""
    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists:
            fcm_token = user_doc.to_dict().get('fcmToken')
            if fcm_token:
                # Use data-only message to trigger onMessageReceived in background
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
        app.logger.error(f"Send notification error: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
