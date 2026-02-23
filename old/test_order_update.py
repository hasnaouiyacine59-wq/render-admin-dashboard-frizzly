#!/usr/bin/env python3
"""Test order status update in Firestore"""

import firebase_admin
from firebase_admin import credentials, firestore
import time

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
try:
    firebase_admin.get_app()
except:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Get first order
orders = list(db.collection('orders').limit(1).stream())

if not orders:
    print("❌ No orders found in database")
    exit(1)

order = orders[0]
order_data = order.to_dict()

print(f"Order ID: {order.id}")
print(f"Current Status: {order_data.get('status')}")
print(f"User ID: {order_data.get('userId')}")

# Update status to CONFIRMED
print("\n🔄 Updating status to CONFIRMED...")
db.collection('orders').document(order.id).update({
    'status': 'CONFIRMED',
    'updatedAt': firestore.SERVER_TIMESTAMP
})

print("✅ Status updated!")

# Wait and check
time.sleep(1)
updated_order = db.collection('orders').document(order.id).get()
print(f"New Status: {updated_order.to_dict().get('status')}")

print("\n📱 Check your Android app - the order should update automatically!")
