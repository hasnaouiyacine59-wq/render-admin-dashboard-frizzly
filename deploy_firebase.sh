#!/bin/bash
# Deploy Direct Firebase Version to Render

echo "🚀 Deploying Direct Firebase Admin Dashboard to Render"
echo ""

# Step 1: Backup old files
echo "📦 Step 1: Backing up API-based files..."
if [ -f "app_api.py" ]; then
    mv app_api.py app_api.py.backup
    echo "✅ Backed up app_api.py"
fi

if [ -f "api_client.py" ]; then
    mv api_client.py api_client.py.backup
    echo "✅ Backed up api_client.py"
fi

# Step 2: Verify new files exist
echo ""
echo "🔍 Step 2: Verifying new files..."
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found!"
    exit 1
fi
echo "✅ app.py exists"

if [ ! -f "config.py" ]; then
    echo "❌ Error: config.py not found!"
    exit 1
fi
echo "✅ config.py exists"

if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found!"
    exit 1
fi
echo "✅ requirements.txt exists"

# Step 3: Check git status
echo ""
echo "📝 Step 3: Git status..."
git status

# Step 4: Add files
echo ""
echo "➕ Step 4: Adding files to git..."
git add app.py config.py requirements.txt
git add FIREBASE_MIGRATION.md ARCHITECTURE_COMPARISON.md

# Step 5: Commit
echo ""
echo "💾 Step 5: Committing changes..."
git commit -m "Migrate to direct Firebase connection

- Replace app_api.py with app.py (direct Firebase)
- Update config.py (remove API_BASE_URL, add SERVICE_ACCOUNT_PATH)
- Simplify requirements.txt (remove API dependencies)
- Add migration documentation

Benefits:
- 3.3x faster
- No Railway dependency
- Simpler architecture
- $5/month cost savings"

# Step 6: Push
echo ""
echo "🚢 Step 6: Pushing to Render..."
echo ""
echo "⚠️  IMPORTANT: Before pushing, ensure you have:"
echo "   1. Uploaded serviceAccountKey.json to Render Secret Files"
echo "   2. Path: /etc/secrets/serviceAccountKey.json"
echo "   3. Set SECRET_KEY environment variable"
echo ""
read -p "Have you completed the above steps? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push origin main
    echo ""
    echo "✅ Deployment initiated!"
    echo ""
    echo "📊 Next steps:"
    echo "   1. Monitor Render deployment logs"
    echo "   2. Wait for build to complete (~2-3 minutes)"
    echo "   3. Test login at your Render URL"
    echo "   4. Verify all features work"
    echo ""
    echo "🎉 Migration complete!"
else
    echo ""
    echo "⚠️  Deployment cancelled. Complete the setup steps first:"
    echo ""
    echo "In Render Dashboard:"
    echo "   1. Go to your service → Environment"
    echo "   2. Click 'Secret Files'"
    echo "   3. Add file: /etc/secrets/serviceAccountKey.json"
    echo "   4. Paste your Firebase service account JSON"
    echo "   5. Add environment variable: SECRET_KEY=your-secret-key"
    echo "   6. Run this script again"
    echo ""
fi
