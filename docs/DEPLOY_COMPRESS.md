# Deploying the Brevitas Compression Service

This guide walks through deploying the LLMLingua-2 compression microservice to a cloud provider. We recommend **Render** as the most cost-effective option for CPU-only torch deployments.

## Platform Comparison & Pricing

| Platform | Config | Cost/Month | Billing | Cold Start | Status |
|----------|--------|-----------|---------|-----------|--------|
| **Render** (Recommended) | 2GB RAM, 1 CPU | **$25** | Fixed monthly | ~10-30s | ✓ Cheapest |
| Fly.io | 2GB RAM, 1 CPU | ~$32-60 | Pay-as-you-go | ~5-10s | Usage varies |
| Railway | 2GB RAM, 1 CPU | ~$40-50 | Usage-based | ~10-20s | More expensive |

**Recommendation**: Use **Render** for:
- Lowest fixed monthly cost ($25)
- Predictable billing (no surprise overages)
- Native Docker support
- Built-in health checks
- Simple GitHub integration

## Important Notes

- **Image Size**: The Docker image is ~3-4GB including torch CPU dependencies. Cold start on first request loads the LLMLingua-2 model (~10-30s).
- **RAM**: 2GB minimum required for torch + model. Lower RAM may cause OOM errors during model loading.
- **CPU**: Single shared CPU sufficient for LLMLingua-2 (bert-base is not GPU-optimized).
- **Storage**: Includes 5GB persistent volume for model cache and logs.
- **Authentication**: `BREVITAS_COMPRESS_TOKEN` is optional; set if you want to require a bearer token on requests.

---

## Option 1: Deploy to Render (Recommended)

Render is the cheapest and easiest option for this workload.

### Prerequisites

