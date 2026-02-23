#!/usr/bin/env python3
"""
Create user profile in Firestore from Firebase Auth data
Run this to populate user profiles for existing users
"""
import requests
import sys

API_URL = "https://apifrizzly-production.up.railway.app"

def create_user_profile(user_id):
    """Create a basic user profile in Firestore"""
    # Login as admin
    login_response = requests.post(f'{API_URL}/api/admin/login', 
                                  json={'email': 'admin@frizzly.com', 'password': 'admin123'})
    
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.json()}")
        return
    
    token = login_response.json()['token']
    
    # Get user from Firebase Auth
    user_response = requests.get(f'{API_URL}/api/admin/users/{user_id}',
                                headers={'Authorization': f'Bearer {token}'})
    
    if user_response.status_code != 200:
        print(f"Failed to get user: {user_response.json()}")
        return
    
    user = user_response.json()['user']
    print(f"User: {user.get('email')} - {user.get('displayName')}")
    print("\nTo populate full profile with device info:")
    print("1. Open FRIZZLY app on Android")
    print("2. Sign out")
    print("3. Sign in again")
    print("\nThis will trigger the app to save device info to Firestore.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 create_user_profile.py <user_id>")
        print("\nExample: python3 create_user_profile.py orI6CDcLXHSfrZ5vkuwaSo2PktO2")
        sys.exit(1)
    
    create_user_profile(sys.argv[1])
