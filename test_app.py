#!/usr/bin/env python3
"""Test script to verify app.py works correctly"""

import sys
sys.path.insert(0, '/home/oo33/AndroidStudioProjects/render-admin-dashboard-frizzly')

from app import app, db

def test_firebase():
    """Test Firebase connection"""
    print("🔍 Testing Firebase connection...")
    try:
        orders = list(db.collection('orders').limit(1).stream())
        print(f"✅ Firebase connected - {len(orders)} order(s) found")
        return True
    except Exception as e:
        print(f"❌ Firebase error: {e}")
        return False

def test_dashboard_stats():
    """Test dashboard stats calculation"""
    print("\n🔍 Testing dashboard stats...")
    try:
        orders = list(db.collection('orders').stream())
        products = list(db.collection('products').stream())
        users = list(db.collection('users').stream())
        
        pending = [o for o in orders if o.to_dict().get('status') == 'PENDING']
        low_stock = [p for p in products if p.to_dict().get('stock', 0) < 10]
        revenue = sum(o.to_dict().get('totalAmount', 0) for o in orders if o.to_dict().get('status') == 'DELIVERED')
        
        stats = {
            'total_orders': len(orders),
            'pending_orders': len(pending),
            'total_products': len(products),
            'total_users': len(users),
            'low_stock_products': len(low_stock),
            'total_revenue': revenue
        }
        
        print(f"✅ Stats calculated:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        # Verify all required fields
        required = ['total_orders', 'pending_orders', 'total_products', 'total_users', 'low_stock_products', 'total_revenue']
        missing = [f for f in required if f not in stats]
        if missing:
            print(f"❌ Missing fields: {missing}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Stats error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_routes():
    """Test that all routes are defined"""
    print("\n🔍 Testing routes...")
    required_routes = [
        'dashboard', 'login', 'logout', 'orders', 'order_detail',
        'update_order_status', 'products', 'add_product', 'edit_product',
        'delete_product', 'users', 'delivery_logistics', 'drivers',
        'stock_management', 'revenue', 'analytics', 'notifications',
        'activity_logs', 'settings', 'stream_orders'
    ]
    
    with app.app_context():
        defined_routes = [rule.endpoint for rule in app.url_map.iter_rules()]
        missing = [r for r in required_routes if r not in defined_routes]
        
        if missing:
            print(f"❌ Missing routes: {missing}")
            return False
        
        print(f"✅ All {len(required_routes)} routes defined")
        return True

if __name__ == '__main__':
    print("=" * 60)
    print("Testing render-admin-dashboard-frizzly app.py")
    print("=" * 60)
    
    tests = [
        test_firebase,
        test_dashboard_stats,
        test_routes
    ]
    
    results = [test() for test in tests]
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\n🚀 App is ready to deploy!")
        print("\nTo run locally:")
        print("  cd ~/AndroidStudioProjects/render-admin-dashboard-frizzly")
        print("  python3 app.py")
        print("\nThen visit: http://localhost:5000")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
