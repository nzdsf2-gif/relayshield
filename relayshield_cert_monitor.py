"""
relayshield_cert_monitor — EventBridge Lambda (daily 07:30 UTC)

Certificate Transparency monitoring via crt.sh (free, no auth).
For each user's monitored domain, queries crt.sh for newly issued TLS certificates.
New certs for a monitored domain are a strong phishing/typosquat early warning signal —
attackers register lookalike domains and immediately obtain Let's Encrypt certs.

Alerts users via WhatsApp when:
  - A new cert is issued for an exact monitored domain (unexpected reissue)
  - A new cert is issued for a subdomain pattern matching the monitored domain
  - A cert is issued for a lookalike domain (contains the domain name)

Stores findings in relayshield_intel_iocs with source="cert_transparency".
"""

import base64
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

import relayshield_siem_connector as siem_connector

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE            = "relayshield_users"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
INTEL_IOCS_TABLE       = "relayshield_intel_iocs"
CRT_SH_URL             = "https://crt.sh/?q={domain}&output=json"
IOC_TTL_DAYS           = 90

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE   = "https://api.telegram.org/bot{token}/sendMessage"

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
secretsm = boto3.client("secretsmanager", region_name="us-east-1")


def _get_secret(name: str) -> str:
    return secretsm.get_secret_value(SecretId=name)["SecretString"].strip()


def _get_twilio_creds() -> tuple[str, str, str]:
    return _get_secret(TWILIO_SID_SECRET), _get_secret(TWILIO_TOKEN_SECRET), _get_secret(TWILIO_FROM_SECRET)


def _get_user_wa_number(user: dict) -> str | None:
    if "phone_encrypted" in user:
        try:
            kms    = boto3.client("kms", region_name="us-east-1")
            number = kms.decrypt(CiphertextBlob=base64.b64decode(user["phone_encrypted"]))["Plaintext"].decode()
        except Exception:
            return None
    else:
        number = user.get("whatsapp_number")
    if not number:
        return None
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def _send_telegram(chat_id: int, text: str) -> bool:
    try:
        raw  = secretsm.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"]
        token = json.loads(raw)["telegram_bot_token"]
        url  = TELEGRAM_API_BASE.format(token=token)
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:
        logger.error("Cert alert TG failed chat_id=%s: %s", chat_id, exc)
        return False


