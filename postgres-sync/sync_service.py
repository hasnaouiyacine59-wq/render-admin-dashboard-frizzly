"""
Firebase to PostgreSQL Sync Service
Listens to Firestore changes and syncs to PostgreSQL in real-time
"""
import firebase_admin
from firebase_admin import credentials, firestore
import psycopg2
from psycopg2.extras import Json
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase
cred_path = os.getenv('FIREBASE_CREDENTIALS', '/app/serviceAccountKey.json')
if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# PostgreSQL connection
def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        database=os.getenv('POSTGRES_DB', 'frizzly'),
        user=os.getenv('POSTGRES_USER', 'admin'),
        password=os.getenv('POSTGRES_PASSWORD', 'password')
    )

def sync_order(order_id, order_data):
    """Sync single order to PostgreSQL"""
    conn = get_pg_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO orders (id, order_id, user_id, status, total_amount, timestamp, customer_name, items)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                total_amount = EXCLUDED.total_amount,
                customer_name = EXCLUDED.customer_name,
                items = EXCLUDED.items,
                updated_at = NOW()
        """, (
            order_id,
            order_data.get('orderId', order_id),
            order_data.get('userId'),
            order_data.get('status'),
            order_data.get('totalAmount'),
            order_data.get('timestamp'),
            order_data.get('customerName'),
            Json(order_data.get('items', []))
        ))
        conn.commit()
        logger.info(f"✅ Synced order: {order_id}")
    except Exception as e:
        logger.error(f"❌ Failed to sync order {order_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def sync_product(product_id, product_data):
    """Sync single product to PostgreSQL"""
    conn = get_pg_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO products (id, name, description, price, category, stock, image_url, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                price = EXCLUDED.price,
                category = EXCLUDED.category,
                stock = EXCLUDED.stock,
                image_url = EXCLUDED.image_url,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
        """, (
            product_id,
            product_data.get('name'),
            product_data.get('description'),
            product_data.get('price'),
            product_data.get('category'),
            product_data.get('stock'),
            product_data.get('imageUrl'),
            product_data.get('isActive', True)
        ))
        conn.commit()
        logger.info(f"✅ Synced product: {product_id}")
    except Exception as e:
        logger.error(f"❌ Failed to sync product {product_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def sync_user(user_id, user_data):
    """Sync single user to PostgreSQL"""
    conn = get_pg_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO users (id, email, name, phone, fcm_token)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                phone = EXCLUDED.phone,
                fcm_token = EXCLUDED.fcm_token,
                updated_at = NOW()
        """, (
            user_id,
            user_data.get('email'),
            user_data.get('name'),
            user_data.get('phone'),
            user_data.get('fcmToken')
        ))
        conn.commit()
        logger.info(f"✅ Synced user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to sync user {user_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def initial_sync():
    """Initial sync of all data from Firebase to PostgreSQL"""
    logger.info("🔄 Starting initial sync...")
    
    # Sync orders
    logger.info("📦 Syncing orders...")
    orders = db.collection('orders').stream()
    count = 0
    for doc in orders:
        sync_order(doc.id, doc.to_dict())
        count += 1
    logger.info(f"✅ Synced {count} orders")
    
    # Sync products
    logger.info("🛍️ Syncing products...")
    products = db.collection('products').stream()
    count = 0
    for doc in products:
        sync_product(doc.id, doc.to_dict())
        count += 1
    logger.info(f"✅ Synced {count} products")
    
    # Sync users
    logger.info("👥 Syncing users...")
    users = db.collection('users').stream()
    count = 0
    for doc in users:
        sync_user(doc.id, doc.to_dict())
        count += 1
    logger.info(f"✅ Synced {count} users")
    
    logger.info("✅ Initial sync complete!")

def listen_to_orders():
    """Listen to Firestore orders and sync to PostgreSQL"""
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name in ['ADDED', 'MODIFIED']:
                doc = change.document
                sync_order(doc.id, doc.to_dict())
            elif change.type.name == 'REMOVED':
                conn = get_pg_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM orders WHERE id = %s", (change.document.id,))
                conn.commit()
                cur.close()
                conn.close()
                logger.info(f"🗑️ Deleted order: {change.document.id}")
    
    db.collection('orders').on_snapshot(on_snapshot)
    logger.info("👂 Listening to orders collection...")

def listen_to_products():
    """Listen to Firestore products and sync to PostgreSQL"""
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name in ['ADDED', 'MODIFIED']:
                doc = change.document
                sync_product(doc.id, doc.to_dict())
            elif change.type.name == 'REMOVED':
                conn = get_pg_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM products WHERE id = %s", (change.document.id,))
                conn.commit()
                cur.close()
                conn.close()
                logger.info(f"🗑️ Deleted product: {change.document.id}")
    
    db.collection('products').on_snapshot(on_snapshot)
    logger.info("👂 Listening to products collection...")

def refresh_materialized_view():
    """Refresh daily stats materialized view"""
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("SELECT refresh_daily_stats()")
        conn.commit()
        cur.close()
        conn.close()
        logger.info("📊 Refreshed daily stats")
    except Exception as e:
        logger.error(f"❌ Failed to refresh stats: {e}")

if __name__ == '__main__':
    logger.info("🚀 Starting Firebase to PostgreSQL sync service...")
    
    # Wait for PostgreSQL to be ready
    time.sleep(5)
    
    # Run initial sync
    initial_sync()
    
    # Start real-time listeners
    listen_to_orders()
    listen_to_products()
    
    logger.info("✅ Sync service running!")
    
    # Keep running and refresh stats every 5 minutes
    try:
        while True:
            time.sleep(300)
            refresh_materialized_view()
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
