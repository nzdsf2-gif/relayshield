"""Mini App watchlist monitor: the half of the promise nothing was keeping.

`relayshield_watchlist.py` stores a target and says "we will tell you if this
changes". It encrypts the chat_id rather than hashing it, and its own docstring
says why: "we cannot send an alert without the chat_id". Then nothing ever sent
one. There was no scheduled monitor, no notification code and no workflow --
the storage was built for an alert that did not exist.

A promise with no sender is worse than no promise. This file is the sender.

=============================================================================
WHY TON ONLY, AND WHY THAT IS NOT A LIMITATION WE APOLOGISE FOR
=============================================================================

Telegram Mini Apps live inside Telegram's own rules and TON is the chain
Telegram ships. A Mini App that alerts on Ethereum is a Mini App arguing with
its host. So this monitor watches TON and nothing else, deliberately.

Rows of other kinds are NOT deleted and NOT alerted on. They are counted and
logged, so "we are watching 40 things and can only re-check 12 of them" is a
number somebody can read rather than a silence. A watchlist that quietly drops
what it cannot handle is the quiet-alarm shape this repo keeps getting bitten
by, and the fix is always to make the gap visible rather than tidy.

=============================================================================
THE SIGNALS, EACH ONE A CASE WHERE THE USER'S MONEY IS ON THE LINE
=============================================================================

A checker answers "is this bad now". A monitor only earns a notification when
it answers "this became bad since you asked", so every signal below is a DELTA
against a stored snapshot, never a state.

  IOC_LISTED        the address is now in our criminal-channel corpus.
                    The one signal nobody replicating this product has, and the
                    reason the corpus exists. CRITICAL.

  SCAM_FLAGGED      TON's own community database flipped is_scam to true.
                    Covers wallets, jetton masters and NFT collections alike,
                    because all three are accounts on TON. CRITICAL.

  LIQUIDITY_GONE    the token had a pool and now has none. That is the exit,
                    and it is the single most expensive thing that happens to a
                    retail holder on any chain. CRITICAL.

  LIQUIDITY_DRAIN   the pool lost most of its depth without vanishing. A soft
                    rug, and the one people argue about afterwards. CRITICAL.

  PRICE_COLLAPSE    price fell through the floor with liquidity still present.
                    Not necessarily fraud, always worth knowing. HIGH.

  BALANCE_DRAINED   a watched wallet that held a material balance no longer
                    does. This is how a compromise announces itself, and the
                    person watching is often the victim's counterparty. HIGH.

  CONTRACT_DEPLOYED an address that was uninitialized is now running code.
                    You sent funds to something that was not a contract and it
                    is one now. MEDIUM, because it is also how ordinary wallets
                    come into existence.

  VERDICT_WORSENED  the product's own risk_level went up for any other reason.
                    A catch-all so a new upstream flag reaches the user even
                    before it has a named signal here.

THRESHOLDS ARE DELIBERATELY BLUNT. A 60% liquidity fall is a real event and a
6% one is a Tuesday. Tight thresholds produce a bot people mute, and a muted
bot detects nothing at all, so the bias is towards saying less.

=============================================================================
THREE RULES THAT ARE NOT NEGOTIABLE
=============================================================================

1. THE FIRST RUN AGAINST A ROW NEVER ALERTS. A row written before this file
   existed has no snapshot, so every signal would read as "changed from
   nothing" and the first scheduled run would message every user about every
   target at once. The first sighting seeds the snapshot and returns silently.
   This is the single most likely way to get the bot reported as spam, and it
   is one `if` away from happening.

2. IMPROVEMENTS ARE RECORDED, NEVER SENT. An alert is for action. "Good news,
   the thing you were worried about is fine now" at 3am trains people to turn
   alerts off, and the next message they ignore is the one that mattered.

3. IT NEVER SAYS SAFE, in keeping with every other surface. The ceiling on a
   clean re-check is "nothing new against it", and the alert copy says so.

=============================================================================
WHY IT IMPORTS handle_ton_address RATHER THAN CALLING THE VENDORS ITSELF
=============================================================================

Two reasons, and the second is the one that decided it.

This repo already carries four copies of one pattern table and has paid for it.
A monitor with its own TON Center and DexScreener calls is a fifth copy, and it
would drift from the endpoint it is supposed to be monitoring the answer of.

And the alternative that looks cleaner is worse: calling our own public
/v1/ton-address over HTTP would work exactly once per cap window, because the
keyless per-IP cap would see every invocation of this Lambda arriving from one
NAT address and throttle the monitor against itself. An in-process import has
no such problem.

The deployer's resolve_deps grep is `^[[:space:]]*(import|from) relayshield_`,
so the import below is packaged. Checked against that grep, not assumed.
"""

