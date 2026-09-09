"""Mini App watchlist: tell a user when the answer about a target CHANGES.

WHY THIS IS THE ONE FEATURE THAT MATTERS. A checker is a utility with no reason
to return, and our moment of need is rare and arrives when the user is not
thinking about us. A watchlist is the only correct answer to "so should I check
again later?", because a clean result today is not a promise about tomorrow --
which every one of our responses already says in its own body.

AND IT RUNS THE FLYWHEEL THE RIGHT WAY ROUND. A Telegram bot may message a user
who has started it, so registering a watch hands off to @relayshield_bot. The
Mini App therefore CREATES bot subscribers, rather than the bot's tiny audience
being asked to carry the Mini App. That was the founder's objection and this is
the answer to it.

=============================================================================
THE PRIVACY DESIGN, WHICH IS THE PART TO READ BEFORE CHANGING ANYTHING
=============================================================================

This is the first thing in the product that stores a record about a PERSON, and
a watchlist is an unusually sensitive one: it is a list of the addresses and
domains somebody is anxious about. Two different protections, because the two
fields need different things:

  THE PARTITION KEY IS A HASH, AND IS NOT REVERSIBLE.
  HMAC-SHA256(pepper, telegram_user_id), pepper from Secrets Manager. So the
  table cannot be read back to a list of Telegram accounts even by someone
  holding a full export, and a lookup still works because we recompute the same
  HMAC from the id the client presents.

  A plain SHA-256 would NOT do. Telegram ids are sequential integers in a space
  small enough to enumerate exhaustively in minutes, so an unpeppered digest is
  a reversible encoding wearing a hash's clothes.

  THE VALUES ARE ENCRYPTED, AND ARE REVERSIBLE ON PURPOSE.
  The watched target and the chat_id go through KMS under the SAME alias the
  email fields already use, `alias/relayshield-data-key`. They must be
  reversible: we cannot send an alert without the chat_id, and we cannot re-run
  a check without the target. Hashing them would make the feature impossible,
  so they are encrypted rather than digested, and the distinction is deliberate.

  Reusing the existing alias is also deliberate. A second key means a second
  rotation story and a second set of grants, and this repo already carries four
  copies of one pattern table.

AND THE IDENTITY IS PROVEN, NOT ASSERTED. This is the hole the first draft of
this file had, caught by its own test suite: the endpoints took
`telegram_user_id` straight from the request body, so ANYONE could post any id
and read or delete a stranger's watchlist. A per-user store that trusts a
client-supplied id has no access control at all.

So the client sends Telegram's `initData` string and the user id is taken from
the VERIFIED payload. Telegram signs initData with a key derived from the bot
token: secret = HMAC-SHA256("WebAppData", bot_token), then the signature is
HMAC-SHA256(secret, data_check_string) where the check string is every field
except `hash`, sorted, joined with newlines. Nobody without the bot token can
forge one. `auth_date` is checked for freshness too, because a signature that
never expires is a bearer token that never expires.

The Mini App worker's own header used to say initData verification was
unnecessary "because nothing here is user-specific". That stopped being true the
moment this file existed, which is exactly the kind of comment that goes stale
silently.

WHAT IS NOT STORED AT ALL: no message text, no contact list, no social graph,
and no history of checks the user ran. The Mini App keeps its scan history in
localStorage on the device for exactly this reason.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")
secrets_client = boto3.client("secretsmanager")

TABLE_NAME    = os.environ.get("WATCHLIST_TABLE", "relayshield_watchlist")
KMS_KEY_ALIAS = os.environ.get("KMS_DATA_KEY_ALIAS", "alias/relayshield-data-key")
PEPPER_SECRET = os.environ.get("WATCHLIST_PEPPER_SECRET", "relayshield/watchlist-pepper")

BOT_TOKEN_SECRET = os.environ.get("BOT_TOKEN_SECRET", "relayshield/telegram-bot-token")
INITDATA_MAX_AGE = 86400          # a signature that never expires is a bearer token

MAX_WATCHES_PER_USER = 25
_SECRET_TTL = 300
_secret_cache: dict = {}


def _get_secret(secret_name: str) -> str:
    """Cached with a TTL, and falls back to the last known good value.

    Same shape as relayshield_mpp_settlement.py's, and for the same reason: a
    module-level cache with NO expiry silently under-billed for hours after a
    rotation, so every secret read in this repo carries a TTL now.
    """
    cached = _secret_cache.get(secret_name)
    if cached and (time.time() - cached[0]) < _SECRET_TTL:
        return cached[1]
    try:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
    except Exception:
        if cached:
            logger.warning("pepper refresh failed, using the cached value")
            return cached[1]
        raise
    _secret_cache[secret_name] = (time.time(), raw)
    return raw


def verified_user_id(init_data: str):
    """Return the Telegram user id from a SIGNED initData string, or None.

    The whole access-control story rests on this function. Never take a user id
    from anywhere else in this module.
    """
    if not init_data or len(init_data) > 4096:
        return None
    try:
        from urllib.parse import parse_qsl
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    their_hash = pairs.pop("hash", "")
    if not their_hash:
        return None

    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    token = _get_secret(BOT_TOKEN_SECRET)
    try:
        parsed = json.loads(token)
        token = parsed.get("bot_token") or parsed.get("token") or token
    except (json.JSONDecodeError, AttributeError):
        pass

    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    ours = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    # compare_digest, not ==, so a timing side channel cannot leak the signature.
    if not hmac.compare_digest(ours, their_hash):
        return None

    try:
        if (time.time() - int(pairs.get("auth_date", "0"))) > INITDATA_MAX_AGE:
            return None
    except ValueError:
        return None

    try:
        return json.loads(pairs.get("user", "{}")).get("id")
    except json.JSONDecodeError:
        return None


def user_key(telegram_user_id) -> str:
    """HMAC, not a bare hash. See the module docstring: Telegram ids are
    sequential integers and an unpeppered digest of one is reversible by
    enumeration."""
    pepper = _get_secret(PEPPER_SECRET).encode()
    return hmac.new(pepper, str(telegram_user_id).encode(), hashlib.sha256).hexdigest()


def encrypt_field(plaintext: str) -> str:
    resp = kms_client.encrypt(KeyId=KMS_KEY_ALIAS, Plaintext=plaintext.encode())
    return base64.b64encode(resp["CiphertextBlob"]).decode()


def decrypt_field(ciphertext_b64: str) -> str:
    resp = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return resp["Plaintext"].decode()


def _normalise(target: str) -> tuple:
    """Return (kind, normalised). Cheap and local: the real classification is
    the widget's, and this only has to decide which endpoint re-checks it."""
    t = (target or "").strip()
    if not t:
        return "", ""
    if t.startswith(("http://", "https://")):
        return "url", t[:2048]
    if t.startswith("ronin:"):
        return "address", t
    if len(t) > 400:
        return "", ""
    if "." in t and " " not in t and "/" not in t:
        return "domain", t.lower()
    return "address", t