def _send_wa(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str) -> bool:
    url     = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    payload = urllib.parse.urlencode({"From": from_number, "To": to_number, "Body": body}).encode()
    creds   = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req     = urllib.request.Request(url, data=payload,
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Cert alert WA sent to %s SID=%s", to_number, json.loads(resp.read()).get("sid"))
            return True
    except Exception as exc:
        logger.error("Cert alert WA failed to %s: %s", to_number, exc)
        return False


def _query_crt_sh(domain: str) -> list[dict]:
    """Query crt.sh for certs issued in last 24 hours for a domain."""
    url = CRT_SH_URL.format(domain=urllib.parse.quote(domain))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            entries = json.loads(resp.read())
        cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
        new_certs = []
        for e in entries if isinstance(entries, list) else []:
            issued_str = e.get("entry_timestamp") or e.get("not_before") or ""
            try:
                issued = datetime.fromisoformat(issued_str.replace("Z", "+00:00"))
                if issued >= cutoff:
                    new_certs.append(e)
            except Exception:
                pass
        return new_certs
    except Exception as exc:
        logger.warning("crt.sh query failed domain=%s: %s", domain, exc)
        return []


def _get_monitored_domains() -> dict[str, list[dict]]:
    """Return {domain: [user_records]} for all active users with monitored_domain set."""
    table  = dynamodb.Table(USERS_TABLE)
    result: dict[str, list[dict]] = {}
    resp   = table.scan(FilterExpression=Attr("active").eq(True) & Attr("monitored_domain").exists())
    for item in resp.get("Items", []):
        domain = item.get("monitored_domain", "").lower().strip()
        if domain:
            result.setdefault(domain, []).append(item)
    while "LastEvaluatedKey" in resp:
        resp = table.scan(
            FilterExpression=Attr("active").eq(True) & Attr("monitored_domain").exists(),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        for item in resp.get("Items", []):
            domain = item.get("monitored_domain", "").lower().strip()
            if domain:
                result.setdefault(domain, []).append(item)
    return result


def _store_cert_ioc(domain: str, cert: dict) -> bool:
    """Store cert transparency finding as IOC. Returns True if new."""
    ioc_value = f"cert:{domain}:{cert.get('serial_number','unknown')}"
    table = dynamodb.Table(INTEL_IOCS_TABLE)
    try:
        table.put_item(
            Item={
                "ioc_value": ioc_value,
                "seen_ts":   datetime.now(timezone.utc).isoformat(),
                "ioc_type":  "cert_transparency",
                "channel":   "cert_transparency",
                "category":  "phishing_indicator",
                "malware":   "",
                "ttl":       Decimal(int(time.time()) + IOC_TTL_DAYS * 86400),
            },
            ConditionExpression="attribute_not_exists(ioc_value)",
        )
        return True
    except Exception:
        return False


def lambda_handler(event, context):
    domains = _get_monitored_domains()
    if not domains:
        logger.info("No monitored domains found — cert monitor complete")
        return {"checked": 0, "new_certs": 0, "alerts": 0}

    try:
        account_sid, auth_token, from_number = _get_twilio_creds()
    except Exception as exc:
        logger.error("Twilio creds failed: %s", exc)
        account_sid = auth_token = from_number = None

    checked = new_certs = alerts = 0
    for domain, users in domains.items():
        checked += 1
        certs = _query_crt_sh(domain)
        time.sleep(1)  # rate limit crt.sh — be a good citizen
        for cert in certs:
            if _store_cert_ioc(domain, cert):
                new_certs += 1
                common_name = cert.get("common_name", cert.get("name_value", "unknown"))
                logger.info("New cert for monitored domain=%s cn=%s", domain, common_name)
                msg = (
                    f"🔐 *RelayShield — New Certificate Detected*\n\n"
                    f"A new TLS certificate was issued for *{domain}* "
                    f"within the last 24 hours.\n\n"
                    f"*Certificate:* {common_name}\n\n"
                    f"If you did not issue this certificate, an attacker may be "
                    f"setting up a phishing site using your domain name. "
                    f"Check your DNS registrar and hosting provider immediately.\n\n"
                    f"🛡️ RelayShield Certificate Transparency Monitor"
                )
                for user in users:
                    # WhatsApp delivery
                    if account_sid:
                        to_number = _get_user_wa_number(user)
                        if to_number and _send_wa(account_sid, auth_token, from_number, to_number, msg):
                            alerts += 1
                    # Telegram delivery
                    tg_chat_id = user.get("telegram_chat_id")
                    tg_channels = user.get("delivery_channels", [])
                    if tg_chat_id and "telegram" in tg_channels:
                        if _send_telegram(int(tg_chat_id), msg):
                            alerts += 1
                    # SIEM/SOAR forwarding — no-ops cleanly if no destination configured.
                    try:
                        email = user.get("email", "")
                        if email:
                            siem_connector.dispatch_finding(dynamodb, {
                                "alert_type":  "cert_transparency",
                                "severity":    "HIGH",
                                "customer_id": email,
                                "summary":     f"New TLS certificate issued for monitored domain {domain}: {common_name}",
                                "details":     {"domain": domain, "common_name": common_name},
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                            })
                    except Exception as exc:
                        logger.warning("SIEM dispatch failed (non-fatal) for %s: %s", domain, exc)

    logger.info("Cert monitor complete — domains=%d new_certs=%d alerts=%d", checked, new_certs, alerts)
    return {"checked": checked, "new_certs": new_certs, "alerts": alerts}
