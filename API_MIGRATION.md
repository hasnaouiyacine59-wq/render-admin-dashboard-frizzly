# FRIZZLY Admin Dashboard - API Version

## Architecture Change

**OLD (Direct Firebase Access):**
```
Dashboard → serviceAccountKey.json → Firebase
```

**NEW (API-Based):**
```
Dashboard → API Server → serviceAccountKey.json → Firebase
```

## Security Benefits

✅ **Centralized credentials** - serviceAccountKey.json only on API server
✅ **No admin SDK exposure** - Dashboard can't perform arbitrary Firebase operations
✅ **Controlled access** - API enforces business logic and permissions
✅ **Easier to audit** - All Firebase operations logged through API
✅ **Reduced attack surface** - Compromised dashboard = limited API access only

---

## Setup Instructions

### 1. Start the API Server

First, make sure your API server is running:

```bash
cd ~/AndroidStudioProjects/API_FRIZZLY
python flask_app.py
```

The API will run on `http://localhost:5000`

### 2. Configure Dashboard

Edit `config.py` in the dashboard folder:

```python
# For local development
API_BASE_URL = "http://localhost:5000"

# For production
# API_BASE_URL = "https://your-api-url.com"
```

### 3. Install Dashboard Dependencies

```bash
cd ~/AndroidStudioProjects/admin-dashboard-frizzly
pip install flask flask-login requests
```

### 4. Run the Dashboard

```bash
python app_api.py
```

The dashboard will run on `http://localhost:5001`

### 5. Login

Use your existing admin credentials:
- Email: `admin@frizzly.com`
- Password: `admin123` (or whatever you set)

---

## What Changed

### Files Modified

1. **API_FRIZZLY/flask_app.py**
   - Added `@require_admin` decorator
   - Added admin endpoints:
     - `POST /api/admin/login` - Admin authentication
     - `GET /api/admin/orders` - Get all orders
     - `GET /api/admin/orders/<id>` - Get single order
     - `PUT /api/admin/orders/<id>` - Update order
     - `DELETE /api/admin/orders/<id>` - Delete order
     - `GET /api/admin/users` - Get all users
     - `GET /api/admin/analytics` - Get analytics

### Files Created

1. **admin-dashboard-frizzly/app_api.py**
   - New dashboard app that uses API
   - No Firebase SDK dependency
   - No serviceAccountKey.json needed

2. **admin-dashboard-frizzly/config.py**
   - Configuration for API URL
   - Easy to switch between dev/production

3. **admin-dashboard-frizzly/api_client.py**
   - Reusable API client (optional, not used in app_api.py)

### Files Unchanged

- All templates (HTML files) work as-is
- Original `app.py` still exists (backup)

---

## Deployment

### Deploy API Server

Deploy your API to any platform:
- Fly.io (free Docker hosting)
- Railway.app ($5/month credit)
- Render.com
- PythonAnywhere

### Deploy Dashboard

Deploy dashboard to:
- PythonAnywhere (free)
- Vercel (free)
- Netlify (free)

Update `config.py` with your API URL:
```python
API_BASE_URL = "https://your-api.fly.dev"
```

---

## Testing

### Test API Endpoints

```bash
# Health check
curl http://localhost:5000/api/health

# Login (get token)
curl -X POST http://localhost:5000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@frizzly.com","password":"admin123"}'

# Get orders (use token from login)
curl http://localhost:5000/api/admin/orders \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Test Dashboard

1. Open `http://localhost:5001`
2. Login with admin credentials
3. Navigate through orders, products, users

---

## Troubleshooting

### Dashboard can't connect to API

**Error:** "API request failed"

**Solution:**
1. Check API is running: `curl http://localhost:5000/api/health`
2. Check `config.py` has correct API_BASE_URL
3. Check firewall/network settings

### Login fails

**Error:** "Invalid credentials"

**Solution:**
1. Verify admin exists in Firebase `admins` collection
2. Check password hash is correct
3. Check API logs for errors

### Orders/Products not loading

**Error:** Empty lists

**Solution:**
1. Check API has access to serviceAccountKey.json
2. Check Firebase collections have data
3. Check API logs for errors

---

## Migration Checklist

- [ ] API server running with admin endpoints
- [ ] Dashboard configured with API_BASE_URL
- [ ] Admin can login successfully
- [ ] Orders page loads
- [ ] Products page loads
- [ ] Users page loads
- [ ] Analytics page loads
- [ ] Order status updates work
- [ ] Product CRUD operations work
- [ ] Remove serviceAccountKey.json from dashboard folder

---

## Security Notes

⚠️ **Important:**

1. **Never commit serviceAccountKey.json** - Keep it only on API server
2. **Use HTTPS in production** - Protect tokens in transit
3. **Rotate tokens regularly** - Implement token refresh
4. **Rate limit API** - Prevent abuse
5. **Monitor API logs** - Detect suspicious activity

---

## Rollback

If you need to rollback to direct Firebase access:

```bash
# Use original app.py
python app.py
```

The original `app.py` is unchanged and still works.

---

## Support

For issues:
1. Check API logs: `tail -f ~/AndroidStudioProjects/API_FRIZZLY/server.log`
2. Check dashboard logs: `tail -f ~/AndroidStudioProjects/admin-dashboard-frizzly/app.log`
3. Test API endpoints with curl
