from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..app import db # Assuming db is initialized in app.py
from ..utils import admin_required, User # Assuming User is in utils.py

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
@admin_required
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
        # app.logger.error(f"Dashboard error: {e}") # Logger not directly accessible here yet
        flash('Error loading dashboard', 'error')
        return render_template('dashboard.html', stats={'total_orders': 0, 'pending_orders': 0, 'total_products': 0, 'total_users': 0, 'low_stock_products': 0, 'total_revenue': 0}, recent_orders=[])
