# FIRESTORE OPTIMIZATION GUIDE

## Current Problems

### 1. Context Processor Waste (CRITICAL)
- **Issue**: Runs on every page load, reads all orders
- **Cost**: 1000+ reads per page view
- **Location**: `app.py` line 103-115

### 2. No Pagination
- **Issue**: All pages load entire collections
- **Affected**: Orders, products, users, analytics, revenue

### 3. Inefficient Counting
- **Issue**: Reading documents just to count them
- **Location**: `dashboard.py` lines 33-36

### 4. No Caching Strategy
- **Issue**: Same data fetched repeatedly
- **Affected**: All routes

---

## Solutions

### Solution 1: Remove/Fix Context Processor

**Option A: Remove it entirely** (Recommended)
The stats are already calculated in dashboard route. Remove lines 103-115 from `app.py`.

**Option B: Cache aggressively**
```python
@app.context_processor
def inject_stats():
    if current_user.is_authenticated:
        cache_key = 'global_stats'
        if cache_key in session:
            cache_time = session.get('global_stats_time', 0)
            if time.time() - cache_time < 600:  # 10 minutes
                return {'stats': session[cache_key]}
        
        # Only count, don't fetch all data
        orders_ref = firestore_extension.db.collection('orders')
        stats = {
            'total_orders': orders_ref.count().get()[0][0].value,  # Aggregation query
            'pending_orders': orders_ref.where('status', '==', 'PENDING').count().get()[0][0].value,
            'in_progress_orders': orders_ref.where('status', 'in', ['CONFIRMED', 'ON_WAY']).count().get()[0][0].value,
            'delivered_orders': orders_ref.where('status', '==', 'DELIVERED').count().get()[0][0].value
        }
        
        session[cache_key] = stats
        session['global_stats_time'] = time.time()
        return {'stats': stats}
    return {'stats': {'total_orders': 0, 'pending_orders': 0, 'in_progress_orders': 0, 'delivered_orders': 0}}
```

### Solution 2: Use Firestore Aggregation Queries

**For counting** (requires firebase-admin >= 6.0.0):
```python
# Instead of:
total = sum(1 for _ in db.collection('orders').stream())  # ❌ Reads all docs

# Use:
from firebase_admin.firestore import AggregationQuery
total = db.collection('orders').count().get()[0][0].value  # ✅ 1 read
```

### Solution 3: Implement Pagination

**For orders list**:
```python
@orders_bp.route('/orders')
@login_required
def orders():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    status_filter = request.args.get('status', 'all')
    
    orders_ref = firestore_extension.db.collection('orders')
    
    # Apply filter
    if status_filter != 'all':
        orders_ref = orders_ref.where('status', '==', status_filter)
    
    # Order by timestamp
    orders_ref = orders_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
    
    # Pagination using offset (simple but not ideal for large datasets)
    orders_query = orders_ref.limit(per_page).offset((page - 1) * per_page)
    
    orders_list = [{'id': doc.id, **doc.to_dict()} for doc in orders_query.stream()]
    
    # Get total count (cache this!)
    total_count = orders_ref.count().get()[0][0].value
    total_pages = (total_count + per_page - 1) // per_page
    
    return render_template('orders.html', 
                         orders=orders_list, 
                         page=page, 
                         total_pages=total_pages,
                         status_filter=status_filter)
```

### Solution 4: Cursor-Based Pagination (Better for Large Datasets)

```python
@orders_bp.route('/orders')
@login_required
def orders():
    status_filter = request.args.get('status', 'all')
    last_doc_id = request.args.get('last_doc')
    per_page = 50
    
    orders_ref = firestore_extension.db.collection('orders')
    
    if status_filter != 'all':
        orders_ref = orders_ref.where('status', '==', status_filter)
    
    orders_ref = orders_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
    
    # Start after last document if provided
    if last_doc_id:
        last_doc = firestore_extension.db.collection('orders').document(last_doc_id).get()
        orders_ref = orders_ref.start_after(last_doc)
    
    orders_query = orders_ref.limit(per_page)
    docs = list(orders_query.stream())
    orders_list = [{'id': doc.id, **doc.to_dict()} for doc in docs]
    
    # Next page cursor
    next_cursor = docs[-1].id if len(docs) == per_page else None
    
    return render_template('orders.html', 
                         orders=orders_list,
                         next_cursor=next_cursor,
                         status_filter=status_filter)
```

### Solution 5: Cache Dashboard Stats

Already partially implemented in `dashboard.py`, but improve it:

