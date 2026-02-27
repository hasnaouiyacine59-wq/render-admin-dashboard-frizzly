"""
Background Job for Pre-computing Analytics
Run this daily/hourly to pre-compute expensive analytics
"""
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from collections import defaultdict

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate('/etc/secrets/serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()

def compute_daily_analytics():
    """
    Pre-compute analytics and store in daily_reports collection
    Run this once per day (e.g., via cron or Cloud Scheduler)
    """
    print("[ANALYTICS] Starting daily analytics computation...")
    
    # Get yesterday's date
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    # Get all orders from yesterday
    start_timestamp = int(yesterday.replace(hour=0, minute=0, second=0).timestamp() * 1000)
    end_timestamp = int(yesterday.replace(hour=23, minute=59, second=59).timestamp() * 1000)
    
    orders = db.collection('orders').where('timestamp', '>=', start_timestamp).where('timestamp', '<=', end_timestamp).stream()
    
    # Compute statistics
    total_orders = 0
    total_revenue = 0
    status_counts = defaultdict(int)
    
    for order in orders:
        data = order.to_dict()
        total_orders += 1
        status = data.get('status', 'UNKNOWN')
        status_counts[status] += 1
        
        if status == 'DELIVERED':
            total_revenue += data.get('totalAmount', 0)
    
    # Store pre-computed results
    report = {
        'date': date_str,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'status_counts': dict(status_counts),
        'computed_at': firestore.SERVER_TIMESTAMP
    }
    
    db.collection('daily_reports').document(date_str).set(report)
    print(f"[ANALYTICS] Computed report for {date_str}: {total_orders} orders, ${total_revenue} revenue")

def compute_monthly_analytics():
    """
    Pre-compute monthly analytics
    Run this once per month
    """
    print("[ANALYTICS] Starting monthly analytics computation...")
    
    # Get last month
    today = datetime.now()
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_day_last_month.replace(day=1)
    
    month_str = last_day_last_month.strftime('%Y-%m')
    
    # Get all orders from last month
    start_timestamp = int(first_day_last_month.timestamp() * 1000)
    end_timestamp = int(last_day_last_month.replace(hour=23, minute=59, second=59).timestamp() * 1000)
    
    # Use aggregation for efficiency
    try:
        from firebase_admin.firestore import aggregation
        
        orders_query = db.collection('orders').where('timestamp', '>=', start_timestamp).where('timestamp', '<=', end_timestamp)
        
        total_orders = orders_query.count().get()[0][0].value
        delivered_query = orders_query.where('status', '==', 'DELIVERED')
        total_revenue = delivered_query.sum('totalAmount').get()[0][0].value
        
        report = {
            'month': month_str,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'computed_at': firestore.SERVER_TIMESTAMP
        }
        
        db.collection('monthly_reports').document(month_str).set(report)
        print(f"[ANALYTICS] Computed report for {month_str}: {total_orders} orders, ${total_revenue} revenue")
    except Exception as e:
        print(f"[ANALYTICS] Error: {e}")

if __name__ == '__main__':
    # Run daily analytics
    compute_daily_analytics()
    
    # Uncomment to run monthly (only on 1st of month)
    # if datetime.now().day == 1:
    #     compute_monthly_analytics()
