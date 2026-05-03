"""
RelayShield WhatsApp Webhook Lambda
Receives all inbound WhatsApp messages via Twilio and routes them based
on the user's current onboarding_state.

Onboarding state machine:
  AWAITING_EMAIL_1       → validate + store first email, ask for more
  AWAITING_MORE_EMAILS   → add email (up to tier limit) or DONE → next stage
  AWAITING_PASSWORD_MANAGER → YES/NO → set flag → confirm + activate
  ACTIVE                 → handle reply commands

Reply commands (ACTIVE users):
  SWEEP    — Email Security Sweep instructions
  RESET    — Strong password guide
  REUSE    — Cross-account password reuse walkthrough (next account in sequence)
  MANAGER  — Bitwarden setup guide
  PHONE    — Carrier hardening steps (SIM swap + smishing defence)
  OTP      — User received an unexpected OTP they did not request
  WASCAM   — User received a suspicious WhatsApp message (bank/carrier/family impersonation)
  SMS <text> — User forwards a suspicious text for analysis
  SESSIONS — Revoke active sessions and OAuth tokens (Google, Microsoft, social media)
  SAFE     — Vishing warning acknowledged
  CALL     — User received a suspicious call
  VERIFY   — Personal Verification Protocol: four rules to set before an attack (callback rule,
             OTP rule, family safe word, wire transfer rule)
  RESOLVED — User confirms remediation complete after a breach incident — clears breach_alert
             signals from recent_signals to prevent re-triggering coordinated attack alerts
  HELP     — List all available commands
  ADD +1XXXXXXXXXX — Business tier: add employee phone number (admin only)

Employee onboarding (Business tiers):
  Admin sends: ADD +16175551234
  RelayShield messages that number with abbreviated onboarding:
    AWAITING_EMPLOYEE_EMAIL_1 → AWAITING_EMPLOYEE_MORE_EMAILS → EMPLOYEE_ACTIVE
  Employee is linked to admin's account via admin_user_id field.
"""

import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")
kms_client = boto3.client("kms")

# KMS key alias for field-level encryption (email + phone).
# Key must exist in the same region as the Lambda.
KMS_EMAIL_KEY_ALIAS = "alias/relayshield-data-key"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

# GSI name for phone number hash lookup
PHONE_HASH_INDEX = "phone_hash-index"

USERS_TABLE = "relayshield_users"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"
TWILIO_AUTH_TOKEN_SECRET = "relayshield/twilio_auth_token"
GSB_SECRET_NAME = "relayshield/google_safe_browsing"
GSB_SECRET_KEY = "google_safe_browsing_api_key"
VT_SECRET_NAME = "relayshield/virustotal_api_key"
VT_SECRET_KEY = "virustotal_api_key"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)
GSB_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
VT_BASE_URL = "https://www.virustotal.com/api/v3"

# VirusTotal polling config
# URL scans typically complete in 10–20 s; file scans up to 40 s.
# Lambda timeout must be set to 60 s to accommodate worst-case file scans.
VT_POLL_INTERVAL = 3   # seconds between status checks
VT_URL_MAX_WAIT  = 30  # max seconds to wait for URL analysis (increased for cold-start headroom)
VT_FILE_MAX_WAIT = 45  # max seconds to wait for file analysis

# Twilio media content-type → safe filename mapping
VT_FILENAME_MAP = {
    "application/pdf":      "attachment.pdf",
    "application/zip":      "attachment.zip",
    "application/x-zip-compressed": "attachment.zip",
    "application/msword":   "attachment.doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "attachment.docx",
    "application/vnd.ms-excel": "attachment.xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "attachment.xlsx",
    "image/jpeg": "attachment.jpg",
    "image/png":  "attachment.png",
    "text/plain": "attachment.txt",
}

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_PERSONAL        = "personal_shield"
TIER_STARTER         = "business_starter"
TIER_STARTER_DOMAIN  = "starter_domain"
TIER_BASIC           = "business_basic"
TIER_SHIELD          = "business_shield"
TIER_PRO             = "business_shield_pro"

BUSINESS_TIERS = {TIER_STARTER, TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}

# Max emails per subscriber (personal) or per employee (business)
EMAIL_LIMITS = {
    TIER_PERSONAL:       3,
    TIER_STARTER:        3,
    TIER_STARTER_DOMAIN: 3,
    TIER_BASIC:          2,
    TIER_SHIELD:         2,
    TIER_PRO:            2,
}

# Max employee seats per business tier (starter_domain is solo-only — no seats)
SEAT_LIMITS = {
    TIER_STARTER: 2,
    TIER_BASIC:   5,
    TIER_SHIELD:  10,
    TIER_PRO:     25,
}

# Domain monitoring — eligible tiers and per-tier domain limits
DOMAIN_TIERS = {TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}
DOMAIN_LIMITS = {
    TIER_STARTER_DOMAIN: 1,
    TIER_BASIC:          2,
    TIER_SHIELD:         2,
    TIER_PRO:            2,
}

# Free email providers — domain cannot be extracted as a business domain
FREE_EMAIL_PROVIDERS = {
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.ca", "yahoo.com.au",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr",
    "outlook.com", "outlook.co.uk",
    "live.com", "live.co.uk",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "aol.co.uk",
    "protonmail.com", "proton.me", "pm.me",
    "mail.com", "gmx.com", "gmx.net",
    "yandex.com", "yandex.ru",
    "zoho.com",
    "msn.com",
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net",
    "bellsouth.net", "cox.net",
}

# Onboarding states
STATE_EMAIL_1 = "AWAITING_EMAIL_1"
STATE_MORE_EMAILS = "AWAITING_MORE_EMAILS"
STATE_PASSWORD_MANAGER = "AWAITING_PASSWORD_MANAGER"
STATE_ACTIVE = "ACTIVE"

# Employee onboarding states
STATE_EMP_EMAIL_1 = "AWAITING_EMPLOYEE_EMAIL_1"
STATE_EMP_MORE_EMAILS = "AWAITING_EMPLOYEE_MORE_EMAILS"
STATE_EMP_ACTIVE = "EMPLOYEE_ACTIVE"

# ---------------------------------------------------------------------------
# Cross-account reuse walkthrough
# ---------------------------------------------------------------------------

CROSS_ACCOUNT_SERVICES = [
    ("Gmail / Outlook / Yahoo Mail", "email — the master key to every other account"),
    ("Banking and financial apps", "direct access to money"),
    ("Amazon / PayPal / shopping accounts", "saved payment cards"),
    ("Apple ID / Google Account", "device access and app purchases"),
    ("Facebook / LinkedIn / social media", "identity and contact data"),
    ("Square / payment processing tools", "business bank account access"),
]


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


