# RelayShield B2A API — Setup Guide

## What you're building

| Layer | What |
|---|---|
| Lambda | `relayshield-api` — handles all 5 endpoints |
| API Gateway | REST API with Lambda proxy integration |
| API Keys | Per-customer keys with usage plans (rate + quota limits) |
| RapidAPI | Public developer marketplace listing |

---

## Step 1 — Deploy the Lambda

### 1a. Zip and upload

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle"
zip relayshield_api.zip relayshield_api.py
```

**AWS Console → Lambda → Create function**
- Name: `relayshield-api`
- Runtime: Python 3.12
- Architecture: x86_64
- Execution role: same role as your other RelayShield Lambdas (already has Secrets Manager + DynamoDB access)

Upload `relayshield_api.zip`, set handler to `relayshield_api.lambda_handler`.

### 1b. Configuration

| Setting | Value |
|---|---|
| Timeout | 60 seconds |
| Memory | 256 MB |
| Environment variables | none (all config via Secrets Manager) |

### 1c. Verify Secrets Manager access

The Lambda needs `secretsmanager:GetSecretValue` for:
- `relayshield/hibp_api_key`
- `relayshield/virustotal_api_key`
- `relayshield/twilio_account_sid`
- `relayshield/twilio_auth_token`
- `relayshield/google_safe_browsing`

Your existing Lambda IAM role already has this — no changes needed.

---

## Step 2 — Create the API Gateway REST API

**AWS Console → API Gateway → Create API → REST API** (not HTTP API — REST API has native API key support)

- Protocol: REST
- Create new API: New API
- API name: `relayshield-api`
- Endpoint type: Regional

### 2a. Create resources and methods

For each endpoint, create a resource and POST method:

**Resource structure:**
```
/v1
  /breach      POST
  /scan-url    POST
  /scan-file   POST
  /sim-swap    POST
  /domain      POST
```

**To create `/v1/breach` (repeat for all 5):**

1. Select the root `/` → Actions → Create Resource
   - Resource name: `v1`, Resource path: `v1`
2. Select `/v1` → Actions → Create Resource
   - Resource name: `breach`, Resource path: `breach`
3. Select `/v1/breach` → Actions → Create Method → POST
   - Integration type: Lambda Function
   - Use Lambda Proxy integration: ✅ **checked**
   - Lambda Region: us-east-1 (or your region)
   - Lambda Function: `relayshield-api`
4. Click Save, then OK when prompted to add Lambda permission

Repeat step 3 for: `/v1/scan-url`, `/v1/scan-file`, `/v1/sim-swap`, `/v1/domain`

### 2b. Enable API Key Required on each method

For each POST method:
1. Click the method → Method Request
2. API Key Required: `true`

Do this for all 5 POST methods.

### 2c. Deploy the API

Actions → Deploy API
- Deployment stage: [New Stage]
- Stage name: `prod`

Copy the **Invoke URL** — it looks like:
`https://abc12345.execute-api.us-east-1.amazonaws.com/prod`

---

## Step 3 — Create Usage Plans and API Keys

### 3a. Create the usage plan

**API Gateway → Usage Plans → Create**

| Plan | Rate limit | Burst | Monthly quota | Price |
|---|---|---|---|---|
| `relayshield-starter` | 10 req/sec | 20 | 5,000/month | Free / low tier |
| `relayshield-growth`  | 50 req/sec | 100 | 50,000/month | $99/month |
| `relayshield-pro`     | 200 req/sec | 500 | Unlimited | $299/month |

For now, create one plan: `relayshield-growth`
- Throttling: Rate = 50, Burst = 100
- Quota: 50,000 requests per month

Add API Stage:
- API: `relayshield-api`
- Stage: `prod`

### 3b. Create a test API key

**API Gateway → API Keys → Create API Key**
- Name: `relayshield-test-key`
- Auto Generate: ✅

Then: **API Keys → relayshield-test-key → Usage Plans → Add to Plan**
- Select `relayshield-growth`

### 3c. Test the API

```bash
# Replace with your actual values
API_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
API_KEY="YOUR_API_KEY"

# Test breach check
curl -X POST "$API_URL/v1/breach" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Test SIM swap check
curl -X POST "$API_URL/v1/sim-swap" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"phone": "+14155551234"}'

# Test domain scan
curl -X POST "$API_URL/v1/domain" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain": "yourcompany.com"}'

# Test URL scan
curl -X POST "$API_URL/v1/scan-url" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://google.com"}'
```

---

## Step 4 — RapidAPI Listing

RapidAPI is the fastest path to developer distribution — no approval queue, no commission on free tiers, listing live within hours.

### 4a. Sign up

Go to **rapidapi.com/provider** and create a provider account. Use your business email.

### 4b. Create a new API listing

Provider Dashboard → My APIs → Add New API

- API Name: `RelayShield Security Intelligence`
- Description: Use the pitch from the OpenAPI spec description
- Category: Data → Security
- Visibility: Public

### 4c. Configure the base URL

Settings → Configure:
- Base URL: `https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod`
- Header forwarding: add `x-api-key` mapped to your RapidAPI-managed key

RapidAPI will proxy requests and inject your `x-api-key` header automatically. Create a dedicated API key in API Gateway for RapidAPI (don't reuse the test key) and paste it in the RapidAPI dashboard.

### 4d. Import endpoints from OpenAPI spec

API Definition tab → Import OpenAPI → upload `relayshield_api_openapi.yaml`

RapidAPI will auto-generate the endpoint documentation and test console.

### 4e. Set pricing tiers

Pricing tab:
| Plan | Price | Quota |
|---|---|---|
| Basic | Free | 100 calls/month |
| Growth | $29/month | 5,000 calls/month |
| Pro | $99/month | 25,000 calls/month |
| Ultra | $299/month | Unlimited |

Set overage pricing: $0.02 per call above quota.

### 4f. Publish

Settings → Visibility → Public → Save

Your listing will be live at:
`rapidapi.com/relayshield/relayshield-security-intelligence`

---

## Step 5 — Per-Endpoint Pricing Reference (B2A)

For direct API integrations (enterprise, MCP, MSP) outside RapidAPI:

| Endpoint | What it calls | Per-call cost |
|---|---|---|
| `/v1/breach` | HIBP v3 | $0.01 |
| `/v1/scan-url` | VirusTotal URL | $0.03 |
| `/v1/scan-file` | VirusTotal binary | $0.05 |
| `/v1/sim-swap` | Twilio Lookup v2 | $0.02 |
| `/v1/domain` | DNS + CT + GSB | $0.02 |

---

## Quick reference — Secret names required

All secrets already exist in AWS Secrets Manager from prior deployments:

| Secret | Key inside JSON |
|---|---|
| `relayshield/hibp_api_key` | `HIBP_API_KEY` |
| `relayshield/virustotal_api_key` | `virustotal_api_key` |
| `relayshield/twilio_account_sid` | `TWILIO_ACCOUNT_SID` |
| `relayshield/twilio_auth_token` | `TWILIO_AUTH_TOKEN` |
| `relayshield/google_safe_browsing` | `google_safe_browsing_api_key` |
