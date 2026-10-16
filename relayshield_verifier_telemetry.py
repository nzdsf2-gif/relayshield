"""relayshield_verifier_telemetry -- opt-in threat telemetry for the hosted verifiers
(TAP today, PAP and x401 through the same call).

    from relayshield_verifier_telemetry import maybe_report
    maybe_report("tap", verdict, api_event, request)      # never raises

WHAT IT DOES. When a verifier REJECTS a request and the calling account has turned
telemetry on, it writes ONE row to relayshield_verifier_telemetry describing the
rejection. Nothing else is ever written: not accepts, not reviews, not transactions.

THE DEFAULT IS OFF, AND THE TEST THAT KEEPS IT OFF IS STRICT. The opt-in is the boolean
`verifier_telemetry_opt_in` on the account's API key record, set by
POST /v1/verifiers/config. It is compared with `is True`, so the string "false", the
number 1 and a missing field all mean OFF. A missing key, an inactive key, a lookup that
errors and an unreadable record all mean OFF too: every doubt resolves to "send nothing".

NEVER ON THE HOT PATH. An accept or review verdict returns before this module touches
DynamoDB at all, so the opt-in lookup (one consistent read) is paid only on a reject, and
a verifier that is merely slow to reach DynamoDB cannot slow down the merchants it
protects. Every failure is swallowed and logged WITHOUT any value from the request.

WHAT A ROW CONTAINS (and the privacy policy, section 13, says exactly this -- a test
reads both):
    agent_id_hash      SHA-256 of the agent identifier (keyid / DID). One-way, but
                       identifiers are public, so anyone holding a candidate can hash it
                       and compare. The policy says that; it does NOT say "cannot be
                       reversed".
    ip_prefix          network prefix of the AGENT's source address, if the merchant
                       supplied one: IPv4 /24, IPv6 /48, global addresses only. Never the
                       address of the account calling us.
    rejection_reason   one value from a closed set. The raw reason string is never stored.
    attack_pattern     which indicator types were SCREENED when a threat-intelligence
                       match caused the reject. It never holds an indicator.
    verifier_type      tap | pap | x401 | tap+x401
    issuer_hash        SHA-256 of the credential issuer (x401 only, else absent)
    reporter_hash      first 16 hex of SHA-256 of the API key. Lets us delete a customer's
                       reports on request, and count distinct accounts before anything is
                       ever treated as corroborated. Not the key.
    pk / sk / ttl      bucket by UTC day, time + random suffix, 90 days.

NEVER STORED: amounts, merchants, customer or cardholder data, the full agent
identifier, a full IP address, anything from an x401 credential about the human, the API
key, or any free text.

THE LOOP HAZARD, recorded so nobody builds on it by accident. A `ti_match` rejection is
our own corpus's verdict coming back at us. Counting it is useful trend data; treating it
as INDEPENDENT evidence would let a false positive look corroborated by the very
customers it fooled. Nothing reads this table into the IOC corpus, and nothing should
without a reviewed step like tools/promote_mcp_candidates.py that refuses echoes.
"""

import hashlib
import ipaddress
import logging
import os
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE = "relayshield_verifier_telemetry"
API_KEYS_TABLE = "relayshield_api_keys"
TTL_DAYS = 90
OPT_IN_FIELD = "verifier_telemetry_opt_in"
OPT_IN_AT_FIELD = "verifier_telemetry_opt_in_at"

VERIFIER_TYPES = ("tap", "pap", "x401", "tap+x401")
ATTACK_PATTERNS = ("", "wallet", "domain", "wallet+domain")

# The closed set a row may carry. Anything a verifier says that is not mapped lands on
# "other": the raw string is never stored, because reasons can carry request values.
REJECTION_REASONS = (
    "bad_signature", "malformed", "expired", "replay", "unknown_key",
    "intent_mismatch", "mandate_exceeded", "ti_match", "other",
)

