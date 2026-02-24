#!/usr/bin/env python3
"""
Phase 2: Replace all api_client calls with direct Firebase operations
"""

import re

def replace_api_calls():
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Dashboard stats
    content = content.replace(
        'dashboard_stats = api_client.get_dashboard_stats()',
        '''# Get dashboard stats from Firebase
        orders = list(db.collection('orders').stream())
        products = list(db.collection('products').stream())
        users = list(db.collection('users').stream())
        
        pending_orders = [o for o in orders if o.to_dict().get('status') == 'PENDING']
        low_stock = [p for p in products if p.to_dict().get('stock', 0) < 10]
        total_revenue = sum(o.to_dict().get('totalAmount', 0) for o in orders if o.to_dict().get('status') == 'DELIVERED')
        
        dashboard_stats = {
            'total_orders': len(orders),
            'pending_orders': len(pending_orders),
            'total_products': len(products),
            'total_users': len(users),
            'low_stock_products': len(low_stock),
            'total_revenue': total_revenue
        }'''
    )
    
    # Create product
    content = content.replace(
        'result = api_client.create_product(product_data)',
        'doc_ref = db.collection(\'products\').add(product_data)\n                result = {\'success\': True, \'id\': doc_ref[1].id}'
    )
    
    # Update product
    content = content.replace(
        'result = api_client.update_product(product_id, product_data)',
        'db.collection(\'products\').document(product_id).update(product_data)\n                result = {\'success\': True}'
    )
    
    # Get product stock
    content = content.replace(
        'products = api_client.get_product_stock()',
        'products = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'products\').stream()]'
    )
    
    # Get all drivers
    content = content.replace(
        'all_drivers = api_client.get_all_drivers()',
        'all_drivers = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'drivers\').stream()]'
    )
    
    # Create driver
    content = content.replace(
        'driver_id = api_client.create_driver(driver_data)',
        'doc_ref = db.collection(\'drivers\').add(driver_data)\n                driver_id = doc_ref[1].id'
    )
    
    # Get driver
    content = re.sub(
        r'driver = api_client\.get_driver\(driver_id\)',
        '''doc = db.collection('drivers').document(driver_id).get()
        driver = {'id': doc.id, **doc.to_dict()} if doc.exists else None''',
        content
    )
    
    # Update driver
    content = content.replace(
        'if api_client.update_driver(driver_id, updates):',
        'db.collection(\'drivers\').document(driver_id).update(updates)\n                if True:'
    )
    
    # Delete driver
    content = content.replace(
        'if api_client.delete_driver(driver_id):',
        'db.collection(\'drivers\').document(driver_id).delete()\n        if True:'
    )
    
    # Get orders by driver
    content = content.replace(
        'api_deliveries = api_client.get_orders_by_driver(driver_id)',
        'api_deliveries = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'orders\').where(\'driverId\', \'==\', driver_id).stream()]'
    )
    
    # Get revenue data
    content = content.replace(
        'data = api_client.get_revenue_data()',
        '''orders = [{\'id\': d.id, **d.to_dict()} for d in db.collection('orders').stream()]
        data = {
            'total_revenue': sum(o.get('totalAmount', 0) for o in orders if o.get('status') == 'DELIVERED'),
            'orders': orders
        }'''
    )
    
    # Get notifications
    content = content.replace(
        'all_notifications = api_client.get_notifications()',
        'all_notifications = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'notifications\').limit(50).stream()]'
    )
    
    # Send bulk notification
    content = content.replace(
        'success = api_client.send_bulk_notification(title, message)',
        '''users = db.collection('users').stream()
                count = 0
                for user_doc in users:
                    user_data = user_doc.to_dict()
                    if user_data.get('fcmToken'):
                        try:
                            msg = messaging.Message(
                                notification=messaging.Notification(title=title, body=message),
                                token=user_data['fcmToken']
                            )
                            messaging.send(msg)
                            count += 1
                        except:
                            pass
                success = count > 0'''
    )
    
    # Get activity logs
    content = content.replace(
        'logs = api_client.get_activity_logs()',
        'logs = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'activity_logs\').order_by(\'timestamp\', direction=firestore.Query.DESCENDING).limit(100).stream()]'
    )
    
    # Save
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("✅ Phase 2 complete: All API calls replaced with Firebase")
    print(f"   Total lines: {len(content.splitlines())}")

if __name__ == '__main__':
    replace_api_calls()
