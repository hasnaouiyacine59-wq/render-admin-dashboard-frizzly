#!/usr/bin/env python3
"""
Test SSE notification flow
"""
import requests
import json
import time

API_URL = "http://localhost:5000"
ADMIN_TOKEN = "YOUR_ADMIN_ID"  # Replace with actual admin ID from Firestore

def test_sse_connection():
    """Test SSE connection"""
    print("🔴 Testing SSE connection...")
    
    headers = {'Authorization': f'Bearer {ADMIN_TOKEN}'}
    
    try:
        response = requests.get(
            f"{API_URL}/api/admin/stream/orders",
            headers=headers,
            stream=True,
            timeout=5
        )
        
        print(f"✅ Connected! Status: {response.status_code}")
        
        # Read first few events
        for i, line in enumerate(response.iter_lines()):
            if i > 5:
                break
            if line:
                print(f"📨 Received: {line.decode('utf-8')}")
        
        print("✅ SSE connection working!")
        
    except Exception as e:
        print(f"❌ SSE connection failed: {e}")

def test_order_submission():
    """Test order submission"""
    print("\n🔴 Testing order submission...")
    
    # You need a valid Firebase user token
    user_token = "YOUR_USER_TOKEN"  # Get from Android app
    
    headers = {
        'Authorization': f'Bearer {user_token}',
        'Content-Type': 'application/json'
    }
    
    order_data = {
        "order": {
            "items": [
                {
                    "productId": "test-product",
                    "name": "Test Product",
                    "price": 10.0,
                    "quantity": 2
                }
            ],
            "totalAmount": 20.0,
            "deliveryAddress": "123 Test St"
        }
    }
    
    try:
        response = requests.post(
            f"{API_URL}/api/order/submit",
            headers=headers,
            json=order_data
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Order submitted successfully!")
        else:
            print(f"❌ Order submission failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def check_firestore_listener():
    """Check if Firestore listener is working"""
    print("\n🔴 Checking Firestore listener...")
    print("1. Start API server: cd ~/AndroidStudioProjects/API_FRIZZLY && python flask_app.py")
    print("2. Watch logs for: '🔴 SSE: Starting Firestore listener...'")
    print("3. Create an order from Android app")
    print("4. Watch logs for: '🔴 SSE: Snapshot received with X changes'")
    print("5. Watch logs for: '🔴 SSE: Queuing event: ORD123'")

if __name__ == '__main__':
    print("=" * 60)
    print("SSE NOTIFICATION FLOW TEST")
    print("=" * 60)
    
    print("\n📋 SETUP:")
    print("1. API Server running on http://localhost:5000")
    print("2. Admin Dashboard running on http://localhost:5001")
    print("3. Replace ADMIN_TOKEN with your admin ID from Firestore")
    print("4. Replace USER_TOKEN with valid Firebase user token")
    
    print("\n" + "=" * 60)
    
    # Test SSE connection
    test_sse_connection()
    
    # Instructions for manual testing
    check_firestore_listener()
    
    print("\n" + "=" * 60)
    print("📝 DEBUGGING CHECKLIST:")
    print("=" * 60)
    print("✓ API server running?")
    print("✓ Dashboard running?")
    print("✓ Admin logged in to dashboard?")
    print("✓ Browser console open (F12)?")
    print("✓ SSE connection established? (check logs)")
    print("✓ Firestore listener started? (check API logs)")
    print("✓ Create order from Android app")
    print("✓ Check API logs for '🔴 SSE: Snapshot received'")
    print("✓ Check dashboard logs for '🔴 Dashboard SSE: Received'")
    print("✓ Check browser console for event")
    print("=" * 60)
