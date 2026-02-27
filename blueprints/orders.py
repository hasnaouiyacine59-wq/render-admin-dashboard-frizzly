from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app, jsonify
from flask_login import login_required, current_user
import csv
from io import StringIO
from firebase_admin import firestore # Added firestore import
from extensions import firestore_extension
from utils import admin_required, send_notification, VALID_ORDER_STATUSES
from cache import cache
from sync_service import sync_service

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/orders')
@login_required
@admin_required
def orders():
    try:
        status_filter = request.args.get('status', 'all')
        last_doc_id = request.args.get('cursor')  # Cursor-based pagination
        per_page = 50
        
        # Build query with server-side filtering
        orders_ref = firestore_extension.db.collection('orders')
        
        if status_filter != 'all':
            orders_ref = orders_ref.where('status', '==', status_filter)
        
        orders_ref = orders_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        # Cursor-based pagination (efficient)
        if last_doc_id:
            last_doc = firestore_extension.db.collection('orders').document(last_doc_id).get()
            if last_doc.exists:
                orders_ref = orders_ref.start_after(last_doc)
        
        # Fetch one extra to check if there's a next page
        docs = list(orders_ref.limit(per_page + 1).stream())
        
        has_next = len(docs) > per_page
        if has_next:
            docs = docs[:per_page]
        
        orders_list = [{'id': doc.id, **doc.to_dict()} for doc in docs]
        next_cursor = docs[-1].id if docs and has_next else None
        
        return render_template('orders.html', 
                             orders=orders_list, 
                             status_filter=status_filter, 
                             valid_statuses=VALID_ORDER_STATUSES,
                             next_cursor=next_cursor,
                             has_next=has_next)
    except Exception as e:
        current_app.logger.error(f"Orders error: {e}")
        flash('Error loading orders', 'error')
        return render_template('orders.html', orders=[], status_filter='all', valid_statuses=VALID_ORDER_STATUSES, total_count=0)

@orders_bp.route('/orders/<order_id>')
@login_required
@admin_required
def order_detail(order_id):
    try:
        doc = firestore_extension.db.collection('orders').document(order_id).get()
        if not doc.exists:
            flash('Order not found', 'error')
            return redirect(url_for('orders.orders')) # Updated to blueprint
        
        order = doc.to_dict()
        order['id'] = doc.id
        
        # Get available drivers with limit
        drivers = []
        for d in firestore_extension.db.collection('drivers').where(filter=firestore.FieldFilter('status', '==', 'available')).limit(50).stream():
            driver_data = d.to_dict()
            driver_data['id'] = d.id
            drivers.append(driver_data)
        
        return render_template('order_detail.html', order=order, drivers=drivers, valid_statuses=VALID_ORDER_STATUSES)
    except Exception as e:
        current_app.logger.error(f"Order detail error: {e}") # Using current_app.logger
        flash('Error loading order', 'error')
        return redirect(url_for('orders.orders')) # Updated to blueprint

@orders_bp.route('/orders/<order_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    try:
        new_status = request.form.get('status')
        user_id = request.form.get('user_id')  # Pass userId from form to avoid extra read
        
        # Update order status
        firestore_extension.db.collection('orders').document(order_id).update({
            'status': new_status,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        # Send notification using passed user_id (no extra read)
        if user_id:
            send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash('Order status updated', 'success')
    except Exception as e:
        current_app.logger.error(f"Update status error: {e}")
        flash('Failed to update status', 'error')
    
    return redirect(url_for('orders.order_detail', order_id=order_id))

@orders_bp.route('/orders/export')
@login_required
@admin_required
def export_orders():
    """Export orders to CSV (limited to recent 1000)"""
    try:
        orders = [{'id': doc.id, **doc.to_dict()} for doc in firestore_extension.db.collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1000).stream()]
        
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
        current_app.logger.error(f"Export orders error: {e}") # Using current_app.logger
        flash('Failed to export orders', 'error')
        return redirect(url_for('orders.orders')) # Updated to blueprint

@orders_bp.route('/orders/<order_id>/assign-driver', methods=['POST'])
@login_required
@admin_required
def assign_driver(order_id):
    try:
        driver_id = request.form.get('driver_id')
        firestore_extension.db.collection('orders').document(order_id).update({
            'driverId': driver_id,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        flash('Driver assigned successfully', 'success')
    except Exception as e:
        current_app.logger.error(f"Assign driver error: {e}") # Using current_app.logger
        flash('Failed to assign driver', 'error')
    return redirect(url_for('orders.order_detail', order_id=order_id))

@orders_bp.route('/orders/bulk-update', methods=['POST'])
@login_required
@admin_required
def bulk_update_status():
    try:
        order_ids = request.form.getlist('order_ids')
        user_ids = request.form.getlist('user_ids')  # Get userIds from frontend
        new_status = request.form.get('status')
        
        if not order_ids:
            flash('No orders selected', 'error')
            return redirect(url_for('orders.orders'))
        
        # Batch write (efficient)
        batch = firestore_extension.db.batch()
        for order_id in order_ids:
            ref = firestore_extension.db.collection('orders').document(order_id)
            batch.update(ref, {
                'status': new_status,
                'updatedAt': firestore.SERVER_TIMESTAMP
            })
        batch.commit()
        
        # Send notifications using passed user_ids (no extra reads)
        for i, order_id in enumerate(order_ids):
            if i < len(user_ids) and user_ids[i]:
                send_notification(user_ids[i], 'Order Update', f'Your order status: {new_status}')
        
        flash(f'Updated {len(order_ids)} orders', 'success')
    except Exception as e:
        current_app.logger.error(f"Bulk update error: {e}")
        flash('Failed to update orders', 'error')
    return redirect(url_for('orders.orders'))

@orders_bp.route('/api/sync-orders', methods=['POST'])
@login_required
@admin_required
def sync_orders_api():
    """API endpoint to manually trigger order sync"""
    try:
        orders = sync_service.sync_orders()
        return jsonify({
            'success': True,
            'total_orders': len(orders),
            'message': 'Orders synced successfully'
        })
    except Exception as e:
        current_app.logger.error(f"Sync error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