_EXACT = {
    "bad_signature": "bad_signature",
    "bad_signature_encoding": "bad_signature",
    "missing_signature_for_label": "bad_signature",
    "signature_too_old": "expired",
    "signature_expired": "expired",
    "created_in_future": "expired",
    "replay_nonce": "replay",
    "unknown_keyid": "unknown_key",
    "intent_mismatch": "intent_mismatch",
    "ti_flagged": "ti_match",
    "mandate_scope_exceeded": "mandate_exceeded",
    "mandate_exceeded": "mandate_exceeded",
    "unknown_issuer": "unknown_key",
    # x401 relying party (current draft)
    "invalid_signature": "bad_signature",
    "holder_binding_failed": "bad_signature",
    "untrusted_issuer": "unknown_key",
    "replayed_nonce": "replay",
    "invalid_nonce": "replay",
    "credential_expired": "expired",
    "credential_not_yet_valid": "expired",
    "expired_request": "expired",
    "claims_not_satisfied": "mandate_exceeded",
    "credential_type_mismatch": "mandate_exceeded",
    "invalid_response": "malformed",
    "invalid_credential": "malformed",
    "unsupported_protocol": "malformed",
}
# Prefix rules for families of "the request was not well formed" reasons.
_PREFIX = (("missing_", "malformed"), ("malformed_", "malformed"), ("bad_", "malformed"),
           ("unsupported_", "malformed"), ("base_construction", "malformed"))

# Reasons that mean OUR infrastructure failed, not that the caller attacked. Reporting
# them would record an outage as an attack.
NOT_AN_ATTACK = frozenset({"nonce_store_error", "ti_unavailable", "jwks_unavailable",
                           "x401_unavailable", "x401_issuers_unconfigured",
                           "x401_internal_error", "proof_required", "verifier_not_configured",
                           "unknown_policy", "status_unavailable", "reference_unavailable"})


def classify_reason(reasons):
    """First reason decides. Returns one value of REJECTION_REASONS, or None when the
    rejection was caused by our own infrastructure and must not be reported."""
    first = ""
    for r in reasons or []:
        if isinstance(r, str) and r:
            first = r
            break
    if not first:
        return "other"
    if first in NOT_AN_ATTACK:
        return None
    if first in _EXACT:
        return _EXACT[first]
    for prefix, label in _PREFIX:
        if first.startswith(prefix):
            return label
    return "other"


def hash_id(value):
    """SHA-256 hex of a trimmed identifier, or "" when there is nothing to hash."""
    if not isinstance(value, str):
        return ""
    value = value.strip()[:512]
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def network_prefix(ip):
    """IPv4 /24 or IPv6 /48 of a GLOBAL address; "" for anything else.

    Private, loopback, link-local and reserved addresses return "": they say nothing
    about an attacker and, when the merchant forwards a proxy's address, they describe
    the merchant's own network."""
    if not isinstance(ip, str):
        return ""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return ""
    if not addr.is_global:
        return ""
    net = ipaddress.ip_network(f"{addr}/{24 if addr.version == 4 else 48}", strict=False)
    return str(net)


def _decision_and_reasons(verdict):
    if isinstance(verdict, dict):
        return verdict.get("decision"), verdict.get("reasons")
    return getattr(verdict, "decision", None), getattr(verdict, "reasons", None)


