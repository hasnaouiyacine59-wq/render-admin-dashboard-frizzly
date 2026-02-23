#!/bin/bash

echo "🚀 Starting FRIZZLY Admin Dashboard..."
echo ""

# Check if serviceAccountKey.json exists
if [ ! -f "serviceAccountKey.json" ]; then
    echo "❌ Error: serviceAccountKey.json not found!"
    echo "Please copy your Firebase credentials to this folder."
    exit 1
fi

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install flask flask-login firebase-admin werkzeug
fi

# Kill any existing Flask process on port 5000
echo "🔍 Checking for existing processes..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || true

# Start the dashboard
echo "✅ Starting dashboard on http://localhost:5000"
echo ""
echo "Login credentials:"
echo "  Email: admin@frizzly.com"
echo "  Password: admin123"
echo ""
echo "Press Ctrl+C to stop the server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 app.py &
celery -A celery_worker worker --loglevel=info &

wait -n

exit $?
