"""
relayshield_connectwise_webhook — Lambda handler
Receives RelayShield alert payloads and creates ConnectWise Manage service tickets.

Triggered by: API Gateway POST /webhook/connectwise
Auth: HMAC-SHA256 signature header X-RelayShield-Signature (shared secret in Secrets Manager)
ConnectWise credentials: stored in Secrets Manager as relayshield/connectwise_credentials

ConnectWise Manage REST API docs:
  https://developer.connectwise.com/Products/Manage/REST

Expected payload from RelayShield:
{
  "alert_type": "INFOSTEALER" | "BREACH" | "SIM_SWAP" | "NHI_EXPOSURE" | "IDENTITY_RISK",
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "domain": "acme-corp.com",
  "identity": "user@acme-corp.com",           # optional
  "risk_score": 78,                            # optional
  "detail": "RedLine Stealer: 3 credentials extracted...",
  "risk_factors": ["factor1", "factor2"],      # optional
  "timestamp": "2026-06-26T14:30:00Z",
  "client_id": "cw-client-id-123"             # optional — maps to CW company
}
"""

import hashlib
import hmac
import json
import logging
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timezone

import boto3
from boto3 import client as boto3_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretsm = boto3_client("secretsmanager", region_name="us-east-1")

# Secrets Manager key names
CW_CREDENTIALS_SECRET = "relayshield/connectwise_credentials"
RS_WEBHOOK_SECRET     = "relayshield/webhook_signing_secret"

# ConnectWise priority IDs (standard CW Manage defaults — confirm in your instance)
CW_PRIORITY = {
    "CRITICAL": 1,   # Priority 1 - Critical
    "HIGH":     2,   # Priority 2 - High
    "MEDIUM":   3,   # Priority 3 - Medium
    "LOW":      4,   # Priority 4 - Low
}

# ConnectWise ticket status IDs (standard defaults)
CW_STATUS_NEW = 1  # "New" status

# ConnectWise board name to create tickets on
CW_BOARD_NAME = "Service"


def get_secret(name: str) -> dict | str:
    val = secretsm.get_secret_value(SecretId=name)["SecretString"]
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return val.strip()


def verify_signature(body: bytes, sig_header: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header.lstrip("sha256="))


def cw_request(method: str, path: str, cw: dict, body: dict | None = None) -> dict:
    """Make an authenticated ConnectWise Manage REST API request."""
    base_url = cw["site_url"].rstrip("/")  # e.g. https://na.myconnectwise.net
    company  = cw["company_id"]             # e.g. mycompany
    pub_key  = cw["public_key"]
    priv_key = cw["private_key"]
    client_id = cw["client_id"]             # x-ConnectWise-clientid header value

    auth_str = base64.b64encode(f"{company}+{pub_key}:{priv_key}".encode()).decode()
    headers = {
        "Authorization":        f"Basic {auth_str}",
        "Content-Type":         "application/json",
        "Accept":               "application/json",
        "x-ConnectWise-clientid": client_id,
    }

    url  = f"{base_url}/v4_6_release/apis/3.0{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode()
        logger.error("CW API %s %s → HTTP %d: %s", method, path, exc.code, err_body)
        raise


def get_cw_board_id(cw: dict, board_name: str) -> int:
    """Look up a service board ID by name."""
    results = cw_request("GET", f"/service/boards?conditions=name='{board_name}'&fields=id,name", cw)
    if not results:
        raise ValueError(f"ConnectWise board '{board_name}' not found")
    return results[0]["id"]


def get_or_create_company(cw: dict, domain: str) -> int | None:
    """Find a CW company by domain identifier. Returns company ID or None."""
    identifier = domain.split(".")[0]  # acme-corp from acme-corp.com
    results = cw_request("GET", f"/company/companies?conditions=identifier='{identifier}'&fields=id,identifier,name", cw)
    if results:
        return results[0]["id"]
    return None