- GitHub account with access to the brevitas-systems repository
- Render account (free signup at https://render.com)

### Step 1: Connect GitHub to Render

1. Go to https://render.com and sign up or log in
2. Click **"New +"** → **"Web Service"**
3. Click **"Connect a repository"**
4. Authorize Render to access your GitHub account
5. Select the `brevitas-systems` repository

### Step 2: Configure the Service

After selecting the repository, Render shows a configuration form:

- **Name**: `brevitas-compress` (or your preferred name)
- **Environment**: `Docker`
- **Region**: Choose closest to you (e.g., `oregon` for US West, `frankfurt` for EU)
- **Branch**: `main`
- **Dockerfile Path**: `services/compress/Dockerfile` ← **Important**

Under **Advanced**:
- **Instance Type**: Standard (2GB RAM, 1 CPU) — $25/month
- **Health Check Path**: `/health`
- **Health Check Protocol**: HTTP

### Step 3: Add Environment Variables

If using optional authentication:

- Key: `BREVITAS_COMPRESS_TOKEN`
- Value: _(leave blank for no auth, or set to a secret string)_

If you leave it blank, the `/v1/optimize` endpoint will accept requests without a token.

### Step 4: Deploy

1. Scroll to the bottom and click **"Create Web Service"**
2. Render builds and deploys automatically
   - Build time: ~3-5 minutes (downloading torch, installing dependencies)
   - First request: ~10-30s (model loading)
3. Once deployed, you'll see a public URL like `https://brevitas-compress-xxxx.onrender.com`

### Step 5: Configure Your Client

Set environment variables on your client machine:

```bash
export BREVITAS_COMPRESS_URL="https://brevitas-compress-xxxx.onrender.com"
# Optional: if you set BREVITAS_COMPRESS_TOKEN above
export BREVITAS_COMPRESS_TOKEN="your-secret-token"
```

Then use the pip client:

```bash
pip install brevitas-client  # or your package name
python -c "
from brevitas_client import CompressClient
client = CompressClient()
result = client.optimize('Your long prompt here...', rate=0.5)
print(result)
"
```

### Monitoring

- **Logs**: Render dashboard → Web Service → Logs
- **Health**: Render dashboard → Metrics
- **Cold Starts**: Model loads on first request after idle period (~5-10s if machine stays warm)

### Cost Breakdown (Monthly)

- Web service (2GB RAM, 1 CPU): **$25.00**
- Persistent disk (5GB): Included
- **Total: $25/month**

---

## Option 2: Deploy to Fly.io

Alternative for users who prefer pay-as-you-go pricing.

### Prerequisites

- Fly.io account (free signup at https://fly.io)
- Fly CLI installed: `curl -L https://fly.io/install.sh | sh`
- GitHub access

### Step 1: Initialize Fly App

```bash
cd /path/to/brevitas-systems
fly auth login
fly launch
```

When prompted:
- **App name**: `brevitas-compress` (or your choice)
- **Region**: Choose closest to you (e.g., `sjc` for San Francisco)
- **Deploy now?**: No (we'll customize first)

### Step 2: Configure fly.toml

The repo includes `deploy/fly.toml`. Copy it to the root:

```bash
cp deploy/fly.toml ./fly.toml
```

Or edit `fly.toml` manually:

```toml
[http_service]
  internal_port = 8080
  force_https = false

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 2048

[checks]
  [checks.http]
    grace_period = "40s"
    interval = "30s"
    method = "GET"
    path = "/health"
```

### Step 3: Set Environment Variables

```bash
fly secrets set BREVITAS_COMPRESS_TOKEN=your-secret-token
# Leave unset if no token required
```

### Step 4: Deploy

```bash
fly deploy
```

Deployment takes ~5-10 minutes. Once done, your service is at `https://brevitas-compress.fly.dev` (or `https://<app-name>.fly.dev`).

### Cost Breakdown (Monthly, 24/7 Running)

- Machine (2GB RAM, shared CPU): ~$0.0447/hr = **~$32/month**
- Bandwidth (outbound, if any): $0.02/GB
- **Estimated total: $35-50/month** (depending on traffic)

---

## Option 3: Deploy to Railway

Alternative if you prefer a managed platform with integrated databases.

### Prerequisites

- Railway account (free signup at https://railway.app)
- GitHub connected to Railway

### Step 1: Create New Project

1. Go to https://railway.app and log in
2. Click **"+ New Project"**
3. Click **"Deploy from GitHub repo"**
4. Select `brevitas-systems` repository

### Step 2: Add Service

1. Click **"Add a service"** → **"GitHub repo"**
2. Configure:
   - **Name**: `compress`
   - **Service**: Select `brevitas-systems`
   - **Dockerfile path**: `services/compress/Dockerfile`
   - **Port**: `8080`

### Step 3: Configure Resources

In the Service settings:
- **Memory**: 2GB (sufficient for torch)
- **CPU**: 1 vCPU

### Step 4: Add Environment Variables

```
BREVITAS_COMPRESS_TOKEN=your-secret-token  # optional
```

### Step 5: Deploy

Railway auto-deploys. Once live, you'll get a public URL.

### Cost Breakdown (Monthly)

- CPU (1 vCPU, 24/7): $20
- Memory (2GB, 24/7): $20
- **Base total: $40/month** (before egress charges)

---

## Testing Your Deployment

Once deployed, test the service:

```bash
# Health check
curl https://brevitas-compress-xxxx.onrender.com/health

# Compression (no auth)
curl -X POST https://brevitas-compress-xxxx.onrender.com/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "This is a long prompt that needs compression. " * 100,
    "rate": 0.5
  }'

# With optional token auth
curl -X POST https://brevitas-compress-xxxx.onrender.com/v1/optimize \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "...", "rate": 0.5}'
```

Expected response:
```json
{
  "compressed": "Shorter version of the prompt...",
  "ratio": 0.48,
  "original_tokens": 2050,
  "compressed_tokens": 987
}
```

---

## Scaling & Optimization

### If You Need Better Performance

- **Render Pro plan** ($85/month): 4GB RAM, 2 CPU
- **Fly.io performance-2x**: 4GB RAM, 2 CPU (~$0.0894/hr)
- **Railway with GPU**: Add a GPU worker (not recommended for bert-base; CPU is sufficient)

### If You Need Auto-Scaling

- **Fly.io**: Scales machines automatically; pay only for what runs
- **Render**: Single instance; scaling requires paid plan upgrade
- **Railway**: Auto-scaling with usage-based billing

### Cost Control

For cost-sensitive setups:
1. **Use Render** ($25 fixed) for predictable monthly cost
2. **Scale down**: Use smaller configs temporarily (Fly allows scaling to 512MB for testing)
3. **Monitor**: Check dashboard regularly for unexpected spikes
4. **Set budgets**: Railway and Fly support spending alerts

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **Model loading timeout** | First request takes >30s | Increase health check `grace_period` to 60s; model caches after first load |
| **OOM errors** | 2GB insufficient | Upgrade to 4GB RAM plan |
| **High latency** | Model inference slow | bert-base CPU inference is 1-3s/request; this is normal |
| **Service won't start** | Docker build fails | Check logs; ensure `services/compress/Dockerfile` exists and uses Python 3.11 |
| **Token validation fails** | Bearer token mismatch | Verify `BREVITAS_COMPRESS_TOKEN` env var matches client request header |

---

## Pricing Sources

- [Render Pricing](https://render.com/pricing) — $25/month Standard plan
- [Fly.io Pricing](https://fly.io/pricing/) — $0.0447/hr for 2GB performance-1x
- [Railway Pricing](https://railway.com/pricing) — $20 CPU + $10 RAM per GB/month

---

## Notes

- **You own the deployment**: These configs and credentials are yours to manage. Back up your cloud provider credentials.
- **Image rebuild**: After code changes to `services/compress/`, trigger a rebuild in your cloud provider's dashboard (auto if using GitHub integration).
- **Model updates**: LLMLingua-2 model is cached in the image; to update, rebuild the Docker image.
- **Security**: Store `BREVITAS_COMPRESS_TOKEN` in your cloud provider's secrets manager, never in code.

