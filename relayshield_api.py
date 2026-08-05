"""
RelayShield B2A API Lambda

Exposes RelayShield security intelligence as REST endpoints for
Business-to-Agent (B2A) and third-party developer consumption.

Subscription endpoints (API key required — enforced by API Gateway usage plan):
  POST /v1/breach                   — HIBP email breach check
  POST /v1/scan-url                 — VirusTotal URL malware analysis
  POST /v1/scan-file                — VirusTotal binary/file analysis
  POST /v1/scan-wallet              — GoPlus EVM wallet risk scan (legacy)
  POST /v1/wallet-risk              — Multi-chain wallet risk: EVM/Solana/TON/Bitcoin (auto-detect)
  POST /v1/token-security           — GoPlus token risk: honeypot, tax, ownership flags
  POST /v1/nft-security             — GoPlus NFT contract risk scan
  POST /v1/sim-swap                 — Twilio Lookup v2 SIM/eSIM swap detection
  POST /v1/domain                   — Typosquat/lookalike domain scan (DNS + CT + GSB)
  POST /v1/intel/telegram           — Threat Intelligence API: IOC lookup against live Telegram criminal channel pipeline (intel_access flag required)
  POST /v1/metered/supply-chain     — Vendor/supply chain risk: breach + infostealer exposure per domain (up to 10 domains)
  POST /v1/metered/session-risk     — INTEL-5 active session hijack detection from stealer log corpus
  GET  /v1/result/{analysis_id}     — Poll VT scan result

Pay-as-you-go endpoints (no API key — x402 payment verified in Lambda):
  POST /v1/payg/breach              — $0.10 USDC
  POST /v1/payg/sim-swap            — $0.25 USDC
  POST /v1/payg/domain              — $0.50 USDC
  POST /v1/payg/oauth-watchlist     — $0.15 USDC
  POST /v1/payg/scan-wallet         — $0.10 USDC (legacy EVM-only)
  POST /v1/payg/scan-url            — $0.05 USDC
  POST /v1/payg/scan-file           — $0.10 USDC
  POST /v1/payg/wallet-risk         — $0.15 USDC — multi-chain EVM/Solana/TON/Bitcoin
  POST /v1/payg/token-security      — $0.10 USDC — token honeypot + tax analysis
  POST /v1/payg/nft-security        — $0.10 USDC — NFT contract risk
  POST /v1/payg/wallet-screen-batch — $0.50 USDC — batch up to 10 addresses
  POST /v1/payg/infostealer         — $0.15 USDC — Hudson Rock infostealer detection
  POST /v1/payg/supply-chain        — $0.10 USDC per domain — vendor breach + infostealer risk (up to 10 domains)
  POST /v1/payg/session-risk        — $0.30 USDC — INTEL-5 active session hijack / AiTM detection
  POST /v1/payg/tech-stack-cve      — $0.20 USDC — CVE targeting risk by declared tech stack
  POST /v1/payg/bulk-identity-risk  — $2.00 USDC — hierarchical org + per-agent-email risk scoring
  GET  /v1/payg/result/{id}         — $0.00 (free — poll a paid scan)

x402 payment flow:
  1. Call PAYG endpoint with no X-PAYMENT header → receive 402 + PAYMENT-REQUIRED header
  2. Pay USDC on Base to the address in PAYMENT-REQUIRED
  3. Retry with X-PAYMENT header containing payment proof
  4. Lambda verifies proof via PayAI x402 facilitator → executes and returns result

Authentication: Subscription routes — API key enforced by API Gateway usage plan.
               PAYG routes — no API key; x402 payment verified inside this Lambda.

Environment variables (set on Lambda):
  RELAYSHIELD_X402_WALLET — Coinbase Exchange USDC deposit address (x402 payTo)

Secrets used (all in Secrets Manager):
  relayshield/hibp_api_key
  relayshield/virustotal_api_key
  relayshield/twilio_account_sid / twilio_auth_token
  relayshield/google_safe_browsing
"""

import base64
import bisect as _bisect
import concurrent.futures
from decimal import Decimal
import json
import html
import logging
import os
import random
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta

import boto3

# Local module — pure data, no AWS dependencies. MUST be included in this
# function's deployment zip; without it every invocation dies at import with
# Runtime.ImportModuleError. See .claude/skills/relayshield-deploy step 3.
import relayshield_openapi_spec

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client  = boto3.client("secretsmanager")
dynamodb        = boto3.resource("dynamodb")
kms_client      = boto3.client("kms")

KMS_DATA_KEY    = "alias/relayshield-data-key"


def _kms_encrypt(value: str) -> str:
    """KMS-encrypt a plaintext string. Returns base64-encoded ciphertext."""
    resp = kms_client.encrypt(KeyId=KMS_DATA_KEY, Plaintext=value.encode("utf-8"))
    return base64.b64encode(resp["CiphertextBlob"]).decode("utf-8")


def _kms_decrypt(ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded KMS ciphertext. Returns plaintext string."""
    raw = base64.b64decode(ciphertext_b64)
    return kms_client.decrypt(CiphertextBlob=raw)["Plaintext"].decode("utf-8")


def _sha256(value: str) -> str:
    """SHA-256 hash of a normalised string — used as queryable index key for PII fields."""
    import hashlib
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
ses             = boto3.client("ses", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# x402 PAYG configuration
X402_PAYTO_ADDRESS   = os.environ.get("RELAYSHIELD_X402_WALLET", "")   # EVM (Base) payTo
SOL_PAYTO_ADDRESS    = os.environ.get("RELAYSHIELD_SOL_WALLET", "")    # Solana payTo

# Alchemy / Helius — backend proxy (keys never sent to client)
ALCHEMY_API_KEY   = os.environ.get("ALCHEMY_API_KEY", "")
ALCHEMY_AUTH_TOKEN = os.environ.get("ALCHEMY_AUTH_TOKEN", "")
HELIUS_API_KEY    = os.environ.get("HELIUS_API_KEY", "")
# Crypto Shield App NFT (Solana dApp Store). Release NFTs group under this.
# LEGACY as of 2026-08-01 — kept only as a fallback. See CS_MOBILE_PUBLISHER.
CS_MOBILE_APP_NFT = "FNg9dzf1JjJ9D8G1i7o1L7KL6ztpLADVQAeonwT5KaDo"

# The publisher's on-chain signing identity — the authority and verified creator
# of the App NFT and every Release NFT under it.
#
# The latest-version lookup keys off THIS rather than off the App NFT, because
# the App NFT is not stable: certificate rotation is unsupported by the dApp
# Store, so shipping v1.5.0 required a brand-new app record under a new package
# name, which mints a brand-new App NFT. Anything pinned to the old App NFT would
# silently stop seeing new releases the moment that happened — the update nudge
# would never fire again, which is the exact failure v1.5.0 exists to fix.
#
# The publisher account carries over across app records (confirmed by Solana
# Mobile support 2026-07-30), so this address survives the rename and any future
# one. Verified live 2026-08-01: getAssetsByAuthority returns the App NFT plus
# all 5 Release NFTs (v1.2.0, v1.3.0 x2, v1.4.0, v1.5.0).
CS_MOBILE_PUBLISHER = "E64PiTT7U8ZUWFKdkrBFw1YzdD2bU1gKcuGnBRVqp7M6"

# Release NFTs are named "<app name> vX.Y.Z". Requiring the prefix keeps a future
# second app by the same publisher from being mistaken for a Crypto Shield release;
# requiring a version excludes the App NFT itself, which carries no version.
CS_MOBILE_RELEASE_PREFIX = "Crypto Shield"
X402_FACILITATOR_URL = "https://facilitator.payai.network"   # EVM (Base) — PayAI facilitator; auto-listed in Bazaar, free tier 10k/month
SOL_FACILITATOR_URL  = "https://facilitator.payai.network"    # Solana — PayAI (same facilitator as Base; x402.org was a testnet facilitator with no Bazaar support, confirmed 2026-07-10)

# CDP (Coinbase Developer Platform) facilitator — preferred over PayAI when
# configured. Added 2026-07-11: CDP's own Bazaar is the discovery registry
# AWS surfaces through Bedrock AgentCore's gateway, so routing settlements
# through CDP is what actually makes these endpoints reachable by any
# AgentCore-built agent, not just a nice-to-have second facilitator.
CDP_API_KEY_ID       = os.environ.get("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET   = os.environ.get("CDP_API_KEY_SECRET", "")
CDP_FACILITATOR_HOST = "api.cdp.coinbase.com"
CDP_FACILITATOR_URL  = f"https://{CDP_FACILITATOR_HOST}/platform/v2/x402"

USDC_BASE_ADDRESS    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"   # USDC on Base
USDC_SOL_ADDRESS     = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" # USDC on Solana mainnet
BASE_CHAIN_ID        = "base"           # V1 named network
BASE_CHAIN_ID_V2     = "eip155:8453"     # V2 CAIP-2 format — Base mainnet
SOL_CHAIN_ID         = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"       # Solana mainnet CAIP-2 — same value in V1 and V2
# CDP Facilitator Solana fee-payer public key (sponsors gas for all SVM x402 transactions)
SOL_FEE_PAYER        = "EwWqGE4ZFKLofuestmU4LDdK7XM1N4ALgdZccwYugwGd"

# x402 V2 staged migration (TODO.md item 50) — empty by default, everything
# stays on V1. Add paths in small batches (3-4 at a time) as each batch is
# funded, settled, and confirmed re-indexed in CDP's Bazaar before the next.
# Batch 1 (2026-07-14): breach/domain/sim-swap TEMPORARILY REVERTED to V1
# 2026-07-14 — their Bazaar entries stayed stale/V1-shaped after real V2
# settlements (confirmed via CDP's discovery search + an isolated solo-
# settlement test that ruled out batching/debounce as the cause), meaning any
# real agent trusting Bazaar's cached data right now would build a payment
# against the wrong shape. Reverting closes that exposure until the stale-
# indexing cause is understood. supply-chain stays on V2 — its Bazaar entry
# is confirmed correctly updated.
#
# domain: second attempt at a fix, 2026-07-16 — corrected paymentPayload
# .resource shape (proper ResourceInfo object, confirmed against the real
# x402 SDK schema, not the broken bare-string first attempt) settled
# successfully end-to-end (real tx 0x092f86d5b82dc1c8a5cca2c63d847f4ac8ce
# 47bb0474960849aaf874dde31799, payer 0xa26054A..., confirmed on Base).
# Checked CDP's Bazaar discovery search immediately after: domain's
# quality.lastCalledAt is STILL frozen at 2026-07-12T14:03:38.196Z,
# completely unchanged, and the entry is still indexed under the old V1
# shape (x402Version: 1). This rules out Ethan Oroshiba's "missing
# paymentPayload.resource" diagnosis (x402-foundation/x402#2814) as the
# actual fix — it's schema-correct and settles fine, but CDP's own
# tracking for this specific resource genuinely does not move. Matches
# the original investigation's conclusion better: a CDP-side stuck
# record, not a payload-shape problem. Reverted back to V1 — V2 gives no
# benefit here and only adds a real vs-indexed shape mismatch.
X402_V2_ENABLED_PATHS: set[str] = {
    "/v1/payg/supply-chain",
    # Batch B (CDPX-7), added 2026-07-17 — no prior V2 attempt/failure history.
    # Froze at pre-migration lastCalledAt for ~1 day, then self-resolved with
    # no CDP-side fix — treating that lag as expected, not a permanent break.
    "/v1/payg/target-risk",
    "/v1/payg/wallet-screen-batch",
    "/v1/payg/oauth-watchlist",
    "/v1/payg/tech-stack-cve",
    # Batch C (CDPX-7), added 2026-07-18.
    "/v1/payg/identity-risk-score",
    "/v1/payg/secret-scan",
    "/v1/payg/session-risk",
    "/v1/payg/nhi-exposure",
    # LLMjacking (added 2026-07-26) — dedicated LLM/AI provider credential
    # exposure check, filtered subset of nhi-exposure's detection.
    "/v1/payg/llm-credential-exposure",
    # Batch A (CDPX-7), added 2026-07-19 — held pending Batch C resolution,
    # resumed once both of Batch C's open patterns cleared.
    "/v1/payg/bulk-identity-risk",
    # Batch E (CDPX-7), added 2026-07-20 — no prior V2 attempt/failure history.
    "/v1/payg/identity-graph",
    "/v1/payg/ransomware-risk",
    # Batch D (CDPX-7), added 2026-07-20 — no prior V2 attempt/failure history.
    "/v1/payg/wallet-risk",
    "/v1/payg/token-security",
    "/v1/payg/scan-url",
    "/v1/payg/nft-security",
    "/v1/payg/scan-file",
    "/v1/payg/scan-wallet",
    "/v1/payg/infostealer",
    # Roadmap additions (competitive benchmark, CDPX-7 era), added 2026-07-21.
    "/v1/payg/cert-expiry",
    "/v1/payg/ip-intel",
    # Phase 2 trio (CDPX-7), added 2026-07-21 — held back since 2026-07-15
    # after 2 prior failed real-money cataloging attempts on `domain`
    # specifically. Every other batch (A/B/C/D/E) has since resolved cleanly
    # within ~11-24hrs, so retrying now with that established precedent.
    "/v1/payg/domain",
    "/v1/payg/breach",
    "/v1/payg/sim-swap",
}

# PAYG pricing in USDC base units (6 decimals): $0.10 = 100000
PAYG_PRICE_UNITS: dict[str, int] = {
    "/v1/payg/breach":                100000,
    "/v1/payg/sim-swap":              250000,
    "/v1/payg/domain":                500000,
    "/v1/payg/oauth-watchlist":       300000,   # $0.30 — combined HIBP watchlist + INTEL-5 stealer corpus (premium positioning vs SpyCloud)
    "/v1/payg/scan-wallet":           100000,   # legacy — EVM only
    "/v1/payg/scan-url":               50000,
    "/v1/payg/scan-file":             100000,
    # Crypto Shield intelligence endpoints
    "/v1/payg/wallet-risk":           50000,    # $0.05 — multi-chain EVM/Solana/TON (teaser price, CDPX-3)
    "/v1/payg/token-security":        50000,    # $0.05 — GoPlus token risk (teaser price, CDPX-3)
    "/v1/payg/nft-security":          100000,   # $0.10 — GoPlus NFT risk
    "/v1/payg/wallet-screen-batch":   500000,   # $0.50 — up to 10 addresses
    "/v1/payg/infostealer":           150000,   # $0.15 — Hudson Rock infostealer check
    "/v1/payg/supply-chain":          100000,   # $0.10 per call (up to 10 vendor domains)
    "/v1/payg/session-risk":          300000,   # $0.30 — INTEL-5 active session hijack / AiTM detection (premium)
    "/v1/payg/identity-graph":        350000,   # $0.35 — identity correlation: email → linked phones/domains from dumps
    "/v1/payg/ransomware-risk":       400000,   # $0.40 — ransomware victim list + pre-ransomware credential check
    "/v1/payg/nhi-exposure":          400000,   # $0.40 — non-human identity: API keys/tokens in stealer logs
    "/v1/payg/llm-credential-exposure": 400000,  # $0.40 — LLMjacking: exposed LLM/AI provider API keys
    "/v1/payg/secret-scan":           350000,   # $0.35 — 6-source public artifact secret detection (GitHub, npm, PyPI, Docker Hub, HF, Postman)
    "/v1/payg/secret-scan-text":       50000,   # $0.05 — local scan, no external API call (see METERED_CREDIT_COSTS)
    "/v1/payg/target-risk":           500000,   # $0.50 — target probability score (6-signal correlation)
    "/v1/payg/tech-stack-cve":        200000,   # $0.20 — CVE targeting risk by declared tech stack
    "/v1/payg/bulk-identity-risk":    2000000,  # $2.00 — hierarchical org + per-agent-email risk scoring
    "/v1/payg/identity-risk-score":   350000,   # $0.35 — domain security credit score (0-100), 6 dimensions
    "/v1/payg/cert-expiry":            50000,   # $0.05 — TLS cert expiry/renewal risk for your own domain (crt.sh, free source)
    "/v1/payg/ip-intel":              100000,   # $0.10 — passive DNS + IP reputation via VirusTotal
}

GOPLUS_BASE_URL        = "https://api.gopluslabs.io/api/v1/address_security"
GOPLUS_TOKEN_URL       = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
GOPLUS_NFT_URL         = "https://api.gopluslabs.io/api/v1/nft_security"
TONAPI_ACCOUNTS_URL    = "https://tonapi.io/v2/accounts/{address}"

# OAuth supply chain watchlist — high-risk OAuth-capable SaaS apps
OAUTH_WATCHLIST = {
    "slack", "notion", "github", "zapier", "linear", "vercel", "loom",
    "hubspot", "okta", "salesforce", "dropbox", "box", "atlassian", "jira",
    "confluence", "asana", "monday", "clickup", "figma", "miro",
    "zoom", "webex", "intercom", "zendesk", "freshdesk",
    "openai", "anthropic", "canva", "jasper", "grammarly", "copy.ai",
}

OAUTH_REVOCATION_URLS: dict[str, str] = {
    "GitHub":     "https://github.com/settings/applications",
    "Slack":      "https://slack.com/apps/manage",
    "Notion":     "https://www.notion.so/my-integrations",
    "Vercel":     "https://vercel.com/account/tokens",
    "Zapier":     "https://zapier.com/app/connections",
    "Linear":     "https://linear.app/settings/api",
    "HubSpot":    "https://app.hubspot.com/integrations-settings",
    "Dropbox":    "https://www.dropbox.com/account/connected_apps",
    "Atlassian":  "https://id.atlassian.com/manage-profile/apps",
    "Salesforce": "https://help.salesforce.com/s/articleView?id=sf.remoteaccess_revoke_token.htm",
}

API_KEYS_TABLE          = "relayshield_api_keys"
INTEL_IOCS_TABLE        = "relayshield_intel_iocs"
INTEL_CVE_TABLE         = "relayshield_intel_cve"
STOLEN_CARDS_TABLE      = "relayshield_stolen_cards"
ASSET_WATCHLIST_TABLE   = "relayshield_asset_watchlist"
ACTOR_WATCHLIST_TABLE   = "relayshield_actor_watchlist"
EXPLOIT_CHATTER_TABLE   = "relayshield_exploit_chatter"
SHARED_REPORTS_TABLE    = "relayshield_shared_reports"
FROM_EMAIL              = "noreply@relayshield.net"

# Quota warning thresholds for mp_499 (10,000 call/month) TI plan.
# We fire one email per threshold per billing period; flags are stored on the key record.
INTEL_WARN_80_CALLS = 8_000   # 80% — nudge to upgrade, still 2K calls left
INTEL_WARN_95_CALLS = 9_500   # 95% — urgent, 500 calls remaining
STRIPE_SECRET_NAME = "relayshield/stripe_secret_key"
STRIPE_METER_API   = "https://api.stripe.com/v1/billing/meter_events"

# Threat Intelligence API subscription tiers — monthly call caps.
# None = unlimited. Tier is provisioned automatically by relayshield-developer-signup
# on checkout.session.completed for the $499/$999 Payment Links.
# Defaults to the $499 cap if intel_plan_tier is unset — fails safe rather than
# granting unlimited access to an unverified key.
INTEL_PLAN_LIMITS: dict[str, int | None] = {
    "mp_499":    10000,   # $499/mo — 10,000 calls
    "mssp_999":  None,    # $999/mo — unlimited
}
INTEL_DEFAULT_TIER = "mp_499"

# Single aggregate Stripe Billing Meter, replacing the 29 per-endpoint meters
# for billing purposes on 2026-08-04. formula=sum over payload[value], where
# value is the call's price in CENTS, billed against a $0.01-per-unit price
# (price_1U0jLZL2dcjOeFiYG8VktTxK, meter mtr_61VA7IvTDjEhWKu9941L2dcjOeFiY7OS).
#
# One line item instead of 29 is not a nicety: Stripe Checkout rejects more
# than 20 recurring prices, and STRIPE_PRICE_IDS had reached 24, so developer
# signup had been returning HTTP 400 since 2026-06-24. See
# _record_stripe_meter_event for the full account.
STRIPE_USAGE_METER_EVENT = "relayshield_api_usage"

# Per-endpoint meter event names. NO LONGER USED FOR BILLING — kept because the
# meters still exist in Stripe with their historical data, and because
# relayshield_agentic_api.py's AWS Marketplace path still reads its own copy.
# METERED_CREDIT_COSTS is now the authoritative "is this endpoint billable"
# check; adding an entry here bills nothing on its own.
STRIPE_METER_EVENTS: dict[str, str] = {
    "/v1/metered/breach":           "relayshield_breach_calls",
    "/v1/metered/sim-swap":         "relayshield_sim_swap_calls",
    "/v1/metered/infostealer":      "relayshield_infostealer_calls",
    "/v1/metered/domain":           "relayshield_domain_calls",
    "/v1/metered/oauth-watchlist":  "relayshield_oauth_watchlist_calls",   # combined HIBP + INTEL-5
    "/v1/metered/crypto-intel":     "relayshield_crypto_intel_calls",
    "/v1/metered/supply-chain":     "relayshield_supply_chain_calls",
    "/v1/metered/session-risk":     "relayshield_session_risk_calls",
    "/v1/metered/identity-graph":   "relayshield_identity_graph_calls",
    "/v1/metered/ransomware-risk":  "relayshield_ransomware_risk_calls",
    "/v1/metered/nhi-exposure":     "relayshield_nhi_exposure_calls",
    "/v1/metered/llm-credential-exposure": "relayshield_llm_credential_exposure_calls",
    "/v1/metered/secret-scan":      "relayshield_secret_scan_calls",
    # Its OWN meter, not secret-scan's. Reusing secret-scan's meter looked like
    # it avoided creating Stripe objects, but _record_stripe_meter_event always
    # posts value:1 and that meter's only price is $0.35/unit -- so every
    # secret-scan-text call would have billed a Stripe-subscription developer
    # $0.35 instead of $0.05, a 7x overcharge. The credits and x402 rails were
    # correct; only the Stripe rail was wrong. Caught 2026-07-31 before launch.
    # Meter mtr_61V8daayOdgGiVieY41L2dcjOeFiYH16, price price_1TzFdML2dcjOeFiYHmUg2UK8.
    "/v1/metered/secret-scan-text": "relayshield_secret_scan_text_calls",
    "/v1/metered/target-risk":      "relayshield_target_risk_calls",
    "/v1/metered/asset-intel":      "relayshield_asset_intel_calls",
    "/v1/metered/threat-actor":     "relayshield_threat_actor_calls",
    "/v1/metered/cve-identity-risk":   "relayshield_cve_identity_risk_calls",
    "/v1/metered/identity-risk-score": "relayshield_identity_risk_score_calls",
    "/v1/metered/bulk-ioc":             "relayshield_bulk_ioc_calls",          # up to 100 IOC lookups per call
    "/v1/metered/ioc-pivot":           "relayshield_ioc_pivot_calls",         # related IOC discovery
    "/v1/metered/brand-monitor":       "relayshield_brand_monitor_calls",     # brand mention scan in IOC corpus
    "/v1/metered/bulk-identity-risk":  "relayshield_bulk_identity_risk_calls",# up to 10 domains + 5 agents each
    "/v1/metered/tech-stack-cve":      "relayshield_tech_stack_cve_calls",    # CVE targeting alert by declared tech stack
    "/v1/metered/cert-expiry":         "relayshield_cert_expiry_calls",       # TLS cert expiry/renewal risk (crt.sh)
    "/v1/metered/ip-intel":            "relayshield_ip_intel_calls",          # passive DNS + IP reputation (VirusTotal)
    "/v1/metered/card-exposure":       "relayshield_card_exposure_calls",     # BIN/stolen-card monitoring — CREATE METER IN DASHBOARD
}

# Credits deducted per successful call (1 credit = $0.01)
METERED_CREDIT_COSTS: dict[str, int] = {
    "/v1/metered/breach":          10,   # $0.10
    "/v1/metered/sim-swap":        25,   # $0.25
    "/v1/metered/infostealer":     50,   # $0.50
    "/v1/metered/domain":          30,   # $0.30
    "/v1/metered/oauth-watchlist": 30,   # $0.30 — combined HIBP watchlist + INTEL-5 stealer corpus (premium)
    "/v1/metered/crypto-intel":    30,   # $0.30
    "/v1/metered/supply-chain":    10,   # $0.10 per call (up to 10 vendor domains)
    "/v1/metered/session-risk":    30,   # $0.30 — INTEL-5 active session hijack / AiTM detection (premium)
    "/v1/metered/identity-graph":  35,   # $0.35 — identity correlation
    "/v1/metered/ransomware-risk": 40,   # $0.40 — ransomware victim + pre-ransomware credential check
    "/v1/metered/nhi-exposure":    40,   # $0.40 — NHI: API keys/tokens in stealer logs
    "/v1/metered/llm-credential-exposure": 40,   # $0.40 — LLMjacking: exposed LLM/AI provider API keys
    "/v1/metered/secret-scan":     35,   # $0.35 — 6-source public artifact secret detection (GitHub, npm, PyPI, Docker Hub, HF, Postman)
    "/v1/metered/secret-scan-text": 5,   # $0.05 — local pattern scan, no external API call.
                                         # Deliberately below secret-scan's $0.35: this is the
                                         # pre-commit path and fires on every commit, so parity
                                         # pricing would cost a 20-commit-a-day developer $7/day
                                         # and kill hook adoption, which is the entire point of
                                         # the endpoint. Confirm with founder before launch.
    "/v1/metered/target-risk":     50,   # $0.50 — 6-signal target probability correlation score
    "/v1/metered/asset-intel":      15,   # $0.15/call — asset watchlist register + sweep
    "/v1/metered/threat-actor":    30,   # $0.30/call — exploit chatter + actor/campaign lookup
    "/v1/metered/cve-identity-risk": 40,   # $0.40/call — CVE × identity signal composite risk
    "/v1/metered/identity-risk-score": 35, # $0.35/call — domain security credit score (0-100)
    "/v1/metered/bulk-ioc":             50,   # $0.50/batch — up to 100 IOC lookups (TC-competitor bulk enrichment)
    "/v1/metered/ioc-pivot":           20,   # $0.20/call — related IOC discovery by malware family / source
    "/v1/metered/brand-monitor":       35,   # $0.35/call — raised from $0.25 2026-07-24: now covers image/logo mentions too (text + domain + image corpus, RF/Intel471-competitor)
    "/v1/metered/bulk-identity-risk":  200,  # $2.00/call — up to 10 domains + 5 agents each (MSP sweep / OrcX agentic)
    "/v1/metered/tech-stack-cve":      20,   # $0.20/call — CVE targeting risk by declared tech stack
    "/v1/metered/cert-expiry":         5,    # $0.05/call — mirrors PAYG price, new endpoint 2026-07-21
    "/v1/metered/ip-intel":            10,   # $0.10/call — mirrors PAYG price, new endpoint 2026-07-21
    "/v1/metered/card-exposure":       30,   # $0.30/call — compromised-card lookup (Flashpoint/SOCRadar-competitor), new endpoint 2026-07-24
}

HIBP_SECRET_NAME  = "relayshield/hibp_api_key"
VT_SECRET_NAME    = "relayshield/virustotal_api_key"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOK_SECRET = "relayshield/twilio_auth_token"
GSB_SECRET_NAME   = "relayshield/google_safe_browsing"

HIBP_BASE_URL     = "https://haveibeenpwned.com/api/v3/breachedaccount/"
VT_BASE_URL       = "https://www.virustotal.com/api/v3"
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{phone}"
GSB_URL           = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
CRT_SH_URL        = "https://crt.sh/?q={domain}&output=json"

VT_POLL_INTERVAL  = 3    # seconds between VT status polls
VT_URL_MAX_WAIT   = 30   # max seconds for URL analysis
VT_FILE_MAX_WAIT  = 45   # max seconds for file analysis

# Typosquat generation config (mirrors domain_monitor)
COMMON_TLDS = [
    ".com", ".net", ".org", ".co", ".io", ".biz",
    ".info", ".us", ".co.uk", ".ca", ".com.au",
]
PHISHING_PREFIXES = ["secure-", "login-", "my-", "get-", "support-", "help-"]
PHISHING_SUFFIXES = ["-secure", "-login", "-online", "-support", "-portal", "-verify"]

# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}


def _get_secret(secret_name: str) -> str:
    if secret_name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        _secret_cache[secret_name] = raw
    return _secret_cache[secret_name]


def _get_secret_json(secret_name: str, key: str) -> str:
    raw = _get_secret(secret_name)
    try:
        return json.loads(raw)[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def _hibp_api_key() -> str:
    return _get_secret_json(HIBP_SECRET_NAME, "HIBP_API_KEY")


def _vt_api_key() -> str:
    return _get_secret_json(VT_SECRET_NAME, "virustotal_api_key")


def _twilio_creds() -> tuple[str, str]:
    sid   = _get_secret_json(TWILIO_SID_SECRET, "TWILIO_ACCOUNT_SID")
    token = _get_secret_json(TWILIO_TOK_SECRET, "TWILIO_AUTH_TOKEN")
    return sid, token


def _gsb_api_key() -> str:
    raw = _get_secret(GSB_SECRET_NAME)
    try:
        return json.loads(raw)["google_safe_browsing_api_key"]
    except (json.JSONDecodeError, KeyError):
        return raw


def _stripe_secret_key() -> str:
    raw = _get_secret(STRIPE_SECRET_NAME)
    try:
        return json.loads(raw).get("stripe_secret_key") or json.loads(raw).get("STRIPE_SECRET_KEY") or raw
    except (json.JSONDecodeError, KeyError):
        return raw


# ---------------------------------------------------------------------------
# Stripe metered billing helpers
# ---------------------------------------------------------------------------

def _verify_rs_api_key(api_key_str: str) -> dict | None:
    """Look up a RelayShield API key in DynamoDB. Returns the record or None.

    ConsistentRead=True (added 2026-07-17) — this gates a billing decision
    (credits/subscription check right after), so it must never see a stale
    pre-write copy of the record. Diagnosed live: a key record edited via
    the AWS CLI kept intermittently showing its pre-edit state (missing
    `source`/`active`) on the very next real request, then the correct
    state again moments later on a fresh read — classic default
    eventually-consistent GetItem staleness, not a second process
    overwriting the record."""
    if not api_key_str or not (api_key_str.startswith("rs_live_") or api_key_str.startswith("rs_demo_")):
        return None
    try:
        table  = dynamodb.Table(API_KEYS_TABLE)
        result = table.get_item(Key={"api_key": api_key_str}, ConsistentRead=True)
        item   = result.get("Item")
        if item and item.get("active"):
            return item
        return None
    except Exception as exc:
        logger.error("API key lookup failed key=%s error=%s", api_key_str[:16], exc)
        return None


# Daily call caps for shared demo keys embedded in public source (e.g. a pip
# package or public HF Space file). Unlike a server-side-only key such as
# "demo_portal" (used exclusively by the Cloudflare Worker TI demo, never
# visible to a browser), a key inside a published Python file is scrapable
# within hours of release — so it must be both rate-limited and low-privilege
# from the start, never reused from an existing unlimited demo key.
DEMO_QUOTA_TABLE   = "relayshield_demo_key_usage"
DEMO_QUOTA_SOURCES = {"hf_smolagents_demo": 20, "mcp_space_demo": 20}  # source -> shared daily cap, all callers combined

# Contract/address-reputation endpoints that accept calls with NO API key.
#
# This is deliberate, not an oversight: Crypto Shield Mobile's free tier runs
# these scans without a subscription (see FREE_SCAN_TYPES in the app), which is
# what makes a free-tier monitored wallet useful at all. The comment further down
# claiming "API key enforced by API Gateway" was never true in production —
# verified 2026-08-01, these returned 200 to completely unauthenticated callers.
#
# Every one of them costs money on an upstream account (GoPlus, Rugcheck,
# DexScreener, Tensor, XRPSCAN), so keyless callers are capped per source IP.
# Calls carrying a valid key are unaffected and never counted.
KEYLESS_SCAN_ENDPOINTS = frozenset({
    "/v1/token-security",
    "/v1/nft-security",
    "/v1/dapp-security",
    "/v1/approval-security",
    "/v1/nft-floor",
    "/v1/solana/token-risk",
    "/v1/solana/address-risk",
    "/v1/solana/nft-tensor",
    "/v1/ton-address",
    "/v1/xrp-address",
    "/v1/wallet-risk",
    "/v1/scan-wallet",
    "/v1/wallet-inbound",
})

# Deliberately generous. These are MOBILE clients, and carrier-grade NAT puts
# very large numbers of real users behind one address — a tight per-IP cap would
# lock out legitimate free-tier users on a mobile network long before it
# inconvenienced anyone scraping. This stops the endpoints being an unmetered
# upstream proxy; it is not a substitute for authentication. The durable fix is
# per-install free-tier keys, which needs a client release.
KEYLESS_IP_DAILY_CAP = 300


def _check_keyless_ip_quota(source_ip: str) -> bool:
    """Per-IP daily cap for unauthenticated scan calls. Returns True if allowed.

    Fails OPEN on a DynamoDB error, matching _check_demo_quota — this is a cost
    guardrail, not a security control, and an infra blip must not break scanning
    for every free-tier user at once."""
    if not source_ip:
        return True
    usage_key = f"ip#{source_ip}#{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    try:
        table = dynamodb.Table(DEMO_QUOTA_TABLE)
        resp  = table.update_item(
            Key={"usage_key": usage_key},
            UpdateExpression="ADD call_count :one SET expires_at = if_not_exists(expires_at, :ttl)",
            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 3 * 86400},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["call_count"]) <= KEYLESS_IP_DAILY_CAP
    except Exception as exc:
        logger.error("keyless IP quota check failed ip=%s error=%s", source_ip, exc)
        return True


def _check_demo_quota(key_record: dict) -> bool:
    """Atomically increments today's call count for a quota-capped demo key
    and returns whether it's still under cap. Fails open on a DynamoDB error —
    this is a cost/abuse guardrail, not a security control, so an infra blip
    should not break the demo experience for a legitimate visitor."""
    cap = DEMO_QUOTA_SOURCES.get(key_record.get("source"))
    if cap is None:
        return True
    usage_key = f"{key_record.get('api_key', '')}#{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    try:
        table = dynamodb.Table(DEMO_QUOTA_TABLE)
        resp  = table.update_item(
            Key={"usage_key": usage_key},
            UpdateExpression="ADD call_count :one SET expires_at = if_not_exists(expires_at, :ttl)",
            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 3 * 86400},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["call_count"]) <= cap
    except Exception as exc:
        logger.error("demo quota check failed key=%s error=%s", key_record.get("api_key", "")[:16], exc)
        return True


# AWS Marketplace Bundle D usage dimensions — API identifiers must match
# exactly what's configured in the AWS Marketplace pricing dimensions.
# Only these 3 endpoints (of this file's routes) belong to Bundle D — the
# other 2 (mcp-registry-risk, prompt-injection-breach) live in the isolated
# relayshield_agentic_api.py Lambda with their own copy of this logic.
# llm_credential_exposure added 2026-07-27 while the changeset was back in
# limited visibility for the Usage Instructions fix — bundled into the same
# resubmission rather than a separate pricing-terms change-set later.
BUNDLE_D_PRODUCT_CODE = os.environ.get("BUNDLE_D_PRODUCT_CODE", "")
BUNDLE_D_DIMENSION_NAMES = {
    "/v1/metered/tech-stack-cve":          "tech_stack_cve",
    "/v1/metered/bulk-identity-risk":      "bulk_identity_risk",
    "/v1/metered/llm-credential-exposure": "llm_credential_exposure",
}

# Bundle A ("Core Identity Exposure", $150/mo min) — same AWS Marketplace
# product entity as Bundle D ("RelayShield - Consumption Security API
# Bundles", prod-kkvurtspreofy), just a different contract dimension —
# hence reusing BUNDLE_D_PRODUCT_CODE's value rather than a separate env var.
# Verified zero path/dimension-key/gate-flag overlap with Bundle D 2026-07-13.
BUNDLE_A_DIMENSION_NAMES = {
    "/v1/metered/breach":          "breach_calls",
    "/v1/metered/sim-swap":        "sim_swap_calls",
    "/v1/metered/infostealer":     "infostealer_calls",
    "/v1/metered/domain":          "domain_calls",
    "/v1/metered/oauth-watchlist": "oauth_watchlist_calls",
    "/v1/metered/crypto-intel":    "crypto_intel_calls",
}

# Crypto Shield Mobile ($10.99/mo or $105.99/yr) — the exact set of metered
# endpoints the app calls (crypto-shield-app/src/api/relayshield.ts), and
# nothing more. Deliberately excludes bulk-identity-risk even though it's
# defined in the app's API client — that's a $2.00/call enterprise endpoint
# (dead code in the app, never actually called from any screen, confirmed
# 2026-07-11) and must never be free just because a user pays for the mobile
# app. Keeping this as an explicit allowlist rather than reusing has_subscription
# is the whole point — see is_cs_mobile_call below.
CS_MOBILE_ALLOWED_ENDPOINTS = frozenset({
    "/v1/metered/identity-risk-score",
    "/v1/metered/infostealer",
    "/v1/metered/breach",
    "/v1/metered/nhi-exposure",
    "/v1/metered/supply-chain",
    "/v1/metered/sim-swap",
})


def _report_marketplace_usage(aws_account_id: str, license_arn: str, dimension: str) -> None:
    """Report one call of usage to AWS Marketplace Metering Service for a
    Bundle D contract customer. Fire-and-forget — never raises. Duplicated
    in relayshield_agentic_api.py and relayshield_bundle_fulfillment.py
    rather than shared, same isolation rationale used throughout Bundle D.

    Uses CustomerAWSAccountId + LicenseArn, not the older CustomerIdentifier
    + ProductCode-only pattern — AWS's Concurrent Agreements model (rolled
    out 2026-06-01) rejects the old pattern for products created after that
    date with InvalidLicenseException, confirmed 2026-07-10."""
    if not aws_account_id or not license_arn or not dimension or not BUNDLE_D_PRODUCT_CODE:
        logger.warning("Skipping Bundle D usage report — missing account/license_arn/dimension/product_code")
        return
    try:
        mp_client = boto3.client("meteringmarketplace", region_name="us-east-1")
        mp_client.batch_meter_usage(
            UsageRecords=[{
                "Timestamp": datetime.now(timezone.utc),
                "CustomerAWSAccountId": aws_account_id,
                "LicenseArn": license_arn,
                "Dimension": dimension,
                "Quantity": 1,
            }],
        )
        logger.info("Bundle D usage reported account=%s dimension=%s", aws_account_id, dimension)
    except Exception as exc:
        logger.warning("Bundle D usage reporting failed (non-fatal) account=%s dimension=%s error=%s",
                       aws_account_id, dimension, exc)


def _record_stripe_meter_event(stripe_customer_id: str, path: str) -> None:
    """Post a usage event to Stripe Billing Meter. Fire-and-forget — never raises.

    Rewritten 2026-08-04 from one meter per endpoint to a single aggregate
    meter carrying the call's price in cents.

    Why: the old model needed one metered Price per endpoint on every
    developer's subscription, and **Stripe Checkout rejects more than 20
    recurring prices**. The list had reached 24, so `handle_signup()` had been
    failing with HTTP 400 — and self-serve developer signup had been dead —
    since 2026-06-24, when the 21st price was added. Verified by probing the
    live API: 20 prices succeed, 21 fail.

    The aggregate meter (`relayshield_api_usage`, formula=sum) takes
    `payload[value]` in cents against a $0.01-per-unit price, so a $0.35 call
    posts 35 and bills $0.35 — identical amounts, one line item, and no
    ceiling to hit as endpoints are added.

    Takes the request path, not a meter event name: the price is looked up here
    so a caller can never post a usage event with the wrong amount.

    Trade-off accepted: Stripe no longer shows a per-endpoint revenue split,
    because meter summaries cannot group by a payload key. `path` is still sent
    on each event for forensics, and CloudWatch remains the per-endpoint
    breakdown.
    """
    cents = METERED_CREDIT_COSTS.get(path, 0)
    if not cents:
        logger.warning("no price for %s — skipping meter event rather than billing 0", path)
        return
    try:
        secret_key = _stripe_secret_key()
        identifier = f"{stripe_customer_id}-{uuid.uuid4().hex}"
        payload    = urllib.parse.urlencode({
            "event_name":                  STRIPE_USAGE_METER_EVENT,
            "payload[value]":              str(cents),
            "payload[stripe_customer_id]": stripe_customer_id,
            "payload[path]":               path,
            "identifier":                  identifier,
        }).encode("utf-8")
        req = urllib.request.Request(
            STRIPE_METER_API,
            data=payload,
            headers={
                "Authorization":  f"Bearer {secret_key}",
                "Content-Type":   "application/x-www-form-urlencoded",
                "Stripe-Version": "2024-06-20",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("stripe meter event recorded customer=%s path=%s cents=%d status=%d",
                        stripe_customer_id, path, cents, resp.status)
    except Exception as exc:
        logger.warning("stripe meter event failed (non-fatal) customer=%s path=%s error=%s",
                       stripe_customer_id, path, exc)


def _send_intel_quota_warning(api_key_str: str, key_record: dict, threshold: int, calls_used: int) -> None:
    """
    Send a one-time SES email warning when an mp_499 key crosses a quota threshold.
    Sets a flag on the key record so the email fires exactly once per threshold per period.
    Non-fatal — never raises; quota enforcement continues even if the email fails.
    """
    email = key_record.get("email", "")
    if not email:
        logger.warning("intel quota warning: no email on key=%s — skipping send", api_key_str[:16])
        return

    flag_field  = "intel_quota_warned_80" if threshold == INTEL_WARN_80_CALLS else "intel_quota_warned_95"
    period      = key_record.get("intel_period_start", datetime.now(timezone.utc).strftime("%Y-%m"))
    flag_value  = key_record.get(flag_field)

    # Only fire once per billing period
    if flag_value == period:
        return

    calls_left  = 10_000 - calls_used
    pct         = threshold // 100  # 8000 → 80, 9500 → 95
    is_urgent   = threshold == INTEL_WARN_95_CALLS

    subject = (
        f"⚠️ Urgent: {calls_left} RelayShield TI calls remaining this month"
        if is_urgent else
        f"RelayShield Threat Intelligence: {pct}% of monthly quota used"
    )

    if is_urgent:
        body_html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#dc2626;">⚠️ You have {calls_left:,} Threat Intelligence calls left this month</h2>
  <p>Your RelayShield Threat Intelligence API key has used <strong>{calls_used:,} of 10,000 calls</strong>
  on your current MSP plan ($499/month). At your current rate you will hit the limit before
  the month resets.</p>
  <p>When you reach 10,000 calls, the API returns <code>HTTP 429</code> and all subsequent
  TI queries will fail until the next billing period begins.</p>
  <h3 style="margin-top:2rem;">Upgrade to MSSP — $999/month, unlimited calls</h3>
  <ul>
    <li><strong>No monthly call cap</strong> — query as often as your pipeline demands</li>
    <li>Priority support + SLA</li>
    <li>Same IOC database, same API key — zero integration changes</li>
  </ul>
  <p style="margin-top:1.5rem;">
    <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f"
       style="background:#6c63ff;color:#fff;padding:.65rem 1.4rem;border-radius:8px;
              text-decoration:none;font-weight:600;display:inline-block;">
      Upgrade to MSSP — $999/mo →
    </a>
  </p>
  <p style="margin-top:1.5rem;font-size:.85rem;color:#6b7280;">
    Questions? Reply to this email or contact
    <a href="mailto:support@relayshield.net">support@relayshield.net</a>.<br>
    Your billing period resets on the 1st of next month.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:2rem 0;">
  <p style="font-size:.75rem;color:#9ca3af;">RelayShield LLC · relayshield.net · API key: {api_key_str[:16]}...</p>
</body></html>
"""
    else:
        body_html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#d97706;">You've used 80% of your monthly Threat Intelligence quota</h2>
  <p>Your RelayShield Threat Intelligence API key has used <strong>{calls_used:,} of 10,000 calls</strong>
  on your current MSP plan ($499/month). You have <strong>{calls_left:,} calls remaining</strong>
  this billing period.</p>
  <p>This is an early heads-up — no action required yet. If your usage continues at the
  current rate, you may hit the limit before month end.</p>
  <h3 style="margin-top:2rem;">Consider upgrading to MSSP — $999/month</h3>
  <p>For MSSPs running continuous monitoring across multiple client environments,
  the MSSP tier removes the call cap entirely:</p>
  <ul>
    <li><strong>Unlimited calls/month</strong> — no quota, no 429 errors</li>
    <li>2.5× more value per dollar at scale</li>
    <li>Priority support + SLA</li>
    <li>Same API key, zero integration changes</li>
  </ul>
  <p style="margin-top:1.5rem;">
    <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f"
       style="background:#6c63ff;color:#fff;padding:.65rem 1.4rem;border-radius:8px;
              text-decoration:none;font-weight:600;display:inline-block;">
      Upgrade to MSSP — $999/mo →
    </a>
  </p>
  <p style="margin-top:1rem;font-size:.85rem;color:#6b7280;">
    No rush — you still have {calls_left:,} calls this month. We'll send another reminder
    if you reach 95%.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:2rem 0;">
  <p style="font-size:.75rem;color:#9ca3af;">RelayShield LLC · relayshield.net · API key: {api_key_str[:16]}...</p>
</body></html>
"""

    try:
        ses.send_email(
            Source=f"RelayShield <{FROM_EMAIL}>",
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body":    {"Html": {"Data": body_html, "Charset": "UTF-8"}},
            },
        )
        logger.info("intel quota warning sent to=%s threshold=%d key=%s", email, threshold, api_key_str[:16])

        # Mark this threshold as warned for the current period
        dynamodb.Table(API_KEYS_TABLE).update_item(
            Key={"api_key": api_key_str},
            UpdateExpression=f"SET {flag_field} = :p",
            ExpressionAttributeValues={":p": period},
        )
    except Exception as exc:
        logger.error("intel quota warning email failed key=%s error=%s", api_key_str[:16], exc)


def _check_and_increment_intel_quota(api_key_str: str, key_record: dict) -> dict | None:
    """
    Enforce the Threat Intelligence API monthly call cap for the api key's
    intel_plan_tier (default mp_499 — fails safe to the capped tier if unset).
    Resets the counter on a new calendar month. Returns an error response
    dict if the key is over quota, or None if the call is allowed (and the
    counter has already been incremented).
    """
    tier  = key_record.get("intel_plan_tier") or INTEL_DEFAULT_TIER
    limit = INTEL_PLAN_LIMITS.get(tier, INTEL_PLAN_LIMITS[INTEL_DEFAULT_TIER])

    table          = dynamodb.Table(API_KEYS_TABLE)
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    stored_period  = key_record.get("intel_period_start")

    if stored_period != current_period:
        # New billing month (or first call ever) — reset counter.
        try:
            table.update_item(
                Key={"api_key": api_key_str},
                UpdateExpression="SET intel_period_start = :p, intel_period_calls = :z",
                ExpressionAttributeValues={":p": current_period, ":z": 0},
            )
        except Exception as exc:
            logger.warning("intel quota reset failed key=%s error=%s", api_key_str[:16], exc)
        period_calls = 0
    else:
        period_calls = int(key_record.get("intel_period_calls") or 0)

    if limit is not None and period_calls >= limit:
        return {
            "statusCode": 429,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":      False,
                "error":   f"Monthly call limit ({limit}) reached for the {tier} Threat Intelligence plan.",
                "upgrade_url": "https://api.relayshield.net/developers",
            }),
        }

    try:
        table.update_item(
            Key={"api_key": api_key_str},
            UpdateExpression="SET intel_period_calls = if_not_exists(intel_period_calls, :z) + :one, "
                              "intel_period_start = :p",
            ExpressionAttributeValues={":z": 0, ":one": 1, ":p": current_period},
        )
    except Exception as exc:
        logger.warning("intel quota increment failed (non-fatal) key=%s error=%s", api_key_str[:16], exc)

    # Quota warning emails — only for capped tier (mp_499); mssp_999 has no limit.
    # Check AFTER incrementing so `period_calls` reflects the call just made.
    if limit is not None:
        new_count = period_calls + 1
        if new_count >= INTEL_WARN_95_CALLS:
            _send_intel_quota_warning(api_key_str, key_record, INTEL_WARN_95_CALLS, new_count)
        elif new_count >= INTEL_WARN_80_CALLS:
            _send_intel_quota_warning(api_key_str, key_record, INTEL_WARN_80_CALLS, new_count)

    return None


def handle_metered_request(path: str, method: str, event: dict) -> dict:
    """Auth + dispatch for /v1/metered/* routes. Verifies RS API key, runs handler,
    then records a Stripe Billing Meter event on success."""
    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    headers    = event.get("headers") or {}
    api_key_str = (
        _header(headers, "X-RS-API-KEY")
        or _header(headers, "Authorization").removeprefix("Bearer ").strip()
    )

    key_record = _verify_rs_api_key(api_key_str)
    if not key_record:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Invalid or missing API key. Pass your key as X-RS-API-KEY header.",
                "docs":  "https://api.relayshield.net/developers",
            }),
        }

    metered_routes = {
        "/v1/metered/breach":          handle_breach,
        "/v1/metered/sim-swap":        handle_sim_swap,
        "/v1/metered/infostealer":     handle_infostealer,
        "/v1/metered/domain":          handle_domain,
        "/v1/metered/oauth-watchlist": handle_oauth_watchlist,
        "/v1/metered/crypto-intel":    handle_crypto_intel,
        "/v1/metered/supply-chain":    handle_supply_chain,
        "/v1/metered/session-risk":    handle_session_risk,
        "/v1/metered/identity-graph":  handle_identity_graph,
        "/v1/metered/ransomware-risk": handle_ransomware_risk,
        "/v1/metered/nhi-exposure":    handle_nhi_exposure,
        "/v1/metered/llm-credential-exposure": handle_llm_credential_exposure,
        "/v1/metered/secret-scan":     handle_secret_scan,
        "/v1/metered/secret-scan-text": handle_secret_scan_text,
        "/v1/metered/target-risk":     handle_target_risk,
        "/v1/metered/asset-intel":         lambda p: handle_asset_intel(p, api_key_str),
        "/v1/metered/threat-actor":        handle_threat_actor,
        "/v1/metered/cve-identity-risk":   handle_cve_identity_risk,
        "/v1/metered/identity-risk-score": handle_identity_risk_score,
        "/v1/metered/bulk-ioc":            handle_bulk_ioc,
        "/v1/metered/ioc-pivot":           handle_ioc_pivot,
        "/v1/metered/brand-monitor":       handle_brand_monitor,
        "/v1/metered/bulk-identity-risk":  handle_bulk_identity_risk,
        "/v1/metered/tech-stack-cve":      handle_tech_stack_cve,
        "/v1/metered/cert-expiry":         handle_cert_expiry,
        "/v1/metered/ip-intel":            handle_ip_intel,
        "/v1/metered/card-exposure":       handle_card_exposure,
        "/v1/webhook/configure":       lambda p: handle_webhook_configure(p, api_key_str),
        "/v1/siem/configure":          lambda p: handle_siem_configure(p, api_key_str),
    }
    handler = metered_routes.get(path)
    if not handler:
        return _err(f"unknown metered endpoint: {path}", 404)

    # Billing check before executing — must have credits OR active subscription
    # Demo keys bypass billing entirely. "hf_smolagents_demo" is a separate,
    # quota-capped key (see _check_demo_quota below) embedded in the public
    # relayshield_smolagents_tool.py package — kept distinct from
    # "demo_portal" (the unlimited, server-side-only TI demo key) so the two
    # can be rate-limited and reported on independently. "mcp_space_demo"
    # (added 2026-07-26) is the same pattern for the HF MCP Space's own
    # zero-key free tier -- a shared, capped demo key baked into the Space
    # itself so a caller can try one tool with no signup at all.
    is_demo = key_record.get("source") in ("demo_portal", "hf_smolagents_demo", "mcp_space_demo")
    if not is_demo:
        credit_balance   = int(key_record.get("credit_balance") or 0)
        # has_subscription covers both billing paths that promise "all metered
        # endpoints included": direct Stripe TI subscribers (stripe_subscription_id)
        # and AWS Marketplace TI subscribers (intel_plan_tier — set exclusively by
        # relayshield_aws_marketplace.py's _provision_api_key, never elsewhere).
        # Fixed 2026-07-08: previously only checked stripe_subscription_id, so
        # every AWS Marketplace TI Starter/Unlimited customer got a 402 on every
        # metered endpoint despite the welcome email promising all of them included.
        # Explicitly excludes source=="cs_mobile" (added 2026-07-11) — those keys
        # also carry stripe_subscription_id (needed for cancellation lookups) but
        # must NOT get the blanket "all endpoints included" grant, since CS Mobile
        # is a $10.99/mo consumer subscription, not a $499-999/mo TI plan. Their
        # access is scoped separately below via is_cs_mobile_call.
        has_subscription = (
            (bool(key_record.get("stripe_subscription_id")) and key_record.get("source") != "cs_mobile")
            or bool(key_record.get("intel_plan_tier"))
        )
        credit_cost      = METERED_CREDIT_COSTS.get(path, 0)
        use_credits      = credit_balance >= credit_cost
        # Free tier (added 2026-08-04): a no-card key issued on email signup.
        # Counted in CALLS, not credits, because that is what the landing page
        # promises -- 20 calls means 20 calls whether each is $0.05 cert-expiry
        # or $2.00 bulk-identity-risk. Checked AFTER credits and subscriptions
        # so a developer who later adds a card is billed normally rather than
        # silently burning a leftover free allowance. Decremented atomically on
        # success only, below.
        free_calls        = int(key_record.get("free_calls_remaining") or 0)
        is_free_tier_call = free_calls > 0 and not use_credits and not has_subscription
        is_bundle_d_call = (
            bool(key_record.get("bundle_d_access"))
            and bool(key_record.get("aws_customer_id"))
            and path in BUNDLE_D_DIMENSION_NAMES
        )
        is_bundle_a_call = (
            bool(key_record.get("bundle_a_access"))
            and bool(key_record.get("aws_customer_id"))
            and path in BUNDLE_A_DIMENSION_NAMES
        )
        # Crypto Shield Mobile — scoped bypass for the small set of endpoints the
        # app actually calls (see CS_MOBILE_ALLOWED_ENDPOINTS), not the full catalog.
        is_cs_mobile_call = bool(key_record.get("cs_mobile_access")) and path in CS_MOBILE_ALLOWED_ENDPOINTS
        # LLMjacking Detection License ($39/mo or $399/yr, added 2026-07-26) —
        # scoped bypass for exactly one endpoint, same shape as is_cs_mobile_call.
        # llm_access must never grant the rest of the metered catalog.
        is_llm_license_call = bool(key_record.get("llm_access")) and path == "/v1/metered/llm-credential-exposure"

    if key_record.get("source") in DEMO_QUOTA_SOURCES and not _check_demo_quota(key_record):
        return {
            "statusCode": 429,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Shared demo key's daily call quota reached. Get your own free-tier key: "
                         "https://api.relayshield.net/developers?source=hf-smolagents",
                "docs":  "https://api.relayshield.net/developers",
            }),
        }

    if (not is_demo and not use_credits and not has_subscription and not is_bundle_d_call
            and not is_bundle_a_call and not is_cs_mobile_call and not is_llm_license_call
            and not is_free_tier_call):
        logger.warning(
            "402 insufficient credits — path=%s key=%s credit_balance=%s source=%s",
            path, api_key_str[:24], credit_balance, key_record.get("source"),
        )
        return {
            "statusCode": 402,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":      False,
                # Says which of the two states the caller is actually in. A key
                # that has used its free allowance needs a card; a key that
                # never had one is a different conversation, and one generic
                # message for both leaves the developer guessing.
                "error": (
                    "Your 20 free calls are used up. Add a card to keep going. "
                    "You are billed only for the calls you make, with no minimum "
                    "and no subscription fee."
                    if key_record.get("free_calls_remaining") is not None
                    else "Insufficient credits and no active subscription."
                ),
                "topup_url": "https://api.relayshield.net/developers",
            }),
        }

    params = _body(event)
    try:
        result = handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in metered %s: %s", path, exc)
        return _err("internal server error", 500)

    # Only bill on success (demo keys never billed)
    if not is_demo and result.get("statusCode", 200) < 300:
        if is_bundle_d_call:
            _report_marketplace_usage(
                key_record.get("aws_account_id", ""), key_record.get("aws_license_arn", ""), BUNDLE_D_DIMENSION_NAMES[path]
            )
        elif is_bundle_a_call:
            _report_marketplace_usage(
                key_record.get("aws_account_id", ""), key_record.get("aws_license_arn", ""), BUNDLE_A_DIMENSION_NAMES[path]
            )
        elif is_free_tier_call:
            # Conditional update: if two calls race, the second fails the
            # condition rather than driving the counter negative. Non-fatal --
            # the work is already done and refusing to return it because a
            # counter update failed would be the wrong trade.
            try:
                dynamodb.Table(API_KEYS_TABLE).update_item(
                    Key={"api_key": api_key_str},
                    UpdateExpression="SET free_calls_remaining = free_calls_remaining - :one",
                    ConditionExpression="free_calls_remaining >= :one",
                    ExpressionAttributeValues={":one": 1},
                )
                logger.info("free-tier call key=%s path=%s remaining=%d",
                            api_key_str[:16], path, free_calls - 1)
            except Exception as exc:
                logger.warning("free-tier decrement failed (non-fatal) key=%s error=%s",
                               api_key_str[:16], exc)
        elif use_credits:
            # Deduct credits atomically
            try:
                dynamodb.Table(API_KEYS_TABLE).update_item(
                    Key={"api_key": api_key_str},
                    UpdateExpression="SET credit_balance = credit_balance - :cost",
                    ConditionExpression="credit_balance >= :cost",
                    ExpressionAttributeValues={":cost": credit_cost},
                )
                logger.info("credits deducted key=%s cost=%d remaining=%d",
                            api_key_str[:16], credit_cost, credit_balance - credit_cost)
            except Exception as exc:
                logger.warning("credit deduction failed (non-fatal) key=%s error=%s", api_key_str[:16], exc)
        elif is_cs_mobile_call:
            # Included in the $10.99/mo subscription — no credits, no Stripe
            # meter event. Nothing to bill or track here by design.
            pass
        elif is_llm_license_call:
            # Included in the $39/mo or $399/yr LLMjacking license — no
            # credits, no Stripe meter event.
            pass
        else:
            # Fall back to Stripe meter event. Gated on the path having a
            # price rather than a per-endpoint meter event name (single
            # aggregate meter since 2026-08-04 — see
            # _record_stripe_meter_event). Gating on METERED_CREDIT_COSTS also
            # closes the older failure mode where an endpoint added to
            # STRIPE_METER_EVENTS but not to the price table would post a
            # usage event nothing could bill.
            stripe_customer_id = key_record.get("stripe_customer_id", "")
            if METERED_CREDIT_COSTS.get(path) and stripe_customer_id:
                _record_stripe_meter_event(stripe_customer_id, path)

        source = headers.get("X-RS-Source") or headers.get("x-rs-source")
        if source == "hf-mcp-space":
            _log_hf_mcp_call(path, METERED_CREDIT_COSTS.get(path, 0))

        # Webhook push delivery — fire async if customer has registered a webhook
        webhook_url = key_record.get("webhook_url", "")
        if webhook_url and result.get("statusCode", 200) < 300:
            try:
                result_data = json.loads(result.get("body", "{}")).get("data", {})
                if result_data.get("found") or result_data.get("matched") or result_data.get("on_victim_list") or result_data.get("breach_count", 0) > 0:
                    import threading
                    t = threading.Thread(
                        target=_fire_webhook,
                        args=(webhook_url, {"id": result_data.get("email") or result_data.get("domain") or path, "endpoint": path, **result_data}),
                    )
                    t.start()
                    t.join(timeout=6)
            except Exception as wh_exc:
                logger.debug("Webhook thread error: %s", wh_exc)

    return result


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _badge_svg(domain: str, level: str, color: str, style: str = "flat", score: int = 0) -> str:
    """Generate an SVG security badge for embedding on partner sites."""
    value   = f"{level} {score}/100" if score and level != "UNKNOWN" else level
    label_w = 150
    value_w = 100
    total_w = label_w + value_w
    h       = 28

    if style == "compact":
        # Minimal pill badge
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20">'
            f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
            f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
            f'<rect rx="3" width="120" height="20" fill="#0a1628"/>'
            f'<rect rx="3" x="70" width="50" height="20" fill="{color}"/>'
            f'<rect rx="3" width="120" height="20" fill="url(#s)"/>'
            f'<text x="5" y="14" font-family="DejaVu Sans,Verdana,sans-serif" font-size="10" fill="#fff">🛡 RS Shield</text>'
            f'<text x="75" y="14" font-family="DejaVu Sans,Verdana,sans-serif" font-size="10" fill="#0a1628" font-weight="bold">{level}</text>'
            f'</svg>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{h}">'
        f'<rect rx="4" width="{total_w}" height="{h}" fill="#0a1628"/>'
        f'<rect rx="4" x="{label_w}" width="{value_w}" height="{h}" fill="{color}"/>'
        f'<rect rx="4" width="{total_w}" height="{h}" fill="url(#a)"/>'
        f'<linearGradient id="a" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".15"/>'
        f'<stop offset="1" stop-opacity=".15"/>'
        f'</linearGradient>'
        f'<g fill="#fff" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">'
        f'<text x="8" y="19" fill="#00B5A5" font-weight="bold">🛡 RelayShield</text>'
        f'<text x="{label_w + 8}" y="19" fill="#0a1628" font-weight="bold">{value}</text>'
        f'</g>'
        f'<a href="https://api.relayshield.net/developers" target="_blank">'
        f'<rect width="{total_w}" height="{h}" fill="transparent"/>'
        f'</a>'
        f'</svg>'
    )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _dynamodb_resource():
    import boto3
    return boto3.resource("dynamodb", region_name="us-east-1")


def _ok(data: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "data": data}),
    }


def _header(headers: dict, name: str) -> str:
    """Case-insensitive header lookup.

    API Gateway's REST API preserves the case the client sent, so exact-match
    lookups only catch the spellings someone thought to enumerate. Python's
    stdlib urllib normalizes header names with str.capitalize(), which turns
    "X-RS-API-KEY" into "X-rs-api-key" — a spelling that matched neither of the
    two variants previously checked, so every urllib-based caller got a 401
    while curl and `requests` worked. Found 2026-07-31 building the pre-commit
    hook, which is itself urllib-based.
    """
    if not headers:
        return ""
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v or ""
    return ""


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": False, "error": message}),
    }


def _body(event: dict) -> dict:
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return {}


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/breach
# ---------------------------------------------------------------------------
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "breach_count": N, "breaches": [...] }
#
# Breaches list contains summarised HIBP objects: Name, Domain, BreachDate,
# DataClasses. Full HIBP schema preserved so callers can apply their own
# filtering logic.

def handle_breach(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("HIBP call failed for %s: %s", email, exc)
        return _err("breach check failed — upstream error", 502)

    summary = [
        {
            "name":         b.get("Name"),
            "domain":       b.get("Domain"),
            "breach_date":  b.get("BreachDate"),
            "data_classes": b.get("DataClasses", []),
            "is_verified":  b.get("IsVerified", False),
        }
        for b in breaches
    ]

    logger.info("breach check — email=%s count=%d", email, len(summary))
    return _ok({
        "email":        email,
        "record_type":  "credential_exposure",
        "breach_count": len(summary),
        "breaches":     summary,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-url
# ---------------------------------------------------------------------------
# Request:  { "url": "https://example.com/path" }
# Response: { "status": "pending", "analysis_id": "...", "poll_endpoint": "/v1/result/{id}" }
#
# Submits to VirusTotal and returns immediately with an analysis_id.
# Caller polls GET /v1/result/{analysis_id} for the verdict.

def handle_scan_url(params: dict) -> dict:
    url = (params.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return _err("url is required and must start with http:// or https://")

    api_key = _vt_api_key()
    payload = urllib.parse.urlencode({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"{VT_BASE_URL}/urls",
        data=payload,
        headers={
            "x-apikey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT URL submit failed for %s: %s", url, exc)
        return _err("URL submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    # Immediate heuristic signal — added 2026-07-16 to unify this endpoint
    # with Telegram's /scan and WhatsApp's SCAN/ATTACH, which already
    # combine VT with RelayShield's IOC corpus + Google Safe Browsing +
    # RDAP domain-age. VT's own submit-then-poll model means the definitive
    # verdict isn't available in this response, but a caller shouldn't have
    # to wait on that poll to learn about a domain that's already a known
    # red flag right now.
    heuristics = _heuristic_url_check(url)

    logger.info("scan-url submitted — url=%s analysis_id=%s heuristics=%s", url, analysis_id, heuristics)
    return _ok({
        "status":               "pending",
        "target":               url,
        "analysis_id":          analysis_id,
        "poll_endpoint":        f"/v1/result/{analysis_id}",
        "immediate_signal":     "flagged" if heuristics["flagged"] else "no_immediate_red_flags",
        "immediate_reasons":    heuristics["reasons"],
        "note":                 "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-file
# ---------------------------------------------------------------------------
# Request:  { "file_url": "https://cdn.example.com/report.pdf",
#             "filename": "report.pdf" }          ← filename optional
# Response: same shape as /v1/scan-url
#
# RelayShield downloads the file from file_url, then submits the bytes to
# VirusTotal /files. The caller never needs to forward raw bytes — only a URL.

def handle_scan_file(params: dict) -> dict:
    file_url = (params.get("file_url") or "").strip()
    filename = (params.get("filename") or file_url.split("/")[-1] or "upload").strip()

    if not file_url.startswith(("http://", "https://")):
        return _err("file_url is required and must start with http:// or https://")

    # Download the file
    try:
        req = urllib.request.Request(file_url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            file_bytes   = resp.read()
            content_type = resp.headers.get_content_type() or "application/octet-stream"
    except Exception as exc:
        logger.error("File download failed for %s: %s", file_url, exc)
        return _err(f"could not download file from file_url: {exc}", 400)

    if not file_bytes:
        return _err("downloaded file was empty", 400)

    api_key  = _vt_api_key()
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{VT_BASE_URL}/files",
        data=body,
        headers={
            "x-apikey": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT file submit failed: %s", exc)
        return _err("file submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    logger.info("scan-file submitted — file_url=%s analysis_id=%s", file_url, analysis_id)
    return _ok({
        "status":        "pending",
        "target":        file_url,
        "filename":      filename,
        "analysis_id":   analysis_id,
        "poll_endpoint": f"/v1/result/{analysis_id}",
        "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


def _poll_vt(analysis_id: str, api_key: str, max_wait: int) -> dict | None:
    """Poll VT analyses/{id} until completed or timeout. Returns stats dict or None."""
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    waited = 0
    while waited <= max_wait:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data  = json.loads(resp.read())
                attrs = data.get("data", {}).get("attributes", {})
                if attrs.get("status") == "completed":
                    return attrs.get("stats", {})
        except Exception as exc:
            logger.error("VT poll error %s: %s", analysis_id, exc)
            return None
        time.sleep(VT_POLL_INTERVAL)
        waited += VT_POLL_INTERVAL
    logger.warning("VT analysis %s timed out after %ds", analysis_id, max_wait)
    return None


def _vt_response(target: str, analysis_id: str, stats: dict | None) -> dict:
    if stats is None:
        return _ok({
            "target":       target,
            "analysis_id":  analysis_id,
            "verdict":      "timeout",
            "note":         "analysis did not complete in time — treat as unverified",
        })
    malicious  = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless   = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)
    total      = malicious + suspicious + harmless + undetected
    if malicious > 0:
        verdict = "malicious"
    elif suspicious > 0:
        verdict = "suspicious"
    else:
        verdict = "clean"
    logger.info("VT result — target=%s verdict=%s malicious=%d/%d",
                target, verdict, malicious, total)
    return _ok({
        "target":         target,
        "analysis_id":    analysis_id,
        "verdict":        verdict,
        "malicious":      malicious,
        "suspicious":     suspicious,
        "harmless":       harmless,
        "undetected":     undetected,
        "total_engines":  total,
    })


def _vt_get(path: str, api_key: str) -> dict | None:
    req = urllib.request.Request(f"{VT_BASE_URL}{path}", headers={"x-apikey": api_key}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


IP_INTEL_CACHE_TABLE   = "relayshield_ip_intel_cache"
IP_INTEL_CACHE_SECONDS = 6 * 3600  # reputation doesn't change minute-to-minute; this is the
                                    # main lever for staying under VT's rate limit on repeat/popular queries

def _ip_intel_cache_get(queried: str) -> dict | None:
    try:
        item = dynamodb.Table(IP_INTEL_CACHE_TABLE).get_item(Key={"queried": queried}).get("Item")
        return _decimals_to_plain(dict(item["result"])) if item else None
    except Exception as exc:
        logger.warning("ip-intel cache read failed for %s: %s", queried, exc)
        return None


def _ip_intel_cache_put(queried: str, result: dict) -> None:
    try:
        dynamodb.Table(IP_INTEL_CACHE_TABLE).put_item(Item={
            "queried": queried,
            "result": result,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(time.time()) + IP_INTEL_CACHE_SECONDS,
        })
    except Exception as exc:
        logger.warning("ip-intel cache write failed for %s: %s", queried, exc)


def handle_ip_intel(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower().removeprefix("www.")
    ip     = (params.get("ip") or "").strip()
    if not domain and not ip:
        return _err("domain or ip is required")

    query_type = "ip" if ip else "domain"
    queried    = ip or domain

    cached = _ip_intel_cache_get(queried)
    if cached is not None:
        logger.info("ip-intel cache hit query_type=%s queried=%s", query_type, queried)
        return _ok(cached)

    # Check RelayShield's own IOC corpus first — free, fast, no VT call needed,
    # and a confirmed hit here is a stronger signal than a VT vote count (this
    # is RelayShield's own criminal-marketplace/breach pipeline, not a
    # third-party vote). Only calls VT if nothing is already known internally.
    try:
        corpus_table = dynamodb.Table(INTEL_IOCS_TABLE)
        corpus_resp = corpus_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(queried),
            FilterExpression=boto3.dynamodb.conditions.Attr("ioc_type").is_in(["ip", "domain"] if query_type == "ip" else ["domain", "url"]),
            Limit=5,
        )
        corpus_hits = corpus_resp.get("Items", [])
    except Exception as exc:
        logger.warning("ip-intel own-corpus lookup failed for %s: %s", queried, exc)
        corpus_hits = []

    if corpus_hits:
        corpus_result = {
            "queried":          queried,
            "query_type":       query_type,
            "found":            True,
            "reputation":       None,
            "malicious_votes":  len(corpus_hits),
            "suspicious_votes": 0,
            "source":           "relayshield_ioc_corpus",
            "resolutions":      [],
            "checked_at":       datetime.now(timezone.utc).isoformat(),
        }
        logger.info("ip-intel own-corpus hit query_type=%s queried=%s hits=%d — skipping VT", query_type, queried, len(corpus_hits))
        _ip_intel_cache_put(queried, corpus_result)
        return _ok(corpus_result)

    api_key = _vt_api_key()

    try:
        if query_type == "ip":
            report      = _vt_get(f"/ip_addresses/{urllib.parse.quote(ip)}", api_key)
            resolutions = _vt_get(f"/ip_addresses/{urllib.parse.quote(ip)}/resolutions?limit=10", api_key)
        else:
            report      = _vt_get(f"/domains/{urllib.parse.quote(domain)}", api_key)
            resolutions = _vt_get(f"/domains/{urllib.parse.quote(domain)}/resolutions?limit=10", api_key)
    except Exception as exc:
        logger.error("ip-intel VT lookup failed for %s: %s", queried, exc)
        return _err("intel lookup failed — upstream error", 502)

    if report is None:
        not_found_result = {
            "queried":          queried,
            "query_type":       query_type,
            "found":            False,
            "reputation":       None,
            "malicious_votes":  None,
            "suspicious_votes": None,
            "resolutions":      [],
            "checked_at":       datetime.now(timezone.utc).isoformat(),
        }
        _ip_intel_cache_put(queried, not_found_result)
        return _ok(not_found_result)

    attrs = report.get("data", {}).get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})

    resolution_list = []
    for item in (resolutions or {}).get("data", [])[:10]:
        r_attrs = item.get("attributes", {})
        raw_date = r_attrs.get("date")
        date_iso = None
        if isinstance(raw_date, (int, float)):
            date_iso = datetime.fromtimestamp(raw_date, tz=timezone.utc).isoformat()
        entry = {"date": date_iso}
        if query_type == "ip":
            entry["hostname"] = r_attrs.get("host_name", "")
        else:
            entry["ip_address"] = r_attrs.get("ip_address", "")
        resolution_list.append(entry)

    result = {
        "queried":          queried,
        "query_type":       query_type,
        "found":            True,
        "reputation":       attrs.get("reputation", 0),
        "malicious_votes":  stats.get("malicious", 0),
        "suspicious_votes": stats.get("suspicious", 0),
        "resolutions":      resolution_list,
        "checked_at":       datetime.now(timezone.utc).isoformat(),
    }
    if query_type == "ip":
        result["as_owner"] = attrs.get("as_owner", "")
        result["country"]  = attrs.get("country", "")

    logger.info("ip-intel query_type=%s queried=%s reputation=%s malicious=%s",
                query_type, queried, result["reputation"], result["malicious_votes"])
    _ip_intel_cache_put(queried, result)
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/card-exposure
#
# BIN/stolen-card monitoring (competitive benchmark roadmap item, added
# 2026-07-24). Data source: relayshield_stolen_cards, populated by
# _parse_card_data() in relayshield_intel_monitor.py from stealer-log
# Autofill/CreditCards archive files.
#
# Deliberately does NOT accept a raw card number as input, by design, not
# by oversight -- unlike a domain or email, RelayShield receiving a live PAN
# even transiently carries real PCI-adjacent exposure for no real benefit.
# Instead:
#   { "pan_hash": "<sha256 hex of the digit-only card number, client-computed>" }
#     -> exact match: is THIS specific card in the corpus (k-anonymity-style,
#        same shape as HaveIBeenPwned's password-hash-prefix pattern -- the
#        client hashes locally, RelayShield never sees the raw number)
#   { "bin": "411111" }
#     -> aggregate only: how many distinct cards with this BIN have leaked,
#        and when most recently -- no per-card details returned, since a
#        bulk BIN query isn't a specific-cardholder lookup
# Both may be supplied together. At least one is required.
# ---------------------------------------------------------------------------

_RE_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


def handle_card_exposure(params: dict) -> dict:
    pan_hash = (params.get("pan_hash") or "").strip().lower()
    bin_     = (params.get("bin") or "").strip()

    if not pan_hash and not bin_:
        return _err("pan_hash or bin is required")
    if pan_hash and not _RE_SHA256_HEX.match(pan_hash):
        # Never log the rejected value itself -- if a caller mistakenly (or
        # otherwise) sends a raw card number here, that string does not
        # belong in CloudWatch either.
        return _err("pan_hash must be a 64-character SHA-256 hex digest of the digit-only card number, not a raw card number")
    if bin_ and not re.match(r"^\d{6,8}$", bin_):
        return _err("bin must be 6-8 digits")

    result: dict = {}
    table = dynamodb.Table(STOLEN_CARDS_TABLE)

    if pan_hash:
        try:
            item = table.get_item(Key={"pan_hash": pan_hash}).get("Item")
        except Exception as exc:
            logger.error("card-exposure pan_hash lookup failed: %s", exc)
            return _err("Card exposure lookup failed", 500)
        result["card_exposed"] = bool(item)
        if item:
            result["last4"]      = item.get("last4", "")
            result["first_seen"] = item.get("seen_ts", "")

    if bin_:
        try:
            resp = table.query(
                IndexName="bin-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("bin").eq(bin_),
                ProjectionExpression="seen_ts",
            )
            items = resp.get("Items", [])
            while "LastEvaluatedKey" in resp:
                resp = table.query(
                    IndexName="bin-index",
                    KeyConditionExpression=boto3.dynamodb.conditions.Key("bin").eq(bin_),
                    ProjectionExpression="seen_ts",
                    ExclusiveStartKey=resp["LastEvaluatedKey"],
                )
                items.extend(resp.get("Items", []))
        except Exception as exc:
            logger.error("card-exposure bin lookup failed: %s", exc)
            return _err("Card exposure lookup failed", 500)
        result["bin_exposed_card_count"] = len(items)
        result["bin_last_seen"] = max((i["seen_ts"] for i in items if i.get("seen_ts")), default=None)

    logger.info("card-exposure query bin_present=%s pan_hash_present=%s", bool(bin_), bool(pan_hash))
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/sim-swap
# ---------------------------------------------------------------------------
# Request:  { "phone": "+14155551234" }
# Response: { "phone": "...", "swapped": bool, "swap_timestamp": "...",
#             "carrier": "...", "checked_at": "..." }

def handle_sim_swap(params: dict) -> dict:
    phone = (params.get("phone") or "").strip()
    if not phone.startswith("+"):
        return _err("phone is required in E.164 format (e.g. +14155551234)")

    account_sid, auth_token = _twilio_creds()
    encoded     = urllib.parse.quote(phone, safe="")
    url         = TWILIO_LOOKUP_URL.format(phone=encoded) + "?Fields=sim_swap"
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body         = json.loads(resp.read())
            sim_swap_obj = body.get("sim_swap") or {}
            last_swap    = sim_swap_obj.get("last_sim_swap") or {}
            result = {
                "phone":          phone,
                "swapped":        bool(last_swap.get("swapped_in_period", False)),
                "swap_timestamp": last_swap.get("last_sim_swap_date", ""),
                "carrier":        sim_swap_obj.get("carrier_name", ""),
                "checked_at":     datetime.now(timezone.utc).isoformat(),
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio Lookup HTTP %d for %s: %s", exc.code, phone, error_body)
        return _err(f"Twilio returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("Twilio Lookup failed for %s: %s", phone, exc)
        return _err("SIM swap check failed — upstream error", 502)

    logger.info("sim-swap check — phone=%s swapped=%s carrier=%s",
                phone, result["swapped"], result["carrier"] or "unknown")
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/domain
# ---------------------------------------------------------------------------
# Request:  { "domain": "acme.com" }
# Response: { "domain": "...", "lookalikes_found": N,
#             "lookalikes": [{ "domain": "...", "gsb_flagged": bool,
#                              "registration_age_days": N | null,
#                              "cert_count": N, "cert_recent": bool,
#                              "latest_cert_issued": "..." }],
#             "candidates_checked": N, "checked_at": "..." }

def handle_domain(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower()
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")
    # Strip scheme if someone passes a full URL
    for prefix in ("https://", "http://", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]

    candidates  = _generate_typosquat_permutations(domain)
    prioritised = _prioritise_candidates(domain, candidates)
    active      = _find_active_lookalikes(prioritised)

    lookalikes = _enrich_lookalikes(active, _gsb_api_key())

    logger.info("domain scan — domain=%s candidates=%d active=%d",
                domain, len(prioritised), len(active))
    return _ok({
        "domain":             domain,
        "lookalikes_found":   len(active),
        "lookalikes":         lookalikes,
        "candidates_checked": len(prioritised),
        "checked_at":         datetime.now(timezone.utc).isoformat(),
    })


def _generate_typosquat_permutations(domain: str) -> set[str]:
    if "." not in domain:
        return set()
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    perms: set[str] = set()

    for i in range(len(name)):
        candidate = name[:i] + name[i + 1:]
        if candidate:
            perms.add(candidate + tld)
    for i, c in enumerate(name):
        perms.add(name[:i] + c + c + name[i + 1:] + tld)
    for i in range(len(name) - 1):
        t = list(name)
        t[i], t[i + 1] = t[i + 1], t[i]
        perms.add("".join(t) + tld)
    for i, c in enumerate(name):
        if c == "o":
            perms.add(name[:i] + "0" + name[i + 1:] + tld)
        elif c == "0":
            perms.add(name[:i] + "o" + name[i + 1:] + tld)
        elif c == "l":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
        elif c == "i":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
        elif c == "1":
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
    for i in range(1, len(name)):
        perms.add(name[:i] + "-" + name[i:] + tld)
    if "-" in name:
        perms.add(name.replace("-", "") + tld)
    for alt_tld in COMMON_TLDS:
        if alt_tld != tld:
            perms.add(name + alt_tld)
    for prefix in PHISHING_PREFIXES:
        perms.add(prefix + name + tld)
    for suffix in PHISHING_SUFFIXES:
        perms.add(name + suffix + tld)
    perms.add("www" + domain)
    perms.discard(domain)
    return {p for p in perms if p and len(p) > 2}


def _prioritise_candidates(domain: str, candidates: set[str]) -> list[str]:
    """Return up to 60 candidates, highest-risk first."""
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    high, med, low = [], [], []
    for c in candidates:
        if any(c == name + alt for alt in COMMON_TLDS if alt != tld):
            high.append(c)  # TLD swap — most commonly registered by attackers
        elif any(c.startswith(p + name) or c.endswith(name + s)
                 for p in PHISHING_PREFIXES for s in PHISHING_SUFFIXES):
            med.append(c)   # phishing prefix/suffix
        else:
            low.append(c)   # char-level typos
    combined = high + med + low
    return combined[:30]


def _dns_resolves(domain: str, timeout: float = 1.0) -> bool:
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, OSError):
        return False
    finally:
        socket.setdefaulttimeout(old)


def _find_active_lookalikes(candidates: list[str], max_workers: int = 50,
                             overall_timeout: float = 8.0) -> list[str]:
    active = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = {ex.submit(_dns_resolves, d): d for d in candidates}
        done, _ = concurrent.futures.wait(futures, timeout=overall_timeout)
        for fut in done:
            if fut.result():
                active.append(futures[fut])
    finally:
        # wait=False + cancel_futures: don't let this function's total time
        # exceed overall_timeout waiting for stragglers — a plain `with`
        # block's implicit shutdown(wait=True) blocks until every submitted
        # task finishes regardless of the wait() timeout above, which is
        # exactly what pushed a real request past API Gateway's hard 29s
        # ceiling (see _enrich_lookalikes for the incident this fixed).
        ex.shutdown(wait=False, cancel_futures=True)
    return sorted(active)


def _assess_lookalike_intent(domain: str, gsb_api_key: str) -> dict:
    """Per-domain intent signal for a confirmed-active lookalike: GSB verdict
    (active phishing/malware flag), RDAP registration age (recent = opportunistic
    squat, old = plausibly the brand's own defensive registration), and
    Certificate Transparency data (a fresh cert suggests a live hosted site,
    not a parked domain)."""
    gsb_flagged = _check_gsb(domain, gsb_api_key)
    age_days    = _rdap_registration_age_days(domain)
    ct          = _check_ct(domain)
    return {
        "domain":                 domain,
        "gsb_flagged":            gsb_flagged,
        "registration_age_days":  age_days,
        "cert_count":             ct["cert_count"],
        "cert_recent":            ct["recent"],
        "latest_cert_issued":     ct["latest_issued"],
    }


def _enrich_lookalikes(domains: list[str], gsb_api_key: str, max_workers: int = 8,
                        overall_timeout: float = 15.0) -> list[dict]:
    """Runs _assess_lookalike_intent for each active lookalike in parallel.
    Domains whose enrichment doesn't finish within overall_timeout fall back
    to None/unknown fields rather than blocking the whole response.

    max_workers is deliberately modest (8, not 50) — crt.sh starts returning
    429 Too Many Requests once too many CT lookups hit it in parallel from
    one Lambda, and that's worse for total latency than mild serialization.

    Incident 2026-07-18: with a 28s overall_timeout and a plain `with`-block
    ThreadPoolExecutor, one real request (uniswap.org) still took 32.6s
    total and API Gateway's hard 29s integration timeout killed the response
    after the x402 payment had already settled — the caller was charged for
    a check that completed successfully server-side but was never delivered.
    Root cause: `with ThreadPoolExecutor() as ex:` calls shutdown(wait=True)
    on exit, which blocks for every submitted task to finish regardless of
    the wait(timeout=...) call above already having "timed out" and moved
    on. Explicit shutdown(wait=False, cancel_futures=True) below is what
    actually bounds this function's wall-clock time."""
    results: dict[str, dict] = {}
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = {ex.submit(_assess_lookalike_intent, d, gsb_api_key): d for d in domains}
        done, _ = concurrent.futures.wait(futures, timeout=overall_timeout)
        for fut in done:
            d = futures[fut]
            try:
                results[d] = fut.result()
            except Exception as exc:
                logger.warning("Lookalike intent assessment failed for %s: %s", d, exc)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    for d in domains:
        if d not in results:
            results[d] = {
                "domain": d, "gsb_flagged": None, "registration_age_days": None,
                "cert_count": None, "cert_recent": None, "latest_cert_issued": None,
            }
    return [results[d] for d in domains]


def _check_gsb(domain: str, api_key: str) -> bool:
    urls    = [f"http://{domain}/", f"https://{domain}/"]
    payload = json.dumps({
        "client": {"clientId": "relayshield", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes":      ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes":    ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries":    [{"url": u} for u in urls],
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GSB_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return bool(json.loads(resp.read()).get("matches"))
    except Exception as exc:
        logger.warning("GSB check failed for %s: %s", domain, exc)
        return False


def _rdap_registration_age_days(domain: str) -> int | None:
    """Mirrors relayshield_agentic_api.py's / relayshield_telegram_webhook.py's
    helper of the same name."""
    url = f"https://rdap.org/domain/{urllib.parse.quote(domain)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                reg_str = event.get("eventDate", "")
                if reg_str:
                    reg_dt = datetime.fromisoformat(reg_str.replace("Z", "+00:00"))
                    return (datetime.now(timezone.utc) - reg_dt).days
    except Exception as exc:
        logger.warning("RDAP lookup failed for %s: %s", domain, exc)
    return None


def _heuristic_url_check(url: str) -> dict:
    """Fast, VT-independent red-flag check — unifies /v1/scan-url with the
    same three signals Telegram's /scan and WhatsApp's SCAN/ATTACH already
    use: RelayShield's own criminal IOC corpus, Google Safe Browsing's
    real-time blocklist, and very recent domain registration. Added
    2026-07-16. Not as authoritative as a real multi-engine VT verdict —
    callers should word a heuristic-only "flagged" result more cautiously
    than a VT one. Returns {"flagged": bool, "reasons": [str, ...]}."""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        domain = ""

    reasons: list[str] = []
    if not domain:
        return {"flagged": False, "reasons": reasons}

    try:
        table = dynamodb.Table(INTEL_IOCS_TABLE)
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(domain),
            FilterExpression=boto3.dynamodb.conditions.Attr("ioc_type").is_in(["domain", "url"]),
            Limit=5,
        )
        if resp.get("Items"):
            reasons.append("this domain appears in RelayShield's criminal IOC corpus")
    except Exception as exc:
        logger.warning("Heuristic IOC lookup failed domain=%s: %s", domain, exc)

    try:
        if _check_gsb(domain, _gsb_api_key()):
            reasons.append("Google Safe Browsing flags this domain")
    except Exception as exc:
        logger.warning("Heuristic GSB check failed for %s: %s", domain, exc)

    age_days = _rdap_registration_age_days(domain)
    if age_days is not None and age_days < 30:
        reasons.append(f"the domain was registered only {age_days} day{'s' if age_days != 1 else ''} ago")

    return {"flagged": bool(reasons), "reasons": reasons}


def _check_ct(domain: str) -> dict:
    url = CRT_SH_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            certs = json.loads(resp.read())
        if not certs:
            return {"cert_count": 0, "recent": False, "latest_issued": None}
        now   = datetime.now(timezone.utc)
        dates = []
        for cert in certs:
            raw = cert.get("not_before") or cert.get("entry_timestamp", "")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00").split(".")[0])
                    if not dt.tzinfo:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dates.append(dt)
                except Exception:
                    pass
        if not dates:
            return {"cert_count": len(certs), "recent": False, "latest_issued": None}
        latest   = max(dates)
        days_old = (now - latest).days
        return {
            "cert_count":    len(certs),
            "recent":        days_old <= 30,
            "latest_issued": latest.strftime("%-d %b %Y"),
        }
    except Exception as exc:
        logger.warning("CT check failed for %s: %s", domain, exc)
        return {"cert_count": 0, "recent": False, "latest_issued": None}


def handle_cert_expiry(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")

    url = CRT_SH_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            certs = json.loads(resp.read())
    except Exception as exc:
        logger.error("cert-expiry crt.sh lookup failed for %s: %s", domain, exc)
        return _err("certificate lookup failed — upstream error", 502)

    if not certs:
        return _ok({
            "domain":         domain,
            "cert_found":     False,
            "expires_at":     None,
            "days_remaining": None,
            "risk_level":     None,
            "issued_at":      None,
            "recommendation": "No certificates found in Certificate Transparency logs for this domain.",
            "checked_at":     datetime.now(timezone.utc).isoformat(),
        })

    # Find the currently-valid cert: among entries that haven't expired yet,
    # the one with the latest not_before is the one most likely deployed
    # right now (crt.sh can return many historical/duplicate entries for
    # the same domain across CAs and pre-certs).
    now = datetime.now(timezone.utc)

    def _parse(raw: str) -> datetime | None:
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00").split(".")[0])
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    candidates = []
    for cert in certs:
        not_before = _parse(cert.get("not_before", ""))
        not_after  = _parse(cert.get("not_after", ""))
        if not_before and not_after and not_after > now:
            candidates.append((not_before, not_after))

    if not candidates:
        return _ok({
            "domain":         domain,
            "cert_found":     True,
            "expires_at":     None,
            "days_remaining": None,
            "risk_level":     "CRITICAL",
            "issued_at":      None,
            "recommendation": (
                f"Found {len(certs)} historical certificate(s) in CT logs, but none are "
                "currently unexpired — this domain may not have a live, valid certificate right now."
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })

    issued_at, expires_at = max(candidates, key=lambda c: c[0])
    days_remaining = (expires_at - now).days

    if days_remaining <= 7:
        risk_level = "CRITICAL"
    elif days_remaining <= 14:
        risk_level = "HIGH"
    elif days_remaining <= 30:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    recommendation = (
        f"Certificate expires in {days_remaining} day(s) — renew immediately."
        if risk_level in ("CRITICAL", "HIGH") else
        f"Certificate renews in {days_remaining} days — no action needed yet, but confirm your "
        "renewal automation is configured."
        if risk_level == "MEDIUM" else
        f"Certificate is healthy, {days_remaining} days remaining."
    )

    logger.info("cert-expiry domain=%s days_remaining=%d risk=%s", domain, days_remaining, risk_level)
    return _ok({
        "domain":         domain,
        "cert_found":     True,
        "expires_at":     expires_at.isoformat(),
        "days_remaining": days_remaining,
        "risk_level":     risk_level,
        "issued_at":      issued_at.isoformat(),
        "recommendation": recommendation,
        "checked_at":     datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Endpoint: GET /v1/result/{analysis_id}
# ---------------------------------------------------------------------------
# Polls VirusTotal for the result of a previously submitted scan-url or scan-file.
# Returns verdict once completed, or {"status":"pending"} if still processing.

def handle_result(analysis_id: str) -> dict:
    if not analysis_id:
        return _err("analysis_id is required")
    api_key = _vt_api_key()
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data  = json.loads(resp.read())
            attrs = data.get("data", {}).get("attributes", {})
            status = attrs.get("status")
            if status != "completed":
                return _ok({"status": "pending", "analysis_id": analysis_id})
            stats = attrs.get("stats", {})
            return _vt_response(analysis_id, analysis_id, stats)
    except Exception as exc:
        logger.error("VT result poll failed for %s: %s", analysis_id, exc)
        return _err("could not retrieve analysis result", 502)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/oauth-watchlist  /  POST /v1/payg/oauth-watchlist
# ---------------------------------------------------------------------------
# Combined OAuth / token exposure check — two signal sources:
#   1. HIBP breach history × 31-app OAuth watchlist (historical risk)
#   2. INTEL-5 stealer corpus (relayshield_stolen_sessions) — active token theft
#      from stealer log archives captured from criminal Telegram channels
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...",
#   "matched_count": N,           — HIBP-matched breached OAuth apps
#   "matched_apps":  [...],       — breach-source app list with revoke URLs
#   "stolen_token_count": N,      — INTEL-5: credentials found in stealer logs
#   "stolen_tokens": [...],       — service, severity, category, ingested_at
#   "highest_severity": "...",    — CRITICAL|HIGH|MEDIUM|LOW|NONE
#   "recommendation": "...",
#   "checked_at": "..."
# }

def handle_oauth_watchlist(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    # --- Signal 1: HIBP breach × OAuth watchlist ---
    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for oauth-watchlist %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("oauth-watchlist HIBP call failed for %s: %s", email, exc)
        return _err("oauth watchlist check failed — upstream error", 502)

    matched_apps = []
    for b in breaches:
        name   = (b.get("Name")   or "").lower()
        domain = (b.get("Domain") or "").lower()
        title  = (b.get("Title")  or "").lower()
        for app in OAUTH_WATCHLIST:
            if app in name or app in domain or app in title:
                app_name = b.get("Name", "")
                matched_apps.append({
                    "app":          app_name,
                    "source":       "breach_history",
                    "breach_date":  b.get("BreachDate"),
                    "data_classes": b.get("DataClasses", []),
                    "revoke_url":   OAUTH_REVOCATION_URLS.get(
                                        app_name, "https://myaccount.google.com/permissions"
                                    ),
                })
                break

    # --- Signal 2: INTEL-5 stealer log corpus ---
    stolen_tokens: list[dict] = []
    try:
        resp  = dynamodb.Table(STOLEN_SESSIONS_TABLE_API).query(
            IndexName="email-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("matched_email").eq(_sha256(email)),
            FilterExpression=boto3.dynamodb.conditions.Attr("session_type").eq("credential"),
        )
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        raw_tokens = sorted(
            resp.get("Items", []),
            key=lambda x: severity_order.get(x.get("severity", "LOW"), 0),
            reverse=True,
        )
        stolen_tokens = [
            {
                "domain":           t.get("domain", ""),
                "source":           "stealer_log",
                "severity":         t.get("severity", "LOW"),
                "service_category": t.get("service_category", ""),
                "channel_source":   t.get("channel_source", ""),
                "ingested_at":      t.get("ingested_at", ""),
            }
            for t in raw_tokens
        ]
    except Exception as exc:
        logger.warning("oauth-watchlist INTEL-5 query failed email=%s: %s", email, exc)
        # Non-fatal — return HIBP results even if INTEL-5 query fails

    # Derive highest severity across both signals
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}
    intel5_highest = max(
        (severity_order.get(t["severity"], 0) for t in stolen_tokens),
        default=0,
    )
    hibp_severity  = 3 if matched_apps else 0   # HIBP match = HIGH by default
    combined_score = max(intel5_highest, hibp_severity)
    highest = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: "NONE"}.get(combined_score, "NONE")

    # Build recommendation from the most severe signal present
    if stolen_tokens and stolen_tokens[0]["severity"] in ("CRITICAL", "HIGH"):
        rec = (
            "URGENT: Stolen credentials for high-value services were found in criminal stealer logs. "
            "Rotate API keys, revoke OAuth tokens, and invalidate active sessions for all listed services immediately. "
            "For cloud consoles and code repos, treat this as an active incident."
        )
    elif stolen_tokens:
        rec = (
            "Stolen credentials detected in stealer logs. Revoke OAuth tokens and rotate passwords "
            "for all listed services. Check each service's connected-apps or API keys page."
        )
    elif matched_apps:
        rec = (
            "Revoke OAuth access for matched apps immediately using the revoke_url for each. "
            "Also audit all connected apps at myaccount.google.com/permissions and myapps.microsoft.com."
        )
    else:
        rec = "No OAuth exposure detected via breach history or active stealer log corpus."

    logger.info(
        "oauth-watchlist email=%s hibp_matched=%d stolen_tokens=%d highest=%s",
        email, len(matched_apps), len(stolen_tokens), highest,
    )
    return _ok({
        "email":             email,
        "matched_count":     len(matched_apps),
        "matched_apps":      matched_apps,
        "stolen_token_count": len(stolen_tokens),
        "stolen_tokens":     stolen_tokens,
        "highest_severity":  highest,
        "recommendation":    rec,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-wallet  (subscription) / POST /v1/payg/scan-wallet (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "address": "0x..." }
# Response: { "address": "...", "chain_id": "1", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_scan_wallet(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return _err("address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = (params.get("chain_id") or "1").strip()

    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data     = json.loads(resp.read())
            raw      = data.get("result", {}).get(address.lower(), {})
    except Exception as exc:
        logger.error("GoPlus scan failed for %s: %s", address, exc)
        return _err("wallet scan failed — upstream error", 502)

    risk_flags = [k for k, v in raw.items() if v == "1"]
    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("scan-wallet address=%s chain=%s risk=%s flags=%d", address, chain_id, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower(),
        "chain_id":   chain_id,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "raw":        raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/token-security  (subscription) / POST /v1/payg/token-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "chain_id": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "critical_flags": [...], "warning_flags": [...], "raw": {...} }
#
# Supports any GoPlus chain: 1=ETH, 56=BSC, 137=Polygon, 8453=Base, etc.

def _check_lookalike_token(token_symbol: str, contract_address: str) -> dict | None:
    """Cross-check a scanned token's symbol against CoinGecko's verified
    contract registry. Common scam pattern: deploy a token sharing the name/
    symbol of a newly-listed legitimate asset or tokenized stock, under a
    different, unverified contract, hoping buyers mistake it for the real
    thing. Fails open (returns None) on any error — this is an enrichment
    signal, never a reason to break the underlying scan."""
    if not token_symbol:
        return None
    try:
        search_url = f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(token_symbol)}"
        req = urllib.request.Request(search_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            coins = json.loads(resp.read()).get("coins", [])
        matches = [c for c in coins if (c.get("symbol") or "").lower() == token_symbol.lower()]
        if not matches:
            return None
        # Most established match (lowest/best market cap rank) is the likely "real" asset
        matches.sort(key=lambda c: (c.get("market_cap_rank") is None, c.get("market_cap_rank") or 0))
        best    = matches[0]
        coin_id = best.get("id")
        if not coin_id:
            return None

        detail_url = (f"https://api.coingecko.com/api/v3/coins/{coin_id}"
                      f"?localization=false&tickers=false&market_data=false"
                      f"&community_data=false&developer_data=false")
        req2 = urllib.request.Request(detail_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req2, timeout=6) as resp2:
            platforms = json.loads(resp2.read()).get("platforms") or {}

        verified_addrs = {addr.lower() for addr in platforms.values() if addr}
        if not verified_addrs:
            return None  # native coin (no contract) or CoinGecko has no platform data — can't compare

        if contract_address.lower() not in verified_addrs:
            return {
                "verified_name":          best.get("name", ""),
                "verified_coingecko_id":  coin_id,
                "market_cap_rank":        best.get("market_cap_rank"),
            }
        return None
    except Exception as exc:
        logger.warning("lookalike-token check failed symbol=%s: %s", token_symbol, exc)
        return None


def handle_token_security(params: dict) -> dict:
    contract_raw = (params.get("contract_address") or "").strip()
    if not contract_raw:
        return _err("contract_address is required")

    # Detect chain from address format if not supplied
    is_evm    = bool(re.match(r"^0x[0-9a-fA-F]{40}$", contract_raw, re.IGNORECASE))
    is_solana = bool(re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", contract_raw))

    if not is_evm and not is_solana:
        return _err("contract_address must be a valid EVM address (0x + 40 hex) or Solana base58 address")

    # EVM addresses are case-insensitive; Solana base58 is case-sensitive — preserve case
    contract = contract_raw.lower() if is_evm else contract_raw

    # Auto-detect chain_id if caller sends "solana" or omits it
    supplied = str(params.get("chain_id") or "").strip()
    if supplied in ("solana", ""):
        chain_id = "solana" if is_solana else (supplied or "1")
    else:
        chain_id = supplied

    try:
        url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # GoPlus keys result by the address as submitted — try both cases
        result_map = data.get("result") or {}
        raw = result_map.get(contract) or result_map.get(contract.lower()) or result_map.get(contract_raw) or {}
    except Exception as exc:
        logger.error("GoPlus token security failed contract=%s: %s", contract, exc)
        return _err("token security check failed — upstream error", 502)

    # ── DexScreener fallback when GoPlus has no data ─────────────────────────
    # Covers popular tokens on chains GoPlus doesn't fully index (e.g. Avalanche)
    dexscreener_meta = {}
    if not raw:
        try:
            ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
            ds_req = urllib.request.Request(ds_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(ds_req, timeout=8) as ds_resp:
                ds_data = json.loads(ds_resp.read())
            pairs = ds_data.get("pairs") or []
            # Prefer pairs matching the requested chain; fall back to any pair
            _DS_CHAIN_MAP = {
                "1": "ethereum", "56": "bsc", "137": "polygon", "8453": "base",
                "43114": "avalanche", "42161": "arbitrum", "10": "optimism",
                "100": "gnosis", "999": "hyperliquid", "250": "fantom", "25": "cronos",
            }
            preferred_chain = _DS_CHAIN_MAP.get(str(chain_id), "")
            matching = [p for p in pairs if p.get("chainId", "").lower() == preferred_chain] or pairs
            if matching:
                best = matching[0]
                base = best.get("baseToken", {})
                dexscreener_meta = {
                    "token_name":    base.get("name", ""),
                    "token_symbol":  base.get("symbol", ""),
                    "price_usd":     best.get("priceUsd"),
                    "liquidity_usd": (best.get("liquidity") or {}).get("usd"),
                    "volume_24h":    (best.get("volume") or {}).get("h24"),
                    "dex":           best.get("dexId", ""),
                    "chain":         best.get("chainId", ""),
                    "source":        "dexscreener",
                }
                logger.info("token-security DexScreener fallback contract=%s name=%s", contract, base.get("name"))
        except Exception as ds_exc:
            logger.warning("DexScreener fallback failed contract=%s: %s", contract, ds_exc)

    _CRITICAL = {
        "is_honeypot":     "honeypot",
        "is_airdrop_scam": "airdrop scam",
        "fake_token":      "fake token",
    }
    _WARNINGS = {
        "transfer_pausable":       "transfers can be paused",
        "hidden_owner":            "hidden owner",
        "can_take_back_ownership": "owner can reclaim contract",
        "is_mintable":             "mintable supply",
        "external_call":           "external call risk",
    }

    critical_flags = [label for k, label in _CRITICAL.items() if str(raw.get(k, "0")) == "1"]
    warning_flags  = [label for k, label in _WARNINGS.items() if str(raw.get(k, "0")) == "1"]

    # Sell tax — critical if >=50%, warning if >=10%
    try:
        sell_tax = float(raw.get("sell_tax", 0))
        if sell_tax >= 0.5:
            critical_flags.append(f"sell tax {sell_tax*100:.0f}%")
        elif sell_tax >= 0.1:
            warning_flags.append(f"sell tax {sell_tax*100:.0f}%")
    except (TypeError, ValueError):
        pass

    risk_level = "HIGH" if critical_flags else "MEDIUM" if warning_flags else "LOW"

    token_name   = raw.get("token_name", "")   or dexscreener_meta.get("token_name", "")
    token_symbol = raw.get("token_symbol", "") or dexscreener_meta.get("token_symbol", "")

    lookalike = _check_lookalike_token(token_symbol, contract)
    if lookalike:
        warning_flags.append(
            f"name/symbol matches verified asset '{lookalike['verified_name']}' "
            f"(CoinGecko #{lookalike['market_cap_rank'] or '?'}) but this contract isn't its verified address — possible impersonation"
        )
        if risk_level == "LOW":
            risk_level = "MEDIUM"

    logger.info("token-security contract=%s chain=%s risk=%s name=%s", contract, chain_id, risk_level, token_name)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "critical_flags":   critical_flags,
        "warning_flags":    warning_flags,
        "token_name":       token_name,
        "token_symbol":     token_symbol,
        "holder_count":     raw.get("holder_count"),
        "dexscreener":      dexscreener_meta or None,
        "lookalike_check":  lookalike,
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/nft-security  (subscription) / POST /v1/payg/nft-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_nft_security(params: dict) -> dict:
    contract = (params.get("contract_address") or "").strip().lower()
    if not contract:
        return _err("contract_address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", contract):
        return _err("contract_address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = str(params.get("chain_id") or "1").strip()

    try:
        # chain_id is a path segment, not a query param (GoPlus's NFT security
        # endpoint differs from their token-security endpoint in this respect —
        # confirmed 2026-07-04 against a live BAYC lookup after the old
        # ?chain_id= form started 404ing).
        url = f"{GOPLUS_NFT_URL}/{chain_id}?contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = data.get("result") or {}
    except Exception as exc:
        logger.error("GoPlus NFT security failed contract=%s: %s", contract, exc)
        return _err("NFT security check failed — upstream error", 502)

    def _privileged(field: str) -> bool:
        # These fields are objects — {owner_address, value, owner_type} — not
        # simple booleans. owner_type "blackhole" means the privilege was
        # renounced to an unowned address (safe) even if the contract code
        # still technically has the capability. Only flag when a real,
        # non-renounced owner holds a nonzero privilege.
        obj = raw.get(field)
        if not isinstance(obj, dict):
            return False
        return bool(obj.get("value")) and obj.get("owner_type") != "blackhole"

    risk_flags = []
    if str(raw.get("malicious_nft_contract", "0")) == "1":
        risk_flags.append("flagged as malicious NFT contract")
    if _privileged("privileged_burn"):
        risk_flags.append("owner can burn tokens")
    if _privileged("privileged_minting"):
        risk_flags.append("owner retains minting privilege")
    if _privileged("transfer_without_approval"):
        risk_flags.append("owner can transfer tokens without approval")
    if _privileged("self_destruct"):
        risk_flags.append("contract can self-destruct")
    if str(raw.get("restricted_approval", "0")) == "1":
        risk_flags.append("approvals restricted to specific addresses")

    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("nft-security contract=%s chain=%s risk=%s", contract, chain_id, risk_level)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "risk_flags":       risk_flags,
        "nft_name":         raw.get("nft_name", ""),
        "nft_symbol":       raw.get("nft_symbol", ""),
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/crypto-intel  (Stripe metered — $0.30/call)
# ---------------------------------------------------------------------------
# Composite asset-surface intelligence: address risk + optional token risk,
# synthesised into a single risk object with cross-surface correlation advisories.
#
# Request:  { "address": "0x...",            # required — wallet or EOA
#             "token_address": "0x...",       # optional — token/contract to check
#             "chain_id": "1" }              # optional — default ETH mainnet
#
# Response: { "address": "...", "chain_id": "...",
#             "composite_risk": "LOW|MEDIUM|HIGH|CRITICAL",
#             "address_flags": [...], "token_risk": {...},
#             "correlation_advisories": [...] }

_ADDR_CRITICAL = {"phishing_activities", "blacklist_doubt", "honeypot_related_address",
                  "cybercrime", "money_laundering", "sanctioned"}
_ADDR_WARNING  = {"darkweb_transactions", "fake_kyc", "gas_abuse"}

def handle_crypto_intel(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return _err("address must be a valid EVM address (0x + 40 hex chars)")

    chain_id      = str(params.get("chain_id") or "1").strip()
    token_address = (params.get("token_address") or "").strip().lower()

    # --- Address security (GoPlus address_security) ---
    address_flags    = []
    address_critical = False
    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            addr_raw = json.loads(resp.read()).get("result", {}).get(address.lower(), {})
        for k, v in addr_raw.items():
            if v == "1":
                address_flags.append(k)
                if k in _ADDR_CRITICAL:
                    address_critical = True
    except Exception as exc:
        logger.error("crypto-intel address_security failed address=%s: %s", address, exc)
        addr_raw = {}

    # --- Token security (GoPlus token_security) — only if token_address supplied ---
    token_result = None
    token_critical = False
    token_high     = False
    if token_address and re.match(r"^0x[0-9a-fA-F]{40}$", token_address):
        try:
            url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={token_address}"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tok_raw = json.loads(resp.read()).get("result", {}).get(token_address, {})

            tok_critical = []
            tok_warnings = []
            for k, label in [("is_honeypot", "honeypot"), ("is_airdrop_scam", "airdrop scam"),
                              ("fake_token", "fake token")]:
                if str(tok_raw.get(k, "0")) == "1":
                    tok_critical.append(label)
            for k, label in [("transfer_pausable", "transfers pausable"),
                              ("is_mintable", "mintable supply"),
                              ("hidden_owner", "hidden owner")]:
                if str(tok_raw.get(k, "0")) == "1":
                    tok_warnings.append(label)
            try:
                sell_tax = float(tok_raw.get("sell_tax", 0))
                if sell_tax >= 0.5:
                    tok_critical.append(f"sell tax {sell_tax*100:.0f}%")
                elif sell_tax >= 0.1:
                    tok_warnings.append(f"sell tax {sell_tax*100:.0f}%")
            except (TypeError, ValueError):
                pass

            token_critical = bool(tok_critical)
            token_high     = bool(tok_warnings)
            token_result   = {
                "contract_address": token_address,
                "token_name":       tok_raw.get("token_name", ""),
                "token_symbol":     tok_raw.get("token_symbol", ""),
                "critical_flags":   tok_critical,
                "warning_flags":    tok_warnings,
            }
        except Exception as exc:
            logger.error("crypto-intel token_security failed contract=%s: %s", token_address, exc)

    # --- Composite risk ---
    if address_critical or token_critical:
        composite_risk = "CRITICAL"
    elif address_flags or token_high:
        composite_risk = "HIGH"
    elif set(address_flags) & _ADDR_WARNING:
        composite_risk = "MEDIUM"
    else:
        composite_risk = "LOW"

    # --- Cross-surface correlation advisories ---
    advisories = []
    if address_critical:
        advisories.append(
            "CRITICAL: This address appears in phishing/sanctions/cybercrime databases. "
            "If the associated account owner has an active SIM swap, call /v1/metered/sim-swap — "
            "this combination indicates an in-progress coordinated crypto theft chain."
        )
    if token_critical:
        advisories.append(
            "CRITICAL: Token contract shows honeypot or scam indicators. "
            "Cross-reference with /v1/metered/infostealer if the wallet owner's email is known — "
            "device credential theft is a common precursor to honeypot-targeted asset drain."
        )
    if address_flags and not advisories:
        advisories.append(
            "ELEVATED: Address has risk flags. Recommend also checking "
            "/v1/metered/breach on the account email and /v1/metered/sim-swap on the associated "
            "phone number to detect coordinated identity + asset attack chains."
        )
    if not advisories:
        advisories.append(
            "No risk signals detected on this address. For complete protection, monitor "
            "the associated email via /v1/metered/breach and phone via /v1/metered/sim-swap."
        )

    logger.info("crypto-intel address=%s chain=%s risk=%s addr_flags=%d token=%s",
                address, chain_id, composite_risk, len(address_flags),
                token_result["token_symbol"] if token_result else "none")

    result = {
        "address":                address.lower(),
        "chain_id":               chain_id,
        "composite_risk":         composite_risk,
        "address_flags":          address_flags,
        "correlation_advisories": advisories,
    }
    if token_result:
        result["token_risk"] = token_result
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/wallet-risk  (subscription) / POST /v1/payg/wallet-risk (PAYG)
# ---------------------------------------------------------------------------
# Multi-chain wallet risk: EVM and Solana via GoPlus, TON via TONAPI v2,
# Bitcoin via Blockstream heuristics. Chain is auto-detected from address format.
#
# Request:  { "address": "0x...|SolanaAddr|EQTonAddr" }
# Response: { "address": "...", "chain": "evm|solana|ton|bitcoin",
#             "risk_level": "LOW|MEDIUM|HIGH", "risk_flags": [...],
#             "metadata": {...} }

_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}

def _detect_chain_api(address: str) -> str:
    if re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return "evm"
    if re.match(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$", address):
        return "ton"
    if re.match(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$", address):
        return "bitcoin"
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address):
        return "solana"
    return "unknown"


def handle_wallet_risk(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        logger.warning("wallet-risk: missing address — params keys=%s raw=%r", list(params.keys()), params)
        return _err("address is required")

    chain = _detect_chain_api(address)
    if chain == "unknown":
        logger.warning("wallet-risk: unknown chain — address=%r len=%d", address, len(address))
        return _err("unrecognised address format — supported: EVM (0x), Solana, TON (EQ.../UQ...), Bitcoin")

    risk_flags = []
    metadata   = {}

    if chain == "bitcoin":
        try:
            btc_url = f"https://blockstream.info/api/address/{address}"
            req = urllib.request.Request(btc_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                btc_data = json.loads(resp.read())
            chain_stats  = btc_data.get("chain_stats", {})
            mempool_stats = btc_data.get("mempool_stats", {})
            tx_count     = chain_stats.get("tx_count", 0)
            funded_sum   = chain_stats.get("funded_txo_sum", 0)
            spent_sum    = chain_stats.get("spent_txo_sum", 0)
            balance_sats = funded_sum - spent_sum
            mempool_txs  = mempool_stats.get("tx_count", 0)

            if tx_count == 0:
                risk_flags.append("never_used")
            if tx_count > 500:
                risk_flags.append("high_tx_volume")
            if balance_sats == 0 and tx_count > 10:
                risk_flags.append("zero_balance_high_activity")
            if 0 < balance_sats < 1000:
                risk_flags.append("dust_balance")
            if mempool_txs > 0:
                risk_flags.append("unconfirmed_transactions")

            metadata["tx_count"]      = tx_count
            metadata["balance_sats"]  = balance_sats
            metadata["balance_btc"]   = round(balance_sats / 100_000_000, 8)
            metadata["mempool_txs"]   = mempool_txs
            metadata["explorer"]      = f"https://mempool.space/address/{address}"
        except Exception as exc:
            logger.error("Blockstream wallet-risk failed address=%s: %s", address, exc)
            metadata["blockstream_error"] = "upstream unavailable"

        risk_level = "HIGH" if "zero_balance_high_activity" in risk_flags or "high_tx_volume" in risk_flags \
            else "MEDIUM" if risk_flags else "LOW"
        logger.info("wallet-risk address=%s chain=bitcoin risk=%s flags=%d", address, risk_level, len(risk_flags))
        return _ok({
            "address":    address,
            "chain":      "bitcoin",
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "metadata":   metadata,
        })

    if chain in ("evm", "solana"):
        goplus_chain_id = _GOPLUS_CHAIN_IDS[chain]
        try:
            url = f"{GOPLUS_BASE_URL}/{address}?chain_id={goplus_chain_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            raw = data.get("result", {})
            _MALICIOUS = {
                "phishing_activities":  "linked to phishing",
                "blacklist_doubt":      "security blacklisted",
                "darkweb_transactions": "dark web activity",
                "stealing_attack":      "stealing attacks",
                "cybercrime":           "cybercrime",
            }
            risk_flags = [label for k, label in _MALICIOUS.items() if raw.get(k) == "1"]
        except Exception as exc:
            logger.error("GoPlus wallet-risk failed address=%s: %s", address, exc)
            metadata["goplus_error"] = "upstream unavailable"

    elif chain == "ton":
        try:
            ton_url = TONAPI_ACCOUNTS_URL.format(
                address=urllib.parse.quote(address, safe="-_=")
            )
            req = urllib.request.Request(ton_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ton_data = json.loads(resp.read())
            if ton_data.get("is_scam"):
                risk_flags.append("flagged as scam in TON community database")
            metadata["contract_type"]  = ton_data.get("interfaces", [])
            metadata["account_status"] = ton_data.get("status", "")
        except Exception as exc:
            logger.error("TONAPI wallet-risk failed address=%s: %s", address, exc)
            metadata["tonapi_error"] = "upstream unavailable"

    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"
    logger.info("wallet-risk address=%s chain=%s risk=%s flags=%d", address, chain, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower() if chain == "evm" else address,
        "chain":      chain,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "metadata":   metadata,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/wallet-screen-batch  (PAYG only — $0.50 for up to 10)
# ---------------------------------------------------------------------------
# Screens up to 10 addresses in parallel. Mixed chains supported.
#
# Request:  { "addresses": ["0x...", "SolAddr", "EQTonAddr"] }
# Response: { "results": [ { "address": "...", "chain": "...",
#                             "risk_level": "...", "risk_flags": [...] }, ... ] }

def handle_wallet_screen_batch(params: dict) -> dict:
    addresses = params.get("addresses") or []
    if not isinstance(addresses, list) or not addresses:
        return _err("addresses must be a non-empty list")
    if len(addresses) > 10:
        return _err("maximum 10 addresses per batch request")
    addresses = [str(a).strip() for a in addresses if str(a).strip()]

    def _screen_one(addr: str) -> dict:
        result = handle_wallet_risk({"address": addr})
        body   = json.loads(result.get("body", "{}"))
        data   = body.get("data", {})
        return {
            "address":    data.get("address", addr),
            "chain":      data.get("chain", "unknown"),
            "risk_level": data.get("risk_level", "UNKNOWN"),
            "risk_flags": data.get("risk_flags", []),
            "error":      body.get("error") if not body.get("ok") else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_screen_one, addresses))

    high_count = sum(1 for r in results if r["risk_level"] == "HIGH")
    logger.info("wallet-screen-batch count=%d high_risk=%d", len(addresses), high_count)
    return _ok({
        "screened":   len(results),
        "high_risk":  high_count,
        "results":    results,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/infostealer  (PAYG only — $0.15)
# ---------------------------------------------------------------------------
# Checks an email address against Hudson Rock Cavalier (free, no API key).
# Returns whether the email appears in infostealer logs, and summary details
# about compromised machines.
#
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "found": true/false, "stealer_count": N,
#             "stealers": [ { "date_compromised": "...", "computer_name": "...",
#                             "operating_system": "...", "malware_path": "...",
#                             "total_corporate_services": N,
#                             "total_user_services": N } ] }

CAVALIER_URL        = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-login"
CAVALIER_DOMAIN_URL = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-domain"


def handle_infostealer(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    encoded_email = urllib.parse.quote(email, safe="")
    url = f"{CAVALIER_URL}?email={encoded_email}"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Hudson Rock returns 404 when email is not found
            return _ok({"email": email, "found": False, "stealer_count": 0, "stealers": []})
        logger.error("Cavalier API HTTP error: %s", exc)
        return _err(f"infostealer check failed: HTTP {exc.code}", 502)
    except Exception as exc:
        logger.error("Cavalier API error: %s", exc)
        return _err("infostealer check failed: upstream error", 502)

    stealers_raw = raw.get("stealers", [])
    stealers = []
    for s in stealers_raw:
        stealers.append({
            "date_compromised":         s.get("date_compromised"),
            "computer_name":            s.get("computer_name"),
            "operating_system":         s.get("operating_system"),
            "malware_path":             s.get("malware_path"),
            "total_corporate_services": s.get("total_corporate_services", 0),
            "total_user_services":      s.get("total_user_services", 0),
        })

    found = len(stealers) > 0
    logger.info("infostealer email=%s found=%s count=%d", email, found, len(stealers))
    return _ok({
        "record_type":   "credential_exposure",
        "email":         email,
        "found":         found,
        "stealer_count": len(stealers),
        "stealers":      stealers,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/supply-chain  /  POST /v1/payg/supply-chain
# ---------------------------------------------------------------------------
# Supply chain / vendor identity risk monitoring.
# For each vendor domain supplied, checks:
#   1. HIBP breacheddomain — how many accounts at that domain appeared in breaches
#   2. Hudson Rock Cavalier — infostealer log hits for that domain
#
# Billing: $0.10 per domain checked (PAYG) / 10 credits per domain (metered).
# For PAYG callers the x402 payment covers up to MAX_VENDOR_DOMAINS domains
# in one call. Metered callers are billed once per call regardless of domain count
# (up to the per-call maximum); the credit cost reflects one unit of work.
#
# Request:
#   { "vendor_domains": ["acme.com", "widget.io"] }          — explicit domain list
#   { "vendor_emails":  ["alice@acme.com", "bob@widget.io"] } — domains extracted
#   Both keys may be supplied; they are merged and deduplicated.
#   Maximum MAX_VENDOR_DOMAINS domains per call.
#
# Response per domain:
#   {
#     "domain":              "acme.com",
#     "breach_count":        3,
#     "breached_accounts":   12,         # distinct email prefixes seen across breaches
#     "breach_names":        ["Adobe", "LinkedIn", ...],
#     "infostealer_found":   true,
#     "infostealer_count":   2,          # infected machines linked to this domain
#     "risk_level":          "HIGH",     # CRITICAL | HIGH | MEDIUM | LOW | CLEAN
#     "risk_factors":        ["active_stealer_logs", "multiple_breaches"],
#     "recommendation":      "...",
#   }

HIBP_DOMAIN_URL   = "https://haveibeenpwned.com/api/v3/breacheddomain/{domain}"
MAX_VENDOR_DOMAINS = 10

# Risk scoring — both signals contribute independently
_CREDENTIAL_DATA_CLASSES = {
    "Passwords", "Password hints", "Auth tokens", "Security questions and answers",
    "PIN numbers", "Private messages", "Social media profiles",
}

def _supply_chain_risk(
    breach_count: int,
    breached_accounts: int,
    stealer_count: int,
    all_data_classes: list[str] | None = None,
) -> tuple[str, list[str]]:
    factors: list[str] = []
    score = 0

    if stealer_count > 0:
        factors.append("active_stealer_logs")
        score += 40 if stealer_count >= 3 else 30

    if breach_count >= 5:
        factors.append("many_breaches")
        score += 20
    elif breach_count >= 2:
        factors.append("multiple_breaches")
        score += 10
    elif breach_count == 1:
        factors.append("one_breach")
        score += 5

    if breached_accounts >= 50:
        factors.append("high_account_exposure")
        score += 20
    elif breached_accounts >= 10:
        factors.append("moderate_account_exposure")
        score += 10

    # Credential/password data classes dramatically raise account takeover risk
    if all_data_classes:
        matched = _CREDENTIAL_DATA_CLASSES.intersection(set(all_data_classes))
        if matched:
            factors.append("credential_data_exposed")
            score += 20

    if score >= 60:
        level = "CRITICAL"
    elif score >= 35:
        level = "HIGH"
    elif score >= 15:
        level = "MEDIUM"
    elif score > 0:
        level = "LOW"
    else:
        level = "CLEAN"

    return level, factors


def _check_vendor_domain(domain: str, hibp_key: str) -> dict:
    """Run HIBP domain breach check + Cavalier infostealer check for one vendor domain."""
    # --- HIBP domain breach check ---
    breach_count      = 0
    breached_accounts = 0
    breach_names: list[str] = []
    all_data_classes: list[str] = []
    try:
        # Public endpoint — no domain ownership verification required
        req = urllib.request.Request(
            f"https://haveibeenpwned.com/api/v3/breaches?domain={urllib.parse.quote(domain, safe='')}",
            headers={"User-Agent": "RelayShield-SupplyChain/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches_list = json.loads(resp.read())
        breach_count      = len(breaches_list) if isinstance(breaches_list, list) else 0
        breached_accounts = sum(b.get("PwnCount", 0) for b in breaches_list) if isinstance(breaches_list, list) else 0
        breach_names      = [b.get("Name", "") for b in breaches_list] if isinstance(breaches_list, list) else []
        all_data_classes  = list({dc for b in breaches_list for dc in b.get("DataClasses", [])}) if isinstance(breaches_list, list) else []
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning("HIBP breach check failed domain=%s status=%d", domain, exc.code)
    except Exception as exc:
        logger.warning("HIBP breach check error domain=%s: %s", domain, exc)

    # --- Cavalier infostealer domain check ---
    stealer_count = 0
    stealer_dates: list[str] = []
    try:
        url = f"{CAVALIER_DOMAIN_URL}?domain={urllib.parse.quote(domain, safe='')}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-SupplyChain/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            cav_data      = json.loads(resp.read())
        stealers      = cav_data.get("stealers", [])
        stealer_count = len(stealers)
        stealer_dates = [s.get("date_compromised", "") for s in stealers[:5] if s.get("date_compromised")]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning("Cavalier domain check failed domain=%s status=%d", domain, exc.code)
    except Exception as exc:
        logger.warning("Cavalier domain check error domain=%s: %s", domain, exc)

    risk_level, risk_factors = _supply_chain_risk(breach_count, breached_accounts, stealer_count, all_data_classes)

    rec_map = {
        "CRITICAL": (
            "Immediate action required. Active infostealer infections at this vendor mean credentials "
            "they hold for your systems may be compromised right now. Rotate any shared secrets, "
            "revoke API tokens, and request an incident report from this vendor."
        ),
        "HIGH": (
            "High risk. This vendor has significant breach and/or infostealer exposure. "
            "Audit their access to your systems, enforce MFA on any shared portals, "
            "and consider reducing their permission scope."
        ),
        "MEDIUM": (
            "Moderate risk. This vendor has some breach history. Review what data and access "
            "they hold in your environment and confirm they are following credential hygiene practices."
        ),
        "LOW": (
            "Low risk. Minor breach exposure detected. No immediate action required "
            "but include in your next vendor security review cycle."
        ),
        "CLEAN": "No breach or infostealer exposure found for this vendor domain.",
    }

    result = {
        "domain":            domain,
        "breach_count":      breach_count,
        "breached_accounts": breached_accounts,
        "breach_names":      breach_names[:10],   # cap list length in response
        "infostealer_found": stealer_count > 0,
        "infostealer_count": stealer_count,
        "risk_level":        risk_level,
        "risk_factors":      risk_factors,
        "recommendation":    rec_map[risk_level],
    }
    if stealer_dates:
        result["infostealer_dates"] = stealer_dates
    return result


def handle_supply_chain(params: dict) -> dict:
    # Collect domains from both input keys
    raw_domains: list[str] = list(params.get("vendor_domains") or [])
    raw_emails:  list[str] = list(params.get("vendor_emails")  or [])

    # Extract domain portion from any email addresses supplied
    for email in raw_emails:
        email = email.strip().lower()
        if "@" in email:
            raw_domains.append(email.split("@", 1)[1])

    # Normalise + deduplicate
    domains = list({d.strip().lower() for d in raw_domains if d.strip()})

    if not domains:
        return _err("supply_chain requires at least one entry in vendor_domains or vendor_emails")
    if len(domains) > MAX_VENDOR_DOMAINS:
        return _err(f"maximum {MAX_VENDOR_DOMAINS} vendor domains per call; {len(domains)} supplied")

    hibp_key = _hibp_api_key()
    results  = []
    for domain in domains:
        results.append(_check_vendor_domain(domain, hibp_key))

    # Aggregate summary
    risk_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}
    highest    = max(results, key=lambda r: risk_order.get(r["risk_level"], 0))
    critical   = [r["domain"] for r in results if r["risk_level"] == "CRITICAL"]
    high       = [r["domain"] for r in results if r["risk_level"] == "HIGH"]

    logger.info(
        "supply-chain domains=%d critical=%d high=%d",
        len(domains), len(critical), len(high),
    )
    # Enhancement 7: Vendor dark web composite score (0–100)
    def _composite_score(r: dict) -> int:
        score = 0
        if r.get("infostealer_found"):
            score += 40 + min(r.get("infostealer_count", 0) * 5, 20)
        bc = r.get("breach_count", 0)
        if bc >= 5:    score += 20
        elif bc >= 2:  score += 12
        elif bc == 1:  score += 6
        ae = r.get("breached_accounts", 0)
        if ae >= 50:   score += 15
        elif ae >= 10: score += 8
        return min(score, 100)

    for r in results:
        r["dark_web_score"] = _composite_score(r)

    results.sort(key=lambda r: r["dark_web_score"], reverse=True)

    return _ok({
        "domains_checked":   len(domains),
        "highest_risk":      highest["risk_level"],
        "critical_vendors":  critical,
        "high_risk_vendors": high,
        "results":           results,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# INTEL-5 shared data — service severity classification (mirrors intel_monitor)
# ---------------------------------------------------------------------------

_INTEL5_SEVERITY: list[tuple[str, str, list[str]]] = [
    ("CRITICAL", "Cloud Infrastructure",       ["console.aws.amazon.com", "console.cloud.google.com", "portal.azure.com", "app.cloudflare.com", "cloudflare.com"]),
    ("CRITICAL", "Code Repository / CI-CD",    ["github.com", "gitlab.com", "bitbucket.org", "app.circleci.com", "app.travis-ci.com", "argocd"]),
    ("CRITICAL", "Identity Provider",          ["okta.com", "auth0.com", "login.microsoftonline.com", "admin.google.com", "accounts.google.com"]),
    ("HIGH",     "Payment Processor",          ["dashboard.stripe.com", "paypal.com", "braintreegateway.com"]),
    ("HIGH",     "Domain Registrar / DNS",     ["godaddy.com", "namecheap.com", "name.com", "porkbun.com", "domains.google.com", "dnsimple.com"]),
    ("HIGH",     "Security Tooling",           ["falcon.crowdstrike.com", "app.datadoghq.com", "app.pagerduty.com", "splunk.com", "sentinelone.com"]),
    ("HIGH",     "Financial / Accounting",     ["quickbooks.intuit.com", "xero.com", "app.gusto.com"]),
    ("MEDIUM",   "Developer / Infra SaaS",     ["vercel.com", "app.netlify.com", "heroku.com", "render.com", "digitalocean.com"]),
    ("MEDIUM",   "Productivity / CRM SaaS",    ["slack.com", "notion.so", "app.hubspot.com", "salesforce.com", "linear.app", "atlassian.net", "jira.com"]),
    ("MEDIUM",   "Communication",              ["zoom.us", "teams.microsoft.com", "discord.com"]),
    ("LOW",      "Consumer / Social",          ["twitter.com", "x.com", "facebook.com", "instagram.com", "reddit.com", "linkedin.com"]),
]


def _intel5_classify(domain: str) -> tuple[str, str]:
    domain = domain.lower().lstrip(".")
    for severity, label, patterns in _INTEL5_SEVERITY:
        for pat in patterns:
            if pat in domain:
                return severity, label
    return "LOW", "General Web Service"


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/session-risk  /  POST /v1/payg/session-risk
# ---------------------------------------------------------------------------
# Queries the INTEL-5 stolen-sessions corpus (relayshield_stolen_sessions)
# for active session hijack findings linked to the supplied email address.
# Returns categorized stolen sessions with severity scores.
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...",
#   "found": true/false,
#   "session_count": N,
#   "highest_severity": "CRITICAL|HIGH|MEDIUM|LOW",
#   "sessions": [
#     { "domain": "github.com", "session_type": "cookie", "cookie_name": "user_session",
#       "severity": "CRITICAL", "service_category": "Code Repository / CI-CD",
#       "channel_source": "logsmarket", "ingested_at": "..." }
#   ]
# }

STOLEN_SESSIONS_TABLE_API = "relayshield_stolen_sessions"


def handle_session_risk(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    # GSI key stores SHA-256 hash of email, not plaintext
    email_hash = _sha256(email)
    try:
        table = dynamodb.Table(STOLEN_SESSIONS_TABLE_API)
        resp  = table.query(
            IndexName="email-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("matched_email").eq(email_hash),
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("session-risk DynamoDB query failed email=%s: %s", email, exc)
        return _err("session risk query failed — internal error", 500)

    if not items:
        return _ok({
            "email":            email,
            "record_type":      "credential_exposure",
            "found":            False,
            "session_count":    0,
            "highest_severity": None,
            "sessions":         [],
        })

    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sessions = sorted(items, key=lambda x: severity_order.get(x.get("severity", "LOW"), 0), reverse=True)

    highest = sessions[0].get("severity", "LOW") if sessions else "LOW"

    result_sessions = [
        {
            "domain":           s.get("domain", ""),
            "session_type":     s.get("session_type", ""),
            "cookie_name":      s.get("cookie_name", ""),
            "severity":         s.get("severity", "LOW"),
            "service_category": s.get("service_category", ""),
            "channel_source":   s.get("channel_source", ""),
            "ingested_at":      s.get("ingested_at", ""),
        }
        for s in sessions
    ]

    logger.info("session-risk email=%s found=%d highest=%s", email, len(sessions), highest)
    return _ok({
        "email":            email,
        "found":            True,
        "session_count":    len(sessions),
        "highest_severity": highest,
        "sessions":         result_sessions,
        "action_required":  (
            "IMMEDIATE: Log out of all listed services from a clean device and revoke active sessions. "
            "Changing your password alone is insufficient — stolen session cookies bypass 2FA and "
            "remain valid until explicitly invalidated."
        ),
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/identity-graph  /  POST /v1/payg/identity-graph
# ---------------------------------------------------------------------------
# Identity correlation — links an email to associated phones, usernames, and
# domains seen alongside it in criminal channel dumps. Built from co-occurrence
# data extracted by the INTEL-2 monitor (relayshield_identity_graph table).
#
# Customer value:
#   • Pivot from one compromised identifier to find all others exposed in same dump
#   • Correlation engine signal: if linked phone is SIM-swapped, alert email holder
#   • B2A incident responders: full identity surface from a single compromised email
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...", "found": bool, "correlated_identifiers": N,
#   "correlated_phones": [...], "correlated_domains": [...],
#   "sources": [...], "checked_at": "..."
# }

IDENTITY_GRAPH_TABLE_API = "relayshield_identity_graph"


def handle_identity_graph(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    # Query by SHA-256 hash of email (PK stores hash, not plaintext)
    anchor_hash = _sha256(email)
    try:
        resp  = dynamodb.Table(IDENTITY_GRAPH_TABLE_API).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("anchor").eq(anchor_hash),
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("identity-graph query failed email=%s: %s", email, exc)
        return _err("identity graph query failed — internal error", 500)

    if not items:
        return _ok({
            "email":                   email,
            "found":                   False,
            "correlated_identifiers":  0,
            "correlated_phones":       [],
            "correlated_domains":      [],
            "sources":                 [],
            "checked_at":              datetime.now(timezone.utc).isoformat(),
        })

    # Decrypt correlated values from KMS ciphertext
    phones  = []
    domains = []
    for i in items:
        enc = i.get("correlated_encrypted", "")
        raw = i.get("correlated_id", "")
        corr_type = i.get("correlated_type", "")
        if enc:
            try:
                raw = _kms_decrypt(enc)
            except Exception:
                raw = "[decrypt error]"
        if corr_type == "phone":
            phones.append(raw)
        elif corr_type == "domain":
            domains.append(raw)
    phones  = list(set(phones))
    domains = list(set(domains))
    sources = list({i.get("source", "") for i in items if i.get("source")})

    logger.info("identity-graph email=%s phones=%d domains=%d", email, len(phones), len(domains))
    return _ok({
        "email":                   email,
        "found":                   True,
        "correlated_identifiers":  len(phones) + len(domains),
        "correlated_phones":       phones,
        "correlated_domains":      domains,
        "sources":                 sources,
        "recommendation": (
            "All listed identifiers were found alongside this email in criminal channel dumps. "
            "Treat each as potentially compromised — change passwords and check accounts linked to "
            "any of the correlated phone numbers or domains."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# STIX/TAXII 2.1 — /v1/intel/taxii/*
# ---------------------------------------------------------------------------
# TAXII 2.1 compliant feed of RelayShield IOCs as STIX 2.1 Indicator objects.
# Enterprise SIEMs (Splunk, Sentinel, Elastic, QRadar) can point their built-in
# TAXII client at this endpoint and pull IOCs on a schedule automatically.
#
# Requires TI subscription API key (intel_access flag).
#
# TAXII 2.1 endpoints:
#   GET /v1/intel/taxii/             — server discovery
#   GET /v1/intel/taxii/collections/ — available collections
#   GET /v1/intel/taxii/collections/iocs/objects/ — STIX Indicator objects
#     ?added_after=<ISO8601>          — only IOCs added after this timestamp
#     ?limit=<N>                      — page size (default 500, max 2000)
#     ?next=<cursor>                  — pagination cursor

import uuid as _uuid_mod


def _intel_api_key(headers: dict) -> str:
    """Extract the RelayShield API key from any accepted header form.

    Added 2026-07-29. Elastic's only generic STIX/TAXII integration is
    `ti_custom` ("Custom Threat Intelligence"), and it can ONLY authenticate by
    sending `Authorization: <key_type> <api_key>` -- its `key_type` var sets the
    scheme inside an Authorization header and there is no field to name a custom
    header. Accepting X-RS-API-KEY alone therefore made our TAXII feed
    impossible to consume from Elastic, which is what the published integration
    guide told customers to do. Note there is no generic "Threat Intel TAXII
    2.x" package in the Elastic registry at all -- verified across all 14,491
    package entries in EPR.

    Purely additive: every header that worked before still works.
    """
    key = _header(headers, "X-RS-API-KEY") or _header(headers, "X-API-Key")
    if key:
        return key

    auth = _header(headers, "Authorization").strip()
    if not auth:
        return ""
    parts = auth.split(None, 1)
    if len(parts) != 2:
        # A bare "<key>" with no scheme.
        return parts[0].strip()

    scheme, rest = parts[0].strip(), parts[1].strip()

    # HTTP Basic, added 2026-07-29 to unblock Microsoft Sentinel. Sentinel's
    # "Threat Intelligence - TAXII" data connector offers only Username and
    # Password fields -- no API key field, no bearer token, no custom header --
    # so Basic is the ONLY way it can authenticate. Verified against Microsoft's
    # connector documentation before building, rather than after publishing a
    # guide that could not work (see the Elastic ti_custom incident).
    #
    # The key is accepted in either field so the guide can tell customers to put
    # it wherever is convenient: username=<key> with any password, or any
    # username with password=<key>.
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(rest + "=" * (-len(rest) % 4)).decode("utf-8", "replace")
        except Exception:
            return ""
        user, _, pwd = decoded.partition(":")
        for candidate in (user.strip(), pwd.strip()):
            if candidate.startswith("rs_"):
                return candidate
        # No RelayShield-looking value; hand back the likelier field so the
        # caller's own key verification produces the 401 rather than us.
        return pwd.strip() or user.strip()

    # "Bearer <key>" / "Token <key>" / any other scheme.
    return rest


STIX_VALID_DAYS = 90


def _stix_valid_until(seen_ts: str) -> str:
    """Expiry for a STIX indicator, STIX_VALID_DAYS after the sighting."""
    try:
        base = datetime.fromisoformat(str(seen_ts).replace("Z", "+00:00"))
    except Exception:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=STIX_VALID_DAYS)).isoformat().replace("+00:00", "Z")


def _ioc_to_stix(item: dict) -> dict | None:
    """Convert a relayshield_intel_iocs record to a STIX 2.1 Indicator object."""
    ioc_val  = item.get("ioc_value", "")
    ioc_type = item.get("ioc_type", "")
    seen_ts  = item.get("seen_ts", datetime.now(timezone.utc).isoformat())
    malware  = item.get("malware", "")
    channel  = item.get("channel", "")
    category = item.get("category", "")

    pattern_map = {
        "ip":         f"[ipv4-addr:value = '{ioc_val}']",
        "domain":     f"[domain-name:value = '{ioc_val}']",
        "url":        f"[url:value = '{ioc_val}']",
        # The hash key MUST be quoted. STIX 2.1 patterning grammar only allows a
        # bare object-path key made of [a-zA-Z0-9_]; "SHA-256" contains a hyphen,
        # so the unquoted form is a parse error, confirmed 2026-07-30 with the
        # OASIS stix2-patterns validator ("no viable alternative at input
        # 'file:hashes.SHA-256'"). Consumers that parse the pattern to derive the
        # observable -- Microsoft Sentinel populates ObservableKey/ObservableValue
        # this way -- silently store the indicator with both fields EMPTY, so
        # every SHA-256 IOC we have ever published was unusable for detection on
        # those platforms. Elastic never caught it because ti_custom reads
        # stix.pattern as an opaque string.
        "hash_sha256":f"[file:hashes.'SHA-256' = '{ioc_val}']",
        "email":      f"[email-message:from_ref.value = '{ioc_val}']",
        "phone":      None,    # not a standard STIX observable
        "wallet_eth": None,
        "wallet_btc": None,
        "wallet_sol": None,
        "wallet_ton": None,
    }
    pattern = pattern_map.get(ioc_type)
    if pattern is None:
        return None

    indicator_id = f"indicator--{str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, f'relayshield:{ioc_val}'))}"
    labels       = ["malicious-activity"]
    if malware and malware not in ("None", "n/a", ""):
        labels.append(f"malware:{malware[:50]}")

    return {
        "type":          "indicator",
        "spec_version":  "2.1",
        "id":            indicator_id,
        "created":       seen_ts,
        "modified":      seen_ts,
        "name":          ioc_val,
        "description":   f"Observed in {channel} ({category})" + (f" — {malware}" if malware and malware not in ("None","n/a","") else ""),
        "pattern":       pattern,
        "pattern_type":  "stix",
        "valid_from":    seen_ts,
        # valid_until added 2026-07-29. Elastic's ti_custom ingest pipeline runs a
        # date processor on an expiration field and ABORTS the whole document if it
        # is absent -- which meant no threat.indicator.* fields were ever set and an
        # Indicator Match rule silently matched nothing. The integration can supply
        # this from its own ioc_expiration_duration setting, but that is a required
        # field the customer can get wrong; emitting it ourselves makes ingestion
        # work regardless of how they configure the integration. 90 days from the
        # sighting, which is a deliberately conservative window for marketplace-
        # sourced IOCs.
        "valid_until":   _stix_valid_until(seen_ts),
        "labels":        labels,
        "external_references": [{"source_name": "relayshield", "url": "https://relayshield.net"}],
        "x_relayshield_record_type": "ioc_indicator",
        "x_relayshield_source":      item.get("channel", ""),
        "x_relayshield_category":    item.get("category", ""),
    }


def handle_taxii_discovery(params: dict, api_key_record: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/taxii+json;version=2.1",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({
            "title":       "RelayShield Threat Intelligence",
            # Feed count corrected 11 -> 20 on 2026-07-28: counted the ingest
            # functions actually invoked by relayshield_intel_feed's handler
            # (22 total, less _ingest_malpedia which loads family taxonomy not
            # IOCs, and _ingest_github_tool_repos which writes a different
            # table). The AWS Marketplace listing's "20+ feeds" was correct all
            # along; this discovery document was the understated one.
            "description": "RelayShield TAXII 2.1 server — 4,500,000+ IOCs from 83+ criminal Telegram channels and 20 authoritative feeds",
            "contact":     "support@relayshield.net",
            # Must be the branded host: a TAXII 2.1 client reads api_roots from
            # this discovery document and follows it for every subsequent
            # request, so advertising the raw execute-api hostname would pin
            # every integrating customer (Elastic, OpenCTI, MISP, Anomali) to
            # an AWS-internal URL that breaks if the API Gateway ID ever changes.
            "api_roots":   ["https://api.relayshield.net/v1/intel/taxii/"],
            "default":     "https://api.relayshield.net/v1/intel/taxii/",

            # --- API Root resource fields (TAXII 2.1 s4.2) ---
            # This URL is BOTH the Discovery endpoint and the one API Root it
            # advertises, so it has to satisfy both resource shapes at once.
            # Until 2026-07-30 it returned Discovery fields only, and the OASIS
            # reference client (taxii2-client 2.3.0) rejected it outright:
            #   ValidationError: No 'versions' in API Root
            # That aborts before any collection or object request, so every
            # protocol-walking consumer -- Microsoft Sentinel, OpenCTI, Anomali,
            # anything on cti-taxii-client -- could read exactly nothing. Elastic
            # was unaffected only because ti_custom is a plain HTTP poller that
            # hits the objects URL directly and never walks discovery.
            # Merging the two resources keeps every already-published URL intact;
            # splitting them would have moved the api root out from under the
            # configuration in the live Elastic guide.
            "versions":    ["application/taxii+json;version=2.1"],
            # 6 MiB: the Lambda synchronous response ceiling, which is the real
            # limit here. Nominal for a read-only server (no write endpoints).
            "max_content_length": 6291456,
        }),
    }


# The one collection this server exposes. Defined once so the collections list
# and the single-collection resource can never drift apart.
TAXII_COLLECTION = {
    "id":          "iocs",
    "title":       "RelayShield IOCs",
    "description": "Malicious IPs, domains, URLs, and file hashes from 83+ criminal Telegram channels and 20 authoritative threat feeds. 3,750+ malware families tracked.",
    "can_read":    True,
    "can_write":   False,
    "media_types": ["application/stix+json;version=2.1"],
}


def handle_taxii_collections(params: dict, api_key_record: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/taxii+json;version=2.1"},
        "body": json.dumps({"collections": [TAXII_COLLECTION]}),
    }


def handle_taxii_collection(params: dict, api_key_record: dict, collection_id: str) -> dict:
    """GET /{api-root}/collections/{id}/ -- the single Collection resource.

    Required by TAXII 2.1 s5.2 and 404'd until 2026-07-30. taxii2-client (and
    therefore every client built on it) fetches this resource lazily before it
    will issue an objects request, so the 404 meant get_objects() failed without
    ever reaching /objects/ -- the endpoint that has always worked.
    """
    if collection_id not in ("iocs", "relayshield-iocs"):
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/taxii+json;version=2.1"},
            "body": json.dumps({"title": "Not Found",
                                "description": f"No collection with id '{collection_id}'."}),
        }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/taxii+json;version=2.1"},
        "body": json.dumps(TAXII_COLLECTION),
    }


def handle_taxii_objects(params: dict, api_key_record: dict, query_params: dict) -> dict:
    added_after = query_params.get("added_after", "")
    try:
        limit = min(int(query_params.get("limit", 500)), 2000)
    except (ValueError, TypeError):
        limit = 500

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    scan_kwargs: dict = {
        "ProjectionExpression":     "ioc_value, ioc_type, seen_ts, malware, channel, category",
        "FilterExpression":         boto3.dynamodb.conditions.Attr("ioc_type").is_in(
                                        ["ip", "domain", "url", "hash_sha256", "email"]
                                    ),
        "Limit":                    limit * 3,  # over-fetch to account for type filtering
    }
    if added_after:
        scan_kwargs["FilterExpression"] = (
            scan_kwargs["FilterExpression"] &
            boto3.dynamodb.conditions.Attr("seen_ts").gte(added_after)
        )
    if cursor := query_params.get("next"):
        try:
            scan_kwargs["ExclusiveStartKey"] = json.loads(cursor)
        except Exception:
            pass

    # Deduplication, 2026-07-29. The table is keyed (ioc_value HASH, seen_ts RANGE)
    # -- one row per *sighting* -- while _ioc_to_stix derives the STIX id from
    # ioc_value alone. Every sighting of the same IOC therefore emitted an object
    # with an identical `id`, which is invalid STIX (one bundle, one id, differing
    # content) as well as wasteful. Measured live 2026-07-28: 25 objects across 5
    # pages contained only 3 unique indicators, so a polling customer spent ~8x the
    # calls for the same intelligence and their logs-ti_* index churned on repeats.
    #
    # Now: collapse by ioc_value within the response, keeping the most recent
    # seen_ts so `modified`/`valid_from` reflect the latest sighting rather than an
    # arbitrary one. `added_after` semantics are unchanged -- the seen_ts filter
    # still applies, so incremental pulls keep working.
    #
    # Because duplicates collapse, a single over-fetched scan can no longer be
    # relied on to yield `limit` unique indicators, so we scan forward across a
    # bounded number of pages instead of returning a near-empty response.
    MAX_SCAN_PAGES = 6
    unique: dict[str, dict] = {}
    last_consumed_key = None
    next_key = None
    pages = 0

    try:
        while pages < MAX_SCAN_PAGES:
            resp = table.scan(**scan_kwargs)
            pages += 1
            items = resp.get("Items", [])
            next_key = resp.get("LastEvaluatedKey")

            hit_limit = False
            for item in items:
                val = item.get("ioc_value", "")
                prev = unique.get(val)
                if prev is None:
                    if len(unique) >= limit:
                        # This row belongs to the *next* page. Break without
                        # consuming it so the cursor below does not skip it.
                        hit_limit = True
                        break
                    if _ioc_to_stix(item) is not None:
                        unique[val] = item
                elif str(item.get("seen_ts", "")) > str(prev.get("seen_ts", "")):
                    unique[val] = item
                last_consumed_key = {"ioc_value": val, "seen_ts": item.get("seen_ts")}

            if hit_limit:
                # Stopped mid-page: resume from the last row actually CONSUMED, not
                # the row that tripped the limit (that one has not been sent yet and
                # must be re-read), and never the scan's LastEvaluatedKey, which sits
                # past every examined item -- that was the bug fixed on 2026-07-28
                # which had been silently skipping up to two thirds of the corpus.
                next_key = last_consumed_key
                break
            if not next_key:
                break
            scan_kwargs["ExclusiveStartKey"] = next_key
    except Exception as exc:
        logger.exception("TAXII objects scan failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/taxii+json;version=2.1"},
            "body": json.dumps({"title": "Internal Server Error", "description": str(exc)}),
        }

    indicators = [obj for obj in (_ioc_to_stix(i) for i in unique.values()) if obj]

    bundle = {
        "type":           "bundle",
        "id":             f"bundle--{str(_uuid_mod.uuid4())}",
        "spec_version":   "2.1",
        "objects":        indicators,
    }

    response_body = {"objects": indicators, "more": bool(next_key)}
    if next_key:
        response_body["next"] = json.dumps(next_key)

    logger.info("TAXII objects returned=%d more=%s", len(indicators), bool(next_key))
    return {
        "statusCode": 200,
        # The Envelope is a TAXII resource, not a STIX one, so TAXII 2.1 s3.6
        # makes this application/taxii+json -- the STIX media type belongs on the
        # collection's `media_types`, describing what the envelope CONTAINS.
        # taxii2-client checks the response Content-Type against the Accept it
        # sent (common.py:312) and raises TAXIIServiceException on a mismatch, so
        # the old value would have failed every conformant client even after the
        # discovery and collection fixes above. Elastic already sends
        # `Accept: application/taxii+json;version=2.1`, so this narrows the
        # mismatch it was tolerating rather than introducing one.
        "headers": {"Content-Type": "application/taxii+json;version=2.1"},
        "body": json.dumps(response_body),
    }


# ---------------------------------------------------------------------------
# MISP JSON export — GET /v1/intel/misp/event (INTEL-6)
# ---------------------------------------------------------------------------
# MISP is the default/co-primary IOC format for many government, CERT/ISAC,
# and mid-market SOC tools that STIX-only integration doesn't reach.
# Serialization-only against the same relayshield_intel_iocs data STIX/TAXII
# already uses — no new detection engineering. Requires TI subscription
# (intel_access flag), same gating and pagination shape as TAXII.
#
#   GET /v1/intel/misp/event?added_after=<ISO8601>&limit=<N>&next=<cursor>

_MISP_TYPE_MAP = {
    # ioc_type -> (misp type, misp category)
    "ip":          ("ip-dst",  "Network activity"),
    "domain":      ("domain",  "Network activity"),
    "url":         ("url",     "Network activity"),
    "hash_sha256": ("sha256",  "Payload delivery"),
    "email":       ("email-src", "Payload delivery"),
}


def _ioc_to_misp_attribute(item: dict) -> dict | None:
    """Convert a relayshield_intel_iocs record to a MISP Attribute object."""
    ioc_val  = item.get("ioc_value", "")
    ioc_type = item.get("ioc_type", "")
    seen_ts  = item.get("seen_ts", datetime.now(timezone.utc).isoformat())
    malware  = item.get("malware", "")
    channel  = item.get("channel", "")
    category_field = item.get("category", "")

    mapped = _MISP_TYPE_MAP.get(ioc_type)
    if mapped is None:
        return None
    misp_type, misp_category = mapped

    comment = f"Observed in {channel} ({category_field})"
    if malware and malware not in ("None", "n/a", ""):
        comment += f" — {malware}"

    try:
        timestamp = str(int(datetime.fromisoformat(seen_ts.replace("Z", "+00:00")).timestamp()))
    except Exception:
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

    return {
        "type":     misp_type,
        "category": misp_category,
        "value":    ioc_val,
        "to_ids":   True,
        "comment":  comment,
        "timestamp": timestamp,
        "Tag": (
            [{"name": f"malware:{malware[:50]}"}] if malware and malware not in ("None", "n/a", "") else []
        ),
    }


# RelayShield ioc_type -> MISP attribute type. These exact strings are what
# Elastic's ti_misp ingest pipeline switches on to derive threat.indicator.type
# (verified 2026-07-29 against ti_misp 1.43.1's default.yml):
#   ip-dst  -> ipv4-addr      domain -> domain-name    url    -> url
#   sha256  -> file           email-src -> email-addr
_MISP_ATTR_TYPE = {
    "ip":          "ip-dst",
    "domain":      "domain",
    "url":         "url",
    "hash_sha256": "sha256",
    "email":       "email-src",
}
# MISP category is metadata only; the pipeline does not branch on it.
_MISP_ATTR_CATEGORY = {
    "ip":          "Network activity",
    "domain":      "Network activity",
    "url":         "Network activity",
    "hash_sha256": "Payload delivery",
    "email":       "Payload delivery",
}


def _iso_to_unix(value: str) -> int:
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def _ioc_to_misp_attribute(item: dict, seq: int) -> dict | None:
    """Render one IOC as a MISP Attribute object.

    Shape matches what MISP's /attributes/restSearch returns, because Elastic's
    ti_misp integration splits on `body.response.Attribute` and its pipeline reads
    misp.attribute.{type,value,timestamp,...}. The `timestamp` field is also the
    integration's pagination cursor (`[[.last_event.timestamp]]`), so it must be a
    unix-seconds string on every attribute or incremental polling breaks.
    """
    ioc_type = item.get("ioc_type", "")
    attr_type = _MISP_ATTR_TYPE.get(ioc_type)
    if not attr_type:
        return None

    ioc_val = item.get("ioc_value", "")
    seen_ts = str(item.get("seen_ts", ""))
    malware = item.get("malware", "")
    channel = item.get("channel", "")
    category = item.get("category", "")

    comment = f"Observed in {channel} ({category})"
    if malware and malware not in ("None", "n/a", ""):
        comment += f" - {malware}"

    return {
        "id":                  str(seq),
        "uuid":                str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, f"relayshield:{ioc_val}")),
        "event_id":            "1",
        "object_id":           "0",
        "object_relation":     None,
        "category":            _MISP_ATTR_CATEGORY.get(ioc_type, "Network activity"),
        "type":                attr_type,
        "to_ids":              True,
        "timestamp":           str(_iso_to_unix(seen_ts)),
        "distribution":        "3",
        "sharing_group_id":    "0",
        "comment":             comment,
        "deleted":             False,
        "disable_correlation": False,
        "first_seen":          None,
        "last_seen":           None,
        "value":               ioc_val,
        "Event": {
            "id":           "1",
            "uuid":         str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, "relayshield:feed")),
            "distribution": "3",
            "info":         "RelayShield Threat Intelligence",
            "org_id":       "1",
            "orgc_id":      "1",
        },
    }


# MISP instance identity shims.
#
# Added 2026-07-30. Elastic's ti_misp integration is a plain HTTP poller, so
# /attributes/restSearch alone was enough for it. PyMISP is not: its constructor
# handshakes with the instance before it will issue a single search, and any 404
# there raises PyMISPError and aborts. That blocked the whole MISP-to-Sentinel
# path, which runs through misp2sentinel -> PyMISP.
#
# The endpoint list below is not from documentation -- it is what PyMISP 2.5.34.1
# was observed requesting, in order, against the live server until init stopped
# failing. Values are deliberately minimal and honest: RelayShield is a read-only
# feed wearing a MISP-shaped API, so sync/sighting permissions are false and the
# identity is a service account, not a fabricated human user.
MISP_COMPAT_VERSION = "2.4.190"


def _misp_shim(path: str) -> dict | None:
    """Serve the MISP instance-identity endpoints PyMISP requires at startup."""
    body: dict
    if path == "/servers/getVersion":
        body = {
            "version":                   MISP_COMPAT_VERSION,
            "pymisp_recommended_version": MISP_COMPAT_VERSION,
            "perm_sync":                 False,
            "perm_sighting":             False,
            "perm_galaxy_editor":        False,
            "request_encoding":          [],
        }
    elif path == "/servers/getPyMISPVersion.json":
        body = {"version": MISP_COMPAT_VERSION}
    elif path == "/users/view/me":
        body = {
            "User": {
                "id":       "1",
                "org_id":   "1",
                "email":    "support@relayshield.net",
                "autoalert": False,
                "invited_by": "0",
                "gpgkey":   None,
                "nids_sid": "0",
                "termsaccepted": True,
                "role_id":  "1",
                "disabled": False,
            },
            "Role": {
                "id":   "1",
                "name": "Read Only",
                # Read-only feed: no write, sync, admin or tagging rights.
                "perm_add": False, "perm_modify": False, "perm_modify_org": False,
                "perm_publish": False, "perm_sync": False, "perm_admin": False,
                "perm_site_admin": False, "perm_auth": True, "perm_tagger": False,
                "perm_sighting": False, "perm_galaxy_editor": False,
            },
            "Organisation": {"id": "1", "name": "RelayShield", "uuid":
                             str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, "relayshield:org"))},
            "UserSetting": [],
        }
    else:
        return None
    return {"statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def handle_misp_rest_search(api_key_record: dict, body: dict) -> dict:
    """MISP-compatible POST /attributes/restSearch.

    Built 2026-07-29. The previously published integration guide told customers to
    point Elastic's "Threat Intel MISP" integration at /v1/intel/misp/, which 404'd
    -- only /v1/intel/misp/event existed, and that is not a MISP API shape. Elastic's
    ti_misp integration issues POST {url}/attributes/restSearch with a JSON body and
    splits the response on body.response.Attribute, so that is what this serves.

    Contract verified against ti_misp 1.43.1's httpjson.yml.hbs:
      request : POST {url}/attributes/restSearch, header Authorization: <token>
      body    : page (1-based), limit, returnFormat, timestamp (unix secs, >=),
                includeDecayScore, order
      response: {"response": {"Attribute": [...]}} -- an EMPTY array is how the
                client knows to stop paginating, so never 404 a valid page request.
      cursor  : [[.last_event.timestamp]] -- see _ioc_to_misp_attribute.

    Deduplicated by ioc_value exactly like the TAXII feed, for the same reason: the
    table holds one row per sighting, so without this a poller re-ingests the same
    indicator many times over.
    """
    try:
        page = max(int(body.get("page", 1) or 1), 1)
    except (ValueError, TypeError):
        page = 1
    try:
        limit = min(max(int(body.get("limit", 500) or 500), 1), 2000)
    except (ValueError, TypeError):
        limit = 500

    since_iso = ""
    raw_ts = body.get("timestamp")
    if raw_ts not in (None, ""):
        try:
            since_iso = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            since_iso = ""

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    scan_kwargs: dict = {
        "ProjectionExpression": "ioc_value, ioc_type, seen_ts, malware, channel, category",
        "FilterExpression":     boto3.dynamodb.conditions.Attr("ioc_type").is_in(
                                    ["ip", "domain", "url", "hash_sha256", "email"]
                                ),
        # Fixed, page-independent. Sizing the scan from `page` made each request
        # build a different pool, so consecutive pages overlapped and the client
        # re-ingested the same indicators (measured: 2 of 5 duplicated between
        # page 1 and page 2). A constant window makes the ordered pool identical
        # for every page, so slicing it is stable.
        "Limit":                2000,
    }
    if since_iso:
        scan_kwargs["FilterExpression"] = (
            scan_kwargs["FilterExpression"] &
            boto3.dynamodb.conditions.Attr("seen_ts").gte(since_iso)
        )

    # DynamoDB has no offset, so page N is served by collecting enough unique
    # indicators to cover it and slicing. Bounded by MAX_SCAN_PAGES to keep the
    # read cost of a deep page from running away.
    # Both bounds are constants so the pool -- and therefore every page sliced from
    # it -- is identical no matter which page was requested.
    MAX_SCAN_PAGES = 8
    POOL_TARGET    = 4000
    unique: dict[str, dict] = {}
    pages = 0
    try:
        while pages < MAX_SCAN_PAGES:
            resp = table.scan(**scan_kwargs)
            pages += 1
            for item in resp.get("Items", []):
                val = item.get("ioc_value", "")
                prev = unique.get(val)
                if prev is None:
                    unique[val] = item
                elif str(item.get("seen_ts", "")) > str(prev.get("seen_ts", "")):
                    unique[val] = item
            nxt = resp.get("LastEvaluatedKey")
            if len(unique) >= POOL_TARGET or not nxt:
                break
            scan_kwargs["ExclusiveStartKey"] = nxt
    except Exception as exc:
        logger.exception("MISP restSearch scan failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"errors": ["Internal Server Error"]}),
        }

    # `order: timestamp` is requested by the integration, and the cursor depends on
    # the last event's timestamp, so ascending seen_ts is the correct ordering.
    ordered = sorted(unique.values(), key=lambda i: str(i.get("seen_ts", "")))
    window = ordered[(page - 1) * limit: page * limit]

    attributes = []
    for offset, item in enumerate(window, start=(page - 1) * limit + 1):
        attr = _ioc_to_misp_attribute(item, offset)
        if attr:
            attributes.append(attr)

    logger.info("MISP restSearch page=%d limit=%d returned=%d unique_pool=%d",
                page, limit, len(attributes), len(unique))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"response": {"Attribute": attributes}}),
    }


def handle_misp_event(params: dict, api_key_record: dict, query_params: dict) -> dict:
    added_after = query_params.get("added_after", "")
    try:
        limit = min(int(query_params.get("limit", 500)), 2000)
    except (ValueError, TypeError):
        limit = 500

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    scan_kwargs: dict = {
        "ProjectionExpression": "ioc_value, ioc_type, seen_ts, malware, channel, category",
        "FilterExpression":     boto3.dynamodb.conditions.Attr("ioc_type").is_in(
                                    ["ip", "domain", "url", "hash_sha256", "email"]
                                ),
        "Limit":                limit * 3,  # over-fetch to account for type filtering
    }
    if added_after:
        scan_kwargs["FilterExpression"] = (
            scan_kwargs["FilterExpression"] &
            boto3.dynamodb.conditions.Attr("seen_ts").gte(added_after)
        )
    if cursor := query_params.get("next"):
        try:
            scan_kwargs["ExclusiveStartKey"] = json.loads(cursor)
        except Exception:
            pass

    try:
        resp  = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        next_key = resp.get("LastEvaluatedKey")
    except Exception as exc:
        logger.exception("MISP event scan failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"errors": [str(exc)]}),
        }

    attributes = []
    for item in items:
        attr = _ioc_to_misp_attribute(item)
        if attr:
            attributes.append(attr)
        if len(attributes) >= limit:
            break

    now_iso = datetime.now(timezone.utc)
    event = {
        "Event": {
            "info":            "RelayShield Threat Intelligence Feed",
            "threat_level_id": "2",   # Medium — mixed-severity feed, not uniformly critical
            "analysis":        "1",   # Ongoing
            "distribution":    "0",   # Your organisation only — recipient controls further sharing
            "date":            now_iso.strftime("%Y-%m-%d"),
            "published":       True,
            "Orgc":            {"name": "RelayShield"},
            "Attribute":       attributes,
            "more":            bool(next_key),
            **({"next": json.dumps(next_key)} if next_key else {}),
        }
    }

    logger.info("MISP event returned=%d more=%s", len(attributes), bool(next_key))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(event),
    }


# ---------------------------------------------------------------------------
# Shareable report links (INTEL-8) — POST /v1/report/share (generate, gated
# to paying subscribers), GET /v1/r/{report_id} (view, public no-auth).
# ---------------------------------------------------------------------------
# Growth lever: generation is gated (consistent with no-free-tier stance),
# viewing is public so SOC teams/security write-ups can freely link to a
# report the same way VirusTotal/Shodan/ANY.RUN report pages work.

def _floats_to_decimal(obj):
    """DynamoDB's boto3 resource API rejects native floats — recursively
    convert to Decimal before put_item. Caller-supplied summary dicts can
    contain arbitrary nested floats (risk scores, prices, etc.)."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(v) for v in obj]
    return obj


def _decimals_to_plain(obj):
    """Reverse of _floats_to_decimal, for reading back out of DynamoDB."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _decimals_to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimals_to_plain(v) for v in obj]
    return obj


def handle_report_share(params: dict, api_key_record: dict) -> dict:
    """Generate a shareable public link for a scan finding. Caller already
    has the full result client-side right after a scan — this stores a
    clean, presentable summary of it (not the full raw payload)."""
    report_type = (params.get("report_type") or "").strip()
    summary     = params.get("summary")
    if not report_type:
        return _err("report_type is required")
    if not isinstance(summary, dict) or not summary:
        return _err("summary is required and must be a non-empty object")

    report_id = secrets.token_urlsafe(9)
    try:
        dynamodb.Table(SHARED_REPORTS_TABLE).put_item(Item={
            "report_id":   report_id,
            "report_type": report_type,
            "summary":     _floats_to_decimal(summary),
            "created_at":  datetime.now(timezone.utc).isoformat(),
            "created_by":  api_key_record.get("email", "unknown"),
        })
    except Exception as exc:
        logger.error("report share creation failed: %s", exc)
        return _err("report creation failed", 500)

    logger.info("report share created id=%s type=%s", report_id, report_type)
    return _ok({
        "report_id": report_id,
        # api.relayshield.net, not bare relayshield.net — the latter 404s for
        # anything API-served (confirmed precedent: /developers has the same issue).
        # A cleaner relayshield.net/r/{id} redirect can be added later as a
        # DNS/routing follow-up; this is the URL that actually works today.
        "share_url": f"https://api.relayshield.net/v1/r/{report_id}",
    })


def handle_report_view(report_id: str) -> dict:
    """Public, no-auth view of a shared report — GET /v1/r/{report_id}."""
    try:
        item = dynamodb.Table(SHARED_REPORTS_TABLE).get_item(Key={"report_id": report_id}).get("Item")
    except Exception as exc:
        logger.error("report view lookup failed id=%s: %s", report_id, exc)
        item = None

    if not item:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": "<html><body style='background:#0a1628;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px'>"
                    "<h2>Report not found</h2><p style='color:#64748b'>This link may have expired or never existed.</p></body></html>",
        }

    report_type = item.get("report_type", "")
    created_at  = item.get("created_at", "")
    summary     = _decimals_to_plain(item.get("summary", {}))

    rows = "".join(
        f"<tr><td style='padding:8px 12px;color:#94a3b8;border-bottom:1px solid #1e3a5f'>{html.escape(str(k))}</td>"
        f"<td style='padding:8px 12px;color:#e2e8f0;border-bottom:1px solid #1e3a5f;text-align:right'>{html.escape(str(v))}</td></tr>"
        for k, v in summary.items()
    )
    body = f"""<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield Report — {html.escape(report_type)}</title></head>
<body style="background:#0a1628;color:#e2e8f0;font-family:-apple-system,sans-serif;margin:0;padding:24px">
<div style="max-width:480px;margin:0 auto">
<div style="text-align:center;margin-bottom:24px">
<div style="font-size:40px">🛡</div>
<div style="font-size:20px;font-weight:800">RelayShield Report</div>
<div style="font-size:13px;color:#00B5A5;text-transform:uppercase;letter-spacing:0.5px">{html.escape(report_type)}</div>
</div>
<table style="width:100%;border-collapse:collapse;background:#0F1F3D;border-radius:12px;overflow:hidden">{rows}</table>
<p style="text-align:center;color:#475569;font-size:11px;margin-top:20px">Generated {html.escape(created_at)} · <a href="https://relayshield.net" style="color:#00B5A5">relayshield.net</a></p>
</div></body></html>"""

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300"},
        "body": body,
    }


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/ransomware-risk  /  POST /v1/payg/ransomware-risk
# ---------------------------------------------------------------------------
# Checks a domain against the INTEL-4 ransomware victim corpus and the
# pre-ransomware credential label in the IOC table.
#
# Request:  { "domain": "acme.com" }
# Response: {
#   "domain": "...",
#   "on_victim_list": bool,
#   "victim_groups": [...],      — ransomware groups that claimed the domain
#   "first_seen": "...",         — earliest victim listing date
#   "pre_ransomware_ioc_count":  N,  — IOCs tagged pre_ransomware for this domain
#   "risk_level": "CRITICAL|HIGH|MEDIUM|CLEAN",
#   "recommendation": "..."
# }

RANSOMWARE_TABLE_API  = "relayshield_intel_ransomware"
MITRE_ATTACK_TABLE    = "relayshield_mitre_attack"
WEBHOOK_MAX_TIMEOUT   = 5   # seconds — webhook delivery must not block main response


def _build_threat_graph(malware_family: str) -> dict | None:
    """Build lightweight threat graph for a malware family from MITRE ATT&CK data.
    Returns actor graph with group_id, country, techniques, aliases."""
    family_key = malware_family.lower().split(",")[0].strip()
    actor_name = THREAT_ACTOR_MAP.get(family_key, "")
    if not actor_name:
        return None
    search_term = actor_name.split(" ")[0].split("/")[0].strip()
    try:
        resp = dynamodb.Table(MITRE_ATTACK_TABLE).scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("sk").eq("info") &
                boto3.dynamodb.conditions.Attr("name").contains(search_term)
            ),
            ProjectionExpression="group_id, #n, aliases, technique_ids, country_origin, description",
            ExpressionAttributeNames={"#n": "name"},
            Limit=3,
        )
        groups = resp.get("Items", [])
        if not groups:
            return None
        g = groups[0]
        return {
            "group_id":       g.get("group_id", ""),
            "name":           g.get("name", ""),
            "aliases":        g.get("aliases", [])[:3],
            "country_origin": g.get("country_origin", "Unknown"),
            "top_techniques": g.get("technique_ids", [])[:8],
            "description":    (g.get("description") or "")[:200],
        }
    except Exception as exc:
        logger.debug("Threat graph lookup failed family=%s: %s", family_key, exc)
        return None


def _fire_webhook(webhook_url: str, payload: dict) -> None:
    """POST alert payload to customer-registered webhook URL. Non-blocking — called in thread."""
    try:
        body = json.dumps({"source": "relayshield", "payload": payload}).encode()
        req  = urllib.request.Request(
            webhook_url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": "RelayShield-Webhook/1.0"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=WEBHOOK_MAX_TIMEOUT)
        logger.info("Webhook delivered url=%s", webhook_url[:60])
    except Exception as exc:
        logger.warning("Webhook delivery failed url=%s: %s", webhook_url[:60], exc)
EPSS_THRESHOLD_HIGH   = 0.50   # EPSS ≥50% = CRITICAL signal
EPSS_THRESHOLD_MEDIUM = 0.10   # EPSS ≥10% = HIGH signal


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/webhook/configure
# ---------------------------------------------------------------------------
# Registers or updates a webhook URL on the caller's API key.
# When a metered endpoint returns a positive finding (breach found, infostealer
# found, session hijack detected), RelayShield POSTs the full JSON result to
# the registered webhook within 5 seconds. Enables real-time SOAR integration.
#
# Request:  { "webhook_url": "https://your-soar.example.com/alerts" }
# ---------------------------------------------------------------------------
# Feature: Asset Intel — register assets + on-demand IOC sweep
# POST /v1/metered/asset-intel
# Request:  { "action": "register|sweep|list|remove", "assets": ["domain.com", "1.2.3.4"] }
# Billing:  $0.15/call (covers both registration and sweep)
# ---------------------------------------------------------------------------

def handle_asset_intel(params: dict, api_key_str: str) -> dict:
    action = (params.get("action") or "sweep").strip().lower()
    assets = params.get("assets") or []
    if not isinstance(assets, list):
        assets = [assets]
    assets = [str(a).strip().lower() for a in assets if a]

    table     = dynamodb.Table(ASSET_WATCHLIST_TABLE)
    ioc_table = dynamodb.Table(INTEL_IOCS_TABLE)

    if action == "list":
        try:
            resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("api_key").eq(api_key_str))
            return _ok({"assets": [i["asset"] for i in resp.get("Items", [])], "count": resp["Count"]})
        except Exception as exc:
            logger.exception("asset-intel list failed: %s", exc)
            return _err("failed to list assets", 500)

    if action == "remove":
        for asset in assets:
            try:
                table.delete_item(Key={"api_key": api_key_str, "asset": asset})
            except Exception as exc:
                logger.warning("asset-intel remove failed asset=%s: %s", asset, exc)
        return _ok({"removed": assets})

    if action == "register":
        if not assets:
            return _err("assets array required")
        added = []
        for asset in assets[:50]:
            try:
                table.put_item(Item={
                    "api_key":    api_key_str,
                    "asset":      asset,
                    "asset_type": "ip" if re.match(r"^\d+\.\d+\.\d+\.\d+$", asset) else "domain",
                    "added_at":   datetime.now(timezone.utc).isoformat(),
                    "active":     True,
                })
                added.append(asset)
            except Exception as exc:
                logger.warning("asset-intel register failed asset=%s: %s", asset, exc)
        logger.info("asset-intel registered api_key=%s count=%d", api_key_str[:16], len(added))
        return _ok({"registered": added, "count": len(added),
                    "note": "Push alerts will fire via your registered webhook when new IOCs match these assets."})

    # action == "sweep" — check registered assets (or supplied assets) against IOC corpus
    sweep_targets = assets
    if not sweep_targets:
        try:
            resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("api_key").eq(api_key_str))
            sweep_targets = [i["asset"] for i in resp.get("Items", [])]
        except Exception as exc:
            logger.exception("asset-intel sweep query failed: %s", exc)
            return _err("failed to load asset watchlist", 500)

    if not sweep_targets:
        return _ok({"matches": [], "assets_checked": 0,
                    "note": "No assets registered. Use action: register to add assets."})

    matches = []
    for asset in sweep_targets:
        try:
            ioc_resp = ioc_table.get_item(Key={"ioc_value": asset})
            item = ioc_resp.get("Item")
            if item:
                matches.append({
                    "asset":        asset,
                    "ioc_type":     item.get("ioc_type"),
                    "source":       item.get("source"),
                    "malware":      item.get("malware_family", ""),
                    "confidence":   item.get("confidence_score", 0.5),
                    "first_seen":   item.get("first_seen", ""),
                    "threat_actor": item.get("threat_actor", ""),
                })
        except Exception as exc:
            logger.warning("asset-intel sweep failed asset=%s: %s", asset, exc)

    logger.info("asset-intel sweep api_key=%s assets=%d matches=%d", api_key_str[:16], len(sweep_targets), len(matches))
    return _ok({"matches": matches, "assets_checked": len(sweep_targets),
                "match_count": len(matches), "clean_count": len(sweep_targets) - len(matches)})


# ---------------------------------------------------------------------------
# Feature: Threat Actor — exploit chatter detection + actor/campaign lookup
# POST /v1/metered/threat-actor
# Request:  { "action": "exploit-chatter|actor-lookup", "cve_id": "CVE-2024-12345" }
#        or { "action": "actor-lookup", "actor": "LummaC2", "actors": ["LummaC2"] }
# Billing:  $0.30/call
# ---------------------------------------------------------------------------

def handle_threat_actor(params: dict) -> dict:
    action = (params.get("action") or "actor-lookup").strip().lower()

    if action == "exploit-chatter":
        cve_id = (params.get("cve_id") or "").strip().upper()
        if not cve_id or not re.match(r"^CVE-\d{4}-\d+$", cve_id):
            return _err("cve_id required (format: CVE-YYYY-NNNNN)")

        chatter_table = dynamodb.Table(EXPLOIT_CHATTER_TABLE)
        ioc_table     = dynamodb.Table(INTEL_IOCS_TABLE)
        cve_table     = dynamodb.Table(INTEL_CVE_TABLE)

        chatter_found = []
        try:
            resp = chatter_table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("cve_id").eq(cve_id))
            chatter_found = resp.get("Items", [])
        except Exception as exc:
            logger.warning("exploit-chatter table query failed: %s", exc)

        kev_data = {}
        try:
            kev_data = cve_table.get_item(Key={"cve_id": cve_id}).get("Item", {})
        except Exception:
            pass

        ioc_hits = []
        try:
            ioc_hits = ioc_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("malware_family").contains(cve_id)
            ).get("Items", [])[:10]
        except Exception:
            pass

        found      = bool(chatter_found or ioc_hits)
        risk_level = "HIGH" if chatter_found else ("MEDIUM" if ioc_hits else "LOW")
        logger.info("exploit-chatter cve=%s found=%s risk=%s", cve_id, found, risk_level)
        return _ok({
            "cve_id":          cve_id,
            "found":           found,
            "risk_level":      risk_level,
            "chatter_count":   len(chatter_found),
            "chatter_sources": [c.get("source", "") for c in chatter_found[:5]],
            "first_seen":      chatter_found[0].get("first_seen", "") if chatter_found else "",
            "ioc_hits":        len(ioc_hits),
            "in_kev":          bool(kev_data),
            "epss_score":      kev_data.get("epss_score", 0.0),
            "kev_date_added":  kev_data.get("date_added", ""),
            "note":            "Chatter detected before NVD publication indicates active exploit development."
                               if chatter_found else "No pre-publication exploit chatter detected.",
        })

    # action == "actor-lookup"
    #
    # Fixed 2026-07-16 — this previously never returned a single real IOC for
    # any actor, for two compounding reasons found while building real
    # threat-actor -> malware-family -> live-IOC attribution for the TI demo:
    # (1) it filtered the IOC corpus on `malware_family`/`threat_actor`
    #     attributes that don't exist on real IOC records (the actual field
    #     is `malware`, populated with a real lowercase family name like
    #     "mirai" by relayshield_intel_feed.py's bulk ingestion); (2) it read
    #     `techniques` off the MITRE group record, but the ingestion writes
    #     `technique_ids`. Also, relayshield_intel_attack.py's Group->Software
    #     relationship was never populated at all until today (STIX
    #     relationship objects have type "relationship" + a separate
    #     relationship_type field, not type "uses" as the ingestion assumed)
    #     — so even with correct field names there was no software list to
    #     cross-reference against. Now: resolve the group's real associated
    #     malware/tool names via MITRE's own software_ids list, then query
    #     the IOC corpus's new malware-index GSI for each one (a full table
    #     scan isn't viable at 3.2M+ items).
    actor        = (params.get("actor") or "").strip()
    actors       = params.get("actors") or []
    ioc_table    = dynamodb.Table(INTEL_IOCS_TABLE)
    mitre_table  = dynamodb.Table("relayshield_mitre_attack")

    if not actor and not actors:
        return _err("actor or actors required for actor-lookup")

    search_terms = [actor] if actor else actors[:5]
    results = []
    for term in search_terms:
        mitre_info = {}
        software_names: list[str] = []
        try:
            mitre_items = mitre_table.scan(
                FilterExpression=(
                    boto3.dynamodb.conditions.Attr("sk").eq("info") &
                    boto3.dynamodb.conditions.Attr("name").contains(term)
                ),
                Limit=200,
            ).get("Items", [])
            if mitre_items:
                group = mitre_items[0]
                mitre_info = {
                    "group_name":  group.get("name", ""),
                    "aliases":     group.get("aliases", []),
                    "techniques":  group.get("technique_ids", [])[:10],
                    "description": group.get("description", "")[:300],
                }
                for sid in group.get("software_ids", [])[:30]:
                    sw = mitre_table.get_item(Key={"group_id": sid, "sk": f"software:{sid}"}).get("Item")
                    if sw:
                        software_names.append(sw.get("name", ""))
                        software_names.extend(sw.get("aliases", []))
        except Exception as exc:
            logger.warning("actor-lookup MITRE scan failed term=%s: %s", term, exc)

        iocs = []
        checked_names = set()
        for name in software_names:
            key = name.strip().lower()
            if not key or key in checked_names:
                continue
            checked_names.add(key)
            try:
                hits = ioc_table.query(
                    IndexName="malware-index",
                    KeyConditionExpression=boto3.dynamodb.conditions.Key("malware").eq(key),
                    Limit=20,
                ).get("Items", [])
                iocs.extend(hits)
            except Exception as exc:
                logger.warning("actor-lookup IOC query failed malware=%s: %s", key, exc)

        ioc_types = {}
        sources   = set()
        latest    = ""
        for ioc in iocs:
            t = ioc.get("ioc_type", "unknown")
            ioc_types[t] = ioc_types.get(t, 0) + 1
            sources.add(ioc.get("channel", ""))
            ts = ioc.get("seen_ts", "")
            if ts > latest:
                latest = ts

        results.append({
            "term":               term,
            "found":              bool(iocs or mitre_info),
            "ioc_count":          len(iocs),
            "ioc_breakdown":      ioc_types,
            "sources":            sorted(s for s in sources if s),
            "latest_ioc":         latest,
            "mitre":              mitre_info,
            "associated_malware": sorted(checked_names),
            "sample_iocs":        [{"value": i.get("ioc_value", ""), "type": i.get("ioc_type", ""),
                                     "malware": i.get("malware", ""), "seen_ts": i.get("seen_ts", "")} for i in iocs[:5]],
        })

    logger.info("actor-lookup terms=%s total_iocs=%d", search_terms, sum(r["ioc_count"] for r in results))
    return _ok({"results": results, "terms_searched": len(results)})


# ---------------------------------------------------------------------------
# Feature: CVE-Identity-Risk — CVE × identity signal composite risk
# POST /v1/metered/cve-identity-risk
# Request:  { "cve_id": "CVE-2024-12345", "domain": "example.com" }
# Returns:  composite risk score combining EPSS, KEV status, breach timing,
#           infostealer family chain, and ransomware victim correlation
# Billing:  $0.40/call
# ---------------------------------------------------------------------------

def handle_cve_identity_risk(params: dict) -> dict:
    cve_id = (params.get("cve_id") or "").strip().upper()
    domain = (params.get("domain") or "").strip().lower()

    if not cve_id or not re.match(r"^CVE-\d{4}-\d+$", cve_id):
        return _err("cve_id required (format: CVE-YYYY-NNNNN)")
    if not domain:
        return _err("domain required")

    cve_table      = dynamodb.Table(INTEL_CVE_TABLE)
    ioc_table      = dynamodb.Table(INTEL_IOCS_TABLE)
    ransomware_tbl = dynamodb.Table("relayshield_intel_ransomware")
    chatter_tbl    = dynamodb.Table(EXPLOIT_CHATTER_TABLE)

    # 1. Get CVE baseline data (EPSS + KEV)
    kev_data = {}
    try:
        kev_data = cve_table.get_item(Key={"cve_id": cve_id}).get("Item", {})
    except Exception:
        pass

    epss_score      = float(kev_data.get("epss_score") or 0.0)
    in_kev          = bool(kev_data.get("date_added"))
    ransomware_linked = bool(kev_data.get("ransomware_campaign"))
    affected_product  = kev_data.get("product", "")
    attack_vector     = kev_data.get("attack_vector", "")

    # 2. CVE → malware family chain via ATT&CK technique mapping
    exploiting_families = list(kev_data.get("exploiting_malware_families", []))
    if not exploiting_families and kev_data.get("techniques"):
        # Derive from ATT&CK techniques already stored on KEV record
        exploiting_families = kev_data.get("associated_groups", [])[:5]

    # 3. Check if exploiting families appear in our IOC corpus for this domain
    stealer_hits_for_domain = []
    if exploiting_families:
        for family in exploiting_families[:5]:
            try:
                resp = ioc_table.scan(
                    FilterExpression=(
                        boto3.dynamodb.conditions.Attr("malware_family").contains(family) &
                        boto3.dynamodb.conditions.Attr("ioc_value").contains(domain.split(".")[0])
                    ),
                    Limit=10,
                )
                if resp.get("Items"):
                    stealer_hits_for_domain.append({
                        "family": family,
                        "ioc_count": len(resp["Items"]),
                        "latest": max(i.get("first_seen", "") for i in resp["Items"]),
                    })
            except Exception:
                pass

    # 4. Post-CVE breach velocity — ransomware victim check for domain
    on_victim_list = False
    victim_groups = []
    try:
        resp = ransomware_tbl.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("domain").eq(domain),
            Limit=5,
        )
        items = resp.get("Items", [])
        on_victim_list = bool(items)
        victim_groups = [i.get("group", "") for i in items]
    except Exception:
        pass

    # 5. Exploit chatter check
    chatter_count = 0
    try:
        chatter_count = len(chatter_tbl.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("cve_id").eq(cve_id)
        ).get("Items", []))
    except Exception:
        pass

    # 6. Composite risk score
    score = 0
    factors = []

    if in_kev:
        score += 25
        factors.append("CVE is in CISA KEV — confirmed active exploitation")
    if epss_score >= 0.5:
        score += 20
        factors.append(f"EPSS score {epss_score:.2f} — top exploitation probability tier")
    elif epss_score >= 0.2:
        score += 10
        factors.append(f"EPSS score {epss_score:.2f} — elevated exploitation probability")
    if stealer_hits_for_domain:
        score += 30
        factors.append(f"Domain appears in IOC corpus alongside {len(stealer_hits_for_domain)} exploiting malware "
                        f"family/families: {', '.join(h['family'] for h in stealer_hits_for_domain)}")
    if on_victim_list:
        score += 20
        factors.append(f"Domain appears on ransomware victim list — groups: {', '.join(victim_groups)}")
    if ransomware_linked:
        score += 10
        factors.append("CVE is linked to known ransomware campaigns")
    if chatter_count > 0:
        score += 10
        factors.append(f"Pre-publication exploit chatter detected ({chatter_count} signals)")

    score = min(score, 100)
    risk_level = "CRITICAL" if score >= 75 else "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW"

    logger.info("cve-identity-risk cve=%s domain=%s score=%d risk=%s", cve_id, domain, score, risk_level)
    return _ok({
        "cve_id":                cve_id,
        "domain":                domain,
        "risk_score":            score,
        "risk_level":            risk_level,
        "in_kev":                in_kev,
        "epss_score":            epss_score,
        "ransomware_linked":     ransomware_linked,
        "affected_product":      affected_product,
        "exploiting_families":   exploiting_families,
        "stealer_corpus_hits":   stealer_hits_for_domain,
        "on_ransomware_victim_list": on_victim_list,
        "victim_groups":         victim_groups,
        "exploit_chatter_count": chatter_count,
        "risk_factors":          factors,
        "recommendation":        (
            "URGENT: Active exploitation of this CVE has been detected in infrastructure associated with this domain. "
            "Immediate patch verification and incident response assessment recommended."
            if score >= 75 else
            "HIGH PRIORITY: Multiple correlated signals indicate elevated exploitation risk for this domain. "
            "Verify patch status and review infostealer exposure."
            if score >= 50 else
            "MONITOR: CVE poses above-average risk for this domain. Schedule patch verification."
            if score >= 25 else
            "LOW RISK: No correlated identity signals detected for this domain against this CVE."
        ),
    })


# ---------------------------------------------------------------------------
# Feature: Identity Risk Score — composite domain security credit score (0-100)
# POST /v1/metered/identity-risk-score
# Request:  { "domain": "example.com" }
# Returns:  0-100 composite score across 6 identity signal dimensions
# Billing:  $0.35/call
# ---------------------------------------------------------------------------

def handle_identity_risk_score(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower()
    if not domain or "." not in domain:
        return _err("domain required (e.g. example.com)")

    ioc_table      = dynamodb.Table(INTEL_IOCS_TABLE)
    cve_table      = dynamodb.Table(INTEL_CVE_TABLE)
    ransomware_tbl = dynamodb.Table("relayshield_intel_ransomware")
    sessions_tbl   = dynamodb.Table("relayshield_stolen_sessions")
    base_name      = domain.split(".")[0]  # adobe.com -> adobe
    company        = base_name.capitalize()  # adobe -> Adobe

    factors    = []
    dim_scores = {}

    # Dimension 1: Breach exposure (0-25)
    # Uses public HIBP /breaches?domain= — no ownership verification needed
    breach_score = 0
    try:
        req = urllib.request.Request(
            f"https://haveibeenpwned.com/api/v3/breaches?domain={domain}",
            headers={"User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            breaches = json.loads(resp.read())
            breach_count = len(breaches) if isinstance(breaches, list) else 0
            pwned_total  = sum(b.get("PwnCount", 0) for b in breaches) if isinstance(breaches, list) else 0
            # Scale by accounts affected — 100M+ = max score
            if pwned_total >= 100_000_000:   breach_score = 25
            elif pwned_total >= 10_000_000:  breach_score = 20
            elif pwned_total >= 1_000_000:   breach_score = 15
            elif pwned_total >= 100_000:     breach_score = 10
            elif breach_count > 0:           breach_score = 5
            if breach_count:
                factors.append(f"Breach exposure: {breach_count} known breach event(s), {pwned_total:,} accounts affected")
    except Exception:
        pass
    dim_scores["breach_exposure"] = breach_score

    # Dimension 2: Infostealer density (0-25)
    # Hudson Rock Cavalier — credential stealer log hits for domain
    stealer_score = 0
    try:
        cav_resp = urllib.request.urlopen(
            urllib.request.Request(
                f"{CAVALIER_DOMAIN_URL}?domain={domain}",
                headers={"User-Agent": "RelayShield/1.0"},
            ), timeout=10)
        cav_data = json.loads(cav_resp.read())
        stealer_count = cav_data.get("total", 0) or len(cav_data.get("stealers", []))
        # Scale by stealer hit volume
        if stealer_count >= 1_000_000:    stealer_score = 25
        elif stealer_count >= 500_000:    stealer_score = 20
        elif stealer_count >= 100_000:    stealer_score = 15
        elif stealer_count >= 10_000:     stealer_score = 10
        elif stealer_count >= 1_000:      stealer_score = 7
        elif stealer_count > 0:           stealer_score = 3
        if stealer_count:
            factors.append(f"Infostealer density: {stealer_count:,} credentials found in stealer malware logs")
    except Exception:
        pass
    dim_scores["infostealer_density"] = stealer_score

    # Dimension 3: Threat actor targeting (0-15)
    # Checks whether known threat actors in our MITRE ATT&CK + IOC corpus
    # have attributed attacks against this company's sector or brand
    ioc_score = 0
    try:
        # Check IOC corpus for entries attributed to threat actors targeting this domain/brand
        ioc_resp = ioc_table.scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("threat_actor").exists() &
                boto3.dynamodb.conditions.Attr("ioc_value").contains(base_name)
            ),
            Limit=20,
        )
        ioc_items = ioc_resp.get("Items", [])
        attributed = [i for i in ioc_items if i.get("threat_actor") and domain not in i.get("ioc_value","")]
        actor_count = len(attributed)
        unique_actors = len({i.get("threat_actor") for i in attributed})
        if actor_count >= 5:    ioc_score = 15
        elif actor_count >= 3:  ioc_score = 10
        elif actor_count >= 1:  ioc_score = 6
        if actor_count:
            factors.append(f"Threat actor targeting: {actor_count} attributed IOCs ({unique_actors} distinct threat actor(s)) reference {company} brand infrastructure")
        # Also check our intel_iocs for any Telegram-sourced IOC mentioning this domain
        if ioc_score == 0:
            tg_resp = ioc_table.scan(
                FilterExpression=(
                    boto3.dynamodb.conditions.Attr("channel").begins_with("@") &
                    boto3.dynamodb.conditions.Attr("ioc_value").contains(base_name)
                ),
                Limit=10,
            )
            tg_iocs = [i for i in tg_resp.get("Items",[]) if domain not in i.get("ioc_value","")]
            if tg_iocs:
                ioc_score = 6
                factors.append(f"Dark web presence: {len(tg_iocs)} IOC reference(s) to {company} brand found in criminal Telegram channel corpus")
    except Exception:
        pass
    dim_scores["ioc_presence"] = ioc_score

    # Dimension 4: Ransomware victim listing (0-20)
    ransomware_score = 0
    try:
        rw_resp = ransomware_tbl.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("domain").eq(domain),
            Limit=5,
        )
        rw_items = rw_resp.get("Items", [])
        if rw_items:
            ransomware_score = 20
            groups = list({i.get("group", "") for i in rw_items if i.get("group")})
            factors.append(f"Ransomware victim: {domain} listed by {', '.join(groups[:3])} ransomware group(s)")
    except Exception:
        pass
    dim_scores["ransomware_victim"] = ransomware_score

    # Dimension 5: Active session exposure (0-10)
    session_score = 0
    try:
        sess_resp = sessions_tbl.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("matched_email").contains(domain),
            Limit=10,
        )
        sess_count = len(sess_resp.get("Items", []))
        session_score = min(10, sess_count * 5)
        if sess_count:
            factors.append(f"Active session exposure: {sess_count} stolen session cookie record(s) in criminal corpus")
    except Exception:
        pass
    dim_scores["session_exposure"] = session_score

    # Dimension 6: CVE exposure (0-15)
    # Full paginated scan of CISA KEV corpus for company-specific CVEs
    # Note: Limit on DynamoDB Scan caps items READ not items matched —
    #       must paginate to find all matches across 1,782 KEV records
    cve_score = 0
    try:
        cve_items = []
        kwargs = {"FilterExpression": boto3.dynamodb.conditions.Attr("vendor_project").eq(company)}
        # First try exact vendor match
        while True:
            resp = cve_table.scan(**kwargs)
            cve_items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

        # Fallback: search short_description if no exact vendor match
        if not cve_items:
            desc_items = []
            desc_kwargs = {"FilterExpression": boto3.dynamodb.conditions.Attr("short_description").contains(company)}
            while True:
                resp = cve_table.scan(**desc_kwargs)
                desc_items.extend(resp.get("Items", []))
                if "LastEvaluatedKey" not in resp:
                    break
                desc_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            cve_items = desc_items

        ransomware_cves = sum(1 for c in cve_items if c.get("known_ransomware_campaign_use","") not in ("","Unknown","No"))
        total_cves = len(cve_items)
        # Score scales with ransomware-linked CVE count — max 25 (equal weight to breach/infostealer)
        if ransomware_cves >= 50:    cve_score = 25
        elif ransomware_cves >= 20:  cve_score = 20
        elif ransomware_cves >= 10:  cve_score = 15
        elif ransomware_cves >= 5:   cve_score = 12
        elif ransomware_cves >= 2:   cve_score = 9
        elif ransomware_cves >= 1:   cve_score = 6
        elif total_cves >= 20:       cve_score = 5
        elif total_cves >= 5:        cve_score = 3
        if total_cves:
            factors.append(f"CVE exposure: {total_cves} actively exploited CVEs affecting {company} products ({ransomware_cves} linked to ransomware campaigns in CISA KEV)")
    except Exception:
        pass
    dim_scores["cve_exposure"] = cve_score

    total_score = min(100, sum(dim_scores.values()))
    active_dims = len([v for v in dim_scores.values() if v > 0])
    risk_level  = "CRITICAL" if total_score >= 70 else "HIGH" if total_score >= 45 else "MEDIUM" if total_score >= 22 else "LOW"
    grade       = "F" if total_score >= 70 else "D" if total_score >= 45 else "C" if total_score >= 25 else "B" if total_score >= 10 else "A"

    logger.info("identity-risk-score domain=%s score=%d risk=%s dims=%d", domain, total_score, risk_level, active_dims)
    return _ok({
        "domain":           domain,
        "risk_score":       total_score,
        "risk_level":       risk_level,
        "grade":            grade,
        "dimension_scores": dim_scores,
        "max_score":        100,
        "risk_factors":     factors,
        "summary": (
            f"Domain {domain} scores {total_score}/100 ({grade} — {risk_level}) across "
            f"{active_dims} of 6 monitored identity signal dimensions."
        ),
        "recommendation": (
            "CRITICAL: Active compromise indicators detected. Immediate incident response required across breach, credential, and threat infrastructure signals."
            if total_score >= 75 else
            "HIGH: Significant identity exposure. Prioritize credential rotation, MFA enforcement, and threat actor attribution review."
            if total_score >= 50 else
            "MEDIUM: Elevated risk signals across multiple surfaces. Review breach history, enforce MFA, and monitor for escalation."
            if total_score >= 25 else
            "LOW: Limited identity risk signals at this time. Continue standard monitoring cadence."
        ),
    })


#           { "webhook_url": "" }   — clears the webhook
# Response: { "webhook_url": "...", "status": "registered" }

def handle_webhook_configure(params: dict, api_key_str: str) -> dict:
    webhook_url = (params.get("webhook_url") or "").strip()
    if webhook_url and not webhook_url.startswith(("https://", "http://")):
        return _err("webhook_url must be a valid https:// URL")
    try:
        dynamodb.Table(API_KEYS_TABLE).update_item(
            Key={"api_key": api_key_str},
            UpdateExpression="SET webhook_url = :url",
            ExpressionAttributeValues={":url": webhook_url},
        )
    except Exception as exc:
        logger.exception("webhook configure failed: %s", exc)
        return _err("webhook configuration failed", 500)
    status = "registered" if webhook_url else "cleared"
    logger.info("webhook %s for key=%s url=%s", status, api_key_str[:16], webhook_url[:60])
    return _ok({"webhook_url": webhook_url, "status": status})


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/siem/configure
# ---------------------------------------------------------------------------
# Registers a SIEM/SOAR destination for the calling account, keyed by the
# account's email (not the API key) — monitor Lambdas (breach_monitor,
# domain_monitor, etc.) alert off relayshield_users/monitored-email records,
# not API keys, so lookups at alert time need to resolve by email. See
# relayshield_siem_connector.py for the format adapters and delivery logic.
# Request:  { "format": "splunk_hec"|"cef"|"xsoar_webhook", "url": "https://...",
#             "auth_token": "..." (optional), "enabled": bool (default true) }
# Response: { "format": "...", "url": "...", "enabled": bool, "status": "..." }

# Table name duplicated here rather than imported from
# relayshield_siem_connector.py — this Lambda is deployed as a single-file
# zip (relayshield-deploy skill convention), no local cross-file imports.
SIEM_DESTINATIONS_TABLE = "relayshield_siem_destinations"
_SIEM_FORMATS = {"splunk_hec", "cef", "xsoar_webhook"}


def handle_siem_configure(params: dict, api_key_str: str) -> dict:
    key_record = dynamodb.Table(API_KEYS_TABLE).get_item(Key={"api_key": api_key_str}).get("Item") or {}
    email = (key_record.get("email") or "").strip().lower()
    if not email:
        return _err("no account email on file for this API key — cannot register a SIEM destination", 400)

    fmt      = (params.get("format") or "").strip()
    url      = (params.get("url") or "").strip()
    enabled  = params.get("enabled", True)
    auth_tok = (params.get("auth_token") or "").strip()

    if not url and not fmt:
        # No format/url supplied — treat as a clear/disable request.
        try:
            dynamodb.Table(SIEM_DESTINATIONS_TABLE).update_item(
                Key={"customer_id": email},
                UpdateExpression="SET enabled = :e",
                ExpressionAttributeValues={":e": False},
            )
        except Exception as exc:
            logger.exception("siem configure clear failed for %s: %s", email, exc)
            return _err("SIEM configuration update failed", 500)
        return _ok({"status": "cleared"})

    if fmt not in _SIEM_FORMATS:
        return _err(f"format must be one of: {', '.join(sorted(_SIEM_FORMATS))}")
    if not url.startswith(("https://", "http://")):
        return _err("url must be a valid https:// URL")

    try:
        dynamodb.Table(SIEM_DESTINATIONS_TABLE).put_item(Item={
            "customer_id": email,
            "format":      fmt,
            "url":         url,
            "auth_token":  auth_tok,
            "enabled":     bool(enabled),
            "updated_at":  datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.exception("siem configure failed for %s: %s", email, exc)
        return _err("SIEM configuration update failed", 500)

    logger.info("SIEM destination %s for %s format=%s", "enabled" if enabled else "disabled", email, fmt)
    return _ok({"format": fmt, "url": url, "enabled": bool(enabled), "status": "registered"})


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/target-risk  /  POST /v1/payg/target-risk
# ---------------------------------------------------------------------------
# Correlation scoring engine: estimates probability that a domain is currently
# being targeted by threat actors. Combines six independent signal sources
# into a weighted score (0–100) with a probability tier and recommended action.
#
# Signal weights:
#   Ransomware victim listing         +40 (highest — known active attack)
#   Infostealer stealer log hits      +25 (active device compromise)
#   Pre-ransomware credential count   +15 per hit (capped at 20)
#   HIBP breach count                 +10 (5+ breaches)
#   Brand mention in criminal channel +15 (from identity_graph/brand intel)
#   CVE active exploit (KEV+EPSS)     +20 (if EPSS ≥50% for domain's sector)
#
# Request:  { "domain": "acme.com" }
# Response: {
#   "domain": "...", "target_risk_score": 0–100,
#   "probability_tier": "CRITICAL|HIGH|MEDIUM|LOW",
#   "signals": [...], "recommendation": "..."
# }

def handle_target_risk(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")

    score   = 0
    signals = []

    # Signal 1: Ransomware victim listing (+40)
    try:
        victim_resp  = dynamodb.Table(RANSOMWARE_TABLE_API).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("domain").eq(domain),
        )
        victims = victim_resp.get("Items", [])
        if victims:
            groups = [v.get("group", "") for v in victims]
            score += 40
            signals.append({"signal": "ransomware_victim", "weight": 40,
                             "detail": f"Listed by {', '.join(groups[:3])}"})
    except Exception as exc:
        logger.warning("target-risk ransomware check failed: %s", exc)

    # Signal 2+3: Infostealer hits + pre-ransomware credentials
    try:
        from urllib.parse import urlparse as _up
        # Check stealer log corpus for this domain
        ses_resp = dynamodb.Table(STOLEN_SESSIONS_TABLE_API).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("domain").contains(domain),
            Select="COUNT",
        )
        stealer_count = ses_resp.get("Count", 0)
        if stealer_count > 0:
            score += min(25, stealer_count * 5)
            signals.append({"signal": "stealer_log_hits", "weight": min(25, stealer_count * 5),
                             "detail": f"{stealer_count} credential/session entries in stealer corpus"})
    except Exception as exc:
        logger.warning("target-risk stealer check failed: %s", exc)

    # Signal 4: HIBP breach exposure
    try:
        hibp_key = _hibp_api_key()
        hibp_url = f"https://haveibeenpwned.com/api/v3/breacheddomain/{urllib.parse.quote(domain, safe='')}"
        hibp_req = urllib.request.Request(hibp_url,
            headers={"hibp-api-key": hibp_key, "user-agent": "RelayShield-TargetRisk/1.0"})
        with urllib.request.urlopen(hibp_req, timeout=15) as hr:
            breach_data = json.loads(hr.read())
        breach_count    = len(breach_data)
        account_count   = sum(len(v) for v in breach_data.values())
        if breach_count >= 5:
            score += 10
            signals.append({"signal": "breach_exposure", "weight": 10,
                             "detail": f"{breach_count} breaches, {account_count} accounts exposed"})
        elif breach_count > 0:
            score += 5
            signals.append({"signal": "breach_exposure", "weight": 5,
                             "detail": f"{breach_count} breach(es)"})
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning("target-risk HIBP failed: %s", exc)
    except Exception as exc:
        logger.warning("target-risk HIBP failed: %s", exc)

    # Signal 5: IOC corpus mention (brand monitoring signal)
    try:
        ioc_resp = dynamodb.Table(INTEL_IOCS_TABLE).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(domain),
            Limit=5,
        )
        if ioc_resp.get("Count", 0) > 0:
            score += 15
            signals.append({"signal": "criminal_channel_mention", "weight": 15,
                             "detail": f"Domain observed in criminal Telegram channels"})
    except Exception as exc:
        logger.warning("target-risk IOC check failed: %s", exc)

    # Signal 6: High-EPSS KEV CVEs in corpus (proxy for sector targeting)
    try:
        cve_resp = dynamodb.Table(INTEL_CVE_TABLE).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("epss_score").gte(
                boto3.dynamodb.types.Decimal(str(EPSS_THRESHOLD_HIGH))
            ),
            ProjectionExpression="cve_id, epss_score, vulnerability_name",
            Limit=5,
        )
        high_epss = cve_resp.get("Items", [])
        if high_epss:
            score += 20
            top = high_epss[0]
            signals.append({"signal": "high_epss_cves_active", "weight": 20,
                             "detail": f"{len(high_epss)} CVE(s) with ≥50% exploitation probability active globally — {top.get('cve_id', '')} ({top.get('vulnerability_name', '')[:60]})"})
    except Exception as exc:
        logger.warning("target-risk EPSS check failed: %s", exc)

    score = min(score, 100)

    if score >= 60:
        tier = "CRITICAL"
        rec  = (f"CRITICAL: Multiple high-confidence signals indicate {domain} is actively targeted. "
                "Treat as an active incident — isolate affected systems, rotate credentials, "
                "audit access logs, and engage incident response.")
    elif score >= 35:
        tier = "HIGH"
        rec  = (f"HIGH risk: {domain} shows significant exposure signals. "
                "Rotate credentials, audit vendor access, and increase monitoring frequency.")
    elif score >= 15:
        tier = "MEDIUM"
        rec  = f"MEDIUM risk: Some exposure detected for {domain}. Include in next security review cycle."
    else:
        tier = "LOW"
        rec  = f"LOW risk: No significant targeting signals detected for {domain}."

    logger.info("target-risk domain=%s score=%d tier=%s signals=%d",
                domain, score, tier, len(signals))
    return _ok({
        "record_type":       "threat_prediction",
        "domain":            domain,
        "target_risk_score": score,
        "probability_tier":  tier,
        "signals":           signals,
        "recommendation":    rec,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
    })

# Threat actor attribution — maps malware family tags to known groups.
# Sourced from public CTI reports (MITRE ATT&CK, Mandiant, CrowdStrike naming).
# Enhancement 4: SIGMA rule references for active malware families
# Links to community-maintained detection rules — added to IOC hit responses so
# TI subscribers get actionable hunt content alongside raw IOC data.
SIGMA_RULE_MAP: dict[str, str] = {
    "qakbot":        "https://github.com/SigmaHQ/sigma/search?q=qakbot",
    "emotet":        "https://github.com/SigmaHQ/sigma/search?q=emotet",
    "trickbot":      "https://github.com/SigmaHQ/sigma/search?q=trickbot",
    "lummac2":       "https://github.com/SigmaHQ/sigma/search?q=lumma",
    "redline":       "https://github.com/SigmaHQ/sigma/search?q=redline+stealer",
    "vidar":         "https://github.com/SigmaHQ/sigma/search?q=vidar",
    "cobalt_strike": "https://github.com/SigmaHQ/sigma/search?q=cobalt+strike",
    "dridex":        "https://github.com/SigmaHQ/sigma/search?q=dridex",
    "icedid":        "https://github.com/SigmaHQ/sigma/search?q=icedid",
    "bumblebee":     "https://github.com/SigmaHQ/sigma/search?q=bumblebee",
    "pikabot":       "https://github.com/SigmaHQ/sigma/search?q=pikabot",
    "clearfake":     "https://github.com/SigmaHQ/sigma/search?q=clearfake",
    "mirai":         "https://github.com/SigmaHQ/sigma/search?q=mirai",
    "remcos":        "https://github.com/SigmaHQ/sigma/search?q=remcos",
    "asyncrat":      "https://github.com/SigmaHQ/sigma/search?q=asyncrat",
}

THREAT_ACTOR_MAP: dict[str, str] = {
    "qakbot":        "TA505 / multiple financially-motivated actors",
    "emotet":        "TA542 (Mealybug)",
    "trickbot":      "Wizard Spider",
    "dridex":        "Evil Corp (TA505)",
    "icedid":        "Shatak (TA551)",
    "bumblebee":     "Exotic Lily (initial access broker)",
    "lummac2":       "Multiple threat actors (MaaS)",
    "redline":       "Multiple threat actors (MaaS)",
    "vidar":         "Multiple threat actors (MaaS)",
    "raccoon":       "TrafficStealer group",
    "stealc":        "Multiple threat actors (MaaS)",
    "pikabot":       "Water Curupira",
    "bazarloader":   "Wizard Spider",
    "cobalt_strike": "Multiple (post-exploitation framework)",
    "remcos":        "Breaking Security (MaaS)",
    "asyncrat":      "Multiple threat actors (open source RAT)",
    "clearfake":     "SocGholish operators",
    "mirai":         "Multiple IoT botnet operators",
}

# IOC source confidence weights — higher = more trusted source
IOC_SOURCE_WEIGHTS: dict[str, float] = {
    "threatfox":         0.90,
    "feodo_aggressive":  0.95,
    "feodo":             0.90,
    "malwarebazaar":     0.88,
    "spamhaus":          0.95,
    "urlhaus":           0.85,
    "emerging_threats":  0.80,
    "abuseipdb":         0.82,
    "talos":             0.85,
    "ipsum":             0.75,
    "blocklist_de":      0.70,
    "openphish":         0.80,
    "otx":               0.75,
    "logsmarket":        0.92,   # criminal channel — very high signal
    "breachforums":      0.88,
    "leakbase":          0.88,
    "exposed_vc":        0.85,
    "vxunderground":     0.85,
}


_ip_enrich_cache: dict[str, dict] = {}   # per-invocation cache


def _enrich_ip(ip: str) -> dict:
    """Context enrichment for an IP — ASN, country, city, ISP via ip-api.com.
    Free tier: 45 req/min, no auth. Cached per Lambda invocation."""
    if ip in _ip_enrich_cache:
        return _ip_enrich_cache[ip]
    try:
        url  = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,isp,org,as"
        req  = urllib.request.Request(url, headers={"User-Agent": "RelayShield-TI/1.0"})
        resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if resp.get("status") == "success":
            result = {
                "country":      resp.get("country", ""),
                "country_code": resp.get("countryCode", ""),
                "city":         resp.get("city", ""),
                "isp":          resp.get("isp", ""),
                "org":          resp.get("org", ""),
                "asn":          resp.get("as", ""),
            }
            _ip_enrich_cache[ip] = result
            return result
    except Exception:
        pass
    return {}


def _enrich_domain(domain: str) -> dict:
    """Lightweight domain context via RDAP (IANA standard, free, no auth).
    Returns registrar and registration date where available."""
    try:
        url  = f"https://rdap.org/domain/{domain}"
        req  = urllib.request.Request(url, headers={"User-Agent": "RelayShield-TI/1.0"})
        resp = json.loads(urllib.request.urlopen(req, timeout=8).read())
        events = {e.get("eventAction"): e.get("eventDate", "")
                  for e in resp.get("events", [])}
        entities = resp.get("entities", [])
        registrar = ""
        for e in entities:
            if "registrar" in e.get("roles", []):
                card = e.get("vcardArray", [None, []])[1]
                for field in card:
                    if field[0] == "fn":
                        registrar = field[3]
                        break
        return {
            "registrar":      registrar,
            "registered":     events.get("registration", "")[:10],
            "last_changed":   events.get("last changed", "")[:10],
        }
    except Exception:
        return {}


def _ioc_confidence(source: str, seen_ts: str) -> float:
    """Score 0.0–1.0 combining source weight and freshness decay.
    IOCs lose 2% confidence per week after ingestion, flooring at 0.40."""
    base  = IOC_SOURCE_WEIGHTS.get(source.lower(), 0.65)
    try:
        from datetime import datetime, timezone
        from dateutil import parser as dp
        age_days = (datetime.now(timezone.utc) - dp.parse(seen_ts)).days
    except Exception:
        age_days = 0
    decay = max(0.0, (age_days // 7) * 0.02)
    return round(max(0.40, base - decay), 2)


def handle_ransomware_risk(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")

    # Check victim list
    try:
        resp         = dynamodb.Table(RANSOMWARE_TABLE_API).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("domain").eq(domain),
        )
        victim_items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("ransomware-risk victim query failed domain=%s: %s", domain, exc)
        return _err("ransomware risk query failed — internal error", 500)

    # Count pre-ransomware tagged IOCs for this domain
    pre_ransomware_count = 0
    try:
        pr_resp = dynamodb.Table(INTEL_IOCS_TABLE).scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("pre_ransomware").eq(True) &
                boto3.dynamodb.conditions.Attr("ioc_value").contains(domain)
            ),
            Select="COUNT",
        )
        pre_ransomware_count = pr_resp.get("Count", 0)
    except Exception as exc:
        logger.warning("Pre-ransomware IOC count failed domain=%s: %s", domain, exc)

    on_victim_list = len(victim_items) > 0
    victim_groups  = list({i.get("group", "") for i in victim_items if i.get("group")})
    first_seen     = min((i.get("discovered", "") for i in victim_items), default="") if victim_items else ""

    if on_victim_list:
        risk_level = "CRITICAL"
        rec = (
            f"{domain} has been claimed as a ransomware victim by {', '.join(victim_groups)}. "
            "Treat any shared credentials, API tokens, or access grants from this domain as compromised. "
            "Rotate secrets immediately, audit access logs, and contact the affected organisation."
        )
    elif pre_ransomware_count > 0:
        risk_level = "HIGH"
        rec = (
            f"{pre_ransomware_count} credential(s) for {domain} appeared in criminal stealer logs "
            "before a ransomware incident was associated with this domain. These credentials may "
            "indicate pre-attack reconnaissance. Rotate any shared credentials with this organisation."
        )
    else:
        risk_level = "CLEAN"
        rec = f"No ransomware victim listing or pre-ransomware credential exposure found for {domain}."

    logger.info("ransomware-risk domain=%s victim=%s pre_creds=%d risk=%s",
                domain, on_victim_list, pre_ransomware_count, risk_level)
    return _ok({
        "domain":                   domain,
        "on_victim_list":           on_victim_list,
        "victim_groups":            victim_groups,
        "first_seen":               first_seen,
        "pre_ransomware_ioc_count": pre_ransomware_count,
        "risk_level":               risk_level,
        "recommendation":           rec,
        "checked_at":               datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Threat Intelligence API — /v1/intel/telegram
# ---------------------------------------------------------------------------
# Subscription endpoint (API key + intel_access flag required).
# Queries relayshield_intel_iocs — IOCs extracted from INTEL-2 Telegram channel
# pipeline — 24–72 hours ahead of HIBP and public breach databases.
#
# ---------------------------------------------------------------------------
# NHI (Non-Human Identity) detection patterns
# ---------------------------------------------------------------------------
# Matches credential patterns that infostealers steal beyond passwords:
# API keys, tokens, private keys found in stealer log credential files.

import re as _re


def _ctx_key(vendors: str, key_re: str) -> str:
    """Build a context-anchored credential regex (gitleaks style).

    Several LLM vendors (DeepSeek, Moonshot/Kimi, Alibaba DashScope/Qwen) issue
    OpenAI-compatible keys with a bare ``sk-`` prefix and publish no format spec,
    so the key alone is not attributable to a provider by shape. Requiring the
    vendor name or its env-var nearby is the only way to attribute one without
    guessing -- stealer-log dumps generally capture the surrounding ``.env`` line.
    The secret itself must be the single capturing group; _detect_nhi_in_text
    reports group(1) so the vendor context never leaks into the preview.
    """
    return (
        rf"(?i)(?:{vendors})[\w.\-]{{0,20}}[\s'\"]{{0,3}}"
        rf"(?:=|:|=>|:=|\|\|)[\s'\"`]{{0,5}}({key_re})"
    )


NHI_PATTERNS: list[tuple[str, str, str, str, str | None]] = [
    # (name, regex, severity, description, llm_provider)
    # llm_provider is None for non-LLM credentials, or a short provider slug
    # for LLM/AI API keys — used to power the dedicated LLMjacking check
    # (handle_llm_credential_exposure) without a second detection pass.
    ("aws_access_key",   r"AKIA[A-Z0-9]{16}",                         "CRITICAL", "AWS IAM Access Key", None),
    ("github_pat",       r"gh[pousr]_[a-zA-Z0-9]{36,}",              "CRITICAL", "GitHub Personal Access Token", None),
    ("github_pat_fine",  r"github_pat_[a-zA-Z0-9_]{82}",             "CRITICAL", "GitHub Fine-Grained PAT", None),
    ("stripe_secret",    r"sk_live_[a-zA-Z0-9]{24,}",                "CRITICAL", "Stripe Secret Key", None),
    ("private_key",      r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "CRITICAL", "Private Cryptographic Key", None),
    ("slack_bot",        r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+",        "HIGH",     "Slack Bot Token", None),
    ("slack_user",       r"xoxp-[0-9]+-[0-9]+-[0-9]+-[a-zA-Z0-9]+","HIGH",     "Slack User Token", None),
    # LLM/AI provider keys — bumped to CRITICAL 2026-07-26 (LLMjacking):
    # a leaked key here isn't just data exposure, it's a live, uncapped
    # billing liability — real incidents range from $46K/day (Sysdig, AWS
    # Bedrock) to $82K/48hr (leaked Gemini key) to a $500K single-month
    # bill from one unthrottled account. Underground price for a stolen
    # LLM key is ~$30 — the asymmetry between theft cost and victim damage
    # is exactly why this deserves CRITICAL, not the generic HIGH other
    # SaaS API keys get.
    ("google_api",       r"AIza[0-9A-Za-z\-_]{35}",                  "CRITICAL", "Google AI (Gemini) API Key", "google"),
    # OpenAI rebuilt its key format around prefixed keys (sk-proj-/sk-svcacct-/
    # sk-admin-) that contain hyphens and underscores and run far longer than the
    # 48-char legacy shape. The previous pattern (sk-[a-zA-Z0-9]{48}) matched ONLY
    # legacy keys, so every modern key was a silent false negative -- on the most
    # common LLM provider, in the LLMjacking product. Fixed 2026-07-28.
    # Both branches anchor on T3BlbkFJ, which is base64("OpenAI") embedded in the
    # key body (verified locally). That anchor is what makes attribution safe
    # despite the sk- prefix being shared with DeepSeek/Moonshot/Qwen.
    ("openai_key",       r"sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})T3BlbkFJ(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})",
                                                                     "CRITICAL", "OpenAI API Key", "openai"),
    ("openai_key_v1",    r"sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}", "CRITICAL", "OpenAI API Key (v1 format)", "openai"),
    # Legacy pre-2023 keys carry no T3BlbkFJ anchor, so a bare sk-+48 match cannot
    # be attributed to OpenAI rather than DeepSeek/Moonshot/Qwen. Context-anchored
    # instead of guessing -- see _ctx_key.
    ("openai_key_legacy", _ctx_key(r"openai|OPENAI_API_KEY", r"sk-[a-zA-Z0-9]{48}"),
                                                                     "CRITICAL", "OpenAI API Key (legacy format)", "openai"),
    # Underscore added to the body class 2026-07-28: real Anthropic keys contain
    # "_" as well as "-", and the previous class [a-zA-Z0-9\-] caused the {90,}
    # quantifier to fail on any key with an underscore in its first 90 body
    # chars -- a silent false negative of the same class as the OpenAI one above.
    # Kept looser than gitleaks' sk-ant-api03-...{93}AA so it survives a future
    # version bump past api03.
    ("anthropic_key",    r"sk-ant-[a-zA-Z0-9_\-]{90,}",              "CRITICAL", "Anthropic API Key", "anthropic"),
    ("groq_key",         r"gsk_[a-zA-Z0-9]{52}",                     "CRITICAL", "Groq API Key", "groq"),
    ("xai_key",          r"xai-[a-zA-Z0-9]{80}",                     "CRITICAL", "xAI (Grok) API Key", "xai"),
    ("replicate_key",    r"r8_[a-zA-Z0-9]{37}",                      "CRITICAL", "Replicate API Key", "replicate"),
    # --- added 2026-07-28 (TODO item 77) -------------------------------------
    # Amazon Bedrock now issues dedicated API keys used as bearer tokens via
    # AWS_BEARER_TOKEN_BEDROCK, distinct from IAM credentials. Because they are
    # Bedrock-scoped they CAN be tagged with an llm_provider, unlike generic AKIA
    # keys below. Both anchors verified locally:
    #   long-lived : ABSK + base64("BedrockAPIKey-") -> ABSKQmVkcm9ja0FQSUtleS...
    #   short-lived: literal "bedrock-api-key-" + base64("bedrock.amazonaws.com")
    ("bedrock_key_long",  r"ABSKQmVkcm9ja0FQSUtleS[A-Za-z0-9+/]{80,250}={0,2}",
                                                                     "CRITICAL", "Amazon Bedrock API Key (long-lived)", "bedrock"),
    ("bedrock_key_short", r"bedrock-api-key-YmVkcm9jay5hbWF6b25hd3MuY29t[A-Za-z0-9+/=]*",
                                                                     "CRITICAL", "Amazon Bedrock API Key (short-lived)", "bedrock"),
    # Hugging Face tokens are the highest-leverage LLM credential in this list:
    # Kimi, DeepSeek, Qwen and NVIDIA models are all reachable through HF
    # Inference Providers, so a leaked hf_ token bills against those models
    # without the attacker ever holding a vendor key. Body is letters only.
    ("huggingface_token", r"hf_[a-zA-Z]{34}",                        "CRITICAL", "Hugging Face User Access Token", "huggingface"),
    ("huggingface_org",   r"api_org_[a-zA-Z]{34}",                   "CRITICAL", "Hugging Face Organization Token", "huggingface"),
    # Alibaba Cloud AccessKey ID -- the cloud credential that grants Model Studio
    # (Qwen) access. Distinct from the DashScope sk- key, and unlike it this one
    # has a reliable, unambiguous prefix.
    ("alibaba_access_key_id", r"LTAI[a-zA-Z0-9]{20}",                "HIGH",     "Alibaba Cloud AccessKey ID (Qwen/Model Studio)", "alibaba"),
    # NVIDIA NIM (build.nvidia.com / integrate.api.nvidia.com). BEST-EFFORT
    # LENGTH: the "nvapi-" prefix is consistently attested across NVIDIA's own
    # docs and multiple independent sources, but no source documents the body
    # length or character set -- and gitleaks ships no NVIDIA rule at all, so
    # there is no external pattern to borrow. Shipped anyway on the same basis
    # as mcp_token_generic below: the prefix is distinctive enough to carry
    # attribution on its own (unlike the sk- family, which is why NVIDIA needs
    # no context anchor), so an open-ended {40,} risks a stray match rather than
    # a wrong provider label. Tighten if a real key length is ever confirmed.
    ("nvidia_nim_key",   r"nvapi-[A-Za-z0-9_\-]{40,}",               "CRITICAL", "NVIDIA NIM API Key", "nvidia"),
    # OpenAI-compatible vendors with no published key format. Context-anchored
    # rather than pattern-guessed, so provider attribution is never fabricated.
    ("deepseek_key",     _ctx_key(r"deepseek|DEEPSEEK_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "DeepSeek API Key", "deepseek"),
    ("moonshot_key",     _ctx_key(r"moonshot|kimi|MOONSHOT_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "Moonshot (Kimi) API Key", "moonshot"),
    ("qwen_key",         _ctx_key(r"dashscope|qwen|DASHSCOPE_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "Alibaba DashScope (Qwen) API Key", "qwen"),
    # Catch-all for a bare OpenAI-compatible key with no vendor context to
    # attribute it. Deliberately claims NO provider: the sk- prefix is shared by
    # OpenAI (legacy), DeepSeek, Moonshot/Kimi and DashScope/Qwen, so naming one
    # would be a fabricated attribution. HIGH rather than CRITICAL only because
    # a bare sk- string carries some residual false-positive risk from non-LLM
    # services; the billing liability if it is real is identical.
    # MUST stay last in this list -- _detect_nhi_in_text suppresses it for any
    # value an attributed pattern already claimed, so it never double-reports.
    ("llm_key_generic_sk", r"sk-[a-zA-Z0-9]{32,64}",                 "HIGH",     "OpenAI-compatible LLM API Key (provider unattributed)", "unknown_openai_compatible"),
    # Cohere and Azure OpenAI keys are opaque tokens with no verifiable
    # standardized prefix -- deliberately not pattern-matched rather than
    # shipping a guessed regex that would silently fail to catch real
    # leaked keys. (Cohere could be covered contextually via _ctx_key if it
    # ever justifies the noise; not done yet.)
    #
    # Corrected 2026-07-28: this block previously said Bedrock had no separate
    # key format and used plain IAM credentials. AWS has since shipped dedicated
    # Bedrock API keys -- see bedrock_key_long / bedrock_key_short above.
    # Generic AKIA IAM keys are still deliberately NOT tagged llm_provider
    # (most AWS key leaks have nothing to do with Bedrock; tagging every one
    # would make the dedicated LLM-exposure endpoint noisy) -- that reasoning
    # stands, it just no longer means Bedrock itself is undetectable.
    #
    # Still unshippable for lack of any published format (researched 2026-07-28,
    # see llmjacking_provider_regex_research.md): NVIDIA NIM (nvapi- prefix is
    # well attested but its length is documented nowhere) and Meta Muse Spark /
    # Meta Model API (format undisclosed, waitlisted public preview).
    ("sendgrid_key",     r"SG\.[a-zA-Z0-9\-_.]{22}\.[a-zA-Z0-9\-_.]{43}", "HIGH", "SendGrid API Key", None),
    ("twilio_sid",       r"AC[a-f0-9]{32}",                           "MEDIUM",   "Twilio Account SID", None),
    ("stripe_pub",       r"pk_live_[a-zA-Z0-9]{24,}",                "MEDIUM",   "Stripe Publishable Key", None),
    ("jwt_token",        r"eyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}", "MEDIUM", "JWT Token", None),
    # Agent-framework credentials (added 2026-07-07, AGENTIC-1) — AI agent
    # orchestration platforms are now a confirmed autonomous-attack target
    # (JadePuffer/Sysdig, July 2026).
    ("langsmith_key",    r"lsv2_(?:pt|sk)_[a-f0-9]{32,}",             "HIGH",     "LangSmith API Key", "langsmith"),
    # MCP has no standardized token format as of 2026-07 — this is a
    # best-effort pattern based on an emerging informal prefix convention
    # in some MCP server implementations, not a guaranteed catch-all.
    ("mcp_token_generic", r"mcp_(?:live|sk|pat)_[a-zA-Z0-9]{20,}",    "MEDIUM",   "Possible MCP Server Auth Token", None),
]

_NHI_COMPILED = [(name, _re.compile(pat), sev, desc, provider) for name, pat, sev, desc, provider in NHI_PATTERNS]


def _detect_nhi_in_text(text: str, domain: str) -> list[dict]:
    """Scan text for NHI credential patterns associated with a domain context."""
    findings = []
    seen: set[str] = set()
    # Values already claimed by a provider-attributed pattern. The unattributed
    # sk- catch-all (llm_key_generic_sk) is suppressed for these so a DeepSeek
    # key found via context is not also reported as an unknown generic key.
    attributed: set[str] = set()
    for name, pattern, severity, description, llm_provider in _NHI_COMPILED:
        for match in pattern.finditer(text):
            # Context-anchored patterns (_ctx_key) wrap the secret in the single
            # capturing group, so the vendor name / env-var prefix that anchored
            # the match never reaches the preview or the dedup key. Prefix-based
            # patterns have no capturing group and fall back to the whole match.
            val = match.group(1) if pattern.groups else match.group(0)
            if llm_provider == "unknown_openai_compatible":
                if val in attributed:
                    continue
            elif llm_provider:
                attributed.add(val)
            key = (name, val[:16])    # dedup on type + prefix
            if key not in seen:
                seen.add(key)
                finding = {
                    "type":        name,
                    "description": description,
                    "severity":    severity,
                    "preview":     val[:8] + "..." + val[-4:],   # never return full key
                }
                if llm_provider:
                    finding["llm_provider"] = llm_provider
                findings.append(finding)
    return findings


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/nhi-exposure  /  POST /v1/payg/nhi-exposure
# ---------------------------------------------------------------------------
# Scans the INTEL-5 stealer log corpus for non-human identity credentials
# (API keys, tokens, private keys) linked to a domain.
# Optionally checks vendor/supply chain domains for third-party NHI exposure.
#
# Request:
#   { "domain": "acme.com" }                      — your own domain
#   { "vendor_domains": ["acme.com", "co.io"] }   — supply chain NHI check
#   (Both keys may be combined)
#
# Response:
#   { "domains_checked": N, "findings": [ { domain, type, description,
#     severity, source, ingested_at, preview } ], "highest_severity": "..." }

NHI_SESSIONS_TABLE = "relayshield_stolen_sessions"


def handle_nhi_exposure(params: dict) -> dict:
    raw_domains  = list(params.get("vendor_domains") or [])
    own_domain   = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if own_domain:
        raw_domains.append(own_domain)
    if not raw_domains:
        return _err("domain or vendor_domains is required")

    domains = list({d.strip().lower().removeprefix("www.") for d in raw_domains if d.strip()})[:10]
    all_findings: list[dict] = []

    table = dynamodb.Table(NHI_SESSIONS_TABLE)
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    for domain in domains:
        # Scan credential-type stolen session entries for this domain
        try:
            resp  = table.scan(
                FilterExpression=(
                    boto3.dynamodb.conditions.Attr("session_type").eq("credential") &
                    boto3.dynamodb.conditions.Attr("domain").contains(domain)
                ),
            )
            items = resp.get("Items", [])
        except Exception as exc:
            logger.warning("NHI scan failed domain=%s: %s", domain, exc)
            items = []

        for item in items:
            # Use pre-classified NHI records first (from INTEL-5 archive parsing)
            if item.get("nhi_description"):
                all_findings.append({
                    "domain":      domain,
                    "type":        item.get("category", "Credential"),
                    "description": item.get("nhi_description", ""),
                    "severity":    item.get("severity", "HIGH"),
                    "preview":     item.get("cookie_name", ""),
                    "source":      item.get("channel_source", ""),
                    "ingested_at": item.get("ingested_at", ""),
                })
            else:
                # Fallback: detect NHI patterns in domain value text
                domain_val = item.get("domain", "")
                nhi_hits   = _detect_nhi_in_text(domain_val, domain)
                for hit in nhi_hits:
                    all_findings.append({
                        "domain":      domain,
                        "type":        hit["type"],
                        "description": hit["description"],
                        "severity":    hit["severity"],
                        "preview":     hit["preview"],
                        "source":      item.get("channel_source", ""),
                        "ingested_at": item.get("ingested_at", ""),
                    })

    if not all_findings:
        return _ok({
            "domains_checked":   len(domains),
            "found":             False,
            "findings":          [],
            "highest_severity":  None,
            "recommendation":    "No non-human identity credentials detected in the stealer log corpus for the supplied domain(s).",
            "checked_at":        datetime.now(timezone.utc).isoformat(),
        })

    all_findings.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)
    highest = all_findings[0]["severity"]
    critical = [f for f in all_findings if f["severity"] == "CRITICAL"]

    logger.info("nhi-exposure domains=%d findings=%d highest=%s", len(domains), len(all_findings), highest)
    return _ok({
        "domains_checked":   len(domains),
        "found":             True,
        "findings":          all_findings,
        "highest_severity":  highest,
        "recommendation": (
            f"CRITICAL: {len(critical)} high-value credential(s) detected. "
            "Rotate immediately — API keys and private keys found in stealer logs "
            "may be actively exploited. Check your cloud provider IAM access logs for "
            "unauthorised activity."
            if critical else
            "Non-human credentials detected. Rotate all identified keys and audit "
            "access logs for the affected services."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/llm-credential-exposure  /  POST /v1/payg/llm-credential-exposure
# ---------------------------------------------------------------------------
# LLMjacking detection — reuses the same INTEL-5 stealer log scan as
# nhi-exposure, filtered to only LLM/AI provider API keys (llm_provider tag
# on the matched pattern). Deliberately a separate endpoint rather than just
# a filter flag on nhi-exposure: LLMjacking is a distinct, fast-growing
# threat category with its own dollar-impact story (real incidents from
# $46K/day to a $500K single-month bill from one leaked/unthrottled key) —
# it deserves its own dedicated messaging, not to be buried inside generic
# "some API key leaked" language.
#
# Request:  { "domain": "acme.com" }  or  { "vendor_domains": [...] }  (same as nhi-exposure)
# Response: { "domains_checked": N, "found": bool, "findings": [...],
#             "highest_severity": "...", "providers_affected": [...],
#             "recommendation": "..." }

def handle_llm_credential_exposure(params: dict) -> dict:
    raw_domains = list(params.get("vendor_domains") or [])
    own_domain  = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if own_domain:
        raw_domains.append(own_domain)
    if not raw_domains:
        return _err("domain or vendor_domains is required")

    domains = list({d.strip().lower().removeprefix("www.") for d in raw_domains if d.strip()})[:10]
    llm_findings: list[dict] = []

    table = dynamodb.Table(NHI_SESSIONS_TABLE)
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    for domain in domains:
        try:
            resp  = table.scan(
                FilterExpression=(
                    boto3.dynamodb.conditions.Attr("session_type").eq("credential") &
                    boto3.dynamodb.conditions.Attr("domain").contains(domain)
                ),
            )
            items = resp.get("Items", [])
        except Exception as exc:
            logger.warning("LLM credential scan failed domain=%s: %s", domain, exc)
            items = []

        for item in items:
            # Primary path: llm_provider persisted at ingest by the stealer-log
            # parser. Added 2026-07-28 -- previously this endpoint ONLY regexed
            # item["domain"], but that attribute holds a bare hostname
            # ("adobe.com"), never raw key material, so no scan could ever
            # match and the endpoint could not return a finding for any input.
            # The detection has to happen where the credential text exists, at
            # ingest, and be read back here -- mirroring how nhi-exposure reads
            # the pre-classified nhi_description.
            if item.get("llm_provider"):
                llm_findings.append({
                    "domain":       domain,
                    "type":         item.get("nhi_type", "llm_credential"),
                    "llm_provider": item["llm_provider"],
                    "description":  item.get("nhi_description") or item.get("cookie_name", "LLM provider API key"),
                    "severity":     item.get("severity", "CRITICAL"),
                    "preview":      item.get("cookie_name", ""),
                    "source":       item.get("channel_source", ""),
                    "ingested_at":  item.get("ingested_at", ""),
                })
                continue
            # Fallback: rescan free text for records that predate the ingest-side
            # tagging, or any record whose domain field does carry raw log text.
            domain_val = item.get("domain", "")
            hits = [h for h in _detect_nhi_in_text(domain_val, domain) if h.get("llm_provider")]
            for hit in hits:
                llm_findings.append({
                    "domain":       domain,
                    "type":         hit["type"],
                    "llm_provider": hit["llm_provider"],
                    "description":  hit["description"],
                    "severity":     hit["severity"],
                    "preview":      hit["preview"],
                    "source":       item.get("channel_source", ""),
                    "ingested_at":  item.get("ingested_at", ""),
                })

    if not llm_findings:
        return _ok({
            "domains_checked":     len(domains),
            "found":               False,
            "findings":            [],
            "highest_severity":    None,
            "providers_affected":  [],
            "recommendation": (
                "No exposed LLM/AI provider API keys detected in the stealer log corpus for the "
                "supplied domain(s). Note: an AWS key exposure (see nhi-exposure) can also enable "
                "LLMjacking if that key has Bedrock access — this check only covers keys with a "
                "recognizable LLM-provider format, not every possible route to inference access."
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })

    llm_findings.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)
    highest = llm_findings[0]["severity"]
    providers_affected = sorted({f["llm_provider"] for f in llm_findings})

    logger.info("llm-credential-exposure domains=%d findings=%d providers=%s",
                len(domains), len(llm_findings), providers_affected)
    return _ok({
        "domains_checked":    len(domains),
        "found":              True,
        "findings":           llm_findings,
        "highest_severity":   highest,
        "providers_affected": providers_affected,
        "recommendation": (
            f"CRITICAL: {len(llm_findings)} exposed LLM/AI provider API key(s) detected "
            f"({', '.join(providers_affected)}). This is a live, uncapped billing liability, not "
            "just a data exposure — rotate immediately and check your provider's usage dashboard "
            "for anomalous spend right now, don't wait for the invoice. Real incidents have run "
            "from tens of thousands of dollars per day to a $500K single-month bill from one "
            "unthrottled key. If the key belongs to an autonomous agent, also verify it hasn't "
            "been used to spawn additional API keys or agent sessions."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/secret-scan  /  POST /v1/payg/secret-scan
# ---------------------------------------------------------------------------
# Scans public GitHub repositories for secrets accidentally committed
# alongside a monitored domain name. Covers own domains and supply chain domains.
#
# Request:
#   { "domain": "acme.com" }
#   { "vendor_domains": ["acme.com", "widget.io"] }
#
# Response:
#   { "domains_checked": N, "findings": [ { domain, repo, file, type, severity,
#     preview, url } ], "highest_severity": "..." }

GITHUB_SEARCH_URL = "https://api.github.com/search/code"
# NO GitLab constant here on purpose. GitLab code search (`blobs` scope) is
# Premium/Ultimate only at BOTH instance and project level, and every /search
# call 401s unauthenticated -- verified live 2026-08-02. A URL constant sat
# here unused for months while GitLab was advertised as covered. See BB-3.
GITHUB_SECRET_NAME = "relayshield/github_search_token"

# Literal, searchable prefixes per NHI pattern (BB-1, 2026-08-02).
#
# GitHub code search has NO regex support. The previous implementation sent
# `pattern.pattern[:20]` -- raw regex -- as a search term, so the engine matched
# the literal characters of the regex source. Measured against the live API:
#
#     "openai.com" AKIA[A-Z0-9]{16}       ->   119 results   (regex, broken)
#     "openai.com" AKIA                   -> 4,272 results   (literal, 36x)
#     "openai.com" gh[pousr]_[a-zA-Z0-9   ->   261 results   (truncated mid-class)
#     "openai.com" ghp_                   -> 3,552 results   (literal, 14x)
#
# `pattern.pattern[:20]` was also cutting `gh[pousr]_[a-zA-Z0-9]{36,}` mid
# character-class, which is why that one was worse than a plain bad query.
#
# An empty tuple means "no literal specific enough to search on". Those are the
# context-anchored `_ctx_key` patterns and the generic sk- catch-all, whose only
# literal is `sk-` -- far too common to be a useful query and guaranteed to
# return noise. They are deliberately NOT queried; they are still applied as
# real regexes to returned code fragments by _verify_github_fragment below, so
# they cost zero queries while remaining able to classify a hit.
_GITHUB_SEARCH_LITERALS: dict[str, tuple[str, ...]] = {
    "aws_access_key":        ("AKIA",),
    # gh[pousr]_ is five distinct real prefixes; ghp_ (classic PAT) is by far the
    # most common in public code, and each extra spelling costs a whole query
    # against a 10-req/min budget.
    "github_pat":            ("ghp_",),
    "github_pat_fine":       ("github_pat_",),
    "stripe_secret":         ("sk_live_",),
    "private_key":           ("BEGIN RSA PRIVATE KEY",),
    "slack_bot":             ("xoxb-",),
    "slack_user":            ("xoxp-",),
    "google_api":            ("AIza",),
    # Every modern OpenAI key embeds T3BlbkFJ -- base64("OpenAI") -- which is a
    # far more selective literal than the shared sk- prefix.
    "openai_key":            ("T3BlbkFJ",),
    "openai_key_v1":         ("T3BlbkFJ",),
    "openai_key_legacy":     (),
    "anthropic_key":         ("sk-ant-",),
    "groq_key":              ("gsk_",),
    "xai_key":               ("xai-",),
    "replicate_key":         ("r8_",),
    "bedrock_key_long":      ("ABSKQmVkcm9ja0FQSUtleS",),
    "bedrock_key_short":     ("bedrock-api-key-",),
    "huggingface_token":     ("hf_",),
    "huggingface_org":       ("api_org_",),
    "alibaba_access_key_id": ("LTAI",),
    "nvidia_nim_key":        ("nvapi-",),
    "deepseek_key":          (),
    "moonshot_key":          (),
    "qwen_key":              (),
    "llm_key_generic_sk":    (),
    "sendgrid_key":          ("SG.",),
    "twilio_sid":            (),   # "AC" + 32 hex is far too short/common to query
    "stripe_pub":            ("pk_live_",),
    "jwt_token":             ("eyJ",),
    "langsmith_key":         ("lsv2_",),
    "mcp_token_generic":     ("mcp_live_", "mcp_sk_", "mcp_pat_"),
}

# Max GitHub code-search queries per domain. GitHub allows 10 requests/minute
# authenticated (measured via /rate_limit, code_search.limit=10) and that budget
# is shared by EVERY customer, because all scans go through one RelayShield
# token. At 6 queries/domain, two concurrent single-domain scans already exceed
# the limit -- which is why the cache below is not an optimisation, it is what
# makes this endpoint viable at all.
_GITHUB_QUERY_BUDGET = 6

SECRET_SCAN_CACHE_TABLE   = "relayshield_secret_scan_cache"
SECRET_SCAN_CACHE_SECONDS = 24 * 3600   # founder-approved 24h TTL


def _secret_scan_cache_get(domain: str) -> list[dict] | None:
    try:
        item = dynamodb.Table(SECRET_SCAN_CACHE_TABLE).get_item(Key={"domain": domain}).get("Item")
        if not item:
            return None
        return [_decimals_to_plain(dict(f)) for f in item.get("findings", [])]
    except Exception as exc:
        logger.warning("secret-scan cache read failed for %s: %s", domain, exc)
        return None


def _secret_scan_cache_put(domain: str, findings: list[dict]) -> None:
    try:
        dynamodb.Table(SECRET_SCAN_CACHE_TABLE).put_item(Item={
            "domain": domain,
            "findings": findings,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(time.time()) + SECRET_SCAN_CACHE_SECONDS,
        })
    except Exception as exc:
        logger.warning("secret-scan cache write failed for %s: %s", domain, exc)


def _classify_github_fragment(pattern_name: str, item: dict) -> list[tuple[str, str, str]]:
    """Return every credential pattern genuinely present in a hit's code fragment.

    GitHub matched a literal prefix, not the full credential pattern, so a hit is
    a *candidate*, not a finding. Two jobs, both measured against the live API:

    1. **Reject false positives (BB-1).** 5 of the top 5 hits for
       `"openai.com" AKIA` were noise -- a docs table listing OPENAI_API_KEY, the
       literal placeholder `aws_access_key_id=AKIA....`, a README describing which
       formats it redacts, a link list, and a domain allowlist. All five would
       have reached the customer as a CRITICAL AWS key exposure.

    2. **Classify for free (BB-2).** Running all 31 compiled regexes over the
       fragment means low-signal patterns -- and the 6 with no searchable literal
       at all -- get classified without ever costing one of the 10 queries/minute
       GitHub allows. A repo surfaced by `AKIA` that actually leaks a `ghp_` is
       reported as the GitHub token it is, not mislabelled as an AWS key.

    Returns a list of (name, severity, description). An **empty list means
    reject**. When no fragment is available it degrades open, returning the
    pattern that was queried, so a missing text-match payload falls back to the
    old behaviour instead of silently dropping real findings.
    """
    fragments = [
        m.get("fragment", "")
        for m in (item.get("text_matches") or [])
        if m.get("fragment")
    ]

    def _queried() -> list[tuple[str, str, str]]:
        for name, _pattern, sev, desc, _prov in _NHI_COMPILED:
            if name == pattern_name:
                return [(name, sev, desc)]
        return []

    if not fragments:
        return _queried()   # degrade open -- never drop a hit for lack of a fragment

    blob = "\n".join(fragments)
    matched: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, pattern, sev, desc, _prov in _NHI_COMPILED:
        if name not in seen and pattern.search(blob):
            seen.add(name)
            matched.append((name, sev, desc))
    return matched


def _github_secret_scan(domain: str) -> tuple[list[dict], bool]:
    """Search GitHub public repos for NHI patterns alongside a domain.

    Returns (findings, was_cached). The cache is mandatory rather than an
    optimisation: the 10 req/min code-search budget is per TOKEN and RelayShield
    uses one token for every customer, so two concurrent uncached single-domain
    scans already blow the limit. A cache miss on a rate-limited window would
    otherwise return an empty list -- a silent false all-clear, the same class of
    defect as BUNDLE-B-5's non-firing writer.
    """
    cached = _secret_scan_cache_get(domain)
    if cached is not None:
        return cached, True

    findings = []
    try:
        raw = secrets_client.get_secret_value(SecretId=GITHUB_SECRET_NAME)["SecretString"].strip()
        token = json.loads(raw).get("token", raw) if raw.startswith("{") else raw
        headers = {
            "Authorization": f"Bearer {token}",
            # text-match media type is what makes the API return the matching code
            # fragment. Without it there is nothing to verify a hit against, so
            # _verify_github_fragment cannot reject blocklist-style false positives.
            "Accept": "application/vnd.github.text-match+json",
            "User-Agent": "RelayShield-SecretScan/1.0",
        }
    except Exception:
        headers = {
            "Accept": "application/vnd.github.text-match+json",
            "User-Agent": "RelayShield-SecretScan/1.0",
        }  # unauthenticated fallback

    # 5-tuple unpack: llm_provider was appended to NHI_PATTERNS on 2026-07-26 for
    # the LLMjacking check and this call site was not updated, so every call to
    # this endpoint raised ValueError at the for statement (outside the inner
    # try) and returned 500. Fixed 2026-07-31.
    #
    # Selection is now literal-aware rather than a blind _NHI_COMPILED[:6]: only
    # patterns with a searchable literal are queried, highest severity first, so
    # the budget is never spent on a pattern that cannot produce a usable query.
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    queryable = [
        (name, pattern, severity, description, literal)
        for name, pattern, severity, description, _llm_provider in _NHI_COMPILED
        for literal in _GITHUB_SEARCH_LITERALS.get(name, ())
    ]
    queryable.sort(key=lambda r: severity_rank.get(r[2], 9))
    seen_hits: set[tuple[str, str, str]] = set()
    planned = queryable[:_GITHUB_QUERY_BUDGET]
    completed = 0

    for name, pattern, severity, description, literal in planned:
        try:
            query = f'"{domain}" {literal}'   # domain + LITERAL prefix, never regex
            url   = f"{GITHUB_SEARCH_URL}?q={urllib.parse.quote(query)}&per_page=5"
            req   = urllib.request.Request(url, headers=headers)
            resp  = json.loads(urllib.request.urlopen(req, timeout=10).read())
            for item in resp.get("items", []):
                repo = item.get("repository", {}).get("full_name", "")
                path = item.get("path", "")
                classified = _classify_github_fragment(name, item)
                if not classified:
                    logger.info(
                        "GitHub hit rejected as false positive pattern=%s repo=%s file=%s",
                        name, repo, path,
                    )
                    continue
                # One hit can legitimately carry several credential types; emit each
                # once per repo+file so a single leaky .env is not collapsed to
                # whichever pattern happened to surface it.
                for c_name, c_sev, c_desc in classified:
                    dedup = (repo, path, c_name)
                    if dedup in seen_hits:
                        continue
                    seen_hits.add(dedup)
                    findings.append({
                        "source":      "github",
                        "type":        c_name,
                        "description": c_desc,
                        "severity":    c_sev,
                        "repo":        repo,
                        "file":        path,
                        "url":         item.get("html_url", ""),
                        "preview":     f"Match in {path}",
                        # Which query surfaced it, when that differs from what was
                        # actually found -- makes the classify-for-free path visible
                        # in support tickets instead of looking like a mislabel.
                        **({"surfaced_by": name} if c_name != name else {}),
                    })
            completed += 1
        except Exception as exc:
            logger.warning("GitHub scan failed pattern=%s domain=%s: %s", name, domain, exc)

    # Only cache a COMPLETE scan. A partial run -- typically the shared token
    # hitting 10 req/min -- must never be written, or a rate-limited moment gets
    # frozen in as a 24h "all clear" for that domain. Same reasoning as the
    # silent-false-all-clear defects found on 2026-07-31.
    if completed == len(planned) and planned:
        _secret_scan_cache_put(domain, findings)
    else:
        logger.warning(
            "secret-scan incomplete for %s (%d/%d queries) - not cached",
            domain, completed, len(planned),
        )

    return findings, False


RSSCAN_INSTALLS_TABLE = "relayshield_rsscan_installs"


def handle_rsscan_install(params: dict) -> dict:
    """Record that an rsscan install at some org domain ran a scan.

    Unauthenticated on purpose: requiring a key to report adoption would defeat
    the point, since the whole funnel premise is that the free tool needs no
    account. Opt-in on the client (`--org`), off by default.

    **Deliberately stores nothing sensitive.** Org domain, an anonymous
    per-machine install id, tool version and per-severity counts. No file paths,
    no fingerprints, no repo names, no source and no secret values -- and if a
    future caller wants to send those, the answer is no. Anything richer than a
    count turns an adoption signal into a data-handling liability.

    Aggregation to "how many distinct engineers at this company" is a COUNT over
    install_id per org, done at read time; nothing here identifies a person.
    """
    org = (params.get("org") or "").strip().lower().removeprefix("www.")
    install_id = (params.get("install_id") or "").strip()
    if not org or not install_id:
        return _err("org and install_id are required")
    # Cheap sanity check -- this is an open endpoint, so don't let it become a
    # free-text store. A domain has a dot and no whitespace.
    if len(org) > 253 or "." not in org or any(c.isspace() for c in org):
        return _err("org must be a domain")
    if len(install_id) > 64 or not install_id.isalnum():
        return _err("install_id must be alphanumeric")

    counts = params.get("counts") or {}
    safe_counts = {
        k: int(v)
        for k, v in counts.items()
        if k in ("CRITICAL", "HIGH", "MEDIUM", "LOW") and isinstance(v, (int, float))
    } if isinstance(counts, dict) else {}

    try:
        dynamodb.Table(RSSCAN_INSTALLS_TABLE).put_item(Item={
            "org":          org,
            "install_id":   install_id,
            "version":      str(params.get("version") or "")[:32],
            "last_seen":    datetime.now(timezone.utc).isoformat(),
            "last_counts":  safe_counts,
            # Retention cap: an install that stops reporting ages out rather than
            # accumulating forever.
            "ttl":          int(time.time()) + 180 * 86400,
        })
    except Exception as exc:
        # Never surface a storage failure to a developer's commit hook.
        logger.warning("rsscan install signal write failed org=%s: %s", org, exc)

    logger.info("rsscan install org=%s version=%s counts=%s", org, params.get("version"), safe_counts)
    return _ok({"recorded": True})


# ---------------------------------------------------------------------------
# BB-4 / BB-5 / BB-6 / BB-7 — package, image, model-hub and API-collection sources
# ---------------------------------------------------------------------------
# Secrets ship inside published artifacts constantly, and that is a genuinely
# different surface from repo scanning: GitGuardian's public monitoring is
# GitHub-centric, so a key that only ever leaked in a published wheel or an
# image description is invisible to it.
#
# Every API below was verified reachable UNAUTHENTICATED before this was built
# (2026-08-02) -- the lesson from BB-3, where GitLab was advertised for months
# behind an endpoint that 401s for everyone and needs a paid tier.
#
# Bounded on purpose: a fixed number of artifacts per source per scan. These
# APIs are far more generous than GitHub's 10 req/min, but an unbounded fan-out
# over an org with hundreds of packages would be slow and expensive for no
# additional signal.
_SOURCE_ARTIFACT_LIMIT = 10
_PYPI_SIMPLE_URL = "https://pypi.org/simple/"


def _org_token(domain: str) -> str:
    """Reduce a domain to the token an artifact is likely published under.

    acme.com -> acme, my-corp.co.uk -> my-corp. Deliberately naive: a wrong
    token yields no matches rather than wrong matches, and every hit is
    fingerprint-verified downstream anyway.
    """
    host = (domain or "").strip().lower().removeprefix("www.")
    first = host.split(".")[0] if host else ""
    return first if len(first) >= 3 else ""      # 1-2 char tokens match everything


def _http_json(url: str, timeout: int = 10) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-SecretScan/1.0"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as exc:
        logger.warning("source fetch failed url=%s: %s", url.split("?")[0], exc)
        return None


def _http_json_post(url: str, payload: dict, timeout: int = 10) -> dict | list | None:
    """POST variant of _http_json. Postman's search is the only POST source."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "User-Agent":   "RelayShield-SecretScan/1.0",
                "Content-Type": "application/json",
            },
        )
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as exc:
        logger.warning("source post failed url=%s: %s", url.split("?")[0], exc)
        return None


def _findings_from_text(text: str, *, source: str, artifact: str, url: str) -> list[dict]:
    """Run the credential patterns over an artifact's text and shape the results.

    Reuses _scan_text_for_secrets, so these sources inherit the same patterns,
    the same never-return-the-value rule and the same fingerprints as the
    pre-commit path -- one detection engine, not a second one that can drift.
    """
    out = []
    for f in _scan_text_for_secrets(text or "", artifact):
        out.append({
            "source":      source,
            "type":        f["type"],
            "description": f["description"],
            "severity":    f["severity"],
            "repo":        artifact,
            "file":        artifact,
            "url":         url,
            "preview":     f"Match in {artifact}",
            "fingerprint": f["fingerprint"],
        })
    return out


def _npm_secret_scan(org: str) -> list[dict]:
    """BB-4a — npm. Registry search, then each package's own README."""
    findings: list[dict] = []
    data = _http_json(
        f"https://registry.npmjs.org/-/v1/search?text={urllib.parse.quote(org)}"
        f"&size={_SOURCE_ARTIFACT_LIMIT}"
    )
    for obj in (data or {}).get("objects", [])[:_SOURCE_ARTIFACT_LIMIT]:
        name = (obj.get("package") or {}).get("name")
        if not name:
            continue
        doc = _http_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@/')}")
        if not doc:
            continue
        blob = "\n".join(filter(None, [doc.get("readme", ""), json.dumps(doc.get("versions", {}).get(
            (doc.get("dist-tags") or {}).get("latest", ""), {}).get("scripts", {}))]))
        findings += _findings_from_text(
            blob, source="npm", artifact=name, url=f"https://www.npmjs.com/package/{name}")
    return findings


def _pypi_secret_scan(org: str) -> list[dict]:
    """BB-4b — PyPI. Discovery has no search API, so the simple index is streamed.

    PyPI removed its search API, so "which packages belong to this org" has no
    endpoint. The simple index does answer it, but it is ~45 MB. Measured on
    this Lambda's shape: streaming it with a chunked regex costs 5.6s and a
    28 MB peak RSS, against a 256 MB / 120s budget -- json.load() of the same
    payload would not fit. Never buffer the whole body.
    """
    names: list[str] = []
    try:
        pat = _re.compile(rb'>([^<]*' + _re.escape(org.encode()) + rb'[^<]*)</a>', _re.I)
        req = urllib.request.Request(_PYPI_SIMPLE_URL, headers={"User-Agent": "RelayShield-SecretScan/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            tail = b""
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                buf = tail + chunk
                for m in pat.finditer(buf):
                    n = m.group(1).decode(errors="replace")
                    if n not in names:
                        names.append(n)
                if len(names) >= _SOURCE_ARTIFACT_LIMIT * 3:
                    break                      # plenty; stop pulling 45 MB
                tail = buf[-200:]              # overlap so a name split across chunks still matches
    except Exception as exc:
        logger.warning("pypi index stream failed org=%s: %s", org, exc)
        return []

    findings: list[dict] = []
    for name in names[:_SOURCE_ARTIFACT_LIMIT]:
        doc = _http_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
        info = (doc or {}).get("info") or {}
        findings += _findings_from_text(
            info.get("description") or "", source="pypi", artifact=name,
            url=f"https://pypi.org/project/{name}/")
    return findings


def _dockerhub_secret_scan(org: str) -> list[dict]:
    """BB-5 — Docker Hub. Repo descriptions; high signal, poorly served elsewhere."""
    findings: list[dict] = []
    data = _http_json(
        f"https://hub.docker.com/v2/search/repositories/?query={urllib.parse.quote(org)}"
        f"&page_size={_SOURCE_ARTIFACT_LIMIT}"
    )
    for repo in (data or {}).get("results", [])[:_SOURCE_ARTIFACT_LIMIT]:
        name = repo.get("repo_name")
        if not name:
            continue
        blob = "\n".join(filter(None, [repo.get("short_description"), repo.get("description")]))
        findings += _findings_from_text(
            blob, source="dockerhub", artifact=name, url=f"https://hub.docker.com/r/{name}")
    return findings


def _huggingface_secret_scan(org: str) -> list[dict]:
    """BB-7 — Hugging Face models and Spaces. On-brand; model cards leak keys."""
    findings: list[dict] = []
    for kind, web in (("models", ""), ("spaces", "spaces/")):
        data = _http_json(
            f"https://huggingface.co/api/{kind}?search={urllib.parse.quote(org)}"
            f"&limit={_SOURCE_ARTIFACT_LIMIT}&full=true"
        )
        for item in (data or [])[:_SOURCE_ARTIFACT_LIMIT]:
            rid = item.get("id")
            if not rid:
                continue
            card = item.get("cardData")
            blob = json.dumps(card) if card else ""
            blob += "\n" + (item.get("description") or "")
            findings += _findings_from_text(
                blob, source=f"huggingface_{kind}", artifact=rid,
                url=f"https://huggingface.co/{web}{rid}")
    return findings


_POSTMAN_SEARCH_URL = "https://www.postman.com/_api/ws/proxy"


def _postman_secret_scan(org: str) -> list[dict]:
    """BB-6 — Postman public workspaces and collections.

    A well known and underserved leak surface: teams publish an API collection
    to share it, and the description, the example requests and the environment
    notes routinely carry a working key. GitGuardian's public monitoring is
    GitHub-centric, so none of this is covered by a repo scanner.

    Verified unauthenticated 2026-08-05 before building, per the BB-3 lesson.
    The public search is a POST through Postman's own web proxy -- there is no
    documented REST search endpoint, this is the one the site itself calls.

    The description comes back INSIDE the search response (measured up to
    ~3.5 KB), so unlike the request/header surface this needs no second fetch
    per collection, which keeps it to one HTTP call per domain.
    """
    data = _http_json_post(_POSTMAN_SEARCH_URL, {
        "service": "search",
        "method":  "POST",
        "path":    "/search-all",
        "body": {
            # Both indices: a workspace description leaks as readily as a
            # collection's, and they are ranked into one result set.
            "queryIndices":      ["collaboration.workspace", "runtime.collection"],
            "queryText":         org,
            "size":              _SOURCE_ARTIFACT_LIMIT,
            "from":              0,
            "clientTraceId":     "",
            "requestOrigin":     "srp",
            "mergeEntities":     True,
            "nonNestedRequests": True,
        },
    })

    findings: list[dict] = []
    for item in (data or {}).get("data", [])[:_SOURCE_ARTIFACT_LIMIT]:
        doc = item.get("document") or {}
        name = doc.get("name")
        if not name:
            continue

        kind      = doc.get("entityType") or "collection"
        publisher = doc.get("publisherHandle") or ""
        ident     = doc.get("id") or ""

        # Public URL. Workspaces expose a slug; collections hang off their
        # workspace's slug. Fall back to the publisher page rather than
        # emitting a broken link -- a finding a customer cannot open is noise.
        slug = ""
        for ws in (doc.get("workspaces") or []):
            if ws.get("slug"):
                slug = ws["slug"]
                break
        if kind == "workspace" and publisher and slug:
            url = f"https://www.postman.com/{publisher}/{slug}"
        elif publisher and slug and ident:
            url = f"https://www.postman.com/{publisher}/{slug}/collection/{ident}"
        elif publisher:
            url = f"https://www.postman.com/{publisher}"
        else:
            url = "https://www.postman.com/search?q=" + urllib.parse.quote(org)

        blob = "\n".join(filter(None, [
            doc.get("name"), doc.get("summary"), doc.get("description"),
        ]))
        findings += _findings_from_text(
            blob, source=f"postman_{kind}", artifact=name, url=url)
    return findings


def handle_secret_scan(params: dict) -> dict:
    raw_domains = list(params.get("vendor_domains") or [])
    own_domain  = (params.get("domain") or "").strip().lower().removeprefix("www.")
    if own_domain:
        raw_domains.append(own_domain)
    if not raw_domains:
        return _err("domain or vendor_domains is required")

    domains      = list({d.strip().lower().removeprefix("www.") for d in raw_domains if d.strip()})[:5]
    all_findings: list[dict] = []
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    # Per-domain cache state, reported honestly rather than hidden. A caller that
    # cannot tell a fresh scan from a 24h-old one cannot tell a real all-clear
    # from a stale one.
    coverage: list[dict] = []

    # Which artifact sources to run. GitHub is the repo surface; the rest are
    # published-artifact surfaces (BB-4/5/7) that repo scanning cannot see -- a
    # key that only ever leaked in a published wheel or an image description is
    # invisible to a GitHub-centric scanner.
    include_artifacts = params.get("include_artifact_sources", True)

    # Wall-clock budget. Measured 2026-08-02: artifact discovery costs ~12.5s per
    # domain (PyPI's 45 MB index stream dominates), and this endpoint accepts up
    # to 5 domains against a 120s Lambda timeout. Without a deadline a cold
    # 5-domain scan can be killed mid-flight, which returns nothing at all --
    # a false all-clear, the worst possible failure for this product. Past the
    # budget we stop starting new artifact work and report reduced coverage
    # honestly instead.
    artifact_deadline = time.time() + 75

    for domain in domains:
        hits, was_cached = _github_secret_scan(domain)
        for h in hits:
            h["domain"] = domain
        all_findings.extend(hits)
        sources_run = ["github"]

        org = _org_token(domain) if include_artifacts else ""
        if org:
            for label, fn in (
                ("npm",         _npm_secret_scan),
                ("pypi",        _pypi_secret_scan),
                ("dockerhub",   _dockerhub_secret_scan),
                ("huggingface", _huggingface_secret_scan),
                ("postman",     _postman_secret_scan),
            ):
                if time.time() > artifact_deadline:
                    logger.warning(
                        "artifact budget exhausted, skipping %s for %s", label, domain)
                    break
                try:
                    extra = fn(org)
                except Exception as exc:
                    # One dead upstream must never blank the whole scan -- that
                    # would surface to the customer as a false all-clear.
                    logger.warning("source %s failed org=%s: %s", label, org, exc)
                    continue
                for h in extra:
                    h["domain"] = domain
                all_findings.extend(extra)
                sources_run.append(label)

        coverage.append({
            "domain":  domain,
            "cached":  was_cached,
            "sources": sources_run,
        })

    if not all_findings:
        return _ok({
            "domains_checked":  len(domains),
            "found":            False,
            "findings":         [],
            "highest_severity": None,
            "coverage":         coverage,
            "recommendation":   "No secrets detected in public GitHub repositories for the supplied domain(s).",
            "checked_at":       datetime.now(timezone.utc).isoformat(),
        })

    all_findings.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)
    highest  = all_findings[0]["severity"]
    critical = [f for f in all_findings if f["severity"] == "CRITICAL"]

    logger.info("secret-scan domains=%d findings=%d highest=%s", len(domains), len(all_findings), highest)
    return _ok({
        "domains_checked":  len(domains),
        "found":            True,
        "findings":         all_findings,
        "highest_severity": highest,
        "coverage":         coverage,
        "recommendation": (
            f"CRITICAL: {len(critical)} high-value secret(s) found in public repositories. "
            "Rotate these credentials immediately — GitHub repos are indexed and may already "
            "have been scraped by automated secret hunters."
            if critical else
            "Secrets found in public repositories. Rotate and revoke, then audit git history "
            "to confirm the secret has been fully purged (git history rewrite may be required)."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/secret-scan-text  /  POST /v1/payg/secret-scan-text
# ---------------------------------------------------------------------------
# Scans submitted text or a unified diff for the same 31 NHI credential patterns
# handle_secret_scan uses, with no external API call — the detection is entirely
# local, so this costs nothing per call beyond compute.
#
# Platform-agnostic by design. handle_secret_scan asks "is this domain's secret
# already public on GitHub", which is CI-shaped and after-the-fact. This asks
# "does this text contain a secret", which any client can call before a commit
# ever enters history: the pre-commit hook, a GitHub Action, a GitLab CI
# component, or a plain curl from Jenkins/CircleCI/Azure DevOps/Bitbucket.
#
# Three deliberate constraints, because the submitted content is by definition
# unreviewed source that may contain the very secrets being scanned for:
#   1. The content is never logged and never persisted. Only counts and pattern
#      names reach the log line.
#   2. Matched values are never echoed back. Callers get a byte offset, a line
#      number and a truncated SHA-256 fingerprint, which is enough to locate the
#      secret in a file they already hold and to maintain an allowlist, without
#      the secret making a second trip over the wire.
#   3. Payloads are capped, and oversized ones are rejected rather than silently
#      truncated — a silent truncation would report "clean" for a file whose
#      secret sat past the cutoff.
#
# Request:
#   { "content": "...", "filename": "src/config.py" }   # arbitrary text
#   { "diff": "..." }                                    # unified diff
#
# When "diff" is supplied only added lines are scanned, and filenames/line
# numbers are recovered from the +++ and @@ headers, so a hook that sends
# `git diff --cached` does not re-flag secrets that were already in the file.

SECRET_SCAN_TEXT_MAX_BYTES = 1_048_576   # 1 MiB


def _fingerprint_secret(value: str) -> str:
    """Stable, non-reversible id for a matched secret.

    Lets a caller dedupe findings across runs and maintain an allowlist without
    us returning, logging or storing the secret itself. Truncated to 16 hex
    chars: collision-irrelevant at this scale, and short enough to paste into a
    config file.
    """
    import hashlib   # imported locally, matching this file's existing convention
    return "sha256:" + hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]


def _scan_text_for_secrets(text: str, filename: str = "") -> list[dict]:
    """Run every NHI pattern over `text`, returning located findings.

    Deliberately does not reuse _detect_nhi_in_text: that one is domain-context
    aware and returns a `preview` of the matched value, which is exactly what
    must not cross this boundary.
    """
    findings: list[dict] = []
    seen: set[tuple[str, int]] = set()
    attributed: set[str] = set()

    # Precompute line starts once so offset -> line is a bisect, not a rescan.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    for name, pattern, severity, description, llm_provider in _NHI_COMPILED:
        for match in pattern.finditer(text):
            # Context-anchored patterns keep the secret in group 1 so the vendor
            # name that anchored the match is not fingerprinted along with it.
            val   = match.group(1) if pattern.groups else match.group(0)
            start = match.start(1) if pattern.groups else match.start(0)

            # Mirror _detect_nhi_in_text's attribution rule: a provider-attributed
            # key must not also be reported by the unattributed sk- catch-all.
            if llm_provider == "unknown_openai_compatible":
                if val in attributed:
                    continue
            elif llm_provider:
                attributed.add(val)

            key = (val, start)
            if key in seen:
                continue
            seen.add(key)

            findings.append({
                "type":        name,
                "description": description,
                "severity":    severity,
                "line":        _bisect.bisect_right(line_starts, start),
                "byte_offset": start,
                "length":      len(val),
                "fingerprint": _fingerprint_secret(val),
                "llm_provider": llm_provider,
                "file":        filename,
            })

    return findings


def _scan_unified_diff(diff: str) -> list[dict]:
    """Scan only the added lines of a unified diff.

    Existing secrets already in a file are somebody else's problem (and already
    in history); a pre-commit hook must only block on what this commit adds, or
    it becomes unbypassable noise on any repo with legacy findings.

    Added lines are reassembled per file and scanned as one block so a pattern
    is not missed at a line boundary, while a side table maps the reassembled
    offsets back to real line numbers in the new file.
    """
    findings: list[dict] = []
    current_file = ""
    new_lineno   = 0
    buf: list[str] = []
    line_map: list[int] = []

    def flush() -> None:
        nonlocal buf, line_map
        if buf:
            block = "\n".join(buf)
            for f in _scan_text_for_secrets(block, current_file):
                idx = f["line"] - 1
                f["line"] = line_map[idx] if 0 <= idx < len(line_map) else 0
                # Offsets are relative to the reassembled added-lines block, not
                # the file on disk, and would mislead. The line number is the
                # locator that survives; drop the offset rather than lie.
                f.pop("byte_offset", None)
                findings.append(f)
        buf, line_map = [], []

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            flush()
            path = raw[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current_file = "" if path == "/dev/null" else path
        elif raw.startswith("@@"):
            m = _re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
            new_lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            buf.append(raw[1:])
            line_map.append(new_lineno)
            new_lineno += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            pass                      # removed line: not in the new file
        elif raw.startswith("\\"):
            pass                      # "\ No newline at end of file"
        else:
            new_lineno += 1           # context line

    flush()
    return findings


def handle_secret_scan_text(params: dict) -> dict:
    diff     = params.get("diff")
    content  = params.get("content")
    filename = (params.get("filename") or "").strip()

    if diff is None and content is None:
        return _err("content or diff is required")
    if diff is not None and content is not None:
        return _err("supply either content or diff, not both")

    payload = diff if diff is not None else content
    if not isinstance(payload, str):
        return _err("content and diff must be strings")

    size = len(payload.encode("utf-8", "replace"))
    if size > SECRET_SCAN_TEXT_MAX_BYTES:
        # Rejected, never truncated — see the module comment above.
        return _err(
            f"payload is {size} bytes, over the {SECRET_SCAN_TEXT_MAX_BYTES} byte limit. "
            "Split the scan into smaller batches.",
            413,
        )

    findings = _scan_unified_diff(payload) if diff is not None else _scan_text_for_secrets(payload, filename)

    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    findings.sort(key=lambda f: (-severity_order.get(f["severity"], 0), f.get("line", 0)))

    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    highest = findings[0]["severity"] if findings else None

    # Pattern names and counts only. The scanned content never reaches the log.
    logger.info(
        "secret-scan-text mode=%s bytes=%d findings=%d highest=%s types=%s",
        "diff" if diff is not None else "content", size, len(findings), highest,
        sorted({f["type"] for f in findings}),
    )

    return _ok({
        "found":            bool(findings),
        "bytes_scanned":    size,
        "findings":         findings,
        "findings_count":   len(findings),
        "severity_counts":  counts,
        "highest_severity": highest,
        "recommendation": (
            "CRITICAL secrets detected. Do not commit. Rotate any credential that has "
            "already left this machine, then remove it from the working tree."
            if counts.get("CRITICAL") else
            "Secrets detected. Review each finding and move the value to a secrets manager "
            "or environment variable before committing."
            if findings else
            "No secrets detected."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# Request: POST /v1/intel/telegram
#   { "email": "...", "phone": "...", "domain": "...", "wallet": "..." }
#   At least one field required. Each queried independently; results merged.
#
# Response:
#   { ok: true, matched: bool, hit_count: int, ioc_types: [...],
#     earliest_seen: ISO, latest_seen: ISO,
#     hits: [{ ioc_value, ioc_type, channel, category, seen_ts }] }
# ---------------------------------------------------------------------------

def handle_intel_telegram(params: dict, api_key_record: dict | None = None) -> dict:
    # Verify caller has intel_access — TI API subscribers get this flag provisioned
    if not api_key_record or not api_key_record.get("intel_access"):
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Threat Intelligence API access required. Upgrade at api.relayshield.net/developers.",
            }),
        }

    # Monthly call cap — $499/mo tier capped at 10K, $999/mo unlimited.
    # Fails safe to the capped tier if intel_plan_tier was never set.
    quota_error = _check_and_increment_intel_quota(api_key_record["api_key"], api_key_record)
    if quota_error:
        return quota_error

    # Collect IOC values to query
    targets: list[tuple[str, str]] = []
    if params.get("email"):
        targets.append((params["email"].strip().lower(), "email"))
    if params.get("phone"):
        phone = re.sub(r"[^\d+]", "", params["phone"].strip())
        if phone:
            targets.append((phone, "phone"))
    if params.get("domain"):
        targets.append((params["domain"].strip().lower(), "domain"))
    if params.get("wallet"):
        targets.append((params["wallet"].strip().lower(), "wallet"))

    if not targets:
        return _err("at least one of email, phone, domain, or wallet is required")

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    all_hits: list[dict] = []

    for ioc_value, _ in targets:
        try:
            resp = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(ioc_value),
                ScanIndexForward=False,  # newest first
                Limit=50,
            )
            all_hits.extend(resp.get("Items", []))
        except Exception as exc:
            logger.error("intel_iocs query failed ioc=%s: %s", ioc_value[:20], exc)

    if not all_hits:
        return _ok({
            "matched":       False,
            "record_type":   "ioc_indicator",
            "hit_count":     0,
            "ioc_types":     [],
            "earliest_seen": None,
            "latest_seen":   None,
            "hits":          [],
        })

    timestamps   = [h.get("seen_ts", "") for h in all_hits if h.get("seen_ts")]
    ioc_types    = sorted({h.get("ioc_type", "") for h in all_hits})
    safe_hits    = []
    enrich_count = 0
    for h in all_hits:
        malware  = h.get("malware", "") or ""
        source   = h.get("channel", "") or ""
        seen_ts  = h.get("seen_ts", "") or ""
        ioc_val  = h.get("ioc_value", "") or ""
        ioc_type = h.get("ioc_type", "") or ""
        hit = {
            "ioc_value":        ioc_val,
            "ioc_type":         ioc_type,
            "channel":          source,
            "category":         h.get("category"),
            "seen_ts":          seen_ts,
            "confidence_score": _ioc_confidence(source, seen_ts),
        }
        if malware and malware not in ("None", "n/a", ""):
            hit["malware_family"] = malware
            family_key = malware.lower().split(",")[0].strip()
            actor = THREAT_ACTOR_MAP.get(family_key)
            if actor:
                hit["threat_actor"] = actor
            sigma = SIGMA_RULE_MAP.get(family_key)
            if sigma:
                hit["sigma_rules"] = sigma
            graph = _build_threat_graph(malware)
            if graph:
                hit["threat_graph"]      = graph
                hit["country_of_origin"] = graph.get("country_origin", "Unknown")
        if h.get("pre_ransomware"):
            hit["pre_ransomware"]   = True
            hit["ransomware_group"] = h.get("ransomware_group", "")
        # Context enrichment — limit to first 15 hits to respect ip-api.com rate limit
        if enrich_count < 15:
            if ioc_type == "ip":
                ctx = _enrich_ip(ioc_val)
                if ctx:
                    hit["context"] = ctx
                    enrich_count += 1
            elif ioc_type == "domain" and enrich_count < 5:
                ctx = _enrich_domain(ioc_val)
                if ctx:
                    hit["context"] = ctx
                    enrich_count += 1
        safe_hits.append(hit)

    logger.info("intel_telegram queried=%d hits=%d", len(targets), len(all_hits))
    return _ok({
        "record_type":   "ioc_indicator",
        "matched":       True,
        "hit_count":     len(all_hits),
        "ioc_types":     ioc_types,
        "earliest_seen": min(timestamps) if timestamps else None,
        "latest_seen":   max(timestamps) if timestamps else None,
        "hits":          safe_hits,
    })


# ---------------------------------------------------------------------------
# x402 Bazaar discovery extensions — per-endpoint metadata for Agentic.Market
# ---------------------------------------------------------------------------
# Format follows the x402 BodyDiscoveryExtension schema (POST endpoints).
# These are injected into the `extensions` field of each payment-requirements
# `accepts` entry so the CDP Facilitator can catalog them on settlement.

def _bazaar_body_ext(input_example: dict, input_schema: dict, output_example: dict) -> dict:
    """Discovery metadata for a POST endpoint, stored once and rendered into
    whichever wire shape a given path currently uses (see
    _v1_output_schema / _v2_bazaar_extension below).

    V1 (Corrected 2026-07-12 to match Coinbase's own V1 reference extraction,
    x402/extensions/bazaar/v1/facilitator.py, extract_discovery_info_v1):
    metadata lives in a top-level `outputSchema` field shaped exactly as
    `{"input": {...}, "output": <example>}`.

    V2 (added 2026-07-14, verified against the actual SDK source —
    python/x402/extensions/bazaar/types.py): metadata lives in a top-level
    `extensions.bazaar` field shaped as `{"info": {"input", "output"},
    "schema": {...}}` — this is where `input_schema` (unused by V1) is
    actually needed, kept under `_input_schema` so it doesn't leak into the
    V1 wire shape, which must stay exactly `{input, output}`.
    """
    return {
        "input": {
            "type":         "http",
            "method":       "POST",
            "discoverable": True,
            "bodyType":     "json",
            "body":         input_example,
        },
        "output":         output_example,
        "_input_schema":  input_schema,
    }


def _v1_output_schema(bazaar_ext: dict) -> dict:
    """Strips the V2-only _input_schema field so V1's outputSchema stays
    exactly {input, output} on the wire."""
    return {"input": bazaar_ext["input"], "output": bazaar_ext["output"]}


def _v2_bazaar_extension(bazaar_ext: dict) -> dict:
    """Builds the V2 extensions.bazaar shape from the same stored data used
    for V1's outputSchema.

    Fixed 2026-07-16 — confirmed against the actual SDK validator
    (x402/extensions/bazaar/facilitator.py, validate_discovery_extension):
    it runs jsonschema.validate(instance=info, schema=schema), so `schema`
    must describe the shape of the whole `info` object ({input, output}),
    not the shape of the request body directly. The previous version put
    `_input_schema` (which describes the BODY, e.g. {"domain": "acme.com"})
    straight under schema.properties.input — that validates info.input
    ITSELF (the {type, method, bodyType, body} wrapper) against the body's
    schema, which always fails since the wrapper has no top-level `domain`
    key. Root-caused via a real CDP facilitator rejection reported on
    GitHub (x402-foundation/x402#2814): "(root).input: domain is required".
    `_input_schema` now nests under schema.properties.input.properties.body,
    matching where the body actually lives in `info.input.body`.
    """
    return {
        "info": {
            "input":  bazaar_ext["input"],
            "output": {"type": "json", "example": bazaar_ext["output"]},
        },
        "schema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "body": bazaar_ext.get("_input_schema") or {"type": "object"},
                    },
                    "required": ["body"],
                },
                "output": {"type": "object"},
            },
            "required": ["input"],
        },
    }


BAZAAR_EXTENSIONS: dict[str, dict] = {
    "/v1/payg/breach": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email": "user@example.com",
                "breach_count": 3,
                "breaches": [
                    {"name": "ExampleBreach", "domain": "example.com",
                     "breach_date": "2023-06-01",
                     "data_classes": ["Passwords", "Email addresses"],
                     "is_verified": True},
                ],
            },
        },
    ),
    "/v1/payg/sim-swap": _bazaar_body_ext(
        input_example={"phone": "+14155551234"},
        input_schema={
            "type": "object",
            "properties": {"phone": {"type": "string", "description": "Phone number in E.164 format"}},
            "required": ["phone"],
        },
        output_example={
            "ok": True,
            "data": {
                "phone": "+14155551234",
                "swapped": True,
                "swap_timestamp": "2026-05-18T14:23:00Z",
                "carrier": "T-Mobile",
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/domain": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Root domain to scan for lookalikes"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {
                "domain": "acme.com",
                "lookalikes_found": 2,
                "lookalikes": [
                    {"domain": "acrne.com"},
                    {"domain": "acme-login.com"},
                ],
                "candidates_checked": 30,
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/oauth-watchlist": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for OAuth exposure"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email": "user@example.com",
                "matched_count": 1,
                "matched_apps": [
                    {"app": "GitHub", "breach_date": "2023-01-15",
                     "data_classes": ["Usernames", "Email addresses"],
                     "revoke_url": "https://github.com/settings/applications"},
                ],
                "recommendation": "Revoke OAuth access for matched apps immediately.",
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/scan-wallet": _bazaar_body_ext(
        input_example={"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "address":  {"type": "string", "description": "EVM wallet address (0x + 40 hex chars)"},
                "chain_id": {"type": "string", "description": "EVM chain ID: 1=ETH, 8453=Base, 137=Polygon"},
            },
            "required": ["address"],
        },
        output_example={
            "ok": True,
            "data": {
                "address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                "chain_id": "1",
                "risk_level": "LOW",
                "risk_flags": [],
                "raw": {},
            },
        },
    ),
    "/v1/payg/scan-url": _bazaar_body_ext(
        input_example={"url": "https://suspicious-site.example.com"},
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to scan (must start with http:// or https://)"}},
            "required": ["url"],
        },
        output_example={
            "ok": True,
            "data": {
                "status":        "pending",
                "target":        "https://suspicious-site.example.com",
                "analysis_id":   "u-abc123def456",
                "poll_endpoint": "/v1/result/u-abc123def456",
                "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
            },
        },
    ),
    "/v1/payg/scan-file": _bazaar_body_ext(
        input_example={"file_url": "https://cdn.example.com/invoice.pdf", "filename": "invoice.pdf"},
        input_schema={
            "type": "object",
            "properties": {
                "file_url": {"type": "string", "description": "Publicly accessible download URL"},
                "filename": {"type": "string", "description": "Optional filename hint for AV engines"},
            },
            "required": ["file_url"],
        },
        output_example={
            "ok": True,
            "data": {
                "status":        "pending",
                "target":        "https://cdn.example.com/invoice.pdf",
                "filename":      "invoice.pdf",
                "analysis_id":   "f-abc123def456",
                "poll_endpoint": "/v1/result/f-abc123def456",
                "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
            },
        },
    ),
    "/v1/payg/wallet-risk": _bazaar_body_ext(
        input_example={"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"},
        input_schema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address — EVM (0x), Solana (base58), TON (EQ.../UQ...), or Bitcoin",
                },
            },
            "required": ["address"],
        },
        output_example={
            "ok": True,
            "data": {
                "address":    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                "chain":      "evm",
                "risk_level": "LOW",
                "risk_flags": [],
                "metadata":   {},
            },
        },
    ),
    "/v1/payg/token-security": _bazaar_body_ext(
        input_example={"contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "contract_address": {"type": "string", "description": "EVM token contract address"},
                "chain_id":         {"type": "string", "description": "EVM chain ID (default: 1 for Ethereum)"},
            },
            "required": ["contract_address"],
        },
        output_example={
            "ok": True,
            "data": {
                "contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "chain_id":         "1",
                "risk_level":       "HIGH",
                "critical_flags":   ["honeypot"],
                "warning_flags":    ["mintable supply"],
                "token_name":       "Example Token",
                "token_symbol":     "EXT",
                "holder_count":     "12345",
                "raw":              {},
            },
        },
    ),
    "/v1/payg/nft-security": _bazaar_body_ext(
        input_example={"contract_address": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "contract_address": {"type": "string", "description": "NFT contract address"},
                "chain_id":         {"type": "string", "description": "EVM chain ID (default: 1 for Ethereum)"},
            },
            "required": ["contract_address"],
        },
        output_example={
            "ok": True,
            "data": {
                "contract_address": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d",
                "chain_id":         "1",
                "risk_level":       "LOW",
                "risk_flags":       [],
                "nft_name":         "Bored Ape Yacht Club",
                "nft_symbol":       "BAYC",
                "raw":              {},
            },
        },
    ),
    "/v1/payg/wallet-screen-batch": _bazaar_body_ext(
        input_example={"addresses": ["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"]},
        input_schema={
            "type": "object",
            "properties": {
                "addresses": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "maxItems":    10,
                    "description": "Up to 10 wallet addresses (any chain: EVM, Solana, TON, Bitcoin)",
                },
            },
            "required": ["addresses"],
        },
        output_example={
            "ok": True,
            "data": {
                "screened":  2,
                "high_risk": 0,
                "results": [
                    {"address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                     "chain": "evm", "risk_level": "LOW", "risk_flags": [], "error": None},
                    {"address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
                     "chain": "solana", "risk_level": "LOW", "risk_flags": [], "error": None},
                ],
            },
        },
    ),
    "/v1/payg/infostealer": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for infostealer compromise"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email":         "user@example.com",
                "found":         False,
                "stealer_count": 0,
                "stealers":      [],
            },
        },
    ),
    "/v1/payg/supply-chain": _bazaar_body_ext(
        input_example={"vendor_domains": ["acme.com", "vendor2.com"]},
        input_schema={
            "type": "object",
            "properties": {
                "vendor_domains": {"type": "array", "items": {"type": "string"}, "description": "Up to 10 vendor domains"},
                "vendor_emails":  {"type": "array", "items": {"type": "string"}, "description": "Alternative: vendor contact emails, domain extracted automatically"},
            },
        },
        output_example={
            "ok": True,
            "data": {
                "domains_checked": 1,
                "highest_risk":    "LOW",
                "results":         [{"domain": "acme.com", "risk_level": "LOW", "breach_count": 0, "infostealer_found": False}],
            },
        },
    ),
    "/v1/payg/session-risk": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for active session/AiTM exposure"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {"email": "user@example.com", "found": False, "session_count": 0, "highest_severity": None, "sessions": []},
        },
    ),
    "/v1/payg/identity-graph": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to correlate against the criminal dump corpus"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {"email": "user@example.com", "found": False, "correlated_identifiers": 0, "correlated_phones": [], "correlated_domains": [], "sources": []},
        },
    ),
    "/v1/payg/ransomware-risk": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Domain to check against the ransomware victim list"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {"domain": "acme.com", "on_victim_list": False, "pre_ransomware_credential_count": 0},
        },
    ),
    "/v1/payg/nhi-exposure": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {
                "domain":         {"type": "string", "description": "Your own domain"},
                "vendor_domains": {"type": "array", "items": {"type": "string"}, "description": "Optional: vendor/supply-chain domains, up to 10"},
            },
        },
        output_example={
            "ok": True,
            "data": {"domains_checked": 1, "found": False, "findings": [], "highest_severity": None},
        },
    ),
    "/v1/payg/llm-credential-exposure": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {
                "domain":         {"type": "string", "description": "Your own domain"},
                "vendor_domains": {"type": "array", "items": {"type": "string"}, "description": "Optional: vendor/supply-chain domains, up to 10"},
            },
        },
        output_example={
            "ok": True,
            "data": {"domains_checked": 1, "found": False, "findings": [], "highest_severity": None, "providers_affected": []},
        },
    ),
    "/v1/payg/secret-scan": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {
                "domain":         {"type": "string", "description": "Your own domain"},
                "vendor_domains": {"type": "array", "items": {"type": "string"}, "description": "Optional: vendor domains, up to 5"},
            },
        },
        output_example={
            "ok": True,
            "data": {"domains_checked": 1, "found": False, "findings": [], "highest_severity": None},
        },
    ),
    "/v1/payg/target-risk": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Domain to score (e.g. acme.com)"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {"domain": "acme.com", "target_risk_score": 0, "probability_tier": "LOW", "signals": []},
        },
    ),
    "/v1/payg/tech-stack-cve": _bazaar_body_ext(
        input_example={"tech_stack": ["nginx", "wordpress", "cisco ios"]},
        input_schema={
            "type": "object",
            "properties": {
                "tech_stack": {"type": "array", "items": {"type": "string"}, "description": "Declared technology product names"},
                "domain":     {"type": "string", "description": "Alternative: pull tech_stack from a stored user profile by domain"},
            },
        },
        output_example={
            "ok": True,
            "data": {"tech_stack_queried": ["nginx"], "matched_cves": [], "critical_count": 0},
        },
    ),
    "/v1/payg/bulk-identity-risk": _bazaar_body_ext(
        input_example={"targets": [{"domain": "acme.com", "agents": ["ceo@acme.com"]}]},
        input_schema={
            "type": "object",
            "properties": {
                "targets": {
                    "type": "array",
                    "description": "Up to 10 domains, each with up to 5 agent emails",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string"},
                            "agents": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["domain"],
                    },
                },
            },
            "required": ["targets"],
        },
        output_example={
            "ok": True,
            "data": {"queried": 1, "critical_count": 0, "high_count": 0, "results": [{"domain": "acme.com", "domain_score": 10, "domain_grade": "A", "agent_count": 1}]},
        },
    ),
    "/v1/payg/identity-risk-score": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Root domain to score"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {
                "domain": "acme.com",
                "risk_score": 10,
                "risk_level": "LOW",
                "grade": "A",
                "dimension_scores": {
                    "breach_exposure": 5, "infostealer_density": 0, "threat_actor_targeting": 0,
                    "ransomware_exposure": 0, "session_exposure": 0, "cve_exposure": 5,
                },
                "max_score": 100,
                "risk_factors": ["Breach exposure: 1 known breach event(s), 50,000 accounts affected"],
                "summary": "Domain acme.com scores 10/100 (A — LOW) across 2 of 6 monitored identity signal dimensions.",
            },
        },
    ),
    "/v1/payg/cert-expiry": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Domain to check TLS certificate expiry for"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {
                "domain":            "acme.com",
                "cert_found":        True,
                "expires_at":        "2026-09-05T00:00:00+00:00",
                "days_remaining":    46,
                "risk_level":        "MEDIUM",
                "issued_at":         "2026-06-07T00:00:00+00:00",
                "recommendation":    "Certificate renews in 46 days — no action needed yet, but confirm your renewal automation is configured.",
            },
        },
    ),
    "/v1/payg/ip-intel": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to look up (returns reputation + passive DNS resolution history)"},
                "ip":     {"type": "string", "description": "Alternative: IP address to look up (returns reputation + reverse passive DNS)"},
            },
        },
        output_example={
            "ok": True,
            "data": {
                "queried":        "acme.com",
                "query_type":     "domain",
                "reputation":     0,
                "malicious_votes": 0,
                "suspicious_votes": 0,
                "resolutions": [
                    {"ip_address": "93.184.216.34", "date": "2026-06-01T00:00:00+00:00"},
                ],
            },
        },
    ),
}

# Rich, natural-language descriptions for CDP Bazaar semantic search — added
# 2026-07-17. Previously every endpoint used a single generic auto-generated
# one-liner ("RelayShield {path} check", ~25 chars) regardless of path; CDP's
# own discovery docs confirm ranking is driven by description quality against
# a 500-char budget, so a bare endpoint-name string was actively hurting
# discoverability. Each description explains what the check does and when an
# agent should call it. wallet-risk/token-security/nft-security/scan-wallet/
# wallet-screen-batch are deliberately framed in DeFi/trading-agent language
# (screen a counterparty before transacting) rather than generic "security
# check" language — that's the one demand category the market research
# (task tracked in TODO.md) found real evidence of agents actually paying for.
PAYG_DESCRIPTIONS: dict[str, str] = {
    "/v1/payg/breach": (
        "Check whether an email address appears in known data breaches. Returns breach count, "
        "source names, dates, and exposed data types (passwords, emails, etc). Call before "
        "trusting a new user identity or granting elevated access."
    ),
    "/v1/payg/sim-swap": (
        "Check whether a phone number has had a SIM swap or carrier port in the last 24 hours "
        "via real-time carrier lookup. A recent swap is a strong signal of an active "
        "account-takeover attempt targeting SMS-based 2FA. Call before trusting an SMS OTP "
        "from this number."
    ),
    "/v1/payg/domain": (
        "Scan a domain for phishing lookalikes — typosquats, homoglyphs, and common phishing "
        "registration patterns. Returns matched lookalike domains found in the wild. Call to "
        "detect brand-impersonation phishing campaigns targeting a company before they're "
        "reported elsewhere."
    ),
    "/v1/payg/oauth-watchlist": (
        "Check whether an email address has OAuth-connected app credentials exposed in a known "
        "SaaS breach (GitHub, Slack, Notion, Zapier, and 30+ other high-risk OAuth-capable "
        "apps). Returns matched apps and direct revoke-access links. Call to detect "
        "supply-chain credential exposure via connected apps."
    ),
    "/v1/payg/scan-wallet": (
        "Screen an EVM wallet address for known scam, exploit, or sanctions-list association "
        "before your agent transacts with it. Returns a risk level and specific risk flags. "
        "Call before an autonomous agent sends funds to or interacts with an unfamiliar wallet."
    ),
    "/v1/payg/scan-url": (
        "Scan a URL for phishing or malware using heuristic signals (Google Safe Browsing, "
        "RDAP domain age, known IOC corpus) plus VirusTotal multi-engine analysis. Returns an "
        "async analysis ID to poll. Call before an agent clicks, fetches, or shares a link from "
        "an untrusted source."
    ),
    "/v1/payg/scan-file": (
        "Scan a file (via its public download URL) for malware using VirusTotal's multi-engine "
        "analysis. Returns an async analysis ID to poll. Call before an agent downloads, opens, "
        "or executes a file attachment from an untrusted source."
    ),
    "/v1/payg/wallet-risk": (
        "Screen a wallet address across EVM, Solana, TON, or Bitcoin for known scam, exploit, "
        "drainer, or sanctions-list association before your agent transacts with it. Returns a "
        "risk level and specific risk flags. The recommended first call for any autonomous "
        "trading or DeFi agent before interacting with a new counterparty wallet."
    ),
    "/v1/payg/token-security": (
        "Screen an ERC-20/BEP-20 token contract for honeypot, mintable-supply, hidden-owner, "
        "and other rug-pull risk signals before your agent trades it. Returns risk level, "
        "specific critical/warning flags, and basic token metadata. Call before an autonomous "
        "trading agent buys or approves spending on an unfamiliar token."
    ),
    "/v1/payg/nft-security": (
        "Screen an NFT contract for known scam, wash-trading, or malicious-approval risk "
        "signals before your agent buys, bids on, or approves it. Returns risk level and risk "
        "flags plus basic collection metadata. Call before an autonomous agent interacts with "
        "an unfamiliar NFT contract."
    ),
    "/v1/payg/wallet-screen-batch": (
        "Screen up to 10 wallet addresses (any chain: EVM, Solana, TON, Bitcoin) for known "
        "scam or exploit association in a single call. Returns per-address risk level and "
        "flags. Use for bulk counterparty screening in trading or portfolio-monitoring agent "
        "workflows."
    ),
    "/v1/payg/infostealer": (
        "Check whether an email address's credentials were harvested by infostealer malware "
        "and appear in a criminal stealer-log marketplace — detected 24-72 hours ahead of "
        "public breach databases. Call to catch device-level compromise before stolen session "
        "cookies or saved passwords are used for account takeover."
    ),
    "/v1/payg/supply-chain": (
        "Check up to 10 vendor domains for combined breach, infostealer, and dark-web risk "
        "exposure in one call. Returns a composite risk score per vendor. Call to assess "
        "third-party API/vendor risk before an agent integrates with or continues calling an "
        "external service."
    ),
    "/v1/payg/session-risk": (
        "Check whether an email address has an active stolen session cookie circulating in a "
        "criminal archive — a signal of account takeover that bypasses password resets and 2FA "
        "entirely. Call to detect AiTM/session-hijack attacks before an authenticated agent "
        "session is trusted."
    ),
    "/v1/payg/identity-graph": (
        "Correlate an email address against the criminal breach/stealer corpus to surface "
        "linked phone numbers, secondary domains, and other identifiers tied to the same "
        "compromised identity. Call to map the blast radius of a known compromise across an "
        "organization."
    ),
    "/v1/payg/ransomware-risk": (
        "Check whether a domain appears on a known ransomware group's victim/leak-site list, "
        "and whether pre-ransomware credential harvesting was detected beforehand. Call to "
        "assess active ransomware exposure for a domain, not just historical breach history."
    ),
    "/v1/payg/nhi-exposure": (
        "Check whether API keys or tokens tied to a domain — used by non-human identities like "
        "AI agents, service accounts, or CI/CD — appear exposed in criminal stealer logs. Call "
        "to audit whether the credentials an autonomous agent relies on have already been "
        "compromised upstream."
    ),
    "/v1/payg/llm-credential-exposure": (
        "Check whether a domain's LLM/AI provider API keys (OpenAI, Anthropic, Google, Groq, "
        "xAI, Replicate) appear exposed in criminal stealer logs — LLMjacking, a fast-growing "
        "threat where a leaked key becomes a live, uncapped billing liability rather than just "
        "a data exposure. Call to catch an exposed key before the drain, not after the invoice."
    ),
    "/v1/payg/secret-scan": (
        "Scan public GitHub repositories, npm and PyPI packages, Docker Hub images, "
        "Hugging Face models and Spaces, and Postman public workspaces and collections "
        "for API keys, tokens and credentials already published against a domain. "
        "Repo-only scanners miss credentials shipped inside "
        "released packages and images. Every hit is verified against the credential "
        "pattern before it is reported."
    ),
    "/v1/payg/target-risk": (
        "Score a domain's probability of being an active or upcoming cyberattack target using "
        "a 6-signal correlation model (breach, infostealer, ransomware, session, CVE, and "
        "threat-actor targeting history). Call for proactive risk triage, not just "
        "after-the-fact breach checking."
    ),
    "/v1/payg/tech-stack-cve": (
        "Check a declared technology stack (e.g. nginx, WordPress, Cisco IOS) against "
        "actively-exploited CVEs (CISA KEV) and high-EPSS-score vulnerabilities. Call before "
        "deploying or continuing to run a given technology stack in production."
    ),
    "/v1/payg/bulk-identity-risk": (
        "Score up to 10 organizational domains, each with up to 5 associated agent/employee "
        "emails, for combined breach/infostealer/session/CVE risk in one call. Built for "
        "enterprise AI-governance platforms scoring many identities per customer in one pass — "
        "the recommended entry point for agent-governance and identity-posture integrations."
    ),
    "/v1/payg/identity-risk-score": (
        "Return a 0-100 domain security score across 6 identity-risk dimensions (breach "
        "exposure, infostealer density, ransomware exposure, session exposure, CVE exposure, "
        "threat-actor targeting) with a letter grade and plain-English risk factors. Call as a "
        "single-number identity health check before onboarding, financing, or partnering with "
        "a domain."
    ),
    "/v1/payg/cert-expiry": (
        "Check how many days remain before a domain's TLS certificate expires, via Certificate "
        "Transparency logs. Call to catch a lapsing certificate before it causes an outage — "
        "especially relevant as CA/Browser Forum rules shrink standard certificate lifespans "
        "toward 47 days by 2029."
    ),
    "/v1/payg/ip-intel": (
        "Look up passive DNS resolution history and reputation for a domain or IP address. "
        "For a domain: which IPs it has resolved to over time. For an IP: which hostnames have "
        "resolved to it, plus malicious/suspicious vendor detection counts. Call to pivot from "
        "an indicator to its infrastructure history during an investigation."
    ),
}

# SDK discovery tags (CDPX-4a) — up to 5 per endpoint per the bazaar spec,
# only takes effect on V2-enabled paths (X402_V2_ENABLED_PATHS). Chosen per
# endpoint's actual subject matter, not blanket-applied — wallet-screen-batch
# is the one Batch B endpoint that's genuinely DeFi/wallet-screening; the
# other three get tags matching what they actually check.
PAYG_TAGS: dict[str, list[str]] = {
    "/v1/payg/wallet-screen-batch": ["defi", "wallet-screening", "crypto-security"],
    "/v1/payg/target-risk":         ["identity-risk", "threat-intelligence", "risk-scoring"],
    "/v1/payg/oauth-watchlist":     ["oauth-security", "saas-security", "supply-chain"],
    "/v1/payg/tech-stack-cve":      ["cve", "vulnerability-management", "agent-security"],
    "/v1/payg/cert-expiry":         ["certificate-management", "domain-security", "ops-hygiene"],
    "/v1/payg/ip-intel":            ["passive-dns", "ip-reputation", "threat-intelligence"],
    # Added 2026-07-21 — the CDPX-4 "reweight toward wallet/token/NFT" endpoints
    # had crypto-forward descriptions live but no tags, so they weren't
    # surfacing in category-based Bazaar discovery.
    "/v1/payg/wallet-risk":         ["defi", "wallet-screening", "crypto-security"],
    "/v1/payg/token-security":      ["defi", "token-security", "crypto-security"],
    "/v1/payg/nft-security":        ["defi", "nft-security", "crypto-security"],
    "/v1/payg/scan-wallet":         ["defi", "wallet-screening", "crypto-security"],
    "/v1/payg/scan-url":            ["url-scanning", "malware-detection", "crypto-security"],
    "/v1/payg/scan-file":           ["file-scanning", "malware-detection", "crypto-security"],
}


# ---------------------------------------------------------------------------
# x402 PAYG — payment requirements, verification, 402 response
# ---------------------------------------------------------------------------

def _build_payment_requirements(path: str, price_units: int) -> dict:
    api_base    = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
    resource    = f"{api_base}{path}"
    description = PAYG_DESCRIPTIONS.get(
        path, f"RelayShield {path.split('/')[-1].replace('-', ' ')} check"
    )
    bazaar_ext  = BAZAAR_EXTENSIONS.get(path)

    if path in X402_V2_ENABLED_PATHS:
        # V2 shape — verified 2026-07-13 against actual SDK source
        # (python/x402/schemas/{base,payments}.py): "amount" replaces
        # "maxAmountRequired", and resource/extensions live once at the top
        # level of the whole response instead of being duplicated on every
        # accept entry the way V1's resource/description/mimeType/outputSchema
        # are today.
        base_entry: dict = {
            "scheme":            "exact",
            "network":           BASE_CHAIN_ID_V2,
            "amount":            str(price_units),
            "payTo":             X402_PAYTO_ADDRESS,
            "maxTimeoutSeconds": 300,
            "asset":             USDC_BASE_ADDRESS,
            "extra":             {"name": "USD Coin", "version": "2"},
        }
        accepts = [base_entry]
        if SOL_PAYTO_ADDRESS:
            accepts.append({
                "scheme":            "exact",
                "network":           SOL_CHAIN_ID,
                "amount":            str(price_units),
                "payTo":             SOL_PAYTO_ADDRESS,
                "maxTimeoutSeconds": 60,
                "asset":             USDC_SOL_ADDRESS,
                "extra":             {"feePayer": SOL_FEE_PAYER},
            })
        resource_info: dict = {
            "url":         resource,
            "description": description,
            "mimeType":    "application/json",
        }
        tags = PAYG_TAGS.get(path)
        if tags:
            resource_info["tags"] = tags
        result: dict = {
            "x402Version": 2,
            "resource": resource_info,
            "accepts": accepts,
        }
        if bazaar_ext:
            result["extensions"] = {"bazaar": _v2_bazaar_extension(bazaar_ext)}
        return result

    # V1 shape (default — unchanged)
    base_entry: dict = {
        "scheme":            "exact",
        "network":           BASE_CHAIN_ID,
        "maxAmountRequired": str(price_units),
        "resource":          resource,
        "description":       description,
        "mimeType":          "application/json",
        "payTo":             X402_PAYTO_ADDRESS,
        "maxTimeoutSeconds": 300,
        "asset":             USDC_BASE_ADDRESS,
        "extra":             {"name": "USD Coin", "version": "2"},
    }
    if bazaar_ext:
        base_entry["outputSchema"] = _v1_output_schema(bazaar_ext)

    accepts = [base_entry]

    # Solana (SVM) entry — added when RELAYSHIELD_SOL_WALLET is configured.
    # CDP Facilitator sponsors gas; client signs a partial SPL TransferChecked
    # transaction and sends it base64-encoded in X-PAYMENT.
    if SOL_PAYTO_ADDRESS:
        sol_entry: dict = {
            "scheme":            "exact",
            "network":           SOL_CHAIN_ID,
            "maxAmountRequired": str(price_units),
            "resource":          resource,
            "description":       description,
            "mimeType":          "application/json",
            "payTo":             SOL_PAYTO_ADDRESS,
            "maxTimeoutSeconds": 60,          # Solana blockhash TTL ~60–90s
            "asset":             USDC_SOL_ADDRESS,
            "extra": {
                "feePayer": SOL_FEE_PAYER,    # CDP Facilitator sponsors transaction gas
            },
        }
        if bazaar_ext:
            sol_entry["outputSchema"] = _v1_output_schema(bazaar_ext)
        accepts.append(sol_entry)

    return {
        "x402Version": 1,
        "accepts":     accepts,
    }


def _x402_payment_required(path: str) -> dict:
    price_units  = PAYG_PRICE_UNITS.get(path, 250000)
    requirements = _build_payment_requirements(path, price_units)
    encoded      = base64.b64encode(json.dumps(requirements).encode()).decode()
    price_usd    = f"${price_units / 1_000_000:.2f}"
    chains       = "Base or Solana" if SOL_PAYTO_ADDRESS else "Base"
    return {
        "statusCode": 402,
        "headers": {
            "Content-Type":                  "application/json",
            "PAYMENT-REQUIRED":              encoded,
            "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
        },
        "body": json.dumps({
            "ok":             False,
            "error":          "Payment required",
            "price":          f"{price_usd} USDC ({chains})",
            "x402":           requirements,
            "subscribe_url":  "https://rapidapi.com/relayshield/relayshield-security-intelligence",
            "subscribe_note": f"Subscribe for 96%+ lower per-check cost vs {price_usd} PAYG rate.",
        }),
    }


def _payload_network(parsed: dict) -> str:
    """V1 payloads carry `network` at the top level. V2 payloads (verified
    2026-07-14 against python/x402/schemas/payments.py's PaymentPayload)
    nest it under `accepted.network` instead — top-level `network` doesn't
    exist on a V2 payload at all."""
    if parsed.get("network"):
        return parsed["network"]
    return (parsed.get("accepted") or {}).get("network", "")


def _detect_payment_chain(x_payment: str) -> str:
    """Detect chain by parsing the network field from the x402 payment payload.
    Both EVM and Solana payloads are base64-encoded JSON — check network field.
    Returns 'solana' or 'evm'.
    """
    try:
        decoded = base64.b64decode(x_payment + "==")
        parsed = json.loads(decoded)
        if _payload_network(parsed).startswith("solana"):
            return "solana"
        return "evm"
    except Exception:
        # Try raw JSON (non-base64)
        try:
            parsed = json.loads(x_payment)
            if _payload_network(parsed).startswith("solana"):
                return "solana"
        except Exception:
            pass
        return "evm"  # default to EVM on decode failure


def _parse_cdp_private_key(key_data: str):
    """Parses a CDP API key secret in either PEM (EC/ES256) or base64
    (Ed25519/EdDSA) format. Mirrors coinbase/cdp-sdk's Python
    _parse_private_key exactly — CDP's key-creation UI defaults to Ed25519
    but still offers ECDSA, so both formats must be supported."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    if "\\n" in key_data:
        key_data = key_data.replace("\\n", "\n")

    try:
        key = serialization.load_pem_private_key(key_data.encode(), password=None)
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key, "ES256"
    except Exception:
        pass

    try:
        decoded = base64.b64decode(key_data)
        if len(decoded) == 64:
            return ed25519.Ed25519PrivateKey.from_private_bytes(decoded[:32]), "EdDSA"
    except Exception:
        pass

    raise ValueError("CDP_API_KEY_SECRET must be either a PEM EC key or a base64 Ed25519 key")


def _cdp_jwt_bearer_token(request_path: str) -> str | None:
    """Builds a short-lived JWT for CDP's REST API auth (ES256 or EdDSA,
    auto-detected from CDP_API_KEY_SECRET's format). Mirrors Coinbase's own
    cdp-sdk (python/cdp/auth/utils/jwt.py generate_jwt) exactly: header
    {alg, kid, typ, nonce}, claims {sub, iss=cdp, nbf, exp, uris}. Not using
    the cdp-sdk package itself to keep this Lambda's dependency footprint to
    just pyjwt + cryptography (bundled via the relayshield-cdp-auth layer).
    Returns None (triggering PayAI fallback) if creds are missing or invalid."""
    if not CDP_API_KEY_ID or not CDP_API_KEY_SECRET:
        return None
    try:
        import jwt as pyjwt

        private_key, algorithm = _parse_cdp_private_key(CDP_API_KEY_SECRET)
        now = int(time.time())
        header = {
            "alg":   algorithm,
            "kid":   CDP_API_KEY_ID,
            "typ":   "JWT",
            "nonce": "".join(random.choices("0123456789", k=16)),
        }
        claims = {
            "sub": CDP_API_KEY_ID,
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,
            "uris": [f"POST {CDP_FACILITATOR_HOST}{request_path}"],
        }
        return pyjwt.encode(claims, private_key, algorithm=algorithm, headers=header)
    except Exception as exc:
        logger.error("CDP JWT generation failed, falling back to PayAI — error=%s", exc)
        return None


def _select_facilitator(verify_path: str, settle_path: str, fallback_url: str) -> tuple[str, dict, dict]:
    """Returns (facilitator_base_url, verify_headers, settle_headers). Prefers
    CDP when CDP_API_KEY_ID/CDP_API_KEY_SECRET are configured (see note above
    _cdp_jwt_bearer_token); falls back to the PayAI facilitator otherwise."""
    if CDP_API_KEY_ID and CDP_API_KEY_SECRET:
        verify_jwt = _cdp_jwt_bearer_token(verify_path)
        settle_jwt = _cdp_jwt_bearer_token(settle_path)
        if verify_jwt and settle_jwt:
            return (
                CDP_FACILITATOR_URL,
                {"Content-Type": "application/json", "Authorization": f"Bearer {verify_jwt}"},
                {"Content-Type": "application/json", "Authorization": f"Bearer {settle_jwt}"},
            )
    plain_headers = {"Content-Type": "application/json"}
    return fallback_url, plain_headers, plain_headers


def _verify_and_settle_x402_payment(x_payment: str, path: str) -> dict | None:
    """Verifies AND settles the x402 payment. Returns the settlement
    response dict on success (encoded into the PAYMENT-RESPONSE header),
    or None if verification or settlement failed.

    Found 2026-07-10: calling /verify alone does NOT move funds — it only
    checks the signed payload is well-formed and funded. /settle is the
    separate call that actually submits the transaction on-chain. This
    file previously only called /verify, meaning every PAYG call ever
    delivered the paid service without collecting payment. Confirmed via
    x402 spec research and PayAI's own facilitator (a bare POST to
    /settle returns HTTP 400, not 404, confirming the endpoint is real
    and was never being called)."""
    price_units  = PAYG_PRICE_UNITS.get(path, 0)
    requirements = _build_payment_requirements(path, price_units)

    chain = _detect_payment_chain(x_payment)
    logger.info("x402 payment detected chain=%s path=%s", chain, path)

    # Decode x_payment from base64 JSON to dict — PayAI expects decoded object
    try:
        payment_payload_dict = json.loads(base64.b64decode(x_payment + "=="))
    except Exception:
        try:
            payment_payload_dict = json.loads(x_payment)
        except Exception:
            logger.error("Failed to decode x_payment for path=%s", path)
            return None

    is_v2 = path in X402_V2_ENABLED_PATHS
    base_network_id = BASE_CHAIN_ID_V2 if is_v2 else BASE_CHAIN_ID

    if chain == "solana":
        if not SOL_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_SOL_WALLET not set — cannot verify Solana x402 payment")
            return None
        chain_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == SOL_CHAIN_ID),
            None,
        )
        if not chain_requirements:
            logger.error("No Solana accepts entry in requirements for path=%s", path)
            return None
    else:
        if not X402_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_X402_WALLET not set — cannot verify EVM x402 payment")
            return None
        chain_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == base_network_id),
            requirements,
        )

    # First attempt (2026-07-16) at this fix injected a bare string as
    # "resource" directly onto payment_payload_dict — broke /verify outright
    # ("'paymentPayload' is invalid: must match one of [x402V2PaymentPayload,
    # x402V1PaymentPayload]"), caught before /settle ran so no funds moved,
    # reverted immediately. Root cause of THAT failure, confirmed against
    # the actual x402 Python SDK schema source
    # (x402/schemas/payments.py — not guessed): PaymentPayload.resource is a
    # real, valid, OPTIONAL field, but it's a structured ResourceInfo object
    # (url/description/mimeType, camelCase on the wire per
    # BaseX402Model's to_camel alias generator), not a bare string — and
    # it's explicitly V2-only (PaymentPayload is documented as "V2 payment
    # payload structure"; V1 has no equivalent concept, so this must never
    # touch V1 payloads). Reusing the exact same ResourceInfo-shaped dict
    # _build_payment_requirements already builds at requirements["resource"]
    # for V2, rather than constructing a second copy that could drift out
    # of sync with it.
    if is_v2 and requirements.get("resource"):
        payment_payload_dict["resource"] = requirements["resource"]

    # NOTE (2026-07-14): the facilitator's own /verify+/settle HTTP contract
    # wrapper keys (paymentPayload/paymentRequirements) are kept as-is for V2
    # too — only x402Version and the nested requirements shape change. This
    # is inferred from CDP still supporting both versions "for now" rather
    # than confirmed against the facilitator's own API docs, so the first V2
    # settlement in each batch is exactly where this gets verified for real.

    request_body = json.dumps({
        "x402Version":         2 if is_v2 else 1,
        "paymentPayload":      payment_payload_dict,
        "paymentRequirements": chain_requirements,
    }).encode("utf-8")

    fallback_url = SOL_FACILITATOR_URL if chain == "solana" else X402_FACILITATOR_URL
    facilitator_base, verify_headers, settle_headers = _select_facilitator(
        "/platform/v2/x402/verify", "/platform/v2/x402/settle", fallback_url,
    )

    # Step 1: verify — well-formed + funded check only, does not move funds.
    verify_url = f"{facilitator_base}/verify"
    logger.info("Sending verify to %s payload_keys=%s", verify_url, list(payment_payload_dict.keys()))

    req = urllib.request.Request(
        verify_url, data=request_body, headers=verify_headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("isValid", False):
                logger.warning("x402 payment invalid — chain=%s reason=%s path=%s",
                               chain, result.get("invalidReason"), path)
                return None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        logger.error("x402 verify HTTP %d — chain=%s path=%s body=%s",
                     exc.code, chain, path, body)
        return None
    except Exception as exc:
        logger.error("x402 verify call failed — chain=%s path=%s error=%s", chain, path, exc)
        return None

    # Step 2: settle — actually submits the transaction on-chain and moves funds.
    settle_url = f"{facilitator_base}/settle"
    req = urllib.request.Request(
        settle_url, data=request_body, headers=settle_headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            settle_result = json.loads(resp.read())
            if not settle_result.get("success", False):
                logger.error("x402 settlement failed — chain=%s path=%s result=%s", chain, path, settle_result)
                return None
            logger.info("x402 payment settled — chain=%s path=%s tx=%s",
                        chain, path, settle_result.get("transaction"))
            return settle_result
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        logger.error("x402 settle HTTP %d — chain=%s path=%s body=%s", exc.code, chain, path, body)
        return None
    except Exception as exc:
        logger.error("x402 settle call failed — chain=%s path=%s error=%s", chain, path, exc)
        return None


PAYG_SETTLEMENTS_TABLE = "relayshield_payg_settlements"


def _log_payg_settlement(path: str, price_units: int, settlement: dict) -> None:
    """Records a settled PAYG payment for weekly revenue reporting. Never
    raises — a logging failure must not break the paid response the
    customer already funded. Payment settles regardless of what happens
    to the endpoint's own handler logic afterward (see 2026-07-12 scan-file
    incident: a real settlement occurred even though the handler itself
    then failed on an unrelated file-download bug), so this is called
    right after settlement succeeds, not after the handler returns."""
    try:
        table = dynamodb.Table(PAYG_SETTLEMENTS_TABLE)
        now   = datetime.now(timezone.utc)
        table.put_item(Item={
            "settlement_id": str(uuid.uuid4()),
            "timestamp":     now.isoformat(),
            "path":          path,
            "amount_usd":    Decimal(str(price_units / 1_000_000)),
            "network":       settlement.get("network", "unknown"),
            "tx_hash":       settlement.get("transaction", ""),
            "payer":         settlement.get("payer", ""),
            "ttl":           int(now.timestamp()) + 90 * 86400,
        })
    except Exception as exc:
        logger.warning("Failed to log PAYG settlement for path=%s: %s", path, exc)


def _log_hf_mcp_call(path: str, credit_cost: int) -> None:
    """Tags a successfully-billed metered call as attributable to the
    relayshield-agentic-attack-surface HF Space, for the weekly metrics
    report (TODO.md item added 2026-07-15). Shares the PAYG settlements
    table rather than a new one — only the source/consuming query differs.
    credit_cost is in METERED_CREDIT_COSTS units (100 = $1.00). Never
    raises, same rationale as _log_payg_settlement."""
    try:
        table = dynamodb.Table(PAYG_SETTLEMENTS_TABLE)
        now   = datetime.now(timezone.utc)
        table.put_item(Item={
            "settlement_id": str(uuid.uuid4()),
            "timestamp":     now.isoformat(),
            "path":          path,
            "amount_usd":    Decimal(str(credit_cost)) / Decimal(100),
            "source":        "hf-mcp-space",
            "ttl":           int(now.timestamp()) + 90 * 86400,
        })
    except Exception as exc:
        logger.warning("Failed to log HF MCP call for path=%s: %s", path, exc)


def handle_payg_request(path: str, method: str, event: dict) -> dict:
    headers   = event.get("headers") or {}
    # V1 clients send the signed payload as X-PAYMENT; V2 clients send it as
    # PAYMENT-SIGNATURE instead (verified 2026-07-14 against the actual SDK,
    # x402/http/x402_http_client_base.py's encode_payment_signature_header).
    # Missing this for V2 paths meant every payment attempt went unseen by
    # the server, which always re-issued a fresh 402 — no funds were ever at
    # risk, but no V2 payment could ever succeed either.
    x_payment = _header(headers, "PAYMENT-SIGNATURE") or _header(headers, "X-PAYMENT")

    # Free poll endpoint — no payment needed
    if method == "GET" and path.startswith("/v1/payg/result/"):
        analysis_id = path[len("/v1/payg/result/"):]
        return handle_result(analysis_id)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    # Require payment proof
    if not x_payment:
        return _x402_payment_required(path)

    settlement = _verify_and_settle_x402_payment(x_payment, path)
    if settlement is None:
        return {
            "statusCode": 402,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Invalid or expired payment proof, or settlement failed — pay again and retry.",
            }),
        }
    _log_payg_settlement(path, PAYG_PRICE_UNITS.get(path, 0), settlement)

    payg_routes = {
        "/v1/payg/breach":                handle_breach,
        "/v1/payg/sim-swap":              handle_sim_swap,
        "/v1/payg/domain":                handle_domain,
        "/v1/payg/oauth-watchlist":       handle_oauth_watchlist,
        "/v1/payg/scan-wallet":           handle_scan_wallet,       # legacy EVM-only
        "/v1/payg/scan-url":              handle_scan_url,
        "/v1/payg/scan-file":             handle_scan_file,
        "/v1/payg/wallet-risk":           handle_wallet_risk,
        "/v1/payg/token-security":        handle_token_security,
        "/v1/payg/nft-security":          handle_nft_security,
        "/v1/payg/wallet-screen-batch":   handle_wallet_screen_batch,
        "/v1/payg/infostealer":           handle_infostealer,
        "/v1/payg/supply-chain":          handle_supply_chain,
        "/v1/payg/session-risk":          handle_session_risk,
        "/v1/payg/identity-graph":        handle_identity_graph,
        "/v1/payg/ransomware-risk":       handle_ransomware_risk,
        "/v1/payg/nhi-exposure":          handle_nhi_exposure,
        "/v1/payg/llm-credential-exposure": handle_llm_credential_exposure,
        "/v1/payg/secret-scan":           handle_secret_scan,
        "/v1/payg/secret-scan-text":      handle_secret_scan_text,
        "/v1/payg/target-risk":           handle_target_risk,
        "/v1/payg/tech-stack-cve":        handle_tech_stack_cve,
        "/v1/payg/bulk-identity-risk":    handle_bulk_identity_risk,
        "/v1/payg/identity-risk-score":   handle_identity_risk_score,
        "/v1/payg/cert-expiry":           handle_cert_expiry,
        "/v1/payg/ip-intel":              handle_ip_intel,
    }
    handler = payg_routes.get(path)
    if not handler:
        return _err(f"unknown PAYG endpoint: {path}", 404)

    params = _body(event)
    try:
        result = handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in PAYG %s: %s", path, exc)
        return _err("internal server error", 500)

    # Include the settlement receipt per x402 spec (PAYMENT-RESPONSE header,
    # base64-encoded JSON) so compliant client libraries get a verifiable
    # receipt instead of crashing on a missing header.
    encoded_settlement = base64.b64encode(json.dumps(settlement).encode()).decode()
    result.setdefault("headers", {})
    result["headers"]["PAYMENT-RESPONSE"] = encoded_settlement
    result["headers"]["Access-Control-Expose-Headers"] = "PAYMENT-RESPONSE"
    return result


# ---------------------------------------------------------------------------
# Threat Intelligence API — /v1/intel/cve
# ---------------------------------------------------------------------------
# Request: POST /v1/intel/cve
#   { "cve_id": "CVE-2024-1234" }   — exact CVE ID lookup
#   { "keyword": "apache" }          — case-insensitive keyword scan across
#                                      vendor_project, product, vulnerability_name
#
# Response:
#   { ok: true, data: { count: int, results: [...] } }
# ---------------------------------------------------------------------------

def _cve_actor_discussion_heat(cve_id: str) -> dict:
    """CVE actor-discussion-heat score -- how often this CVE is actually
    being discussed in monitored criminal-channel chatter, not just its
    static CVSS/EPSS severity. Derived entirely from relayshield_intel_iocs
    (ioc_type="cve"), which extract_iocs() has always extracted per-message
    but _store_iocs() never persisted until 2026-07-24 -- so history here
    starts accumulating from that deploy forward, not backfilled from past
    messages that were never stored this way.

    ioc_value is the table's hash key, so this is a real Query (all
    occurrences of one exact CVE ID), not the substring table.scan()
    brand-monitor uses -- ioc_value there needs prefix/contains matching,
    this doesn't.
    """
    table = dynamodb.Table(INTEL_IOCS_TABLE)
    try:
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(cve_id.lower()),
            FilterExpression=boto3.dynamodb.conditions.Attr("ioc_type").eq("cve"),
        )
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(cve_id.lower()),
                FilterExpression=boto3.dynamodb.conditions.Attr("ioc_type").eq("cve"),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
    except Exception as exc:
        logger.warning("CVE heat query failed cve_id=%s: %s", cve_id, exc)
        return {"mentions_30d": 0, "distinct_channels_30d": 0, "tier": "unknown", "last_seen": None}

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = []
    for it in items:
        try:
            if datetime.fromisoformat(it["seen_ts"]) >= cutoff:
                recent.append(it)
        except (KeyError, ValueError):
            continue

    mentions = len(recent)
    channels = len({it.get("channel", "") for it in recent})
    if mentions >= 10 or channels >= 3:
        tier = "high"
    elif mentions >= 3:
        tier = "medium"
    elif mentions >= 1:
        tier = "low"
    else:
        tier = "none"

    last_seen = max((it["seen_ts"] for it in items if it.get("seen_ts")), default=None)
    return {
        "mentions_30d": mentions,
        "distinct_channels_30d": channels,
        "tier": tier,
        "last_seen": last_seen,
    }


def handle_intel_cve(params: dict, api_key_record: dict | None = None) -> dict:
    cve_id  = (params.get("cve_id") or "").strip().upper()
    keyword = (params.get("keyword") or "").strip().lower()

    if not cve_id and not keyword:
        return _err("cve_id or keyword is required")

    table = dynamodb.Table(INTEL_CVE_TABLE)

    if cve_id:
        try:
            resp = table.get_item(Key={"cve_id": cve_id})
            item = resp.get("Item")
        except Exception as exc:
            logger.error("cve lookup failed cve_id=%s: %s", cve_id, exc)
            return _err("CVE lookup failed", 500)

        if not item:
            return _ok({"count": 0, "results": []})

        item.pop("ttl", None)
        item["actor_discussion_heat"] = _cve_actor_discussion_heat(cve_id)
        return _ok({"count": 1, "results": [item]})

    # Keyword scan — scan table and filter in Python (table is small, <2K rows)
    try:
        resp  = table.scan()
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp  = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except Exception as exc:
        logger.error("cve keyword scan failed keyword=%s: %s", keyword, exc)
        return _err("CVE keyword scan failed", 500)

    matches = []
    for item in items:
        haystack = " ".join([
            item.get("vendor_project", ""),
            item.get("product", ""),
            item.get("vulnerability_name", ""),
            item.get("short_description", ""),
        ]).lower()
        if keyword in haystack:
            item.pop("ttl", None)
            matches.append(item)

    matches.sort(key=lambda x: x.get("date_added", ""), reverse=True)

    # Enhancement 5: Enrich results with ATT&CK threat actor correlation
    attack_table = dynamodb.Table("relayshield_mitre_attack")
    for m in matches[:10]:   # enrich top 10 only — avoid scan latency on large result sets
        product = (m.get("product", "") or "").lower()
        vendor  = (m.get("vendor_project", "") or "").lower()
        related_actors = []
        try:
            # Scan ATT&CK groups for technique associations (T1190 = exploit public-facing app)
            # Use known high-value technique IDs relevant to KEV vulnerabilities
            kev_techniques = {"T1190", "T1133", "T1203", "T1068"}
            scan_resp = attack_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("sk").eq("info"),
                ProjectionExpression="group_id, #n, aliases, technique_ids",
                ExpressionAttributeNames={"#n": "name"},
                Limit=50,
            )
            for actor in scan_resp.get("Items", []):
                techniques = set(actor.get("technique_ids", []))
                if techniques & kev_techniques:
                    related_actors.append({
                        "group_id":  actor.get("group_id", ""),
                        "name":      actor.get("name", ""),
                        "aliases":   actor.get("aliases", [])[:3],
                    })
        except Exception as exc:
            logger.warning("ATT&CK correlation failed: %s", exc)
        if related_actors:
            m["related_threat_actors"] = related_actors[:5]
            m["hunting_note"] = (
                f"This CVE targets {vendor}/{product}. "
                f"Threat groups known to exploit similar techniques: "
                + ", ".join(a["name"] for a in related_actors[:3])
            )

    return _ok({"count": len(matches), "results": matches[:50]})


# ---------------------------------------------------------------------------
# TC Feature 1 — Bulk IOC lookup  POST /v1/metered/bulk-ioc
# Accepts up to 100 IOC values, returns enriched results for each.
# Closes the #1 MSP log-enrichment gap vs ThreatConnect.
# $0.50/batch, Stripe meter: relayshield_bulk_ioc_calls
# ---------------------------------------------------------------------------

def handle_bulk_ioc(params: dict) -> dict:
    iocs = params.get("iocs", [])
    if not iocs or not isinstance(iocs, list):
        return _err("iocs must be a non-empty list of strings")
    if len(iocs) > 100:
        return _err("maximum 100 IOCs per request")
    table   = dynamodb.Table(INTEL_IOCS_TABLE)
    results = []
    for val in iocs:
        val = str(val).strip().lower()
        if not val:
            continue
        try:
            resp = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(val),
                ScanIndexForward=False,
                Limit=5,
            )
            hits = resp.get("Items", [])
            if hits:
                best = hits[0]
                results.append({
                    "ioc_value":        val,
                    "matched":          True,
                    "ioc_type":         best.get("ioc_type", ""),
                    "source":           best.get("channel", ""),
                    "malware":          best.get("malware", ""),
                    "threat_actor":     best.get("threat_actor", ""),
                    "confidence_score": float(best.get("confidence_score", 0.5)),
                    "first_seen":       hits[-1].get("seen_ts", ""),
                    "last_seen":        best.get("seen_ts", ""),
                    "hit_count":        len(hits),
                })
            else:
                results.append({"ioc_value": val, "matched": False})
        except Exception as exc:
            logger.error("bulk_ioc query failed ioc=%s: %s", val[:30], exc)
            results.append({"ioc_value": val, "matched": False, "error": "query_failed"})
    matched = sum(1 for r in results if r.get("matched"))
    return _ok({"queried": len(results), "matched": matched, "results": results})


# ---------------------------------------------------------------------------
# TC Feature 2 — IOC pivot  POST /v1/metered/ioc-pivot
# Given one IOC, return related IOCs sharing the same malware family or source.
# Surfaces lateral infrastructure — e.g., all C2 IPs for LummaC2.
# $0.20/call, Stripe meter: relayshield_ioc_pivot_calls
# ---------------------------------------------------------------------------

def handle_ioc_pivot(params: dict) -> dict:
    ioc_value = (params.get("ioc") or params.get("ioc_value") or "").strip().lower()
    if not ioc_value:
        return _err("ioc is required")
    table = dynamodb.Table(INTEL_IOCS_TABLE)
    # Step 1: look up the pivot IOC to get its malware family
    try:
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(ioc_value),
            ScanIndexForward=False, Limit=1,
        )
        items = resp.get("Items", [])
    except Exception as exc:
        return _err(f"IOC lookup failed: {exc}")
    if not items:
        return _ok({"ioc_value": ioc_value, "matched": False, "related": []})
    seed    = items[0]
    malware = seed.get("malware", "")
    source  = seed.get("channel", "")
    # Step 2: find related IOCs by malware family (most useful pivot)
    related: list[dict] = []
    if malware:
        try:
            scan_resp = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("malware").eq(malware)
                    & boto3.dynamodb.conditions.Attr("ioc_value").ne(ioc_value),
                Limit=200,
            )
            for item in scan_resp.get("Items", []):
                related.append({
                    "ioc_value":    item.get("ioc_value", ""),
                    "ioc_type":     item.get("ioc_type", ""),
                    "source":       item.get("channel", ""),
                    "malware":      item.get("malware", ""),
                    "last_seen":    item.get("seen_ts", ""),
                })
        except Exception as exc:
            logger.error("ioc_pivot scan failed: %s", exc)
    return _ok({
        "ioc_value":     ioc_value,
        "matched":       True,
        "pivot_on":      "malware_family" if malware else "source_feed",
        "pivot_value":   malware or source,
        "seed_ioc_type": seed.get("ioc_type", ""),
        "seed_source":   source,
        "seed_malware":  malware,
        "related_count": len(related),
        "related":       related[:50],
    })


# ---------------------------------------------------------------------------
# TC Feature 3 — Actor profile  GET /v1/intel/actor
# Full MITRE ATT&CK profile for a named threat actor: TTPs, targets,
# recent campaigns, associated IOCs from corpus.
# TI subscription required (intel_access flag). Included in TI plan.
# ---------------------------------------------------------------------------

def handle_intel_actor(params: dict, api_key_record: dict | None = None) -> dict:
    if not api_key_record or not api_key_record.get("intel_access"):
        return {
            "statusCode": 403, "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": False, "error": "Threat Intelligence subscription required."}),
        }
    actor_name = (params.get("actor") or params.get("name") or "").strip()
    if not actor_name:
        return _err("actor name is required")
    mitre_table = dynamodb.Table("relayshield_mitre_attack")
    ioc_table   = dynamodb.Table(INTEL_IOCS_TABLE)
    # Load all MITRE groups, then match in Python.
    #
    # Fixed 2026-08-01. This previously pushed the name match into a DynamoDB
    # FilterExpression using Attr.contains(), which is case-SENSITIVE — so
    # "muddywater" and "MANGO SANDSTORM" returned matched:false while
    # "MuddyWater" worked, and the demo UI renders that as "No threat actor
    # found", indistinguishable from a genuine miss. The scan was also
    # unpaginated, so any match past the first 1MB page was silently invisible;
    # the table is now 593KB and one ATT&CK release away from that being live.
    # There are only ~191 groups, so filtering client-side is cheap and exact.
    try:
        groups: list[dict] = []
        scan_kwargs: dict = {"FilterExpression": boto3.dynamodb.conditions.Attr("sk").eq("info")}
        while True:
            resp = mitre_table.scan(**scan_kwargs)
            groups.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    except Exception as exc:
        return _err(f"MITRE lookup failed: {exc}")

    needle = " ".join(actor_name.lower().split())

    def _names(g: dict) -> list[str]:
        return [g.get("name", "")] + list(g.get("aliases") or [])

    def _norm(n: str) -> str:
        return " ".join((n or "").lower().split())

    # Exact alias match first, substring only as a fallback, so that a query
    # for "APT3" cannot be captured by a group merely containing that text.
    matches = [g for g in groups if any(_norm(n) == needle for n in _names(g))]
    if not matches:
        matches = [
            g for g in groups
            if any(needle and needle in _norm(n) for n in _names(g))
        ]
    if not matches:
        return _ok({"actor": actor_name, "matched": False, "profile": None})
    groups = matches
    group  = groups[0]

    # Real threat-actor -> malware-family -> live-IOC attribution, fixed
    # 2026-07-16. Previously always empty for two reasons: (1) it filtered
    # the IOC corpus on a `threat_actor` field that doesn't exist on real
    # IOC records (the real field is `malware`, a lowercase family name);
    # (2) relayshield_intel_attack.py never actually populated a group's
    # associated software/malware list at all (its STIX relationship parser
    # checked for type "uses" directly, but real STIX 2.1 relationship
    # objects have type "relationship" with the edge name in a separate
    # relationship_type field — fixed same day). Now: resolve the group's
    # real associated malware/tool names via its software_ids list, then
    # query the IOC corpus's malware-index GSI for each one.
    software_names: list[str] = []
    for sid in group.get("software_ids", [])[:30]:
        try:
            sw = mitre_table.get_item(Key={"group_id": sid, "sk": f"software:{sid}"}).get("Item")
        except Exception:
            sw = None
        if sw:
            software_names.append(sw.get("name", ""))
            software_names.extend(sw.get("aliases", []))

    iocs: list[dict] = []
    checked_names: set = set()
    for name in software_names:
        key = name.strip().lower()
        if not key or key in checked_names:
            continue
        checked_names.add(key)
        try:
            ioc_resp = ioc_table.query(
                IndexName="malware-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("malware").eq(key),
                Limit=20,
            )
            for item in ioc_resp.get("Items", []):
                iocs.append({
                    "ioc_value": item.get("ioc_value", ""),
                    "ioc_type":  item.get("ioc_type", ""),
                    "malware":   item.get("malware", ""),
                    "last_seen": item.get("seen_ts", ""),
                })
        except Exception as exc:
            logger.warning("intel-actor IOC query failed malware=%s: %s", key, exc)

    seen_vals: set = set()
    dedup_iocs = []
    for i in iocs:
        if i["ioc_value"] not in seen_vals:
            seen_vals.add(i["ioc_value"])
            dedup_iocs.append(i)

    # Recent open-source reporting naming this group, written by the intel
    # feed ingesters as `sighting:` records under the group's own partition.
    # Added 2026-08-01 — before this, the actor profile was static MITRE data
    # only, and nothing the feeds collected reached this surface.
    recent_reporting: list[dict] = []
    try:
        sight_resp = mitre_table.query(
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key("group_id").eq(group.get("group_id", ""))
                & boto3.dynamodb.conditions.Key("sk").begins_with("sighting:")
            ),
            Limit=25,
        )
        recent_reporting = sorted(
            (
                {
                    "title":       s.get("title", ""),
                    "url":         s.get("article_url", ""),
                    "published":   s.get("published", ""),
                    "source":      s.get("source", ""),
                    "matched_as":  s.get("matched_as", []),
                }
                for s in sight_resp.get("Items", [])
            ),
            key=lambda s: s.get("published", ""),
            reverse=True,
        )[:10]
    except Exception as exc:
        logger.warning("intel-actor sighting query failed group=%s: %s",
                       group.get("group_id"), exc)

    return _ok({
        "actor":              actor_name,
        "matched":            True,
        "mitre_id":           group.get("group_id", ""),
        "recent_reporting":   recent_reporting,
        "reporting_count":    len(recent_reporting),
        "aliases":            group.get("aliases", []),
        "description":        group.get("description", ""),
        "techniques":         group.get("technique_ids", []),
        "associated_malware": sorted(checked_names),
        "origin_country":     group.get("country_origin", ""),
        "associated_iocs":    dedup_iocs[:30],
        "ioc_count":          len(dedup_iocs),
        "source":             "MITRE ATT&CK + RelayShield IOC corpus",
        # Actor pivot — related actors sharing techniques
        "related_actors":     _actor_pivot(group, groups),
    })


def _actor_pivot(group: dict, all_groups: list) -> list[dict]:
    """Find related threat actors sharing ATT&CK techniques. MITRE's Groups
    data doesn't include a "target sectors" concept, so this pivots on
    technique overlap only."""
    pivot_techniques = set((group.get("technique_ids") or [])[:10])
    group_id         = group.get("group_id", "")
    related = []
    for g in all_groups:
        if g.get("group_id") == group_id:
            continue
        g_techniques = set((g.get("technique_ids") or [])[:10])
        shared_ttps = pivot_techniques & g_techniques
        if shared_ttps:
            related.append({
                "actor":             g.get("name", ""),
                "mitre_id":          g.get("group_id", ""),
                "origin_country":    g.get("country_origin", ""),
                "shared_techniques": sorted(shared_ttps)[:3],
            })
    related.sort(key=lambda r: len(r["shared_techniques"]), reverse=True)
    return related[:10]


# ---------------------------------------------------------------------------
# RF Feature 1 — Trending threats  GET /v1/intel/trending
# Top IOCs seen across feeds in the last 24 hours, grouped by type.
# Surfaces what's actively spreading NOW — equivalent to RF's trending threats.
# TI subscription required. Included in TI plan.
# ---------------------------------------------------------------------------

def handle_intel_trending(params: dict, api_key_record: dict | None = None) -> dict:
    if not api_key_record or not api_key_record.get("intel_access"):
        return {
            "statusCode": 403, "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": False, "error": "Threat Intelligence subscription required."}),
        }
    hours  = min(int(params.get("hours", 24)), 72)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    table  = dynamodb.Table(INTEL_IOCS_TABLE)
    try:
        resp  = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("seen_ts").gte(cutoff),
            ProjectionExpression="ioc_value, ioc_type, malware, channel, seen_ts, confidence_score",
        )
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp and len(items) < 2000:
            resp  = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("seen_ts").gte(cutoff),
                ProjectionExpression="ioc_value, ioc_type, malware, channel, seen_ts, confidence_score",
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
    except Exception as exc:
        return _err(f"Trending scan failed: {exc}")
    # Group by type, sort by confidence desc
    by_type: dict[str, list] = {}
    for item in items:
        t = item.get("ioc_type", "unknown")
        by_type.setdefault(t, []).append({
            "ioc_value":  item.get("ioc_value", ""),
            "malware":    item.get("malware", ""),
            "source":     item.get("channel", ""),
            "seen_ts":    item.get("seen_ts", ""),
            "confidence": float(item.get("confidence_score", 0.5)),
        })
    # Top 20 per type by confidence
    trending = {t: sorted(v, key=lambda x: x["confidence"], reverse=True)[:20]
                for t, v in by_type.items()}
    return _ok({
        "window_hours":  hours,
        "total_new_iocs": len(items),
        "trending":      trending,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# RF Feature 2 — Brand monitor  POST /v1/metered/brand-monitor
# Scans IOC domain corpus and Telegram channel IOCs for brand name patterns.
# Surfaces typosquat domains, phishing infrastructure, and dark web mentions.
# Equivalent to RF brand protection / Flare brand monitoring at fraction of cost.
# $0.35/call (raised from $0.25 2026-07-24 — see image_logo_mentions below),
# Stripe meter: relayshield_brand_monitor_calls
#
# Image/logo brand monitoring folded in 2026-07-24 (competitive benchmark
# roadmap item, closes the Intel 471 "text, images, and logos" gap) rather
# than shipped as a separate endpoint, per founder direction — OCR'd image
# text from monitored channels (relayshield_intel_monitor.py) is now
# persisted as ioc_type="image_text" in the same relayshield_intel_iocs
# table this handler already scans, so it's already covered by the existing
# substring scan below with zero extra query logic; only the classification
# breakout (image_logo_mentions) and the price change are new here.
# ---------------------------------------------------------------------------

def handle_brand_monitor(params: dict) -> dict:
    brand = (params.get("brand") or "").strip().lower()
    if not brand or len(brand) < 3:
        return _err("brand must be at least 3 characters")
    table  = dynamodb.Table(INTEL_IOCS_TABLE)
    hits: list[dict] = []
    try:
        resp = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("ioc_value").contains(brand),
            ProjectionExpression="ioc_value, ioc_type, malware, channel, seen_ts, category",
        )
        hits.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp and len(hits) < 500:
            resp = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("ioc_value").contains(brand),
                ProjectionExpression="ioc_value, ioc_type, malware, channel, seen_ts, category",
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            hits.extend(resp.get("Items", []))
    except Exception as exc:
        return _err(f"Brand scan failed: {exc}")
    # Classify hits
    phishing    = [h for h in hits if h.get("category") in ("phishing", "threat_feed")
                   and h.get("ioc_type") in ("domain", "url")]
    malware_c2  = [h for h in hits if h.get("malware")]
    dark_web    = [h for h in hits if h.get("channel", "").startswith("@")
                   or h.get("category") == "credential_exposure"]
    image_logo  = [h for h in hits if h.get("ioc_type") == "image_text"]
    def _fmt(items: list) -> list:
        return [{"ioc_value": i.get("ioc_value",""), "ioc_type": i.get("ioc_type",""),
                 "source": i.get("channel",""), "malware": i.get("malware",""),
                 "last_seen": i.get("seen_ts","")} for i in items[:20]]
    return _ok({
        "brand":                brand,
        "matched":              len(hits) > 0,
        "total_mentions":       len(hits),
        "phishing_domains":     len(phishing),
        "malware_c2":           len(malware_c2),
        "dark_web_mentions":    len(dark_web),
        "image_logo_mentions":  len(image_logo),
        "hits": {
            "phishing":   _fmt(phishing),
            "malware_c2": _fmt(malware_c2),
            "dark_web":   _fmt(dark_web),
            "image_logo": _fmt(image_logo),
        },
        "recommendation": (
            "CRITICAL: active brand abuse detected in criminal infrastructure"
            if len(hits) > 10 else
            "WARNING: brand patterns found — review hits"
            if len(hits) > 0 else
            "No brand mentions found in current corpus"
        ),
    })


# ---------------------------------------------------------------------------
# Bulk identity risk  POST /v1/metered/bulk-identity-risk
#
# Hierarchical org + agent-level risk scoring in one call.
# Use cases: MSP weekly sweep across client domains; OrcX agentic AI governance
# (score the identities enterprise AI agents act on behalf of).
#
# Input:
#   { "targets": [
#       { "domain": "acme.com",
#         "agents": ["agent-cs@acme.com", "agent-sales@acme.com"] },  # optional
#       { "domain": "beta.com" }
#     ]
#   }
# Limits: up to 10 domains, up to 5 agents per domain (50 identity checks max).
# $2.00/call — premium positioning: unique per-agent hierarchy, no competitor equivalent.
# Stripe meter: relayshield_bulk_identity_risk_calls
# ---------------------------------------------------------------------------

def _domain_risk_fast(domain: str) -> dict:
    """Run all 6 identity risk dimensions for one domain. Returns score dict."""
    ioc_table      = dynamodb.Table(INTEL_IOCS_TABLE)
    ransomware_tbl = dynamodb.Table("relayshield_intel_ransomware")
    sessions_tbl   = dynamodb.Table("relayshield_stolen_sessions")
    cve_table      = dynamodb.Table(INTEL_CVE_TABLE)
    base_name      = domain.split(".")[0]
    company        = base_name.capitalize()
    dim            = {}
    factors        = []

    # D1: Breach exposure (0-20)
    try:
        hibp_key = _hibp_api_key()
        req = urllib.request.Request(
            f"https://haveibeenpwned.com/api/v3/breacheddomain/{domain}",
            headers={"hibp-api-key": hibp_key, "User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            breaches = json.loads(r.read())
            n = len(breaches) if isinstance(breaches, list) else 0
            dim["breach_exposure"] = min(20, n * 2)
            if n: factors.append(f"{n} domain breaches")
    except Exception:
        dim["breach_exposure"] = 0

    # D2: Infostealer density (0-20)
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f"{CAVALIER_DOMAIN_URL}?domain={domain}",
            headers={"User-Agent": "RelayShield/1.0"}), timeout=8)
        d = json.loads(r.read())
        n = d.get("total", 0) or len(d.get("stealers", []))
        dim["infostealer_density"] = min(20, n * 5)
        if n: factors.append(f"{n} stealer log hits")
    except Exception:
        dim["infostealer_density"] = 0

    # D3: IOC presence (0-15)
    try:
        resp = ioc_table.scan(FilterExpression=boto3.dynamodb.conditions.Attr("ioc_value").contains(domain.split(".")[0]), Limit=20)
        n = len(resp.get("Items", []))
        dim["ioc_presence"] = min(15, n * 3)
        if n: factors.append(f"{n} IOC corpus hits")
    except Exception:
        dim["ioc_presence"] = 0

    # D4: Ransomware victim (0-20)
    try:
        resp = ransomware_tbl.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("domain").eq(domain), Limit=3)
        items = resp.get("Items", [])
        dim["ransomware_victim"] = 20 if items else 0
        if items: factors.append(f"Ransomware victim: {', '.join(i.get('group','') for i in items)}")
    except Exception:
        dim["ransomware_victim"] = 0

    # D5: Session exposure (0-15)
    try:
        resp = sessions_tbl.scan(FilterExpression=boto3.dynamodb.conditions.Attr("matched_email").contains(domain), Limit=10)
        n = len(resp.get("Items", []))
        dim["session_exposure"] = min(15, n * 5)
        if n: factors.append(f"{n} stolen session records")
    except Exception:
        dim["session_exposure"] = 0

    # D6: CVE exposure — fast single-page scan by vendor_project (no pagination = no timeout)
    try:
        cve_resp = cve_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("vendor_project").eq(company),
            Limit=500,
        )
        cve_items = cve_resp.get("Items", [])
        rw = sum(1 for c in cve_items if c.get("known_ransomware_campaign_use") == "Known")
        tot = len(cve_items)
        cve_score = 25 if rw>=50 else 20 if rw>=20 else 15 if rw>=10 else 12 if rw>=5 else 6 if rw>=1 else 3 if tot>=5 else 0
        dim["cve_exposure"] = cve_score
        if tot: factors.append(f"{tot} actively exploited CVEs affecting {company} products ({rw} ransomware-linked)")
    except Exception:
        dim["cve_exposure"] = 0

    total = min(100, sum(dim.values()))
    return {
        "risk_score":       total,
        "grade":            "F" if total >= 75 else "D" if total >= 50 else "C" if total >= 35 else "B" if total >= 15 else "A",
        "risk_level":       "CRITICAL" if total >= 75 else "HIGH" if total >= 50 else "MEDIUM" if total >= 25 else "LOW",
        "dimension_scores": dim,
        "risk_factors":     factors,
    }


def _agent_risk(email: str) -> dict:
    """Score an individual agent identity (email) across breach, stealer, and session signals."""
    email   = email.strip().lower()
    factors = []
    score   = 0

    # Breach: HIBP individual account (5s timeout to avoid overall timeout)
    try:
        hibp_key = _hibp_api_key()
        req = urllib.request.Request(
            f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=true",
            headers={"hibp-api-key": hibp_key, "User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            breaches = json.loads(r.read())
            n = len(breaches) if isinstance(breaches, list) else 0
            score += min(35, n * 5)
            if n: factors.append(f"{n} account breaches")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            pass
    except Exception:
        pass

    # Infostealer: Hudson Rock by email
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f"{CAVALIER_URL}?email={urllib.parse.quote(email)}",
            headers={"User-Agent": "RelayShield/1.0"}), timeout=8)
        d = json.loads(r.read())
        n = d.get("total", 0) or len(d.get("stealers", []))
        score += min(40, n * 20)
        if n: factors.append(f"{n} infostealer log hits")
    except Exception:
        pass

    # Session/credential exposure: check by matched_email
    try:
        sessions_tbl = dynamodb.Table("relayshield_stolen_sessions")
        resp = sessions_tbl.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("matched_email").eq(email), Limit=5)
        items = resp.get("Items", [])
        n = len(items)
        cred_items = [i for i in items if i.get("session_type") == "credential"]
        score += min(40, len(cred_items) * 25 + (n - len(cred_items)) * 10)
        if cred_items:
            cred_types = list({i.get("category","credential") for i in cred_items})
            factors.append(f"NHI credential exposure: {len(cred_items)} service credential(s) found in stealer archives ({', '.join(cred_types[:2])})")
        elif n:
            factors.append(f"{n} stolen session record(s) in criminal corpus")
    except Exception:
        pass

    score = min(100, score)
    return {
        "identity":     email,
        "risk_score":   score,
        "grade":        "F" if score >= 75 else "D" if score >= 50 else "C" if score >= 35 else "B" if score >= 15 else "A",
        "risk_level":   "CRITICAL" if score >= 75 else "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW",
        "risk_factors": factors,
    }


def handle_bulk_identity_risk(params: dict) -> dict:
    targets = params.get("targets", [])
    if not targets or not isinstance(targets, list):
        return _err("targets must be a non-empty list of {domain, agents?} objects")
    if len(targets) > 10:
        return _err("maximum 10 domains per request")

    results = []
    for t in targets:
        domain = (t.get("domain") or "").strip().lower()
        if not domain or "." not in domain:
            results.append({"domain": domain or "invalid", "error": "invalid domain"})
            continue

        agents_in = (t.get("agents") or [])[:5]  # cap at 5 per domain

        domain_result = _domain_risk_fast(domain)
        agent_results = [_agent_risk(e) for e in agents_in if e]

        # Composite flag: any agent CRITICAL elevates domain to at least HIGH
        if any(a["risk_level"] == "CRITICAL" for a in agent_results):
            if domain_result["risk_level"] == "LOW":
                domain_result["risk_level"] = "HIGH"
                domain_result["risk_factors"].append("Agent identity CRITICAL signal elevates org risk")

        results.append({
            "domain":         domain,
            "domain_score":   domain_result["risk_score"],
            "domain_grade":   domain_result["grade"],
            "domain_risk":    domain_result["risk_level"],
            "dimension_scores": domain_result["dimension_scores"],
            "domain_factors": domain_result["risk_factors"],
            "agents":         agent_results,
            "agent_count":    len(agent_results),
            "highest_agent_risk": max((a["risk_level"] for a in agent_results),
                                      key=lambda l: {"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3}.get(l,0))
                                  if agent_results else None,
        })

    critical = sum(1 for r in results if r.get("domain_risk") == "CRITICAL" or r.get("highest_agent_risk") == "CRITICAL")
    high     = sum(1 for r in results if r.get("domain_risk") == "HIGH"     or r.get("highest_agent_risk") == "HIGH")

    return _ok({
        "queried":         len(results),
        "critical_count":  critical,
        "high_count":      high,
        "results":         results,
        "summary": (
            f"{critical} CRITICAL, {high} HIGH risk identities across {len(results)} domains."
            if (critical + high) else
            f"No high-risk signals detected across {len(results)} domains."
        ),
    })


# ---------------------------------------------------------------------------
# Sprint B Item 7 — Tech Stack CVE Targeting  POST /v1/metered/tech-stack-cve
#
# Cross-references a list of declared technology products against the CISA KEV
# corpus and high-EPSS CVEs. Returns CVEs actively being exploited that target
# the caller's specific tech stack. Closes the Intel 471 / Flashpoint vuln intel gap.
#
# Input:  { "tech_stack": ["nginx", "wordpress", "cisco ios"] }
#         OR pass "domain" to pull tech_stack from a user's profile record.
# Output: matched CVEs with EPSS score, KEV status, ransomware flag, exploit chatter.
# $0.20/call. Stripe meter: relayshield_tech_stack_cve_calls
# ---------------------------------------------------------------------------

def handle_tech_stack_cve(params: dict) -> dict:
    tech_stack = params.get("tech_stack") or []
    domain     = (params.get("domain") or "").strip().lower()

    # Allow domain lookup to pull stored tech_stack from user record
    if not tech_stack and domain:
        try:
            users_table = dynamodb.Table("relayshield_users")
            resp = users_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("monitored_domain").eq(domain),
                Limit=1,
            )
            items = resp.get("Items", [])
            if items:
                tech_stack = items[0].get("tech_stack", [])
        except Exception:
            pass

    if not tech_stack or not isinstance(tech_stack, list):
        return _err("tech_stack must be a non-empty list of product names, or pass domain to use stored stack")

    cve_table = dynamodb.Table(INTEL_CVE_TABLE)
    matched: list[dict] = []

    try:
        resp = cve_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("epss_score").gt(Decimal("0.1")),
        )
        all_cves = resp.get("Items", [])
        while "LastEvaluatedKey" in resp and len(all_cves) < 2000:
            resp = cve_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("epss_score").gt(Decimal("0.1")),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            all_cves.extend(resp.get("Items", []))
    except Exception as exc:
        return _err(f"CVE lookup failed: {exc}")

    stack_lower = [t.lower().strip() for t in tech_stack]
    for cve in all_cves:
        description = (cve.get("description") or cve.get("short_description") or "").lower()
        product     = (cve.get("affected_product") or cve.get("product") or "").lower()
        combined    = f"{description} {product}"
        for tech in stack_lower:
            if tech and len(tech) >= 3 and tech in combined:
                matched.append({
                    "cve_id":             cve.get("cve_id", ""),
                    "matched_product":    tech,
                    "epss_score":         float(cve.get("epss_score", 0)),
                    "in_kev":             cve.get("in_kev", False),
                    "ransomware_campaign": cve.get("ransomware_campaign", False),
                    "cvss_score":         float(cve.get("cvss_score", 0)) if cve.get("cvss_score") else None,
                    "description":        (cve.get("description") or "")[:200],
                    "published":          cve.get("published_date") or cve.get("added_date") or "",
                })
                break

    matched.sort(key=lambda x: (x["in_kev"], x["ransomware_campaign"], x["epss_score"]), reverse=True)
    critical = [m for m in matched if m["in_kev"] or m["ransomware_campaign"]]

    # PoC/exploit-availability signal (added 2026-07-26) — deliberately
    # bounded to the top 3 non-KEV matches, not every matched CVE: a CVE
    # already in KEV means real attackers are already exploiting it in the
    # wild, a strictly stronger signal than "a GitHub PoC exists" — so KEV
    # entries don't need this extra lookup. This is meant to catch the case
    # a CVE hasn't reached KEV yet but is already publicly exploitable,
    # which changes its real urgency. Bounded to keep this endpoint fast
    # and within GitHub's rate limit, not an unbounded per-CVE loop.
    poc_candidates = [m for m in matched if not m["in_kev"]][:3]
    for m in poc_candidates:
        m["poc_available"] = _check_github_poc_exists(m["cve_id"])

    return _ok({
        "tech_stack_queried": tech_stack,
        "total_matches":      len(matched),
        "critical_count":     len(critical),
        "summary": (
            f"{len(critical)} CRITICAL CVEs actively targeting your stack (KEV/ransomware-linked)"
            if critical else
            f"{len(matched)} elevated-risk CVEs found for your tech stack"
            if matched else
            "No high-risk CVEs found matching your declared tech stack"
        ),
        "critical_cves": critical[:10],
        "all_matches":   matched[:25],
    })


def _check_github_poc_exists(cve_id: str) -> bool | None:
    """Best-effort check for a public PoC/exploit repo on GitHub for a given
    CVE ID. Returns None (not False) on any lookup failure -- "unknown" is
    honest, "no PoC found" is a specific claim this shouldn't make if the
    API call itself didn't succeed."""
    if not cve_id:
        return None
    try:
        raw = secrets_client.get_secret_value(SecretId=GITHUB_SECRET_NAME)["SecretString"].strip()
        token = json.loads(raw).get("token", raw) if raw.startswith("{") else raw
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "RelayShield-PocCheck/1.0",
        }
        req = urllib.request.Request(
            f"{GITHUB_SEARCH_URL}?q={urllib.parse.quote(cve_id)}+exploit+poc&per_page=1",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = json.loads(resp.read())
        return int(body.get("total_count", 0)) > 0
    except Exception as exc:
        logger.warning("GitHub PoC check failed cve=%s: %s", cve_id, exc)
        return None


# ---------------------------------------------------------------------------
# Router / Lambda handler
# ---------------------------------------------------------------------------

def handle_account_info(params: dict, api_key_record: dict | None = None) -> dict:
    if not api_key_record:
        return _err("Valid API key required", 401)
    return _ok({
        "plan":             api_key_record.get("plan", "personal"),
        "intel_access":     bool(api_key_record.get("intel_access", False)),
        "calls_this_month": int(api_key_record.get("monthly_calls", 0)),
        "customer_id":      api_key_record.get("stripe_customer_id", ""),
        "email":            api_key_record.get("email", ""),
        "active":           bool(api_key_record.get("active", True)),
    })


def handle_approval_security(params: dict) -> dict:
    """GoPlus spender contract risk check.
    NOTE: GoPlus approval_security checks whether a SPENDER CONTRACT is risky,
    not the list of approvals a wallet has granted. Wallet approval scanning is
    done client-side via Alchemy eth_getLogs; this endpoint validates each spender.
    """
    spender  = (params.get("address") or params.get("spender") or "").strip().lower()
    chain_id = str(params.get("chain_id") or "1").strip()
    if not spender or not re.match(r"^0x[0-9a-fA-F]{40}$", spender):
        return _err("address/spender must be a valid EVM address (0x + 40 hex chars)")
    try:
        url = f"https://api.gopluslabs.io/api/v1/approval_security/{chain_id}?contract_addresses={spender}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        info = (data.get("result") or {}).get(spender) or {}
        is_malicious   = bool(info.get("malicious_behavior") or info.get("doubt_list"))
        is_trusted     = bool(info.get("trust_list"))
        risk = "CRITICAL" if is_malicious else "LOW" if is_trusted else "MEDIUM"
        return _ok({
            "spender":       spender,
            "spender_name":  info.get("tag") or info.get("contract_name") or "",
            "chain_id":      chain_id,
            "risk":          risk,
            "is_trusted":    is_trusted,
            "is_malicious":  is_malicious,
            "is_open_source":bool(int(info.get("is_open_source", 0) or 0)),
            "malicious_behavior": info.get("malicious_behavior", []),
        })
    except Exception as exc:
        return _err(f"spender risk check failed: {exc}", 502)


def _defillama_lookup(domain: str) -> dict:
    """Match a domain against DeFiLlama protocol list. Returns metadata dict or {}."""
    try:
        req = urllib.request.Request(
            "https://api.llama.fi/protocols",
            headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            protocols = json.loads(resp.read())

        # Strip subpath — kamino.com/earn/lend → kamino.com
        base_domain = domain.split("/")[0].removeprefix("www.")

        best = None
        for p in protocols:
            proto_url = (p.get("url") or "").lower().replace("https://", "").replace("http://", "").removeprefix("www.").rstrip("/")
            proto_name = (p.get("name") or "").lower()
            slug       = (p.get("slug") or "").lower()
            if proto_url and (base_domain == proto_url or base_domain.endswith("." + proto_url)):
                best = p
                break
            # fuzzy: domain root word appears in name/slug (e.g. "kamino" in "kamino-lend")
            root = base_domain.split(".")[0]
            if len(root) >= 4 and (root in proto_name or root in slug):
                if best is None or (p.get("tvl") or 0) > (best.get("tvl") or 0):
                    best = p

        if not best:
            return {}

        tvl = best.get("tvl") or 0
        if isinstance(tvl, list):   # historical array — take last entry
            tvl = tvl[-1].get("totalLiquidityUSD", 0) if tvl else 0

        return {
            "name":      best.get("name", ""),
            "category":  best.get("category", ""),
            "chains":    best.get("chains", []),
            "tvl_usd":   round(float(tvl), 0) if tvl else None,
            "audits":    int(best.get("audits") or 0),
            "audit_links": best.get("audit_links") or [],
            "twitter":   best.get("twitter", ""),
            "url":       best.get("url", ""),
            "source":    "defillama",
        }
    except Exception as exc:
        logger.warning("DeFiLlama lookup failed domain=%s: %s", domain, exc)
        return {}


def handle_dapp_security(params: dict) -> dict:
    """dApp security — phishing check + DeFiLlama protocol enrichment (TVL, audits, chains, category)."""
    raw_url = (params.get("url") or "").strip().lower().replace("https://", "").replace("http://", "")
    if not raw_url:
        return _err("url is required")

    # ── GoPlus phishing check ─────────────────────────────────────────────────
    phishing, trust_list, risk_flags, gp_risk_score = False, False, [], 0
    try:
        encoded = urllib.parse.quote(f"https://{raw_url}", safe="")
        gp_url  = f"https://api.gopluslabs.io/api/v1/dapp_security?url={encoded}"
        req     = urllib.request.Request(gp_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        r = data.get("result") or {}
        gp_risk_score = int(r.get("risk_level", 0) or 0)
        phishing      = bool(int(r.get("phishing_site", 0) or 0))
        trust_list    = bool(int(r.get("trust_list", 0) or 0))
        risk_flags    = r.get("risk_items", []) or []
    except Exception as exc:
        logger.warning("GoPlus dApp check failed url=%s: %s", raw_url, exc)

    # ── DeFiLlama protocol enrichment ────────────────────────────────────────
    llama = _defillama_lookup(raw_url)

    # Risk level: GoPlus phishing/score is authoritative; DeFiLlama presence lowers uncertainty
    if phishing or gp_risk_score >= 3:
        risk_level = "CRITICAL"
    elif gp_risk_score >= 2:
        risk_level = "HIGH"
    elif gp_risk_score >= 1 or risk_flags:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # Open source: DeFiLlama audit_links are proof of audited open-source code
    is_open_source = bool(llama.get("audit_links")) or bool(llama.get("audits"))

    logger.info("dapp-security url=%s risk=%s llama=%s tvl=%s", raw_url, risk_level, llama.get("name"), llama.get("tvl_usd"))
    return _ok({
        "url":          raw_url,
        "risk_level":   risk_level,
        "phishing":     phishing,
        "trust_list":   trust_list,
        "risk_flags":   risk_flags,
        "is_open_source": is_open_source,
        "defillama":    llama or None,
    })


def _nft_slug_variants(raw: str) -> list[str]:
    """Return slug variants to try: lowercase, underscores, hyphens, no-spaces."""
    s = raw.strip().lower()
    under  = re.sub(r"[\s\-]+", "_", s)
    hyphen = re.sub(r"[\s_]+",  "-", s)
    nospace = re.sub(r"\s+", "", s)
    seen, out = set(), []
    for v in [s, under, hyphen, nospace]:
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out


def _nft_risk(floor: float, listed: int, avg_24h: float) -> tuple[str, list[str]]:
    flags: list[str] = []
    if floor == 0:
        flags.append("zero floor price — no active buyers")
    if listed == 0:
        flags.append("no active listings — possible rug or abandoned collection")
    elif avg_24h > 0 and avg_24h < floor * 0.7:
        flags.append("avg sale price well below floor — possible distress selling")
    level = "CRITICAL" if floor == 0 and listed == 0 else \
            "HIGH"     if len(flags) >= 2 else \
            "MEDIUM"   if flags else "LOW"
    return level, flags


def handle_nft_floor(params: dict) -> dict:
    """NFT collection floor — auto-routes slug to OpenSea (EVM) or Magic Eden (Solana).
    Accepts human-readable slugs for both: 'boredapeyachtclub', 'mad_lads', 'okay-bears'.
    Also accepts 0x contract addresses for EVM or base58 mint for Solana (falls through to
    appropriate marketplace).
    """
    raw = (params.get("symbol") or "").strip()
    if not raw:
        return _err("symbol is required — use a collection slug (e.g. boredapeyachtclub, mad_lads) "
                    "or a contract address.")

    is_evm_contract = bool(re.match(r"^0x[0-9a-fA-F]{40}$", raw))
    # Solana base58 mint addresses are 32-44 chars with no 0x; slugs are typically shorter
    # but we let Magic Eden be the arbiter — if it 404s, fall through to OpenSea
    slugs = _nft_slug_variants(raw)

    # ── OpenSea (EVM — ETH, Polygon, Base, etc.) ────────────────────────────
    def _try_opensea(slug: str) -> dict | None:
        try:
            url  = f"https://api.opensea.io/api/v2/collections/{slug}/stats"
            req  = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            total     = data.get("total") or {}
            intervals = data.get("intervals") or []
            day       = next((i for i in intervals if i.get("interval") == "one_day"), {})
            floor_eth = float(total.get("floor_price") or 0)
            symbol    = str(total.get("floor_price_symbol") or "ETH").upper()
            vol_all   = float(total.get("volume") or 0)
            vol_24h   = float(day.get("volume") or 0)
            sales_24h = int(day.get("sales") or 0)
            if floor_eth == 0 and vol_all == 0:
                return None  # likely 404 or empty slug
            risk_level, risk_flags = _nft_risk(floor_eth, sales_24h, 0)
            return {
                "symbol":       slug,
                "floor":        round(floor_eth, 4),
                "floor_symbol": symbol,
                "volume_24h":   round(vol_24h, 4),
                "sales_24h":    sales_24h,
                "volume_all":   round(vol_all, 2),
                "risk_level":   risk_level,
                "risk_flags":   risk_flags,
                "chain":        "evm",
                "marketplace":  "opensea",
            }
        except Exception:
            return None

    # ── Magic Eden (Solana) ──────────────────────────────────────────────────
    def _try_magic_eden(slug: str) -> dict | None:
        try:
            url = f"https://api-mainnet.magiceden.dev/v2/collections/{slug}/stats"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            # Treat as not-found if both floor and listed are zero/missing (ETH collection on Solana ME)
            floor_raw  = data.get("floorPrice")
            listed_raw = data.get("listedCount")
            if not data or (not floor_raw and not listed_raw):
                return None
            floor   = float(data.get("floorPrice",   0) or 0) / 1e9
            vol_all = float(data.get("volumeAll",     0) or 0) / 1e9
            listed  = int(data.get("listedCount",     0) or 0)
            avg_24h = float(data.get("avgPrice24hr",  0) or 0) / 1e9
            risk_level, risk_flags = _nft_risk(floor, listed, avg_24h)
            return {
                "symbol":       slug,
                "floor":        round(floor, 4),
                "floor_symbol": "SOL",
                "volume_24h":   round(avg_24h * listed, 4),
                "listed":       listed,
                "avg_24h":      round(avg_24h, 4),
                "volume_all":   round(vol_all, 2),
                "risk_level":   risk_level,
                "risk_flags":   risk_flags,
                "chain":        "solana",
                "marketplace":  "magic_eden",
            }
        except Exception:
            return None

    # Strategy: for EVM contracts try OpenSea directly; for slugs try both,
    # preferring Solana (Magic Eden) first since it was the original behaviour,
    # then fall back to OpenSea if Magic Eden misses.
    if is_evm_contract:
        # Contract address — OpenSea only (Magic Eden doesn't index by EVM address here)
        for slug in slugs:
            result = _try_opensea(slug)
            if result:
                logger.info("nft-floor OpenSea contract=%s floor=%s", slug, result.get("floor"))
                return _ok(result)
    else:
        # Slug — try Magic Eden first, then OpenSea
        for slug in slugs:
            result = _try_magic_eden(slug)
            if result:
                logger.info("nft-floor MagicEden slug=%s floor=%s SOL", slug, result.get("floor"))
                return _ok(result)
        for slug in slugs:
            result = _try_opensea(slug)
            if result:
                logger.info("nft-floor OpenSea slug=%s floor=%s ETH", slug, result.get("floor"))
                return _ok(result)

    return _err(
        f"Collection '{raw}' not found on Magic Eden (Solana) or OpenSea (EVM). "
        "Try the exact marketplace slug — e.g. 'boredapeyachtclub', 'mad_lads', 'pudgypenguins'.",
        404,
    )


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/ton-address
# ---------------------------------------------------------------------------
# Checks a TON address or token contract. Auto-detects wallet vs token:
# - If DexScreener has market data → returns token info (name, price, liquidity)
# - Otherwise → TON Center wallet check (balance, tx count, scam flag)

_TON_RAW_ADDR_RE      = re.compile(r"^-?\d+:[0-9a-fA-F]{64}$")
_TON_FRIENDLY_ADDR_RE = re.compile(r"^[A-Za-z0-9_-]{48}$")


def _is_valid_ton_address(addr: str) -> bool:
    return bool(_TON_RAW_ADDR_RE.match(addr) or _TON_FRIENDLY_ADDR_RE.match(addr))


def handle_ton_address(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not _is_valid_ton_address(address):
        # Most common case: an EVM address (0x + 40 hex) pasted into the TON field —
        # TON raw addresses need 64 hex chars, friendly addresses are 48-char base64url.
        return _err("Not a valid TON address — expected raw format (0:...) or friendly format (EQ.../UQ...)", 400)

    # ── DexScreener: check if this is a known TON token ─────────────────────
    token_meta = {}
    try:
        # Search by address — DexScreener resolves canonical form
        ds_url = f"https://api.dexscreener.com/latest/dex/search?q={urllib.parse.quote(address)}"
        ds_req = urllib.request.Request(ds_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(ds_req, timeout=8) as ds_resp:
            ds_data = json.loads(ds_resp.read())
        pairs = ds_data.get("pairs") or []
        ton_pairs = [p for p in pairs if "ton" in (p.get("chainId") or "").lower()]
        if ton_pairs:
            best = ton_pairs[0]
            base = best.get("baseToken", {})
            token_meta = {
                "token_name":    base.get("name", ""),
                "token_symbol":  base.get("symbol", ""),
                "address":       base.get("address", address),
                "price_usd":     best.get("priceUsd"),
                "liquidity_usd": (best.get("liquidity") or {}).get("usd"),
                "volume_24h":    (best.get("volume") or {}).get("h24"),
                "dex":           best.get("dexId", ""),
                "chain":         "ton",
                "source":        "dexscreener",
            }
    except Exception as exc:
        logger.warning("DexScreener TON lookup failed address=%s: %s", address, exc)

    # If it's a known token, return token data directly (no wallet check needed)
    if token_meta:
        logger.info("ton-address token=%s price=%s", token_meta.get("token_symbol"), token_meta.get("price_usd"))
        return _ok({
            "address":      address,
            "type":         "token",
            "risk_level":   "LOW",
            "risk_flags":   [],
            "token":        token_meta,
        })

    # ── TON Center wallet check ───────────────────────────────────────────────
    try:
        tc_url = f"https://toncenter.com/api/v2/getAddressInformation?address={urllib.parse.quote(address)}"
        tc_req = urllib.request.Request(tc_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(tc_req, timeout=8) as tc_resp:
            tc_data = json.loads(tc_resp.read())
        if not tc_data.get("ok"):
            return _err("TON address not found", 404)
        result = tc_data.get("result", {})
        balance_ton = round(int(result.get("balance", 0) or 0) / 1e9, 4)
        state       = result.get("state", "")
    except Exception as exc:
        logger.error("TON Center failed address=%s: %s", address, exc)
        return _err("TON address lookup failed — upstream error", 502)

    # TON API scam check
    risk_flags = []
    try:
        ton_url = TONAPI_ACCOUNTS_URL.format(address=urllib.parse.quote(address, safe="-_="))
        ton_req = urllib.request.Request(ton_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(ton_req, timeout=6) as ton_resp:
            ton_data = json.loads(ton_resp.read())
        if ton_data.get("is_scam"):
            risk_flags.append("flagged as scam in TON community database")
    except Exception:
        pass

    if state == "uninitialized":
        risk_flags.append("uninitialized contract — proceed with caution")

    risk_level = "CRITICAL" if any("scam" in f for f in risk_flags) else "MEDIUM" if risk_flags else "LOW"
    logger.info("ton-address wallet=%s balance=%.4f risk=%s", address, balance_ton, risk_level)
    return _ok({
        "address":     address,
        "type":        "wallet",
        "balance_ton": balance_ton,
        "state":       state,
        "risk_level":  risk_level,
        "risk_flags":  risk_flags,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/xrp-address
# ---------------------------------------------------------------------------
# Checks an XRP Ledger address — balance, tx activity, and fraud/scam flags.
# Single data source (XRPSCAN, free public API, no key) rather than a
# separate XRPL JSON-RPC call — their account endpoint already returns
# balance plus an "advisory" field populated for accounts reported/flagged
# for fraud (e.g. via Chainabuse), which is the fraud-signal source found
# 2026-07-04 (comparable to BitcoinAbuse for BTC — no equivalently mature
# scam-address database exists for XRP yet, so this is the best available).

_XRP_ADDR_RE = re.compile(r"^r[1-9A-HJ-NP-Za-km-z]{24,34}$")


def handle_xrp_address(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not _XRP_ADDR_RE.match(address):
        return _err("Not a valid XRP Ledger address — expected base58 starting with 'r' (25-35 chars)")

    try:
        url = f"https://api.xrpscan.com/api/v1/account/{urllib.parse.quote(address)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _err("XRP address not found", 404)
        logger.error("XRPSCAN lookup failed address=%s: %s", address, exc)
        return _err("XRP address lookup failed — upstream error", 502)
    except Exception as exc:
        logger.error("XRPSCAN lookup failed address=%s: %s", address, exc)
        return _err("XRP address lookup failed — upstream error", 502)

    if data.get("error"):
        return _err("XRP address not found", 404)

    balance_xrp = float(data.get("xrpBalance", 0) or 0)
    advisory    = data.get("advisory")

    risk_flags = []
    if advisory:
        note = advisory.get("note") if isinstance(advisory, dict) else str(advisory)
        risk_flags.append(f"flagged: {note or 'fraud/scam advisory on record'}")

    risk_level = "CRITICAL" if risk_flags else "LOW"
    logger.info("xrp-address wallet=%s balance=%.4f risk=%s", address, balance_xrp, risk_level)
    return _ok({
        "address":     address,
        "type":        "wallet",
        "balance_xrp": round(balance_xrp, 6),
        "owner_count": data.get("ownerCount", 0),
        "risk_level":  risk_level,
        "risk_flags":  risk_flags,
    })


PUSH_TOKENS_TABLE = "relayshield_push_tokens"

def handle_register_push(params: dict, api_key_record: dict | None = None) -> dict:
    """Register an Expo push token with monitored wallet addresses for server-side alerts.
    wallet_addresses: list of {address, chain, label} dicts OR plain address strings.
    telegram_id: optional Telegram chat_id to also deliver alerts via bot.
    """
    push_token  = (params.get("push_token") or "").strip()
    wallets     = params.get("wallet_addresses") or []
    telegram_id = (params.get("telegram_id") or "").strip()
    if not push_token:
        return _err("push_token is required")
    user_id         = (api_key_record or {}).get("api_key", "anonymous")
    nft_collections = params.get("nft_collections") or []
    # Normalise wallets to {address, chain, label} regardless of input format
    normalised = []
    for w in wallets:
        if isinstance(w, str):
            normalised.append({"address": w, "chain": "solana", "label": ""})
        elif isinstance(w, dict) and w.get("address"):
            normalised.append({
                "address": w["address"],
                "chain":   w.get("chain", "solana"),
                "label":   w.get("label", ""),
            })
    try:
        # update_item (not put_item) — re-registration happens on every app
        # launch, and a full item replacement would wipe fields written by
        # other code paths (e.g. last_alert, set by _expo_push) that aren't
        # part of the registration payload.
        update_expr  = "SET user_id = :u, wallet_addresses = :w, nft_collections = :n, registered_at = :r, active = :a"
        expr_values  = {
            ":u": user_id,
            ":w": normalised,
            ":n": nft_collections,
            ":r": datetime.now(timezone.utc).isoformat(),
            ":a": True,
        }
        if telegram_id:
            update_expr += ", telegram_id = :t"
            expr_values[":t"] = telegram_id
        dynamodb.Table(PUSH_TOKENS_TABLE).update_item(
            Key={"push_token": push_token},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )

        # Auto-add EVM wallet addresses to the Alchemy Address Activity webhook
        # so real-time transaction alerts fire without manual dashboard updates
        evm_addrs = [w["address"] for w in normalised
                     if w.get("chain", "").lower() in ("evm", "ethereum", "base", "arbitrum", "polygon")]
        if evm_addrs:
            _alchemy_webhook_add_addresses(evm_addrs)

        # Auto-add Solana addresses to Helius webhook
        sol_addrs = [w["address"] for w in normalised
                     if w.get("chain", "").lower() in ("solana", "sol")]
        if sol_addrs:
            _helius_webhook_add_addresses(sol_addrs)

        return _ok({"registered": True, "wallets": len(normalised),
                    "nft_collections": len(nft_collections),
                    "telegram_linked": bool(telegram_id),
                    "webhook_addresses_added": len(evm_addrs) + len(sol_addrs)})
    except Exception as exc:
        return _err(f"push registration failed: {exc}", 500)


def _urlopen_with_retry(req: urllib.request.Request, timeout: int = 8, attempts: int = 3) -> dict:
    """Execute a urllib request with retries on transient failure (e.g. momentary 403/5xx
    from a webhook provider). Raises the last exception if all attempts fail."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def _alchemy_webhook_add_addresses(addresses: list[str]) -> None:
    """Add EVM addresses to the Alchemy Address Activity webhook via Notify API."""
    webhook_id = os.environ.get("ALCHEMY_WEBHOOK_ID", "")
    auth_token = os.environ.get("ALCHEMY_AUTH_TOKEN", "")
    if not webhook_id or not auth_token:
        logger.warning("ALCHEMY_WEBHOOK_ID or ALCHEMY_AUTH_TOKEN not set — skipping webhook registration")
        return
    payload = json.dumps({
        "webhook_id":        webhook_id,
        "addresses_to_add":  addresses,
        "addresses_to_remove": [],
    }).encode()
    req = urllib.request.Request(
        "https://dashboard.alchemy.com/api/update-webhook-addresses",
        data=payload, method="PATCH",
        headers={"Content-Type": "application/json", "X-Alchemy-Token": auth_token},
    )
    try:
        resp = _urlopen_with_retry(req)
        logger.info("Alchemy webhook updated: added %d EVM addresses, response=%s",
                    len(addresses), resp)
    except Exception as exc:
        logger.warning("Alchemy webhook address update failed after retries: %s", exc)


def _helius_webhook_add_addresses(addresses: list[str]) -> None:
    """Add Solana addresses to the Helius webhook via their API."""
    webhook_id = os.environ.get("HELIUS_WEBHOOK_ID", "")
    helius_key = HELIUS_API_KEY
    if not webhook_id or not helius_key:
        logger.warning("HELIUS_WEBHOOK_ID or HELIUS_API_KEY not set — skipping Helius webhook registration")
        return
    # Helius: PATCH /v0/webhooks/{id} to append account addresses
    url = f"https://api.helius.xyz/v0/webhooks/{webhook_id}?api-key={helius_key}"
    # First GET current webhook to read existing addresses
    try:
        get_req = urllib.request.Request(url, method="GET",
                                         headers={"Accept": "application/json"})
        current  = _urlopen_with_retry(get_req)
        existing = current.get("accountAddresses") or []
        merged   = list(set(existing + addresses))
        payload  = json.dumps({
            "webhookURL":       current.get("webhookURL", ""),
            "transactionTypes": current.get("transactionTypes", ["Any"]),
            "accountAddresses": merged,
            "webhookType":      current.get("webhookType", "enhanced"),
            "authHeader":       current.get("authHeader", ""),
        }).encode()
        put_req = urllib.request.Request(url, data=payload, method="PUT",
                                         headers={"Content-Type": "application/json"})
        _urlopen_with_retry(put_req)
        logger.info("Helius webhook updated: %d total addresses", len(merged))
    except Exception as exc:
        logger.warning("Helius webhook address update failed after retries: %s", exc)


def _expo_push(push_token: str, title: str, body: str, data: dict | None = None) -> None:
    """Fire-and-forget Expo push notification from within the API Lambda.
    Also persists the alert server-side so the app can fetch its last alert
    on mount/focus rather than depending solely on the OS notification-received
    event, which is unreliable across Android/FCM/Expo app-state combinations."""
    import urllib.request as _r
    payload = json.dumps({
        "to": push_token, "title": title, "body": body,
        "data": data or {}, "sound": "default", "priority": "high",
    }).encode()
    req = _r.Request(
        "https://exp.host/--/api/v2/push/send", data=payload, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with _r.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
        if (resp.get("data") or {}).get("status") == "error":
            logger.warning("Expo push error: %s", resp)
    except Exception as exc:
        logger.warning("Expo push failed: %s", exc)

    try:
        dynamodb.Table(PUSH_TOKENS_TABLE).update_item(
            Key={"push_token": push_token},
            UpdateExpression="SET last_alert = :a",
            ExpressionAttributeValues={":a": {
                "title": title, "body": body,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }},
        )
    except Exception as exc:
        logger.warning("last_alert persist failed for push_token=%s: %s", push_token[:24], exc)


def _find_push_token_for_address(address: str) -> list[dict]:
    """Return all push token records that monitor the given wallet address."""
    try:
        items = dynamodb.Table(PUSH_TOKENS_TABLE).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("active").eq(True),
        ).get("Items", [])
        return [
            rec for rec in items
            if any(
                (w if isinstance(w, str) else w.get("address", "")) == address
                for w in (rec.get("wallet_addresses") or [])
            )
        ]
    except Exception as exc:
        logger.warning("push token lookup failed: %s", exc)
        return []


def handle_alchemy_webhook(event: dict) -> dict:
    """POST /v1/app/webhook/alchemy
    Receives Alchemy Address Activity webhooks for monitored EVM wallets.
    Fires Expo push when a transaction involves a monitored address.
    Alchemy webhook secret verified via X-Alchemy-Signature header (HMAC-SHA256).
    """
    import hmac, hashlib
    raw_body = event.get("body") or ""
    # API Gateway preserves header casing as sent by the client (not lowercased),
    # so look up case-insensitively rather than assuming "x-alchemy-signature".
    headers_ci = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig      = headers_ci.get("x-alchemy-signature", "")
    secret   = os.environ.get("ALCHEMY_WEBHOOK_SECRET", "")
    if secret:
        expected = hmac.new(secret.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return {"statusCode": 403, "body": "invalid signature"}
    try:
        body = json.loads(raw_body)
    except Exception:
        return {"statusCode": 400, "body": "invalid JSON"}

    # Alchemy Address Activity payloads include the source network (e.g. "BASE_MAINNET")
    ALCHEMY_NETWORK_NAMES = {
        "BASE_MAINNET": "Base", "ETH_MAINNET": "Ethereum", "MATIC_MAINNET": "Polygon",
        "ARB_MAINNET": "Arbitrum", "OPT_MAINNET": "Optimism", "AVAX_MAINNET": "Avalanche",
        "BNB_MAINNET": "BNB Chain",
    }
    network_raw  = (body.get("event") or {}).get("network", "")
    network_name = ALCHEMY_NETWORK_NAMES.get(network_raw, network_raw.replace("_MAINNET", "").title() or "EVM")

    activities = (body.get("event") or {}).get("activity") or []
    for act in activities:
        to_addr   = (act.get("toAddress") or "").lower()
        from_addr = (act.get("fromAddress") or "").lower()
        value     = act.get("value") or 0
        asset     = act.get("asset", "ETH")
        category  = act.get("category", "")

        # Alert on incoming transfers to monitored addresses
        records = _find_push_token_for_address(to_addr)
        for rec in records:
            wallet_label = next(
                (w.get("label", "") for w in (rec.get("wallet_addresses") or [])
                 if isinstance(w, dict) and w.get("address", "").lower() == to_addr),
                ""
            )
            short_from = f"{from_addr[:6]}…{from_addr[-4:]}"
            _expo_push(
                rec["push_token"],
                "📥 Inbound transaction",
                f"{wallet_label or to_addr[:8]} ({network_name}): received {value} {asset} from {short_from}",
                {"wallet": to_addr, "from": from_addr, "alert_type": "inbound_tx",
                 "chain": "evm", "network": network_raw, "category": category},
            )

    return {"statusCode": 200, "body": json.dumps({"processed": len(activities)})}


def handle_helius_webhook(event: dict) -> dict:
    """POST /v1/app/webhook/helius
    Receives Helius enhanced transaction webhooks for monitored Solana wallets.
    Helius sends an Authorization header set in the webhook config.
    """
    # API Gateway preserves header casing as sent by the client (not lowercased),
    # so look up case-insensitively rather than assuming "authorization".
    headers_ci = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    auth   = headers_ci.get("authorization", "")
    secret = os.environ.get("HELIUS_WEBHOOK_SECRET", "")
    if secret and auth != f"Bearer {secret}":
        return {"statusCode": 403, "body": "invalid auth"}

    try:
        transactions = json.loads(event.get("body") or "[]")
        if isinstance(transactions, dict):
            transactions = [transactions]
    except Exception:
        return {"statusCode": 400, "body": "invalid JSON"}

    alerted = 0
    for tx in transactions:
        tx_type      = tx.get("type", "")
        fee_payer    = tx.get("feePayer", "")
        native_xfers = tx.get("nativeTransfers") or []
        token_xfers  = tx.get("tokenTransfers") or []

        for xfer in native_xfers:
            to_addr = xfer.get("toUserAccount", "")
            amount  = xfer.get("amount", 0) / 1e9   # lamports → SOL
            if amount < 0.001:
                continue
            records = _find_push_token_for_address(to_addr)
            for rec in records:
                wallet_label = next(
                    (w.get("label", "") for w in (rec.get("wallet_addresses") or [])
                     if isinstance(w, dict) and w.get("address", "") == to_addr),
                    ""
                )
                short_from = f"{fee_payer[:6]}…{fee_payer[-4:]}" if fee_payer else "unknown"
                _expo_push(
                    rec["push_token"],
                    "📥 SOL received",
                    f"{wallet_label or to_addr[:8]} (Solana): +{amount:.4f} SOL from {short_from}",
                    {"wallet": to_addr, "from": fee_payer, "alert_type": "inbound_sol",
                     "chain": "solana", "network": "solana", "amount_sol": str(amount)},
                )
                alerted += 1

        for xfer in token_xfers:
            to_addr   = xfer.get("toUserAccount", "")
            from_addr = xfer.get("fromUserAccount", "")
            mint      = xfer.get("mint", "")
            amount    = float(xfer.get("tokenAmount") or 0)
            if amount <= 0 or not to_addr:
                continue
            records = _find_push_token_for_address(to_addr)
            for rec in records:
                wallet_label = next(
                    (w.get("label", "") for w in (rec.get("wallet_addresses") or [])
                     if isinstance(w, dict) and w.get("address", "") == to_addr),
                    ""
                )
                short_from = f"{from_addr[:6]}…{from_addr[-4:]}" if from_addr else "unknown"
                _expo_push(
                    rec["push_token"],
                    "📥 Token received",
                    f"{wallet_label or to_addr[:8]} (Solana): +{amount} tokens (mint {mint[:8]}…) from {short_from}",
                    {"wallet": to_addr, "from": from_addr, "mint": mint, "alert_type": "inbound_token",
                     "chain": "solana", "network": "solana"},
                )
                alerted += 1

    return {"statusCode": 200, "body": json.dumps({"alerted": alerted})}


_SOLANA_MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def handle_solana_token_risk(params: dict) -> dict:
    """Rugcheck.xyz + DexScreener Solana token risk — mint authority, freeze authority, honeypot detection."""
    mint = (params.get("mint") or "").strip()
    if not mint:
        return _err("mint is required (Solana SPL token mint address)")
    if not _SOLANA_MINT_RE.match(mint):
        return _err("Not a valid Solana mint address — expected base58, 32-44 characters. Enter the token's contract/mint address, not its name or symbol.")

    # ── Rugcheck primary source ───────────────────────────────────────────────
    # Full /report (not /report/summary) — same risk data as summary, plus a
    # "verification" object with Jupiter's jup_verified/jup_strict flags. This
    # is a distinct signal from the lookalike-token check: lookalike catches
    # "same name as a different verified asset"; this catches "is this specific
    # token itself listed on a known verification registry at all."
    score, risk_names, critical_flags, rugcheck_ok = 0, [], [], False
    verification_status = "unverified"
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        score          = int(data.get("score", 0))
        risks          = data.get("risks", [])
        # Only surface danger-level flags as risk flags; warn-level alone is not HIGH
        critical_flags = [r.get("name", "") for r in risks if r.get("level") == "danger"]
        warn_flags     = [r.get("name", "") for r in risks if r.get("level") == "warn"]
        # "Mutable metadata" is near-universal on Solana — only surface if paired with other issues
        meaningful_warns = [f for f in warn_flags if f.lower() != "mutable metadata"]
        risk_names = critical_flags + meaningful_warns
        rugcheck_ok = True

        verification = data.get("verification") or {}
        if verification.get("jup_strict"):
            verification_status = "jupiter_strict"
        elif verification.get("jup_verified"):
            verification_status = "jupiter_verified"
    except Exception as exc:
        logger.warning("Rugcheck failed mint=%s: %s", mint, exc)

    # Risk level: danger flags or score ≥5000 → HIGH; score ≥2000 with meaningful warns → MEDIUM
    if critical_flags or score >= 5000:
        level = "HIGH"
    elif score >= 2000 and meaningful_warns:
        level = "MEDIUM"
    else:
        level = "LOW"

    # ── DexScreener fallback for token name/market data ──────────────────────
    dexscreener_meta = {}
    try:
        ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        ds_req = urllib.request.Request(ds_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(ds_req, timeout=8) as ds_resp:
            ds_data = json.loads(ds_resp.read())
        pairs = ds_data.get("pairs") or []
        sol_pairs = [p for p in pairs if p.get("chainId", "").lower() == "solana"] or pairs
        if sol_pairs:
            best  = sol_pairs[0]
            base  = best.get("baseToken", {})
            dexscreener_meta = {
                "token_name":    base.get("name", ""),
                "token_symbol":  base.get("symbol", ""),
                "price_usd":     best.get("priceUsd"),
                "liquidity_usd": (best.get("liquidity") or {}).get("usd"),
                "volume_24h":    (best.get("volume") or {}).get("h24"),
                "dex":           best.get("dexId", ""),
                "source":        "dexscreener",
            }
    except Exception as ds_exc:
        logger.warning("DexScreener Solana fallback failed mint=%s: %s", mint, ds_exc)

    # Neither source found anything — a valid-format mint that doesn't actually
    # exist, or isn't indexed. Absence of data is not the same as "verified
    # clean" — don't return risk_level: LOW here, that reads as a safety verdict.
    if not rugcheck_ok and not dexscreener_meta:
        return _ok({
            "mint":               mint,
            "risk_level":         "UNKNOWN",
            "risk_flags":         [],
            "verification_status": "unknown",
            "note":               "No data found for this mint on Rugcheck or DexScreener — it may not exist, or may be too new/unindexed. Absence of flags does not mean the token is safe; verify independently.",
        })

    token_name   = dexscreener_meta.get("token_name", "")
    token_symbol = dexscreener_meta.get("token_symbol", "")

    lookalike = _check_lookalike_token(token_symbol, mint)
    if lookalike:
        risk_names.append(
            f"name/symbol matches verified asset '{lookalike['verified_name']}' "
            f"(CoinGecko #{lookalike['market_cap_rank'] or '?'}) but this mint isn't its verified address — possible impersonation"
        )
        if level == "LOW":
            level = "MEDIUM"

    logger.info("solana-token-risk mint=%s name=%s risk=%s score=%d verified=%s", mint, token_name or "unknown", level, score, verification_status)
    return _ok({
        "mint":                mint,
        "token_name":          token_name,
        "token_symbol":        token_symbol,
        "risk_level":          level,
        "risk_score":          score,
        "risk_max":            10000,
        "risk_flags":          risk_names[:8],
        "dexscreener":         dexscreener_meta or None,
        "lookalike_check":     lookalike,
        "verification_status": verification_status,
        "source":              "rugcheck.xyz" if rugcheck_ok else "dexscreener",
    })


def handle_solana_address_risk(params: dict) -> dict:
    """SolanaFM address reputation — transaction risk, blacklist status."""
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    try:
        url = f"https://api.solana.fm/v0/accounts/{address}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        account = data.get("result", {}) or data
        # SolanaFM doesn't have a direct risk score — derive from account type
        risk_flags = []
        is_program = bool(account.get("executable", False))
        onchain_data = account.get("onChainAccountInfo", {}) or {}
        risk_level = "LOW"
        if not account and not onchain_data:
            risk_flags.append("address not found on-chain")
            risk_level = "MEDIUM"
        return _ok({
            "address":    address,
            "risk_level": risk_level,
            "is_program": is_program,
            "risk_flags": risk_flags,
            "source":     "solana.fm",
        })
    except Exception as exc:
        return _err(f"SolanaFM address check failed: {exc}", 502)


def handle_solana_nft_tensor(params: dict) -> dict:
    """Tensor NFT collection floor risk for Solana — alternative to Magic Eden."""
    slug = (params.get("slug") or "").strip().lower()
    if not slug:
        return _err("slug is required (Tensor collection slug)")
    try:
        url = f"https://api.tensor.so/graphql"
        query = json.dumps({"query": f'{{ allCollections(slugs: ["{slug}"]) {{ slug name statsV2 {{ floor1h floor24h volume24h numListed }} }} }}'})
        req = urllib.request.Request(url, data=query.encode(), headers={"Content-Type": "application/json", "User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        collections = (data.get("data") or {}).get("allCollections", [])
        if not collections:
            return _err(f"Collection '{slug}' not found on Tensor")
        coll  = collections[0]
        stats = coll.get("statsV2", {}) or {}
        floor_1h  = float(stats.get("floor1h", 0) or 0) / 1e9
        floor_24h = float(stats.get("floor24h", 0) or 0) / 1e9
        vol_24h   = float(stats.get("volume24h", 0) or 0) / 1e9
        listed    = int(stats.get("numListed", 0) or 0)
        risk_flags = []
        if floor_1h > 0 and floor_24h > 0 and floor_1h < floor_24h * 0.8:
            risk_flags.append(f"floor dropped {((1 - floor_1h/floor_24h)*100):.0f}% in 1 hour")
        if listed == 0:
            risk_flags.append("no active listings")
        level = "CRITICAL" if len(risk_flags) >= 2 else "HIGH" if risk_flags else "LOW"
        return _ok({
            "slug":       slug,
            "name":       coll.get("name", slug),
            "floor_sol":  round(floor_1h, 4) or round(floor_24h, 4),
            "floor_24h_sol": round(floor_24h, 4),
            "volume_24h_sol": round(vol_24h, 2),
            "listed":     listed,
            "risk_level": level,
            "risk_flags": risk_flags,
            "source":     "tensor.trade",
        })
    except Exception as exc:
        return _err(f"Tensor NFT check failed: {exc}", 502)


# ---------------------------------------------------------------------------
# Mobile app proxy — Alchemy + Helius (keys never leave the backend)
# ---------------------------------------------------------------------------

def handle_evm_rpc_proxy(event: dict) -> dict:
    """POST /v1/app/evm-rpc — proxy EVM JSON-RPC calls via Alchemy (ETH mainnet or Base).
    Body: {network?: "eth"|"base", ...json_rpc_payload}
    """
    import urllib.request as _req, json as _j
    if not ALCHEMY_API_KEY:
        return _err("Alchemy not configured", 503)
    try:
        body = _j.loads(event.get("body") or "{}")
    except Exception:
        return _err("invalid JSON", 400)

    network = body.pop("network", "eth")
    subdomain = "base-mainnet" if network == "base" else "eth-mainnet"
    url = f"https://{subdomain}.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
    payload = _j.dumps(body).encode()
    req = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=10) as resp:
            result = _j.loads(resp.read())
    except Exception as exc:
        logger.error("Alchemy EVM RPC proxy error: %s", exc)
        return _err("upstream RPC error", 502)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": _j.dumps(result),
    }


def handle_solana_rpc_proxy(event: dict) -> dict:
    """POST /v1/app/solana-rpc — proxy Solana JSON-RPC calls via Helius.
    Body: standard JSON-RPC payload {jsonrpc, method, params, id}.
    Requires valid RS API key (auth checked by caller).
    """
    import urllib.request as _req, json as _j
    if not HELIUS_API_KEY:
        return _err("Helius not configured", 503)
    try:
        body = _j.loads(event.get("body") or "{}")
    except Exception:
        return _err("invalid JSON", 400)

    import http.client as _http, ssl as _ssl
    payload = _j.dumps(body).encode()
    ctx = _ssl.create_default_context()
    try:
        conn = _http.HTTPSConnection("mainnet.helius-rpc.com", timeout=10, context=ctx)
        conn.request("POST", f"/?api-key={HELIUS_API_KEY}", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        result = _j.loads(resp.read())
        conn.close()
    except Exception as exc:
        logger.error("Helius RPC proxy error: %s", exc)
        return _err("upstream RPC error", 502)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": _j.dumps(result),
    }


def handle_helius_assets_proxy(event: dict) -> dict:
    """POST /v1/app/helius-assets — proxy Helius getAssetsByOwner for SPL portfolio valuation.
    Body: {owner_address: string}
    Requires valid RS API key.
    """
    import urllib.request as _req, json as _j
    if not HELIUS_API_KEY:
        return _err("Helius not configured", 503)
    try:
        body = _j.loads(event.get("body") or "{}")
    except Exception:
        return _err("invalid JSON", 400)

    owner = body.get("owner_address", "")
    if not owner:
        return _err("owner_address required", 400)

    url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    payload = _j.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": owner,
            "page": 1, "limit": 100,
            "displayOptions": {"showFungible": True, "showNativeBalance": True},
        },
    }).encode()
    req = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=10) as resp:
            result = _j.loads(resp.read())
    except Exception as exc:
        logger.error("Helius assets proxy error: %s", exc)
        return _err("upstream Helius error", 502)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": _j.dumps(result),
    }


def handle_wallet_inbound(params: dict) -> dict:
    """
    Return up to 20 recent inbound transaction senders for a wallet address.
    chain: "evm" | "solana" | "ton"
    Used by the mobile app's address-poisoning detector to scan tx history
    server-side (avoids exposing Alchemy/Helius keys on the client).
    Response: { senders: [{address, asset, value, hash}], tx_count: N }
    """
    address = (params.get("address") or "").strip()
    chain   = (params.get("chain") or "").lower()
    if not address:
        return _err("address is required")
    if chain not in ("evm", "solana", "ton"):
        return _err("chain must be evm, solana, or ton")

    senders: list[dict] = []

    # ── EVM via Alchemy ──────────────────────────────────────────────────────
    if chain == "evm":
        alchemy_key = os.environ.get("ALCHEMY_API_KEY", "")
        if not alchemy_key:
            return _err("Alchemy key not configured")
        try:
            payload = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [{
                    "toAddress": address,
                    "category": ["external", "erc20"],
                    "maxCount": "0x14",
                    "order": "desc",
                }],
            }).encode()
            req = urllib.request.Request(
                f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_key}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for tx in (data.get("result") or {}).get("transfers", []):
                sender = (tx.get("from") or "").lower()
                if sender:
                    senders.append({
                        "address": sender,
                        "asset":   tx.get("asset", ""),
                        "value":   str(tx.get("value", "")),
                        "hash":    tx.get("hash", ""),
                    })
        except Exception as exc:
            logger.warning("wallet-inbound EVM failed address=%s: %s", address, exc)
            return _err(f"EVM lookup failed: {exc}")

    # ── Solana via Helius RPC ────────────────────────────────────────────────
    elif chain == "solana":
        helius_key = os.environ.get("HELIUS_API_KEY", "")
        rpc_url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}" if helius_key \
                  else "https://api.mainnet-beta.solana.com"
        try:
            sig_payload = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 20}],
            }).encode()
            req = urllib.request.Request(
                rpc_url, data=sig_payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                sig_data = json.loads(resp.read())
            signatures = [s["signature"] for s in (sig_data.get("result") or [])]

            for sig in signatures:
                try:
                    tx_payload = json.dumps({
                        "jsonrpc": "2.0", "id": 1,
                        "method": "getTransaction",
                        "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
                    }).encode()
                    req2 = urllib.request.Request(
                        rpc_url, data=tx_payload,
                        headers={"Content-Type": "application/json"}, method="POST",
                    )
                    with urllib.request.urlopen(req2, timeout=10) as resp2:
                        tx_data = json.loads(resp2.read())
                    accounts = (tx_data.get("result") or {}).get("transaction", {}) \
                                                            .get("message", {}) \
                                                            .get("accountKeys", [])
                    sender = accounts[0] if accounts else ""
                    if sender and sender != address:
                        senders.append({"address": sender, "asset": "SOL", "value": "", "hash": sig})
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("wallet-inbound Solana failed address=%s: %s", address, exc)
            return _err(f"Solana lookup failed: {exc}")

    # ── TON via TON API v2 (tonapi.io — no key required for basic lookups) ──
    elif chain == "ton":
        try:
            # tonapi.io accepts both friendly (EQ.../UQ...) and raw (0:...) formats
            encoded = urllib.parse.quote(address, safe="")
            url = f"https://tonapi.io/v2/blockchain/accounts/{encoded}/transactions?limit=20"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for tx in (data.get("transactions") or []):
                # Inbound = has in_msg with a source
                in_msg = tx.get("in_msg") or {}
                sender = (in_msg.get("source") or {}).get("address", "")
                if not sender:
                    continue
                raw_value = in_msg.get("value", 0)
                try:
                    value_ton = f"{int(raw_value) / 1e9:.4f}"
                except Exception:
                    value_ton = ""
                senders.append({
                    "address": sender,
                    "asset":   "TON",
                    "value":   value_ton,
                    "hash":    tx.get("hash", ""),
                })
        except Exception as exc:
            logger.warning("wallet-inbound TON failed address=%s: %s", address, exc)
            return _err(f"TON lookup failed: {exc}")

    logger.info("wallet-inbound chain=%s address=%s senders=%d", chain, address[:12], len(senders))
    return _ok({"senders": senders, "tx_count": len(senders)})


ROUTES = {
    "/v1/breach":           handle_breach,
    "/v1/scan-url":         handle_scan_url,
    "/v1/scan-file":        handle_scan_file,
    "/v1/sim-swap":         handle_sim_swap,
    "/v1/domain":           handle_domain,
    "/v1/oauth-watchlist":  handle_oauth_watchlist,
    "/v1/scan-wallet":      handle_scan_wallet,       # legacy EVM-only
    "/v1/wallet-risk":      handle_wallet_risk,       # multi-chain EVM/Solana/TON
    "/v1/token-security":   handle_token_security,
    "/v1/nft-security":     handle_nft_security,
    "/v1/intel/telegram":   handle_intel_telegram,    # TI API — requires intel_access flag
    "/v1/intel/cve":        handle_intel_cve,         # CISA KEV lookup by CVE ID or keyword
    "/v1/intel/actor":      handle_intel_actor,       # TC: actor profile — TI subscription
    "/v1/intel/trending":   handle_intel_trending,    # RF: trending IOCs last 24hrs — TI subscription
    "/v1/account/info":     handle_account_info,
    "/v1/approval-security":    handle_approval_security,
    "/v1/dapp-security":        handle_dapp_security,
    "/v1/nft-floor":            handle_nft_floor,
    "/v1/solana/token-risk":    handle_solana_token_risk,
    "/v1/solana/address-risk":  handle_solana_address_risk,
    "/v1/solana/nft-tensor":    handle_solana_nft_tensor,
    "/v1/ton-address":          handle_ton_address,
    "/v1/xrp-address":          handle_xrp_address,
    "/v1/wallet-inbound":       handle_wallet_inbound,
    "/v1/app/register-push":        handle_register_push,
    "/v1/app/webhook/alchemy":      handle_alchemy_webhook,
    "/v1/app/webhook/helius":       handle_helius_webhook,
    "/v1/app/evm-rpc":              handle_evm_rpc_proxy,
    "/v1/app/solana-rpc":           handle_solana_rpc_proxy,
    "/v1/app/helius-assets":        handle_helius_assets_proxy,
}

PAYG_PATHS = set(PAYG_PRICE_UNITS.keys()) | {"/v1/payg/result/"}


# ---------------------------------------------------------------------------
# Machine-readable discovery surfaces — robots.txt, sitemap.xml, llms.txt,
# openapi.json (added 2026-07-30)
#
# All four are generated from the live route tables rather than hand-maintained,
# so the published surface cannot drift from what the API actually serves. That
# matters most for openapi.json: a spec that lies about an endpoint is worse for
# an agent than no spec at all.
# ---------------------------------------------------------------------------

PUBLIC_BASE_URL = "https://api.relayshield.net"

# Guides that should be indexed in their own right. Each is a real search query
# with buying intent, which a post buried in a blog feed does not capture.
_GUIDE_PAGES = [
    ("/guides/microsoft-sentinel", "Ingest RelayShield threat intelligence into Microsoft Sentinel"),
    ("/guides/elastic-security",   "Ingest RelayShield threat intelligence into Elastic Security"),
]


def _text_response(body: str, content_type: str, max_age: int = 3600) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": content_type, "Cache-Control": f"public, max-age={max_age}"},
        "body": body,
    }


def handle_robots_txt() -> dict:
    body = (
        "User-agent: *\n"
        "Allow: /developers\n"
        "Allow: /guides/\n"
        "Allow: /llms.txt\n"
        "Allow: /openapi.json\n"
        # Authenticated and machine-only surfaces. Disallowing them keeps crawl
        # budget on the pages that can actually convert, and keeps 401 bodies
        # out of search results.
        "Disallow: /v1/\n"
        "Disallow: /developer/\n"
        "Disallow: /marketplace/\n"
        "\n"
        f"Sitemap: {PUBLIC_BASE_URL}/sitemap.xml\n"
        # Cross-referenced so a crawler that finds either host discovers both.
        "Sitemap: https://blog.relayshield.net/sitemap.xml\n"
    )
    return _text_response(body, "text/plain; charset=utf-8", 86400)


def handle_sitemap_xml() -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # /docs added 2026-08-04. "<product> API documentation" is a search query
    # with buying intent, and an unlisted reference page is one nobody but a
    # reviewer we hand the link to will ever find.
    urls = [("/developers", "1.0"), ("/docs", "0.9")] + [(p, "0.8") for p, _t in _GUIDE_PAGES]
    entries = "".join(
        f"  <url><loc>{PUBLIC_BASE_URL}{loc}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>weekly</changefreq><priority>{pri}</priority></url>\n"
        for loc, pri in urls
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}"
        "</urlset>\n"
    )
    return _text_response(body, "application/xml; charset=utf-8", 86400)


def handle_llms_txt() -> dict:
    """https://llmstxt.org/ — a plain-text entry point for LLMs and coding agents."""
    lines = [
        "# RelayShield",
        "",
        "> Threat intelligence and identity-compromise APIs for developers and AI agents.",
        "> Breach exposure, infostealer logs, SIM-swap, domain lookalikes, LLM credential",
        "> exposure and MCP registry risk, over REST, MCP, STIX/TAXII 2.1, MISP and x402.",
        "",
        "Authentication: send your key as the `X-RS-API-KEY` header. Pay-as-you-go with no",
        "monthly minimum; `/v1/payg/*` endpoints accept x402 USDC payment with no API key.",
        "Get a key at https://api.relayshield.net/developers",
        "",
        "## Machine-readable",
        "",
        f"- [API reference]({PUBLIC_BASE_URL}/docs): every endpoint with its parameters, response attributes, errors and examples",
        f"- [OpenAPI specification]({PUBLIC_BASE_URL}/openapi.json): the same reference as OpenAPI 3.1 JSON, with per-call prices",
        f"- [Service discovery]({PUBLIC_BASE_URL}/): endpoint inventory as JSON",
        "",
        "## Threat intelligence feeds",
        "",
        f"- [STIX/TAXII 2.1]({PUBLIC_BASE_URL}/v1/intel/taxii/): TAXII 2.1 server, collection id `iocs`. Requires a TI subscription.",
        f"- [MISP REST]({PUBLIC_BASE_URL}/v1/intel/misp/): MISP-compatible `attributes/restSearch`. Requires a TI subscription.",
        "",
        "## Integration guides",
        "",
    ]
    lines += [f"- [{title}]({PUBLIC_BASE_URL}{loc})" for loc, title in _GUIDE_PAGES]
    lines += [
        "",
        "## Threat research",
        "",
        "- [Blog archive](https://blog.relayshield.net): threat research and integration write-ups",
        "- [RSS feed](https://blog.relayshield.net/rss.xml)",
        "- [Blog sitemap](https://blog.relayshield.net/sitemap.xml)",
    ]
    lines += [
        "",
        "## Endpoints",
        "",
    ]
    for path in sorted(PAYG_DESCRIPTIONS):
        name = path.rsplit("/", 1)[-1]
        price = PAYG_PRICE_UNITS.get(path)
        price_s = f" (${price / 1_000_000:.2f}/call)" if price else ""
        desc = " ".join(PAYG_DESCRIPTIONS[path].split())
        lines.append(f"- `POST /v1/metered/{name}`{price_s}: {desc}")
    lines.append("")
    return _text_response("\n".join(lines), "text/plain; charset=utf-8")


def handle_guide_page(slug: str) -> dict:
    guide = _GUIDE_HTML.get(slug)
    if not guide:
        return {"statusCode": 404, "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Not found</title></head>"
                        "<body><p>No such guide. See "
                        "<a href=\"https://api.relayshield.net/developers\">api.relayshield.net/developers</a>.</p>"
                        "</body></html>"}
    url = f"{PUBLIC_BASE_URL}/guides/{slug}"
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{guide['title']} — RelayShield</title>
<meta name="description" content="{guide['desc']}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:site_name" content="RelayShield">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{guide['title']}">
<meta property="og:description" content="{guide['desc']}">
<meta property="og:image" content="https://blog.relayshield.net/developers-og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{guide['title']}">
<meta name="twitter:description" content="{guide['desc']}">
<meta name="twitter:image" content="https://blog.relayshield.net/developers-og.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"TechArticle","headline":{json.dumps(guide['title'])},
"description":{json.dumps(guide['desc'])},"url":{json.dumps(url)},
"publisher":{{"@type":"Organization","name":"RelayShield","url":"https://relayshield.net"}},
"mainEntityOfPage":{json.dumps(url)}}}
</script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  :root{{--bg:#0d0f14;--surface:#161a23;--border:#242836;--accent:#6c63ff;--text:#e8eaf0;--muted:#8b91a8}}
  body{{background:var(--bg);color:var(--text);line-height:1.7;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
  .wrap{{max-width:820px;margin:0 auto;padding:2.5rem 1.5rem 5rem}}
  nav{{margin-bottom:2.5rem;font-size:.9rem}}
  nav a{{color:var(--accent);text-decoration:none;font-weight:600}}
  h1{{font-size:2.1rem;line-height:1.25;margin:0 0 1.5rem;font-weight:800}}
  h2{{font-size:1.4rem;margin:2.5rem 0 .9rem;font-weight:700}}
  h3{{font-size:1.1rem;margin:2rem 0 .7rem;font-weight:700}}
  p,ul,ol{{margin:0 0 1.1rem}} ul,ol{{padding-left:1.4rem}} li{{margin-bottom:.4rem}}
  a{{color:var(--accent)}}
  code{{background:var(--surface);border:1px solid var(--border);border-radius:5px;
        padding:.12rem .38rem;font-size:.88em;word-break:break-word}}
  pre{{background:var(--surface);border:1px solid var(--border);border-radius:9px;
       padding:1rem 1.1rem;overflow-x:auto;margin:0 0 1.3rem}}
  pre code{{background:none;border:none;padding:0;font-size:.85rem;line-height:1.6}}
  blockquote{{border-left:3px solid var(--accent);padding:.2rem 0 .2rem 1.1rem;
              margin:0 0 1.1rem;color:var(--muted)}}
  table{{width:100%;border-collapse:collapse;margin:0 0 1.4rem;font-size:.92rem;display:block;overflow-x:auto}}
  th,td{{border:1px solid var(--border);padding:.6rem .8rem;text-align:left}}
  th{{background:var(--surface);font-weight:700}}
  hr{{border:none;border-top:1px solid var(--border);margin:2.5rem 0}}
  footer{{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--border);
          color:var(--muted);font-size:.88rem}}
  .cta{{background:var(--surface);border:1px solid var(--accent);border-radius:10px;
        padding:1.3rem 1.5rem;margin:2.5rem 0 0}}
</style>
</head>
<body><div class="wrap">
<nav><a href="{PUBLIC_BASE_URL}/developers">&larr; RelayShield API</a></nav>
{guide['html']}
<div class="cta">
  <p style="margin:0 0 .5rem;font-weight:700">Need an API key?</p>
  <p style="margin:0;color:var(--muted)">Pay per call, no monthly minimum &mdash;
  <a href="{PUBLIC_BASE_URL}/developers">api.relayshield.net/developers</a></p>
</div>
<footer>RelayShield LLC &middot; <a href="https://relayshield.net">relayshield.net</a> &middot;
<a href="mailto:support@relayshield.net">support@relayshield.net</a></footer>
</div></body></html>"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600"},
        "body": body,
    }


def handle_openapi() -> dict:
    """Serve the full OpenAPI 3.1 document from relayshield_openapi_spec.

    Replaced the generated stub on 2026-08-04. The old version synthesised one
    operation per PAYG endpoint with an untyped `additionalProperties: true`
    body and an untyped `data` object, so the spec published prices and paths
    while documenting no parameters, no response attributes and no error
    handling -- exactly what Zapier's partner review asked for on 2026-08-03.

    It also emitted a `/v1/metered/<name>` twin for every PAYG path, and seven
    of those names (nft-security, scan-file, scan-url, scan-wallet,
    token-security, wallet-risk, wallet-screen-batch) have no metered route:
    they are subscription routes under bare `/v1/`. A client generated from the
    old spec called a documented endpoint and got `404 unknown metered
    endpoint`. Those paths are gone here; the metered list is now the routing
    table's real contents.
    """
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(relayshield_openapi_spec.build_spec(PUBLIC_BASE_URL)),
    }


def handle_api_docs() -> dict:
    """Rendered API reference at /docs -- Swagger UI over /openapi.json.

    A machine-readable spec alone does not answer "show me the documentation";
    a partner reviewer, like any developer evaluating the API, wants a page
    that lists each endpoint with its parameters, attributes and errors. This
    is that page, and it stays in step with the spec because it renders it
    rather than restating it.
    """
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
        "body": relayshield_openapi_spec.DOCS_HTML,
    }


# Rendered integration guides, embedded 2026-07-30. Served as their own indexed
# pages at /guides/<slug> rather than only as blog posts: "ingest threat intel
# into Sentinel" is a search query with buying intent and evergreen value, which
# a post buried in a reverse-chronological feed does not capture. Generated from
# the .md sources with build_blog.py's md_to_html, the same renderer the blog
# uses. Regenerate from source rather than editing the HTML here.
_GUIDE_HTML = {
"elastic-security": {
"desc": "Configure Elastic's Custom Threat Intelligence integration against RelayShield's TAXII 2.1 feed. Includes measured ECS field mappings and Indicator Match rule setup.",
"html": "<h1>Ingesting RelayShield Threat Intelligence into Elastic Security</h1>\n<p>RelayShield serves its IOC corpus over <strong>STIX 2.1 / TAXII 2.1</strong> and a <strong>MISP-compatible REST API</strong>. Elastic Security ingests both through integrations it already ships, so this is a configuration task, not a development one.</p>\n<p><strong>What you get:</strong> 4.6M+ indicators sourced from 83+ criminal Telegram marketplaces and 20 authoritative feeds, flowing into Elastic's <code>logs-ti_*</code> indices where they enrich alerts and power Indicator Match detection rules.</p>\n<p><strong>Requirements:</strong> a RelayShield API key with a Threat Intelligence subscription, and Elastic Stack 8.x or later (Elastic Cloud or self-managed) with Fleet and an Elastic Agent.</p>\n<blockquote>Every field name, integration name and mapping below was verified against a live Elasticsearch</blockquote>\n<blockquote>8.15 stack ingesting the production RelayShield feed. If you followed an earlier version of this</blockquote>\n<blockquote>guide, see the note at the end \u2014 the integration name and two of the rule mappings have changed.</blockquote>\n<hr>\n<h2>Option A \u2014 STIX/TAXII via Custom Threat Intelligence (recommended)</h2>\n<p>Use the <strong>Custom Threat Intelligence</strong> integration (package <code>ti_custom</code>), which has a built-in TAXII 2.1 mode. Elastic does not ship a generic \"TAXII\" integration; this is the one.</p>\n<h3>1. Confirm your key works</h3>\n<pre><code>curl -s https://api.relayshield.net/v1/intel/taxii/ \\\n  -H &quot;Authorization: Bearer YOUR_API_KEY&quot;</code></pre>\n<p>A valid key returns the TAXII discovery document. <code>X-RS-API-KEY: YOUR_API_KEY</code> also works and is equivalent \u2014 use whichever your tooling prefers. Without a valid key you get <code>401</code>, which is a useful way to confirm the endpoint is reachable before adding credentials.</p>\n<h3>2. Add the integration in Kibana</h3>\n<p><strong>Management \u2192 Integrations \u2192 Custom Threat Intelligence \u2192 Add</strong></p>\n<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody><tr><td>URL</td><td><code>https://api.relayshield.net/v1/intel/taxii/collections/iocs/objects/</code></td></tr><tr><td>Enable TAXII 2.1</td><td><strong>on</strong></td></tr><tr><td>API Key</td><td>your RelayShield API key</td></tr><tr><td>API Key Type</td><td><code>Bearer</code></td></tr><tr><td>Accept header value</td><td>leave default (<code>application/taxii+json;version=2.1</code>)</td></tr><tr><td>Interval</td><td><code>1h</code> to start; tighten only if your use case needs it</td></tr><tr><td>IOC Expiration Duration</td><td>leave default</td></tr></tbody></table>\n<p>The collection is part of the URL \u2014 there is no separate \"Collection ID\" field. The trailing slash is optional.</p>\n<p><strong>On API Key Type:</strong> the integration sends your key as <code>Authorization: &lt;API Key Type&gt; &lt;API Key&gt;</code>. <code>Bearer</code> is the default and works. It cannot send a custom header name, which is why the URL above is authenticated with <code>Authorization</code> rather than <code>X-RS-API-KEY</code>.</p>\n<p><strong>On IOC Expiration Duration:</strong> RelayShield emits <code>valid_until</code> on every indicator (90 days from the sighting), so expiry is handled for you regardless of what you set here.</p>\n<h3>3. Confirm data is arriving</h3>\n<p>In <strong>Discover</strong>, query the threat intel data stream:</p>\n<pre><code>data_stream.dataset : &quot;ti_custom.indicator&quot;</code></pre>\n<p>Indicators land with <code>threat.indicator.type</code> set to <code>ipv4-addr</code>, <code>domain-name</code>, <code>url</code>, <code>file</code> or <code>email-addr</code> depending on the IOC.</p>\n<hr>\n<h2>Option B \u2014 MISP-compatible REST API</h2>\n<p>If you already run Elastic's <strong>MISP</strong> integration, RelayShield can be added as an additional source rather than replacing your existing one.</p>\n<p><strong>Management \u2192 Integrations \u2192 MISP \u2192 Add</strong>, and enable the <strong>Threat Attributes</strong> data stream:</p>\n<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody><tr><td>URL</td><td><code>https://api.relayshield.net/v1/intel/misp</code></td></tr><tr><td>API Key / token</td><td>your RelayShield API key</td></tr><tr><td>Interval</td><td><code>1h</code></td></tr></tbody></table>\n<p>The integration appends <code>/attributes/restSearch</code> to that base URL and sends your key in the <code>Authorization</code> header \u2014 both are handled. Confirm ingestion with:</p>\n<pre><code>data_stream.dataset : &quot;ti_misp.threat_attributes&quot;</code></pre>\n<p>Attributes are returned with MISP types <code>ip-dst</code>, <code>domain</code>, <code>url</code>, <code>sha256</code> and <code>email-src</code>, which Elastic maps to the same <code>threat.indicator.type</code> values as Option A.</p>\n<hr>\n<h2>Using the data</h2>\n<h3>Enrichment</h3>\n<p>Once indicators are flowing, Elastic's built-in <strong>Threat Intel enrichment</strong> matches them against your existing logs automatically. No rule authoring needed \u2014 matches appear on the alert under <code>threat.enrichments</code>.</p>\n<h3>Indicator Match rule</h3>\n<p>For explicit detection, create a rule under <strong>Security \u2192 Rules \u2192 Create new rule \u2192 Indicator Match</strong>:</p>\n<table><thead><tr><th>Setting</th><th>Value</th></tr></thead><tbody><tr><td>Index patterns</td><td>your source logs (e.g. <code>logs-*</code>, <code>filebeat-*</code>)</td></tr><tr><td>Indicator index</td><td><code>logs-ti_*</code></td></tr><tr><td>Indicator mapping</td><td><code>destination.ip</code> \u2192 <code>threat.indicator.ip</code></td></tr><tr><td></td><td><code>source.ip</code> \u2192 <code>threat.indicator.ip</code></td></tr><tr><td></td><td><code>dns.question.name</code> \u2192 <code>threat.indicator.url.original</code></td></tr><tr><td></td><td><code>url.full</code> \u2192 <code>threat.indicator.url.original</code></td></tr><tr><td></td><td><code>file.hash.sha256</code> \u2192 <code>threat.indicator.file.hash.sha256</code></td></tr></tbody></table>\n<p><strong>Note on domain and URL indicators.</strong> Both land in <code>threat.indicator.url.original</code>. There is no <code>threat.indicator.url.domain</code> or <code>threat.indicator.url.full</code> field on these documents \u2014 mapping to either produces a rule that never matches and raises no error, so it looks configured while doing nothing. Values are stored as arrays, which Indicator Match handles natively but is worth knowing if you write your own queries.</p>\n<p>Set severity to match your triage process. Because RelayShield's corpus is sourced from criminal marketplaces rather than general reputation feeds, a match generally warrants investigation rather than informational logging.</p>\n<h3>A note on timing</h3>\n<p>RelayShield's Telegram-sourced indicators typically surface <strong>24 to 72 hours ahead</strong> of public feeds, because the pipeline collects from the marketplaces where credentials and infrastructure are sold rather than waiting for downstream aggregation. That lead time is the reason to run this alongside, not instead of, your existing feeds.</p>\n<hr>\n<h2>Troubleshooting</h2>\n<table><thead><tr><th>Symptom</th><th>Cause</th></tr></thead><tbody><tr><td><code>401 Unauthorized</code></td><td>Key is missing, wrong, or lacks a TI subscription. The TI endpoints require an active TI plan, separate from PAYG API access.</td></tr><tr><td><code>404</code> on <code>/v1/taxii/...</code></td><td>Wrong path \u2014 the prefix is <code>/v1/intel/taxii/</code>, not <code>/v1/taxii/</code>.</td></tr><tr><td>No \"TAXII\" integration in Kibana</td><td>Correct \u2014 Elastic has no generic TAXII integration. Use <strong>Custom Threat Intelligence</strong> and switch on Enable TAXII 2.1.</td></tr><tr><td>Integration added, no documents</td><td>Check the interval has elapsed, then confirm the URL includes the full collection path <code>/collections/iocs/objects/</code>.</td></tr><tr><td>Documents arrive with only <code>threat.indicator.name</code> and no type</td><td>An expiry field was missing and Elastic's pipeline aborted. RelayShield now emits <code>valid_until</code>, so update to the current feed.</td></tr><tr><td>Indicators arrive but the rule never matches</td><td>Almost always the domain/URL mapping. Both must point at <code>threat.indicator.url.original</code>.</td></tr></tbody></table>\n<hr>\n<h2>Changed from earlier versions of this guide</h2>\n<p>An earlier version named a \"Threat Intel TAXII 2.x\" integration, which does not exist in Elastic's package registry, and gave two Indicator Match mappings (<code>threat.indicator.url.domain</code> and <code>threat.indicator.url.full</code>) that match no field. If you configured from it, three changes are needed:</p>\n<p>1. Use <strong>Custom Threat Intelligence</strong> with Enable TAXII 2.1, not \"Threat Intel TAXII 2.x\". 2. Query <code>ti_custom.indicator</code>, not <code>ti_taxii.indicator</code>. 3. Point both the domain and URL mappings at <code>threat.indicator.url.original</code>.</p>\n<p>The MISP endpoint is now a real MISP-compatible REST surface at <code>/v1/intel/misp</code>; the earlier documented path returned 404.</p>\n<hr>\n<h2>Support</h2>\n<p><code>support@relayshield.net</code> \u2014 include the integration type (Custom Threat Intelligence or MISP) and the Kibana or Elastic Agent error text if there is one.</p>",
"title": "Ingest RelayShield Threat Intelligence into Elastic Security"
},
"microsoft-sentinel": {
"desc": "Configure Sentinel's Threat Intelligence TAXII connector against RelayShield's STIX 2.1 feed. Includes the ThreatIntelIndicators schema, ObservableKey mappings, analytics rules and hunting queries.",
"html": "<h1>Ingesting RelayShield Threat Intelligence into Microsoft Sentinel</h1>\n<p>RelayShield serves its IOC corpus over <strong>STIX 2.1 / TAXII 2.1</strong> and a <strong>MISP-compatible REST API</strong>. Microsoft Sentinel consumes both, so this is a configuration task rather than a development one.</p>\n<p><strong>What you get:</strong> 4.5M+ indicators sourced from 83+ criminal Telegram marketplaces and 20 authoritative feeds, landing in Sentinel's <code>ThreatIntelIndicators</code> table where they drive analytics rules, hunting queries and incident enrichment.</p>\n<p><strong>Requirements:</strong> a RelayShield API key with a Threat Intelligence subscription, and a Sentinel workspace with the <strong>Threat Intelligence</strong> solution installed from Content hub (Microsoft Sentinel Contributor at the resource group level).</p>\n<blockquote><strong>Read this first if you have used any earlier Sentinel threat-intel guide.</strong></blockquote>\n<blockquote>The <code>ThreatIntelligenceIndicator</code> table <strong>stopped receiving data on 31 July 2025 and retired on 31 May 2026</strong>.</blockquote>\n<blockquote>Every query, analytics rule, workbook and automation must target</blockquote>\n<blockquote><strong><code>ThreatIntelIndicators</code></strong> (and <code>ThreatIntelObjects</code> for actors and relationships). A rule still</blockquote>\n<blockquote>pointing at the legacy table matches nothing and raises no error \u2014 the worst failure mode a</blockquote>\n<blockquote>detection control has.</blockquote>\n<hr>\n<h2>Option A \u2014 STIX/TAXII (recommended)</h2>\n<h3>1. Confirm your key works</h3>\n<pre><code>curl -s -u &quot;YOUR_API_KEY:YOUR_API_KEY&quot; https://api.relayshield.net/v1/intel/taxii/</code></pre>\n<p>A valid key returns the TAXII discovery document. Without one you get <code>401</code>, which is a useful way to confirm the endpoint is reachable before adding credentials.</p>\n<blockquote><strong>Put the key in both the username and the password.</strong> Sentinel exposes Username and Password as</blockquote>\n<blockquote>separate optional fields. The OASIS reference TAXII client skips authentication entirely when the</blockquote>\n<blockquote>password is empty (<code>if user and password:</code>), which we confirmed against this feed: key-as-username</blockquote>\n<blockquote>with a blank password returns <code>401</code>, and it looks exactly like a bad key. We have not inspected</blockquote>\n<blockquote>Sentinel's own client, so this may not apply to it \u2014 but RelayShield accepts the key in either</blockquote>\n<blockquote>position, so filling both fields costs nothing and removes the failure mode either way.</blockquote>\n<h3>2. Add the Threat Intelligence - TAXII data connector</h3>\n<p><strong>Microsoft Sentinel \u2192 Data connectors \u2192 Threat Intelligence - TAXII \u2192 Open connector page</strong></p>\n<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody><tr><td>Friendly name</td><td><code>RelayShield</code></td></tr><tr><td>API root URL</td><td><code>https://api.relayshield.net/v1/intel/taxii/</code></td></tr><tr><td>Collection ID</td><td><code>iocs</code></td></tr><tr><td>Username</td><td>your RelayShield API key</td></tr><tr><td>Password</td><td>your RelayShield API key</td></tr><tr><td>Import indicators</td><td><strong>All available</strong></td></tr><tr><td>Polling frequency</td><td><strong>Once an hour</strong> to start</td></tr></tbody></table>\n<p>Select <strong>Add</strong>. Indicators begin arriving within a few minutes and appear under <strong>Threat intelligence</strong> in the Sentinel menu.</p>\n<p>The API root URL is also the discovery endpoint \u2014 RelayShield serves both resources at that one URL, so you can paste the same value wherever a provider asks for either.</p>\n<h3>3. Confirm indicators are landing</h3>\n<pre><code>ThreatIntelIndicators\n| where SourceSystem contains &quot;RelayShield&quot; or Data.external_references contains &quot;relayshield&quot;\n| where TimeGenerated &gt; ago(24h)\n| summarize Indicators = count() by ObservableKey\n| order by Indicators desc</code></pre>\n<p>You should see four <code>ObservableKey</code> values. In a representative 1,000-object sample of the live feed the split was:</p>\n<table><thead><tr><th>IOC type</th><th><code>ObservableKey</code></th><th>Share of sample</th></tr></thead><tbody><tr><td>IP address</td><td><code>ipv4-addr:value</code></td><td>440</td></tr><tr><td>Domain</td><td><code>domain-name:value</code></td><td>349</td></tr><tr><td>URL</td><td><code>url:value</code></td><td>173</td></tr><tr><td>SHA-256</td><td><code>file:hashes.'SHA-256'</code></td><td>38</td></tr></tbody></table>\n<p>If <code>ObservableKey</code> and <code>ObservableValue</code> come back <strong>empty</strong>, Sentinel could not parse the STIX pattern. That is worth reporting to support@relayshield.net \u2014 it should not happen against the current feed (see \"Changed from earlier versions\" below).</p>\n<hr>\n<h2>Option B \u2014 MISP via misp2sentinel</h2>\n<p>Sentinel has no first-party MISP connector. The community standard is <a href=\"https://github.com/cudeso/misp2sentinel\"><code>cudeso/misp2sentinel</code></a>, an Azure Function that reads a MISP instance with PyMISP and pushes indicators through Sentinel's Upload Indicators API.</p>\n<p>RelayShield exposes a MISP-compatible surface, so misp2sentinel can point at it directly with no MISP server of your own.</p>\n<p>In the misp2sentinel configuration:</p>\n<table><thead><tr><th>Setting</th><th>Value</th></tr></thead><tbody><tr><td><code>misp_domain</code></td><td><code>https://api.relayshield.net/v1/intel/misp/</code></td></tr><tr><td><code>misp_key</code></td><td>your RelayShield API key</td></tr><tr><td><code>misp_verifycert</code></td><td><code>True</code></td></tr></tbody></table>\n<blockquote><strong>The trailing slash on <code>misp_domain</code> is required.</strong> PyMISP joins paths with <code>urljoin</code>, which</blockquote>\n<blockquote>replaces the last segment when the base has no trailing slash \u2014 <code>/v1/intel/misp</code> silently becomes</blockquote>\n<blockquote><code>/v1/intel/servers/getVersion</code> and every call 404s.</blockquote>\n<p>Prefer Option A unless you are already running misp2sentinel. TAXII is a first-party connector with no function app to host, monitor or pay for.</p>\n<hr>\n<h2>Using the indicators</h2>\n<h3>Analytics rule: match feed IPs against firewall traffic</h3>\n<pre><code>let lookback = 1h;\nlet relayshield_ips =\n    ThreatIntelIndicators\n    | where TimeGenerated &gt; ago(14d)\n    | where ObservableKey == &quot;ipv4-addr:value&quot;\n    | summarize arg_max(TimeGenerated, *) by Id\n    | where IsDeleted == false\n    | project IndicatorValue = ObservableValue, Confidence, ThreatDescription = tostring(Data.description);\nCommonSecurityLog\n| where TimeGenerated &gt; ago(lookback)\n| join kind=inner relayshield_ips on $left.DestinationIP == $right.IndicatorValue\n| project TimeGenerated, SourceIP, DestinationIP, ThreatDescription, Confidence, DeviceVendor</code></pre>\n<p><code>summarize arg_max(TimeGenerated, *) by Id</code> followed by <code>where IsDeleted == false</code> is the pattern Microsoft's own examples use, and it matters here: the feed republishes every unexpired indicator on a 7\u201310 day cycle, so without it you count the same indicator many times.</p>\n<h3>Analytics rule: match feed domains against DNS</h3>\n<pre><code>let relayshield_domains =\n    ThreatIntelIndicators\n    | where TimeGenerated &gt; ago(14d)\n    | where ObservableKey == &quot;domain-name:value&quot;\n    | summarize arg_max(TimeGenerated, *) by Id\n    | where IsDeleted == false\n    | project IndicatorValue = ObservableValue, ThreatDescription = tostring(Data.description);\nDnsEvents\n| where TimeGenerated &gt; ago(1h)\n| join kind=inner relayshield_domains on $left.Name == $right.IndicatorValue\n| project TimeGenerated, Computer, ClientIP, Name, ThreatDescription</code></pre>\n<h3>Hunting query: which malware families is the feed seeing?</h3>\n<p>RelayShield tags each indicator with the family it was observed alongside, as a <code>malware:&lt;family&gt;</code> label.</p>\n<pre><code>ThreatIntelIndicators\n| where TimeGenerated &gt; ago(7d)\n| summarize arg_max(TimeGenerated, *) by Id\n| where IsDeleted == false\n| mv-expand Label = Data.labels\n| where tostring(Label) startswith &quot;malware:&quot;\n| extend Family = replace_string(tostring(Label), &quot;malware:&quot;, &quot;&quot;)\n| summarize Indicators = count() by Family\n| top 25 by Indicators</code></pre>\n<h3>Reading the legacy-shaped fields</h3>\n<p>If you are porting rules written against <code>ThreatIntelligenceIndicator</code>, this reconstructs the old column names from the new schema:</p>\n<pre><code>ThreatIntelIndicators\n| extend NetworkIP  = iff(ObservableKey == &quot;ipv4-addr:value&quot;,   ObservableValue, &quot;&quot;),\n         DomainName = iff(ObservableKey == &quot;domain-name:value&quot;, ObservableValue, &quot;&quot;),\n         Url        = iff(ObservableKey == &quot;url:value&quot;,         ObservableValue, &quot;&quot;),\n         FileHashValue = iff(ObservableKey has &quot;file:hashes&quot;,   ObservableValue, &quot;&quot;),\n         FileHashType  = iff(ObservableKey has &quot;SHA-256&quot;, &quot;SHA-256&quot;, &quot;&quot;)</code></pre>\n<hr>\n<h2>Cost note</h2>\n<p><code>ThreatIntelIndicators</code> is a billed Log Analytics table, and the feed republishes every unexpired indicator every 7\u201310 days. Before importing <strong>All available</strong>, consider whether your detection surface needs the full corpus. Two levers:</p>\n<ul>\n<li>Set the connector to import a narrower indicator group.</li>\n<li>Apply a workspace transformation to drop the <code>Data</code> column, which carries the full STIX object:</li>\n</ul>\n<p>``<code>kusto source | project-away Data </code>``</p>\n<p>The hunting queries above read <code>Data.labels</code> and <code>Data.description</code>, so drop it only if you do not need those.</p>\n<hr>\n<h2>Changed from earlier versions</h2>\n<p>Four defects were found and fixed in the RelayShield feed on <strong>2026-07-30</strong>, while preparing this guide, by running the OASIS reference TAXII client against production:</p>\n<p>1. The API Root resource omitted the required <code>versions</code> field, so a conformant TAXII client aborted before requesting anything. 2. <code>GET /{api-root}/collections/{id}/</code> returned 404. Clients fetch this before requesting objects, so object polling failed without ever reaching the objects endpoint. 3. The object envelope was served as <code>application/stix+json</code> rather than <code>application/taxii+json;version=2.1</code>. 4. SHA-256 patterns were emitted as <code>[file:hashes.SHA-256 = '...']</code>, which is <strong>invalid STIX 2.1 patterning</strong>. The hash key must be quoted. Sentinel derives <code>ObservableKey</code>/<code>ObservableValue</code> by parsing the pattern, so SHA-256 indicators would have arrived with both fields empty.</p>\n<p><strong>If you configured RelayShield in Sentinel before 2026-07-30</strong>, remove and re-add the connector so it re-polls from the start of the collection, and re-check any rule keyed on file hashes.</p>\n<h2>Verification status</h2>\n<p>Stated plainly, because a threat-intel guide that overstates its testing is worse than no guide:</p>\n<p><strong>Verified against live systems.</strong> Every RelayShield-side claim \u2014 the API root and collection URLs, the auth behaviour including the blank-password trap, the TAXII protocol walk end to end, the validity of every STIX pattern in a 1,000-object live sample, and the PyMISP handshake \u2014 was measured against the production feed with the OASIS <code>taxii2-client</code>, <code>stix2-patterns</code> validator, and PyMISP.</p>\n<p><strong>Derived, not measured.</strong> The <code>ObservableKey</code> values, table schema and KQL come from Microsoft's published <code>ThreatIntelIndicators</code> schema combined with the STIX object paths RelayShield is verified to emit. They have <strong>not</strong> been run through a live Sentinel workspace. The mapping is a straightforward correspondence and we have no reason to doubt it, but an equivalent assumption in an earlier Elastic guide turned out to be wrong in two places, so treat the KQL as needing a first-run check in your own workspace rather than as measured fact.</p>\n<hr>\n<p>Questions: <a href=\"mailto:support@relayshield.net\">support@relayshield.net</a> \u00b7 <a href=\"https://api.relayshield.net/developers\">api.relayshield.net/developers</a></p>",
"title": "Ingest RelayShield Threat Intelligence into Microsoft Sentinel"
}
}


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info("API request — method=%s path=%s", method, path)

    # AWS Marketplace fulfillment — forward to marketplace Lambda (GET or POST)
    if "/marketplace/fulfillment" in path:
        import boto3 as _boto3, json as _json
        lc = _boto3.client("lambda", region_name="us-east-1")
        resp = lc.invoke(
            FunctionName="relayshield-aws-marketplace",
            InvocationType="RequestResponse",
            Payload=_json.dumps(event).encode(),
        )
        return _json.loads(resp["Payload"].read())

    # Machine-discovery surfaces (added 2026-07-30). Nothing here existed, which
    # meant crawlers had no entry point and coding agents had no spec to read --
    # awkward for a product whose whole thesis is that agents discover and pay
    # for it, and whose LangChain placement is driven by install volume.
    if method in ("GET", "HEAD") and path in ("/robots.txt", "/robots.txt/"):
        return handle_robots_txt()
    if method in ("GET", "HEAD") and path in ("/sitemap.xml", "/sitemap.xml/"):
        return handle_sitemap_xml()
    if method in ("GET", "HEAD") and path in ("/llms.txt", "/llms.txt/"):
        return handle_llms_txt()
    if method in ("GET", "HEAD") and path in ("/openapi.json", "/openapi.json/", "/.well-known/openapi.json"):
        return handle_openapi()
    # Human-readable API reference. /docs is the conventional path and the one
    # a reviewer or developer guesses first; /api-docs is kept as an alias so a
    # link written either way resolves.
    if method in ("GET", "HEAD") and path in ("/docs", "/docs/", "/api-docs", "/api-docs/"):
        return handle_api_docs()
    if method in ("GET", "HEAD") and path.startswith("/guides/"):
        return handle_guide_page(path[len("/guides/"):].strip("/"))

    # Discovery — HEAD included since UptimeRobot and similar monitors probe with HEAD
    if method in ("GET", "HEAD") and path in ("/", "/v1", "/v1/"):
        return _ok({
            "service":  "RelayShield B2A API",
            "version":  "1.0",
            "subscription_endpoints": list(ROUTES.keys()) + ["GET /v1/result/{analysis_id}"],
            "metered_endpoints": list(STRIPE_METER_EVENTS.keys()),
            "metered_note": "Stripe card billing — pass RS API key as X-RS-API-KEY header.",
            "payg_endpoints": list(PAYG_PRICE_UNITS.keys()) + ["GET /v1/payg/result/{analysis_id}"],
            "payg_note": "x402 payment required — USDC on Base. No API key needed.",
        })

    # ── Last alert lookup — no auth required (push_token itself is the secret) ─
    # GET /v1/app/last-alert?push_token=ExponentPushToken[...]
    # Lets the app fetch its most recent alert as authoritative server state,
    # rather than depending on the OS notification-received event, which is
    # unreliable across Android/FCM/Expo app-state combinations.
    if method == "GET" and path in ("/v1/app/last-alert", "/v1/app/last-alert/"):
        qp    = event.get("queryStringParameters") or {}
        token = (qp.get("push_token") or "").strip()
        if not token:
            return _err("push_token is required")
        try:
            item = dynamodb.Table(PUSH_TOKENS_TABLE).get_item(Key={"push_token": token}).get("Item") or {}
            return _ok({"last_alert": item.get("last_alert")})
        except Exception as exc:
            logger.warning("last-alert lookup failed: %s", exc)
            return _ok({"last_alert": None})

    # ── CS Mobile latest-version check — no auth required (runs before onboarding) ─
    # GET /v1/app/cs-mobile-latest-version
    # Queries the on-chain Release NFT group under CS Mobile's App NFT via
    # Helius's DAS-compatible RPC to find the latest published version,
    # parsed from each release's "Crypto Shield vX.Y.Z" name. No caching --
    # this is a low-frequency, launch-time-only check for a small user base;
    # add a cache if usage grows enough for the RPC cost to matter.
    if method == "GET" and path in ("/v1/app/cs-mobile-latest-version", "/v1/app/cs-mobile-latest-version/"):
        if not HELIUS_API_KEY:
            return _err("Helius not configured", 503)
        import re as _re, http.client as _http, ssl as _ssl, json as _j

        def _rpc(method: str, params: dict) -> dict:
            ctx  = _ssl.create_default_context()
            conn = _http.HTTPSConnection("mainnet.helius-rpc.com", timeout=10, context=ctx)
            try:
                conn.request(
                    "POST", f"/?api-key={HELIUS_API_KEY}",
                    body=_j.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                return _j.loads(conn.getresponse().read())
            finally:
                conn.close()

        def _versions_from(items: list) -> list:
            out = []
            for item in items or []:
                name = ((item.get("content") or {}).get("metadata") or {}).get("name") or ""
                if not name.startswith(CS_MOBILE_RELEASE_PREFIX):
                    continue
                m = _re.search(r"v(\d+)\.(\d+)\.(\d+)", name)
                if m:
                    out.append(tuple(int(x) for x in m.groups()))
            return out

        try:
            # Primary: every release ever minted by this publisher, across app
            # records. Survives the 2026-08-01 package rename and any future one.
            versions, page = [], 1
            while page <= 5:  # 5 x 1000 releases is far beyond any real ceiling
                result = _rpc("getAssetsByAuthority", {
                    "authorityAddress": CS_MOBILE_PUBLISHER,
                    "page": page, "limit": 1000,
                })
                items = (result.get("result") or {}).get("items") or []
                versions.extend(_versions_from(items))
                if len(items) < 1000:
                    break
                page += 1

            # Fallback: the legacy App NFT collection group. Only reachable if the
            # authority lookup returns nothing (RPC shape change, publisher key
            # rotation) — never silently, since an empty result would otherwise
            # read to the client as "no update available".
            if not versions:
                logger.warning("cs-mobile-latest-version: authority lookup empty, falling back to app-NFT group")
                result = _rpc("getAssetsByGroup", {
                    "groupKey": "collection", "groupValue": CS_MOBILE_APP_NFT,
                    "page": 1, "limit": 1000,
                })
                versions = _versions_from((result.get("result") or {}).get("items") or [])

            if not versions:
                return _err("no releases found", 502)
            latest = max(versions)
            return _ok({"latest_version": f"{latest[0]}.{latest[1]}.{latest[2]}"})
        except Exception as exc:
            logger.warning("cs-mobile-latest-version lookup failed: %s", exc)
            return _err("upstream RPC error", 502)

    # ── App feedback submission — no auth required (push_token identifies device) ─
    # POST /v1/app/feedback  { push_token, rating: "up"|"down", comment?: string }
    # One record per device (update_item, not append) — the app only asks once.
    if method == "POST" and path in ("/v1/app/feedback", "/v1/app/feedback/"):
        params  = _body(event)
        token   = (params.get("push_token") or "").strip()
        rating  = (params.get("rating") or "").strip()
        comment = (params.get("comment") or "").strip()[:1000]
        if not token:
            return _err("push_token is required")
        if rating not in ("up", "down"):
            return _err("rating must be 'up' or 'down'")
        try:
            dynamodb.Table(PUSH_TOKENS_TABLE).update_item(
                Key={"push_token": token},
                UpdateExpression="SET feedback_rating = :r, feedback_comment = :c, feedback_at = :t",
                ExpressionAttributeValues={
                    ":r": rating,
                    ":c": comment,
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            return _ok({"received": True})
        except Exception as exc:
            logger.warning("feedback submission failed: %s", exc)
            return _err("feedback submission failed", 500)

    # ── Public badge endpoint — no auth required ──────────────────────────────
    # GET/HEAD /v1/badge?domain=example.com&style=flat|shield
    # Returns SVG image with risk level, color-coded, cacheable 1hr
    # HEAD must be accepted too -- uptime monitors (e.g. UptimeRobot) default to
    # HEAD requests, and this route falling through to the generic "unknown
    # endpoint" 404 for HEAD only is what made this look like a real outage.
    if method in ("GET", "HEAD") and path in ("/v1/badge", "/v1/badge/"):
        qp     = event.get("queryStringParameters") or {}
        domain = (qp.get("domain") or "").strip().lower().replace("https://","").replace("http://","").split("/")[0]
        style  = qp.get("style", "flat")   # flat | shield | compact

        if not domain:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "image/svg+xml", "Cache-Control": "no-cache"},
                "body": _badge_svg("unknown", "UNKNOWN", "#64748b", style),
            }

        # Pull cached score from DynamoDB or compute fast
        try:
            cached = _dynamodb_resource().Table("relayshield_badge_cache").get_item(Key={"domain": domain}).get("Item")
            if cached:
                score = int(cached.get("risk_score", 0))
                level = cached.get("risk_level", "LOW")
            else:
                # Run a lightweight identity risk score
                result = handle_identity_risk_score({"domain": domain})
                score  = result.get("risk_score", 0)
                level  = result.get("risk_level", "LOW")
                # Cache for 1 hour
                _dynamodb_resource().Table("relayshield_badge_cache").put_item(Item={
                    "domain": domain, "risk_score": score, "risk_level": level,
                    "cached_at": _now_iso(),
                    "ttl": int(__import__("time").time()) + 3600,
                })
        except Exception as exc:
            logger.error("Badge score fetch failed %s: %s", domain, exc)
            score, level = 0, "UNKNOWN"

        color = {"LOW": "#22c55e", "MEDIUM": "#facc15", "HIGH": "#f97316",
                 "CRITICAL": "#ef4444", "UNKNOWN": "#64748b"}.get(level, "#64748b")
        svg = _badge_svg(domain, level, color, style, score)
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "image/svg+xml",
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
            },
            "body": svg,
        }

    # TAXII 2.1 endpoints (GET, intel_access required)
    if path.startswith("/v1/intel/taxii"):
        headers    = event.get("headers") or {}
        api_key    = _intel_api_key(headers)
        key_record = _verify_rs_api_key(api_key) if api_key else None
        if not key_record or not key_record.get("intel_access"):
            return {"statusCode": 401, "headers": {"Content-Type": "application/taxii+json;version=2.1"},
                    "body": json.dumps({"title": "Unauthorized", "description": "TI subscription required. Pass your RS API key as X-RS-API-KEY."})}
        qp = event.get("queryStringParameters") or {}
        if path == "/v1/intel/taxii/" or path == "/v1/intel/taxii":
            return handle_taxii_discovery({}, key_record)
        if path in ("/v1/intel/taxii/collections/", "/v1/intel/taxii/collections"):
            return handle_taxii_collections({}, key_record)
        # Accept both collection ids. The collections endpoint advertised
        # "relayshield-iocs" while this router only ever matched "iocs", so any
        # conformant TAXII client (Elastic, OpenCTI, Anomali) that walks
        # discovery -> collections -> objects requested the advertised id and
        # got a 404. Fixed 2026-07-28: the advertised id is now "iocs" to match
        # what has always actually worked, and "relayshield-iocs" stays routed
        # so anyone who hand-configured the old advertised id keeps working.
        if (path.startswith("/v1/intel/taxii/collections/iocs/objects") or
                path.startswith("/v1/intel/taxii/collections/relayshield-iocs/objects")):
            return handle_taxii_objects({}, key_record, qp)
        # Single Collection resource, TAXII 2.1 s5.2. Must be matched AFTER the
        # /objects/ prefixes above, since both live under /collections/{id}/.
        _coll_prefix = "/v1/intel/taxii/collections/"
        if path.startswith(_coll_prefix):
            _cid = path[len(_coll_prefix):].strip("/")
            if _cid and "/" not in _cid:
                return handle_taxii_collection({}, key_record, _cid)
        return {"statusCode": 404, "headers": {"Content-Type": "application/taxii+json;version=2.1"},
                "body": json.dumps({"title": "Not Found"})}

    # MISP export (INTEL-6) — same TI subscription gating as TAXII
    if path.startswith("/v1/intel/misp"):
        headers    = event.get("headers") or {}
        api_key    = _intel_api_key(headers)
        key_record = _verify_rs_api_key(api_key) if api_key else None
        if not key_record or not key_record.get("intel_access"):
            return {"statusCode": 401, "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"errors": ["TI subscription required. Pass your RS API key as X-RS-API-KEY."]})}
        qp = event.get("queryStringParameters") or {}

        # MISP-compatible REST surface for Elastic's ti_misp integration, which
        # POSTs a JSON body here. Must accept a trailing slash too: customers
        # paste base URLs with and without one.
        if path.rstrip("/") in ("/v1/intel/misp/attributes/restSearch",):
            try:
                misp_body = json.loads(event.get("body") or "{}")
            except Exception:
                misp_body = {}
            if not isinstance(misp_body, dict):
                misp_body = {}
            return handle_misp_rest_search(key_record, misp_body)

        if path in ("/v1/intel/misp/event", "/v1/intel/misp/event/"):
            return handle_misp_event({}, key_record, qp)

        # MISP instance-identity endpoints required by PyMISP's constructor, and
        # therefore by misp2sentinel. See _misp_shim.
        _shim = _misp_shim("/" + path[len("/v1/intel/misp/"):].strip("/")) \
            if path.startswith("/v1/intel/misp/") else None
        if _shim:
            return _shim

        return {"statusCode": 404, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"errors": ["Not Found"]})}

    # Webhook configuration (RS API key verified inside handle_metered_request)
    if path == "/v1/webhook/configure":
        return handle_metered_request(path, method, event)

    # Stripe metered billing routes (RS API key verified inside Lambda)
    if path.startswith("/v1/metered/"):
        return handle_metered_request(path, method, event)

    # PAYG routes (x402 payment verified inside Lambda)
    if path.startswith("/v1/payg/"):
        return handle_payg_request(path, method, event)

    # Subscription: GET /v1/result/{analysis_id}
    if method == "GET" and path.startswith("/v1/result/"):
        analysis_id = path[len("/v1/result/"):]
        return handle_result(analysis_id)

    # rsscan org signal — unauthenticated by design, opt-in from the client.
    # This is the dev -> security-lead bridge: N distinct install ids at one org
    # domain is a qualified account, which PyPI download totals can never show.
    if method == "POST" and path == "/v1/telemetry/rsscan-install":
        return handle_rsscan_install(_body(event))

    # Shareable report links (INTEL-8) — public view, no auth
    if method == "GET" and path.startswith("/v1/r/"):
        report_id = path[len("/v1/r/"):]
        return handle_report_view(report_id)

    # Shareable report links (INTEL-8) — generation, gated to any active
    # (paying) API key — not restricted to intel_access, applies account-wide
    if method == "POST" and path == "/v1/report/share":
        headers    = event.get("headers") or {}
        api_key    = _header(headers, "X-RS-API-KEY") or _header(headers, "X-API-Key")
        key_record = _verify_rs_api_key(api_key) if api_key else None
        if not key_record:
            return _err("Active RS API key required. Pass it as X-RS-API-KEY.", 401)
        return handle_report_share(_body(event), key_record)

    # Subscription routes (API key enforced by API Gateway)
    handler = ROUTES.get(path)
    if not handler:
        return _err(f"unknown endpoint: {path}", 404)

    # Webhook verification: Helius (and some providers) send GET to confirm the endpoint is live
    if method == "GET" and path in ("/v1/app/webhook/alchemy", "/v1/app/webhook/helius"):
        return {"statusCode": 200, "headers": {"Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"}, "body": json.dumps({"ok": True})}

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    # Keyless scan calls are rate-limited per source IP. A valid key skips this
    # entirely, so paying subscribers and the CS Mobile app's linked users are
    # never counted — only genuinely unauthenticated traffic is.
    if path in KEYLESS_SCAN_ENDPOINTS:
        _scan_headers = event.get("headers") or {}
        _scan_key     = _header(_scan_headers, "X-RS-API-KEY") or _header(_scan_headers, "X-API-Key")
        if not (_scan_key and _verify_rs_api_key(_scan_key)):
            _source_ip = ((event.get("requestContext") or {}).get("identity") or {}).get("sourceIp") or ""
            if not _check_keyless_ip_quota(_source_ip):
                logger.warning("keyless scan quota exceeded path=%s ip=%s", path, _source_ip)
                return {
                    "statusCode": 429,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "ok": False,
                        "error": "Daily limit reached for unauthenticated scans. "
                                 "Link a Crypto Shield Pro subscription in Settings, or get an API key.",
                        "docs": "https://api.relayshield.net/developers",
                    }),
                }

    params = _body(event)
    try:
        if path in ("/v1/intel/telegram", "/v1/intel/cve", "/v1/intel/actor", "/v1/intel/trending", "/v1/account/info"):
            headers    = event.get("headers") or {}
            api_key    = _header(headers, "X-API-Key") or _header(headers, "X-RS-API-KEY")
            key_record = _verify_rs_api_key(api_key) if api_key else None
            qp         = event.get("queryStringParameters") or {}
            merged     = {**qp, **params}
            return handler(merged, api_key_record=key_record)
        if path in ("/v1/app/evm-rpc", "/v1/app/solana-rpc", "/v1/app/helius-assets"):
            return handler(event)
        # Webhook endpoints receive raw event (signature verified internally)
        if path in ("/v1/app/webhook/alchemy", "/v1/app/webhook/helius"):
            return handler(event)
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in %s: %s", path, exc)
        return _err("internal server error", 500)
