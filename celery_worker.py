from celery import Celery

# Initialize Celery - it will be configured later with the Flask app
celery_app = Celery('admin_dashboard')

def create_celery_app(flask_app):
    flask_app.config.update(
        CELERY_BROKER_URL=flask_app.config['CELERY_BROKER_URL'],
        CELERY_RESULT_BACKEND=flask_app.config['CELERY_RESULT_BACKEND']
    )
    celery_app.conf.update(flask_app.config)

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app

# Example task (will be moved to a separate tasks.py later for better organization)
@celery_app.task
def debug_task(x, y):
    import time
    time.sleep(5) # Simulate long-running task
    print(f"Debug task executed: {x} + {y} = {x + y}")
    return x + y

@celery_app.task
def send_customer_notification_task(user_id, order_id, status, message_type):
    """
    Celery task to send customer notifications (SMS/Email).
    This would integrate with a third-party service like Twilio or SendGrid.
    """
    # Placeholder for actual SMS/Email sending logic
    # In a real application, you would fetch user contact info (phone/email)
    # from Firestore based on user_id and then use a service API.

    # Example status messages (can be more detailed)
    status_messages = {
        'PENDING': 'Your order {order_id} is pending confirmation.',
        'CONFIRMED': 'Your order {order_id} has been confirmed!',
        'PREPARING_ORDER': 'Your order {order_id} is being prepared!',
        'READY_FOR_PICKUP': 'Your order {order_id} is ready for pickup!',
        'ON_WAY': 'Your order {order_id} is on the way!',
        'OUT_FOR_DELIVERY': 'Your order {order_id} is out for delivery!',
        'DELIVERED': 'Your order {order_id} has been delivered!',
        'DELIVERY_ATTEMPT_FAILED': 'Delivery attempt for order {order_id} failed. We will try again soon.',
        'CANCELLED': 'Your order {order_id} has been cancelled.',
        'RETURNED': 'Your order {order_id} has been returned.'
    }
    
    notification_body = status_messages.get(status, f'Order {order_id} status: {status}').format(order_id=order_id)

    if message_type == 'sms':
        # Placeholder for SMS sending
        print(f"Sending SMS to user {user_id} for order {order_id}: {notification_body}")
        # Example: twilio_client.messages.create(to=user_phone, from_=twilio_number, body=notification_body)
    elif message_type == 'email':
        # Placeholder for Email sending
        print(f"Sending Email to user {user_id} for order {order_id}: {notification_body}")
        # Example: sendgrid_client.send_email(to=user_email, subject="Order Update", body=notification_body)
    else:
        print(f"Unknown message type: {message_type} for user {user_id}, order {order_id}")

    return f"Customer notification ({message_type}) dispatched for user {user_id}, order {order_id} with status {status}"
