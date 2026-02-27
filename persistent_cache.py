"""
Persistent local cache with incremental sync
Stores data locally and only fetches new/updated records from Firestore
"""
import json
import os
from datetime import datetime
from pathlib import Path

class PersistentCache:
    def __init__(self, cache_dir='cache_data'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
    def _get_cache_file(self, collection):
        return self.cache_dir / f'{collection}.json'
    
    def _get_metadata_file(self, collection):
        return self.cache_dir / f'{collection}_meta.json'
    
    def get_collection(self, collection):
        """Get cached collection data"""
        cache_file = self._get_cache_file(collection)
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
        return {}
    
    def get_last_sync_time(self, collection):
        """Get last sync timestamp for collection"""
        meta_file = self._get_metadata_file(collection)
        if meta_file.exists():
            with open(meta_file, 'r') as f:
                meta = json.load(f)
                return meta.get('last_sync_timestamp', 0)
        return 0
    
    def save_collection(self, collection, data, last_timestamp=None):
        """Save collection data to cache"""
        cache_file = self._get_cache_file(collection)
        with open(cache_file, 'w') as f:
            json.dump(data, f)
        
        # Save metadata
        if last_timestamp:
            meta_file = self._get_metadata_file(collection)
            with open(meta_file, 'w') as f:
                json.dump({
                    'last_sync_timestamp': last_timestamp,
                    'last_sync_date': datetime.now().isoformat()
                }, f)
    
    def update_collection(self, collection, new_items, updated_items):
        """Update cache with new/updated items"""
        data = self.get_collection(collection)
        
        # Add new items
        for item in new_items:
            data[item['id']] = item
        
        # Update existing items
        for item in updated_items:
            data[item['id']] = item
        
        # Find latest timestamp
        latest_timestamp = 0
        for item in data.values():
            ts = item.get('timestamp', 0)
            if ts > latest_timestamp:
                latest_timestamp = ts
        
        self.save_collection(collection, data, latest_timestamp)
        return data
    
    def clear_collection(self, collection):
        """Clear cached collection"""
        cache_file = self._get_cache_file(collection)
        meta_file = self._get_metadata_file(collection)
        
        if cache_file.exists():
            cache_file.unlink()
        if meta_file.exists():
            meta_file.unlink()

# Global instance
persistent_cache = PersistentCache()
