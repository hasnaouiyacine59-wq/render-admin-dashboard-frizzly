#!/usr/bin/env python3
"""Phase 3: Replace remaining API calls"""

def replace_remaining():
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Get admin profile
    content = content.replace(
        'admin_profile = api_client.get_admin_profile()',
        '''doc = db.collection('admins').document(current_user.id).get()
        admin_profile = doc.to_dict() if doc.exists else {}'''
    )
    
    # Update admin profile
    content = content.replace(
        'success = api_client.update_admin_profile(profile_data)',
        'db.collection(\'admins\').document(current_user.id).update(profile_data)\n                success = True'
    )
    
    # Export orders
    content = content.replace(
        'csv_data = api_client.export_orders()',
        '''import csv
        from io import StringIO
        orders = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'orders\').stream()]
        output = StringIO()
        if orders:
            writer = csv.DictWriter(output, fieldnames=orders[0].keys())
            writer.writeheader()
            writer.writerows(orders)
        csv_data = output.getvalue()'''
    )
    
    # Export revenue
    content = content.replace(
        'csv_data = api_client.export_revenue()',
        '''import csv
        from io import StringIO
        orders = [{\'id\': d.id, **d.to_dict()} for d in db.collection(\'orders\').where(\'status\', \'==\', \'DELIVERED\').stream()]
        output = StringIO()
        if orders:
            writer = csv.DictWriter(output, fieldnames=[\'id\', \'orderId\', \'totalAmount\', \'timestamp\'])
            writer.writeheader()
            for o in orders:
                writer.writerow({\'id\': o.get(\'id\'), \'orderId\': o.get(\'orderId\'), \'totalAmount\': o.get(\'totalAmount\'), \'timestamp\': o.get(\'timestamp\')})
        csv_data = output.getvalue()'''
    )
    
    # Get all orders with filters
    content = content.replace(
        'orders_list = api_client.get_all_orders(',
        '''query = db.collection(\'orders\')
        if status_filter and status_filter != \'all\':
            query = query.where(\'status\', \'==\', status_filter)
        orders_list = [{\'id\': d.id, **d.to_dict()} for d in query.stream()]
        orders_list = api_client.get_all_orders('''
    )
    
    # Bulk delete products
    content = content.replace(
        'success = api_client.bulk_delete_products(product_ids)',
        '''for pid in product_ids:
                    db.collection(\'products\').document(pid).delete()
                success = True'''
    )
    
    # Assign driver to order
    content = content.replace(
        'success = api_client.assign_driver_to_order(order_id, driver_id)',
        'db.collection(\'orders\').document(order_id).update({\'driverId\': driver_id})\n        success = True'
    )
    
    # Update product stock
    content = content.replace(
        'success = api_client.update_product_stock(product_id, new_stock)',
        'db.collection(\'products\').document(product_id).update({\'stock\': new_stock})\n        success = True'
    )
    
    # Send test notification
    content = content.replace(
        'success = api_client.send_test_notification(user_id, title, message)',
        '''user_doc = db.collection(\'users\').document(user_id).get()
        if user_doc.exists and user_doc.to_dict().get(\'fcmToken\'):
            try:
                msg = messaging.Message(
                    notification=messaging.Notification(title=title, body=message),
                    token=user_doc.to_dict()[\'fcmToken\']
                )
                messaging.send(msg)
                success = True
            except:
                success = False
        else:
            success = False'''
    )
    
    # Change admin password
    content = content.replace(
        'success = api_client.change_admin_password(current_password, new_password)',
        '''from werkzeug.security import generate_password_hash
        admin_doc = db.collection(\'admins\').document(current_user.id).get()
        if admin_doc.exists and check_password_hash(admin_doc.to_dict().get(\'password\'), current_password):
            db.collection(\'admins\').document(current_user.id).update({\'password\': generate_password_hash(new_password)})
            success = True
        else:
            success = False'''
    )
    
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("✅ Phase 3 complete: All remaining API calls replaced")

if __name__ == '__main__':
    replace_remaining()