import base64
import html
import json
import logging
import os
import time
import urllib.parse
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key

from relayshield_api import handle_ton_address

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")

WATCHLIST_TABLE  = os.environ.get("WATCHLIST_TABLE", "relayshield_watchlist")
INTEL_IOCS_TABLE = os.environ.get("INTEL_IOCS_TABLE", "relayshield_intel_iocs")
TELEGRAM_API     = "https://api.telegram.org/bot{token}/{method}"

# THE BOT TOKEN IS NOT READ HERE. It is imported from relayshield_watchlist,
# which owns it, and that is the fix for the defect this module's own
# BOT_TOKEN_SECRET constant WAS.
#
# It said "relayshield/telegram-bot-token" with HYPHENS. The secret is
# "relayshield/telegram_bot_token" with UNDERSCORES, so every get_secret_value
# raised ResourceNotFoundException and EVERY ALERT THIS MONITOR EVER TRIED TO
# SEND FAILED -- in the one function whose whole job is to keep the promise the
# watchlist makes, and with no trace but a WARNING line saying the send failed.
# Same one-character defect as relayshield_watchlist.py's, in the file nobody
# re-checked after fixing that one.
#
# This module's own _get_secret unwrapped the JSON envelope correctly, which is
# worth saying plainly: it was not wrong, it was reading a name that does not
# exist. It is gone anyway, because four copies of a three-line unwrap is how
# the sibling file ended up with three dead call sites, and the deployer's
# resolve_deps grep packages this import exactly as it packages
# relayshield_api above.
from relayshield_watchlist import bot_token

# TON Center's free tier is one request per second and handle_ton_address makes
# up to three upstream calls per target. Pacing here rather than being throttled
# there: a 429 from an upstream looks identical to "the target has no data",
# which would read as LIQUIDITY_GONE and send a false rug alert.
PACE_SECONDS = float(os.environ.get("WATCHLIST_PACE_SECONDS", "1.2"))

# A Lambda that runs out of time mid-scan leaves half the watchlist unchecked
# and no record of where it stopped. Stopping early on purpose is better: the
# next scheduled run picks the rest up, and the log says how many were skipped.
TIME_BUDGET_SECONDS = int(os.environ.get("WATCHLIST_TIME_BUDGET", "540"))

LIQUIDITY_DRAIN_RATIO = 0.40     # keeping <40% of the pool is a drain
PRICE_COLLAPSE_RATIO  = 0.20     # keeping <20% of the price is a collapse
BALANCE_DRAIN_RATIO   = 0.10     # keeping <10% of the balance is a drain
MATERIAL_BALANCE_TON  = 1.0      # below this, a "drain" is dust moving

_LEVEL_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

def decrypt_field(ciphertext_b64: str) -> str:
    resp = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return resp["Plaintext"].decode()


# ---------------------------------------------------------------------------
# Reading one TON target
# ---------------------------------------------------------------------------

