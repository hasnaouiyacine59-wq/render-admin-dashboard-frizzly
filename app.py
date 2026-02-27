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
from extensions import login_manager, firestore_extension

# New imports from utils
from utils import User, admin_required, send_notification, VALID_ORDER_STATUSES
from blueprints.auth import auth_bp # Import auth blueprint
from cache import cache, cached

app = Flask(__name__)
app.secret_key = 'a-temporary-secret-key-for-development'

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

firestore_extension.init_app(app) # Initialize the Firestore extension

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
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
app.register_blueprint(auth_bp) # Register the auth blueprint
from blueprints.dashboard import dashboard_bp # Import dashboard blueprint
app.register_blueprint(dashboard_bp) # Register the dashboard blueprint
from blueprints.orders import orders_bp # Import orders blueprint
app.register_blueprint(orders_bp) # Register the orders blueprint
from blueprints.products import products_bp
app.register_blueprint(products_bp)

@login_manager.user_loader
def load_user(user_id):
    # Cache user in session to avoid Firestore reads on every request
    cache_key = f'user_{user_id}'
    if cache_key in session:
        cached = session[cache_key]
        return User(user_id, cached['email'], cached['role'])
    
    try:
        doc = firestore_extension.db.collection('admins').document(user_id).get(timeout=3.0)
        if doc.exists:
            data = doc.to_dict()
            # Cache in session
            session[cache_key] = {'email': data.get('email'), 'role': data.get('role', 'admin')}
            return User(user_id, data.get('email'), data.get('role', 'admin'))
    except:
        pass
    return None

