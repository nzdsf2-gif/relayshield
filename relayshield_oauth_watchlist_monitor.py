"""
RelayShield OAuth Supply Chain Watchlist Monitor Lambda

Triggered by EventBridge daily. Polls the HIBP Breaches API for newly indexed
breaches and cross-references against an internal watchlist of OAuth-capable
SaaS apps. When a watched app is newly breached, fires a WhatsApp alert to all
active RelayShield subscribers directing them to revoke OAuth access immediately.

This is the automated version of the Vercel/Context.ai attack scenario:
    Context.ai was breached → attacker took stored OAuth tokens →
    authenticated into Vercel employee's Google Workspace →
    accessed production infrastructure without ever touching credentials.

RelayShield catches this the moment HIBP indexes the breach.

Watchlist coverage (~40 apps):
    AI tools:         OpenAI, Anthropic, Cursor, Perplexity, Context.ai, Loom
    Productivity:     Slack, Notion, Zoom, Calendly, DocuSign, Monday.com,
                      Asana, Trello, HubSpot, Zapier, Airtable, Miro, Figma
    Developer tools:  GitHub, Heroku, Netlify, Cloudflare, Vercel, Linear,
                      Render, Atlassian
    Identity:         Okta, Auth0, OneLogin
    Storage/Files:    Dropbox, Box
    CRM/Support:      Salesforce, Zendesk, Intercom, Mailchimp

Deduplication:
    Filters HIBP results to breaches where AddedDate >= (now - 48 hours).
    Running daily with a 48-hour window provides a safe overlap for catch-up
    without requiring a separate DynamoDB state table.

Phone resolution:
    Primary:  KMS decrypt of phone_encrypted (post-migration records)
    Fallback: legacy plaintext whatsapp_number field

Alert delivery: freeform WhatsApp (all active users, all tiers).
    Freeform works because this Lambda is triggered by an event, not a user
    message — the 24-hour Twilio session window may or may not be open.
    Phase 2: upgrade to a Meta-approved template for guaranteed delivery.

Deployment:
    - Lambda name:   relayshield-oauth-watchlist-monitor
    - Handler:       relayshield_oauth_watchlist_monitor.lambda_handler
    - Trigger:       EventBridge rate(1 day)
    - Runtime:       Python 3.12
    - Timeout:       300 seconds (5 minutes)
    - Memory:        256 MB
    - IAM requires:
        DynamoDB Scan on relayshield_users
        Secrets Manager GetSecretValue for HIBP + Twilio secrets
        KMS Decrypt on alias/relayshield-data-key

Test payload (dry run — checks HIBP but sends no WhatsApp messages):
    { "dry_run": true }

Test payload (force a specific app alert to your number only):
    { "force_app": "Slack", "test_user_id": "user-onboard-test-001" }
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")
lambda_client  = boto3.client("lambda")

USERS_TABLE              = "relayshield_users"
KMS_PHONE_KEY_ALIAS      = "alias/relayshield-data-key"
TG_WEBHOOK_LAMBDA        = os.environ.get("TG_WEBHOOK_LAMBDA", "")
CORRELATION_WINDOW_HOURS = 72

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

HIBP_SECRET_NAME    = "relayshield/hibp_api_key"
TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

HIBP_BREACHES_URL  = "https://haveibeenpwned.com/api/v3/breaches"
TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)

# ---------------------------------------------------------------------------
# Dedup window
# ---------------------------------------------------------------------------

# Only alert for breaches HIBP indexed within the last N hours.
# 48 hours provides safe overlap for a daily schedule.
BREACH_WINDOW_HOURS = 48

# ---------------------------------------------------------------------------
# OAuth-capable SaaS app watchlist
# Key: domain (lowercased) as stored in HIBP breach data
# Value: display name used in the alert message
# ---------------------------------------------------------------------------

OAUTH_WATCHLIST: dict[str, str] = {
    # AI tools — highest risk: broad OAuth scopes, rapidly growing user base
    "openai.com":       "OpenAI",
    "anthropic.com":    "Anthropic",
    "cursor.sh":        "Cursor",
    "perplexity.ai":    "Perplexity",
    "context.ai":       "Context.ai",
    "character.ai":     "Character.AI",
    "midjourney.com":   "Midjourney",

    # Developer tools — often hold org-wide OAuth grants
    "github.com":       "GitHub",
    "heroku.com":       "Heroku",
    "netlify.com":      "Netlify",
    "vercel.com":       "Vercel",
    "cloudflare.com":   "Cloudflare",
    "linear.app":       "Linear",
    "render.com":       "Render",
    "atlassian.com":    "Atlassian",
    "bitbucket.org":    "Bitbucket",
    "gitlab.com":       "GitLab",
    "circleci.com":     "CircleCI",
    "sentry.io":        "Sentry",

    # Productivity & collaboration
    "slack.com":        "Slack",
    "notion.so":        "Notion",
    "notion.com":       "Notion",
    "zoom.us":          "Zoom",
    "calendly.com":     "Calendly",
    "loom.com":         "Loom",
    "miro.com":         "Miro",
    "figma.com":        "Figma",
    "monday.com":       "Monday.com",
    "asana.com":        "Asana",
    "trello.com":       "Trello",
    "airtable.com":     "Airtable",
    "zapier.com":       "Zapier",
    "make.com":         "Make",
    "docusign.com":     "DocuSign",

    # CRM / marketing / support
    "hubspot.com":      "HubSpot",
    "salesforce.com":   "Salesforce",
    "zendesk.com":      "Zendesk",
    "intercom.io":      "Intercom",
    "intercom.com":     "Intercom",
    "mailchimp.com":    "Mailchimp",
    "sendgrid.com":     "SendGrid",

    # Identity & SSO — breach here = catastrophic cascade
    "okta.com":         "Okta",
    "auth0.com":        "Auth0",
    "onelogin.com":     "OneLogin",
    "duo.com":          "Duo Security",

    # Storage & files
    "dropbox.com":      "Dropbox",
    "box.com":          "Box",

    # E-commerce / payments (OAuth grant common)
    "shopify.com":      "Shopify",
    "stripe.com":       "Stripe",
}

# Name-based fallback: match HIBP breach Name field (lowercased) when Domain is absent
# Maps lowercase breach name fragment → display name
OAUTH_NAME_WATCHLIST: dict[str, str] = {
    "github":       "GitHub",
    "slack":        "Slack",
    "notion":       "Notion",
    "openai":       "OpenAI",
    "atlassian":    "Atlassian",
    "okta":         "Okta",
    "dropbox":      "Dropbox",
    "salesforce":   "Salesforce",
    "hubspot":      "HubSpot",
    "shopify":      "Shopify",
    "zoom":         "Zoom",
    "cloudflare":   "Cloudflare",
    "gitlab":       "GitLab",
    "bitbucket":    "Bitbucket",
    "docusign":     "DocuSign",
    "intercom":     "Intercom",
    "zapier":       "Zapier",
    "figma":        "Figma",
    "asana":        "Asana",
    "trello":       "Trello",
    "airtable":     "Airtable",
    "calendly":     "Calendly",
    "mailchimp":    "Mailchimp",
    "sendgrid":     "SendGrid",
    "auth0":        "Auth0",
    "heroku":       "Heroku",
    "vercel":       "Vercel",
    "netlify":      "Netlify",
    "render":       "Render",
    "linear":       "Linear",
    "sentry":       "Sentry",
    "circleci":     "CircleCI",
    "cursor":       "Cursor",
    "perplexity":   "Perplexity",
    "loom":         "Loom",
    "miro":         "Miro",
}

# ---------------------------------------------------------------------------
# Eligible onboarding states
# ---------------------------------------------------------------------------

ELIGIBLE_STATES = {"ACTIVE", "AWAITING_EMAIL_1", "AWAITING_EMAIL_2", "EMPLOYEE_ACTIVE"}

# ---------------------------------------------------------------------------
# Secret helpers
# ---------------------------------------------------------------------------

def get_secret(secret_name: str) -> str:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


def get_secret_json(secret_name: str, key: str) -> str:
    raw = get_secret(secret_name)
    try:
        data = json.loads(raw)
        return data[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def get_hibp_api_key() -> str:
    return get_secret_json(HIBP_SECRET_NAME, "HIBP_API_KEY")


def get_twilio_credentials() -> tuple[str, str, str]:
    account_sid = get_secret_json(TWILIO_SID_SECRET,   "TWILIO_ACCOUNT_SID")
    auth_token  = get_secret_json(TWILIO_TOKEN_SECRET,  "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET,   "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# Phone helpers
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    response = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return response["Plaintext"].decode()


def get_whatsapp_number(user: dict) -> str:
    """
    Return whatsapp:-prefixed number.
    Primary:  KMS decrypt of phone_encrypted.
    Fallback: legacy plaintext whatsapp_number.
    """
    if "phone_encrypted" in user:
        phone = decrypt_phone(user["phone_encrypted"]).replace("whatsapp:", "").strip()
        return f"whatsapp:{phone}"
    legacy = user.get("whatsapp_number", "")
    if legacy and not legacy.startswith("whatsapp:"):
        legacy = f"whatsapp:{legacy}"
    return legacy


# ---------------------------------------------------------------------------
# HIBP breach polling
# ---------------------------------------------------------------------------

def fetch_recent_breaches(hibp_api_key: str) -> list[dict]:
    """
    Fetch all breaches from HIBP and filter to those added within BREACH_WINDOW_HOURS.
    Returns list of breach dicts matching the watchlist window.
    """
    req = urllib.request.Request(
        HIBP_BREACHES_URL,
        headers={
            "hibp-api-key": hibp_api_key,
            "User-Agent":   "RelayShield-WatchlistMonitor/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("HIBP API HTTP %d: %s", exc.code, error_body)
        return []
    except Exception as exc:
        logger.exception("HIBP API request failed: %s", exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=BREACH_WINDOW_HOURS)

    recent = []
    for breach in breaches:
        added_str = breach.get("AddedDate", "")
        if not added_str:
            continue
        try:
            added_dt = datetime.fromisoformat(added_str.replace("Z", "+00:00"))
            if added_dt >= cutoff:
                recent.append(breach)
        except (ValueError, TypeError):
            continue

    logger.info(
        "HIBP returned %d total breaches. %d added within last %d hours.",
        len(breaches), len(recent), BREACH_WINDOW_HOURS,
    )
    return recent


def match_watchlist(breach: dict) -> str | None:
    """
    Check if a breach matches the OAuth app watchlist.
    Returns the display name of the matched app, or None if no match.
    Matches on Domain first, then breach Name.
    """
    domain = (breach.get("Domain") or "").lower().strip()
    name   = (breach.get("Name") or "").lower().strip()

    # Domain match (most reliable)
    if domain and domain in OAUTH_WATCHLIST:
        return OAUTH_WATCHLIST[domain]

    # Name fragment match (fallback for apps with no domain in HIBP)
    for fragment, display_name in OAUTH_NAME_WATCHLIST.items():
        if fragment in name:
            return display_name

    return None


# ---------------------------------------------------------------------------
# Alert message builder
# ---------------------------------------------------------------------------

def build_oauth_breach_alert(
    app_name: str,
    breach_date: str,
    data_classes: list[str],
) -> str:
    """
    Build the WhatsApp alert body for a watched app breach.
    Instructs users to revoke OAuth access whether or not their credentials
    were directly exposed — the token is the attack surface.
    """
    # Format breach date
    try:
        dt       = datetime.fromisoformat(breach_date + "T00:00:00+00:00")
        date_str = dt.strftime("%d %b %Y")
    except (ValueError, TypeError):
        date_str = breach_date or "recently"

    # Summarise exposed data classes (cap at 4 for readability)
    if data_classes:
        classes_str = ", ".join(data_classes[:4])
        if len(data_classes) > 4:
            classes_str += f" and {len(data_classes) - 4} more"
        data_line = f"Exposed data includes: {classes_str}.\n\n"
    else:
        data_line = ""

    return (
        f"🚨 *OAuth Supply Chain Alert — {app_name} Breached*\n\n"
        f"*{app_name}* has been confirmed in a data breach ({date_str}). "
        f"{data_line}"
        f"If you have connected *{app_name}* to your Google or Microsoft account — "
        f"or use it to sign in with Google or Microsoft — your account access may be at "
        f"risk even if your own credentials were not directly exposed.\n\n"
        f"An attacker who compromised {app_name}'s OAuth tokens can authenticate "
        f"as you without ever touching your password.\n\n"
        f"*Act now if you use {app_name}:*\n"
        f"1️⃣ Revoke {app_name}'s Google access:\n"
        f"   → myaccount.google.com/permissions\n"
        f"2️⃣ Revoke {app_name}'s Microsoft access:\n"
        f"   → myapps.microsoft.com\n"
        f"3️⃣ If you sign in to other services *using* {app_name}, "
        f"change those account passwords now\n\n"
        f"Reply *OAUTH* for a full connected app audit walkthrough.\n\n"
        f"🛡️ RelayShield — OAuth monitoring active"
    )


# ---------------------------------------------------------------------------
# DynamoDB — user scan
# ---------------------------------------------------------------------------

def scan_active_users() -> list[dict]:
    """Return all active users in eligible onboarding states."""
    table  = dynamodb.Table(USERS_TABLE)
    users: list[dict] = []
    kwargs: dict = {"FilterExpression": Attr("active").eq(True)}

    while True:
        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            if item.get("onboarding_state", "") in ELIGIBLE_STATES:
                users.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return users


def get_user_by_id(user_id: str) -> dict | None:
    table    = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    return response.get("Item")


# ---------------------------------------------------------------------------
# WhatsApp delivery
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a freeform WhatsApp message. Returns True on success."""
    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    to_wa   = to_number   if to_number.startswith("whatsapp:")   else f"whatsapp:{to_number}"
    from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    payload = urllib.parse.urlencode({
        "From": from_wa,
        "To":   to_wa,
        "Body": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("WhatsApp sent to %s SID: %s", to_number, result.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("WhatsApp send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Alert dispatch
# ---------------------------------------------------------------------------

def record_signal(user_id: str, signal_type: str, metadata: dict | None = None) -> list:
    """
    Append a timestamped security signal to recent_signals on the user record.
    Prunes entries older than CORRELATION_WINDOW_HOURS in the same write.
    Returns the updated signal list.
    """
    table  = dynamodb.Table(USERS_TABLE)
    now    = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=CORRELATION_WINDOW_HOURS)).isoformat()

    existing = table.get_item(Key={"user_id": user_id}).get("Item", {}).get("recent_signals", [])
    pruned   = [s for s in existing if isinstance(s, dict) and s.get("ts", "") > cutoff]
    pruned.append({"type": signal_type, "ts": now.isoformat(), "meta": metadata or {}})

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET recent_signals = :s",
        ExpressionAttributeValues={":s": pruned},
    )
    logger.info("Signal recorded — user_id=%s type=%s", user_id, signal_type)
    return pruned


def _push_tg_signal(user_id: str, signal_type: str, tg_chat_id: int) -> None:
    """
    Invoke the Telegram webhook Lambda so it can run Telegram-specific
    predictive warnings and coordinated attack alerts.
    Signal has already been recorded in DynamoDB — do NOT re-record.
    No-ops silently if TG_WEBHOOK_LAMBDA env var is not set.
    """
    if not TG_WEBHOOK_LAMBDA:
        return
    try:
        payload = json.dumps({
            "source":           "relayshield_internal",
            "user_id":          user_id,
            "signal_type":      signal_type,
            "telegram_chat_id": tg_chat_id,
        }).encode()
        lambda_client.invoke(
            FunctionName=TG_WEBHOOK_LAMBDA,
            InvocationType="Event",
            Payload=payload,
        )
        logger.info("TG signal pushed — user_id=%s type=%s chat_id=%s", user_id, signal_type, tg_chat_id)
    except Exception as exc:
        logger.exception("_push_tg_signal failed user_id=%s: %s", user_id, exc)


def alert_all_users(
    app_name: str,
    breach_date: str,
    data_classes: list[str],
    users: list[dict],
    account_sid: str,
    auth_token: str,
    from_number: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """Send OAuth breach alert to all supplied users. Returns counters."""
    body     = build_oauth_breach_alert(app_name, breach_date, data_classes)
    counters = {"sent": 0, "skipped": 0, "failed": 0}

    for user in users:
        user_id = user.get("user_id", "unknown")
        try:
            to_number = get_whatsapp_number(user)
        except Exception as exc:
            logger.exception("Phone resolution failed user_id=%s: %s", user_id, exc)
            counters["skipped"] += 1
            continue

        if not to_number or to_number == "whatsapp:":
            logger.warning("user_id=%s has no phone — skipping.", user_id)
            counters["skipped"] += 1
            continue

        if dry_run:
            logger.info("DRY RUN — would send %s alert to user_id=%s", app_name, user_id)
            counters["sent"] += 1
            continue

        sent = send_whatsapp(to_number, body, account_sid, auth_token, from_number)
        counters["sent" if sent else "failed"] += 1

        if sent:
            # Record per-user signal for cross-monitor correlation
            try:
                record_signal(user_id, "oauth_app_breach", {"app_name": app_name})
            except Exception as exc:
                logger.exception("record_signal failed user_id=%s: %s", user_id, exc)

            # Push to Telegram correlation engine if user has TG delivery
            tg_chat_id  = user.get("telegram_chat_id")
            tg_channels = user.get("delivery_channels", [])
            if tg_chat_id and "telegram" in tg_channels:
                _push_tg_signal(user_id, "oauth_app_breach", int(tg_chat_id))

    return counters


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge daily trigger.

    Dry run (checks HIBP, logs matches, sends no WhatsApp messages):
        { "dry_run": true }

    Force-test a specific app alert to one user (safe in production):
        { "force_app": "Slack", "test_user_id": "user-onboard-test-001" }
    """
    logger.info("OAuth watchlist monitor starting.")

    dry_run      = bool(event.get("dry_run", False))
    force_app    = event.get("force_app", "")
    test_user_id = event.get("test_user_id", "")

    if dry_run:
        logger.info("DRY RUN mode — no WhatsApp messages will be sent.")

    # Load credentials
    try:
        hibp_api_key                          = get_hibp_api_key()
        account_sid, auth_token, from_number  = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    # ── Force-test mode ───────────────────────────────────────────────────
    if force_app and test_user_id:
        user = get_user_by_id(test_user_id)
        if not user:
            return {"statusCode": 404, "body": f"User {test_user_id} not found"}

        body = build_oauth_breach_alert(
            app_name=force_app,
            breach_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            data_classes=["Email addresses", "Passwords", "OAuth tokens"],
        )
        sent = send_whatsapp(
            get_whatsapp_number(user), body, account_sid, auth_token, from_number
        )
        logger.info("Force-test alert — app=%s user=%s sent=%s", force_app, test_user_id, sent)
        return {
            "statusCode": 200,
            "body": json.dumps({"force_app": force_app, "sent": sent}),
        }

    # ── Production mode ───────────────────────────────────────────────────

    # Poll HIBP for recent breaches
    recent_breaches = fetch_recent_breaches(hibp_api_key)
    if not recent_breaches:
        logger.info("No new breaches in the last %d hours. Exiting.", BREACH_WINDOW_HOURS)
        return {"statusCode": 200, "body": json.dumps({"new_breaches": 0, "watchlist_hits": 0})}

    # Cross-reference against watchlist
    watchlist_hits: list[dict] = []
    for breach in recent_breaches:
        app_name = match_watchlist(breach)
        if app_name:
            watchlist_hits.append({
                "app_name":    app_name,
                "breach_name": breach.get("Name", ""),
                "breach_date": breach.get("BreachDate", ""),
                "added_date":  breach.get("AddedDate", ""),
                "data_classes": breach.get("DataClasses", []),
            })
            logger.warning(
                "WATCHLIST HIT — app=%s breach=%s added=%s",
                app_name, breach.get("Name"), breach.get("AddedDate"),
            )

    if not watchlist_hits:
        logger.info(
            "%d new breach(es) found — none matched watchlist.", len(recent_breaches)
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "new_breaches":   len(recent_breaches),
                "watchlist_hits": 0,
            }),
        }

    # Load active users once (shared across all watchlist hits)
    users = scan_active_users()
    logger.info("Loaded %d active users for alert dispatch.", len(users))

    results = []
    for hit in watchlist_hits:
        logger.info(
            "Dispatching %s breach alert to %d users.", hit["app_name"], len(users)
        )
        counters = alert_all_users(
            app_name=hit["app_name"],
            breach_date=hit["breach_date"],
            data_classes=hit["data_classes"],
            users=users,
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            dry_run=dry_run,
        )
        results.append({
            "app":     hit["app_name"],
            "breach":  hit["breach_name"],
            "added":   hit["added_date"],
            **counters,
        })
        logger.info(
            "%s alert complete — sent=%d skipped=%d failed=%d",
            hit["app_name"], counters["sent"], counters["skipped"], counters["failed"],
        )

    logger.info("OAuth watchlist monitor complete — %d watchlist hit(s).", len(watchlist_hits))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "new_breaches":   len(recent_breaches),
            "watchlist_hits": len(watchlist_hits),
            "results":        results,
        }),
    }
