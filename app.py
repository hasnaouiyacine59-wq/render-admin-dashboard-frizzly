"""
FRIZZLY Admin Dashboard - Direct Firebase Version for Render
Uses /etc/secrets/serviceAccountKey.json for Firebase connection
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timedelta
from collections import defaultdict
import os
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from extensions import db, login_manager

# New imports from utils
from utils import User, admin_required, send_notification, VALID_ORDER_STATUSES
from blueprints.auth import auth_bp # Import auth blueprint

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')

# CRITICAL SECURITY CHECK: Ensure SECRET_KEY is not default in production
if not app.debug and app.secret_key == 'change-me-in-production':
    raise ValueError("CRITICAL ERROR: SECRET_KEY must be set to a strong, unique value in production. "
                     "Do NOT use 'change-me-in-production'.")

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

# db is now imported from extensions

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
login_manager.init_app(app)
app.register_blueprint(auth_bp) # Register the auth blueprint
from blueprints.dashboard import dashboard_bp # Import dashboard blueprint
app.register_blueprint(dashboard_bp) # Register the dashboard blueprint
from blueprints.orders import orders_bp # Import orders blueprint
app.register_blueprint(orders_bp) # Register the orders blueprint

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

# ============= PRODUCTS =============

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
            return redirect(url_for('orders.orders'))
        
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
        return redirect(url_for('orders.orders'))

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
        all_orders = [d for d in db.collection('orders').stream()]
        orders_data = [{'id': d.id, **d.to_dict()} for d in all_orders]

        # Filter orders by status
        delivered_orders = [o for o in orders_data if o.get('status') == 'DELIVERED']
        pending_orders = [o for o in orders_data if o.get('status') == 'PENDING']
        
        # Calculate basic stats
        total_revenue = sum(o.get('totalAmount', 0) for o in delivered_orders)
        completed_revenue = total_revenue # Same as total_revenue for delivered
        pending_revenue = sum(o.get('totalAmount', 0) for o in pending_orders)
        delivered_count = len(delivered_orders)
        avg_order_value = total_revenue / delivered_count if delivered_count > 0 else 0

        # Daily Revenue (Last 30 Days)
        daily_revenue = defaultdict(float)
        today = datetime.now()
        for i in range(30):
            date = today - timedelta(days=i)
            daily_revenue[date.strftime('%Y-%m-%d')] = 0.0 # Initialize for last 30 days

        for order in delivered_orders:
            if order.get('timestamp'):
                ts = order['timestamp'] / 1000 if order['timestamp'] > 1e12 else order['timestamp']
                order_date = datetime.fromtimestamp(ts)
                date_str = order_date.strftime('%Y-%m-%d')
                if date_str in daily_revenue:
                    daily_revenue[date_str] += order.get('totalAmount', 0)
        
        # Sort daily revenue by date
        sorted_daily_revenue = dict(sorted(daily_revenue.items()))

        # Revenue by Status
        revenue_by_status = defaultdict(float)
        for order in orders_data: # Use all orders for status breakdown
            status = order.get('status', 'UNKNOWN')
            revenue_by_status[status] += order.get('totalAmount', 0)
        
        # Top Products by Revenue
        product_revenue = defaultdict(float)
        for order in delivered_orders:
            for item in order.get('items', []): # Assuming 'items' is a list of product dicts
                product_name = item.get('name', 'Unknown Product')
                product_revenue[product_name] += item.get('price', 0) * item.get('quantity', 1)
        
        top_products = sorted(product_revenue.items(), key=lambda item: item[1], reverse=True)[:5] # Top 5

        data = {
            'total_revenue': total_revenue,
            'completed_revenue': completed_revenue,
            'pending_revenue': pending_revenue,
            'avg_order_value': avg_order_value,
            'delivered_count': delivered_count, # Keep for completeness, though not directly used in template stats cards
            'daily_revenue': sorted_daily_revenue,
            'revenue_by_status': dict(revenue_by_status),
            'top_products': top_products
        }
        
        return render_template('revenue.html', data=data, orders=orders_data) # Pass orders_data for any other potential use
    except Exception as e:
        app.logger.error(f"Revenue error: {e}")
        return render_template('revenue.html', 
                               data={
                                   'total_revenue': 0, 
                                   'completed_revenue': 0, 
                                   'pending_revenue': 0, 
                                   'avg_order_value': 0,
                                   'daily_revenue': {},
                                   'revenue_by_status': {},
                                   'top_products': []
                               }, 
                               orders=[])

@app.route('/analytics')
@login_required
def analytics():
    try:
        orders = [{'id': d.id, **d.to_dict()} for d in db.collection('orders').stream()]
        
        # Calculate analytics
        status_counts = {}
        monthly_revenue = {} # New calculation
        
        for order in orders:
            status = order.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1

            # Calculate monthly revenue for DELIVERED orders
            if status == 'DELIVERED' and order.get('timestamp'):
                # Convert timestamp to datetime object
                ts = order['timestamp'] / 1000 if order['timestamp'] > 1e12 else order['timestamp']
                order_date = datetime.fromtimestamp(ts)
                month_year = order_date.strftime('%Y-%m') # e.g., "2026-02"
                
                monthly_revenue[month_year] = monthly_revenue.get(month_year, 0) + order.get('totalAmount', 0)
        
        # Sort monthly revenue by month-year
        sorted_monthly_revenue = dict(sorted(monthly_revenue.items()))

        data = {
            'status_counts': status_counts,
            'total_orders': len(orders),
            'total_revenue': sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED'),
            'monthly_revenue': sorted_monthly_revenue # Pass to template
        }
        
        return render_template('analytics.html', data=data)
    except Exception as e:
        app.logger.error(f"Analytics error: {e}")
        return render_template('analytics.html', data={'status_counts': {}, 'total_orders': 0, 'total_revenue': 0, 'monthly_revenue': {}}) # Add default

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
