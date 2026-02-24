# Admin Dashboard Notification Fix

## Problem
Admin dashboard not receiving new order notifications from users.

## Root Cause
The admin dashboard was NOT initializing Firebase Cloud Messaging (FCM) to receive push notifications.

## What Was Missing
1. **No FCM initialization** in the dashboard
2. **No FCM token registration** - admins weren't saving their FCM tokens to Firestore
3. **No foreground message handler** - notifications only worked in background

## Solution Implemented

### 1. Created FCM Initialization Script
**File**: `/static/fcm-init.js`
- Initializes Firebase app with project config
- Requests notification permission
- Gets FCM token
- Saves token to `/api/save-fcm-token` endpoint
- Handles foreground messages

### 2. Added Script to Base Template
**File**: `/templates/base.html`
- Added `<script type="module" src="/static/fcm-init.js"></script>`
- Registers service worker for background notifications

### 3. Existing Components (Already Working)
- ✅ Service worker: `/static/firebase-messaging-sw.js`
- ✅ API endpoint: `/api/save-fcm-token` (saves to `admins` collection)
- ✅ API sends notifications: When order created, sends FCM to all admins with tokens

## How It Works Now

### Order Creation Flow:
1. **User places order** → API receives order
2. **API creates order** with sequential ID (ORD1, ORD2, etc.)
3. **API queries** `admins` collection for all admins
4. **API sends FCM** to each admin's `fcmToken`
5. **Dashboard receives** notification via:
   - **Foreground**: `onMessage` handler shows browser notification
   - **Background**: Service worker shows system notification

### Admin Dashboard Flow:
1. **Page loads** → FCM script runs
2. **Requests permission** → User grants notification access
3. **Gets FCM token** → Unique token for this browser/device
4. **Saves to Firestore** → `admins/{userId}/fcmToken`
5. **Listens for messages** → Shows notifications when orders arrive

## Testing Steps

1. **Open admin dashboard** in browser
2. **Grant notification permission** when prompted
3. **Check browser console** for "✅ FCM token saved"
4. **Place test order** from mobile app or profile button
5. **Verify notification** appears in dashboard

## Verification

Check if admin has FCM token:
```javascript
// In browser console on dashboard
fetch('/api/save-fcm-token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token: 'test' })
}).then(r => r.json()).then(console.log)
```

Check Firestore:
- Collection: `admins`
- Document: `{admin_user_id}`
- Field: `fcmToken` should exist

## Files Modified
1. `/static/fcm-init.js` - NEW
2. `/templates/base.html` - Added FCM script import

## Files Already Present (No Changes Needed)
1. `/static/firebase-messaging-sw.js` - Service worker
2. `/app.py` - `/api/save-fcm-token` endpoint
3. API `/flask_app.py` - Sends notifications on order creation
