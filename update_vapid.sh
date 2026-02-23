#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: ./update_vapid.sh 'YOUR_VAPID_KEY'"
    exit 1
fi

VAPID_KEY="$1"

echo "Updating base.html with VAPID key..."

# Update base.html
sed -i "s/vapidKey: 'YOUR_VAPID_KEY'/vapidKey: '$VAPID_KEY'/g" ~/AndroidStudioProjects/admin-dashboard-frizzly/templates/base.html

echo "✅ VAPID key updated!"
echo ""
echo "Now restart your dashboard:"
echo "  cd ~/AndroidStudioProjects/admin-dashboard-frizzly"
echo "  python3 app_api.py"
