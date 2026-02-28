"""
PostgreSQL Database Helper for Flask Admin Dashboard
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import os

def get_db():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        database=os.getenv('POSTGRES_DB', 'frizzly'),
        user=os.getenv('POSTGRES_USER', 'admin'),
        password=os.getenv('POSTGRES_PASSWORD', 'password')
    )

def get_orders(limit=50, offset=0, status=None):
    """Get orders with pagination"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM orders"
    params = []
    
    if status:
        query += " WHERE status = %s"
        params.append(status)
    
    query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    orders = cur.fetchall()
    cur.close()
    conn.close()
    
    return orders

def get_order_by_id(order_id):
    """Get single order"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def update_order_status(order_id, status):
    """Update order status"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s", (status, order_id))
    conn.commit()
    cur.close()
    conn.close()

def get_products(limit=50, offset=0):
    """Get products with pagination"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM products ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
    products = cur.fetchall()
    cur.close()
    conn.close()
    return products

def get_users(limit=50, offset=0):
    """Get users with pagination"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def get_dashboard_stats():
    """Get dashboard statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            COUNT(*) as total_orders,
            COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending_orders,
            COUNT(CASE WHEN status = 'DELIVERED' THEN 1 END) as delivered_orders,
            SUM(CASE WHEN status = 'DELIVERED' THEN total_amount ELSE 0 END) as total_revenue,
            (SELECT COUNT(*) FROM products) as total_products,
            (SELECT COUNT(*) FROM users) as total_users
        FROM orders
    """)
    
    stats = cur.fetchone()
    cur.close()
    conn.close()
    return stats

def get_revenue_by_month():
    """Get revenue grouped by month"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            TO_CHAR(to_timestamp(timestamp / 1000), 'YYYY-MM') as month,
            SUM(CASE WHEN status = 'DELIVERED' THEN total_amount ELSE 0 END) as revenue
        FROM orders
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """)
    
    revenue = cur.fetchall()
    cur.close()
    conn.close()
    return revenue

def get_orders_by_status():
    """Get order count by status"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT status, COUNT(*) as count
        FROM orders
        GROUP BY status
    """)
    
    status_counts = cur.fetchall()
    cur.close()
    conn.close()
    return status_counts
