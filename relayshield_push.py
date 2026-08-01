"""
relayshield_push.py — Server-side wallet monitoring push notifications

Scheduled by EventBridge every 6 hours.

For each registered push token in relayshield_push_tokens:
  1. Scan registered wallet addresses via GoPlus /wallet-risk
  2. Compare to stored last_score on the record
  3. If score changed ≥5 points → send Expo push notification
  4. Update stored score on the record

Expo Push API: https://exp.host/--/api/v2/push/send
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb          = boto3.resource("dynamodb", region_name="us-east-1")
PUSH_TOKENS_TABLE = "relayshield_push_tokens"
EXPO_PUSH_URL     = "https://exp.host/--/api/v2/push/send"
GOPLUS_WALLET_URL = "https://api.gopluslabs.io/api/v1/address_security/{address}"
SCORE_CHANGE_THRESHOLD = 5

LEVEL_TO_SCORE = {"LOW": 20, "MEDIUM": 45, "HIGH": 70, "CRITICAL": 90}


def _wallet_entry(entry) -> str:
    """Pull the address string out of a stored wallet entry.

    relayshield_push_tokens stores wallet_addresses as a list of dicts shaped
    {chain, address, label}, but this loop used to pass each entry straight
    into _goplus_wallet_risk as if it were a string, so every run died with
    "'dict' object has no attribute 'startswith'". Accepts the legacy
    list-of-strings shape too, since older records may still carry it.
    """
    if isinstance(entry, dict):
        return str(entry.get("address") or "").strip()
    return str(entry or "").strip()


def _detect_chain(address: str) -> str:
    """Chain inferred from the address itself, not from the stored `chain`.

    The stored value is not reliable -- live data has bc1pxuu4z87... (a
    Bitcoin bech32 address) recorded with chain "solana". Sending that to
    GoPlus's Solana endpoint returns meaningless output that would then be
    scored and pushed to the user as a wallet risk change.
    """
    a = address.strip()
    if a.lower().startswith("0x") and len(a) == 42:
        return "evm"
    if a.lower().startswith(("bc1", "tb1")) or (a[:1] in ("1", "3") and 26 <= len(a) <= 35):
        return "bitcoin"
    if a[:2] in ("EQ", "UQ") and len(a) >= 48:
        return "ton"
    if 32 <= len(a) <= 44:
        return "solana"
    return "unknown"


# GoPlus address_security covers EVM chains and Solana only.
_GOPLUS_SUPPORTED_CHAINS = frozenset({"evm", "solana"})


def _goplus_wallet_risk(address: str, chain: str = "") -> tuple[str, int, list[str]]:
    """Call GoPlus address_security. Returns (risk_level, score, flags)."""
    chain = chain or _detect_chain(address)
    if chain == "solana":
        url = f"https://api.gopluslabs.io/api/v1/address_security/{address}?chain_id=solana"
    else:
        url = GOPLUS_WALLET_URL.format(address=address.lower())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-Push/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        result = data.get("result", {})
        # Determine risk level from flags
        critical_flags = []
        high_flags = []
        for k, v in result.items():
            if str(v) == "1":
                if k in ("honeypot_related_address", "stealing_attack", "phishing_activities",
                         "fake_token", "mixer", "cybercrime", "sanctioned", "malicious_mining_activities"):
                    critical_flags.append(k.replace("_", " "))
                elif k in ("darkweb_transactions", "data_source_darkweb", "reinit"):
                    high_flags.append(k.replace("_", " "))
        if critical_flags:
            level, score = "CRITICAL", 90
            flags = critical_flags
        elif high_flags:
            level, score = "HIGH", 70
            flags = high_flags
        else:
            level, score = "LOW", 20
            flags = []
        return level, score, flags
    except Exception as exc:
        logger.warning("GoPlus wallet risk failed address=%s: %s", address, exc)
        return "LOW", 20, []


def _send_expo_push(push_token: str, title: str, body: str, data: dict = None) -> bool:
    """Send a push notification via Expo Push API."""
    payload = json.dumps({
        "to":    push_token,
        "sound": "default",
        "title": title,
        "body":  body,
        "data":  data or {},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            EXPO_PUSH_URL,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            tickets = result.get("data", [])
            if tickets and tickets[0].get("status") == "ok":
                logger.info("Push sent to %s: %s", push_token[:20], title)
                return True
            else:
                logger.warning("Push ticket error: %s", tickets)
                return False
    except Exception as exc:
        logger.error("Expo push failed token=%s: %s", push_token[:20], exc)
        return False


NFT_FLOOR_DROP_THRESHOLD = 0.15   # alert when floor drops ≥15% since last check
MAGIC_EDEN_STATS_URL     = "https://api-mainnet.magiceden.dev/v2/collections/{symbol}/stats"


def _check_nft_floor(symbol: str) -> float | None:
    """Return current floor in SOL from Magic Eden, or None on failure."""
    try:
        url = MAGIC_EDEN_STATS_URL.format(symbol=symbol.lower())
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-Push/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        raw = data.get("floorPrice", 0) or 0
        return float(raw) / 1e9  # lamports → SOL
    except Exception:
        return None


def _monitor_nft_floors(record: dict) -> list[tuple[str, str, dict]]:
    """Check NFT collection floors, return list of (title, body, data) for alerts."""
    collections    = record.get("nft_collections", [])     # list of ME slugs
    stored_floors  = record.get("nft_floors", {})          # {"slug": last_floor_sol}
    alerts = []
    new_floors = dict(stored_floors)

    for slug in collections[:5]:
        floor = _check_nft_floor(slug)
        if floor is None:
            continue
        prev = float(stored_floors.get(slug, -1))
        new_floors[slug] = floor
        if prev <= 0:
            continue   # first check — store baseline
        drop_pct = (prev - floor) / prev if prev > 0 else 0
        if drop_pct >= NFT_FLOOR_DROP_THRESHOLD:
            alerts.append((
                f"📉 NFT floor drop: {slug}",
                f"Floor dropped {drop_pct*100:.0f}%: {prev:.3f} → {floor:.3f} SOL",
                {"collection": slug, "floor": floor, "prev": prev},
            ))

    return alerts, new_floors


def _update_token_record(table, push_token: str, updates: dict) -> None:
    """Update fields on a push token record."""
    expr_parts = []
    attr_names = {}
    attr_values = {}
    for i, (k, v) in enumerate(updates.items()):
        placeholder = f"#f{i}"
        value_ph    = f":v{i}"
        attr_names[placeholder] = k
        attr_values[value_ph]   = v
        expr_parts.append(f"{placeholder} = {value_ph}")
    table.update_item(
        Key={"push_token": push_token},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def lambda_handler(event, context):
    logger.info("Push monitor started trigger=%s", event.get("source", "unknown"))
    table  = dynamodb.Table(PUSH_TOKENS_TABLE)
    pushed = 0
    scanned = 0

    try:
        resp   = table.scan(FilterExpression=Attr("active").eq(True))
        tokens = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp   = table.scan(FilterExpression=Attr("active").eq(True),
                                ExclusiveStartKey=resp["LastEvaluatedKey"])
            tokens.extend(resp.get("Items", []))
    except Exception as exc:
        logger.error("Failed to scan push_tokens table: %s", exc)
        return {"statusCode": 500, "body": "table scan failed"}

    logger.info("Found %d registered push tokens", len(tokens))

    for record in tokens:
        push_token     = record.get("push_token", "")
        wallet_addrs   = record.get("wallet_addresses", [])
        stored_scores  = record.get("wallet_scores", {})  # {"address": score}

        if not push_token or not wallet_addrs:
            continue

        new_scores = dict(stored_scores)
        notifications_to_send = []

        for entry in wallet_addrs[:5]:  # cap at 5 per token to stay within timeout
            address = _wallet_entry(entry)
            if not address:
                continue
            chain = _detect_chain(address)
            if chain not in _GOPLUS_SUPPORTED_CHAINS:
                # Bitcoin and TON are stored by the app but GoPlus does not
                # cover them. Skipping is correct; sending them to the EVM or
                # Solana endpoint returns output that would be scored and
                # pushed to the user as a real risk change.
                logger.info("Skipping %s wallet %s (unsupported by GoPlus)", chain, address[:12])
                continue
            scanned += 1
            level, score, flags = _goplus_wallet_risk(address, chain)
            prev_score = int(stored_scores.get(address, -1))

            if prev_score == -1:
                # First scan — store baseline, no notification
                new_scores[address] = score
                continue

            delta = score - prev_score
            if abs(delta) >= SCORE_CHANGE_THRESHOLD:
                short_addr = f"{address[:6]}...{address[-4:]}"
                if delta > 0:
                    title = f"⚠️ Wallet risk increased: {prev_score} → {score}"
                    body  = f"{short_addr}: {', '.join(flags[:2]) if flags else level + ' risk detected'}"
                else:
                    title = f"✅ Wallet risk improved: {prev_score} → {score}"
                    body  = f"{short_addr} security posture improved"
                notifications_to_send.append((title, body, {"address": address, "score": score, "prev": prev_score}))
                new_scores[address] = score
            else:
                new_scores[address] = score

        # NFT floor monitoring
        nft_alerts, new_nft_floors = _monitor_nft_floors(record)
        notifications_to_send.extend(nft_alerts)

        # Send all collected notifications
        for title, body, data in notifications_to_send:
            if _send_expo_push(push_token, title, body, data):
                pushed += 1

        # Update stored scores + NFT floors
        updates: dict = {"last_scan": datetime.now(timezone.utc).isoformat()}
        if new_scores != stored_scores:
            updates["wallet_scores"] = new_scores
        if new_nft_floors != record.get("nft_floors", {}):
            updates["nft_floors"] = new_nft_floors
        if updates:
            try:
                _update_token_record(table, push_token, updates)
            except Exception as exc:
                logger.warning("Failed to update push record: %s", exc)

    logger.info("Push monitor complete — scanned=%d pushed=%d", scanned, pushed)
    return {"statusCode": 200, "body": json.dumps({"scanned": scanned, "pushed": pushed})}
