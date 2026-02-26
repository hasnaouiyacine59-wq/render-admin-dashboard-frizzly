from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
import csv
from io import StringIO
from firebase_admin import firestore # Added firestore import
from ..app import db # Assuming db is initialized in app.py
from ..utils import admin_required, send_notification, VALID_ORDER_STATUSES

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/orders')
@login_required
@admin_required
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
        current_app.logger.error(f"Orders error: {e}") # Using current_app.logger
        flash('Error loading orders', 'error')
        return render_template('orders.html', orders=[], status_filter='all', valid_statuses=VALID_ORDER_STATUSES)

@orders_bp.route('/orders/<order_id>')
@login_required
@admin_required
def order_detail(order_id):
    try:
        doc = db.collection('orders').document(order_id).get()
        if not doc.exists:
            flash('Order not found', 'error')
            return redirect(url_for('orders.orders')) # Updated to blueprint
        
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
        current_app.logger.error(f"Order detail error: {e}") # Using current_app.logger
        flash('Error loading order', 'error')
        return redirect(url_for('orders.orders')) # Updated to blueprint

@orders_bp.route('/orders/<order_id>/update-status', methods=['POST'])
@login_required
@admin_required
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
        current_app.logger.error(f"Update status error: {e}") # Using current_app.logger
        flash('Failed to update status', 'error')
    
    return redirect(url_for('orders.order_detail', order_id=order_id)) # Updated to blueprint

@orders_bp.route('/orders/export')
@login_required
@admin_required
def export_orders():
    """Export orders to CSV"""
    try:
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
        current_app.logger.error(f"Export orders error: {e}") # Using current_app.logger
        flash('Failed to export orders', 'error')
        return redirect(url_for('orders.orders')) # Updated to blueprint

@orders_bp.route('/orders/<order_id>/assign-driver', methods=['POST'])
@login_required
@admin_required
def assign_driver(order_id):
    try:
        driver_id = request.form.get('driver_id')
        db.collection('orders').document(order_id).update({
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
            db.collection('orders').document(order_id).update({'status': new_status})
            
            # Send notification to user
            order_doc = db.collection('orders').document(order_id).get()
            if order_doc.exists:
                user_id = order_doc.to_dict().get('userId')
                if user_id:
                    send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash(f'Updated {len(order_ids)} orders', 'success')
    except Exception as e:
        current_app.logger.error(f"Bulk update error: {e}") # Using current_app.logger
        flash('Failed to update orders', 'error')
    return redirect(url_for('orders.orders')) # Updated to blueprint
