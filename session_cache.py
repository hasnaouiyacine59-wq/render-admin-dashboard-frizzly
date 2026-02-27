"""
Session-based persistent cache for Render.com (ephemeral filesystem)
Stores data in Flask session instead of local files
"""
from flask import session
from datetime import datetime

class SessionCache:
    """Cache that uses Flask session (works on Render.com)"""
    
    @staticmethod
    def get_collection(collection):
        """Get cached collection from session"""
        key = f'cache_{collection}'
        return session.get(key, {})
    
    @staticmethod
    def get_last_sync_time(collection):
        """Get last sync timestamp from session"""
        key = f'cache_{collection}_timestamp'
        return session.get(key, 0)
    
    @staticmethod
    def save_collection(collection, data, last_timestamp=None):
        """Save collection to session"""
        key = f'cache_{collection}'
        session[key] = data
        
        if last_timestamp:
            timestamp_key = f'cache_{collection}_timestamp'
            session[timestamp_key] = last_timestamp
            session.modified = True
    
    @staticmethod
    def update_collection(collection, new_items, updated_items):
        """Update cache with new/updated items"""
        data = SessionCache.get_collection(collection)
        
        # Add/update items
        for item in new_items + updated_items:
            data[item['id']] = item
        
        # Find latest timestamp
        latest_timestamp = 0
        for item in data.values():
            ts = item.get('timestamp', 0)
            if ts > latest_timestamp:
                latest_timestamp = ts
        
        SessionCache.save_collection(collection, data, latest_timestamp)
        return data
    
    @staticmethod
    def clear_collection(collection):
        """Clear cached collection"""
        key = f'cache_{collection}'
        timestamp_key = f'cache_{collection}_timestamp'
        session.pop(key, None)
        session.pop(timestamp_key, None)
        session.modified = True

# Global instance
session_cache = SessionCache()
