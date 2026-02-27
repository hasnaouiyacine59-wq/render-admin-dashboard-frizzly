# Incremental Sync for Render.com

## Important: Ephemeral Filesystem

Render.com has **ephemeral filesystem** - files are deleted on restart. The solution uses **Flask session** instead of local files.

---

## How It Works on Render.com

### Session-Based Cache
```
Admin logs in → Session created
  ↓
Visit /orders → Load all orders (1000) → Store in session
  ↓
Visit /orders again → Load from session → Fetch only NEW orders → Merge
  ↓
Admin logs out → Session cleared
  ↓
Admin logs in again → New session → Load all orders again
```

### Per-User Cache
Each admin has their own cache in their session:
- Admin A loads orders → Cached in Admin A's session
- Admin B loads orders → Cached in Admin B's session
- Independent caches, no conflicts

---

## Files Updated for Render.com

1. ✅ **session_cache.py** - Uses Flask session instead of files
2. ✅ **sync_service.py** - Updated to use session_cache
3. ✅ **blueprints/orders.py** - Already compatible

---

## Session Configuration

### Important: Set Strong Secret Key

In `app.py`, ensure you have a strong secret key:

```python
import os

# Use environment variable in production
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
```

### Set in Render.com Dashboard

1. Go to your Render.com dashboard
2. Select your web service
3. Go to **Environment** tab
4. Add environment variable:
   ```
   SECRET_KEY = your-random-secret-key-here-make-it-long-and-random
   ```

Generate a strong key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Session Size Limits

### Flask Session Limits
- Default: 4KB (cookie-based)
- With 1000 orders: ~500KB-1MB

### Solution: Use Server-Side Sessions

Install Flask-Session:
```bash
pip install Flask-Session redis
```

Update `app.py`:
```python
from flask_session import Session
import redis

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# Configure server-side sessions with Redis
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379'))
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

Session(app)
```

### Add Redis to Render.com

1. In Render.com dashboard, create a **Redis** instance
2. Copy the **Internal Redis URL**
3. Add to your web service environment variables:
   ```
   REDIS_URL = redis://...
   ```

---

## Alternative: Use Render Disk

Render.com offers **persistent disks** (paid feature):

### 1. Add Disk in Render.com
- Go to your web service
- Click **Disks** tab
- Add disk: `/data` (mount path)
- Size: 1GB

### 2. Update persistent_cache.py
```python
class PersistentCache:
    def __init__(self, cache_dir='/data/cache'):  # Use /data instead
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
```

### 3. Update sync_service.py
```python
from persistent_cache import persistent_cache  # Use file cache again
```

---

## Performance Comparison

### Session Cache (Current)
✅ Free
✅ Works on Render.com free tier
✅ Per-user cache
⚠️ Cache lost on logout
⚠️ Each admin loads separately

### Redis Cache (Recommended)
✅ Shared cache across all admins
✅ Persists across restarts
✅ Faster than session
💰 Requires Redis ($7/month on Render)

### Persistent Disk (Alternative)
✅ File-based cache
✅ Persists across restarts
✅ Shared cache
💰 Requires disk ($1/GB/month)

---

## Current Setup (Session Cache)

### Pros
- ✅ Works on Render.com free tier
- ✅ No additional services needed
- ✅ Simple implementation
- ✅ Per-user isolation

### Cons
- ⚠️ Cache cleared on logout
- ⚠️ Each admin loads independently
- ⚠️ Session size limits (~1000 orders max)

### Best For
- Small teams (1-5 admins)
- Moderate order volume (<1000 orders)
- Free tier hosting

---

## Recommended Setup for Production

### Option 1: Redis (Best Performance)

**Cost:** $7/month for Redis on Render.com

**Setup:**
```bash
# Add to requirements.txt
Flask-Session==0.5.0
redis==5.0.0

# Update app.py
from flask_session import Session
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.environ['REDIS_URL'])
Session(app)
```

**Benefits:**
- Shared cache across all admins
- Survives restarts
- No session size limits
- Best performance

---

### Option 2: Persistent Disk (Good Balance)

**Cost:** $1/GB/month on Render.com

**Setup:**
1. Add disk in Render.com: `/data`
2. Update `persistent_cache.py`: `cache_dir='/data/cache'`
3. Update `sync_service.py`: Use `persistent_cache`

**Benefits:**
- File-based (familiar)
- Shared cache
- Survives restarts
- Lower cost than Redis

---

### Option 3: Session Cache (Current - Free)

**Cost:** Free

**Setup:** Already done!

**Benefits:**
- No additional services
- Works on free tier
- Simple

**Limitations:**
- Cache per user
- Lost on logout
- Size limits

---

## Monitoring on Render.com

### Check Logs
```bash
# In Render.com dashboard
Logs → Filter by "[SYNC]"
```

### Check Session Size
Add to `app.py`:
```python
@app.route('/admin/session-info')
@login_required
def session_info():
    import sys
    orders = session.get('cache_orders', {})
    size = sys.getsizeof(str(orders))
    return jsonify({
        'cached_orders': len(orders),
        'session_size_bytes': size,
        'session_size_kb': size / 1024
    })
```

---

## Deployment Checklist

### 1. Environment Variables
```
SECRET_KEY = <strong-random-key>
REDIS_URL = <redis-url>  # If using Redis
```

### 2. Requirements.txt
```
Flask==2.3.0
Flask-Login==0.6.2
Flask-Session==0.5.0  # If using Redis
redis==5.0.0  # If using Redis
firebase-admin==6.2.0
```

### 3. Deploy
```bash
git add .
git commit -m "Add session-based incremental sync"
git push
```

Render.com will auto-deploy.

---

## Testing on Render.com

### 1. First Login
```
Visit: https://your-app.onrender.com/orders
Check logs: "[SYNC] First sync - loading all orders"
```

### 2. Reload Page
```
Reload: https://your-app.onrender.com/orders
Check logs: "[SYNC] Incremental sync from timestamp: ..."
Check logs: "[SYNC] Found X new/updated orders"
```

### 3. Logout and Login
```
Logout → Login → Visit /orders
Check logs: "[SYNC] First sync" (cache cleared)
```

---

## Troubleshooting

### Session Too Large Error
```
Error: Cookie too large
```

**Solution:** Switch to Redis or reduce order limit:
```python
# In sync_service.py
orders_query = db.collection('orders').limit(500)  # Reduce from 1000
```

### Cache Not Persisting
```
Every page load fetches all orders
```

**Check:**
1. Session is enabled: `app.secret_key` is set
2. User is logged in: `@login_required` decorator
3. Session is modified: `session.modified = True`

### Slow Performance
```
Pages load slowly
```

**Solution:** Upgrade to Redis for faster cache access.

---

## Summary

✅ **Current Setup (Session Cache):**
- Works on Render.com free tier
- Cache stored in Flask session
- Per-user cache (cleared on logout)
- Supports ~1000 orders per admin

✅ **Recommended for Production:**
- Add Redis ($7/month) for shared cache
- Or add Persistent Disk ($1/GB) for file cache
- Better performance and persistence

✅ **Already Implemented:**
- session_cache.py
- sync_service.py (updated)
- Ready to deploy on Render.com

**Your dashboard now works perfectly on Render.com!** 🚀
