# FRIZZLY Admin Dashboard - Quick Start Guide

## ✅ Features Added

### 1. **Stock Management** (`/stock`)
- View all products with current stock levels
- Color-coded stock status (Red: Out of Stock, Yellow: Low Stock, Green: In Stock)
- Update stock quantities with modal dialogs
- Low stock alerts (< 10 units)
- Stock statistics dashboard

### 2. **Delivery Logistics** (`/delivery`)
- View all active deliveries (CONFIRMED & ON_WAY orders)
- Assign drivers to orders
- Track driver information (name, phone)
- View delivery locations on Google Maps
- Delivery statistics (Awaiting Pickup vs Out for Delivery)

### 3. **Enhanced Dashboard**
- Low stock product alerts
- Quick navigation to stock management
- Real-time statistics

---

## 🚀 How to Run

### 1. Install Dependencies
```bash
cd admin-dashboard
pip install flask flask-login firebase-admin werkzeug
```

### 2. Add Firebase Credentials
Place your `serviceAccountKey.json` in the `admin-dashboard/` folder

### 3. Create Admin User
```bash
python create_admin.py
```

Or manually:
```python
from werkzeug.security import generate_password_hash
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

admin = {
    'email': 'admin@frizzly.com',
    'password': generate_password_hash('admin123'),
    'name': 'Admin',
    'role': 'admin'
}

db.collection('admins').add(admin)
print("Admin created!")
```

### 4. Run the Dashboard
```bash
python app.py
```

Visit: **http://localhost:5000**

**Login:**
- Email: `admin@frizzly.com`
- Password: `admin123`

---

## 📋 Admin Features

### **Dashboard** (`/`)
- Total orders, revenue, products, users
- Pending orders count
- Low stock alerts
- Recent orders

### **Orders** (`/orders`)
- View all orders
- Filter by status
- Update order status
- View order details with timeline

### **Delivery** (`/delivery`)
- View active deliveries
- Assign drivers to orders
- Track delivery status
- View delivery locations on map

### **Products** (`/products`)
- Grid view with images
- Add new products
- Edit existing products
- Delete products

### **Stock** (`/stock`)
- View all product stock levels
- Update stock quantities
- Low stock alerts
- Stock statistics

### **Users** (`/users`)
- View all registered users
- User details (email, phone, join date)

### **Analytics** (`/analytics`)
- Order status pie chart
- Monthly revenue line chart
- Status breakdown table

---

## 🔧 Product Stock Management

### Add Stock Field to Products
When adding/editing products, include a `stock` field:

```python
product = {
    'name': 'Apple',
    'price': '$2.99/kg',
    'stock': 100,  # Add this field
    'imageUrl': 'https://...',
    'createdAt': datetime.now().isoformat()
}
```

### Update Stock via Admin
1. Go to **Stock** page
2. Click **Update** button on any product
3. Enter new stock quantity
4. Click **Update Stock**

---

## 🚚 Delivery Management

### Assign Driver to Order
1. Go to **Delivery** page
2. Find order with "No driver assigned" alert
3. Click **Assign Driver**
4. Enter driver name and phone
5. Order status automatically changes to "ON_WAY"

### View Delivery Location
1. Click **View on Map** button
2. Opens Google Maps with delivery coordinates

---

## 📊 Order Status Flow

```
PENDING → CONFIRMED → ON_WAY → COMPLETED
                         ↓
                    CANCELLED
```

### Status Meanings:
- **PENDING**: Order placed, awaiting confirmation
- **CONFIRMED**: Order confirmed, ready for pickup
- **ON_WAY**: Driver assigned, out for delivery
- **COMPLETED**: Order delivered successfully
- **CANCELLED**: Order cancelled

---

## 🔐 Security

⚠️ **Important for Production:**
1. Change `app.secret_key` in `app.py`
2. Change default admin password
3. Use HTTPS
4. Enable Firebase security rules
5. Add rate limiting
6. Use environment variables for secrets

---

## 🌐 Deploy to PythonAnywhere (FREE)

1. Upload files to `/home/YOUR_USERNAME/admin-dashboard/`
2. Install dependencies:
   ```bash
   pip3.8 install --user flask flask-login firebase-admin werkzeug
   ```
3. Configure WSGI file (see README.md)
4. Reload web app

Your dashboard will be live at: `https://YOUR_USERNAME.pythonanywhere.com`

---

## 📱 Mobile Responsive

The admin dashboard is fully responsive and works on:
- Desktop computers
- Tablets
- Mobile phones

---

## 🎨 UI Features

- Modern gradient design (purple theme)
- Bootstrap 5 framework
- Bootstrap Icons
- Chart.js for analytics
- Responsive tables
- Modal dialogs
- Alert notifications
- Color-coded status badges

---

## 🆘 Troubleshooting

### Firebase Connection Error
- Check `serviceAccountKey.json` is in the correct folder
- Verify Firebase credentials are valid

### Login Not Working
- Ensure admin user is created in Firestore
- Check password is hashed correctly

### Stock Not Showing
- Add `stock` field to products in Firestore
- Default value is 0 if field doesn't exist

---

## 📞 Support

For issues or questions:
- Check logs in terminal
- Verify Firebase connection
- Ensure all dependencies are installed

---

## 🎉 You're All Set!

Your admin dashboard is now ready with:
✅ Order management
✅ Stock control
✅ Delivery logistics
✅ Product management
✅ User management
✅ Analytics & reports

Happy managing! 🚀
