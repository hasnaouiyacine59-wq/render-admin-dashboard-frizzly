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
        force_refresh = request.args.get('refresh', '0') == '1'
        
        # Force refresh if requested
        if force_refresh:
            sync_service.force_refresh('orders')
            current_app.logger.info("[ORDERS] Force refresh triggered")
        
        # Use incremental sync to get all orders
        all_orders = sync_service.sync_orders()
        current_app.logger.info(f"[ORDERS] Loaded {len(all_orders)} orders from cache/sync")
        
        # Filter by status
        if status_filter != 'all':
            filtered_orders = [o for o in all_orders if o.get('status') == status_filter]
        else:
            filtered_orders = all_orders
        
        # Sort by timestamp (newest first)
        filtered_orders.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        # Show all orders (no pagination)
        orders_list = filtered_orders
        total_count = len(filtered_orders)
        
        return render_template('orders.html', 
                             orders=orders_list, 
                             status_filter=status_filter, 
                             valid_statuses=VALID_ORDER_STATUSES,
                             total_count=total_count,
                             total_cached=len(all_orders))
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
        
        firestore_extension.db.collection('orders').document(order_id).update({
            'status': new_status,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        # Invalidate cache when order status changes
        cache.invalidate_pattern('dashboard_stats')
        cache.invalidate_pattern('orders')
        
        # Send notification to user
        order_doc = firestore_extension.db.collection('orders').document(order_id).get()
        if order_doc.exists:
            user_id = order_doc.to_dict().get('userId')
            if user_id:
                send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash('Order status updated', 'success')
    except Exception as e:
        current_app.logger.error(f"Update status error: {e}") # Using current_app.logger
        flash('Failed to update status', 'error')
    
    return redirect(url_for('orders.order_detail', order_id=order_id)) # Updated to blueprint

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
        new_status = request.form.get('status')
        
        for order_id in order_ids:
            # Update order status
            firestore_extension.db.collection('orders').document(order_id).update({'status': new_status})
            
            # Send notification to user
            order_doc = firestore_extension.db.collection('orders').document(order_id).get()
            if order_doc.exists:
                user_id = order_doc.to_dict().get('userId')
                if user_id:
                    send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        # Clear local cache to force resync
        sync_service.force_refresh('orders')
        
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
