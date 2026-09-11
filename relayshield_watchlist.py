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
import re
import time
import urllib.request
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

# SLOTS ARE THE UNIT STARS BUY, AND THAT IS A DELIBERATE CHOICE OVER THE TWO
# OBVIOUS ALTERNATIVES.
#
# Not the check: /v1/link-check and /v1/ton-address are keyless and free, and
# CLAUDE.md's Stars section is explicit that Stars pay vendor bills and never
# tax the free tier. Charging for a check would REMOVE a free feature.
#
# And NOT the alert, which an earlier draft of this design proposed. Charging
# for the message is charging at the exact moment the user needs it, and a
# paywall that fires when somebody's money is already moving is indefensible
# whatever the price. It also makes the free tier a lie: "we will tell you if
# this changes" with an invoice attached is not a promise, it is bait.
#
# A SLOT IS THE HONEST UNIT because it is the one that costs us money. Every
# watched target is a TON Center call, a DexScreener call and a corpus query on
# every cycle, forever, and that bill scales with slots and with nothing else.
# So the free tier watches a few things and alerts on them fully and
# immediately, and Stars buy more of the thing that has a marginal cost.
FREE_WATCH_SLOTS = 3
PAID_WATCH_SLOTS = 25
MAX_WATCHES_PER_USER = PAID_WATCH_SLOTS   # kept: the old name is referenced elsewhere

# 90 days rather than forever. A permanent entitlement bought once is a
# liability that outlives the feature, and a subscription is not available to
# us here: Telegram Stars are a one-off purchase, so the expiry has to live on
# our side or not exist at all.
SLOTS_PRICE_STARS = 50
SLOTS_DURATION_DAYS = 90
ENTITLEMENT_ROW = "__entitlement__"

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


# TON addresses, in both forms the network uses. Mirrors _is_valid_ton_address
# in relayshield_api.py, which is the function that will actually re-check them.
# Duplicated rather than imported on purpose: this module is small and must stay
# importable without pulling in the whole API handler, and a disagreement here
# costs one row classified as a generic address, never a wrong verdict.
_TON_RAW      = re.compile(r"^-?\d+:[0-9a-fA-F]{64}$")
_TON_FRIENDLY = re.compile(r"^[A-Za-z0-9_-]{48}$")


def _normalise(target: str) -> tuple:
    """Return (kind, normalised). Cheap and local: the real classification is
    the widget's, and this only has to decide which endpoint re-checks it.

    "ton" is split out from "address" because it is the only kind anything
    actually re-checks. relayshield_watchlist_monitor.py watches TON and only
    TON, per Telegram's own rules for Mini Apps, and it selects rows on this
    field. A TON address stored as a generic "address" is a row that is watched
    in name and re-checked by nothing -- the exact shape of the promise this
    product was already failing to keep before the monitor existed.
    """
    t = (target or "").strip()
    if not t:
        return "", ""
    if t.startswith(("http://", "https://")):
        return "url", t[:2048]
    if t.startswith("ronin:"):
        return "address", t
    if len(t) > 400:
        return "", ""
    if _TON_RAW.match(t) or _TON_FRIENDLY.match(t):
        return "ton", t
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


def slots_for(table, pk: str) -> tuple:
    """(slots, expires_at). The entitlement is a row in the SAME table, under the
    same hashed user key, at a reserved sort key.

    A separate table would mean a second set of IAM grants, a second backup
    story and a second place a user's data lives, all to hold one integer and
    one timestamp. It would also break the privacy property that makes this
    table safe: everything about one person sits under one unguessable
    partition key, and a second table keyed the same way doubles the surface
    without halving anything.

    An expired entitlement is NOT deleted. Deleting it would lose the record
    that a purchase happened, which is the only thing we could answer a refund
    question with.
    """
    try:
        row = table.get_item(
            Key={"user_key": pk, "target_id": ENTITLEMENT_ROW}
        ).get("Item") or {}
    except Exception as exc:
        # Fail to the FREE tier, never to the paid one. A read failure that
        # silently granted 25 slots would be invisible until the bill arrived.
        logger.warning("entitlement read failed: %s", exc)
        return FREE_WATCH_SLOTS, 0
    expires = int(row.get("slots_expire_at", 0) or 0)
    if expires > int(time.time()):
        return int(row.get("slots", PAID_WATCH_SLOTS) or PAID_WATCH_SLOTS), expires
    return FREE_WATCH_SLOTS, expires


