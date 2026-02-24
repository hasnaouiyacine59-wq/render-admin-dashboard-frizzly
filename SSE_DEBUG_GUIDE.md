# 🔍 SSE Real-Time Notifications - Debug Guide

## **Testing SSE Connection**

### **1. Test Page**
Visit: `https://dashboard-frizzly.onrender.com/sse-test`

**What to check:**
- Click "Connect" button
- Status should show "Connected ✅"
- Should see "SSE Connected!" in logs
- Should see heartbeat messages every 30 seconds

### **2. Dashboard Page**
Visit: `https://dashboard-frizzly.onrender.com/dashboard`

**Open Browser Console (F12):**
- Should see: `✅ SSE Connected`
- Should see heartbeat comments every 30s

### **3. Test New Order**
1. Keep dashboard open with console visible
2. Create order from Android app
3. **Expected in console:**
   - `🔔 New order: {orderId: "ORD123", ...}`
4. **Expected on screen:**
   - Toast notification appears below navbar
   - Browser notification (if permission granted)
   - Page reloads after 2 seconds

---

## **Server Logs to Check**

When SSE connects, you should see in Render logs:
```
SSE: New connection from user <admin_id>
SSE: Starting Firestore listener
SSE: Snapshot received with X changes, first=True
SSE: Skipping initial snapshot
SSE: Sending connected message
```

When new order is created:
```
SSE: Snapshot received with 1 changes, first=False
SSE: Change type=ADDED, doc=ORD123
SSE: Queued event for order ORD123
SSE: Sending new_order event
```

---

## **Common Issues**

### **Issue 1: SSE Not Connecting**
**Symptoms:** Console shows error, status stays "Not Connected"

**Check:**
1. Are you logged in?
2. Check browser console for errors
3. Check Render logs for connection attempts

**Fix:** Ensure `/api/stream-orders` route is accessible

### **Issue 2: Connected But No Events**
**Symptoms:** Connected ✅ but no notifications when order created

**Check:**
1. Is Firestore listener starting? (check logs)
2. Is order actually being created in Firestore?
3. Are events being queued? (check logs)

**Debug:**
```javascript
// In browser console
eventSource.addEventListener('message', (e) => console.log('Any message:', e));
```

### **Issue 3: Events Received But No Notification**
**Symptoms:** Console shows event but no toast/browser notification

**Check:**
1. Is `showNotification()` being called?
2. Is Bootstrap loaded?
3. Browser notification permission granted?

**Debug:**
```javascript
// Test notification manually
showNotification('Test', 'This is a test');
```

### **Issue 4: Initial Orders Showing as New**
**Symptoms:** All existing orders trigger notifications on connect

**Status:** ✅ FIXED - We skip first snapshot

---

## **Manual Testing Steps**

### **Step 1: Verify Connection**
```javascript
// In browser console on dashboard
console.log('EventSource state:', eventSource.readyState);
// 0 = CONNECTING, 1 = OPEN, 2 = CLOSED
```

### **Step 2: Test Event Listener**
```javascript
// Add test listener
eventSource.addEventListener('new_order', (e) => {
    console.log('NEW ORDER EVENT:', e.data);
});
```

### **Step 3: Check Heartbeat**
```
// Should see in console every 30s:
: heartbeat
```

### **Step 4: Create Test Order**
1. Use Android app to create order
2. Watch console for event
3. Watch for notification

---

## **Expected Flow**

```
1. Dashboard loads
   ↓
2. JavaScript calls connectSSE()
   ↓
3. EventSource connects to /api/stream-orders
   ↓
4. Server starts Firestore listener
   ↓
5. First snapshot arrives (skipped)
   ↓
6. "connected" message sent to client
   ↓
7. Client shows "✅ SSE Connected"
   ↓
8. Heartbeat every 30s
   ↓
9. New order created in Firestore
   ↓
10. Firestore triggers on_snapshot
   ↓
11. Event queued
   ↓
12. Event sent to client
   ↓
13. Client receives "new_order" event
   ↓
14. showNotification() called
   ↓
15. Toast appears + sound + reload
```

---

## **Debugging Commands**

### **Check if SSE endpoint works:**
```bash
curl -N -H "Cookie: session=YOUR_SESSION" \
  https://dashboard-frizzly.onrender.com/api/stream-orders
```

### **Check Render logs:**
```bash
# In Render dashboard, view logs and filter for "SSE:"
```

### **Test Firestore listener locally:**
```python
# In Python console
from app import db
def callback(snapshot, changes, read_time):
    print(f"Changes: {len(changes)}")
    for change in changes:
        print(f"  {change.type.name}: {change.document.id}")

watch = db.collection('orders').limit(5).on_snapshot(callback)
# Create order from app
# Should see output
watch.unsubscribe()
```

---

## **Current Status**

✅ SSE endpoint implemented  
✅ Firestore listener working  
✅ First snapshot skipped  
✅ Events queued and sent  
✅ JavaScript client implemented  
✅ Toast notifications positioned correctly  
✅ Auto-reconnect on error  
✅ Logging added for debugging  

**Next:** Test with real order creation from Android app

---

## **Quick Test**

1. Open dashboard: https://dashboard-frizzly.onrender.com
2. Open console (F12)
3. Look for: `✅ SSE Connected`
4. Create order from Android app
5. Should see notification within 1-2 seconds

**If not working, check Render logs for SSE messages.**
