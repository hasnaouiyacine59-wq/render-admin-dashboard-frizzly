#!/bin/bash

echo "========================================="
echo "FRIZZLY API Migration Test"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test API health
echo "1. Testing API health..."
response=$(curl -s http://localhost:5000/api/health)
if [[ $response == *"healthy"* ]]; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo -e "${RED}✗ API is not responding${NC}"
    echo "   Make sure API is running: cd ~/AndroidStudioProjects/API_FRIZZLY && python flask_app.py"
    exit 1
fi

echo ""

# Test admin login
echo "2. Testing admin login..."
login_response=$(curl -s -X POST http://localhost:5000/api/admin/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@frizzly.com","password":"admin123"}')

if [[ $login_response == *"customToken"* ]]; then
    echo -e "${GREEN}✓ Admin login successful${NC}"
    TOKEN=$(echo $login_response | grep -o '"customToken":"[^"]*' | cut -d'"' -f4)
else
    echo -e "${RED}✗ Admin login failed${NC}"
    echo "   Response: $login_response"
    exit 1
fi

echo ""

# Test admin orders endpoint
echo "3. Testing admin orders endpoint..."
orders_response=$(curl -s http://localhost:5000/api/admin/orders \
    -H "Authorization: Bearer $TOKEN")

if [[ $orders_response == *"orders"* ]]; then
    echo -e "${GREEN}✓ Admin orders endpoint working${NC}"
else
    echo -e "${RED}✗ Admin orders endpoint failed${NC}"
    echo "   Response: $orders_response"
fi

echo ""

# Test products endpoint
echo "4. Testing products endpoint..."
products_response=$(curl -s http://localhost:5000/api/products)

if [[ $products_response == *"products"* ]]; then
    echo -e "${GREEN}✓ Products endpoint working${NC}"
else
    echo -e "${RED}✗ Products endpoint failed${NC}"
fi

echo ""

# Test admin users endpoint
echo "5. Testing admin users endpoint..."
users_response=$(curl -s http://localhost:5000/api/admin/users \
    -H "Authorization: Bearer $TOKEN")

if [[ $users_response == *"users"* ]]; then
    echo -e "${GREEN}✓ Admin users endpoint working${NC}"
else
    echo -e "${RED}✗ Admin users endpoint failed${NC}"
fi

echo ""

# Test admin analytics endpoint
echo "6. Testing admin analytics endpoint..."
analytics_response=$(curl -s http://localhost:5000/api/admin/analytics \
    -H "Authorization: Bearer $TOKEN")

if [[ $analytics_response == *"totalOrders"* ]]; then
    echo -e "${GREEN}✓ Admin analytics endpoint working${NC}"
else
    echo -e "${RED}✗ Admin analytics endpoint failed${NC}"
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo ""
echo "API Server: http://localhost:5000"
echo "Dashboard: http://localhost:5001"
echo ""
echo "Next steps:"
echo "1. Start dashboard: cd ~/AndroidStudioProjects/admin-dashboard-frizzly && python app_api.py"
echo "2. Open browser: http://localhost:5001"
echo "3. Login with: admin@frizzly.com / admin123"
echo ""
