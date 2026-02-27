# Caching Implementation Guide

## What Was Added

Simple in-memory caching to reduce Firestore reads by caching frequently accessed data.

---

## Files Created/Modified

### 1. **cache.py** (NEW)
Simple in-memory cache with TTL (Time To Live) support.

**Features:**
- Automatic expiration after TTL
- Pattern-based invalidation
- Decorator for easy caching
- No external dependencies

### 2. **app.py** (MODIFIED)
- Imported cache module
- Added caching to `/api/dashboard-stats` (5 min TTL)

### 3. **blueprints/orders.py** (MODIFIED)
- Imported cache module
- Added caching to orders list (2 min TTL)
- Added cache invalidation on order status update

---

## How It Works

### Basic Usage

```python
from cache import cache

# Set cache (5 minute TTL)
cache.set('my_key', {'data': 'value'}, ttl_seconds=300)

# Get from cache
data = cache.get('my_key')  # Returns None if expired or not found

# Delete specific key
cache.delete('my_key')

# Delete all keys matching pattern
cache.invalidate_pattern('orders')  # Deletes all keys containing 'orders'

# Clear all cache
cache.clear()
```

### Using the Decorator

```python
from cache import cached

@cached(ttl_seconds=300, key_prefix='products')
def get_products():
    # This will be cached for 5 minutes
    return list(db.collection('products').stream())
```

---

## Current Caching Strategy

| Endpoint | Cache Key | TTL | Invalidation |
|----------|-----------|-----|--------------|
| `/api/dashboard-stats` | `dashboard_stats` | 5 min | On order update |
| `/orders?page=1&status=all` | `orders:page_1:status_all` | 2 min | On order update |

---

## Cache Invalidation

Cache is automatically invalidated when:
- Order status is updated
- TTL expires

**Manual invalidation:**
```python
# In any route that modifies orders
from cache import cache
cache.invalidate_pattern('orders')
cache.invalidate_pattern('dashboard_stats')
```

---

## Performance Impact

### Before Caching
```
Dashboard stats API: 1000 reads per request
Orders page: 50 reads per request
```

### After Caching (with 10 requests in 5 minutes)
```
Dashboard stats API: 1000 reads (first) + 0 reads (next 9) = 1000 reads total
Orders page: 50 reads (first) + 0 reads (next 9) = 50 reads total
```

**Savings: 90% reduction for repeated requests**

---

## Adding Cache to More Routes

### Example: Cache Products List

```python
# In blueprints/products.py
from cache import cache

@products_bp.route('/products')
@login_required
@admin_required
def products():
    page = request.args.get('page', 1, type=int)
    cache_key = f'products:page_{page}'
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return render_template('products.html', 
                             products=cached_data['products'],
                             pagination=cached_data['pagination'])
    
    # Fetch from Firestore
    # ... existing code ...
    
    # Cache for 5 minutes
    cache.set(cache_key, {
        'products': products_list,
        'pagination': pagination
    }, ttl_seconds=300)
    
    return render_template('products.html', 
                         products=products_list,
                         pagination=pagination)
```

### Example: Cache User Details

```python
@app.route('/users/<user_id>')
@login_required
def user_detail(user_id):
    cache_key = f'user:{user_id}'
    
    # Check cache
    cached_user = cache.get(cache_key)
    if cached_user:
        return render_template('user_detail.html', 
                             user=cached_user['user'],
                             orders=cached_user['orders'])
    
    # Fetch from Firestore
    # ... existing code ...
    
    # Cache for 10 minutes
    cache.set(cache_key, {
        'user': user,
        'orders': orders
    }, ttl_seconds=600)
    
    return render_template('user_detail.html', user=user, orders=orders)
```

---

## Cache Invalidation Patterns

### When to Invalidate

1. **Order Created/Updated/Deleted**
   ```python
   cache.invalidate_pattern('orders')
   cache.invalidate_pattern('dashboard_stats')
   ```

2. **Product Created/Updated/Deleted**
   ```python
   cache.invalidate_pattern('products')
   ```

3. **User Updated**
   ```python
   cache.delete(f'user:{user_id}')
   ```

### Example: Invalidate on Product Update

```python
@products_bp.route('/products/<product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    # Update product
    firestore_extension.db.collection('products').document(product_id).update(product_data)
    
    # Invalidate cache
    cache.invalidate_pattern('products')
    
    flash('Product updated', 'success')
    return redirect(url_for('products.products'))
```

---

## Advanced: Redis Caching (Optional)

For production with multiple servers, use Redis:

### 1. Install Redis
```bash
pip install redis
```

