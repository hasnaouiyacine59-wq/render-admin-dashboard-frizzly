#!/bin/bash

# Test notification sender
# Usage: ./test_send_notification.sh <user_id> <title> <message>

USER_ID="${1:-test_user}"
TITLE="${2:-Test Notification}"
MESSAGE="${3:-This is a test notification from admin dashboard}"

echo "📨 Sending test notification..."
echo "User ID: $USER_ID"
echo "Title: $TITLE"
echo "Message: $MESSAGE"
echo ""

curl -X POST http://localhost:5001/users/send-test-notification \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "user_id=$USER_ID&title=$TITLE&message=$MESSAGE" \
  -v

echo ""
echo ""
echo "📱 Check phone for notification!"
echo "📊 Monitor logs: adb logcat -s FrizzlyFCM:D"
