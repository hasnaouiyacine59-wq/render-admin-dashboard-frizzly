#!/bin/bash

# Start Gunicorn in the background
gunicorn --worker-class eventlet -w 2 --timeout 60 --bind 0.0.0.0:5000 app:app &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?