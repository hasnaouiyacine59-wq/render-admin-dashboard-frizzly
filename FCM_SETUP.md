# FCM Real-time Notifications Setup

## ✅ Files Created

1. `static/firebase-messaging-sw.js` - Service worker for background notifications
2. `templates/base.html` - Updated with FCM code
3. `app_api.py` - Added FCM token endpoint
4. `API_FRIZZLY/flask_app.py` - Added FCM token save endpoint
5. `firebase-functions/index.js` - Cloud Function to send notifications
6. `firebase-functions/package.json` - Dependencies

---

## 🔧 Setup Steps

### Step 1: Get Firebase Config

1. Go to: https://console.firebase.google.com/project/frizzly-9a65f/settings/general
2. Scroll to "Your apps" → Click Web app
3. Copy these values:
   - `apiKey` (you already have: AIzaSyCoTZoQRtiTATNY5JCWqTMCKDxoTcIok3E)
   - `messagingSenderId`
   - `appId`

### Step 2: Get VAPID Key

1. Go to: https://console.firebase.google.com/project/frizzly-9a65f/settings/cloudmessaging
2. Scroll to "Web Push certificates"
3. Click "Generate key pair"
4. Copy the key

### Step 3: Update Files

Replace in `static/firebase-messaging-sw.js`:
```javascript
messagingSenderId: "YOUR_MESSAGING_SENDER_ID",  // Line 7
appId: "YOUR_APP_ID"  // Line 8
```

Replace in `templates/base.html` (2 places):
```javascript
// Around line 540
messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
appId: "YOUR_APP_ID"

// Around line 560
vapidKey: 'YOUR_VAPID_KEY'
```

### Step 4: Deploy Cloud Function

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login
firebase login

# Initialize (select Frizzly project)
cd ~/AndroidStudioProjects/firebase-functions
firebase init functions

# Install dependencies
npm install

# Deploy
firebase deploy --only functions
```

### Step 5: Test

1. Restart dashboard:
   ```bash
   cd ~/AndroidStudioProjects/admin-dashboard-frizzly
   python3 app_api.py
   ```

2. Open dashboard: http://localhost:5001

3. Allow notifications when prompted

4. Check console (F12) - should see:
   - "Service Worker registered"
   - "FCM Token: ..."
   - "FCM token saved successfully"

5. Create a test order from Android app

6. You should get instant notification! 🔔

---

## 🧪 Testing

### Test FCM Token Registration

Open browser console (F12):
```javascript
// Should see:
Service Worker registered
Notification permission granted
FCM Token: eXaMpLe...
FCM token saved successfully
```

### Test Cloud Function

```bash
# Check function logs
firebase functions:log
```

### Test Notification

1. Create order from Android app
2. Within 1 second, you should see:
   - Browser notification popup
   - Toast notification in dashboard
   - Sound alert
   - Badge on notification bell

---

## 🔍 Troubleshooting

### No FCM token

**Problem:** Console shows "Error getting FCM token"

**Solution:**
1. Check VAPID key is correct
2. Check messagingSenderId and appId are correct
3. Make sure HTTPS (or localhost)

### Service Worker not registering

**Problem:** "Service Worker registration failed"

**Solution:**
1. Check `firebase-messaging-sw.js` is in `/static/` folder
2. Clear browser cache
3. Check browser console for errors

### No notifications

**Problem:** Order created but no notification

**Solution:**
1. Check Cloud Function is deployed: `firebase functions:list`
2. Check function logs: `firebase functions:log`
3. Check admin has FCM token in Firestore
4. Check browser notification permission is granted

---

## 📊 How It Works

```
Android App → Creates Order → Firestore
                                  ↓
                        Cloud Function Triggered
                                  ↓
                    Gets Admin FCM Tokens from Firestore
                                  ↓
                        Sends FCM Notification
                                  ↓
                    Admin Dashboard (< 1 second!)
```

---

## 💰 Cost

**Free tier includes:**
- 125K function invocations/month
- 10GB outbound networking/month
- FCM unlimited messages

**Your usage:**
- ~1 function call per order
- Well within free tier!

---

## 🎯 Next Steps

1. Get Firebase config values
2. Update the 3 files with your values
3. Deploy Cloud Function
4. Test with real order
5. Enjoy instant notifications! 🎉

---

## 📝 Notes

- FCM works even when dashboard is closed (browser must be open)
- Notifications show in system tray
- Clicking notification opens dashboard
- Fallback polling still works if FCM fails
- Multiple admins can receive notifications