def build_event(verifier_type, verdict, *, agent_id=None, agent_ip=None, issuer=None,
                screened=(), reporter="", now=None):
    """The row to write, or None. Pure: no I/O, so the whole contract is testable."""
    if verifier_type not in VERIFIER_TYPES:
        return None
    decision, reasons = _decision_and_reasons(verdict)
    if decision != "reject":
        return None
    reason = classify_reason(reasons)
    if reason is None:
        return None
    ts = int(now if now is not None else time.time())
    day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    pattern = ""
    if reason == "ti_match":
        wanted = set(screened or ())
        # Fixed order, not sorted(): "domain+wallet" is not in ATTACK_PATTERNS.
        pattern = "+".join(k for k in ("wallet", "domain") if k in wanted)
        if pattern not in ATTACK_PATTERNS:
            pattern = ""
    item = {
        "pk": f"TELEMETRY#{day}",
        "sk": f"{ts:010d}#{uuid.uuid4().hex}",
        "rejection_reason": reason,
        "verifier_type": verifier_type,
        "ttl": ts + TTL_DAYS * 86400,
    }
    # A DynamoDB key attribute may not be an empty string, and agent_id_hash is the key
    # of the AgentHashIndex GSI. Absent attributes keep the index sparse: a rejection
    # with no agent identifier is simply not in it.
    for name, value in (("agent_id_hash", hash_id(agent_id)),
                        ("ip_prefix", network_prefix(agent_ip)),
                        ("attack_pattern", pattern),
                        ("issuer_hash", hash_id(issuer) if verifier_type in ("x401", "tap+x401") else ""),
                        ("reporter_hash", reporter or "")):
        if value:
            item[name] = value
    return item


def _dynamodb():
    import boto3  # lazily, so the pure functions above import with nothing installed
    return boto3.resource("dynamodb")


def reporter_hash(api_key):
    return hashlib.sha256(str(api_key or "").encode("utf-8")).hexdigest()[:16] if api_key else ""


def _event_header(event, name):
    headers = (event or {}).get("headers") or {}
    lower = name.lower()
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == lower and isinstance(v, str):
            return v.strip()
    return ""


def opted_in(api_event, key_table=None):
    """-> (True, reporter_hash) only for an active key whose record says
    verifier_telemetry_opt_in is exactly True. Every other outcome is (False, "")."""
    try:
        key = _event_header(api_event, "x-rs-api-key") or _event_header(api_event, "x-api-key")
        if not key.startswith("rs_live_"):
            return False, ""
        table = key_table or _dynamodb().Table(API_KEYS_TABLE)
        record = table.get_item(Key={"api_key": key}, ConsistentRead=True).get("Item")
        if not record or not record.get("active") or record.get(OPT_IN_FIELD) is not True:
            return False, ""
        return True, reporter_hash(key)
    except Exception as exc:
        # The message names the exception type only: a boto error string can echo a key.
        logger.warning("verifier telemetry opt-in check failed: %s", type(exc).__name__)
        return False, ""


def maybe_report(verifier_type, verdict, api_event, request=None, *, issuer=None,
                 key_table=None, telemetry_table=None):
    """Record a rejection if, and only if, the account opted in. Never raises.

    `api_event` is the Lambda event of the call to US (it carries the customer's API key).
    `request` is the agent's request the verifier examined. These are different objects
    and mixing them up would store the customer's address instead of the agent's.
    Returns True when a row was written."""
    try:
        if os.environ.get("VERIFIER_TELEMETRY_DISABLED") == "1":
            return False
        decision, reasons = _decision_and_reasons(verdict)
        if decision != "reject":
            return False                      # no DynamoDB access of any kind
        if classify_reason(reasons) is None:
            return False
        ok, reporter = opted_in(api_event, key_table)
        if not ok:
            return False
        request = request if isinstance(request, dict) else {}
        details = getattr(verdict, "details", None) or (verdict.get("details") if isinstance(verdict, dict) else None) or {}
        agent_id = request.get("agent_id") or details.get("keyid")
        # Mirrors what verify_tap_request hands to the TI screen: the wallet, and the
        # merchant domain falling back to the authority.
        screened = [k for k, present in (
            ("wallet", request.get("wallet")),
            ("domain", request.get("merchant_domain") or request.get("authority"))) if present]
        item = build_event(verifier_type, verdict, agent_id=agent_id,
                           agent_ip=request.get("agent_ip"), issuer=issuer,
                           screened=screened, reporter=reporter)
        if item is None:
            return False
        (telemetry_table or _dynamodb().Table(TABLE)).put_item(Item=item)
        return True
    except Exception as exc:
        logger.warning("verifier telemetry write failed: %s", type(exc).__name__)
        return False
