#!/usr/bin/env python3
"""Add test drivers to Firebase for admin dashboard"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
try:
    firebase_admin.get_app()
except:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Test drivers data
test_drivers = [
    {
        'name': 'Ahmed Benali',
        'phone': '+213555123456',
        'email': 'ahmed.benali@frizzly.com',
        'status': 'available',
        'vehicleType': 'Motorcycle',
        'vehicleNumber': '16-123-45',
        'rating': 4.8,
        'totalDeliveries': 156,
        'currentLocation': {
            'latitude': 36.7538,
            'longitude': 3.0588
        },
        'createdAt': firestore.SERVER_TIMESTAMP,
        'lastActive': firestore.SERVER_TIMESTAMP
    },
    {
        'name': 'Karim Messaoudi',
        'phone': '+213770234567',
        'email': 'karim.messaoudi@frizzly.com',
        'status': 'available',
        'vehicleType': 'Car',
        'vehicleNumber': '16-456-78',
        'rating': 4.9,
        'totalDeliveries': 203,
        'currentLocation': {
            'latitude': 36.7650,
            'longitude': 3.0400
        },
        'createdAt': firestore.SERVER_TIMESTAMP,
        'lastActive': firestore.SERVER_TIMESTAMP
    },
    {
        'name': 'Yacine Hamidi',
        'phone': '+213660345678',
        'email': 'yacine.hamidi@frizzly.com',
        'status': 'on_delivery',
        'vehicleType': 'Motorcycle',
        'vehicleNumber': '16-789-12',
        'rating': 4.7,
        'totalDeliveries': 98,
        'currentLocation': {
            'latitude': 36.7400,
            'longitude': 3.0700
        },
        'createdAt': firestore.SERVER_TIMESTAMP,
        'lastActive': firestore.SERVER_TIMESTAMP
    },
    {
        'name': 'Sofiane Bouazza',
        'phone': '+213550456789',
        'email': 'sofiane.bouazza@frizzly.com',
        'status': 'offline',
        'vehicleType': 'Car',
        'vehicleNumber': '16-234-56',
        'rating': 4.6,
        'totalDeliveries': 67,
        'currentLocation': {
            'latitude': 36.7300,
            'longitude': 3.0500
        },
        'createdAt': firestore.SERVER_TIMESTAMP,
        'lastActive': firestore.SERVER_TIMESTAMP
    }
]

print("Adding test drivers to Firebase...\n")

for driver in test_drivers:
    try:
        # Add driver to Firestore
        doc_ref = db.collection('drivers').add(driver)
        print(f"✅ Added: {driver['name']} ({driver['status']}) - ID: {doc_ref[1].id}")
    except Exception as e:
        print(f"❌ Failed to add {driver['name']}: {e}")

print("\n✨ Done! Test drivers added successfully.")
print("\nDriver statuses:")
print("  - available: Can be assigned to orders")
print("  - on_delivery: Currently delivering")
print("  - offline: Not available")