```python
from functools import lru_cache
from datetime import datetime, timedelta

# In-memory cache with TTL
_stats_cache = {'data': None, 'timestamp': None}

def get_dashboard_stats():
    """Get cached stats or fetch new ones"""
    now = datetime.now()
    
    # Check cache (5 minute TTL)
    if _stats_cache['data'] and _stats_cache['timestamp']:
        age = (now - _stats_cache['timestamp']).total_seconds()
        if age < 300:  # 5 minutes
            return _stats_cache['data']
    
    # Fetch fresh data using aggregation
    db = firestore_extension.db
    
    stats = {
        'total_orders': db.collection('orders').count().get()[0][0].value,
        'pending_orders': db.collection('orders').where('status', '==', 'PENDING').count().get()[0][0].value,
        'total_products': db.collection('products').count().get()[0][0].value,
        'total_users': db.collection('users').count().get()[0][0].value,
        'low_stock_products': db.collection('products').where('stock', '<', 10).count().get()[0][0].value,
    }
    
    # Calculate revenue (still needs to read docs, but limit it)
    delivered_orders = db.collection('orders').where('status', '==', 'DELIVERED').limit(500).stream()
    stats['total_revenue'] = sum(doc.to_dict().get('totalAmount', 0) for doc in delivered_orders)
    
    # Update cache
    _stats_cache['data'] = stats
    _stats_cache['timestamp'] = now
    
    return stats
```

### Solution 6: Optimize Revenue Calculations

**Use Firestore counters** (best approach):

Create a `stats` document that updates on each order:
```python
# When order status changes to DELIVERED
def update_order_status(order_id, new_status):
    order_ref = db.collection('orders').document(order_id)
    order = order_ref.get().to_dict()
    
    order_ref.update({'status': new_status})
    
    # Update global stats
    if new_status == 'DELIVERED':
        stats_ref = db.collection('stats').document('global')
        stats_ref.update({
            'total_revenue': firestore.Increment(order['totalAmount']),
            'delivered_count': firestore.Increment(1)
        })
```

Then revenue page just reads one document:
```python
@app.route('/revenue')
@login_required
def revenue():
    stats = db.collection('stats').document('global').get().to_dict()
    return render_template('revenue.html', 
                         total_revenue=stats.get('total_revenue', 0),
                         delivered_count=stats.get('delivered_count', 0))
```

### Solution 7: Implement Redis/Memcached

For production, use external cache:
```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_cached_orders(status='all', ttl=300):
    cache_key = f'orders:{status}'
    
    # Try cache first
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Fetch from Firestore
    orders_ref = db.collection('orders')
    if status != 'all':
        orders_ref = orders_ref.where('status', '==', status)
    
    orders = [{'id': doc.id, **doc.to_dict()} for doc in orders_ref.limit(100).stream()]
    
    # Cache it
    redis_client.setex(cache_key, ttl, json.dumps(orders))
    
    return orders
```

---

## Implementation Priority

### Phase 1: Quick Wins (Do Now)
1. ✅ Remove or cache context processor
2. ✅ Add pagination to orders (50 per page)
3. ✅ Add pagination to products (50 per page)
4. ✅ Add pagination to users (50 per page)

### Phase 2: Aggregation (This Week)
1. ✅ Use count() for dashboard stats
2. ✅ Implement in-memory cache for dashboard
3. ✅ Add limits to all queries (max 500)

### Phase 3: Architecture (Next Sprint)
1. ✅ Implement Firestore counters for revenue
2. ✅ Add Redis for caching
3. ✅ Implement cursor-based pagination
4. ✅ Add background jobs for analytics

---

## Monitoring

Track Firestore usage:
```bash
# Check Firebase Console > Firestore > Usage tab
# Monitor:
# - Document reads per day
# - Document writes per day
# - Storage size
```

Set up alerts:
- Alert if reads > 100k/day
- Alert if costs > $5/month

---

## Expected Improvements

### Before Optimization
- Dashboard load: ~2,000 reads
- Orders page: ~1,500 reads
- Revenue page: ~2,000 reads
- **Total per session: ~10,000 reads**

### After Phase 1
- Dashboard load: ~60 reads (50 orders + 10 recent)
- Orders page: ~50 reads (paginated)
- Revenue page: ~500 reads (limited)
- **Total per session: ~1,000 reads (90% reduction)**

### After Phase 3
- Dashboard load: ~10 reads (cached stats + recent orders)
- Orders page: ~50 reads (paginated)
- Revenue page: ~1 read (counter document)
- **Total per session: ~100 reads (99% reduction)**

---

## Code Quality Notes

1. **Always use limits**: Never call `.stream()` without `.limit()`
2. **Cache aggressively**: Stats don't need real-time accuracy
3. **Use aggregation**: Count documents without reading them
4. **Paginate everything**: Never load full collections
5. **Monitor usage**: Set up Firebase alerts
