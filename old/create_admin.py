#!/usr/bin/env python3
"""
Create admin user for FRIZZLY dashboard
"""

from werkzeug.security import generate_password_hash
import firebase_admin
from firebase_admin import credentials, firestore
import sys

def create_admin():
    try:
        # Initialize Firebase
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        # Get admin details
        print("=== Create FRIZZLY Admin User ===\n")
        email = input("Email: ").strip()
        password = input("Password: ").strip()
        name = input("Name: ").strip()
        
        if not email or not password or not name:
            print("Error: All fields are required!")
            return
        
        # Create admin user
        admin = {
            'email': email,
            'password': generate_password_hash(password),
            'name': name,
            'role': 'admin'
        }
        
        db.collection('admins').add(admin)
        
        print(f"\n✅ Admin user created successfully!")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print(f"\nYou can now login at: http://localhost:5000/login")
        
    except FileNotFoundError:
        print("Error: serviceAccountKey.json not found!")
        print("Download it from Firebase Console and place it in this directory.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    create_admin()
