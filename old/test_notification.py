#!/usr/bin/env python3
"""Test FCM notification sending"""

import firebase_admin
from firebase_admin import credentials, firestore, messaging

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
try:
    firebase_admin.get_app()
except:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Get a user with FCM token
users = db.collection('users').limit(1).stream()
user = next(users, None)

if not user:
    print("❌ No users found in database")
    exit(1)

user_data = user.to_dict()
fcm_token = user_data.get('fcmToken')

print(f"User: {user_data.get('displayName')} ({user_data.get('email')})")
print(f"FCM Token: {fcm_token[:50]}..." if fcm_token else "No FCM token")

if not fcm_token:
    print("\n❌ User has no FCM token. Please login to the app first.")
    exit(1)

# Send test notification
try:
    message = messaging.Message(
        notification=messaging.Notification(
            title='FRIZZLY Test Notification',
            body='✅ Your order has been confirmed!'
        ),
        data={
            'notification_type': 'order',
            'order_id': 'TEST123',
            'status': 'CONFIRMED'
        },
        token=fcm_token
    )
    
    response = messaging.send(message)
    print(f"\n✅ Test notification sent successfully!")
    print(f"Response: {response}")
except Exception as e:
    print(f"\n❌ Failed to send notification: {e}")