def grant_slots(telegram_user_id, stars_paid: int, charge_id: str = "") -> dict:
    """Credit a Stars purchase. Called by the bot webhook, NOT by the client.

    This is the one function here that does not verify initData, and the reason
    is that it must not: the caller is relayshield_telegram_webhook.py handling
    a successful_payment update that Telegram itself delivered. A client-facing
    version of this function would be a button that grants itself paid slots.

    It is idempotent on charge_id. Telegram retries a webhook it did not get a
    200 from, and a retry that extended the entitlement a second time would be
    a free upgrade for anyone who could make our handler time out once.
    """
    table = dynamodb.Table(TABLE_NAME)
    pk = user_key(telegram_user_id)
    now = int(time.time())
    existing = table.get_item(
        Key={"user_key": pk, "target_id": ENTITLEMENT_ROW}
    ).get("Item") or {}

    if charge_id and charge_id in (existing.get("charge_ids") or []):
        logger.info("stars grant already applied, ignoring retry")
        return {"ok": True, "data": {"slots": int(existing.get("slots", PAID_WATCH_SLOTS)),
                                     "expires_at": int(existing.get("slots_expire_at", 0)),
                                     "duplicate": True}}

    # Extend from whichever is later: an unexpired entitlement is topped up
    # rather than truncated, so buying again early never costs the buyer days.
    base = max(now, int(existing.get("slots_expire_at", 0) or 0))
    expires = base + SLOTS_DURATION_DAYS * 86400
    charges = list(existing.get("charge_ids") or [])
    if charge_id:
        charges = (charges + [charge_id])[-20:]

    table.put_item(Item={
        "user_key":        pk,
        "target_id":       ENTITLEMENT_ROW,
        "slots":           PAID_WATCH_SLOTS,
        "slots_expire_at": expires,
        "stars_paid":      int(stars_paid or 0) + int(existing.get("stars_paid", 0) or 0),
        "charge_ids":      charges,
        "updated_at":      now,
    })
    logger.info("stars grant applied stars=%s expires=%s", stars_paid, expires)
    return {"ok": True, "data": {"slots": PAID_WATCH_SLOTS, "expires_at": expires}}


def stars_invoice(params: dict) -> dict:
    """Mint a Telegram Stars invoice link for the slot upgrade.

    Stars are the ONLY compliant way to charge a consumer inside a Telegram
    Mini App: Telegram requires digital goods to be paid in Stars because that
    is how it satisfies Apple's and Google's in-app-purchase rules. Sending the
    user to Stripe, x402 or the developers page from in here for a digital good
    is the route that gets a bot restricted, and it is exactly what a future
    session would reach for because all three rails already exist one link away.

    currency "XTR" with a single labelled price and NO provider_token is the
    Stars shape. A provider token is what makes it a card payment, so passing
    one here would be a different product that Telegram would reject in this
    context.
    """
    uid = verified_user_id(params.get("init_data", ""))
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}

    token = _get_secret(BOT_TOKEN_SECRET)
    payload = json.dumps({
        "title": "RelayShield watch slots",
        "description": (
            f"Watch up to {PAID_WATCH_SLOTS} TON addresses and tokens for "
            f"{SLOTS_DURATION_DAYS} days. Checking stays free and unlimited."
        ),
        # Read back on successful_payment to know WHAT was bought. Telegram
        # returns it verbatim, so it carries no secret and no user id: the id
        # comes from the update's own `from` field, which Telegram signs.
        "payload": f"slots:{SLOTS_DURATION_DAYS}",
        "currency": "XTR",
        "prices": [{"label": f"{PAID_WATCH_SLOTS} slots, {SLOTS_DURATION_DAYS} days",
                    "amount": SLOTS_PRICE_STARS}],
    }).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/createInvoiceLink",
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        logger.error("createInvoiceLink failed: %s", exc)
        return {"ok": False, "error": "could not start the purchase, try again"}

    if not body.get("ok"):
        logger.error("createInvoiceLink rejected: %s", body.get("description"))
        return {"ok": False, "error": "could not start the purchase, try again"}
    return {"ok": True, "data": {"invoice_link": body["result"],
                                 "stars": SLOTS_PRICE_STARS,
                                 "slots": PAID_WATCH_SLOTS,
                                 "days": SLOTS_DURATION_DAYS}}


