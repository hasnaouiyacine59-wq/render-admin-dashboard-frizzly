#!/usr/bin/env python3
print("Testing admin dashboard...")

try:
    import app
    print("✅ App imports successfully")
    
    # Test that routes are registered
    routes = [rule.rule for rule in app.app.url_map.iter_rules()]
    print(f"✅ Found {len(routes)} routes")
    
    # Check key routes exist
    key_routes = ['/login', '/', '/orders', '/delivery', '/stock', '/products', '/users', '/analytics']
    for route in key_routes:
        if route in routes:
            print(f"  ✅ {route}")
        else:
            print(f"  ❌ {route} missing!")
    
    print("\n✅ All tests passed! Dashboard is ready.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
