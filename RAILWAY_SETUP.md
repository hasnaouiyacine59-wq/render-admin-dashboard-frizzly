# Railway PostgreSQL Setup - Complete Guide

## 🚀 Quick Start (5 Steps)

### Step 1: Create Railway Account
1. Go to https://railway.app
2. Sign up with GitHub (free $5 credit)
3. Verify email

### Step 2: Create PostgreSQL Database
```bash
# In Railway dashboard:
1. Click "New Project"
2. Select "Provision PostgreSQL"
3. Wait 30 seconds for deployment
4. Click database → "Variables" tab
5. Copy DATABASE_URL
```

**Example DATABASE_URL:**
```
postgresql://postgres:password@containers-us-west-123.railway.app:5432/railway
```

### Step 3: Initialize Database Schema
```bash
# Install PostgreSQL client locally
sudo apt install postgresql-client

# Connect to Railway database
psql "postgresql://postgres:password@containers-us-west-123.railway.app:5432/railway"

# Run schema (copy/paste from init.sql)
\i postgres-sync/init.sql

# Verify tables created
\dt

# Exit
\q
```

### Step 4: Deploy Sync Service to Railway
```bash
# In Railway dashboard:
1. Click "New" → "Empty Service"
2. Connect GitHub repo (or use CLI)
3. Set root directory: postgres-sync
4. Add environment variables:
   - POSTGRES_HOST: (from DATABASE_URL host)
   - POSTGRES_DB: railway
   - POSTGRES_USER: postgres
   - POSTGRES_PASSWORD: (from DATABASE_URL)
   - FIREBASE_CREDENTIALS: (paste serviceAccountKey.json content)
5. Deploy
```

### Step 5: Update Flask App to Use PostgreSQL
```bash
# Add to requirements.txt
psycopg2-binary==2.9.9

# Set environment variables in Render.com:
POSTGRES_HOST=containers-us-west-123.railway.app
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
USE_POSTGRES=true
```

---

## 📁 Files Created

```
postgres-sync/
├── docker-compose.yml      # Local testing
├── Dockerfile             # Railway deployment
├── init.sql               # Database schema
├── sync_service.py        # Real-time sync
└── requirements.txt       # Python dependencies

db_postgres.py             # PostgreSQL helper functions
```

---

## 🔧 Local Testing (Optional)

```bash
cd postgres-sync

# Start PostgreSQL + Sync Service
docker-compose up -d

# View logs
docker-compose logs -f sync-service

# Stop
docker-compose down
```

**Access local PostgreSQL:**
```bash
psql -h localhost -U admin -d frizzly
# Password: frizzly2026secure
```

---

## 🌐 Update Flask Routes

### Option 1: Automatic Switching (Recommended)

Add to `app.py`:
```python
import os

USE_POSTGRES = os.getenv('USE_POSTGRES', 'false').lower() == 'true'

if USE_POSTGRES:
    from db_postgres import (
        get_orders, get_order_by_id, update_order_status,
        get_products, get_users, get_dashboard_stats,
        get_revenue_by_month, get_orders_by_status
    )
else:
    # Keep existing Firebase functions
    pass
```

### Option 2: Manual Update

Replace Firebase queries with PostgreSQL:

**Before (Firebase):**
```python
orders = db.collection('orders').limit(50).stream()
```

**After (PostgreSQL):**
```python
from db_postgres import get_orders
orders = get_orders(limit=50)
```

---

## 💰 Railway Costs

### Free Tier (First Month)
- $5 credit included
- PostgreSQL: ~$0.67/month
- Sync Service: ~$0.50/month
- **Total: FREE for 4+ months**

### After Credits
- **$1.17/month** (both services)
- Pay-as-you-go (no minimum)

### Cost Breakdown
```
PostgreSQL:
- Storage: 1 GB = $0.25/month
- RAM: 512 MB = $0.42/month

Sync Service:
- RAM: 512 MB = $0.42/month
- CPU: Minimal = $0.08/month

TOTAL: ~$1.17/month
```