def add_watch(params: dict) -> dict:
    uid = verified_user_id(params.get("init_data", ""))
    kind, normalised = _normalise(params.get("target", ""))
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}
    if not kind:
        return {"ok": False, "error": "target is required and must be a URL, domain or address"}

    table = dynamodb.Table(TABLE_NAME)
    pk = user_key(uid)

    slots, _expires = slots_for(table, pk)
    existing = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("user_key").eq(pk),
        Select="COUNT",
    )
    # The entitlement row shares the partition, so it is one of the rows COUNT
    # returns and must not be charged to the user as a watch. Getting this wrong
    # silently costs every paying customer a slot.
    used = max(0, existing.get("Count", 0) - (1 if _has_entitlement_row(table, pk) else 0))
    if used >= slots:
        if slots < PAID_WATCH_SLOTS:
            return {"ok": False, "error": "slots_full", "data": {
                "used": used, "slots": slots,
                "upgrade_stars": SLOTS_PRICE_STARS,
                "upgrade_slots": PAID_WATCH_SLOTS,
                "upgrade_days": SLOTS_DURATION_DAYS,
                "message": (f"You are watching {used} of {slots} free slots. "
                            f"{SLOTS_PRICE_STARS} Stars raises it to "
                            f"{PAID_WATCH_SLOTS} for {SLOTS_DURATION_DAYS} days.")}}
        return {"ok": False,
                "error": f"You are already watching {slots} things, which is the "
                         f"limit. Remove one first."}

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

    # THE FIRST WATCH SENDS A MESSAGE, AND THAT IS THE ANSWER TO "HOW DO I PIN
    # THIS", WHICH HAD BEEN ASKED FOUR TIMES WITHOUT A STRAIGHT ANSWER.
    #
    # Telegram has no primitive for pinning a Mini App. What you pin is a CHAT,
    # and a Mini App opened from a direct link does not create one: the web view
    # opens over the app and the bot never appears in the chat list. So a new
    # user who has never messaged @relayshield_bot has NOTHING to long-press,
    # which is exactly what the founder kept reporting, and every previous
    # answer was about where to find the app rather than about why there was no
    # chat to pin.
    #
    # A bot may message a user who has opened it through a Mini App, and that
    # message is what creates the chat entry. So the first watch produces one.
    # Three things at once, which is why it belongs here rather than behind a
    # button:
    #
    #   1. The chat now exists, so it can be pinned, archived or muted -- all
    #      the things a user expects to be able to do and could not.
    #   2. It PROVES the alert channel before an alert is needed. Discovering
    #      the bot was blocked at the moment something got drained is the worst
    #      possible time to discover it.
    #   3. It turns a Mini App user into a bot subscriber, which is the flywheel
    #      this module's own docstring claims and did not do.
    #
    # Only on the FIRST watch. A confirmation on every add is a notification
    # tax on the feature's own power users.
    if used == 0:
        _greet_first_watch(uid)

    return {"ok": True, "data": {"watching": True, "kind": kind,
                                 "monitored": kind == "ton"}}


