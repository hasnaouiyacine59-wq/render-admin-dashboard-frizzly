# Railway PostgreSQL - Quick Start

## 🚀 5-Minute Setup

### 1. Create Railway Database (2 min)
```
1. Go to https://railway.app
2. Sign up with GitHub
3. New Project → Provision PostgreSQL
4. Copy DATABASE_URL from Variables tab
```

### 2. Initialize Schema (1 min)
```bash
# Install psql
sudo apt install postgresql-client

# Connect and run schema
psql "YOUR_DATABASE_URL" < postgres-sync/init.sql
```

### 3. Deploy Sync Service (2 min)
```
1. Railway → New → Empty Service
2. Connect GitHub repo
3. Root directory: postgres-sync
4. Add env vars (from DATABASE_URL):
   - POSTGRES_HOST
   - POSTGRES_DB
   - POSTGRES_USER
   - POSTGRES_PASSWORD
   - FIREBASE_CREDENTIALS (paste JSON)
5. Deploy
```

### 4. Update Render Dashboard
```
Add environment variables:
- USE_POSTGRES=true
- POSTGRES_HOST=your_host
- POSTGRES_DB=railway
- POSTGRES_USER=postgres
- POSTGRES_PASSWORD=your_password
```

### 5. Verify
```bash
# Check sync logs in Railway
# Should see: "✅ Synced X orders"
```

---

## 💰 Cost: $1.17/month (FREE for 4+ months with credits)

---

## 📁 Files Ready

All files created in:
- `postgres-sync/` - Sync service
- `db_postgres.py` - Flask helpers
- `RAILWAY_SETUP.md` - Full guide

---

## 🎯 Next: Update Flask Routes

See `RAILWAY_SETUP.md` for detailed instructions.