def ton_snapshot(address: str) -> dict:
    """The facts about one TON address, flattened so two of them can be diffed.

    Returns {} when the answer could not be obtained. That is NOT the same as
    "there is nothing there", and every caller below must treat it as "we did
    not look" -- an upstream outage that reads as a drained pool is exactly the
    false rug alert this file must never send.
    """
    try:
        resp = handle_ton_address({"address": address})
    except Exception as exc:
        logger.warning("ton lookup raised: %s", exc)
        return {}

    if resp.get("statusCode") != 200:
        return {}
    try:
        data = json.loads(resp.get("body") or "{}").get("data") or {}
    except ValueError:
        return {}
    if not data:
        return {}

    token = data.get("token") or {}
    snap = {
        "type":       data.get("type") or "",
        "risk_level": str(data.get("risk_level") or "unknown").lower(),
        "risk_flags": [str(f) for f in (data.get("risk_flags") or [])],
        "state":      data.get("state") or "",
    }
    if data.get("type") == "token":
        snap["has_pool"]      = True
        snap["liquidity_usd"] = _num(token.get("liquidity_usd"))
        snap["price_usd"]     = _num(token.get("price_usd"))
        snap["symbol"]        = token.get("token_symbol") or ""
    else:
        snap["has_pool"]    = False
        snap["balance_ton"] = _num(data.get("balance_ton"))
    return snap


