"""
Simple in-memory cache for admin dashboard
Reduces Firestore reads by caching frequently accessed data
"""
from datetime import datetime, timedelta
from functools import wraps
import json

class SimpleCache:
    def __init__(self):
        self._cache = {}
    
    def get(self, key):
        """Get cached value if not expired"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key, value, ttl_seconds=300):
        """Set cache value with TTL (default 5 minutes)"""
        expiry = datetime.now() + timedelta(seconds=ttl_seconds)
        self._cache[key] = (value, expiry)
    
    def delete(self, key):
        """Delete cached value"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
    
    def invalidate_pattern(self, pattern):
        """Delete all keys matching pattern"""
        keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self._cache[key]

# Global cache instance
cache = SimpleCache()

def cached(ttl_seconds=300, key_prefix=''):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{json.dumps(args)}:{json.dumps(kwargs)}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator
