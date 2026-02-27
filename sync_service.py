"""
Incremental sync service for Firestore collections
Uses session cache (works on Render.com ephemeral filesystem)
"""
from firebase_admin import firestore
from extensions import firestore_extension
from session_cache import session_cache

class IncrementalSync:
    
    @staticmethod
    def sync_orders():
        """
        Sync orders incrementally using session cache
        """
        db = firestore_extension.db
        
        # Get cached orders and last sync time from session
        cached_orders = session_cache.get_collection('orders')
        last_sync_timestamp = session_cache.get_last_sync_time('orders')
        
        # First sync - load all orders (with limit)
        if last_sync_timestamp == 0:
            print(f"[SYNC] First sync - loading all orders (limited to 1000)")
            orders_query = db.collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1000)
            docs = list(orders_query.stream())
            
            orders_dict = {}
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                orders_dict[doc.id] = data
            
            # Find latest timestamp
            latest_timestamp = max([o.get('timestamp', 0) for o in orders_dict.values()]) if orders_dict else 0
            
            session_cache.save_collection('orders', orders_dict, latest_timestamp)
            print(f"[SYNC] Cached {len(orders_dict)} orders in session, latest timestamp: {latest_timestamp}")
            return list(orders_dict.values())
        
        # Incremental sync - only fetch new/updated orders
        print(f"[SYNC] Incremental sync from timestamp: {last_sync_timestamp}")
        new_orders_query = db.collection('orders').where('timestamp', '>', last_sync_timestamp).order_by('timestamp', direction=firestore.Query.DESCENDING)
        new_docs = list(new_orders_query.stream())
        
        if new_docs:
            new_orders = []
            for doc in new_docs:
                data = doc.to_dict()
                data['id'] = doc.id
                new_orders.append(data)
            
            print(f"[SYNC] Found {len(new_orders)} new/updated orders")
            updated_cache = session_cache.update_collection('orders', new_orders, [])
            return list(updated_cache.values())
        else:
            print(f"[SYNC] No new orders since last sync")
            return list(cached_orders.values())
    
    @staticmethod
    def sync_products():
        """Sync products incrementally using session cache"""
        db = firestore_extension.db
        
        cached_products = session_cache.get_collection('products')
        last_sync_timestamp = session_cache.get_last_sync_time('products')
        
        if last_sync_timestamp == 0:
            # First sync
            products_query = db.collection('products').limit(500)
            docs = list(products_query.stream())
            
            products_dict = {}
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                products_dict[doc.id] = data
            
            latest_timestamp = max([p.get('createdAt', {}).timestamp() * 1000 if hasattr(p.get('createdAt'), 'timestamp') else 0 for p in products_dict.values()]) if products_dict else 0
            
            session_cache.save_collection('products', products_dict, latest_timestamp)
            return list(products_dict.values())
        
        # Incremental sync
        new_products_query = db.collection('products').where('updatedAt', '>', last_sync_timestamp)
        new_docs = list(new_products_query.stream())
        
        if new_docs:
            new_products = []
            for doc in new_docs:
                data = doc.to_dict()
                data['id'] = doc.id
                new_products.append(data)
            
            updated_cache = session_cache.update_collection('products', new_products, [])
            return list(updated_cache.values())
        else:
            return list(cached_products.values())
    
    @staticmethod
    def force_refresh(collection):
        """Force full refresh of a collection"""
        session_cache.clear_collection(collection)
        if collection == 'orders':
            return IncrementalSync.sync_orders()
        elif collection == 'products':
            return IncrementalSync.sync_products()
        return []

# Global instance
sync_service = IncrementalSync()
