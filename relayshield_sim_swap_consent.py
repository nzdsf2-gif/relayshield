"""Shared SIM swap enrollment and consent contract.

ONE definition of what it means for a phone number to be monitored, imported by
every RelayShield surface that can enroll one: the API (Crypto Shield Mobile and
API customers), the Telegram bot, the WhatsApp webhook and the Stripe webhook.

THE INVARIANT, and the reason this module exists:

    sim_swap_monitoring == True  MEANS  this number's own owner consented.

Nothing may set that flag except through here. `scan_sim_swap_users()` in
relayshield_sim_swap_monitor.py filters on exactly that flag, so the invariant is
what makes the monitored set equal the consented set.

Why a shared module rather than each Lambda writing the table itself: on
2026-08-14 an audit of this feature found four independent defects, one per
surface, all of the same shape.

  * Crypto Shield Mobile stored the number on-device and never sent it, so it
    enrolled nobody.
  * Telegram stored phone_encrypted, told the user "SIM swap monitoring
    activated", and never set the flag, so it also enrolled nobody.
  * The WhatsApp employee path set the flag for OTHER PEOPLE's numbers, which
    the published Terms forbid.
  * Stripe set the flag from a checkout phone with no recorded consent.

Four copies of the write meant four different bugs. This is the one copy.

Carrier context: US carriers require specific consent wording in the Terms, and
the clause reads "YOU authorize your wireless carrier", meaning the subscriber.
That is why third-party enrollment cannot be confirmed by whoever submitted it.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()

USERS_TABLE         = "relayshield_users"
PHONE_HASH_INDEX    = "phone_hash-index"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

# Bump when the carrier consent wording in the Terms changes. Stamped on every
# enrollment so a given number can be tied to the exact text its owner accepted,
# which is what a carrier audit asks for. The carrier authorization clause
# entered https://terms.relayshield.net on 2026-08-14.
CONSENT_TERMS_VERSION = "2026-08-14"

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

CONSENT_SOURCES = {"cs_mobile", "whatsapp", "telegram", "web", "stripe_checkout", "api"}

_dynamodb = boto3.resource("dynamodb")
_kms      = boto3.client("kms")


class AmbiguousPhone(Exception):
    """More than one ACTIVE record shares this number. Refuse rather than guess."""

    def __init__(self, user_ids):
        super().__init__(f"ambiguous phone: {user_ids}")
        self.user_ids = user_ids


def normalise_e164(phone: str) -> str:
    return (phone or "").strip().replace("whatsapp:", "").replace(" ", "")


def is_valid_e164(phone: str) -> bool:
    return bool(E164_RE.match(normalise_e164(phone)))


def hash_phone(phone: str) -> str:
    """SHA-256 of the normalised E.164 number. Deterministic GSI key.

    Must stay byte-identical to the older per-Lambda copies or existing records
    become unfindable.
    """
    return hashlib.sha256(normalise_e164(phone).encode()).hexdigest()


def encrypt_phone(phone: str) -> str:
    """KMS-encrypt the normalised number, base64 for DynamoDB storage."""
    resp = _kms.encrypt(
        KeyId=KMS_PHONE_KEY_ALIAS,
        Plaintext=normalise_e164(phone).encode(),
    )
    return base64.b64encode(resp["CiphertextBlob"]).decode()


def redact(phone: str) -> str:
    """Never log a raw number. This codebase has already had plaintext PII sit
    in CloudWatch with unlimited retention."""
    if not phone:
        return "ph#none"
    return "ph#" + hashlib.sha256(normalise_e164(phone).encode()).hexdigest()[:12]


def find_user_by_phone_hash(phone_hash: str) -> dict | None:
    """Return the user record for this number, or None.

    Deliberately NOT `Limit=1`. A Limit=1 version of this shipped on 2026-08-14
    and picked the wrong record within minutes: the founder's number was on two
    records, a stale deactivated test account and the live one, and enrolling
    through the stale one silently REACTIVATED an account that had been turned
    off to stop the same number being billed to Twilio twice per run.

    Duplicate phone_hash rows are a fact of this table, not a hypothetical.
    Read every match, prefer the active record, and refuse loudly when more than
    one active record shares a number rather than guessing which human is meant.
    """
    items: list[dict] = []
    kwargs = {
        "IndexName": PHONE_HASH_INDEX,
        "KeyConditionExpression": boto3.dynamodb.conditions.Key("phone_hash").eq(phone_hash),
    }
    while True:
        resp = _dynamodb.Table(USERS_TABLE).query(**kwargs)
        items.extend(resp.get("Items") or [])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    if not items:
        return None
    active = [i for i in items if i.get("active") is True]
    if len(active) > 1:
        ids = [i.get("user_id", "?") for i in active]
        logger.error("ambiguous phone_hash: %d active records %s", len(active), ids)
        raise AmbiguousPhone(ids)
    if active:
        return active[0]
    # Only inactive records: revive the most recent rather than forking a new one.
    return sorted(items, key=lambda i: str(i.get("updated_at") or ""), reverse=True)[0]


def enroll(
    phone: str,
    *,
    enrollment_type: str,
    consent_source: str,
    consent_acknowledged: bool = False,
    enrolled_by: str = "",
    extra_attrs: dict | None = None,
) -> dict:
    """Enroll a number, recording who consented and under which Terms.

    enrollment_type:
      "self"        the owner entered it on a surface showing the carrier
                    authorization clause. Requires consent_acknowledged=True.
                    Monitoring starts immediately.
      "third_party" someone enrolled a number that is not theirs. Creates a
                    PENDING record that is NOT monitored and returns a
                    confirmation token. Only the recipient confirming, via
                    confirm(), turns monitoring on.

    Returns {user_id, consent_state, monitoring, terms_version, confirmation_token?}
    Raises ValueError on bad input and AmbiguousPhone on duplicate active records.
    """
    phone = normalise_e164(phone)
    if not is_valid_e164(phone):
        raise ValueError("phone must be in E.164 format, for example +12125551234")
    if enrollment_type not in ("self", "third_party"):
        raise ValueError("enrollment_type must be 'self' or 'third_party'")
    if consent_source not in CONSENT_SOURCES:
        raise ValueError(f"consent_source must be one of: {', '.join(sorted(CONSENT_SOURCES))}")
    # Required rather than defaulted: this flag is what a carrier audit rests on.
    if enrollment_type == "self" and consent_acknowledged is not True:
        raise ValueError("consent_acknowledged must be true for a self enrollment")

    ph        = hash_phone(phone)
    now       = datetime.now(timezone.utc).isoformat()
    existing  = find_user_by_phone_hash(ph)
    confirmed = enrollment_type == "self"
    token     = "" if confirmed else secrets.token_urlsafe(24)

    attrs = {
        "phone_encrypted":       encrypt_phone(phone),
        "phone_hash":            ph,
        "sim_swap_monitoring":   confirmed,
        "active":                True,
        "consent_state":         "CONFIRMED" if confirmed else "PENDING",
        "consent_source":        consent_source,
        "consent_method":        "self_entry" if confirmed else "double_opt_in",
        "consent_terms_version": CONSENT_TERMS_VERSION,
        "updated_at":            now,
    }
    if confirmed:
        attrs["consent_at"] = now
    else:
        attrs["consent_token"] = token
        attrs["consent_requested_at"] = now
    if enrolled_by:
        attrs["enrolled_by_account"] = enrolled_by
    if extra_attrs:
        attrs.update(extra_attrs)

    table = _dynamodb.Table(USERS_TABLE)
    if existing:
        user_id = existing["user_id"]
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in attrs),
            ExpressionAttributeNames={f"#{k}": k for k in attrs},
            ExpressionAttributeValues={f":{k}": v for k, v in attrs.items()},
        )
    else:
        user_id = str(uuid.uuid4())
        table.put_item(Item={"user_id": user_id, "created_at": now, **attrs})

    logger.info(
        "sim-swap enroll phone=%s type=%s source=%s state=%s existing=%s",
        redact(phone), enrollment_type, consent_source, attrs["consent_state"], bool(existing),
    )

    out = {
        "user_id":       user_id,
        "consent_state": attrs["consent_state"],
        "monitoring":    confirmed,
        "terms_version": CONSENT_TERMS_VERSION,
    }
    if not confirmed:
        out["confirmation_token"] = token
    return out


def confirm(phone: str, token: str) -> dict:
    """Complete a double opt-in. The only route from PENDING to monitored.

    Raises LookupError if there is no pending enrollment, PermissionError on a
    bad token, and ValueError if the record is not pending.
    """
    phone = normalise_e164(phone)
    if not is_valid_e164(phone) or not token:
        raise ValueError("phone (E.164) and token are both required")

    existing = find_user_by_phone_hash(hash_phone(phone))
    if not existing:
        raise LookupError("no pending enrollment for that number")
    if existing.get("consent_state") != "PENDING":
        raise ValueError(f"enrollment is not pending (state={existing.get('consent_state')})")

    stored = str(existing.get("consent_token") or "")
    # Constant-time: this token is the only thing between an unconsented number
    # and live carrier lookups.
    if not stored or not secrets.compare_digest(stored, token):
        logger.warning("sim-swap confirm token mismatch phone=%s", redact(phone))
        raise PermissionError("invalid confirmation token")

    now = datetime.now(timezone.utc).isoformat()
    _dynamodb.Table(USERS_TABLE).update_item(
        Key={"user_id": existing["user_id"]},
        UpdateExpression=(
            "SET sim_swap_monitoring = :m, consent_state = :s, consent_at = :c, "
            "consent_method = :cm, updated_at = :u REMOVE consent_token"
        ),
        ExpressionAttributeValues={
            ":m": True, ":s": "CONFIRMED", ":c": now,
            ":cm": "double_opt_in_reply", ":u": now,
        },
    )
    logger.info("sim-swap confirm phone=%s user=%s", redact(phone), existing["user_id"])
    return {"user_id": existing["user_id"], "consent_state": "CONFIRMED", "monitoring": True}


def withdraw(phone: str) -> dict:
    """Withdraw consent. Both the Terms and the Privacy Policy promise this is
    available at any time, so it is a first-class operation."""
    phone = normalise_e164(phone)
    if not is_valid_e164(phone):
        raise ValueError("phone must be in E.164 format")

    existing = find_user_by_phone_hash(hash_phone(phone))
    if not existing:
        raise LookupError("no enrollment for that number")

    now = datetime.now(timezone.utc).isoformat()
    _dynamodb.Table(USERS_TABLE).update_item(
        Key={"user_id": existing["user_id"]},
        UpdateExpression=(
            "SET sim_swap_monitoring = :m, consent_state = :s, "
            "consent_withdrawn_at = :w, updated_at = :u REMOVE consent_token"
        ),
        ExpressionAttributeValues={":m": False, ":s": "WITHDRAWN", ":w": now, ":u": now},
    )
    logger.info("sim-swap withdraw phone=%s user=%s", redact(phone), existing["user_id"])
    return {"user_id": existing["user_id"], "consent_state": "WITHDRAWN", "monitoring": False}


# The exact wording US carriers require, with RelayShield LLC substituted. Any
# surface that enrolls a number must show this before consent is taken. Kept
# here so all four surfaces show identical text and it can never drift.
CARRIER_CONSENT_TEXT = (
    "You authorize your wireless carrier to use or disclose information about "
    "your account and your wireless device, if available, to RelayShield LLC or "
    "its service provider for the duration of your business relationship, solely "
    "to help them identify you or your wireless device and to prevent fraud. "
    "See our Privacy Policy for how we treat your data."
)
