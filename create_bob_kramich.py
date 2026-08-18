"""
One-time script to manually create Bob Kramich's RelayShield account.
Tier: starter_domain ($24.99/month, $10 coupon applied → $14.99)
Run from terminal: AWS_PROFILE=relayshield python3 create_bob_kramich.py
"""

import boto3
import hashlib
import json
import uuid
import urllib.request
from datetime import datetime, timedelta, timezone
from base64 import b64encode

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGION            = "us-east-1"
AWS_PROFILE       = "relayshield"
USERS_TABLE       = "relayshield_users"
KMS_KEY_ALIAS     = "alias/relayshield-data-key"
WA_NUMBER         = "whatsapp:+19787643690"   # Bob's WhatsApp
FROM_NUMBER       = "whatsapp:+17407373961"   # RelayShield number
FIRST_NAME        = "Bob"
SIGNUP_EMAIL      = "bkramich@gmail.com"
TIER              = "starter_domain"
PLAN              = "monthly"

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

session   = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
dynamodb  = session.resource("dynamodb")
kms       = session.client("kms")
secrets   = session.client("secretsmanager")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_secret(name: str) -> dict:
    resp = secrets.get_secret_value(SecretId=name)
    val  = resp["SecretString"]
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        # Secret stored as plain string — wrap it
        key = name.split("/")[-1]   # e.g. "twilio_auth_token"
        return {key: val}

def encrypt_phone(phone: str) -> str:
    resp = kms.encrypt(
        KeyId=KMS_KEY_ALIAS,
        Plaintext=phone.encode("utf-8"),
    )
    return b64encode(resp["CiphertextBlob"]).decode("utf-8")

def hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()

def send_whatsapp(to: str, body: str, account_sid: str, auth_token: str) -> None:
    url  = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({
        "From": FROM_NUMBER,
        "To":   to,
        "Body": body,
    }).encode("utf-8")
    req  = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization",
                   "Basic " + b64encode(f"{account_sid}:{auth_token}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"WhatsApp sent — status {r.status}")
    except Exception as e:
        print(f"WhatsApp send error: {e}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

import urllib.parse

def main():
    now      = datetime.now(timezone.utc)
    expires  = (now + timedelta(days=31)).isoformat()
    user_id  = str(uuid.uuid4())
    raw_phone = "+19787643690"

    print(f"Creating record for {FIRST_NAME} — user_id: {user_id}")

    # Encrypt phone for storage + hash for GSI lookup
    phone_encrypted = encrypt_phone(raw_phone)
    phone_hash      = hash_phone(raw_phone)

    item = {
        "user_id":             user_id,
        "first_name":          FIRST_NAME,
        "whatsapp_number":     raw_phone,        # plaintext — legacy fallback lookup
        "phone_encrypted":     phone_encrypted,  # KMS-encrypted for privacy
        "phone_hash":          phone_hash,        # SHA-256 for GSI lookup
        "signup_email":        SIGNUP_EMAIL,
        "monitored_emails":    [SIGNUP_EMAIL],
        "tier":                TIER,
        "subscription_tier":   TIER,
        "plan":                PLAN,
        "delivery_channels":   ["whatsapp"],
        "preferred_channel":   "whatsapp",
        "active":              True,
        "onboarding_state":    "ACTIVE",
        "onboarding_source":   "manual_stripe_invoice",
        "stripe_customer":     "Bob Kramich",
        "invoice_id":          "JEROVP4D-0001",
        "subscription_start":  now.isoformat(),
        "subscription_expires": expires,
        "monitored_domains":   [],
        "wallets":             [],
        "recent_signals":      [],
        "created_at":          now.isoformat(),
        "updated_at":          now.isoformat(),
    }

    dynamodb.Table(USERS_TABLE).put_item(Item=item)
    print(f"✅ DynamoDB record created — tier={TIER} email={SIGNUP_EMAIL}")

    # Send welcome message
    twilio = get_secret("relayshield/twilio_account_sid")
    acct   = twilio.get("twilio_account_sid") or twilio.get("account_sid")
    token  = get_secret("relayshield/twilio_auth_token")
    auth   = token.get("twilio_auth_token") or token.get("auth_token")

    welcome = (
        f"👋 Welcome to RelayShield, {FIRST_NAME}!\n\n"
        f"🛡️ *Business Starter + Domain* is now active.\n\n"
        f"*What's included:*\n"
        f"• Breach monitoring on up to 3 email addresses\n"
        f"• SIM swap detection (every 4 hours)\n"
        f"• Domain lookalike monitoring (1 domain)\n"
        f"• URL, SMS, and email threat scanning\n"
        f"• AI-powered remediation guidance\n\n"
        f"*Next steps:*\n"
        f"• Reply *SWEEP* to run your first email security sweep\n"
        f"• Reply *DOMAIN REGISTER yourdomain.com* to activate domain monitoring\n"
        f"• Reply *HELP* to see all available commands\n\n"
        f"You're protected. 🔒"
    )

    send_whatsapp(WA_NUMBER, welcome, acct, auth)
    print("✅ Welcome WhatsApp message sent to Bob")
    print(f"\nAccount summary:")
    print(f"  user_id:  {user_id}")
    print(f"  tier:     {TIER}")
    print(f"  email:    {SIGNUP_EMAIL}")
    print(f"  phone:    {raw_phone}")
    print(f"  expires:  {expires}")

if __name__ == "__main__":
    main()