def get_twilio_credentials() -> tuple[str, str, str]:
    """Return (account_sid, auth_token, from_whatsapp_number)."""
    account_sid = get_secret_json(TWILIO_SID_SECRET, "TWILIO_ACCOUNT_SID")
    auth_token = get_secret_json(TWILIO_TOKEN_SECRET, "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET, "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


def get_gsb_api_key() -> str:
    """Retrieve Google Safe Browsing API key from Secrets Manager."""
    return get_secret_json(GSB_SECRET_NAME, GSB_SECRET_KEY)


def get_vt_api_key() -> str:
    """Retrieve VirusTotal API key from Secrets Manager."""
    return get_secret_json(VT_SECRET_NAME, VT_SECRET_KEY)


# ---------------------------------------------------------------------------
# Google Safe Browsing URL analysis
# ---------------------------------------------------------------------------

def extract_urls(text: str) -> list[str]:
    """
    Extract all http/https URLs from a text string.
    Returns a deduplicated list, preserving order of first appearance.
    """
    found = re.findall(r'https?://[^\s<>"\']+', text)
    seen = set()
    unique = []
    for url in found:
        # Strip trailing punctuation that may have been captured
        url = url.rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def check_urls_safe_browsing(urls: list[str], api_key: str) -> dict:
    """
    Submit a list of URLs to Google Safe Browsing API v4.
    Returns a dict with keys:
      "matches"  — list of threat match dicts (empty if all clean)
      "error"    — error message string if API call failed, else None

    Uses urllib.request to stay consistent with the rest of the codebase.
    POST to GSB_URL?key={api_key} with JSON body.
    """
    payload = json.dumps({
        "client": {
            "clientId": "relayshield",
            "clientVersion": "1.0",
        },
        "threatInfo": {
            "threatTypes": [
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in urls],
        },
    }).encode("utf-8")

    url_with_key = f"{GSB_URL}?key={api_key}"
    headers = {
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        url_with_key,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            # GSB returns {} when no threats found; "matches" key only present
            # when threats are detected.
            return {"matches": body.get("matches", []), "error": None}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("GSB API HTTPError %s: %s", e.code, error_body)
        return {"matches": [], "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        logger.error("GSB API URLError: %s", e.reason)
        return {"matches": [], "error": str(e.reason)}
    except Exception as e:
        logger.error("GSB API unexpected error: %s", e)
        return {"matches": [], "error": str(e)}


def build_sms_analysis_response(
    forwarded_text: str,
    urls: list[str],
    gsb_result: dict,
) -> str:
    """
    Build the WhatsApp response for the SMS command based on URL analysis results.
    Three outcomes:
      1. No URLs found — guidance only
      2. URLs found, all clean — low-risk guidance
      3. URLs found, threats detected — CRITICAL warning
    Always falls back gracefully if GSB errored.
    """
    immediate_steps = (
        "→ Do not click any links in the message\n"
        "→ Do not reply to the sender\n"
        "→ Block the sender on your phone\n"
        "→ Report to your carrier: forward the text to *7726* (SPAM) — "
        "works on AT&T, T-Mobile, and Verizon\n"
        "→ Report to the FTC: reportfraud.ftc.gov\n"
    )

    if not urls:
        return (
            "📨 *Suspicious text received — no URLs detected.*\n\n"
            "No links were found in the forwarded text to analyse. "
            "If the message asked you to call a number or reply with personal details, "
            "treat it as a smishing attempt.\n\n"
            + immediate_steps
            + "\nReply *OTP* if you received a verification code, "
            "or *CALL* if you also received a suspicious call.\n\n"
            "— RelayShield"
        )

    if gsb_result["error"]:
        # API failed — return guidance without a verdict rather than crash
        logger.warning("GSB analysis skipped due to error: %s", gsb_result["error"])
        return (
            "📨 *Suspicious text received.*\n\n"
            f"Found {len(urls)} link(s) — automated analysis temporarily unavailable. "
            "Treat the link(s) as unsafe until you can verify them.\n\n"
            + immediate_steps
            + "\nReply *OTP* if you received a verification code, "
            "or *CALL* if you also received a suspicious call.\n\n"
            "— RelayShield"
        )

    matches = gsb_result["matches"]
    flagged_urls = {m["threat"]["url"] for m in matches}

    if flagged_urls:
        url_list = "\n".join(f"⛔ {u}" for u in flagged_urls)
        return (
            "🚨 *MALICIOUS LINK DETECTED*\n\n"
            f"RelayShield flagged {len(flagged_urls)} of the "
            f"{len(urls)} link(s) in that text as a confirmed threat "
            "(malware, phishing, or social engineering):\n\n"
            f"{url_list}\n\n"
            "*Do NOT click these links under any circumstances.*\n\n"
            + immediate_steps
            + "\nIf you already clicked the link:\n"
            "→ Do not enter any information on the page that opened\n"
            "→ Close the browser tab immediately\n"
            "→ Reply *SWEEP* to check your email accounts for backdoors\n"
            "→ Reply *SESSIONS* to revoke active sessions on your accounts\n\n"
            "— RelayShield"
        )

    # URLs found, all clean
    url_list = "\n".join(f"✅ {u}" for u in urls)
    return (
        "📨 *Suspicious text analysed — no known threats detected.*\n\n"
        f"RelayShield checked {len(urls)} link(s) and found no "
        "confirmed malware or phishing:\n\n"
        f"{url_list}\n\n"
        "⚠️ *A clean result does not guarantee the link is safe.* "
        "New phishing sites can take hours to appear in threat databases. "
        "If the text was unexpected or asked for personal information, "
        "treat it with caution regardless.\n\n"
        + immediate_steps
        + "\n— RelayShield"
    )


def build_email_analysis_response(
    urls: list[str],
    gsb_result: dict,
) -> str:
    """
    Build the WhatsApp response for the EMAIL command based on URL analysis results.
    Same three outcomes as build_sms_analysis_response() but with email-specific
    framing: attachment warning, phishing report steps, no SMS carrier reporting.
    """
    immediate_steps = (
        "→ Do not click any links in the email\n"
        "→ Do not open any attachments — even PDFs can execute malicious code when opened\n"
        "→ Do not reply to the sender\n"
        "→ Report as phishing in your email client:\n"
        "   Gmail: three-dot menu → *Report phishing*\n"
        "   Outlook: three-dot menu → *Report* → *Report phishing*\n"
        "→ Report to the FTC: reportfraud.ftc.gov\n"
    )

    if not urls:
        return (
            "📧 *Suspicious email received — no URLs detected in the text you sent.*\n\n"
            "No links were found to analyse. If the email contains an attachment, "
            "do not open it. To check an attachment safely:\n"
            "→ In Gmail: right-click the attachment → *Copy link address* → "
            "paste that URL at virustotal.com (no download needed)\n"
            "→ Do not download the file to open it — opening is when malware executes\n\n"
            + immediate_steps
            + "\nReply *SWEEP* to check your email accounts for backdoors, "
            "or *SESSIONS* if you clicked anything.\n\n"
            "— RelayShield"
        )

    if gsb_result["error"]:
        logger.warning("GSB analysis skipped due to error: %s", gsb_result["error"])
        return (
            "📧 *Suspicious email received.*\n\n"
            f"Found {len(urls)} link(s) — automated analysis temporarily unavailable. "
            "Treat all links and attachments as unsafe until verified.\n\n"
            + immediate_steps
            + "\nReply *SWEEP* to check your email accounts for backdoors.\n\n"
            "— RelayShield"
        )

    matches = gsb_result["matches"]
    flagged_urls = {m["threat"]["url"] for m in matches}

    if flagged_urls:
        url_list = "\n".join(f"⛔ {u}" for u in flagged_urls)
        return (
            "🚨 *MALICIOUS LINK DETECTED IN EMAIL*\n\n"
            f"RelayShield flagged {len(flagged_urls)} of the "
            f"{len(urls)} link(s) as a confirmed threat "
            "(malware, phishing, or social engineering):\n\n"
            f"{url_list}\n\n"
            "*Do NOT click these links or open any attachments in this email.*\n\n"
            + immediate_steps
            + "\nIf you already clicked a link or opened an attachment:\n"
            "→ Do not enter any information on any page that opened\n"
            "→ Close all browser tabs immediately\n"
            "→ Reply *SWEEP* to check your email accounts for backdoors\n"
            "→ Reply *SESSIONS* to revoke active sessions on your accounts\n\n"
            "— RelayShield"
        )

    url_list = "\n".join(f"✅ {u}" for u in urls)
    return (
        "📧 *Suspicious email analysed — no known threats detected in links.*\n\n"
        f"RelayShield checked {len(urls)} link(s) and found no confirmed "
        "malware or phishing:\n\n"
        f"{url_list}\n\n"
        "⚠️ *A clean link result does not make the email safe.* "
        "New phishing sites can take hours to appear in threat databases. "
        "If the email was unexpected, came from an unfamiliar sender, or contains "
        "an attachment — treat it with caution regardless.\n\n"
        + immediate_steps
        + "\n— RelayShield"
    )


# ---------------------------------------------------------------------------
# VirusTotal scanning helpers
# ---------------------------------------------------------------------------

def submit_url_to_vt(url: str, api_key: str) -> str | None:
    """
    Submit a URL to VirusTotal for analysis.
    POST /urls with form-encoded url= parameter.
    Returns the analysis ID string, or None on failure.
    """
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
            data = json.loads(resp.read())
            return data.get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT URL submission failed for %s: %s", url, exc)
        return None


def download_twilio_media(media_url: str, account_sid: str, auth_token: str) -> bytes | None:
    """
    Download a Twilio media attachment using Basic auth.
    Returns raw bytes or None on failure.
    """
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(
        media_url,
        headers={"Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception as exc:
        logger.error("Failed to download Twilio media from %s: %s", media_url, exc)
        return None


def submit_file_to_vt(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    api_key: str,
) -> str | None:
    """
    Submit a file binary to VirusTotal via multipart/form-data POST to /files.
    Returns the analysis ID string, or None on failure.
    """
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
            data = json.loads(resp.read())
            return data.get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT file submission failed: %s", exc)
        return None


def poll_vt_analysis(analysis_id: str, api_key: str, max_wait: int = VT_URL_MAX_WAIT) -> dict | None:
    """
    Poll GET /analyses/{id} until status is 'completed' or max_wait exceeded.
    Returns the stats dict (malicious/suspicious/harmless/undetected keys) or None.
    """
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    waited = 0
    while waited <= max_wait:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                attrs = data.get("data", {}).get("attributes", {})
                if attrs.get("status") == "completed":
                    return attrs.get("stats", {})
        except Exception as exc:
            logger.error("VT poll error for analysis %s: %s", analysis_id, exc)
            return None
        time.sleep(VT_POLL_INTERVAL)
        waited += VT_POLL_INTERVAL
    logger.warning("VT analysis %s did not complete within %ds.", analysis_id, max_wait)
    return None


def build_vt_verdict_response(stats: dict | None, target_label: str) -> str:
    """
    Build WhatsApp response from VirusTotal analysis stats.
    Four outcomes: malicious, suspicious, clean, or timed out / unavailable.
    target_label: short description e.g. "that URL" or "that file".
    """
    if stats is None:
        return (
            "🔍 *RelayShield scan — result not available.*\n\n"
            f"Analysis of {target_label} took longer than expected or could not complete. "
            "Treat it as potentially unsafe until verified.\n\n"
            "💡 You can also check manually at *virustotal.com* by pasting the URL or uploading the file directly.\n\n"
            "— RelayShield"
        )

    malicious  = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless   = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)
    total      = malicious + suspicious + harmless + undetected

    if malicious > 0:
        return (
            f"🚨 *MALICIOUS — {malicious} of {total} security engines confirmed a threat*\n\n"
            f"RelayShield detected {target_label} as malicious "
            "(malware, phishing, or trojan).\n\n"
            "*If you have NOT opened the file:*\n"
            "→ Delete it immediately — do not open, forward, or share it\n"
            "→ Report the email or message it arrived in as phishing\n"
            "→ Block the sender\n\n"
            "*If you already opened it:*\n"
            "→ Disconnect from Wi-Fi immediately\n"
            "→ Run a free device scan: download *Malwarebytes* at malwarebytes.com\n"
            "→ Reply *SESSIONS* to revoke active account sessions before an attacker uses them\n"
            "→ Reply *SWEEP* to check your email for backdoors planted by the malware\n"
            "→ Call your bank's fraud line if any financial accounts were open at the time\n"
            "→ If this is a work device — notify your IT contact immediately\n\n"
            "— RelayShield"
        )

    if suspicious > 0:
        return (
            f"⚠️ *SUSPICIOUS — {suspicious} of {total} engines flagged as suspicious*\n\n"
            f"RelayShield detected low-confidence threat signals on {target_label}. "
            "This may be a false positive — treat it with caution.\n\n"
            "→ Do not open the file or enter any information on the page\n"
            "→ If this arrived in an unexpected email, report the email as phishing\n"
            "→ Reply *SWEEP* if you already interacted with it\n\n"
            "— RelayShield"
        )

    return (
        f"✅ *No threats detected — {harmless + undetected} of {total} "
        f"engines found {target_label} clean.*\n\n"
        "⚠️ A clean result does not guarantee safety. "
        "Zero-day threats and newly created malicious files may not yet appear "
        "in threat databases. If this arrived unexpectedly, treat it with caution regardless.\n\n"
        "— RelayShield"
    )


# ---------------------------------------------------------------------------
# Twilio signature verification
# ---------------------------------------------------------------------------

def verify_twilio_signature(
    auth_token: str,
    signature: str,
    url: str,
    params: dict,
) -> bool:
    """
    Verify the X-Twilio-Signature header.
    Twilio signs: URL + sorted POST params (key+value concatenated).
    """
    try:
        sorted_params = "".join(
            f"{k}{v}" for k, v in sorted(params.items())
        )
        signed_data = url + sorted_params
        expected = base64.b64encode(
            hmac.new(
                auth_token.encode("utf-8"),
                signed_data.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)
    except Exception as exc:
        logger.exception("Twilio signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Phone number helpers
# ---------------------------------------------------------------------------

def normalise_phone(phone: str) -> str:
    """Strip whatsapp: prefix and normalise to E.164."""
    phone = phone.replace("whatsapp:", "").strip()
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def to_whatsapp_number(phone: str) -> str:
    """Prefix E.164 number with whatsapp: for Twilio (idempotent)."""
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def is_valid_phone(phone: str) -> bool:
    """Validate E.164 phone number."""
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    return cleaned.startswith("+") and len(cleaned) >= 8


# ---------------------------------------------------------------------------
# KMS email encryption helpers
# ---------------------------------------------------------------------------

def hash_email(email: str) -> str:
    """SHA-256 of normalised email — deterministic, safe to use in DynamoDB filters."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def encrypt_email(email: str) -> str:
    """Encrypt a normalised email via KMS. Returns base64-encoded ciphertext."""
    response = kms_client.encrypt(
        KeyId=KMS_EMAIL_KEY_ALIAS,
        Plaintext=email.strip().lower().encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


def decrypt_email(ciphertext_b64: str) -> str:
    """Decrypt a KMS-encrypted email ciphertext (base64). Returns plaintext string."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


# ---------------------------------------------------------------------------
# KMS phone encryption helpers
# ---------------------------------------------------------------------------

def hash_phone(phone: str) -> str:
    """SHA-256 of normalised E.164 phone — deterministic GSI lookup key."""
    normalised = phone.strip().replace("whatsapp:", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def encrypt_phone(phone: str) -> str:
    """Encrypt normalised E.164 phone via KMS. Returns base64-encoded ciphertext."""
    normalised = phone.strip().replace("whatsapp:", "")
    response = kms_client.encrypt(
        KeyId=KMS_PHONE_KEY_ALIAS,
        Plaintext=normalised.encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


def decrypt_phone(ciphertext_b64: str) -> str:
    """Decrypt KMS-encrypted phone ciphertext (base64). Returns E.164 string."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


def get_user_whatsapp_number(user: dict) -> str:
    """
    Return the whatsapp:-prefixed number for outbound sends.
    Decrypts from KMS for new encrypted records.
    Falls back to legacy plaintext whatsapp_number for pre-migration records.
    """
    if "phone_encrypted" in user:
        return to_whatsapp_number(decrypt_phone(user["phone_encrypted"]))
    return user.get("whatsapp_number", "")


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def get_user_by_whatsapp(whatsapp_number: str) -> dict | None:
    """
    Look up a user record by their WhatsApp number.
    Primary path: GSI query on phone_hash (encrypted records).
    Fallback: full table scan on plaintext whatsapp_number (pre-migration records).
    """
    table = dynamodb.Table(USERS_TABLE)
    normalised = normalise_phone(whatsapp_number).replace("whatsapp:", "")
    ph = hash_phone(normalised)

    # Primary: GSI lookup — O(1), works for all encrypted records
    response = table.query(
        IndexName=PHONE_HASH_INDEX,
        KeyConditionExpression=Key("phone_hash").eq(ph),
    )
    items = response.get("Items", [])
    if items:
        return items[0]

    # Fallback: scan for legacy plaintext records (removed once migration complete)
    wa = to_whatsapp_number(normalise_phone(whatsapp_number))
    response = table.scan(
        FilterExpression=Attr("whatsapp_number").eq(wa),
    )
    items = response.get("Items", [])
    return items[0] if items else None


def update_user(user_id: str, updates: dict) -> None:
    """Apply a dict of attribute updates to a user record."""
    table = dynamodb.Table(USERS_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    expr_parts = []
    attr_names: dict = {}
    attr_values: dict = {}

    for i, (k, v) in enumerate(updates.items()):
        placeholder = f"#a{i}"
        value_key = f":v{i}"
        attr_names[placeholder] = k
        attr_values[value_key] = v
        expr_parts.append(f"{placeholder} = {value_key}")

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def add_monitored_email(user_id: str, email_address: str) -> str:
    """
    Add an email to relayshield_monitored_emails.
    The plaintext email address is never written to DynamoDB — only the
    KMS ciphertext (email_encrypted) and its SHA-256 hash (email_hash).
    Returns the new email_id.
    """
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    normalised = email_address.strip().lower()
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    table.put_item(Item={
        "email_id": email_id,
        "user_id": user_id,
        "email_encrypted": encrypt_email(normalised),
        "email_hash": hash_email(normalised),
        "created_at": now,
        "last_checked": None,
        "active": True,
    })
    logger.info("Monitored email added — user_id=%s hash=%s", user_id, hash_email(normalised)[:8])
    return email_id


def count_monitored_emails(user_id: str) -> int:
    """Count active monitored emails for a user."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    response = table.scan(
        FilterExpression=Attr("user_id").eq(user_id) & Attr("active").eq(True),
        Select="COUNT",
    )
    return response.get("Count", 0)


def email_already_monitored(user_id: str, email_address: str) -> bool:
    """
    Check if this email is already being monitored for this user.
    Uses the SHA-256 hash for the DynamoDB filter — KMS ciphertext is
    non-deterministic and cannot be used for equality comparisons.
    """
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    eh = hash_email(email_address)
    response = table.scan(
        FilterExpression=(
            Attr("user_id").eq(user_id)
            & Attr("email_hash").eq(eh)
            & Attr("active").eq(True)
        ),
        Limit=1,
    )
    return len(response.get("Items", [])) > 0


# ---------------------------------------------------------------------------
# Domain monitoring helpers
# ---------------------------------------------------------------------------

def extract_business_domain(email: str) -> str | None:
    """
    Extract the domain portion from an email address.
    Returns None if the address is from a known free email provider,
    or if the email is malformed. Gmail addresses (and similar) are not
    business domains and should not be auto-registered for monitoring.
    """
    email = email.strip().lower()
    if "@" not in email:
        return None
    domain = email.split("@", 1)[1]
    if domain in FREE_EMAIL_PROVIDERS:
        return None
    return domain


def is_valid_domain(domain: str) -> bool:
    """Basic format validation for a domain string."""
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    return bool(re.match(pattern, domain)) and len(domain) <= 253


def load_domain_state(user: dict) -> dict:
    raw = user.get("domain_monitor_state", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_domain_state(user_id: str, state: dict) -> None:
    table = dynamodb.Table(USERS_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET domain_monitor_state = :s, updated_at = :t",
        ExpressionAttributeValues={":s": json.dumps(state), ":t": now},
    )


def auto_register_domain(user_id: str, email: str, tier: str) -> str | None:
    """
    If the email has a business domain and the user has no monitored domains yet,
    auto-register that domain. Returns the domain string, or None if skipped.
    Called during onboarding when the admin provides their first email.
    """
    if tier not in DOMAIN_TIERS:
        return None
    domain = extract_business_domain(email)
    if not domain:
        return None
    # Only auto-register if no domains exist yet (don't overwrite manual registrations)
    table    = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    user     = response.get("Item", {})
    if user.get("monitored_domains"):
        return None
    # Store as a list for DynamoDB
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET monitored_domains = :d, updated_at = :t",
        ExpressionAttributeValues={
            ":d": [domain],
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )
    logger.info("Auto-registered domain=%s for user_id=%s tier=%s", domain, user_id, tier)
    return domain


def _doh_mx_fingerprint(domain: str) -> str | None:
    """Quick MX check via Cloudflare DoH. Returns sorted fingerprint string or None."""
    url = f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(domain)}&type=MX"
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data    = json.loads(resp.read())
            answers = [a["data"].strip().lower() for a in data.get("Answer", [])]
            return ",".join(sorted(answers)) if answers else ""
    except Exception as exc:
        logger.warning("DoH MX check failed for %s: %s", domain, exc)
        return None


def _rdap_days_until_expiry(domain: str) -> int | None:
    """RDAP expiry lookup. Returns days until expiry or None if unavailable."""
    url = f"https://rdap.org/domain/{urllib.parse.quote(domain)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        for event in data.get("events", []):
            if event.get("eventAction") == "expiration":
                expiry_str = event.get("eventDate", "")
                if expiry_str:
                    expiry_dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    return (expiry_dt - datetime.now(timezone.utc)).days
    except Exception as exc:
        logger.warning("RDAP check failed for %s: %s", domain, exc)
    return None


def _dns_resolves(domain: str, dns_timeout: float = 2.5) -> bool:
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(dns_timeout)
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, OSError):
        return False
    finally:
        socket.setdefaulttimeout(old)


def _quick_typosquat_check(domain: str, known: list[str], budget_seconds: float = 25.0) -> list[str]:
    """
    Lightweight inline typosquat check for on-demand DOMAIN SCAN.
    Generates permutations and DNS-resolves in parallel.
    Returns newly active lookalikes not in known list.
    """
    if "." not in domain:
        return []
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]

    candidates: set[str] = set()
    # Character omission
    for i in range(len(name)):
        c = name[:i] + name[i + 1:]
        if c:
            candidates.add(c + tld)
    # Character repetition
    for i, ch in enumerate(name):
        candidates.add(name[:i] + ch + ch + name[i + 1:] + tld)
    # Transposition
    for i in range(len(name) - 1):
        t = list(name); t[i], t[i + 1] = t[i + 1], t[i]
        candidates.add("".join(t) + tld)
    # Common homoglyphs
    for i, ch in enumerate(name):
        if ch == "o":   candidates.add(name[:i] + "0" + name[i + 1:] + tld)
        elif ch == "l": candidates.add(name[:i] + "1" + name[i + 1:] + tld)
        elif ch == "i": candidates.add(name[:i] + "1" + name[i + 1:] + tld)
    # TLD swaps
    for alt in [".net", ".org", ".co", ".io", ".biz"]:
        if alt != tld:
            candidates.add(name + alt)
    # Phishing prefixes/suffixes
    for pfx in ["secure-", "login-", "my-"]:
        candidates.add(pfx + name + tld)
    for sfx in ["-secure", "-login", "-online"]:
        candidates.add(name + sfx + tld)
    # www-typo
    candidates.add("www" + domain)
    candidates.discard(domain)

    known_set  = set(known)
    to_check   = [d for d in candidates if d not in known_set]

    registered: list[str] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            fm = {ex.submit(_dns_resolves, d): d for d in to_check}
            for f in concurrent.futures.as_completed(fm, timeout=budget_seconds):
                d = fm[f]
                try:
                    if f.result():
                        registered.append(d)
                except Exception:
                    pass
    except concurrent.futures.TimeoutError:
        logger.warning("Quick typosquat DNS budget exceeded for domain=%s", domain)

    return sorted(registered)


def msg_domain_status(domains: list[str], domain_state: dict, tier: str) -> str:
    """Return the DOMAIN command status message."""
    limit = DOMAIN_LIMITS.get(tier, 1)
    if not domains:
        cmd = "DOMAIN REGISTER yourdomain.com"
        return (
            "🌐 *Domain Security Monitoring*\n\n"
            "No business domain registered.\n\n"
            f"Reply *{cmd}* to start monitoring your business domain.\n\n"
            f"Domain monitoring checks for:\n"
            "• Lookalike/typosquat domains used for phishing\n"
            "• Email configuration (MX) changes\n"
            "• Domain expiry risk\n\n"
            f"Your plan supports up to *{limit}* domain{'s' if limit > 1 else ''}.\n\n"
            "🛡️ RelayShield"
        )

    lines = []
    for d in domains:
        entry        = domain_state.get(d, {})
        last_scanned = entry.get("last_scanned")
        scan_label   = "Never scanned" if not last_scanned else (
            datetime.fromisoformat(last_scanned).strftime("%-d %b %Y") if last_scanned else "Unknown"
        )
        lookalikes   = entry.get("known_lookalikes") or []
        mx_set       = entry.get("mx_fingerprint") is not None
        expiry_alerted = entry.get("expiry_days_alerted")

        lookalike_line = f"⚠️ {len(lookalikes)} lookalike(s) on record" if lookalikes else "✅ No lookalikes detected"
        mx_line        = "✅ Email configuration baseline recorded" if mx_set else "⏳ Email configuration baseline pending (next scan)"
        expiry_line    = (
            f"⚠️ Expiry alert sent ({expiry_alerted}d threshold)" if expiry_alerted else "✅ No expiry warning"
        )
        lines.append(
            f"*{d}*\n"
            f"  Last scan: {scan_label}\n"
            f"  {lookalike_line}\n"
            f"  {mx_line}\n"
            f"  {expiry_line}"
        )

    domain_block = "\n\n".join(lines)
    usage        = f"{len(domains)} of {limit} domain{'s' if limit > 1 else ''} in use"
    return (
        f"🌐 *Domain Security Status* — {usage}\n\n"
        f"{domain_block}\n\n"
        f"Reply *DOMAIN SCAN* to run a fresh check now.\n"
        f"Reply *DOMAIN REGISTER domain.com* to add a domain.\n\n"
        "🛡️ RelayShield"
    )


def count_employees(admin_user_id: str) -> int:
    """Count active employee accounts linked to an admin."""
    table = dynamodb.Table(USERS_TABLE)
    response = table.scan(
        FilterExpression=(
            Attr("admin_user_id").eq(admin_user_id)
            & Attr("active").eq(True)
        ),
        Select="COUNT",
    )
    return response.get("Count", 0)


def create_employee_record(
    phone_number: str,
    admin_user_id: str,
    subscription_tier: str,
    employee_name: str = "",
) -> str:
    """
    Create an employee user record linked to the admin's account.
    Optionally stores employee_name if provided via ADD +1XXXXXXXXXX Name.
    Returns the new user_id.
    """
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    table = dynamodb.Table(USERS_TABLE)
    item = {
        "user_id": user_id,
        "phone_encrypted": encrypt_phone(phone_number),
        "phone_hash": hash_phone(phone_number),
        "subscription_tier": subscription_tier,
        "admin_user_id": admin_user_id,
        "onboarding_state": STATE_EMP_EMAIL_1,
        "emails_added": 0,
        "password_manager_user": False,
        "sim_swap_monitoring": True,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    if employee_name:
        item["employee_name"] = employee_name.strip()
    table.put_item(Item=item)
    logger.info(
        "Employee record created — user_id=%s admin=%s name=%r (phone encrypted)",
        user_id, admin_user_id, employee_name or "(none)",
    )
    return user_id


def get_employee_by_phone_and_admin(phone: str, admin_user_id: str) -> dict | None:
    """
    Find an active employee record by phone hash that belongs to this admin.
    Used by REMOVE command to verify ownership before deactivating.
    """
    table = dynamodb.Table(USERS_TABLE)
    ph = hash_phone(phone)
    response = table.query(
        IndexName=PHONE_HASH_INDEX,
        KeyConditionExpression=Key("phone_hash").eq(ph),
    )
    for item in response.get("Items", []):
        if item.get("admin_user_id") == admin_user_id and item.get("active", False):
            return item
    return None


def get_employees_for_admin(admin_user_id: str) -> list[dict]:
    """Return all active employee records linked to this admin."""
    table = dynamodb.Table(USERS_TABLE)
    response = table.scan(
        FilterExpression=(
            Attr("admin_user_id").eq(admin_user_id)
            & Attr("active").eq(True)
        ),
    )
    return response.get("Items", [])


def deactivate_employee_emails(user_id: str) -> int:
    """
    Set active=False on all monitored emails for this employee.
    Called on REMOVE to stop monitoring deactivated team members.
    Returns count of emails deactivated.
    """
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    response = table.scan(
        FilterExpression=Attr("user_id").eq(user_id) & Attr("active").eq(True),
    )
    items = response.get("Items", [])
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        table.update_item(
            Key={"email_id": item["email_id"]},
            UpdateExpression="SET active = :f, updated_at = :t",
            ExpressionAttributeValues={":f": False, ":t": now},
        )
    return len(items)


# ---------------------------------------------------------------------------
# Coordinated attack detection — signal recording and correlation
# ---------------------------------------------------------------------------

CORRELATION_WINDOW_HOURS = 72
CORRELATION_DEDUP_HOURS  = 48

ATTACK_CHAINS = [
    {
        "chain":    "smishing_to_sim_swap",
        "signals":  {"suspicious_sms", "sim_swap"},
        "severity": "CRITICAL",
        "label":    "Smishing → SIM Swap",
        "what": (
            "Attackers typically send a phishing link first to capture credentials, "
            "then swap or port your SIM to intercept 2FA codes. This is a known "
            "two-stage attack chain."
        ),
    },
    {
        "chain":    "breach_sim_swap",
        "signals":  {"breach_alert", "sim_swap"},
        "severity": "CRITICAL",
        "label":    "Credential Breach + SIM Swap",
        "what": (
            "Your credentials were found in a breach and your SIM was swapped or ported "
            "within the same attack window. Attackers may hold both your password and "
            "control of your phone number — all SMS 2FA is compromised."
        ),
    },
    {
        "chain":    "breach_otp_intercept",
        "signals":  {"breach_alert", "otp_warning"},
        "severity": "HIGH",
        "label":    "Credential Breach + OTP Interception",
        "what": (
            "Your credentials were recently found in a breach and you received an "
            "unexpected OTP. This pattern suggests an active account takeover attempt — "
            "an attacker may be logging into your accounts right now."
        ),
    },
    {
        "chain":    "domain_phishing_breach",
        "signals":  {"domain_lookalike", "breach_alert"},
        "severity": "CRITICAL",
        "label":    "Phishing Domain + Credential Breach",
        "what": (
            "A domain impersonating your business was registered while your credentials "
            "are actively exposed in a breach. Attackers stand up fake login pages on "
            "lookalike domains after obtaining credentials — your employees and customers "
            "may already be targeted with phishing emails from this domain."
        ),
    },
]

_SESSIONS_INLINE = (
    "🔐 *Revoke sessions now — before changing passwords:*\n"
    "→ Google devices: myaccount.google.com/device-activity\n"
    "→ Google apps: myaccount.google.com/permissions\n"
    "→ Microsoft: account.microsoft.com/privacy/activity\n"
    "→ Facebook/Instagram: Settings → Security → Login Activity\n"
    "Sign out of every device and session you don't recognise."
)


def _fmt_delta(seconds: float) -> str:
    """Format elapsed seconds as 'Xh Ym ago'."""
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m ago" if h else f"{m}m ago"


PREDICTIVE_WARNINGS = {
    "breach_sim_swap": {
        "breach_alert": (
            "⚠️ *Heads up:* Credential breaches are frequently followed by SIM swap attempts "
            "within 72 hours. Attackers use stolen credentials to pass carrier identity checks.\n\n"
            "Contact your carrier now and request a *SIM lock / port freeze* on your account."
        ),
        "sim_swap": (
            "⚠️ *Heads up:* SIM swap activity has been detected on your line. Attackers who "
            "already hold breached credentials sometimes trigger a SIM swap to intercept your "
            "2FA codes and complete account takeovers.\n\n"
            "Check your email and banking apps for unauthorised login attempts immediately."
        ),
    },
    "smishing_to_sim_swap": {
        "suspicious_sms": (
            "⚠️ *Heads up:* Smishing campaigns are sometimes the first step in a SIM swap attack. "
            "Attackers harvest personal details from victims who click links, then use that "
            "information to impersonate you with your carrier.\n\n"
            "Do not click any links in unexpected texts, and consider placing a *SIM lock* on "
            "your account as a precaution."
        ),
        "sim_swap": (
            "⚠️ *Heads up:* A SIM swap attempt has been detected. If you recently received "
            "suspicious texts, the two events may be connected — attackers often use smishing "
            "to collect the personal details needed to pass carrier security checks.\n\n"
            "Report the suspicious text to your carrier immediately."
        ),
    },
    "breach_otp_intercept": {
        "breach_alert": (
            "⚠️ *Heads up:* After a credential breach, attackers sometimes trigger unexpected "
            "OTP codes to test which accounts they can access. If you receive any login codes "
            "you did not request, reply *OTP* immediately."
        ),
        "otp_warning": (
            "⚠️ *Heads up:* To trigger this OTP, someone already has your username and password "
            "for that account. They are now trying to get past your 2FA.\n\n"
            "→ Change the password for that account immediately — before they try again\n"
            "→ If you reuse that password elsewhere, change it on those accounts too — reply *REUSE* for a guided check\n"
            "→ Switch that account's 2FA from SMS codes to an authenticator app if possible"
        ),
    },
    "domain_phishing_breach": {
        "domain_lookalike": (
            "⚠️ *Heads up:* A lookalike domain has been registered near your business. "
            "Attackers who set up phishing domains often pair them with credential breach "
            "campaigns — your customers or employees may receive convincing phishing emails "
            "from this domain within the next 24–72 hours.\n\n"
            "Warn your team not to click unexpected login links."
        ),
        "breach_alert": (
            "⚠️ *Heads up:* A credential breach has been detected while a lookalike domain "
            "is active near your business. Attackers may direct breach victims to the fake "
            "domain to harvest additional credentials.\n\n"
            "Ensure all staff have changed passwords and enabled MFA."
        ),
    },
}


def check_and_warn_predictive(
    user_id: str,
    new_signal_type: str,
    signals: list,
    to_number: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
    max_warnings: int | None = None,
) -> None:
    signal_types = {s.get("type") for s in signals if isinstance(s, dict)}
    sent = 0
    for chain in ATTACK_CHAINS:
        if max_warnings is not None and sent >= max_warnings:
            break
        required = set(chain["signals"])
        if new_signal_type not in required:
            continue
        present = required & signal_types
        if len(present) != 1:
            continue
        warning = PREDICTIVE_WARNINGS.get(chain["chain"], {}).get(new_signal_type)
        if warning:
            send_whatsapp(to_number, warning, account_sid, auth_token, from_number)
            sent += 1


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


def _send_coordinated(
    to_number: str, body: str, account_sid: str, auth_token: str, from_number: str,
) -> bool:
    return send_whatsapp(to_number, body, account_sid, auth_token, from_number)


def _build_coordinated_alert(chain: dict, signals: list) -> str:
    now           = datetime.now(timezone.utc)
    chain_signals = chain["signals"]
    relevant      = sorted(
        [s for s in signals if isinstance(s, dict) and s.get("type") in chain_signals],
        key=lambda s: s.get("ts", ""),
    )

    lines = []
    for sig in relevant:
        try:
            ts  = datetime.fromisoformat(sig["ts"].replace("Z", "+00:00"))
            tsl = ts.strftime("%-d %b %H:%M UTC")
            age = _fmt_delta((now - ts).total_seconds())
        except Exception:
            tsl, age = "recently", ""
        label = sig["type"].replace("_", " ").title()
        lines.append(f"→ {label} — {tsl} ({age})" if age else f"→ {label} — {tsl}")

    # Inter-signal timeline for smishing_to_sim_swap
    timeline = ""
    if chain["chain"] == "smishing_to_sim_swap" and len(relevant) >= 2:
        try:
            t0     = datetime.fromisoformat(relevant[0]["ts"].replace("Z", "+00:00"))
            t1     = datetime.fromisoformat(relevant[1]["ts"].replace("Z", "+00:00"))
            gap_m  = int((t1 - t0).total_seconds() / 60)
            gap_h, gap_m = divmod(gap_m, 60)
            gap_str = f"{gap_h}h {gap_m}m" if gap_h else f"{gap_m}m"
            timeline = (
                f"\n*Attack timeline:* Smishing link sent {gap_str} before SIM swap "
                f"— confirming a two-stage attack sequence.\n"
            )
        except Exception:
            pass

    # Lookalike domains for domain_phishing_breach
    lookalike_block = ""
    if chain["chain"] == "domain_phishing_breach":
        for sig in relevant:
            if sig.get("type") == "domain_lookalike":
                lookalikes = sig.get("meta", {}).get("lookalikes", [])
                if lookalikes:
                    domain_lines = "\n".join(f"  • *{d}*" for d in lookalikes[:5])
                    lookalike_block = (
                        f"\n*Impersonating domain(s) detected:*\n{domain_lines}\n"
                        f"These domains may already be sending phishing emails "
                        f"to your employees and customers.\n"
                    )
                break

    # Attacker URLs for smishing_to_sim_swap
    url_block = ""
    if chain["chain"] == "smishing_to_sim_swap":
        for sig in relevant:
            if sig.get("type") == "suspicious_sms":
                urls = sig.get("meta", {}).get("urls", [])
                if urls:
                    url_lines = "\n".join(f"  • {u}" for u in urls[:5])
                    url_block = (
                        f"\n*Attacker link(s) from the phishing SMS:*\n{url_lines}\n"
                        f"Do not click these links.\n"
                    )
                break

    icon          = "🚨" if chain["severity"] == "CRITICAL" else "⚠️"
    signals_block = "\n".join(lines) if lines else "→ Multiple signals detected"

    if chain["severity"] == "CRITICAL":
        action_block = (
            f"*Act immediately — in this order:*\n"
            f"{_SESSIONS_INLINE}\n\n"
            f"2️⃣ Reply *SWEEP* — close email backdoors the attacker may have planted\n"
            f"3️⃣ Reply *PHONE* — lock your SIM against further swaps or ports\n"
            f"4️⃣ Do not enter any one-time codes you receive"
        )
    else:
        action_block = (
            f"*Act immediately — in this order:*\n"
            f"1️⃣ Reply *SESSIONS* — revoke all active sessions before changing passwords\n"
            f"2️⃣ Reply *SWEEP* — close email backdoors the attacker may have planted\n"
            f"3️⃣ Reply *PHONE* — lock your SIM against further swaps or ports\n"
            f"4️⃣ Do not enter any one-time codes you receive"
        )

    return (
        f"{icon} *{chain['severity']} — Coordinated Attack Detected*\n\n"
        f"RelayShield has identified a *{chain['label']}* attack pattern "
        f"targeting your identity.\n\n"
        f"*Signals detected:*\n{signals_block}\n"
        f"{timeline}"
        f"{lookalike_block}"
        f"{url_block}\n"
        f"*What this means:*\n{chain['what']}\n\n"
        f"{action_block}\n\n"
        f"Reply *RESOLVED* once you have completed the steps above to clear this alert.\n\n"
        f"🛡️ RelayShield — Coordinated Attack Detection"
    )


def check_and_fire_correlation(
    user_id: str,
    signals: list,
    to_number: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """
    Evaluate the current signal set against known attack chains.
    Sends a composite alert and stamps dedup timestamp if a chain is matched.
    Returns True if a composite alert was fired.
    """
    table        = dynamodb.Table(USERS_TABLE)
    signal_types = {s["type"] for s in signals if isinstance(s, dict)}

    for chain in ATTACK_CHAINS:
        if not chain["signals"].issubset(signal_types):
            continue

        last_ts = table.get_item(Key={"user_id": user_id}).get("Item", {}).get(
            "last_coordinated_alert_at", ""
        )
        if last_ts:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    last_ts.replace("Z", "+00:00")
                )).total_seconds()
                if age < CORRELATION_DEDUP_HOURS * 3600:
                    logger.info(
                        "Coordinated alert suppressed (dedup) — user_id=%s chain=%s",
                        user_id, chain["chain"],
                    )
                    continue
            except (ValueError, TypeError):
                pass

        sent = _send_coordinated(to_number, _build_coordinated_alert(chain, signals),
                                 account_sid, auth_token, from_number)
        if sent:
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET last_coordinated_alert_at = :t",
                ExpressionAttributeValues={":t": datetime.now(timezone.utc).isoformat()},
            )
            logger.warning("COORDINATED ALERT SENT — user_id=%s chain=%s", user_id, chain["chain"])
        else:
            logger.error("Coordinated alert FAILED — user_id=%s chain=%s", user_id, chain["chain"])
        return sent

    return False


# ---------------------------------------------------------------------------
# Twilio WhatsApp sender
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a WhatsApp message via Twilio REST API. Returns True on success."""
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To": to_whatsapp_number(to_number),
        "Body": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info(
                "WhatsApp sent to %s — SID: %s", to_number, result.get("sid")
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("Twilio send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Response message builders
# ---------------------------------------------------------------------------

def msg_ask_for_more_emails(emails_added: int, email_limit: int) -> str:
    remaining = email_limit - emails_added
    return (
        f"✅ Got it. You have {remaining} email slot{'s' if remaining != 1 else ''} "
        f"remaining.\n\n"
        f"Send another email address to monitor, or reply *DONE* to continue."
    )


def msg_ask_password_manager() -> str:
    return (
        "One quick question to personalise your protection:\n\n"
        "Do you use a password manager like *Bitwarden*, *1Password*, *LastPass*, *Dashlane*, or *Proton Pass*?\n\n"
        "Reply *YES* or *NO*."
    )


def msg_onboarding_complete(email_limit: int, is_business: bool) -> str:
    business_note = (
        "\n\nTo add a team member, reply *ADD* followed by their phone number "
        "(e.g. *ADD +16175551234*). They'll receive their own onboarding message."
        if is_business else ""
    )
    return (
        "🛡️ *You're all set.*\n\n"
        "Your first breach scan runs within the hour. If I find anything, "
        "I'll alert you here with a severity score and walk you through exactly what to do.\n\n"
        "⚠️ *One thing to know before you go:*\n"
        "Attackers increasingly use WhatsApp to impersonate banks, carriers, and "
        "family members — often enabling disappearing messages to destroy evidence. "
        "Three rules that will protect you:\n"
        "→ RelayShield will never ask for an OTP, PIN, or password — ever\n"
        "→ Screenshot any WhatsApp message asking for money or a verification code "
        "before you do anything else\n"
        "→ If a message feels urgent, that urgency is the attack — slow down and verify "
        "through a separate channel\n\n"
        "Reply *VERIFY* to get your personal verification protocol (four rules to share "
        "with your family now), *WASCAM* if you receive a suspicious WhatsApp message, "
        "*OTP* if you receive an unexpected verification code, "
        f"or *HELP* any time to see all available commands.{business_note}"
    )


def msg_help(is_business: bool, is_employee: bool = False, is_domain_tier: bool = False, has_seats: bool = True) -> str:
    commands = (
        "*🛡️ RelayShield — Commands*\n\n"

        "*🔐 Breach Response*\n"
        "• *SWEEP* — Close email backdoors (forwarding rules, filters, sessions)\n"
        "• *SESSIONS* — Revoke active sessions across Google, Microsoft, social media\n"
        "• *OAUTH* — Audit third-party app access\n"
        "• *RESET* — Strong password guide\n"
        "• *REUSE* — Check cross-account password reuse\n"
        "• *MANAGER* — Free password manager setup guide\n"
        "• *RESOLVED* — Mark an incident as resolved\n\n"

        "*🚨 Threat Analysis*\n"
        "• *SMS* <text> — Analyse a suspicious text message\n"
        "• *EMAIL* <text> — Analyse a suspicious email\n"
        "• *ATTACH* <url> — Scan a suspicious file or URL\n"
        "• *OTP* — You received an unexpected verification code\n"
        "• *WASCAM* — Suspicious WhatsApp, call, or browser scam\n"
        "• *CALL* — You received a suspicious phone call\n"
        "• *VERIFY* — Callback rule, OTP rule, safe word, wire transfer protocol\n"
        "• *SAFE* — Confirm you have read a security warning\n\n"

        "*📡 Phone Protection*\n"
        "• *PHONE* — Carrier hardening against SIM swap and smishing\n"
    )

    if is_business and not is_employee and has_seats:
        commands += (
            "\n*🏢 Team Management*\n"
            "• *ADD +1XXXXXXXXXX Name* — Add a team member\n"
            "• *REMOVE +1XXXXXXXXXX* — Remove a team member\n"
            "• *STATUS* — View team onboarding and monitoring status\n"
        )

    if is_domain_tier:
        commands += (
            "\n*🌐 Domain Security*\n"
            "• *DOMAIN* — Your domain security status\n"
            "• *DOMAIN SCAN* — Run a full scan (lookalikes, MX records, expiry)\n"
        )
        if not is_employee:
            commands += (
                "• *DOMAIN REGISTER domain.com* — Add a domain to monitor\n"
                "• *DOMAIN WARN lookalike.com* — Broadcast a phishing domain warning\n"
            )

    commands += "\nReply any command to get started."
    return commands


def msg_oauth(is_business: bool = False, is_employee: bool = False) -> str:
    """
    OAUTH command — guided OAuth grant audit for Google and Microsoft.
    Tiered: Personal Shield gets individual guidance; Business Basic+ admins
    get additional team and Google Workspace admin steps.
    """
    base = (
        "🔐 *OAuth Security Audit — Connected Apps*\n\n"
        "Third-party apps with access to your Google or Microsoft account can be used "
        "to breach you even without your password. An attacker who compromises a connected "
        "app inherits its OAuth access to your account — no credentials needed.\n\n"
        "*Step 1 — Audit Google OAuth grants*\n"
        "→ Go to: myaccount.google.com/permissions\n"
        "→ Remove anything you don't recognise, no longer actively use, or that has "
        "broader access than it needs\n\n"
        "*Step 2 — Audit Microsoft OAuth grants*\n"
        "→ Go to: myapps.microsoft.com\n"
        "→ Same process — remove unrecognised or unnecessary apps\n\n"
        "*What to remove immediately:*\n"
        "→ AI tools and productivity apps you no longer use\n"
        "→ Any app requesting *Read all mail* or *Read all files* you don't actively rely on\n"
        "→ Developer tools, integrations, and bots with broad scopes\n"
        "→ Apps you haven't used in 6+ months\n\n"
        "*Rule:* If you don't recognise it or don't need it — revoke it now.\n\n"
        "Run this audit every 90 days. Reply *SWEEP* to also close email backdoors.\n\n"
        "🛡️ RelayShield"
    )

    if is_business and not is_employee:
        team_block = (
            "\n\n*For your team (admin):*\n"
            "→ Each team member should run this same audit on their work accounts\n"
            "→ Google Workspace admins: review org-wide OAuth grants at "
            "admin.google.com → Security → API controls → Manage third-party app access\n"
            "→ AI tools with broad OAuth access are the highest-risk grants — "
            "review these first\n"
            "→ Reply *STATUS* to see which team members have completed onboarding"
        )
        return base + team_block

    return base


def msg_sweep() -> str:
    return (
        "🔍 *Email Security Sweep — 5 minutes to close the backdoors*\n\n"
        "Attackers plant these after a breach. They survive password resets.\n\n"
        "*Step 1 — Check email forwarding rules*\n"
        "Gmail: Settings → See all settings → Forwarding and POP/IMAP\n"
        "Outlook: Settings → Mail → Forwarding\n"
        "Yahoo: Settings → Mailboxes → your address → Forwarding\n"
        "→ Delete any rule you did not create.\n\n"
        "*Step 2 — Check recovery email and phone*\n"
        "Gmail: myaccount.google.com/security\n"
        "Yahoo: account.yahoo.com/security\n"
        "→ Remove any recovery contact you do not recognise.\n\n"
        "*Step 3 — Check inbox filters*\n"
        "Silent rules that hide breach warnings and delete bank alerts.\n"
        "Gmail: Settings → Filters and Blocked Addresses\n"
        "→ Delete any filter you did not create.\n"
        "Outlook: Settings → Rules → delete unknown rules.\n\n"
        "*Step 4 — Review connected apps*\n"
        "Gmail: myaccount.google.com/permissions\n"
        "Yahoo: account.yahoo.com/security/connected-apps\n"
        "→ Revoke anything unrecognised.\n\n"
        "*Step 5 — Check active sessions*\n"
        "Gmail: myaccount.google.com/device-activity\n"
        "Yahoo: account.yahoo.com/security/recent-activity\n"
        "→ Sign out of all unknown sessions.\n\n"
        "✅ *Sweep complete. All 5 checks done.*\n\n"
        "*Going forward — use a masked email alias*\n"
        "Your real address is a breach risk every time you share it. "
        "A masked alias forwards to your inbox — if it leaks, delete it.\n"
        "→ *SimpleLogin* — free, open source (simplelogin.io)\n"
        "→ *Apple Hide My Email* — built into iCloud\n"
        "→ *Gmail* — youraddress+sitename@gmail.com as a free workaround\n\n"
        "Reply *RESET* for a strong password guide.\n"
        "Reply *MANAGER* for a free Bitwarden setup guide."
    )


def msg_reset() -> str:
    return (
        "🔑 *Strong Password Guide — reset after your sweep*\n\n"
        "Now that you have closed every inbox backdoor, reset your password for "
        "the breached service.\n\n"
        "*Rules for a strong password:*\n"
        "→ Minimum 16 characters\n"
        "→ Use a passphrase: 3 random words + a number + a symbol "
        "(e.g. *Coffee-Balloon-River7!*)\n"
        "→ Never reuse this password on any other service\n"
        "→ Never share it — not by SMS, not by call, not by email\n\n"
        "*Where to reset:*\n"
        "Go directly to the breached service's website — "
        "do not click a reset link in an email unless you requested it yourself.\n\n"
        "*After resetting:*\n"
        "→ Enable two-factor authentication (use an authenticator app, not SMS if possible)\n"
        "→ If you reused this password elsewhere, change it on those accounts too\n\n"
        "Reply *MANAGER* to set up Bitwarden — a free password manager that generates and "
        "remembers strong unique passwords for every service.\n\n"
        "Reply *HELP* to see all available commands."
    )


def msg_reuse_step(step_index: int, flagged: list[str] | None = None) -> str:
    """Return the cross-account reuse check for a given step index."""
    if step_index >= len(CROSS_ACCOUNT_SERVICES):
        flagged = flagged or []
        if not flagged:
            return (
                "✅ *Cross-account check complete.*\n\n"
                "No reused passwords flagged — good discipline.\n\n"
                "Reply *MANAGER* to set up Bitwarden so every account "
                "gets a unique password automatically."
            )
        flagged_list = "\n".join(f"→ {svc}" for svc in flagged)
        return (
            "⚠️ *Cross-account check complete.*\n\n"
            f"You flagged {len(flagged)} account(s) using the same password:\n\n"
            f"{flagged_list}\n\n"
            "*Change each of these now* — go directly to the service website, "
            "not via any email link. Use a unique password for each one.\n\n"
            "Reply *MANAGER* to set up Bitwarden — it generates and remembers "
            "strong unique passwords for every account so this never happens again."
        )
    service, risk = CROSS_ACCOUNT_SERVICES[step_index]
    return (
        f"*Account {step_index + 1} of {len(CROSS_ACCOUNT_SERVICES)}*\n\n"
        f"*{service}*\n"
        f"_{risk}_\n\n"
        f"Did you use the same password here as the breached account?\n"
        f"Reply *YES* to flag it for a change, or *NO* to continue."
    )


def msg_manager() -> str:
    return (
        "🔐 *Free Password Manager Setup — Bitwarden*\n\n"
        "Bitwarden is free, open-source, and independently audited. "
        "Here's how to get started in 5 minutes:\n\n"
        "*Step 1* — Go to bitwarden.com and create a free account\n"
        "*Step 2* — Choose a strong master password (use a passphrase: "
        "3 random words + a number)\n"
        "*Step 3* — Install the browser extension (Chrome/Firefox/Safari)\n"
        "*Step 4* — Install the mobile app (iOS or Android)\n"
        "*Step 5* — Enable biometric unlock (Face ID / fingerprint)\n"
        "*Step 6* — As you log into sites, let Bitwarden save each password\n"
        "*Step 7* — Enable the Bitwarden breach report "
        "(Tools → Breach Report in the web vault)\n\n"
        "💡 *Master password tip:* Write it on paper and store it somewhere "
        "physically safe — not in email.\n\n"
        "Reply *HELP* to see all available commands."
    )


def msg_phone_hardening(subscription_tier: str) -> str:
    base = (
        "📱 *Phone Number Protection — Carrier Hardening Steps*\n\n"
        "Your phone number is a target for two related attacks:\n"
        "→ *SIM swap* — attacker convinces your carrier to move your number to their SIM, "
        "intercepting every SMS code you receive\n"
        "→ *Smishing* — fraudulent texts impersonate your bank, carrier, or delivery services "
        "to steal credentials or carrier PINs. Attackers often use smishing to gather the "
        "information needed to execute a SIM swap.\n\n"
        "These steps lock your carrier account against both attacks.\n\n"
        "⚠️ *Your carrier will never text or call asking for your PIN. "
        "Any message asking for it is an attack.*\n\n"
    )
    if subscription_tier in (TIER_SHIELD, TIER_PRO):
        # Shield and Pro: full carrier-specific steps including eSIM audit guidance
        carrier_steps = (
            "*AT&T*\n"
            "→ Enable Wireless Account Lock: att.com/accountlock\n"
            "→ Add a passcode to your account\n"
            "→ Review eSIM profiles: myAT&T app → Account → Device Management\n\n"
            "*T-Mobile*\n"
            "→ Enable SIM Protection: account.t-mobile.com → Profile → SIM Protection\n"
            "→ Set a PIN/passcode on your account\n"
            "→ Audit eSIM Profiles: T-Mobile app → Account → SIM & eSIM\n\n"
            "*Verizon*\n"
            "→ Enable Number Lock: verizon.com/myverizon → Account → Number Lock\n"
            "→ Set a PIN/passcode on your account\n"
            "→ Review eSIM: My Verizon app → Devices → Manage eSIM\n\n"
            "*All carriers*\n"
            "→ Never give out your account PIN on a phone call — carriers will never ask\n"
            "→ Set a unique carrier PIN not used anywhere else\n"
        )
    elif subscription_tier in (TIER_STARTER, TIER_BASIC):
        # Starter and Basic: carrier-specific lock steps, no eSIM audit guidance
        carrier_steps = (
            "*AT&T*\n"
            "→ Enable Wireless Account Lock: att.com/accountlock\n"
            "→ Add a passcode to your account\n\n"
            "*T-Mobile*\n"
            "→ Enable SIM Protection: account.t-mobile.com → Profile → SIM Protection\n"
            "→ Set a PIN/passcode on your account\n\n"
            "*Verizon*\n"
            "→ Enable Number Lock: verizon.com/myverizon → Account → Number Lock\n"
            "→ Set a PIN/passcode on your account\n\n"
            "*All carriers*\n"
            "→ Never give out your account PIN on a phone call — carriers will never ask\n"
            "→ Set a unique carrier PIN not used anywhere else\n\n"
            "💡 Business Shield plans include eSIM profile audit guidance "
            "to detect silent backdoor SIM cloning."
        )
    else:
        # Personal: concise guidance with upsell note
        carrier_steps = (
            "*Lock your carrier account:*\n"
            "• AT&T: att.com/accountlock\n"
            "• T-Mobile: Account → Profile → SIM Protection\n"
            "• Verizon: verizon.com/myverizon → Number Lock\n\n"
            "→ Set a unique PIN/passcode on your carrier account\n"
            "→ Never share your account PIN — carriers will never call to ask for it\n\n"
            "💡 Business Shield plans include full carrier hardening walkthroughs "
            "and eSIM profile audit guidance."
        )
    return base + carrier_steps + "\n\nReply *HELP* to see all available commands."


def msg_employee_welcome(admin_tier: str) -> str:
    email_limit = EMAIL_LIMITS.get(admin_tier, 2)
    return (
        "🛡️ *Welcome to RelayShield — your employer has added you for protection.*\n\n"
        "I'm an AI security assistant. I'll monitor your work credentials, "
        "alert you here if anything is found, and walk you through every fix.\n\n"
        f"To get started: what's your work email address? "
        f"You can add up to {email_limit} addresses."
    )


def msg_vishing_safe() -> str:
    return (
        "✅ *Good. You are prepared.*\n\n"
        "Keep these rules in mind for any unexpected call:\n"
        "→ Never confirm personal details to an inbound caller\n"
        "→ Never read an OTP code — no legitimate company asks for this\n"
        "→ Hang up and call back on the official number\n"
        "→ Urgency is the attack — slow down\n\n"
        "Reply *SWEEP* to run your Email Security Sweep, or *HELP* to see all commands."
    )


def msg_resolved() -> str:
    """
    RESOLVED command — user confirms they have completed remediation steps.
    Clears breach_alert signals from recent_signals to prevent re-triggering
    coordinated attack alerts for the same incident.
    """
    return (
        "✅ *Incident marked as resolved.*\n\n"
        "Your breach alert signals have been cleared. RelayShield will continue "
        "monitoring your accounts and will alert you if new threats are detected.\n\n"
        "*Stay protected:*\n"
        "→ Run *SWEEP* any time to re-check for email backdoors\n"
        "→ Run *REUSE* to verify no other accounts are at risk\n"
        "→ Run *OAUTH* to audit connected apps\n\n"
        "🛡️ RelayShield"
    )


def msg_verify() -> str:
    """
    VERIFY command — Personal Verification Protocol.
    Four rules to establish before an attack, not after.
    All tiers. Share with family.
    """
    return (
        "🔐 *Personal Verification Protocol — RelayShield*\n\n"
        "Set these four rules with your family *before* an attack — "
        "not after. Attackers are trained to bypass your instincts in the moment.\n\n"
        "*Rule 1 — Callback Rule*\n"
        "If anyone calls claiming to be your bank, carrier, or the IRS: hang up. "
        "Call the official number on the back of your card or their website. "
        "Never call back a number they give you.\n\n"
        "*Rule 2 — OTP Rule*\n"
        "No legitimate organisation will ever ask you to read an OTP back to them. "
        "If anyone asks — hang up immediately. You are being socially engineered.\n\n"
        "*Rule 3 — Family Safe Word*\n"
        "Choose a word only your family knows. If anyone calls claiming to be a "
        "family member in distress, they must say the word — or you hang up. "
        "Discuss and agree on this word with your family today.\n\n"
        "*Rule 4 — Wire Transfer Rule*\n"
        "No legitimate contact will ever ask you to redirect a wire transfer or "
        "change bank details by phone or email alone. Always verify by calling "
        "a known number directly — never one they provide.\n\n"
        "📲 *Forward this message to your family now* — these rules only work "
        "if everyone knows them before the call comes.\n\n"
        "Reply *CALL* if you received a suspicious call.\n"
        "Reply *WASCAM* if you received a suspicious WhatsApp message.\n\n"
        "🛡️ RelayShield"
    )


def msg_vishing_call() -> str:
    return (
        "🚨 *If you believe you have received a vishing call — act now.*\n\n"
        "*Step 1 — Do not call them back on any number they gave you.*\n"
        "Look up the official number on the company's website independently.\n\n"
        "*Step 2 — Did you share any of these?*\n"
        "→ OTP or verification code → Contact the service immediately to lock your account\n"
        "→ Bank details → Call your bank's fraud line from the number on your card\n"
        "→ Account PIN or password → Change it now before doing anything else\n"
        "→ Remote access granted → Disconnect internet, contact your bank and carrier\n\n"
        "*Step 3 — Report the call*\n"
        "→ FTC (US): reportfraud.ftc.gov\n"
        "→ FCC (carrier impersonation): fcc.gov/consumers/guides/filing-informal-complaint\n"
        "→ Your carrier fraud line: AT&T 1-800-331-0500 / T-Mobile 1-877-778-2106 / Verizon 1-800-922-0204\n\n"
        "*Step 4 — Run your Email Security Sweep*\n"
        "Vishing often runs alongside inbox takeover. Reply *SWEEP* to check for backdoors now.\n\n"
        "— RelayShield"
    )


def msg_unexpected_otp_part1() -> str:
    """
    Part 1 of 2: Unexpected OTP — immediate actions (Steps 1–3).
    Kept under 1600 chars to comply with Twilio WhatsApp message limit.
    """
    return (
        "🚨 *Unexpected OTP — an account takeover attempt may be in progress.*\n\n"
        "An OTP you did not request means someone is actively trying to log in to one "
        "of your accounts using your credentials right now.\n\n"
        "*Step 1 — Do NOT share the OTP with anyone.*\n"
        "No legitimate company — not your bank, not your carrier, not any tech support — "
        "will ever call or text asking you to read back an OTP. "
        "If anyone contacts you asking for this code, that contact is the attack.\n\n"
        "*Step 2 — Identify which service sent the OTP.*\n"
        "The sender name or message content will indicate the service. "
        "Go directly to that service by typing the URL — do not click any link in the text.\n\n"
        "⚠️ *If the OTP is a WhatsApp verification code — act immediately.*\n"
        "A stolen WhatsApp OTP gives an attacker full control of your account. "
        "They can read your messages, impersonate you to every contact, take over your groups, "
        "and use your identity to steal OTPs from people you know.\n"
        "Do NOT share the code. Enable Two-Step Verification: "
        "WhatsApp Settings → Account → Two-Step Verification."
    )


def msg_unexpected_otp_part2() -> str:
    """
    Part 2 of 2: Unexpected OTP — lock down and sweep (Steps 3–4).
    Kept under 1600 chars to comply with Twilio WhatsApp message limit.
    """
    return (
        "*🔒 Lock the account immediately*\n"
        "→ Change your password for that account now\n"
        "→ Check for active sessions you don't recognise — reply *SESSIONS* for a guided walkthrough\n"
        "→ If it's your bank — call the fraud line on the back of your card\n"
        "→ If it's your mobile carrier — call them immediately; this may be a SIM swap attempt\n\n"
        "*📧 Run your Email Security Sweep*\n"
        "If an attacker has your credentials, they may also have inbox access. "
        "Reply *SWEEP* to check for forwarding rules and backdoors.\n\n"
        "Reply *CALL* if you also received a suspicious phone call alongside this OTP.\n\n"
        "— RelayShield"
    )


def msg_wascam_part1() -> str:
    """
    Part 1 of 2: Suspicious WhatsApp message — financial and carrier fraud vectors.
    Covers bank impersonation, carrier impersonation, and family/friend scams.
    Kept under 1600 chars to comply with Twilio WhatsApp message limit.
    """
    return (
        "🚨 *Suspicious WhatsApp message — fraud pattern detected.*\n\n"
        "Match your situation below and act immediately.\n\n"

        "*🏦 Bank or financial institution impersonation*\n"
        "Signs: urgent message about a frozen account, suspicious transaction, or payment needed. "
        "Asks you to click a link, call a number, or share a verification code.\n"
        "→ Do not click any link — your bank will never contact you this way\n"
        "→ Do not call any number provided in the message\n"
        "→ Call your bank directly using the number on the back of your card\n"
        "→ Forward any link to RelayShield for analysis — reply *SMS* followed by the link\n\n"

        "*📡 Mobile carrier impersonation*\n"
        "Signs: message claiming your account is suspended, a SIM change was requested, "
        "or you need to verify your identity to avoid service interruption.\n"
        "→ This is a SIM swap setup — do not respond or click any link\n"
        "→ Call your carrier directly from the number on your bill\n"
        "→ Ask them to confirm no changes were requested on your account\n"
        "→ Reply *PHONE* for carrier PIN hardening steps to block this attack\n\n"

        "*👨‍👩‍👦 Family or friend impersonation (Hi Mum / Hi Dad)*\n"
        "Signs: message from an unknown number claiming to be a family member — "
        "'I lost my phone, this is my new number, I need money urgently.'\n"
        "→ Do not send money — this is one of the fastest-growing WhatsApp scams\n"
        "→ Call the family member directly on their known number to verify\n"
        "→ The real person will not be offended that you checked\n"
        "→ Screenshot the message before it disappears\n\n"
        "(continued...)"
    )


def msg_wascam_part2() -> str:
    """
    Part 2 of 2: Suspicious WhatsApp message — disappearing messages, verification, reporting.
    Kept under 1600 chars to comply with Twilio WhatsApp message limit.
    """
    return (
        "*⏱ Disappearing messages + urgency*\n"
        "If the sender has enabled disappearing messages, it is almost always deliberate — "
        "they are destroying evidence.\n"
        "→ Screenshot everything immediately before it disappears\n"
        "→ Urgency is the weapon — any message demanding you act within minutes is an attack\n"
        "→ Slow down, verify through a separate channel, then act\n\n"

        "*✅ How to verify any suspicious WhatsApp message*\n"
        "→ Call the person or organisation directly using a number you already have — "
        "not one provided in the message\n"
        "→ Check the sender's number — legitimate banks and carriers do not use personal "
        "WhatsApp numbers\n"
        "→ If a verification code arrived alongside the message, reply *OTP* immediately\n\n"

        "*📋 Report the scam*\n"
        "→ Screenshot the conversation before it disappears\n"
        "→ Report to WhatsApp: open the chat → tap the contact name → Report\n"
        "→ Report to the FTC (US): reportfraud.ftc.gov\n\n"

        "— RelayShield"
    )


def msg_wascam_part3() -> str:
    """
    Part 3 of 3: Browser-based social engineering patterns.
    Covers fake CAPTCHAs (SMS charge fraud), fake browser security alerts, and ClickFix.
    Kept under 1600 chars to comply with Twilio WhatsApp message limit.
    """
    return (
        "*🌐 Browser scams — when a webpage tries to manipulate you*\n\n"
        "These attacks happen in your browser, not WhatsApp. "
        "The pattern is the same: manufactured urgency to make you act before you think.\n\n"

        "*📱 Fake CAPTCHA — SMS charge fraud*\n"
        "A webpage asks you to 'prove you're human' by sending a text message. "
        "Tapping the button opens your SMS app pre-filled with international numbers. "
        "Each 'confirmation step' sends another text — victims can be charged up to $30 "
        "in international SMS fees before the bill arrives weeks later.\n"
        "→ Legitimate CAPTCHAs never ask you to send a text message\n"
        "→ Close the page immediately\n\n"

        "*🖥️ Fake browser security alert*\n"
        "A full-screen pop-up claims your computer is infected and displays a phone number "
        "to call 'immediately'. The number connects to a scam call centre.\n"
        "→ Legitimate browsers and Microsoft never display phone numbers in security alerts\n"
        "→ Close the tab — if the page blocks closing, force-quit the browser\n\n"

        "*💻 ClickFix — paste-and-run attack*\n"
        "A page instructs you to open your terminal or Windows Run dialog and paste a "
        "command 'to fix a problem' or 'verify your identity'. The command installs malware.\n"
        "→ No legitimate website will ever ask you to run a command on your computer\n"
        "→ Close the page immediately and do not paste anything\n\n"

        "The rule across all three: *legitimate services never ask you to send a text, "
        "run a command, or call a number to prove you are human.*\n\n"
        "— RelayShield"
    )


def msg_sessions() -> str:
    """
    Guided active session revocation across Google, Microsoft, and social media.
    Triggered by SESSIONS command or when session token exposure detected in a breach.
    Critical ordering note: revoke BEFORE changing password so attacker is forced
    out immediately regardless of whether they already have the password.
    """
    return (
        "🔐 *Active Session Audit — revoke access before an attacker uses it*\n\n"
        "A stolen session token gives full account access — no password or 2FA needed. "
        "Complete all 4 steps in order.\n\n"
        "*Step 1 — Google: sign out unknown devices*\n"
        "→ myaccount.google.com/device-activity\n"
        "→ Sign out of every device you don't recognise\n\n"
        "*Step 2 — Google: revoke third-party app access*\n"
        "→ myaccount.google.com/permissions\n"
        "→ Remove any app you don't recognise or no longer use\n\n"
        "*Step 3 — Microsoft: sign out unknown sessions*\n"
        "→ account.microsoft.com/privacy/activity\n"
        "→ Sign out of all unknown sessions\n"
        "→ account.microsoft.com/permissions → remove unknown apps\n\n"
        "*Step 4 — Social media*\n"
        "Facebook: Settings → Security and Login → Where You're Logged In\n"
        "Instagram: Settings → Security → Login Activity\n"
        "→ Log out of all sessions you don't recognise\n\n"
        "⚠️ *Complete steps 1–3 BEFORE changing your password.*\n"
        "Revoking the session forces the attacker out immediately.\n"
        "Changing the password first does nothing if they already have your session token.\n\n"
        "✅ *Session audit complete.*\n\n"
        "Reply *SWEEP* to also check for email backdoors (forwarding rules, rogue recovery options).\n"
        "Reply *HELP* to see all available commands.\n\n"
        "— RelayShield"
    )


def msg_unknown_command() -> str:
    return (
        "I didn't recognise that command.\n\n"
        "Reply *HELP* to see everything I can do."
    )


# ---------------------------------------------------------------------------
# Onboarding handlers
# ---------------------------------------------------------------------------

def handle_awaiting_email_1(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """First email address — validate, store, ask for more or move on."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    email_limit = EMAIL_LIMITS.get(tier, 3)
    to_number = get_user_whatsapp_number(user)
    email = message_body.strip().lower()

    if not is_valid_email(email):
        reply = (
            "That doesn't look like a valid email address. "
            "Please send your email address (e.g. *name@example.com*)."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "invalid_email"

    add_monitored_email(user_id, email)

    # Auto-register business domain from first email for domain-monitoring tiers.
    # Free provider addresses (gmail.com etc.) are skipped automatically.
    if not bool(user.get("admin_user_id")):   # admin accounts only
        domain = auto_register_domain(user_id, email, tier)
        if domain:
            logger.info("Domain auto-registered at onboarding: domain=%s user_id=%s", domain, user_id)

    if email_limit == 1:
        # Edge case: move straight to password manager question
        update_user(user_id, {
            "onboarding_state": STATE_PASSWORD_MANAGER,
            "emails_added": 1,
        })
        send_whatsapp(to_number, msg_ask_password_manager(), account_sid, auth_token, from_number)
    else:
        update_user(user_id, {
            "onboarding_state": STATE_MORE_EMAILS,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(1, email_limit),
            account_sid, auth_token, from_number,
        )
    return "email_1_added"


def handle_awaiting_more_emails(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Subsequent emails or DONE command."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    email_limit = EMAIL_LIMITS.get(tier, 3)
    emails_added = int(user.get("emails_added", 1))
    to_number = get_user_whatsapp_number(user)
    body = message_body.strip()

    if body.upper() == "DONE":
        update_user(user_id, {"onboarding_state": STATE_PASSWORD_MANAGER})
        send_whatsapp(to_number, msg_ask_password_manager(), account_sid, auth_token, from_number)
        return "done_collecting_emails"

    email = body.lower()
    if not is_valid_email(email):
        reply = (
            "That doesn't look like a valid email address.\n\n"
            "Send another email to monitor, or reply *DONE* to continue."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "invalid_email"

    if email_already_monitored(user_id, email):
        reply = (
            f"*{email}* is already being monitored.\n\n"
            "Send another email, or reply *DONE* to continue."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "duplicate_email"

    add_monitored_email(user_id, email)
    emails_added += 1

    if emails_added >= email_limit:
        # Tier limit reached — move to next stage automatically
        update_user(user_id, {
            "onboarding_state": STATE_PASSWORD_MANAGER,
            "emails_added": emails_added,
        })
        limit_msg = (
            f"✅ *{email}* added. You've reached your {email_limit}-email limit.\n\n"
        )
        send_whatsapp(
            to_number,
            limit_msg + msg_ask_password_manager(),
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {"emails_added": emails_added})
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(emails_added, email_limit),
            account_sid, auth_token, from_number,
        )
    return f"email_{emails_added}_added"


def handle_awaiting_password_manager(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """YES/NO password manager question."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    to_number = get_user_whatsapp_number(user)
    body = message_body.strip().upper()

    if body not in ("YES", "NO"):
        send_whatsapp(
            to_number,
            "Please reply *YES* or *NO* — do you use a password manager?",
            account_sid, auth_token, from_number,
        )
        return "invalid_response"

    pm_user = body == "YES"
    update_user(user_id, {
        "onboarding_state": STATE_ACTIVE,
        "password_manager_user": pm_user,
    })

    is_business = tier in BUSINESS_TIERS
    email_limit = EMAIL_LIMITS.get(tier, 3)
    completion_msg = msg_onboarding_complete(email_limit, is_business)

    if pm_user:
        completion_msg += (
            "\n\n💡 Since you use a password manager, I'll include a master password "
            "alert if your credentials ever appear in a breach."
        )

    send_whatsapp(to_number, completion_msg, account_sid, auth_token, from_number)
    logger.info(
        "Onboarding complete — user_id=%s tier=%s pm_user=%s",
        user_id, tier, pm_user,
    )
    return "onboarding_complete"


# ---------------------------------------------------------------------------
# Employee onboarding handlers
# ---------------------------------------------------------------------------

def handle_employee_email_1(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Employee first email collection."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    admin_user_id = user.get("admin_user_id", "")
    tier = user.get("subscription_tier", TIER_BASIC)
    email_limit = EMAIL_LIMITS.get(tier, 2)
    to_number = get_user_whatsapp_number(user)
    email = message_body.strip().lower()

    if not is_valid_email(email):
        send_whatsapp(
            to_number,
            "That doesn't look like a valid email. Please send your work email address.",
            account_sid, auth_token, from_number,
        )
        return "invalid_email"

    add_monitored_email(user_id, email)

    if email_limit == 1:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_ACTIVE,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            "✅ You're all set. I'll alert you here if your credentials appear in a breach.",
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_MORE_EMAILS,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(1, email_limit),
            account_sid, auth_token, from_number,
        )
    return "employee_email_1_added"


def handle_employee_more_emails(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Employee additional email or DONE."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_BASIC)
    email_limit = EMAIL_LIMITS.get(tier, 2)
    emails_added = int(user.get("emails_added", 1))
    to_number = get_user_whatsapp_number(user)
    body = message_body.strip()

    if body.upper() == "DONE":
        update_user(user_id, {"onboarding_state": STATE_EMP_ACTIVE})
        send_whatsapp(
            to_number,
            "✅ You're all set. I'll alert you here if your credentials appear in a breach.\n\n"
            "Reply *HELP* to see available commands.",
            account_sid, auth_token, from_number,
        )
        return "employee_done"

    email = body.lower()
    if not is_valid_email(email):
        send_whatsapp(
            to_number,
            "That doesn't look like a valid email. Send another or reply *DONE* to continue.",
            account_sid, auth_token, from_number,
        )
        return "invalid_email"

    if email_already_monitored(user_id, email):
        send_whatsapp(
            to_number,
            f"*{email}* is already being monitored. Send another or reply *DONE*.",
            account_sid, auth_token, from_number,
        )
        return "duplicate_email"

    add_monitored_email(user_id, email)
    emails_added += 1

    if emails_added >= email_limit:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_ACTIVE,
            "emails_added": emails_added,
        })
        send_whatsapp(
            to_number,
            f"✅ *{email}* added. You've reached your {email_limit}-email limit. "
            "I'll alert you here if your credentials appear in a breach.\n\n"
            "Reply *HELP* to see available commands.",
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {"emails_added": emails_added})
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(emails_added, email_limit),
            account_sid, auth_token, from_number,
        )
    return f"employee_email_{emails_added}_added"


# ---------------------------------------------------------------------------
# Active command handlers
# ---------------------------------------------------------------------------

def handle_active_message(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
    media_info: dict | None = None,
) -> str:
    """Route commands for fully onboarded users."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    to_number = get_user_whatsapp_number(user)
    is_business = tier in BUSINESS_TIERS
    is_employee = bool(user.get("admin_user_id"))
    body = message_body.strip().upper()
    media_info = media_info or {}
    num_media = int(media_info.get("num_media", 0))

    # --- Pending Claude analysis delivery ---
    # If the breach monitor stored an analysis that couldn't be sent due to
    # Twilio 63016 (no active session at alert time), deliver it now.
    # The user's reply opens the session window. We return immediately after
    # delivery so command routing doesn't fire on the triggering message.
    # REMOVE is used instead of SET "" because DynamoDB may silently reject
    # empty string writes depending on the SDK version in the Lambda runtime.
    pending_analysis = user.get("pending_analysis", "")
    if pending_analysis:
        send_whatsapp(to_number, pending_analysis, account_sid, auth_token, from_number)
        _table = dynamodb.Table(USERS_TABLE)
        _table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="REMOVE pending_analysis SET updated_at = :t",
            ExpressionAttributeValues={
                ":t": datetime.now(timezone.utc).isoformat()
            },
        )
        logger.info("Delivered pending Claude analysis to user_id=%s.", user_id)
        return "pending_analysis_delivered"

    # --- WhatsApp file attachment — VirusTotal file scan ---
    # Triggered when user sends a file (PDF, zip, doc, image) directly via WhatsApp.
    # Twilio populates NumMedia + MediaUrl0 + MediaContentType0 in the POST body.
    # Lambda timeout must be 60 s to accommodate worst-case VT file analysis.
    if num_media > 0:
        media_url = media_info.get("media_url", "")
        media_content_type = media_info.get("media_content_type", "application/octet-stream")
        filename = VT_FILENAME_MAP.get(media_content_type, "attachment.bin")

        send_whatsapp(
            to_number,
            "📎 *RelayShield is scanning that file...* This may take up to 30 seconds.",
            account_sid, auth_token, from_number,
        )
        try:
            vt_api_key = get_vt_api_key()
            file_bytes = download_twilio_media(media_url, account_sid, auth_token)
            if file_bytes:
                analysis_id = submit_file_to_vt(file_bytes, filename, media_content_type, vt_api_key)
                stats = poll_vt_analysis(analysis_id, vt_api_key, max_wait=VT_FILE_MAX_WAIT) if analysis_id else None
            else:
                stats = None
        except Exception as exc:
            logger.error("VT file scan pipeline failed: %s", exc)
            stats = None

        verdict = build_vt_verdict_response(stats, "that file")
        send_whatsapp(to_number, verdict, account_sid, auth_token, from_number)
        logger.info(
            "VT file scan complete — content_type=%s stats=%s",
            media_content_type, stats,
        )
        return "vt_file_scanned"

    # --- SWEEP ---
    if body == "SWEEP":
        send_whatsapp(to_number, msg_sweep(), account_sid, auth_token, from_number)
        return "sweep_sent"

    # --- RESET ---
    if body == "RESET":
        send_whatsapp(to_number, msg_reset(), account_sid, auth_token, from_number)
        return "reset_sent"

    # --- REUSE ---
    if body == "REUSE":
        reuse_step = int(user.get("reuse_step", 0))
        update_user(user_id, {"reuse_step": 1})
        send_whatsapp(
            to_number, msg_reuse_step(0), account_sid, auth_token, from_number
        )
        return "reuse_started"

    # --- REUSE YES/NO continuation ---
    if body in ("YES", "NO"):
        reuse_step = int(user.get("reuse_step", 0))
        if reuse_step > 0:
            # Load existing flagged list
            try:
                flagged = json.loads(user.get("reuse_flagged") or "[]")
            except (json.JSONDecodeError, TypeError):
                flagged = []

            # The step the user just answered is reuse_step - 1
            answered_index = reuse_step - 1
            if body == "YES" and answered_index < len(CROSS_ACCOUNT_SERVICES):
                flagged.append(CROSS_ACCOUNT_SERVICES[answered_index][0])

            next_step = reuse_step  # next step to display (0-based index)
            at_end = next_step >= len(CROSS_ACCOUNT_SERVICES)

            updates = {
                "reuse_step": 0 if at_end else next_step + 1,
                "reuse_flagged": json.dumps(flagged),
            }
            update_user(user_id, updates)
            send_whatsapp(
                to_number,
                msg_reuse_step(next_step, flagged),
                account_sid, auth_token, from_number,
            )
            return f"reuse_step_{next_step}_answered"

    # --- MANAGER ---
    if body == "MANAGER":
        send_whatsapp(to_number, msg_manager(), account_sid, auth_token, from_number)
        return "manager_sent"

    # --- PHONE ---
    if body == "PHONE":
        send_whatsapp(
            to_number, msg_phone_hardening(tier), account_sid, auth_token, from_number
        )
        return "phone_hardening_sent"

    # --- SESSIONS (active session revocation walkthrough) ---
    if body == "SESSIONS":
        send_whatsapp(to_number, msg_sessions(), account_sid, auth_token, from_number)
        return "sessions_audit_sent"

    # --- OAUTH (OAuth grant audit — Google + Microsoft connected apps) ---
    if body == "OAUTH":
        send_whatsapp(
            to_number,
            msg_oauth(is_business=is_business, is_employee=is_employee),
            account_sid, auth_token, from_number,
        )
        return "oauth_audit_sent"

    # --- SAFE (vishing warning acknowledged) ---
    if body == "SAFE":
        send_whatsapp(to_number, msg_vishing_safe(), account_sid, auth_token, from_number)
        return "vishing_safe_ack"

    # --- CALL (user received a suspicious call) ---
    if body == "CALL":
        send_whatsapp(to_number, msg_vishing_call(), account_sid, auth_token, from_number)
        return "vishing_call_reported"

    # --- VERIFY (personal verification protocol — four rules to set before an attack) ---
    if body == "VERIFY":
        send_whatsapp(to_number, msg_verify(), account_sid, auth_token, from_number)
        return "verify_protocol_sent"

    # --- RESOLVED (user confirms remediation complete — clears breach signals) ---
    if body == "RESOLVED":
        try:
            table    = dynamodb.Table(USERS_TABLE)
            existing = table.get_item(Key={"user_id": user_id}).get("Item", {}).get("recent_signals", [])
            cleared  = [s for s in existing if isinstance(s, dict) and s.get("type") != "breach_alert"]
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET recent_signals = :s",
                ExpressionAttributeValues={":s": cleared},
            )
            logger.info("Breach signals cleared — user_id=%s remaining_signals=%d", user_id, len(cleared))
        except Exception as exc:
            logger.exception("Failed to clear breach signals user_id=%s: %s", user_id, exc)
        send_whatsapp(to_number, msg_resolved(), account_sid, auth_token, from_number)
        return "incident_resolved"

    # --- OTP (user received an unexpected OTP they did not request) ---
    if body == "OTP":
        send_whatsapp(to_number, msg_unexpected_otp_part1(), account_sid, auth_token, from_number)
        send_whatsapp(to_number, msg_unexpected_otp_part2(), account_sid, auth_token, from_number)
        try:
            signals = record_signal(user_id, "otp_warning")
            check_and_warn_predictive(user_id, "otp_warning", signals, to_number, account_sid, auth_token, from_number)
            check_and_fire_correlation(user_id, signals, to_number, account_sid, auth_token, from_number)
        except Exception as exc:
            logger.exception("Coordinated attack check failed user_id=%s: %s", user_id, exc)
        return "unexpected_otp_reported"

    # --- WASCAM (user received a suspicious WhatsApp message) ---
    if body == "WASCAM":
        send_whatsapp(to_number, msg_wascam_part1(), account_sid, auth_token, from_number)
        send_whatsapp(to_number, msg_wascam_part2(), account_sid, auth_token, from_number)
        send_whatsapp(to_number, msg_wascam_part3(), account_sid, auth_token, from_number)
        return "wascam_reported"

    # --- SMS with no content — prompt user to include the message ---
    if body == "SMS":
        send_whatsapp(
            to_number,
            "📨 *To analyse a suspicious text, reply with SMS followed by the message.*\n\n"
            "Example: *SMS https://suspicious-link.com* or paste the full text of the message.\n\n"
            "RelayShield will check any links for malware and phishing.",
            account_sid, auth_token, from_number,
        )
        return "sms_prompt_sent"

    # --- SMS (user forwards a suspicious text for analysis) ---
    # Extracts URLs from the forwarded text, checks via Google Safe Browsing
    # API v4, and returns a verdict: malicious / clean / no URLs found.
    # Falls back to guidance-only response if GSB API is unavailable.
    if body.startswith("SMS "):
        forwarded_text = message_body.strip()[4:].strip()
        urls = extract_urls(forwarded_text)

        if urls:
            try:
                gsb_api_key = get_gsb_api_key()
                gsb_result = check_urls_safe_browsing(urls, gsb_api_key)
            except Exception as e:
                logger.error("Failed to retrieve GSB API key or run analysis: %s", e)
                gsb_result = {"matches": [], "error": str(e)}
        else:
            gsb_result = {"matches": [], "error": None}

        response_text = build_sms_analysis_response(forwarded_text, urls, gsb_result)
        send_whatsapp(to_number, response_text, account_sid, auth_token, from_number)
        logger.info(
            "SMS analysis complete — urls_found=%d threats=%d error=%s",
            len(urls),
            len(gsb_result.get("matches", [])),
            gsb_result.get("error"),
        )
        try:
            signals = record_signal(user_id, "suspicious_sms", {"urls_found": len(urls), "urls": urls[:5]})
            check_and_warn_predictive(user_id, "suspicious_sms", signals, to_number, account_sid, auth_token, from_number)
            check_and_fire_correlation(user_id, signals, to_number, account_sid, auth_token, from_number)
        except Exception as exc:
            logger.exception("Coordinated attack check failed user_id=%s: %s", user_id, exc)
        return "suspicious_sms_analysed"

    # --- EMAIL with no content — prompt user to include the email body ---
    if body == "EMAIL":
        send_whatsapp(
            to_number,
            "📧 *To analyse a suspicious email, reply with EMAIL followed by the email body text.*\n\n"
            "Paste the text of the email (including any links). "
            "RelayShield will check all links for malware and phishing.\n\n"
            "Example: *EMAIL Your account has been suspended. Click here: https://example.com*\n\n"
            "⚠️ Do not open any attachments in the email before sending.",
            account_sid, auth_token, from_number,
        )
        return "email_prompt_sent"

    # --- EMAIL (user pastes suspicious email body for analysis) ---
    # Extracts URLs from the email body text, checks via Google Safe Browsing
    # API v4, returns email-specific verdict and remediation guidance.
    # Reuses the same URL extraction and GSB pipeline as the SMS command.
    if body.startswith("EMAIL "):
        email_text = message_body.strip()[6:].strip()
        urls = extract_urls(email_text)

        if urls:
            try:
                gsb_api_key = get_gsb_api_key()
                gsb_result = check_urls_safe_browsing(urls, gsb_api_key)
            except Exception as e:
                logger.error("Failed to retrieve GSB API key or run analysis: %s", e)
                gsb_result = {"matches": [], "error": str(e)}
        else:
            gsb_result = {"matches": [], "error": None}

        response_text = build_email_analysis_response(urls, gsb_result)
        send_whatsapp(to_number, response_text, account_sid, auth_token, from_number)
        logger.info(
            "EMAIL analysis complete — urls_found=%d threats=%d error=%s",
            len(urls),
            len(gsb_result.get("matches", [])),
            gsb_result.get("error"),
        )
        return "suspicious_email_analysed"

    # --- ATTACH with no content — safe guidance + usage instructions ---
    if body == "ATTACH":
        send_whatsapp(
            to_number,
            "📎 *To scan a suspicious file or link:*\n\n"
            "*Option 1 — Paste the URL:*\n"
            "Reply *ATTACH* followed by the direct link.\n"
            "Example: *ATTACH https://example.com/invoice.pdf*\n\n"
            "*Option 2 — Send the file:*\n"
            "Send the file directly as a WhatsApp attachment — "
            "RelayShield will scan it automatically.\n\n"
            "💡 *Before downloading from email:* In Gmail, right-click the attachment "
            "→ *Copy link address* and use Option 1. No download needed.",
            account_sid, auth_token, from_number,
        )
        return "attach_prompt_sent"

    # --- ATTACH <url> — VirusTotal URL scan ---
    # User pastes a direct link to a file or a suspicious URL.
    # Synchronous with VT_URL_MAX_WAIT polling window.
    if body.startswith("ATTACH "):
        attach_url = message_body.strip()[7:].strip()

        if not attach_url.startswith(("http://", "https://")):
            send_whatsapp(
                to_number,
                "Please include the full URL starting with https://\n\n"
                "Example: *ATTACH https://example.com/invoice.pdf*",
                account_sid, auth_token, from_number,
            )
            return "attach_invalid_url"

        send_whatsapp(
            to_number,
            "🔍 *RelayShield is scanning that link...* This may take up to 30 seconds.",
            account_sid, auth_token, from_number,
        )

        try:
            vt_api_key = get_vt_api_key()
            analysis_id = submit_url_to_vt(attach_url, vt_api_key)
            stats = poll_vt_analysis(analysis_id, vt_api_key, max_wait=VT_URL_MAX_WAIT) if analysis_id else None
        except Exception as exc:
            logger.error("VT URL scan failed for %s: %s", attach_url, exc)
            stats = None

        verdict = build_vt_verdict_response(stats, "that URL")
        send_whatsapp(to_number, verdict, account_sid, auth_token, from_number)
        logger.info(
            "VT URL scan complete — url=%s stats=%s",
            attach_url, stats,
        )
        return "vt_url_scanned"

    # --- HELP ---
    if body == "HELP":
        send_whatsapp(
            to_number, msg_help(is_business, is_employee, is_domain_tier=tier in DOMAIN_TIERS, has_seats=tier in SEAT_LIMITS), account_sid, auth_token, from_number
        )
        return "help_sent"

    # --- ADD (Business tier admin only) ---
    # Syntax: ADD +16175551234 [Optional Name]
    if body.startswith("ADD ") and tier == TIER_STARTER_DOMAIN and not is_employee:
        send_whatsapp(
            to_number,
            "The Domain Monitoring add-on is a solo licence — team seats are not included.\n\n"
            "To add team members, upgrade to *Business Basic* which includes up to 5 seats "
            "and domain monitoring.\n\n"
            "Reply *HELP* to see your current plan commands.",
            account_sid, auth_token, from_number,
        )
        return "starter_domain_no_seats"

    if body.startswith("ADD ") and is_business and not is_employee:
        add_args = message_body.strip()[4:].strip()
        parts = add_args.split(None, 1)  # split on first whitespace only
        raw_phone = parts[0]
        employee_name = parts[1].strip() if len(parts) > 1 else ""
        phone = normalise_phone(raw_phone)

        if not is_valid_phone(phone):
            send_whatsapp(
                to_number,
                "Please provide a valid phone number in international format.\n"
                "Example: *ADD +16175551234 Jane Smith*",
                account_sid, auth_token, from_number,
            )
            return "invalid_employee_phone"

        # Check seat limit
        seat_limit = SEAT_LIMITS.get(tier, 5)
        current_employees = count_employees(user_id)
        if current_employees >= seat_limit:
            send_whatsapp(
                to_number,
                f"You've reached your {seat_limit}-seat limit for your plan.\n\n"
                "Contact us to upgrade to a higher tier.",
                account_sid, auth_token, from_number,
            )
            return "seat_limit_reached"

        # Create employee record
        employee_id = create_employee_record(phone, user_id, tier, employee_name)
        display = f"*{employee_name}* ({phone})" if employee_name else f"*{phone}*"

        # Confirm to admin
        send_whatsapp(
            to_number,
            f"✅ {display} added. They'll receive an onboarding message shortly.\n\n"
            "Reply *STATUS* to see your full team.",
            account_sid, auth_token, from_number,
        )

        # Send welcome to employee
        send_whatsapp(
            phone,
            msg_employee_welcome(tier),
            account_sid, auth_token, from_number,
        )

        logger.info(
            "Employee added — admin_user_id=%s employee_user_id=%s phone=%s name=%r",
            user_id, employee_id, phone, employee_name or "(none)",
        )
        return "employee_added"

    # --- REMOVE (Business tier admin only) ---
    # Syntax: REMOVE +16175551234
    if body.startswith("REMOVE ") and is_business and not is_employee:
        raw_phone = message_body.strip()[7:].strip()
        phone = normalise_phone(raw_phone)

        if not is_valid_phone(phone):
            send_whatsapp(
                to_number,
                "Please provide a valid phone number.\n"
                "Example: *REMOVE +16175551234*",
                account_sid, auth_token, from_number,
            )
            return "invalid_remove_phone"

        employee = get_employee_by_phone_and_admin(phone, user_id)
        if not employee:
            send_whatsapp(
                to_number,
                f"No active team member found with number {phone}.\n\n"
                "Reply *STATUS* to see your current team.",
                account_sid, auth_token, from_number,
            )
            return "employee_not_found"

        emp_user_id = employee["user_id"]
        emp_name = employee.get("employee_name", "")
        display = f"*{emp_name}* ({phone})" if emp_name else f"*{phone}*"

        # Deactivate employee record and monitored emails
        update_user(emp_user_id, {"active": False})
        emails_removed = deactivate_employee_emails(emp_user_id)

        send_whatsapp(
            to_number,
            f"✅ {display} has been removed from your RelayShield account.\n\n"
            f"{emails_removed} monitored email{'s' if emails_removed != 1 else ''} deactivated.\n\n"
            "Reply *STATUS* to see your updated team.",
            account_sid, auth_token, from_number,
        )
        logger.info(
            "Employee removed — admin_user_id=%s employee_user_id=%s phone=%s emails_deactivated=%d",
            user_id, emp_user_id, phone, emails_removed,
        )
        return "employee_removed"

    # --- STATUS (Business tier admin only) ---
    if body == "STATUS" and is_business and not is_employee:
        employees = get_employees_for_admin(user_id)
        seat_limit = SEAT_LIMITS.get(tier, 5)
        seat_count = len(employees)

        if not employees:
            send_whatsapp(
                to_number,
                f"📊 *Team Status — {seat_count} of {seat_limit} seats in use*\n\n"
                "No team members added yet.\n\n"
                "Reply *ADD +1XXXXXXXXXX Name* to add your first team member.",
                account_sid, auth_token, from_number,
            )
            return "status_empty"

        lines = []
        for i, emp in enumerate(employees, 1):
            name = emp.get("employee_name", "")
            state = emp.get("onboarding_state", "")
            emails = int(emp.get("emails_added", 0))

            if state in (STATE_EMP_ACTIVE, STATE_ACTIVE):
                icon, label = "✅", "Active"
            elif state in (STATE_EMP_EMAIL_1, STATE_EMP_MORE_EMAILS):
                icon, label = "⏳", "Onboarding"
            else:
                icon, label = "❓", "Pending"

            display = f"*{name}*" if name else f"*Member {i}*"
            lines.append(
                f"{icon} {display} — {label} · "
                f"{emails} email{'s' if emails != 1 else ''} monitored"
            )

        team_list = "\n".join(lines)
        send_whatsapp(
            to_number,
            f"📊 *Team Status — {seat_count} of {seat_limit} seats in use*\n\n"
            f"{team_list}\n\n"
            "Reply *ADD +1XXXXXXXXXX Name* to add a team member, "
            "or *REMOVE +1XXXXXXXXXX* to offboard one.",
            account_sid, auth_token, from_number,
        )
        return "status_sent"

    # --- DOMAIN (Business Basic / Shield / Shield Pro only) ---
    # Employees see status and can run scans. Only admins can register/remove.
    if body == "DOMAIN" or body.startswith("DOMAIN "):
        # Gate: domain monitoring is not available on Personal Shield or Business Starter
        if tier not in DOMAIN_TIERS:
            send_whatsapp(
                to_number,
                "🌐 *Domain Monitoring* is available on Business Basic and higher plans.\n\n"
                "Contact us to upgrade.",
                account_sid, auth_token, from_number,
            )
            return "domain_tier_gate"

        # For employee accounts, look up the admin's monitored_domains
        if is_employee:
            admin_id   = user.get("admin_user_id")
            admin_rec  = dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": admin_id}).get("Item", {})
            domains      = admin_rec.get("monitored_domains") or []
            domain_state = load_domain_state(admin_rec)
            state_owner_id = admin_id
        else:
            domains      = user.get("monitored_domains") or []
            domain_state = load_domain_state(user)
            state_owner_id = user_id

        domain_limit = DOMAIN_LIMITS.get(tier, 1)

        # ── DOMAIN (status) ───────────────────────────────────────────────
        if body == "DOMAIN":
            send_whatsapp(
                to_number,
                msg_domain_status(domains, domain_state, tier),
                account_sid, auth_token, from_number,
            )
            return "domain_status_sent"

        # ── DOMAIN REGISTER <domain> (admin only) ─────────────────────────
        if body.startswith("DOMAIN REGISTER ") and not is_employee:
            raw_domain = message_body.strip()[16:].strip().lower()

            if not is_valid_domain(raw_domain):
                send_whatsapp(
                    to_number,
                    "That doesn't look like a valid domain. Please use the format:\n\n"
                    "*DOMAIN REGISTER yourdomain.com*",
                    account_sid, auth_token, from_number,
                )
                return "domain_invalid"

            if raw_domain in domains:
                send_whatsapp(
                    to_number,
                    f"*{raw_domain}* is already registered for monitoring.\n\n"
                    "Reply *DOMAIN* to see your full status.",
                    account_sid, auth_token, from_number,
                )
                return "domain_already_registered"

            if len(domains) >= domain_limit:
                send_whatsapp(
                    to_number,
                    f"You've reached your {domain_limit}-domain limit for your plan.\n\n"
                    "Reply *DOMAIN REMOVE old-domain.com* to remove one first,\n"
                    "or contact us to discuss your options.",
                    account_sid, auth_token, from_number,
                )
                return "domain_limit_reached"

            # Add domain and initialise state
            new_domains = domains + [raw_domain]
            table = dynamodb.Table(USERS_TABLE)
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET monitored_domains = :d, updated_at = :t",
                ExpressionAttributeValues={
                    ":d": new_domains,
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            domain_state[raw_domain] = {
                "registered_at":     datetime.now(timezone.utc).isoformat(),
                "last_scanned":      None,
                "known_lookalikes":  [],
                "mx_fingerprint":    None,
                "expiry_days_alerted": None,
            }
            save_domain_state(user_id, domain_state)

            send_whatsapp(
                to_number,
                f"✅ *{raw_domain}* registered for domain monitoring.\n\n"
                f"RelayShield will check daily for:\n"
                f"• Lookalike/typosquat domains\n"
                f"• Email configuration (MX) changes\n"
                f"• Domain expiry risk\n\n"
                f"Reply *DOMAIN SCAN* to run the first check now.\n\n"
                f"🛡️ RelayShield",
                account_sid, auth_token, from_number,
            )
            logger.info("Domain registered — user_id=%s domain=%s", user_id, raw_domain)
            return "domain_registered"

        # ── DOMAIN REMOVE <domain> (admin only) ───────────────────────────
        if body.startswith("DOMAIN REMOVE ") and not is_employee:
            raw_domain = message_body.strip()[14:].strip().lower()

            if raw_domain not in domains:
                send_whatsapp(
                    to_number,
                    f"*{raw_domain}* is not in your monitored domains.\n\n"
                    "Reply *DOMAIN* to see what's registered.",
                    account_sid, auth_token, from_number,
                )
                return "domain_not_found"

            new_domains = [d for d in domains if d != raw_domain]
            table = dynamodb.Table(USERS_TABLE)
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET monitored_domains = :d, updated_at = :t",
                ExpressionAttributeValues={
                    ":d": new_domains,
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            domain_state.pop(raw_domain, None)
            save_domain_state(user_id, domain_state)

            send_whatsapp(
                to_number,
                f"✅ *{raw_domain}* removed from domain monitoring.",
                account_sid, auth_token, from_number,
            )
            logger.info("Domain removed — user_id=%s domain=%s", user_id, raw_domain)
            return "domain_removed"

        # ── DOMAIN SCAN (admin + employee) ────────────────────────────────
        if body == "DOMAIN SCAN":
            if not domains:
                send_whatsapp(
                    to_number,
                    "No domains registered.\n\n"
                    "Reply *DOMAIN REGISTER yourdomain.com* to add one.",
                    account_sid, auth_token, from_number,
                )
                return "domain_scan_no_domains"

            send_whatsapp(
                to_number,
                f"🔍 *Scanning {len(domains)} domain{'s' if len(domains) > 1 else ''}...* "
                "This may take up to 30 seconds.",
                account_sid, auth_token, from_number,
            )

            findings: list[str] = []
            for domain in domains:
                entry = domain_state.get(domain) or {
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                    "last_scanned": None,
                    "known_lookalikes": [],
                    "mx_fingerprint": None,
                    "expiry_days_alerted": None,
                }
                known = entry.get("known_lookalikes") or []

                # Typosquat (inline, time-boxed)
                new_lookalikes = _quick_typosquat_check(domain, known)
                if new_lookalikes:
                    entry["known_lookalikes"] = list(set(known) | set(new_lookalikes))
                    count = len(new_lookalikes)
                    listing = ", ".join(f"*{d}*" for d in new_lookalikes[:3])
                    more    = f" (+{count - 3} more)" if count > 3 else ""
                    findings.append(
                        f"⚠️ *Lookalike domains registered for {domain}:*\n"
                        f"{listing}{more}\n"
                        "→ Attackers use these to send phishing email that appears to come from you.\n"
                        "→ Report to registrar abuse team; consider registering yourself."
                    )

                # MX check
                current_mx = _doh_mx_fingerprint(domain)
                stored_mx  = entry.get("mx_fingerprint")
                if current_mx is None:
                    findings.append(f"⚠️ Email configuration check unavailable for *{domain}* — retry later.")
                elif stored_mx is None:
                    entry["mx_fingerprint"] = current_mx
                    findings.append(f"✅ *{domain}* email configuration baseline recorded.")
                elif current_mx != stored_mx:
                    entry["mx_fingerprint"] = current_mx
                    findings.append(
                        f"🔴 *Email configuration change detected on {domain}!*\n"
                        "→ Log into your registrar NOW and verify your DNS settings.\n"
                        "→ Unexpected email configuration changes may indicate DNS hijacking.\n"
                        "→ Change your registrar password and enable 2FA immediately."
                    )
                else:
                    findings.append(f"✅ *{domain}* email configuration unchanged.")

                # Expiry check
                days = _rdap_days_until_expiry(domain)
                if days is None:
                    findings.append(f"ℹ️ Expiry data unavailable for *{domain}* (ccTLD or RDAP unsupported).")
                elif days <= 7:
                    findings.append(
                        f"🔴 *CRITICAL — {domain} expires in {days} day{'s' if days != 1 else ''}!*\n"
                        "→ Renew immediately at your registrar."
                    )
                elif days <= 14:
                    findings.append(
                        f"🟠 *{domain} expires in {days} days.*\n"
                        "→ Renew within 24 hours."
                    )
                elif days <= 30:
                    findings.append(
                        f"⚠️ *{domain} expires in {days} days.*\n"
                        "→ Renew now and enable auto-renew."
                    )
                else:
                    findings.append(f"✅ *{domain}* expiry: {days} days away.")

                entry["last_scanned"] = datetime.now(timezone.utc).isoformat()
                domain_state[domain] = entry

            # Persist updated state
            save_domain_state(state_owner_id, domain_state)

            body_text = "\n\n".join(findings) if findings else "✅ No issues detected."
            send_whatsapp(
                to_number,
                f"🌐 *Domain Scan Complete*\n\n{body_text}\n\n"
                "Reply *DOMAIN* for full status.\n\n🛡️ RelayShield",
                account_sid, auth_token, from_number,
            )
            logger.info("DOMAIN SCAN complete — user_id=%s domains=%s", user_id, domains)
            return "domain_scan_complete"

        # ── DOMAIN WARN <domain> (admin only) — broadcast warning to all employees ──
        if body.startswith("DOMAIN WARN ") and not is_employee:
            warn_domain = body[12:].strip().lower()

            if tier == TIER_STARTER_DOMAIN:
                # Starter-domain: solo plan, no employee seats — give direct action steps
                send_whatsapp(
                    to_number,
                    f"⚠️ *Domain Warning: {warn_domain}*\n\n"
                    f"Your plan doesn't include employee seats, so there's no team to broadcast to.\n\n"
                    f"*What you can do right now:*\n"
                    f"→ Report to the registrar's abuse team: look up the registrar at "
                    f"lookup.icann.org then file an abuse report\n"
                    f"→ Defensively register *{warn_domain}* yourself to prevent it being weaponised\n"
                    f"→ If you have a business website, post a notice warning visitors about the fake domain\n"
                    f"→ Upgrade to Business Basic to add employee seats and enable team broadcasts\n\n"
                    f"🛡️ RelayShield",
                    account_sid, auth_token, from_number,
                )
                return "domain_warn_no_employees"

            # Business tier: scan for active employees linked to this admin
            emp_resp  = dynamodb.Table(USERS_TABLE).scan(
                FilterExpression=Attr("admin_user_id").eq(user_id) & Attr("active").eq(True)
            )
            employees = emp_resp.get("Items", [])

            if not employees:
                send_whatsapp(
                    to_number,
                    f"⚠️ *{warn_domain}* — no active employees found to notify.\n\n"
                    f"Add employees first with *ADD +1XXXXXXXXXX*.\n\n"
                    f"🛡️ RelayShield",
                    account_sid, auth_token, from_number,
                )
                return "domain_warn_no_employees"

            warn_body = (
                f"⚠️ *Security Alert from your admin*\n\n"
                f"Do not click any links or open attachments from *{warn_domain}*.\n\n"
                f"This domain is impersonating your company and may be used to send "
                f"phishing emails or fake login pages.\n\n"
                f"If you receive any message from this domain:\n"
                f"→ Do not click any links\n"
                f"→ Do not enter any credentials\n"
                f"→ Forward it to your admin immediately\n\n"
                f"🛡️ RelayShield"
            )
            sent_count = 0
            for emp in employees:
                try:
                    emp_num = get_user_whatsapp_number(emp)
                    if emp_num and send_whatsapp(emp_num, warn_body, account_sid, auth_token, from_number):
                        sent_count += 1
                except Exception as exc:
                    logger.exception("DOMAIN WARN failed for employee user_id=%s: %s", emp.get("user_id"), exc)

            send_whatsapp(
                to_number,
                f"✅ *Domain warning broadcast sent.*\n\n"
                f"Warning about *{warn_domain}* sent to {sent_count} of {len(employees)} employee(s).\n\n"
                f"🛡️ RelayShield",
                account_sid, auth_token, from_number,
            )
            logger.info(
                "DOMAIN WARN sent — user_id=%s domain=%s employees=%d sent=%d",
                user_id, warn_domain, len(employees), sent_count,
            )
            return "domain_warn_sent"

        # Unrecognised DOMAIN sub-command — show usage
        send_whatsapp(
            to_number,
            "🌐 *Domain Monitoring — Available commands:*\n\n"
            "• *DOMAIN* — View registered domains and security status\n"
            "• *DOMAIN SCAN* — Run a full security scan now\n"
            "• *DOMAIN REGISTER yourdomain.com* — Add a domain to monitor\n"
            "• *DOMAIN REMOVE yourdomain.com* — Remove a monitored domain\n"
            "• *DOMAIN WARN lookalike.com* — Broadcast a phishing warning to all employees\n\n"
            "🛡️ RelayShield",
            account_sid, auth_token, from_number,
        )
        return "domain_usage_sent"

    # --- Unknown ---
    send_whatsapp(
        to_number, msg_unknown_command(), account_sid, auth_token, from_number
    )
    return "unknown_command"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event, context):
    """
    Entry point for API Gateway → Lambda (Twilio inbound webhook).

    Twilio sends form-encoded POST body with fields including:
      From  — sender's WhatsApp number (whatsapp:+1XXXXXXXXXX)
      Body  — message text
      X-Twilio-Signature header for verification
    """
    # --- Parse form-encoded body ---
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    params = dict(urllib.parse.parse_qsl(raw_body))
    from_number = params.get("From", "")
    message_body = params.get("Body", "").strip()
    num_media = int(params.get("NumMedia", "0"))
    media_url = params.get("MediaUrl0", "")
    media_content_type = params.get("MediaContentType0", "")

    logger.info(
        "Inbound WhatsApp from=%s body_len=%d num_media=%d",
        from_number, len(message_body), num_media,
    )

    if not from_number:
        logger.warning("No From number in webhook payload.")
        return {"statusCode": 400, "body": "Missing From number"}

    # --- Retrieve Twilio credentials ---
    try:
        account_sid, auth_token, twilio_from = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    twilio_creds = (account_sid, auth_token, twilio_from)

    # --- Verify Twilio signature ---
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    twilio_sig = headers.get("x-twilio-signature", "")
    # HTTP API v2.0 uses rawPath which includes the stage prefix (/prod/webhook/whatsapp)
    # This must match the exact URL Twilio used when computing the signature
    raw_path = (
        event.get("rawPath")
        or event.get("requestContext", {}).get("http", {}).get("path")
        or "/prod/webhook/whatsapp"
    )
    webhook_url = f"https://{headers.get('host', '')}{raw_path}"
    logger.info("Twilio signature check — url=%s sig=%s", webhook_url, twilio_sig[:10] if twilio_sig else "none")

    if not twilio_sig or not verify_twilio_signature(auth_token, twilio_sig, webhook_url, params):
        logger.warning("Twilio signature verification failed — request rejected. url=%s", webhook_url)
        return {"statusCode": 403, "body": "Invalid Twilio signature"}

    # --- Look up user ---
    user = get_user_by_whatsapp(from_number)

    if not user:
        logger.warning("No user found for WhatsApp number: %s", from_number)
        # Send a helpful message rather than silently failing
        send_whatsapp(
            from_number,
            "👋 Welcome! It looks like your account isn't set up yet.\n\n"
            "Visit *relayshield.net* to sign up and get started.",
            account_sid, auth_token, twilio_from,
        )
        return {"statusCode": 200, "body": "No user found"}

    onboarding_state = user.get("onboarding_state", STATE_ACTIVE)

    # --- Clear SMS fallback flag — inbound message proves WhatsApp session is active ---
    if user.get("pending_sms_fallback"):
        try:
            dynamodb.Table(USERS_TABLE).update_item(
                Key={"user_id": user["user_id"]},
                UpdateExpression="REMOVE pending_sms_fallback, pending_sms_fallback_at",
            )
        except Exception as exc:
            logger.warning("Failed to clear pending_sms_fallback: %s", exc)

    # --- Route by state ---
    if onboarding_state == STATE_EMAIL_1:
        result = handle_awaiting_email_1(user, message_body, twilio_creds)

    elif onboarding_state == STATE_MORE_EMAILS:
        result = handle_awaiting_more_emails(user, message_body, twilio_creds)

    elif onboarding_state == STATE_PASSWORD_MANAGER:
        result = handle_awaiting_password_manager(user, message_body, twilio_creds)

    elif onboarding_state == STATE_EMP_EMAIL_1:
        result = handle_employee_email_1(user, message_body, twilio_creds)

    elif onboarding_state == STATE_EMP_MORE_EMAILS:
        result = handle_employee_more_emails(user, message_body, twilio_creds)

    elif onboarding_state in (STATE_ACTIVE, STATE_EMP_ACTIVE):
        result = handle_active_message(
            user, message_body, twilio_creds,
            media_info={
                "num_media": num_media,
                "media_url": media_url,
                "media_content_type": media_content_type,
            },
        )

    else:
        logger.warning(
            "Unknown onboarding_state '%s' for user_id=%s",
            onboarding_state, user.get("user_id"),
        )
        result = "unknown_state"

    logger.info(
        "Handled message from=%s state=%s result=%s",
        from_number, onboarding_state, result,
    )

    # Twilio expects a 200 with TwiML or empty body
    return {"statusCode": 200, "body": ""}
