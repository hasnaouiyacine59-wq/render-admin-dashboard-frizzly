from flask import Blueprint, render_template, current_app, flash, session
from flask_login import login_required
from firebase_admin import firestore
from extensions import firestore_extension
from utils import admin_required
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_cached_stats():
    """Cache dashboard stats for 5 minutes"""
    cache_key = 'dashboard_stats'
    cache_time_key = 'dashboard_stats_time'
    
    # Check if cache is valid (less than 5 minutes old)
    if cache_key in session and cache_time_key in session:
        cache_age = datetime.now().timestamp() - session[cache_time_key]
        if cache_age < 300:  # 5 minutes
            return session[cache_key]
    
    return None

def set_cached_stats(stats):
    """Store stats in session cache"""
    session['dashboard_stats'] = stats
    session['dashboard_stats_time'] = datetime.now().timestamp()

@dashboard_bp.route('/')
@login_required
@admin_required
def dashboard():
    try:
        # Try to get cached stats first
        cached = get_cached_stats()
        if cached:
            stats = cached
        else:
            db = firestore_extension.db
            
            # Use aggregation queries to reduce reads
            orders_ref = db.collection('orders')
            products_ref = db.collection('products')
            users_ref = db.collection('users')
            
            # Get counts efficiently with limits
            total_orders = sum(1 for _ in orders_ref.limit(1000).stream())
            total_products = sum(1 for _ in products_ref.limit(500).stream())
            total_users = sum(1 for _ in users_ref.limit(1000).stream())
            
            # Get pending orders count with filter
            pending_orders = sum(1 for _ in orders_ref.where(
                filter=firestore.FieldFilter('status', '==', 'PENDING')
            ).limit(100).stream())
            
            # Get low stock count with filter
            low_stock_products = sum(1 for _ in products_ref.where(
                filter=firestore.FieldFilter('stock', '<', 10)
            ).limit(100).stream())
            
            # Calculate revenue from delivered orders only
            delivered_orders = orders_ref.where(
                filter=firestore.FieldFilter('status', '==', 'DELIVERED')
            ).limit(500).stream()
            
            total_revenue = sum(doc.to_dict().get('totalAmount', 0) for doc in delivered_orders)
            
            stats = {
                'total_orders': total_orders,
                'pending_orders': pending_orders,
                'total_products': total_products,
                'total_users': total_users,
                'low_stock_products': low_stock_products,
                'total_revenue': total_revenue
            }
            
            # Cache the stats
            set_cached_stats(stats)
        
        # Always fetch recent orders (but limit to 10)
        recent_orders_query = firestore_extension.db.collection('orders').order_by(
            'timestamp', direction=firestore.Query.DESCENDING
        ).limit(10)
        orders_data = [{'id': doc.id, **doc.to_dict()} for doc in recent_orders_query.stream()]
        
        return render_template('dashboard.html', stats=stats, recent_orders=orders_data)
        
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'error')
        return render_template('dashboard.html', 
            stats={'total_orders': 0, 'pending_orders': 0, 'total_products': 0, 
                   'total_users': 0, 'low_stock_products': 0, 'total_revenue': 0}, 
            recent_orders=[])
