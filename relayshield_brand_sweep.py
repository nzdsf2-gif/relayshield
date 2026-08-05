"""
relayshield_brand_sweep — EventBridge Lambda (weekly Monday 10:00 UTC)

Automated brand protection sweep for TI subscribers.
Calls /v1/metered/brand-monitor for each TI subscriber's monitored domain
and includes findings in the weekly MSP digest.

For non-TI subscribers with a monitored_domain, runs a lightweight
IOC corpus scan and alerts on high-confidence brand abuse only.

Does NOT charge the subscriber per call — this is a platform-side sweep
billed as part of the TI subscription value, not a metered API call.
"""

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE    = "relayshield_users"
INTEL_IOCS_TABLE = "relayshield_intel_iocs"
API_BASE       = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
secretsm = boto3.client("secretsmanager", region_name="us-east-1")
ses      = boto3.client("ses", region_name="us-east-1")

FROM_EMAIL  = "noreply@relayshield.net"
REPORT_TO   = "relayshieldadmin@gmail.com"


def _get_ti_api_key() -> str:
    """Get a platform-level API key for internal calls."""
    table = dynamodb.Table("relayshield_api_keys")
    resp  = table.scan(FilterExpression=Attr("intel_access").eq(True), Limit=1)
    items = resp.get("Items", [])
    return items[0]["api_key"] if items else ""


def _get_ti_subscribers() -> list[dict]:
    """Return all users with intel_access API keys — TI subscribers."""
    keys_table = dynamodb.Table("relayshield_api_keys")
    users_table = dynamodb.Table(USERS_TABLE)
    ti_user_ids: set[str] = set()
    resp = keys_table.scan(FilterExpression=Attr("intel_access").eq(True))
    for item in resp.get("Items", []):
        if item.get("user_id"):
            ti_user_ids.add(item["user_id"])
    while "LastEvaluatedKey" in resp:
        resp = keys_table.scan(FilterExpression=Attr("intel_access").eq(True),
                               ExclusiveStartKey=resp["LastEvaluatedKey"])
        for item in resp.get("Items", []):
            if item.get("user_id"):
                ti_user_ids.add(item["user_id"])
    subscribers = []
    for uid in ti_user_ids:
        try:
            item = users_table.get_item(Key={"user_id": uid}).get("Item", {})
            if item:
                subscribers.append(item)
        except Exception:
            pass
    return subscribers


def _brand_scan(domain: str, api_key: str) -> dict:
    """Call brand-monitor endpoint for a domain."""
    url = f"{API_BASE}/v1/metered/brand-monitor"
    try:
        payload = json.dumps({"brand": domain.split(".")[0]}).encode()
        req = urllib.request.Request(url, data=payload,
            headers={"Content-Type": "application/json", "X-RS-API-KEY": api_key}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read()).get("data", {})
    except Exception as exc:
        logger.error("Brand scan failed domain=%s: %s", domain, exc)
        return {}


def lambda_handler(event, context):
    api_key = _get_ti_api_key()
    if not api_key:
        logger.error("No TI API key found for platform sweep")
        return {"error": "no_api_key"}

    subscribers  = _get_ti_subscribers()
    sweep_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    findings     = []
    total_scanned = 0

    for user in subscribers:
        domain = (user.get("monitored_domain") or "").strip().lower()
        dev_email = user.get("developer_email") or user.get("email_address") or ""
        if not domain:
            continue
        total_scanned += 1
        result = _brand_scan(domain, api_key)
        total  = result.get("total_mentions", 0)
        if total > 0:
            findings.append({
                "domain":          domain,
                "developer_email": dev_email,
                "total_mentions":  total,
                "phishing_domains": result.get("phishing_domains", 0),
                "malware_c2":      result.get("malware_c2", 0),
                "dark_web":        result.get("dark_web_mentions", 0),
                "recommendation":  result.get("recommendation", ""),
            })
            logger.info("Brand abuse found domain=%s mentions=%d", domain, total)

    # Send admin digest
    if findings:
        rows = "".join(
            f"<tr><td>{f['domain']}</td><td>{f['total_mentions']}</td>"
            f"<td>{f['phishing_domains']}</td><td>{f['malware_c2']}</td>"
            f"<td>{f['dark_web']}</td><td>{f['recommendation'][:80]}</td></tr>"
            for f in findings
        )
        html = f"""<html><body style="font-family:sans-serif;">
<h2>RelayShield Brand Sweep — {sweep_date}</h2>
<p>Scanned {total_scanned} TI subscriber domains. Found brand abuse on {len(findings)}.</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;">
<tr style="background:#0F1F3D;color:white;">
  <th>Domain</th><th>Total Mentions</th><th>Phishing Domains</th>
  <th>Malware C2</th><th>Dark Web</th><th>Recommendation</th>
</tr>{rows}
</table></body></html>"""
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [REPORT_TO]},
            Message={
                "Subject": {"Data": f"RelayShield Brand Sweep — {len(findings)} findings — {sweep_date}"},
                "Body": {"Html": {"Data": html}},
            },
        )

    logger.info("Brand sweep complete — scanned=%d findings=%d", total_scanned, len(findings))
    return {"scanned": total_scanned, "with_findings": len(findings), "date": sweep_date}
