"""
RelayShield SIEM/SOAR connector — competitive-benchmark roadmap item
(competitive_benchmark_gitguardian_greynoise_cymru_cyberark.md), closes the
enterprise-SOC integration gap GreyNoise already has (native Splunk
SOAR/XSOAR/QRadar SOAR connectors).

Shared by any monitor Lambda that wants to forward a finding to a customer's
own SIEM/SOAR, in addition to (not instead of) the existing WhatsApp/Telegram
alert. Never raises — a SIEM delivery failure must not break the primary
alert, same rationale as _record_stripe_meter_event in relayshield_api.py.

Supported formats:
  - splunk_hec   — Splunk HTTP Event Collector (docs.splunk.com/Documentation/Splunk/latest/Data/HECRESTendpoints)
  - cef          — Common Event Format, natively parsed by QRadar (also ArcSight
                   and most other SIEMs) — sent as an HTTP POST with the CEF
                   string as the body, since QRadar's HTTP Receiver log source
                   type accepts raw CEF over HTTP, not just syslog.
  - xsoar_webhook — Cortex XSOAR's Generic Webhook integration incident-creation shape.

Finding contract (what callers pass in):
    {
        "alert_type":   str,   # e.g. "breach", "domain_lookalike", "sim_swap"
        "severity":     str,   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
        "customer_id":  str,   # email or domain the finding is about
        "summary":      str,   # one-line human-readable summary
        "details":      dict,  # arbitrary structured findings payload
        "detected_at":  str,   # ISO 8601 timestamp
    }
"""

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger()

SIEM_DESTINATIONS_TABLE = "relayshield_siem_destinations"

# CEF severity is 0-10; map RelayShield's 4-tier scale onto it.
_CEF_SEVERITY = {"LOW": 3, "MEDIUM": 5, "HIGH": 7, "CRITICAL": 10}
# XSOAR incident severity: 0=Unknown, 1=Low, 2=Medium, 3=High, 4=Critical.
_XSOAR_SEVERITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _cef_escape(value: str) -> str:
    """CEF extension values must escape backslash, equals, and pipe."""
    return str(value).replace("\\", "\\\\").replace("=", "\\=").replace("|", "\\|")


def format_splunk_hec(finding: dict) -> dict:
    """Splunk HEC event envelope — POST body for /services/collector/event."""
    return {
        "time":       time.time(),
        "sourcetype": "relayshield:alert",
        "source":     "relayshield",
        "event": {
            "alert_type":  finding.get("alert_type", ""),
            "severity":    finding.get("severity", ""),
            "customer_id": finding.get("customer_id", ""),
            "summary":     finding.get("summary", ""),
            "details":     finding.get("details", {}),
            "detected_at": finding.get("detected_at", ""),
        },
    }


def format_cef(finding: dict) -> str:
    """CEF:0|Vendor|Product|Version|SignatureID|Name|Severity|Extension

    QRadar (and most CEF-native SIEMs) parse this directly. SignatureID is a
    stable per-alert-type identifier, not the specific finding's ID — that
    goes in the extension as a custom field."""
    severity = finding.get("severity", "LOW")
    alert_type = finding.get("alert_type", "unknown")
    signature_id = f"relayshield-{alert_type}"
    name = finding.get("summary", "RelayShield alert")
    cef_severity = _CEF_SEVERITY.get(severity, 3)

    extension_parts = [
        f"cs1Label=CustomerId cs1={_cef_escape(finding.get('customer_id', ''))}",
        f"cs2Label=AlertType cs2={_cef_escape(alert_type)}",
        f"rt={int(datetime.now(timezone.utc).timestamp() * 1000)}",
        f"msg={_cef_escape(finding.get('summary', ''))}",
    ]
    for key, value in (finding.get("details") or {}).items():
        # Free-form details go in as additional custom key=value pairs —
        # not standard CEF dictionary keys, but widely accepted by CEF
        # parsers (including QRadar's) as extension fields.
        safe_key = "".join(c for c in str(key) if c.isalnum())
        if safe_key:
            extension_parts.append(f"{safe_key}={_cef_escape(value)}")

    extension = " ".join(extension_parts)
    return f"CEF:0|RelayShield|RelayShield|1.0|{signature_id}|{name}|{cef_severity}|{extension}"


def format_xsoar_webhook(finding: dict) -> dict:
    """Cortex XSOAR Generic Webhook incident-creation shape."""
    severity = finding.get("severity", "LOW")
    return {
        "name":     finding.get("summary", "RelayShield alert"),
        "type":     "RelayShield Alert",
        "severity": _XSOAR_SEVERITY.get(severity, 1),
        "details":  json.dumps(finding.get("details", {})),
        "rawJSON":  json.dumps(finding),
        "occurred": finding.get("detected_at", datetime.now(timezone.utc).isoformat()),
    }


def send_to_siem(finding: dict, destination: dict) -> bool:
    """Format and deliver a finding per the customer's configured destination.
    destination: {"format": "splunk_hec"|"cef"|"xsoar_webhook", "url": str,
                   "auth_token": str (optional, format-dependent)}.
    Never raises — fire-and-forget, must not break the caller's primary alert."""
    fmt = destination.get("format")
    url = destination.get("url")
    if not fmt or not url:
        return False

    try:
        headers = {"Content-Type": "application/json"}
        if fmt == "splunk_hec":
            body = json.dumps(format_splunk_hec(finding)).encode("utf-8")
            token = destination.get("auth_token", "")
            if token:
                headers["Authorization"] = f"Splunk {token}"
        elif fmt == "cef":
            body = format_cef(finding).encode("utf-8")
            headers["Content-Type"] = "text/plain"
            token = destination.get("auth_token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif fmt == "xsoar_webhook":
            body = json.dumps(format_xsoar_webhook(finding)).encode("utf-8")
            token = destination.get("auth_token", "")
            if token:
                headers["Authorization"] = token
        else:
            logger.warning("send_to_siem: unknown format %s", fmt)
            return False

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("SIEM delivery ok format=%s customer=%s status=%d",
                        fmt, finding.get("customer_id", ""), resp.status)
            return True
    except urllib.error.HTTPError as exc:
        logger.warning("SIEM delivery failed (non-fatal) format=%s customer=%s HTTP %d: %s",
                       fmt, finding.get("customer_id", ""), exc.code, exc.read()[:300])
        return False
    except Exception as exc:
        logger.warning("SIEM delivery failed (non-fatal) format=%s customer=%s: %s",
                       fmt, finding.get("customer_id", ""), exc)
        return False


def get_siem_destination(dynamodb, customer_id: str) -> dict | None:
    """Look up a customer's configured SIEM destination, if any and enabled."""
    try:
        table = dynamodb.Table(SIEM_DESTINATIONS_TABLE)
        resp  = table.get_item(Key={"customer_id": customer_id.lower()})
        item  = resp.get("Item")
        if not item or not item.get("enabled"):
            return None
        return {
            "format":     item.get("format"),
            "url":        item.get("url"),
            "auth_token": item.get("auth_token", ""),
        }
    except Exception as exc:
        logger.warning("get_siem_destination lookup failed for %s: %s", customer_id, exc)
        return None


def dispatch_finding(dynamodb, finding: dict) -> bool:
    """Convenience wrapper: look up the customer's destination and deliver
    if one is configured and enabled. Safe to call unconditionally from any
    monitor after an alert fires — no-ops cleanly if the customer has no
    SIEM configured."""
    customer_id = finding.get("customer_id", "")
    if not customer_id:
        return False
    destination = get_siem_destination(dynamodb, customer_id)
    if not destination:
        return False
    return send_to_siem(finding, destination)
