from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
import csv
from io import StringIO
from firebase_admin import firestore
from extensions import firestore_extension
from utils import admin_required, send_notification, VALID_ORDER_STATUSES

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/orders')
@login_required
@admin_required
def orders():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        status_filter = request.args.get('status', 'all')
        
        orders_ref = firestore_extension.db.collection('orders')
        
        # Apply status filter
        if status_filter != 'all':
            orders_ref = orders_ref.where(filter=firestore.FieldFilter('status', '==', status_filter))
        
        # Order by timestamp
        orders_ref = orders_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        # Pagination with offset
        orders_query = orders_ref.limit(per_page).offset((page - 1) * per_page)
        orders_list = [{'id': doc.id, **doc.to_dict()} for doc in orders_query.stream()]
        
        # Get total count (use aggregation if available)
        try:
            if status_filter != 'all':
                total_count = firestore_extension.db.collection('orders').where('status', '==', status_filter).count().get()[0][0].value
            else:
                total_count = firestore_extension.db.collection('orders').count().get()[0][0].value
        except:
            # Fallback: limited count
            if status_filter != 'all':
                total_count = sum(1 for _ in firestore_extension.db.collection('orders').where('status', '==', status_filter).limit(1000).stream())
            else:
                total_count = sum(1 for _ in firestore_extension.db.collection('orders').limit(1000).stream())
        
        total_pages = (total_count + per_page - 1) // per_page
        
        pagination = {
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1
        }
        
        return render_template('orders.html', 
                             orders=orders_list, 
                             status_filter=status_filter, 
                             valid_statuses=VALID_ORDER_STATUSES,
                             pagination=pagination)
    except Exception as e:
        current_app.logger.error(f"Orders error: {e}")
        flash('Error loading orders', 'error')
        pagination = {'page': 1, 'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('orders.html', orders=[], status_filter='all', valid_statuses=VALID_ORDER_STATUSES, pagination=pagination)

@orders_bp.route('/orders/<order_id>')
@login_required
@admin_required
def order_detail(order_id):
    try:
        doc = firestore_extension.db.collection('orders').document(order_id).get()
        if not doc.exists:
            flash('Order not found', 'error')
            return redirect(url_for('orders.orders'))
        
        order = doc.to_dict()
        order['id'] = doc.id
        
        # Get available drivers (limited)
        drivers = []
        for d in firestore_extension.db.collection('drivers').where(filter=firestore.FieldFilter('status', '==', 'available')).limit(50).stream():
            driver_data = d.to_dict()
            driver_data['id'] = d.id
            drivers.append(driver_data)
        
        return render_template('order_detail.html', order=order, drivers=drivers, valid_statuses=VALID_ORDER_STATUSES)
    except Exception as e:
        current_app.logger.error(f"Order detail error: {e}")
        flash('Error loading order', 'error')
        return redirect(url_for('orders.orders'))

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
        
        # Send notification to user
        order_doc = firestore_extension.db.collection('orders').document(order_id).get()
        if order_doc.exists:
            user_id = order_doc.to_dict().get('userId')
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
        current_app.logger.error(f"Export orders error: {e}")
        flash('Failed to export orders', 'error')
        return redirect(url_for('orders.orders'))

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
        current_app.logger.error(f"Assign driver error: {e}")
        flash('Failed to assign driver', 'error')
    return redirect(url_for('orders.order_detail', order_id=order_id))

@orders_bp.route('/orders/bulk-update', methods=['POST'])
@login_required
@admin_required
def bulk_update_status():
    try:
        order_ids = request.form.getlist('order_ids')
        new_status = request.form.get('status')
        
        # Limit bulk operations
        if len(order_ids) > 100:
            flash('Cannot update more than 100 orders at once', 'error')
            return redirect(url_for('orders.orders'))
        
        for order_id in order_ids:
            firestore_extension.db.collection('orders').document(order_id).update({'status': new_status})
            
            # Send notification to user
            order_doc = firestore_extension.db.collection('orders').document(order_id).get()
            if order_doc.exists:
                user_id = order_doc.to_dict().get('userId')
                if user_id:
                    send_notification(user_id, 'Order Update', f'Your order status: {new_status}')
        
        flash(f'Updated {len(order_ids)} orders', 'success')
    except Exception as e:
        current_app.logger.error(f"Bulk update error: {e}")
        flash('Failed to update orders', 'error')
    return redirect(url_for('orders.orders'))