def build_ticket_body(alert: dict, board_id: int, company_id: int | None) -> dict:
    """Build the ConnectWise service ticket payload."""
    severity  = alert.get("severity", "HIGH")
    alert_type = alert.get("alert_type", "IDENTITY_RISK")
    domain    = alert.get("domain", "unknown")
    identity  = alert.get("identity", "")
    risk_score = alert.get("risk_score")
    detail    = alert.get("detail", "")
    factors   = alert.get("risk_factors", [])
    ts        = alert.get("timestamp", datetime.now(timezone.utc).isoformat())

    summary_parts = [f"RelayShield {severity}", alert_type.replace("_", " ").title(), f"— {domain}"]
    if identity:
        summary_parts.append(f"({identity})")
    summary = " ".join(summary_parts)

    initial_note = f"""RelayShield Automated Alert
===========================
Severity:   {severity}
Alert Type: {alert_type}
Domain:     {domain}
{"Identity:   " + identity if identity else ""}
{"Risk Score: " + str(risk_score) + "/100" if risk_score is not None else ""}
Detected:   {ts}

Detail
------
{detail}

{"Risk Factors" + chr(10) + chr(10).join("• " + f for f in factors) if factors else ""}

Recommended Action
------------------
1. Log in to RelayShield dashboard for full context
2. Initiate credential rotation for affected identities
3. Invalidate active sessions for impacted accounts
4. Review infostealer remediation steps via RelayShield WhatsApp bot
5. Update this ticket with resolution steps taken

---
Auto-generated by RelayShield Threat Intelligence
relayshield.net | relayshieldadmin@gmail.com
"""

    ticket = {
        "summary": summary[:100],  # CW summary max 100 chars
        "board": {"id": board_id},
        "status": {"id": CW_STATUS_NEW},
        "priority": {"id": CW_PRIORITY.get(severity, 3)},
        "initialDescription": initial_note,
        "severity": "High" if severity in ("CRITICAL", "HIGH") else "Medium",
        "impact": "High" if severity == "CRITICAL" else "Medium",
    }

    if company_id:
        ticket["company"] = {"id": company_id}

    return ticket


def lambda_handler(event, context):
    # Parse the incoming API Gateway request
    body_raw  = (event.get("body") or "").encode()
    headers   = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("x-relayshield-signature", "")

    # Verify HMAC signature
    try:
        rs_secret = get_secret(RS_WEBHOOK_SECRET)
        if isinstance(rs_secret, dict):
            rs_secret = rs_secret.get("secret", "")
    except Exception as e:
        logger.error("Failed to load webhook signing secret: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": "configuration error"})}

    if sig_header and not verify_signature(body_raw, sig_header, rs_secret):
        logger.warning("Signature verification failed")
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    try:
        alert = json.loads(body_raw)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "invalid json"})}

    severity = alert.get("severity", "LOW")
    # Only create tickets for CRITICAL and HIGH by default
    if severity not in ("CRITICAL", "HIGH"):
        logger.info("Skipping ticket for severity=%s", severity)
        return {"statusCode": 200, "body": json.dumps({"ok": True, "skipped": True, "reason": "below threshold"})}

    # Load ConnectWise credentials
    try:
        cw = get_secret(CW_CREDENTIALS_SECRET)
    except Exception as e:
        logger.error("Failed to load CW credentials: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": "cw credentials unavailable"})}

    try:
        board_id   = get_cw_board_id(cw, CW_BOARD_NAME)
        domain     = alert.get("domain", "")
        company_id = get_or_create_company(cw, domain) if domain else None
        ticket_body = build_ticket_body(alert, board_id, company_id)
        ticket = cw_request("POST", "/service/tickets", cw, ticket_body)

        ticket_id  = ticket.get("id")
        ticket_num = ticket.get("ticketNumber")
        logger.info("CW ticket created: #%s (id=%s) for domain=%s severity=%s", ticket_num, ticket_id, domain, severity)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "ok": True,
                "ticket_id":     ticket_id,
                "ticket_number": ticket_num,
                "company_id":    company_id,
            }),
        }

    except Exception as e:
        logger.exception("Failed to create CW ticket: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
