# Deploy to Google Cloud Run (Firebase's Backend)

## Why Cloud Run?
- Integrated with Firebase
- Free tier: 2M requests/month
- Auto-scales to zero (no cost when idle)
- Supports Docker containers

## Setup

### 1. Install Google Cloud SDK
```bash
curl https://sdk.cloud.google.com | bash
gcloud init
```

### 2. Enable Cloud Run API
```bash
gcloud services enable run.googleapis.com
```

### 3. Build and Deploy
```bash
# Set your project ID
gcloud config set project YOUR_FIREBASE_PROJECT_ID

# Deploy
gcloud run deploy frizzly-admin \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars FLASK_SECRET_KEY=your-secret-key
```

### 4. Add Service Account
```bash
# Create secret
echo '{"type":"service_account",...}' > /tmp/key.json
gcloud secrets create firebase-key --data-file=/tmp/key.json

# Grant access
gcloud run services update frizzly-admin \
  --update-secrets=/etc/secret/serviceAccountKey.json=firebase-key:latest
```

### 5. Access
Your app will be at: `https://frizzly-admin-XXXXX-uc.a.run.app`

## Cost
- **Free tier:** 2M requests, 360,000 GB-seconds, 180,000 vCPU-seconds/month
- **After free tier:** ~$0.00002 per request
- **Typical usage:** $0-5/month for small apps

## Limitations
- Cold starts (~2-5 seconds)
- Max 60 min request timeout
- WebSockets work but keep container running (costs more)

## Recommendation
**Stick with Render.com** - it's simpler and truly free for your use case.