def _fingerprint(kind: str, normalised: str) -> str:
    """A stable id for one target, WITHOUT storing the target in the clear.

    The sort key has to be deterministic so adding the same target twice updates
    one row rather than making a second, and it must not leak the target. So it
    is peppered too: an unpeppered digest of a domain is trivially reversed
    against a wordlist of every domain that exists.
    """
    pepper = _get_secret(PEPPER_SECRET).encode()
    return hmac.new(pepper, f"{kind}:{normalised}".encode(), hashlib.sha256).hexdigest()[:32]


def add_watch(params: dict) -> dict:
    uid = verified_user_id(params.get("init_data", ""))
    kind, normalised = _normalise(params.get("target", ""))
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}
    if not kind:
        return {"ok": False, "error": "target is required and must be a URL, domain or address"}

    table = dynamodb.Table(TABLE_NAME)
    pk = user_key(uid)

    existing = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("user_key").eq(pk),
        Select="COUNT",
    )
    if existing.get("Count", 0) >= MAX_WATCHES_PER_USER:
        return {"ok": False,
                "error": f"You are already watching {MAX_WATCHES_PER_USER} things, "
                         f"which is the limit. Remove one first."}

    now = int(time.time())
    table.put_item(Item={
        "user_key":     pk,
        "target_id":    _fingerprint(kind, normalised),
        "kind":         kind,
        # Encrypted, and reversible on purpose: an alert cannot be sent without
        # the chat_id and a re-check cannot run without the target.
        "target_enc":   encrypt_field(normalised),
        "chat_id_enc":  encrypt_field(str(uid)),
        "last_level":   params.get("level") or "unknown",
        "created_at":   now,
        "checked_at":   now,
        "watch_id":     uuid.uuid4().hex[:12],
    })
    logger.info("watchlist add kind=%s", kind)      # never the target itself
    return {"ok": True, "data": {"watching": True, "kind": kind}}


def list_watches(params: dict) -> dict:
    uid = verified_user_id(params.get("init_data", ""))
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}
    table = dynamodb.Table(TABLE_NAME)
    rows = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("user_key").eq(user_key(uid))
    ).get("Items", [])
    out = []
    for r in rows:
        try:
            target = decrypt_field(r["target_enc"])
        except Exception:
            # A row we cannot decrypt is not a reason to fail the whole list.
            logger.warning("watchlist row failed to decrypt watch_id=%s", r.get("watch_id"))
            continue
        out.append({"watch_id": r.get("watch_id"), "kind": r.get("kind"),
                    "target": target, "last_level": r.get("last_level"),
                    "checked_at": int(r.get("checked_at", 0))})
    out.sort(key=lambda x: x["checked_at"], reverse=True)
    return {"ok": True, "data": {"watches": out, "limit": MAX_WATCHES_PER_USER}}


def remove_watch(params: dict) -> dict:
    uid = verified_user_id(params.get("init_data", ""))
    watch_id = params.get("watch_id")
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}
    if not watch_id:
        return {"ok": False, "error": "watch_id is required"}
    table = dynamodb.Table(TABLE_NAME)
    pk = user_key(uid)
    for r in table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("user_key").eq(pk)
    ).get("Items", []):
        if r.get("watch_id") == watch_id:
            table.delete_item(Key={"user_key": pk, "target_id": r["target_id"]})
            return {"ok": True, "data": {"removed": True}}
    return {"ok": False, "error": "not found"}


ROUTES = {
    "/v1/watchlist/add":    add_watch,
    "/v1/watchlist/list":   list_watches,
    "/v1/watchlist/remove": remove_watch,
}


def lambda_handler(event, context):
    # The deployer invokes what it deploys to prove the package imports. Return
    # early rather than touching DynamoDB on a probe.
    if isinstance(event, dict) and event.get("source") == "ci.import-probe":
        return {"statusCode": 200, "body": json.dumps({"ok": True, "probe": True})}

    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    handler = ROUTES.get(path)
    if not handler:
        return {"statusCode": 404,
                "body": json.dumps({"ok": False, "error": f"unknown path {path}"})}
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"ok": False, "error": "invalid JSON"})}

    result = handler(body if isinstance(body, dict) else {})
    return {"statusCode": 200 if result.get("ok") else 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(result)}
