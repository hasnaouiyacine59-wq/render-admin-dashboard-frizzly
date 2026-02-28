#!/bin/bash

# Railway PostgreSQL Setup Script
# Run this after creating Railway PostgreSQL database

echo "🚀 Railway PostgreSQL Setup"
echo "=============================="
echo ""

# Check if DATABASE_URL is provided
if [ -z "$1" ]; then
    echo "❌ Error: DATABASE_URL required"
    echo ""
    echo "Usage: ./setup_railway.sh 'postgresql://user:pass@host:5432/db'"
    echo ""
    echo "Get DATABASE_URL from:"
    echo "1. Railway Dashboard → Your PostgreSQL → Variables tab"
    echo "2. Copy DATABASE_URL value"
    exit 1
fi

DATABASE_URL="$1"

echo "✅ DATABASE_URL provided"
echo ""

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo "📦 Installing PostgreSQL client..."
    sudo apt update && sudo apt install -y postgresql-client
fi

echo "✅ PostgreSQL client ready"
echo ""

# Initialize schema
echo "📊 Initializing database schema..."
psql "$DATABASE_URL" < postgres-sync/init.sql

if [ $? -eq 0 ]; then
    echo "✅ Schema initialized successfully!"
else
    echo "❌ Failed to initialize schema"
    exit 1
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Deploy sync service to Railway"
echo "2. Add environment variables to Render dashboard"
echo "3. See RAILWAY_SETUP.md for details"
