# Background Notification Fix

## Problem
System notifications were NOT showing when the Android app was running in the background.

## Root Cause
The admin dashboard was sending FCM messages with the `notification` field:

```python
message = messaging.Message(
    notification=messaging.Notification(title=title, body=body),
    token=fcm_token
)
```

**FCM Behavior:**
- **Foreground**: `onMessageReceived()` is called → Custom notification with sound ✅
- **Background**: FCM auto-displays notification → `onMessageReceived()` NOT called → No custom sound/vibration ❌

## Solution
Changed to **data-only messages** (no `notification` field):

```python
message = messaging.Message(
    data={
        'title': title,
        'body': body,
        'type': 'order',
        'timestamp': str(int(time.time() * 1000))
    },
    token=fcm_token
)
```

**New Behavior:**
- **Foreground**: `onMessageReceived()` called → Custom notification ✅
- **Background**: `onMessageReceived()` called → Custom notification ✅

## Changes Made

### 1. Admin Dashboard (`app.py`)
- Added `import time`
- Modified `send_notification()` function (line 800)
- Modified `send_test_notification()` function (line 706)
- Changed from `notification=` to `data=` payload

### 2. Android App (Already Compatible)
`FrizzlyMessagingService.kt` already handles both message types:

```kotlin
override fun onMessageReceived(message: RemoteMessage) {
    if (message.notification != null) {
        // Notification message (foreground only)
        title = message.notification!!.title ?: "FRIZZLY"
        body = message.notification!!.body ?: ""
    } else if (message.data.isNotEmpty()) {
        // Data-only message (works in background) ✅
        title = message.data["title"] ?: "FRIZZLY Order Update"
        body = message.data["body"] ?: "Order status updated"
    }
    
    showNotification(title, body, type, orderId)
}
```

## Testing

### Before Fix
1. Put app in background (press home button)
2. Update order status in admin dashboard
3. ❌ No notification sound/vibration
4. ❌ Generic system notification

### After Fix
1. Put app in background
2. Update order status in admin dashboard
3. ✅ Custom notification sound plays
4. ✅ Vibration pattern triggers
5. ✅ Custom notification with proper styling

## Deployment
- **Commit**: `719b23d`
- **Message**: "Fix background notifications: use data-only FCM messages"
- **Status**: 🟢 Deployed to Render

## References
- [FCM Message Types](https://firebase.google.com/docs/cloud-messaging/concept-options#notifications_and_data_messages)
- `FrizzlyMessagingService.kt` - Lines 30-70
- `app.py` - Lines 800-815, 706-730
