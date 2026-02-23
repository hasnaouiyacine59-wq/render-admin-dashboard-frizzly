"""
API Client for FRIZZLY Admin Dashboard
Communicates with the API server instead of directly accessing Firebase
"""
import requests
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class FrizzlyAPIClient:
    def __init__(self, base_url: str, admin_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.admin_token = admin_token
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.admin_token:
            headers['Authorization'] = f'Bearer {self.admin_token}'
        return headers
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        try:
            response = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            raise
    
    # ==================== ORDERS ====================
    
    def get_all_orders(self, status: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, min_amount: Optional[float] = None, max_amount: Optional[float] = None) -> List[Dict]:
        """Get all orders (admin endpoint) with optional filters"""
        try:
            params = {}
            if status:
                params['status'] = status
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            if min_amount is not None:
                params['min_amount'] = min_amount
            if max_amount is not None:
                params['max_amount'] = max_amount

            result = self._request('GET', '/api/admin/orders', params=params)
            return result.get('orders', [])
        except:
            return []
    
    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get single order"""
        try:
            result = self._request('GET', f'/api/admin/orders/{order_id}')
            return result.get('order')
        except:
            return None
    
    def update_order_status(self, order_id: str, status: str) -> bool:
        """Update order status"""
        try:
            self._request('PUT', f'/api/admin/orders/{order_id}', json={'status': status})
            return True
        except:
            return False
    
    def delete_order(self, order_id: str) -> bool:
        """Delete order"""
        try:
            self._request('DELETE', f'/api/admin/orders/{order_id}')
            return True
        except:
            return False
    
    # ==================== PRODUCTS ====================
    
    def get_products(self, active_only: bool = False, limit: int = 100) -> List[Dict]:
        """Get all products"""
        try:
            params = {'active': str(active_only).lower(), 'limit': limit}
            result = self._request('GET', '/api/products', params=params)
            return result.get('products', [])
        except:
            return []
    
    def create_product(self, product_data: Dict) -> Optional[str]:
        """Create new product"""
        try:
            result = self._request('POST', '/api/products', json=product_data)
            return result.get('productId')
        except:
            return None
    
    def update_product(self, product_id: str, product_data: Dict) -> bool:
        """Update product"""
        try:
            self._request('PUT', f'/api/products/{product_id}', json=product_data)
            return True
        except:
            return False
    
    def delete_product(self, product_id: str) -> bool:
        """Delete product"""
        try:
            self._request('DELETE', f'/api/products/{product_id}')
            return True
        except:
            return False
    
    # ==================== USERS ====================
    
    def get_all_users(self) -> List[Dict]:
        """Get all users (admin endpoint)"""
        try:
            result = self._request('GET', '/api/admin/users')
            return result.get('users', [])
        except:
            return []
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        try:
            result = self._request('GET', f'/api/users/{user_id}')
            return result.get('user')
        except:
            return None
    
    # ==================== ANALYTICS ====================
    
    def get_analytics(self) -> Dict:
        """Get analytics data (admin endpoint)"""
        try:
            return self._request('GET', '/api/admin/analytics')
        except:
            return {'totalOrders': 0, 'totalRevenue': 0, 'statusCounts': {}}
    
    # ==================== HEALTH ====================
    
    def health_check(self) -> bool:
        """Check API health"""
        try:
            result = self._request('GET', '/api/health')
            return result.get('status') == 'healthy'
        except:
            return False

    # ==================== DRIVERS ====================
    
    def get_all_drivers(self) -> List[Dict]:
        try:
            result = self._request('GET', '/api/drivers')
            return result.get('drivers', [])
        except:
            return []
            
    def get_driver(self, driver_id: str) -> Optional[Dict]:
        try:
            result = self._request('GET', f'/api/drivers/{driver_id}')
            return result.get('driver')
        except:
            return None

    def create_driver(self, driver_data: Dict) -> Optional[str]:
        try:
            result = self._request('POST', '/api/drivers', json=driver_data)
            return result.get('driverId')
        except:
            return None

    def update_driver(self, driver_id: str, driver_data: Dict) -> bool:
        try:
            self._request('PUT', f'/api/drivers/{driver_id}', json=driver_data)
            return True
        except:
            return False

    def delete_driver(self, driver_id: str) -> bool:
        try:
            self._request('DELETE', f'/api/drivers/{driver_id}')
            return True
        except:
            return False
            
    # ==================== ACTIVITY LOGS ====================
    
    def log_activity(self, action: str, details: str, user_id: Optional[str] = None, user_name: Optional[str] = None, ip_address: Optional[str] = None) -> bool:
        try:
            data = {
                'action': action,
                'details': details,
                'userId': user_id,
                'userName': user_name,
                'ipAddress': ip_address
            }
            self._request('POST', '/api/activity-logs', json=data)
            return True
        except:
            return False

    # ==================== ORDERS (for driver history) ====================

    def get_orders_by_driver(self, driver_id: str) -> List[Dict]:
        try:
            result = self._request('GET', '/api/orders', params={'driverId': driver_id})
            return result.get('orders', [])
        except:
            return []

    # ==================== NOTIFICATIONS ====================

    def send_notification(self, user_id: str, status: str, order_id: str) -> bool:
        """Send notification about order status update"""
        try:
            data = {
                'user_id': user_id,
                'status': status,
                'order_id': order_id
            }
            result = self._request('POST', '/api/notifications/send', json=data)
            return result.get('success', False)
        except:
            return False

    def send_bulk_notification(self, title: str, message: str) -> bool:
        """Send bulk notification"""
        try:
            data = {
                'title': title,
                'message': message
            }
            result = self._request('POST', '/api/notifications/send-bulk', json=data)
            return result.get('success', False)
        except:
            return False

    def send_test_notification(self, user_id: str, title: str, message: str) -> bool:
        try:
            data = {
                'user_id': user_id,
                'title': title,
                'message': message
            }
            result = self._request('POST', '/api/notifications/send-test', json=data)
            return result.get('success', False)
        except:
            return False

    # ==================== PRODUCTS (Categories) ====================

    def get_product_categories(self) -> List[str]:
        try:
            result = self._request('GET', '/api/products/categories')
            return result.get('categories', [])
        except:
            return []

    # ==================== DRIVERS (Available) ====================

    def get_available_drivers(self) -> List[Dict]:
        try:
            result = self._request('GET', '/api/drivers/available')
            return result.get('drivers', [])
        except:
            return []

    # ==================== DASHBOARD ====================

    def get_dashboard_stats(self) -> Dict:
        try:
            result = self._request('GET', '/api/admin/dashboard-stats')
            return result.get('stats', {})
        except:
            return {}

    # ==================== ORDERS (Driver Assignment) ====================

    def assign_driver_to_order(self, order_id: str, driver_id: str) -> bool:
        try:
            data = {'driverId': driver_id}
            result = self._request('POST', f'/api/admin/orders/{order_id}/assign-driver', json=data)
            return result.get('success', False)
        except:
            return False

    # ==================== PRODUCTS (Bulk Operations) ====================

    def bulk_delete_products(self, product_ids: List[str]) -> bool:
        try:
            data = {'productIds': product_ids}
            result = self._request('POST', '/api/products/bulk-delete', json=data)
            return result.get('success', False)
        except:
            return False

    # ==================== NOTIFICATIONS (List) ====================

    def get_notifications(self, limit: int = 100) -> List[Dict]:
        try:
            params = {'limit': limit}
            result = self._request('GET', '/api/notifications', params=params)
            return result.get('notifications', [])
        except:
            return []

    # ==================== NOTIFICATIONS (Bulk Send) ====================

    def send_bulk_notification(self, title: str, message: str) -> bool:
        try:
            data = {
                'title': title,
                'message': message
            }
            result = self._request('POST', '/api/notifications/send-bulk', json=data)
            return result.get('success', False)
        except:
            return False

    # ==================== ACTIVITY LOGS (List) ====================

    def get_activity_logs(self, limit: int = 100) -> List[Dict]:
        try:
            params = {'limit': limit}
            result = self._request('GET', '/api/activity-logs', params=params)
            return result.get('logs', [])
        except:
            return []

    # ==================== EXPORTS ====================

    def export_orders(self) -> Optional[str]:
        try:
            response = self.session.request('GET', '/api/exports/orders', headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            return response.text # Assuming API returns CSV directly as text
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for export_orders: {e}")
            return None

    def export_revenue(self) -> Optional[str]:
        try:
            response = self.session.request('GET', '/api/exports/revenue', headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            return response.text # Assuming API returns CSV directly as text
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for export_revenue: {e}")
            return None

    # ==================== ANALYTICS (Revenue) ====================

    def get_revenue_data(self) -> Dict:
        try:
            result = self._request('GET', '/api/analytics/revenue')
            return result.get('data', {})
        except:
            return {}

    # ==================== ADMIN PROFILE ====================

    def get_admin_profile(self) -> Optional[Dict]:
        try:
            result = self._request('GET', '/api/admin/profile')
            return result.get('profile')
        except:
            return None

    def update_admin_profile(self, profile_data: Dict) -> bool:
        try:
            result = self._request('PUT', '/api/admin/profile', json=profile_data)
            return result.get('success', False)
        except:
            return False

    # ==================== ADMIN PASSWORD ====================

    def change_admin_password(self, current_password: str, new_password: str) -> bool:
        try:
            data = {
                'currentPassword': current_password,
                'newPassword': new_password
            }
            result = self._request('PUT', '/api/admin/change-password', json=data)
            return result.get('success', False)
        except:
            return False

    # ==================== PRODUCTS (Stock) ====================

    def get_product_stock(self) -> List[Dict]:
        try:
            result = self._request('GET', '/api/products/stock')
            return result.get('products', [])
        except:
            return []

    def update_product_stock(self, product_id: str, new_stock: int) -> bool:
        """Update product stock"""
        try:
            self._request('PUT', f'/api/products/{product_id}/stock', json={'stock': new_stock})
            return True
        except:
            return False
