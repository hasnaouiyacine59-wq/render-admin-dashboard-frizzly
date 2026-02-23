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
        
        stats = {
            'total_orders': len(orders),
            'pending_orders': len(pending_orders),
            'total_products': len(products),
            'total_users': len(users),
            'low_stock_products': len(low_stock)
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
        return render_template('dashboard.html', stats={'total_orders': 0, 'pending_orders': 0, 'total_products': 0, 'total_users': 0, 'low_stock_products': 0}, recent_orders=[])

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
        
        return render_template('orders.html', orders=orders_list, status_filter=status_filter)
    except Exception as e:
        app.logger.error(f"Orders error: {e}")
        return render_template('orders.html', orders=[], status_filter='all')

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
        
        return render_template('order_detail.html', order=order)
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
        
        return render_template('products.html', products=products_list)
    except Exception as e:
        app.logger.error(f"Products error: {e}")
        return render_template('products.html', products=[])

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
    
    return render_template('product_form.html', product=None)

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
        return render_template('product_form.html', product=product)
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
        
        return render_template('users.html', users=users_list)
    except Exception as e:
        app.logger.error(f"Users error: {e}")
        return render_template('users.html', users=[])

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
        
        return render_template('delivery_logistics.html', orders=orders)
    except Exception as e:
        app.logger.error(f"Delivery logistics error: {e}")
        return render_template('delivery_logistics.html', orders=[])

@app.route('/drivers')
@login_required
def drivers():
    try:
        drivers_list = []
        for doc in db.collection('drivers').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            drivers_list.append(data)
        
        return render_template('drivers.html', drivers=drivers_list)
    except Exception as e:
        app.logger.error(f"Drivers error: {e}")
        return render_template('drivers.html', drivers=[])

@app.route('/stock-management')
@login_required
def stock_management():
    try:
        products = []
        for doc in db.collection('products').stream():
            data = doc.to_dict()
            data['id'] = doc.id
            products.append(data)
        
        return render_template('stock_management.html', products=products)
    except Exception as e:
        app.logger.error(f"Stock management error: {e}")
        return render_template('stock_management.html', products=[])

# ============= ANALYTICS & REPORTS =============

@app.route('/revenue')
@login_required
def revenue():
    try:
        orders = [doc.to_dict() for doc in db.collection('orders').stream()]
        total_revenue = sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED')
        return render_template('revenue.html', total_revenue=total_revenue, orders=orders)
    except Exception as e:
        app.logger.error(f"Revenue error: {e}")
        return render_template('revenue.html', total_revenue=0, orders=[])

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/notifications')
@login_required
def notifications():
    return render_template('notifications.html')

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

# ============= NOTIFICATIONS =============

def send_notification(user_id, title, body):
    """Send FCM notification to user"""
    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists:
            fcm_token = user_doc.to_dict().get('fcmToken')
            if fcm_token:
                message = messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    token=fcm_token
                )
                messaging.send(message)
    except Exception as e:
        app.logger.error(f"Send notification error: {e}")

# ============= SSE FOR REAL-TIME ORDERS =============

@app.route('/api/stream-orders')
@login_required
def stream_orders():
    """Server-Sent Events for real-time order updates"""
    import queue
    
    message_queue = queue.Queue(maxsize=100)
    
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name in ['ADDED', 'MODIFIED']:
                doc = change.document
                data = doc.to_dict()
                event_data = {
                    'id': doc.id,
                    'orderId': data.get('orderId', doc.id),
                    'totalAmount': data.get('totalAmount', 0),
                    'status': data.get('status', 'PENDING'),
                    'type': 'new_order' if change.type.name == 'ADDED' else 'order_update'
                }
                try:
                    message_queue.put_nowait(event_data)
                except queue.Full:
                    pass
    
    col_query = db.collection('orders').limit(20)
    doc_watch = col_query.on_snapshot(on_snapshot)
    
    def generate():
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            
            timeout_count = 0
            while timeout_count < 6:  # 3 minutes
                try:
                    event_data = message_queue.get(timeout=30)
                    event_type = event_data.pop('type', 'message')
                    yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
                    timeout_count = 0
                except queue.Empty:
                    yield f": heartbeat\n\n"
                    timeout_count += 1
        finally:
            doc_watch.unsubscribe()
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