def _num(value):
    """None stays None. A number that cannot be read is None, not zero.

    Zero would be a lie with consequences here: an unreadable liquidity figure
    coerced to 0 is indistinguishable from a pool that was emptied, and the
    difference between those two is whether we wake somebody up.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ioc_listed(address: str) -> bool:
    """Is this address in the criminal-channel corpus?

    relayshield_intel_iocs is keyed (ioc_value HASH, seen_ts RANGE), so this is
    a bounded query on the partition key and not a scan. Limit 1: the question
    is existence, and pulling every sighting to answer it would be the same
    mistake as counting diff lines to decide drift direction.
    """
    try:
        table = dynamodb.Table(INTEL_IOCS_TABLE)
        resp = table.query(
            KeyConditionExpression=Key("ioc_value").eq(address),
            Select="COUNT",
            Limit=1,
        )
        return bool(resp.get("Count", 0))
    except Exception as exc:
        # An unavailable corpus must not read as "not listed". The caller
        # compares against the stored snapshot, and None means "did not look".
        logger.warning("ioc lookup failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# The diff, which is the whole product
# ---------------------------------------------------------------------------

def detect_changes(previous: dict, current: dict, was_listed, now_listed) -> list:
    """Return the signals that fired, worst first. Pure: no network, no clock.

    Every branch compares two observations. Nothing here fires on a state, so a
    target that has always been flagged produces no alert on every run forever,
    which is the behaviour that decides whether the bot stays unmuted.
    """
    if not previous or not current:
        return []

    out = []

    if now_listed and not was_listed:
        out.append(("IOC_LISTED", "critical",
                    "This address now appears in indicators we collect from "
                    "criminal Telegram channels."))

    was_scam = any("scam" in f.lower() for f in previous.get("risk_flags") or [])
    now_scam = any("scam" in f.lower() for f in current.get("risk_flags") or [])
    if now_scam and not was_scam:
        out.append(("SCAM_FLAGGED", "critical",
                    "TON's community database has flagged this address as a scam "
                    "since you added it."))

    prev_liq, cur_liq = previous.get("liquidity_usd"), current.get("liquidity_usd")
    if previous.get("has_pool") and not current.get("has_pool"):
        out.append(("LIQUIDITY_GONE", "critical",
                    "The trading pool for this token has gone. There is nothing "
                    "left to sell into."))
    elif prev_liq and cur_liq is not None and prev_liq > 0:
        if cur_liq / prev_liq < LIQUIDITY_DRAIN_RATIO:
            out.append(("LIQUIDITY_DRAIN", "critical",
                        f"Pool depth fell from ${prev_liq:,.0f} to ${cur_liq:,.0f} "
                        f"since you added it."))

    prev_px, cur_px = previous.get("price_usd"), current.get("price_usd")
    if prev_px and cur_px is not None and prev_px > 0:
        if cur_px / prev_px < PRICE_COLLAPSE_RATIO:
            out.append(("PRICE_COLLAPSE", "high",
                        f"Price fell more than "
                        f"{int((1 - PRICE_COLLAPSE_RATIO) * 100)}% since you added it."))

    prev_bal, cur_bal = previous.get("balance_ton"), current.get("balance_ton")
    if (prev_bal is not None and cur_bal is not None
            and prev_bal >= MATERIAL_BALANCE_TON and prev_bal > 0):
        if cur_bal / prev_bal < BALANCE_DRAIN_RATIO:
            out.append(("BALANCE_DRAINED", "high",
                        f"Balance fell from {prev_bal:,.2f} to {cur_bal:,.2f} TON."))

    if previous.get("state") == "uninitialized" and current.get("state") == "active":
        out.append(("CONTRACT_DEPLOYED", "medium",
                    "This address was not a contract when you added it and is "
                    "running code now."))

    named = {s[0] for s in out}
    prev_rank = _LEVEL_RANK.get(previous.get("risk_level", "unknown"), 0)
    cur_rank  = _LEVEL_RANK.get(current.get("risk_level", "unknown"), 0)
    if cur_rank > prev_rank and not named:
        new_flags = [f for f in (current.get("risk_flags") or [])
                     if f not in (previous.get("risk_flags") or [])]
        detail = new_flags[0] if new_flags else "the upstream verdict got worse"
        out.append(("VERDICT_WORSENED", current.get("risk_level", "medium"), detail))

    out.sort(key=lambda s: _LEVEL_RANK.get(s[1], 0), reverse=True)
    return out


# ---------------------------------------------------------------------------
# The message
# ---------------------------------------------------------------------------

_HEADS = {
    "critical": "⛔ <b>Something you are watching just got worse.</b>",
    "high":     "⚠️ <b>Something you are watching just changed.</b>",
    "medium":   "ℹ️ <b>Something you are watching just changed.</b>",
}


def format_alert(target: str, signals: list) -> str:
    """HTML, not legacy Markdown, and that is a rule rather than a preference.

    Telegram's legacy Markdown has NO ESCAPE SYNTAX: a backslash before an
    underscore renders as a visible backslash, and a TON address or a URL is
    full of characters that open formatting runs. An alert is also the message
    with the most structure in the product, which is the case CLAUDE.md already
    says HTML is for. So the whole class is sidestepped rather than defended
    against, and html.escape does the work that no backslash can.
    """
    worst = signals[0][1] if signals else "medium"
    lines = [_HEADS.get(worst, _HEADS["medium"]), "",
             "<code>%s</code>" % html.escape(target), ""]
    for _, _, detail in signals:
        lines.append("• " + html.escape(detail))
    lines += ["",
              "<i>You asked us to watch this. Re-checked against TON's account "
              "data, DEX liquidity and our own indicator corpus.</i>",
              "",
              '<a href="https://t.me/relayshield_bot/idcheck?startapp=alert">'
              'Open RelayShield IDCheck</a>']
    return "\n".join(lines)


def send_alert(chat_id: str, text: str) -> bool:
    token = bot_token()
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        TELEGRAM_API.format(token=token, method="sendMessage"),
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as exc:
        # A user who blocked the bot is a 403 here and is not an error worth
        # reddening a run over. It IS worth logging, because a rising 403 rate
        # is the only measurement of people muting us.
        logger.warning("alert send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _rows(table):
    """Every watch row. Scan, deliberately, and with the reason written down.

    There is no index on `kind`, and adding one to filter TON rows would cost a
    GSI on a table whose whole design is that it leaks nothing. At this size a
    scan is cents. Revisit when the row count has an extra digit, not before --
    and the log line below is what says when that is.
    """
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            yield item
        key = resp.get("LastEvaluatedKey")
        if not key:
            return
        kwargs["ExclusiveStartKey"] = key


def lambda_handler(event, context):
    if event.get("source") == "ci.import-probe":
        # The deployer invokes what it deploys to prove the package imports, and
        # this handler would otherwise start a full watchlist sweep on every
        # deploy. Three lines, and every handler that does real work on invoke
        # needs them.
        return {"ok": True, "probe": True}

    started = time.time()
    table = dynamodb.Table(WATCHLIST_TABLE)

    stats = {"rows": 0, "ton": 0, "seeded": 0, "checked": 0, "unreadable": 0,
             "alerted": 0, "send_failed": 0, "skipped_not_ton": 0,
             "lookup_failed": 0, "ran_out_of_time": 0}

    for row in _rows(table):
        stats["rows"] += 1

        if time.time() - started > TIME_BUDGET_SECONDS:
            stats["ran_out_of_time"] += 1
            continue

        if row.get("kind") != "ton":
            # Counted, not deleted, and not silently dropped. See the module
            # docstring: a watchlist that hides what it cannot re-check is
            # indistinguishable from one that is working.
            stats["skipped_not_ton"] += 1
            continue
        stats["ton"] += 1

        try:
            target = decrypt_field(row["target_enc"])
        except Exception:
            logger.warning("row failed to decrypt watch_id=%s", row.get("watch_id"))
            stats["unreadable"] += 1
            continue

        current = ton_snapshot(target)
        time.sleep(PACE_SECONDS)
        if not current:
            # "We did not look" is not "nothing is there". Leaving the stored
            # snapshot untouched means the next run diffs against the last real
            # observation rather than against an outage.
            stats["lookup_failed"] += 1
            continue
        stats["checked"] += 1

        now_listed = ioc_listed(target)
        previous   = _stored_snapshot(row)
        was_listed = row.get("last_ioc_listed")

        if previous is None:
            # RULE 1. A row with no snapshot has never been observed by this
            # monitor, so every signal would read as a change. Seed and move on.
            _store_snapshot(table, row, current, now_listed)
            stats["seeded"] += 1
            continue

        signals = detect_changes(previous, current,
                                 was_listed if isinstance(was_listed, bool) else False,
                                 now_listed if isinstance(now_listed, bool) else False)

        _store_snapshot(table, row, current, now_listed)

        if not signals:
            continue

        try:
            chat_id = decrypt_field(row["chat_id_enc"])
        except Exception:
            logger.warning("cannot decrypt chat_id watch_id=%s", row.get("watch_id"))
            stats["unreadable"] += 1
            continue

        if send_alert(chat_id, format_alert(target, signals)):
            stats["alerted"] += 1
            logger.info("watchlist alert sent signals=%s",
                        ",".join(s[0] for s in signals))   # never the target
        else:
            stats["send_failed"] += 1

    logger.info("watchlist monitor %s", json.dumps(stats))
    return {"ok": True, "stats": stats}


def _stored_snapshot(row: dict):
    raw = row.get("last_snapshot")
    if not raw:
        return None
    if isinstance(raw, dict):
        return _floats(raw)
    try:
        return _floats(json.loads(raw))
    except (ValueError, TypeError):
        return None


def _floats(snap: dict) -> dict:
    """DynamoDB hands numbers back as Decimal and Decimal/float comparisons are
    a TypeError waiting for the first token with a price. Normalise once, here,
    rather than at every comparison site."""
    out = dict(snap)
    for key in ("liquidity_usd", "price_usd", "balance_ton"):
        if key in out:
            out[key] = _num(out[key])
    return out


def _store_snapshot(table, row, snapshot: dict, listed) -> None:
    expr = {":s": json.dumps(snapshot), ":t": int(time.time()),
            ":l": snapshot.get("risk_level", "unknown")}
    names = "SET last_snapshot = :s, checked_at = :t, last_level = :l"
    if isinstance(listed, bool):
        names += ", last_ioc_listed = :i"
        expr[":i"] = listed
    table.update_item(
        Key={"user_key": row["user_key"], "target_id": row["target_id"]},
        UpdateExpression=names,
        ExpressionAttributeValues=expr,
    )