---

## 🔄 How It Works

```
Mobile App → Firebase (writes)
                ↓
         Sync Service (Railway)
                ↓
         PostgreSQL (Railway)
                ↓
    Admin Dashboard (Render) → FREE READS!
```

**Benefits:**
- ✅ Zero Firebase read costs
- ✅ Unlimited admin queries
- ✅ Complex analytics (JOINs, aggregations)
- ✅ Real-time sync (< 1 second delay)
- ✅ Materialized views for fast stats

---

## 📊 Performance

### Firebase (Before)
- Dashboard load: 160 reads
- Orders page: 50 reads
- Analytics: 500 reads
- **Cost: $0.03/month**

### PostgreSQL (After)
- Dashboard load: 0 Firebase reads
- Orders page: 0 Firebase reads
- Analytics: 0 Firebase reads
- **Cost: $1.17/month**

**Break-even: When Firebase > $1.17/month (39,000 reads/day)**

---

## 🚨 Troubleshooting

### Sync service not starting
```bash
# Check Railway logs
railway logs

# Common issues:
1. Wrong DATABASE_URL format
2. Missing FIREBASE_CREDENTIALS
3. Firestore permissions
```

### Connection refused
```bash
# Verify PostgreSQL is running
railway run psql $DATABASE_URL

# Check environment variables
railway variables
```

### Data not syncing
```bash
# Check sync service logs
railway logs --service sync-service

# Manually trigger sync
railway run python sync_service.py
```

---

## 🎯 Next Steps

1. ✅ Create Railway account
2. ✅ Deploy PostgreSQL
3. ✅ Run init.sql schema
4. ✅ Deploy sync service
5. ✅ Update Flask app
6. ✅ Test locally with docker-compose
7. ✅ Deploy to Render.com
8. ✅ Monitor Railway costs

---

## 📝 Environment Variables

### Railway Sync Service
```env
POSTGRES_HOST=containers-us-west-123.railway.app
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
FIREBASE_CREDENTIALS={"type":"service_account",...}
```

### Render.com Dashboard
```env
USE_POSTGRES=true
POSTGRES_HOST=containers-us-west-123.railway.app
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
```

---

## ✅ Verification Checklist

- [ ] Railway account created
- [ ] PostgreSQL deployed
- [ ] Schema initialized (5 tables)
- [ ] Sync service deployed
- [ ] Initial sync completed (check logs)
- [ ] Real-time sync working (test by creating order)
- [ ] Flask app updated
- [ ] Dashboard loads from PostgreSQL
- [ ] Zero Firebase reads confirmed

---

## 🔗 Useful Commands

```bash
# Railway CLI (optional)
npm install -g @railway/cli
railway login
railway link
railway logs
railway run psql $DATABASE_URL

# Check sync status
railway logs --service sync-service | grep "Synced"

# Monitor costs
railway dashboard
```

---

## 📈 Monitoring

### Railway Dashboard
- View real-time costs
- Monitor CPU/RAM usage
- Check deployment logs

### PostgreSQL Queries
```sql
-- Check sync status
SELECT COUNT(*) FROM orders;
SELECT COUNT(*) FROM products;
SELECT COUNT(*) FROM users;

-- View recent syncs
SELECT * FROM orders ORDER BY updated_at DESC LIMIT 10;

-- Check materialized view
SELECT * FROM daily_stats ORDER BY date DESC LIMIT 7;
```

---

## 🎉 Success Criteria

✅ Sync service shows "✅ Sync service running!"
✅ Orders/products/users synced to PostgreSQL
✅ Dashboard loads without Firebase reads
✅ Real-time updates work (< 1 second)
✅ Railway cost < $1.50/month

---

**Estimated Setup Time: 30-45 minutes**
**Monthly Cost: $1.17 (after $5 credit)**
**Firebase Savings: 100% read reduction**
