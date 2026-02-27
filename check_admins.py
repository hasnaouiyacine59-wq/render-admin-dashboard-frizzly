import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase Admin SDK
SERVICE_ACCOUNT_PATH = '/etc/secrets/serviceAccountKey.json'

# Fallback for local development if the secret file is not in the default Render path
if not os.path.exists(SERVICE_ACCOUNT_PATH):
    # Assuming serviceAccountKey.json is in the project root for local dev
    SERVICE_ACCOUNT_PATH = 'serviceAccountKey.json' 

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    print(f"CRITICAL: Firebase service account key not found at /etc/secrets/serviceAccountKey.json or serviceAccountKey.json.")
    exit(1)

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        exit(1)

db = firestore.client()

try:
    admins_ref = db.collection('admins')
    admins = admins_ref.stream()
    
    print("--- Admin Users in Firestore ---")
    count = 0
    for admin in admins:
        count += 1
        print(f"ID: {admin.id}, Data: {admin.to_dict()}")
    
    if count == 0:
        print("No admin users found in the 'admins' collection.")
        print("\nTo create one, you can run a script like this (replace with actual details):")
        print("python3 create_admin.py your-email@example.com your-password")
    
    print("---------------------------------")

except Exception as e:
    print(f"An error occurred while fetching admins: {e}")
