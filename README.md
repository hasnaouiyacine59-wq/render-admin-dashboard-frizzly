# FRIZZLY Admin Dashboard

Modern, responsive admin dashboard for managing FRIZZLY grocery delivery app.

## Features

✅ **Authentication** - Secure login with Flask-Login
✅ **Dashboard** - Real-time statistics and recent orders
✅ **Order Management** - View, update status (Pending → Confirmed → On Way → Completed)
✅ **Product Management** - Add, edit, delete products with images
✅ **User Management** - View all registered users
✅ **Analytics** - Charts and reports (status breakdown, revenue trends)
✅ **Responsive Design** - Works on desktop, tablet, mobile
✅ **Modern UI** - Bootstrap 5 with gradient design

---

## Installation

### 1. Install Dependencies
```bash
cd admin-dashboard
pip install -r requirements.txt
```

### 2. Add Firebase Credentials
Place `serviceAccountKey.json` in the `admin-dashboard/` folder

### 3. Create Admin User
Run this Python script to create your first admin:

```python
from werkzeug.security import generate_password_hash
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Create admin user
admin = {
    'email': 'admin@frizzly.com',
    'password': generate_password_hash('admin123'),  # Change this!
    'name': 'Admin User',
    'role': 'admin'
}

db.collection('admins').add(admin)
print("Admin user created!")
```

### 4. Run the Dashboard
```bash
python app.py
```

Visit: `http://localhost:5000`

**Login:**
- Email: `admin@frizzly.com`
- Password: `admin123`

---

## Deployment

### Deploy to PythonAnywhere (FREE)

1. Upload all files to `/home/YOUR_USERNAME/admin-dashboard/`
2. Install dependencies:
   ```bash
   pip3.8 install --user flask flask-login firebase-admin werkzeug
   ```
3. Configure WSGI file:
   ```python
   import sys
   project_home = '/home/YOUR_USERNAME/admin-dashboard'
   if project_home not in sys.path:
       sys.path = [project_home] + sys.path
   
   from app import app as application
   application.secret_key = 'your-secret-key-here'
   ```
4. Reload web app

Your dashboard will be live at: `https://YOUR_USERNAME.pythonanywhere.com`

---

## Features Overview

### Dashboard
- Total orders, revenue, products, users
- Recent orders table
- Quick stats cards

### Orders
- View all orders
- Filter by status (Pending, Confirmed, On Way, Completed, Cancelled)
- Search orders
- Update order status
- View order details with timeline
- See delivery location

### Products
- Grid view with images
- Add new products
- Edit existing products
- Delete products
- Stock management

### Users
- View all registered users
- See user details (email, phone, join date)

### Analytics
- Order status pie chart
- Monthly revenue line chart
- Status breakdown table

---

## Order Status Flow

```
PENDING → CONFIRMED → ON_WAY → COMPLETED
                         ↓
                    CANCELLED
```

---

## Screenshots

### Dashboard
![Dashboard](https://via.placeholder.com/800x400?text=Dashboard)

### Orders
![Orders](https://via.placeholder.com/800x400?text=Orders)

### Products
![Products](https://via.placeholder.com/800x400?text=Products)

---

## Security

⚠️ **Important:**
1. Change `app.secret_key` in production
2. Change default admin password
3. Use HTTPS in production
4. Enable Firebase security rules

---

## Tech Stack

- **Backend:** Flask, Flask-Login
- **Database:** Firebase Firestore
- **Frontend:** Bootstrap 5, Chart.js
- **Icons:** Bootstrap Icons
- **Fonts:** Google Fonts (Inter)

---

## Support

For issues or questions, contact: support@frizzly.com

---

## License

MIT License - Free to use and modify
