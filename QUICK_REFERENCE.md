# FRIZZLY Dashboard - Quick Reference

## 🚀 Start Services

### API Server (Terminal 1)
```bash
cd ~/AndroidStudioProjects/API_FRIZZLY
python flask_app.py
```
Runs on: `http://localhost:5000`

### Dashboard (Terminal 2)
```bash
cd ~/AndroidStudioProjects/admin-dashboard-frizzly
python app_api.py
```
Runs on: `http://localhost:5001`

---

## 🔐 Login

**URL:** `http://localhost:5001`

**Credentials:**
- Email: `admin@frizzly.com`
- Password: `admin123`

---

## 🧪 Test API

```bash
cd ~/AndroidStudioProjects/admin-dashboard-frizzly
./test_api_migration.sh
```

---

## 📁 File Structure

```
API_FRIZZLY/
├── flask_app.py          ← API server (has serviceAccountKey.json)
├── serviceAccountKey.json ← Firebase credentials (KEEP HERE)
└── requirements.txt

admin-dashboard-frizzly/
├── app_api.py            ← NEW dashboard (uses API)
├── app.py                ← OLD dashboard (backup)
├── config.py             ← Configuration
├── api_client.py         ← API helper
├── requirements_api.txt  ← Minimal dependencies
├── templates/            ← HTML files (unchanged)
├── static/               ← CSS/JS (unchanged)
└── serviceAccountKey.json ← DELETE after migration ✗
```

---

## 🔄 Architecture

**Before:**
```
Dashboard → serviceAccountKey.json → Firebase
```

**After:**
```
Dashboard → API → serviceAccountKey.json → Firebase
```

---

## ✅ Migration Checklist

- [ ] API server running
- [ ] Dashboard running
- [ ] Can login
- [ ] Orders page works
- [ ] Products page works
- [ ] Users page works
- [ ] Analytics page works
- [ ] Delete serviceAccountKey.json from dashboard folder

---

## 🐛 Troubleshooting

### Dashboard can't connect to API
```bash
# Check API is running
curl http://localhost:5000/api/health

# Check config.py
cat config.py | grep API_BASE_URL
```

### Login fails
```bash
# Test login directly
curl -X POST http://localhost:5000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@frizzly.com","password":"admin123"}'
```

### Check logs
```bash
# API logs
tail -f ~/AndroidStudioProjects/API_FRIZZLY/server.log

# Dashboard logs
tail -f ~/AndroidStudioProjects/admin-dashboard-frizzly/app.log
```

---

## 📚 Documentation

- `API_MIGRATION.md` - Complete migration guide
- `MIGRATION_SUMMARY.md` - Summary of changes
- `README.md` - Original dashboard docs

---

## 🔒 Security

✅ serviceAccountKey.json only on API server
✅ Dashboard has limited API access
✅ All operations logged through API
✅ Easier to monitor and audit

---

## 🌐 Production Deployment

### 1. Deploy API
```bash
# Example: Fly.io
cd ~/AndroidStudioProjects/API_FRIZZLY
fly launch
fly deploy
```

### 2. Update Dashboard Config
```python
# config.py
API_BASE_URL = "https://your-api.fly.dev"
```

### 3. Deploy Dashboard
```bash
# Example: PythonAnywhere
# Upload: app_api.py, config.py, templates/, static/
# Install: pip install -r requirements_api.txt
```

### 4. Clean Up
```bash
# Remove serviceAccountKey.json from dashboard
rm ~/AndroidStudioProjects/admin-dashboard-frizzly/serviceAccountKey.json
```

---

## 🔙 Rollback

If needed, use original dashboard:
```bash
cd ~/AndroidStudioProjects/admin-dashboard-frizzly
python app.py
```

---

## 📞 Support

Check logs, test endpoints, read documentation.
