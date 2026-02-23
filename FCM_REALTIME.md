# Real-time Notifications with FCM

## Option 1: FCM Web Push (Best for Dashboard)

### Step 1: Get Firebase Web Config

In Firebase Console:
1. Project Settings → General
2. Scroll to "Your apps" → Web app
3. Copy the config (including `messagingSenderId`)

### Step 2: Add to Dashboard

Create `firebase-messaging-sw.js` in `static/`:
```javascript
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCoTZoQRtiTATNY5JCWqTMCKDxoTcIok3E",
  projectId: "frizzly-9a65f",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('Background message:', payload);
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/static/icon.png'
  };
  self.registration.showNotification(notificationTitle, notificationOptions);
});
```

### Step 3: Add FCM to base.html

```html
<script type="module">
  import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
  import { getMessaging, getToken, onMessage } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging.js';

  const firebaseConfig = {
    apiKey: "AIzaSyCoTZoQRtiTATNY5JCWqTMCKDxoTcIok3E",
    projectId: "frizzly-9a65f",
    messagingSenderId: "YOUR_SENDER_ID",
    appId: "YOUR_APP_ID"
  };

  const app = initializeApp(firebaseConfig);
  const messaging = getMessaging(app);

  // Request permission and get token
  Notification.requestPermission().then((permission) => {
    if (permission === 'granted') {
      getToken(messaging, { vapidKey: 'YOUR_VAPID_KEY' }).then((token) => {
        console.log('FCM Token:', token);
        // Send token to your API to save for this admin
        fetch('/api/save-fcm-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token })
        });
      });
    }
  });

  // Handle foreground messages
  onMessage(messaging, (payload) => {
    console.log('Foreground message:', payload);
    showNotification(1);
    playNotificationSound();
  });
</script>
```

### Step 4: Cloud Function (Trigger on new order)

Create `functions/index.js`:
```javascript
const functions = require('firebase-functions');
const admin = require('firebase-admin');
admin.initializeApp();

exports.notifyAdminOnNewOrder = functions.firestore
  .document('orders/{orderId}')
  .onCreate(async (snap, context) => {
    const order = snap.data();
    
    // Get all admin FCM tokens
    const adminsSnapshot = await admin.firestore().collection('admins').get();
    const tokens = [];
    adminsSnapshot.forEach(doc => {
      const fcmToken = doc.data().fcmToken;
      if (fcmToken) tokens.push(fcmToken);
    });

    if (tokens.length === 0) return null;

    // Send notification
    const message = {
      notification: {
        title: '🔔 New Order!',
        body: `Order #${order.orderId} - $${order.totalAmount}`
      },
      tokens: tokens
    };

    return admin.messaging().sendMulticast(message);
  });
```

Deploy:
```bash
cd functions
npm install firebase-functions firebase-admin
firebase deploy --only functions
```

---

## Option 2: Server-Sent Events (SSE) - Simpler

### Add to API (flask_app.py):

```python
from flask import Response
import json
import time

# Store connected clients
admin_clients = []

@app.route('/api/admin/stream')
@require_admin
def admin_stream():
    def event_stream():
        admin_clients.append(request.user_id)
        try:
            while True:
                # Keep connection alive
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                time.sleep(30)
        finally:
            admin_clients.remove(request.user_id)
    
    return Response(event_stream(), mimetype='text/event-stream')

# Trigger notification when order created
def notify_admins(order_data):
    # This would be called when new order is created
    # Send to all connected admin clients
    pass
```

### Add to Dashboard:

```javascript
const eventSource = new EventSource('/api/admin/stream');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'new_order') {
    showNotification(1);
    playNotificationSound();
  }
};
```

---

## Option 3: WebSockets (Most Real-time)

### Add to API:

```python
from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    print('Admin connected')

# Trigger when new order
def notify_new_order(order):
    socketio.emit('new_order', {
        'orderId': order['orderId'],
        'totalAmount': order['totalAmount']
    }, broadcast=True)
```

### Add to Dashboard:

```javascript
const socket = io('https://apifrizzly-production.up.railway.app');

socket.on('new_order', (data) => {
  console.log('New order:', data);
  showNotification(1);
  playNotificationSound();
});
```

---

## Recommendation

**For your use case:**

1. **FCM (Best)** - True push notifications, works even when dashboard closed
2. **WebSockets (Good)** - Real-time, but requires dashboard open
3. **Polling (Current)** - Simple, but 10s delay

**Easiest to implement now: FCM with Cloud Functions**

Want me to implement FCM for you?