### 2. Create redis_cache.py
```python
import redis
import json
from datetime import timedelta

redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

class RedisCache:
    def get(self, key):
        value = redis_client.get(key)
        return json.loads(value) if value else None
    
    def set(self, key, value, ttl_seconds=300):
        redis_client.setex(key, ttl_seconds, json.dumps(value))
    
    def delete(self, key):
        redis_client.delete(key)
    
    def invalidate_pattern(self, pattern):
        keys = redis_client.keys(f'*{pattern}*')
        if keys:
            redis_client.delete(*keys)
    
    def clear(self):
        redis_client.flushdb()

cache = RedisCache()
```

### 3. Update imports
```python
# Change from:
from cache import cache

# To:
from redis_cache import cache
```

**Benefits:**
- Shared cache across multiple servers
- Persistent cache (survives restarts)
- Better performance for large datasets

---

## Monitoring Cache Performance

### Add Cache Hit/Miss Logging

```python
@app.route('/orders')
def orders():
    cache_key = f'orders:page_{page}'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        app.logger.info(f"Cache HIT: {cache_key}")
        return render_template(...)
    else:
        app.logger.info(f"Cache MISS: {cache_key}")
        # Fetch from Firestore
```

### Check Logs
```bash
tail -f app.log | grep "Cache"
```

---

## Cache Statistics (Optional)

Add to cache.py:

```python
class SimpleCache:
    def __init__(self):
        self._cache = {}
        self._hits = 0
        self._misses = 0
    
    def get(self, key):
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                self._hits += 1
                return value
            else:
                del self._cache[key]
        self._misses += 1
        return None
    
    def stats(self):
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f'{hit_rate:.2f}%',
            'cached_keys': len(self._cache)
        }
```

Add endpoint to view stats:

```python
@app.route('/admin/cache-stats')
@login_required
def cache_stats():
    return jsonify(cache.stats())
```

---

## Best Practices

### 1. Choose Appropriate TTL

| Data Type | Recommended TTL | Reason |
|-----------|----------------|--------|
| Dashboard stats | 5-10 minutes | Changes frequently |
| Orders list | 2-5 minutes | Real-time updates needed |
| Products list | 10-30 minutes | Changes less often |
| User profiles | 10-30 minutes | Rarely changes |
| Analytics | 1-24 hours | Historical data |

### 2. Always Invalidate on Write

```python
# Bad: Cache never invalidated
cache.set('products', products, ttl_seconds=3600)

# Good: Invalidate when data changes
@app.route('/products/add', methods=['POST'])
def add_product():
    # Add product
    cache.invalidate_pattern('products')  # Clear cache
```

### 3. Use Specific Cache Keys

```python
# Bad: Too generic
cache_key = 'orders'

# Good: Specific to request
cache_key = f'orders:page_{page}:status_{status}:user_{user_id}'
```

### 4. Handle Cache Failures Gracefully

```python
try:
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
except Exception as e:
    app.logger.error(f"Cache error: {e}")
    # Continue to fetch from Firestore
```

---

## Testing Cache

### 1. Test Cache Hit
```bash
# First request (cache miss)
curl http://localhost:5000/api/dashboard-stats
# Response: {"cached": false, ...}

# Second request within TTL (cache hit)
curl http://localhost:5000/api/dashboard-stats
# Response: {"cached": true, ...}
```

### 2. Test Cache Invalidation
```bash
# Update order status
curl -X POST http://localhost:5000/orders/123/update-status -d "status=DELIVERED"

# Check cache was cleared
curl http://localhost:5000/api/dashboard-stats
# Response: {"cached": false, ...}  # Cache was invalidated
```

---

## Summary

✅ **Implemented:**
- In-memory cache with TTL
- Dashboard stats caching (5 min)
- Orders list caching (2 min)
- Automatic cache invalidation

✅ **Benefits:**
- 90% reduction for repeated requests
- No external dependencies
- Easy to extend
- Automatic expiration

✅ **Next Steps:**
- Add caching to products page
- Add caching to users page
- Consider Redis for production
- Monitor cache hit rates

---

## Estimated Impact

### Scenario: 10 admins, each viewing dashboard 5 times in 5 minutes

**Without cache:**
- 10 admins × 5 views × 1000 reads = **50,000 reads**

**With cache (5 min TTL):**
- 10 admins × 1 cache miss × 1000 reads = **10,000 reads**

**Savings: 80% reduction (40,000 reads saved)**

### Monthly Savings (100 admin sessions/day)

**Without cache:**
- 100 sessions × 10,000 reads = 1,000,000 reads/day
- 30,000,000 reads/month = **$18/month**

**With cache:**
- 100 sessions × 2,000 reads = 200,000 reads/day
- 6,000,000 reads/month = **$3.60/month**

**Savings: $14.40/month (80% reduction)**