def _greet_first_watch(uid) -> None:
    """Send the message that creates the chat. Never raises: a watch that was
    stored is stored, and a failed greeting must not turn a successful add into
    an error the user sees."""
    text = (
        "You are watching your first address. This chat is where the alert "
        "arrives if it changes.\n\n"
        "Pin this chat and you have RelayShield one tap away: press and hold "
        "it in your chat list, then Pin.\n\n"
        "Live re-checks cover TON addresses and tokens. Checking anything else "
        "is still free and unlimited in the app."
    )
    try:
        token = _get_secret(BOT_TOKEN_SECRET)
        try:
            token = json.loads(token).get("bot_token") or json.loads(token).get("token") or token
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        # No parse_mode at all. Legacy Markdown has NO ESCAPE SYNTAX and this
        # text needs no formatting, so the safest option is to ask for none --
        # plain prose is the third item in CLAUDE.md's standing preference and
        # the right one whenever there is nothing to mark up.
        body = json.dumps({"chat_id": uid, "text": text,
                           "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            ok = json.loads(resp.read()).get("ok", False)
        logger.info("first-watch greeting sent=%s", ok)
    except Exception as exc:
        logger.warning("first-watch greeting failed: %s", exc)


def _has_entitlement_row(table, pk: str) -> bool:
    try:
        return bool(table.get_item(
            Key={"user_key": pk, "target_id": ENTITLEMENT_ROW}).get("Item"))
    except Exception:
        return False


def list_watches(params: dict) -> dict:
    uid = verified_user_id(params.get("init_data", ""))
    if not uid:
        return {"ok": False, "error": "unverified: open this inside Telegram"}
    table = dynamodb.Table(TABLE_NAME)
    rows = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("user_key").eq(user_key(uid))
    ).get("Items", [])
    out = []
    slots, expires = FREE_WATCH_SLOTS, 0
    for r in rows:
        if r.get("target_id") == ENTITLEMENT_ROW:
            # The entitlement lives in the same partition, so it arrives in this
            # query. Read it here rather than paying for a second get_item, and
            # never render it as a watched target.
            exp = int(r.get("slots_expire_at", 0) or 0)
            if exp > int(time.time()):
                slots, expires = int(r.get("slots", PAID_WATCH_SLOTS)), exp
            continue
        try:
            target = decrypt_field(r["target_enc"])
        except Exception:
            # A row we cannot decrypt is not a reason to fail the whole list.
            logger.warning("watchlist row failed to decrypt watch_id=%s", r.get("watch_id"))
            continue
        out.append({"watch_id": r.get("watch_id"), "kind": r.get("kind"),
                    "target": target, "last_level": r.get("last_level"),
                    # TON rows are the ones the monitor re-checks. Saying so per
                    # row is how the user can see that a domain they added is
                    # stored and not watched, rather than assuming it is.
                    "monitored": r.get("kind") == "ton",
                    "checked_at": int(r.get("checked_at", 0))})
    out.sort(key=lambda x: x["checked_at"], reverse=True)
    return {"ok": True, "data": {
        "watches": out,
        "used": len(out),
        "limit": slots,
        "slots_expire_at": expires,
        "upgrade_stars": SLOTS_PRICE_STARS,
        "upgrade_slots": PAID_WATCH_SLOTS,
        "upgrade_days": SLOTS_DURATION_DAYS,
    }}


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
    "/v1/watchlist/add":     add_watch,
    "/v1/watchlist/list":    list_watches,
    "/v1/watchlist/remove":  remove_watch,
    "/v1/watchlist/invoice": stars_invoice,
}


# CORS IS NOT COSMETIC HERE, IT IS THE WHOLE FEATURE.
#
# The Mini App is served by cloudflare_worker_miniapp.js on its own hostname and
# calls api.relayshield.net, so every watchlist request is CROSS-ORIGIN from a
# browser. Two things follow, and missing either one makes the button silently
# do nothing while the Lambda logs a perfectly successful call:
#
#   1. The POST sends `content-type: application/json`, which is not a
#      CORS-safelisted value, so the browser sends an OPTIONS PREFLIGHT first.
#      A preflight that 403s or 404s means the real request is never sent.
#   2. The real response needs Access-Control-Allow-Origin or the browser
#      discards a 200 it already has in hand.
#
# relayshield_api.py has carried `Access-Control-Allow-Origin: *` on its
# responses for months. This file did not, and nothing would have reported it:
# curl ignores CORS entirely, so the endpoint tests clean from a terminal and is
# dead in the only client that uses it. That is the quiet-alarm shape again.
#
# `*` rather than the Mini App's origin, deliberately and consistently with the
# rest of the API: these endpoints are authenticated by Telegram's SIGNED
# initData in the body, never by a cookie or an Origin header, so there is no
# ambient authority for an origin allowlist to protect. Locking it to one origin
# would break the widget and every other caller for no security gain.
_CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST,OPTIONS",
    "access-control-max-age": "86400",
}


def _respond(status: int, payload: dict) -> dict:
    return {"statusCode": status,
            "headers": {"content-type": "application/json", **_CORS},
            "body": json.dumps(payload)}


def _method(event: dict) -> str:
    """REST (payload v1) puts it at the top level; HTTP API v2 nests it."""
    return (event.get("httpMethod")
            or event.get("requestContext", {}).get("http", {}).get("method")
            or "POST").upper()


def lambda_handler(event, context):
    # The deployer invokes what it deploys to prove the package imports. Return
    # early rather than touching DynamoDB on a probe.
    if isinstance(event, dict) and event.get("source") == "ci.import-probe":
        return {"statusCode": 200, "body": json.dumps({"ok": True, "probe": True})}

    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")

    # Answer the preflight before anything else, including the route lookup: a
    # preflight carries no body and must succeed on a path the browser has not
    # yet been allowed to POST to.
    if _method(event) == "OPTIONS":
        return {"statusCode": 204, "headers": dict(_CORS), "body": ""}

    handler = ROUTES.get(path)
    if not handler:
        return _respond(404, {"ok": False, "error": f"unknown path {path}"})
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _respond(400, {"ok": False, "error": "invalid JSON"})

    result = handler(body if isinstance(body, dict) else {})
    return _respond(200 if result.get("ok") else 400, result)