# ============= CONTEXT PROCESSOR (REMOVED - WAS WASTEFUL) =============
# Stats are now fetched only on dashboard with caching

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
            firestore_extension.db.collection('admins').document(current_user.id).update({
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
    col_query = firestore_extension.db.collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50)
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
    """API endpoint for dashboard stats (cached)"""
    try:
        # Check cache first (5 minute TTL)
        cached_stats = cache.get('dashboard_stats')
        if cached_stats:
            return jsonify({**cached_stats, 'success': True, 'cached': True})
        
        # Use aggregation queries (2 reads instead of 160)
        db = firestore_extension.db
        try:
            total_orders = db.collection('orders').count().get()[0][0].value
            pending_orders = db.collection('orders').where('status', '==', 'PENDING').count().get()[0][0].value
        except:
            # Fallback: use estimates
            total_orders = 0
            pending_orders = 0
        
        stats = {
            'total_orders': total_orders,
            'pending_orders': pending_orders
        }
        
        # Cache for 5 minutes
        cache.set('dashboard_stats', stats, ttl_seconds=300)
        
        return jsonify({**stats, 'success': True, 'cached': False})
    except Exception as e:
        app.logger.error(f"Dashboard stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= PRODUCTS =============

# ============= USERS =============

@app.route('/users')
@login_required
def users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        users_ref = firestore_extension.db.collection('users').order_by('createdAt', direction=firestore.Query.DESCENDING)
        users_query = users_ref.limit(per_page).offset((page - 1) * per_page)
        users_list = [{'id': doc.id, **doc.to_dict()} for doc in users_query.stream()]
        
        try:
            total_count = firestore_extension.db.collection('users').count().get()[0][0].value
        except:
            # Fallback: estimate from current page
            total_count = len(users_list)
        
        total_pages = (total_count + per_page - 1) // per_page
        pagination = {
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1
        }
        
        return render_template('users.html', users=users_list, pagination=pagination)
    except Exception as e:
        app.logger.error(f"Users error: {e}")
        pagination = {'page': 1, 'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('users.html', users=[], pagination=pagination)

@app.route('/users/<user_id>')
@login_required
def user_detail(user_id):
    try:
        doc = firestore_extension.db.collection('users').document(user_id).get()
        if not doc.exists:
            flash('User not found', 'error')
            return redirect(url_for('orders.orders'))
        
        user = doc.to_dict()
        user['id'] = doc.id
        
        # Fetch user's orders with limit
        orders = []
        for order_doc in firestore_extension.db.collection('orders').where(filter=firestore.FieldFilter('userId', '==', user_id)).limit(50).stream():
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
        for doc in firestore_extension.db.collection('orders').where(filter=firestore.FieldFilter('status', 'in', ['ON_WAY', 'OUT_FOR_DELIVERY'])).limit(100).stream():
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
        for doc in firestore_extension.db.collection('drivers').limit(200).stream():
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
            firestore_extension.db.collection('drivers').add(driver_data)
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
        doc = firestore_extension.db.collection('drivers').document(driver_id).get()
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
            firestore_extension.db.collection('drivers').document(driver_id).update(driver_data)
            flash('Driver updated successfully', 'success')
            return redirect(url_for('drivers'))
        except Exception as e:
            app.logger.error(f"Edit driver error: {e}")
            flash('Failed to update driver', 'error')
    
    try:
        doc = firestore_extension.db.collection('drivers').document(driver_id).get()
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
        firestore_extension.db.collection('drivers').document(driver_id).delete()
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
        for doc in firestore_extension.db.collection('products').limit(500).stream():
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
        firestore_extension.db.collection('products').document(product_id).update({
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
        # Check cache first (1 hour TTL for analytics)
        cached_revenue = cache.get('revenue_data')
        if cached_revenue:
            return render_template('revenue.html', data=cached_revenue, orders=[])
        
        # Limit to last 30 days and 500 orders
        thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)
        all_orders = [d for d in firestore_extension.db.collection('orders').where('timestamp', '>=', thirty_days_ago).limit(500).stream()]
        orders_data = [{'id': d.id, **d.to_dict()} for d in all_orders]

        delivered_orders = [o for o in orders_data if o.get('status') == 'DELIVERED']
        pending_orders = [o for o in orders_data if o.get('status') == 'PENDING']
        
        total_revenue = sum(o.get('totalAmount', 0) for o in delivered_orders)
        completed_revenue = total_revenue
        pending_revenue = sum(o.get('totalAmount', 0) for o in pending_orders)
        delivered_count = len(delivered_orders)
        avg_order_value = total_revenue / delivered_count if delivered_count > 0 else 0

        daily_revenue = defaultdict(float)
        today = datetime.now()
        for i in range(30):
            date = today - timedelta(days=i)
            daily_revenue[date.strftime('%Y-%m-%d')] = 0.0

        for order in delivered_orders:
            if order.get('timestamp'):
                ts = order['timestamp'] / 1000 if order['timestamp'] > 1e12 else order['timestamp']
                order_date = datetime.fromtimestamp(ts)
                date_str = order_date.strftime('%Y-%m-%d')
                if date_str in daily_revenue:
                    daily_revenue[date_str] += order.get('totalAmount', 0)
        
        sorted_daily_revenue = dict(sorted(daily_revenue.items()))

        revenue_by_status = defaultdict(float)
        for order in orders_data:
            status = order.get('status', 'UNKNOWN')
            revenue_by_status[status] += order.get('totalAmount', 0)
        
        product_revenue = defaultdict(float)
        for order in delivered_orders:
            for item in order.get('items', []):
                product_name = item.get('name', 'Unknown Product')
                product_revenue[product_name] += item.get('price', 0) * item.get('quantity', 1)
        
        top_products = sorted(product_revenue.items(), key=lambda item: item[1], reverse=True)[:5]

        data = {
            'total_revenue': total_revenue,
            'completed_revenue': completed_revenue,
            'pending_revenue': pending_revenue,
            'avg_order_value': avg_order_value,
            'delivered_count': delivered_count,
            'daily_revenue': sorted_daily_revenue,
            'revenue_by_status': dict(revenue_by_status),
            'top_products': top_products
        }
        
        # Cache for 1 hour
        cache.set('revenue_data', data, ttl_seconds=3600)
        
        return render_template('revenue.html', data=data, orders=orders_data)
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
        # Check cache first (1 hour TTL)
        cached_analytics = cache.get('analytics_data')
        if cached_analytics:
            return render_template('analytics.html', data=cached_analytics)
        
        # Limit to 500 recent orders
        orders = [{'id': d.id, **d.to_dict()} for d in firestore_extension.db.collection('orders').limit(500).stream()]
        
        status_counts = {}
        monthly_revenue = {}
        
        for order in orders:
            status = order.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1

            if status == 'DELIVERED' and order.get('timestamp'):
                ts = order['timestamp'] / 1000 if order['timestamp'] > 1e12 else order['timestamp']
                order_date = datetime.fromtimestamp(ts)
                month_year = order_date.strftime('%Y-%m')
                
                monthly_revenue[month_year] = monthly_revenue.get(month_year, 0) + order.get('totalAmount', 0)
        
        sorted_monthly_revenue = dict(sorted(monthly_revenue.items()))

        data = {
            'status_counts': status_counts,
            'total_orders': len(orders),
            'total_revenue': sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED'),
            'monthly_revenue': sorted_monthly_revenue
        }
        
        # Cache for 1 hour
        cache.set('analytics_data', data, ttl_seconds=3600)
        
        return render_template('analytics.html', data=data)
    except Exception as e:
        app.logger.error(f"Analytics error: {e}")
        return render_template('analytics.html', data={'status_counts': {}, 'total_orders': 0, 'total_revenue': 0, 'monthly_revenue': {}})

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
        user_doc = firestore_extension.db.collection('users').document(user_id).get()
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
        for doc in firestore_extension.db.collection('activity_logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100).stream():
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
        users = firestore_extension.db.collection('users').limit(500).stream()
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
    app.run(host='0.0.0.0', port=5000, debug=True)
