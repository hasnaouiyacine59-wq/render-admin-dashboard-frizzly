from flask import Blueprint, render_template, current_app, flash, session
from flask_login import login_required
from firebase_admin import firestore
from extensions import firestore_extension
from utils import admin_required
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_cached_stats():
    """Cache dashboard stats globally for 5 minutes"""
    return cache.get('dashboard_stats_global')

def set_cached_stats(stats):
    """Store stats in global cache"""
    cache.set('dashboard_stats_global', stats, ttl_seconds=300)

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
            
            # Use aggregation queries (5 reads instead of 160+)
            try:
                total_orders = db.collection('orders').count().get()[0][0].value
                total_products = db.collection('products').count().get()[0][0].value
                total_users = db.collection('users').count().get()[0][0].value
                pending_orders = db.collection('orders').where('status', '==', 'PENDING').count().get()[0][0].value
                low_stock_products = db.collection('products').where('stock', '<', 10).count().get()[0][0].value
            except:
                # Fallback: use estimates
                total_orders = 0
                total_products = 0
                total_users = 0
                pending_orders = 0
                low_stock_products = 0
            
            # Calculate revenue using server-side aggregation (1 read instead of 500)
            try:
                from firebase_admin.firestore import aggregation
                delivered_query = db.collection('orders').where('status', '==', 'DELIVERED')
                total_revenue = delivered_query.sum('totalAmount').get()[0][0].value
            except:
                # Fallback: limited query
                delivered_orders = db.collection('orders').where('status', '==', 'DELIVERED').limit(500).stream()
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
