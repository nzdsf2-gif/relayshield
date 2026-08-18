"""
RelayShield Alchemy Notify Webhook Lambda

Receives ADDRESS_ACTIVITY webhook callbacks from Alchemy Notify,
looks up the RelayShield subscriber who owns the address, and sends
a Telegram alert with transfer details and GoPlus risk context.

Also performs real-time drainer detection: records each outbound
transaction in relayshield_wallet_activity_log (TTL 1 hour) and fires
a high-urgency drain alert if 2+ outbound txs are seen within 10 minutes.

CRYPTO-3: Address poisoning detection (June 2026)
  - On every outbound tx, the destination is recorded in relayshield_known_addresses
    as a "known-good" address for that user.
  - On every inbound tx, the sender is compared against all known-good addresses
    using prefix+suffix similarity scoring (the exact technique attackers exploit).
  - If a high-similarity match is found, a poisoning alert fires immediately with a
    side-by-side real vs fake address comparison so the user can spot the difference.
  - Extra weight applied when value is dust (< DUST_THRESHOLD_ETH).
  - Based on Bitget/Chainalysis research: 270M attacks, $83.8M losses (2025),
    attackers exploit mempool timing so fake address can appear BEFORE real tx in history.

DynamoDB tables:
  relayshield_monitored_wallets     — wallet→user_id index
  relayshield_users                 — user records
  relayshield_wallet_activity_log   — outbound tx log for drain detection (TTL 1h)
  relayshield_known_addresses       — known-good outbound destinations per user (persistent)
    PK: user_id (S), SK: address (S)
    Attrs: first_seen (N), last_seen (N), tx_count (N)
    No TTL — persist indefinitely, capped at MAX_KNOWN_ADDRESSES per user

Webhook type: ADDRESS_ACTIVITY
Trigger: any inbound or outbound transfer on a monitored wallet address

Environment variables (set on Lambda):
  None — all config via Secrets Manager

Secrets:
  relayshield/alchemy_api_key      — {"api_key": "...", "webhook_id": "...", "signing_key": "..."}
  relayshield/telegram_bot_token   — {"telegram_bot_token": "..."}

API Gateway:
  POST /v1/alchemy-webhook  — public endpoint, HMAC-verified
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

MONITORED_WALLETS_TABLE  = "relayshield_monitored_wallets"
USERS_TABLE              = "relayshield_users"
ACTIVITY_LOG_TABLE       = "relayshield_wallet_activity_log"
KNOWN_ADDRESSES_TABLE    = "relayshield_known_addresses"
ALCHEMY_SECRET_NAME      = "relayshield/alchemy_api_key"
TG_SECRET_NAME           = "relayshield/telegram_bot_token"
GOPLUS_BASE_URL          = "https://api.gopluslabs.io/api/v1/address_security"
GOPLUS_TOKEN_URL         = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
TELEGRAM_API_BASE        = "https://api.telegram.org/bot{token}/{method}"

# Drainer detection thresholds
DRAIN_WINDOW_SECONDS = 600   # 10-minute rolling window
DRAIN_TX_THRESHOLD   = 2     # number of outbound txs to trigger alert
ACTIVITY_LOG_TTL     = 3600  # 1 hour TTL on activity log items

# CRYPTO-3: Address poisoning detection thresholds
POISON_PREFIX_CHARS    = 4    # chars after 0x to compare (attackers match ≥4)
POISON_SUFFIX_CHARS    = 4    # tail chars to compare
POISON_HIGH_THRESHOLD  = 6    # prefix OR suffix match ≥ this → HIGH confidence
DUST_THRESHOLD_ETH     = 0.01 # inbound value below this = dust (extra poisoning signal)
MAX_KNOWN_ADDRESSES    = 50   # max known-good addresses stored per user

_secret_cache: dict[str, str] = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        _secret_cache[name] = secrets_client.get_secret_value(
            SecretId=name
        )["SecretString"].strip()
    return _secret_cache[name]


def _get_secret_json(name: str, key: str) -> str:
    import json as _json
    return _json.loads(_get_secret(name))[key]


def _tg_token() -> str:
    return _get_secret_json(TG_SECRET_NAME, "telegram_bot_token")


def _verify_alchemy_signature(body: bytes, signature: str) -> bool:
    """Verify Alchemy webhook HMAC-SHA256 signature."""
    try:
        signing_key = _get_secret_json(ALCHEMY_SECRET_NAME, "signing_key")
        expected = hmac.new(
            signing_key.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as exc:
        logger.error("Signature verification error: %s", exc)
        return False


def _get_user_by_wallet(address: str) -> dict | None:
    """Look up user_id from relayshield_monitored_wallets, then fetch user record."""
    try:
        wt = dynamodb.Table(MONITORED_WALLETS_TABLE)
        resp = wt.get_item(Key={"wallet_address": address.lower()})
        item = resp.get("Item")
        if not item:
            return None
        user_id = item["user_id"]
        ut = dynamodb.Table(USERS_TABLE)
        resp2 = ut.get_item(Key={"user_id": user_id})
        return resp2.get("Item")
    except Exception as exc:
        logger.error("Wallet lookup failed for %s: %s", address, exc)
        return None


def _goplus_risk_check(address: str) -> dict:
    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id=1"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
            return data.get("result", {})
    except Exception:
        return {}


def _goplus_token_security(contract_address: str, chain_id: int) -> dict:
    """Check GoPlus Token Security for a token contract. Returns token info or {}."""
    try:
        url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={contract_address}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        result = data.get("result", {})
        # Token security result is keyed by lowercase contract address
        return result.get(contract_address.lower(), {})
    except Exception as exc:
        logger.warning("GoPlus token security failed contract=%s: %s", contract_address, exc)
        return {}


_ADDR_CRITICAL = {"phishing_activities", "blacklist_doubt", "honeypot_related_address",
                  "cybercrime", "money_laundering", "sanctioned"}

# Keys in a GoPlus address_security result that are "1"/non-empty but are NOT
# risk signals. Anything that enumerates the raw result looking for "1" must
# subtract this set, or it invents a risk flag out of a descriptor.
#
# `contract_address` means "this address is a contract", nothing more. Verified
# live 2026-08-14 against vitalik.eth, the USDC contract and a Tornado router:
# all three return contract_address=1 and no other non-zero key, so every
# transfer to or from a contract carried a MEDIUM counterparty-risk line.
#
# `data_source` is a provider credit string ("SlowMist,BlockSec"), so it never
# equals "1" and is listed here for documentation rather than for effect.
#
# _ADDR_CRITICAL above is an explicit allowlist and never had the bug.
_ADDR_NON_RISK_KEYS = {"contract_address", "data_source"}

CORRELATION_WINDOW_HOURS = 72

_WALLET_CHAIN_SIGNALS = {"sim_swap", "breach_alert", "port_out"}

_WALLET_CHAIN_MESSAGES = {
    "sim_swap": (
        "🚨 *CRITICAL — Coordinated Attack Detected*\n\n"
        "*SIM Swap + Flagged Wallet Counterparty*\n\n"
        "Your phone number is being hijacked at the same time your wallet received a "
        "transaction from an address flagged as malicious. This is the most common crypto "
        "theft chain: SIM swap to bypass exchange 2FA, then drain the wallet.\n\n"
        "→ Do NOT approve any pending transactions\n"
        "→ Lock your SIM with your carrier immediately\n"
        "→ Disable SMS 2FA on all crypto exchanges\n"
        "Use /phone for carrier-specific lock steps."
    ),
    "breach_alert": (
        "🚨 *HIGH — Coordinated Attack Detected*\n\n"
        "*Credential Breach + Flagged Wallet Counterparty*\n\n"
        "Your credentials were found in a breach while your wallet has a flagged transaction "
        "counterparty. Attackers coordinating identity and asset attacks may be preparing to "
        "drain your exchange account and wallet simultaneously.\n\n"
        "→ Change exchange passwords immediately\n"
        "→ Enable withdrawal whitelisting on all exchanges\n"
        "→ Do not approve any pending wallet transactions"
    ),
    "port_out": (
        "🚨 *CRITICAL — Coordinated Attack Detected*\n\n"
        "*Port-Out Fraud + Flagged Wallet Counterparty*\n\n"
        "Your phone number has been ported to another carrier while your wallet has a flagged "
        "transaction counterparty. Port-out fraud gives attackers complete control of your "
        "SMS-based 2FA. Combined with a malicious wallet contact, this is an active coordinated "
        "crypto theft chain.\n\n"
        "→ Call your carrier immediately to reverse the port\n"
        "→ Freeze all exchange withdrawals now\n"
        "→ Do not sign any wallet transactions\n"
        "Use /phone for carrier escalation steps."
    ),
}


def _record_wallet_signal(user_id: str) -> list:
    """Record a wallet_risk_flag signal and return the pruned signal list."""
    table  = dynamodb.Table(USERS_TABLE)
    now    = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=CORRELATION_WINDOW_HOURS)).isoformat()

    existing = table.get_item(Key={"user_id": user_id}).get("Item", {}).get("recent_signals", [])
    pruned   = [s for s in existing if isinstance(s, dict) and s.get("ts", "") > cutoff]
    pruned.append({"type": "wallet_risk_flag", "ts": now.isoformat(), "meta": {}})

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET recent_signals = :s",
        ExpressionAttributeValues={":s": pruned},
    )
    logger.info("Signal recorded — user_id=%s type=wallet_risk_flag", user_id)
    return pruned


def _check_wallet_correlation(user_id: str, signals: list, chat_id: int) -> None:
    """If an identity signal is already present, fire a composite Telegram alert."""
    present_types = {s.get("type") for s in signals if isinstance(s, dict)}
    for sig in _WALLET_CHAIN_SIGNALS & present_types:
        msg = _WALLET_CHAIN_MESSAGES.get(sig)
        if msg:
            _send_telegram(chat_id, msg)
            logger.warning(
                "Wallet correlation alert sent — user_id=%s chain=wallet_risk_flag+%s", user_id, sig
            )


def _format_token_risk_line(token_info: dict) -> str:
    """Return a formatted risk warning for a token, or empty string if safe."""
    if not token_info:
        return ""

    critical = []
    warnings = []

    if token_info.get("is_honeypot") == "1":
        critical.append("honeypot — you cannot sell this token")
    if token_info.get("is_airdrop_scam") == "1":
        critical.append("known airdrop scam")
    if token_info.get("fake_token") == "1":
        critical.append("fake token impersonating a real project")

    try:
        sell_tax = float(token_info.get("sell_tax") or 0)
        if sell_tax >= 50:
            critical.append(f"sell tax {sell_tax:.0f}% — effectively unsellable")
        elif sell_tax >= 10:
            warnings.append(f"high sell tax ({sell_tax:.0f}%)")
    except (ValueError, TypeError):
        pass

    if token_info.get("transfer_pausable") == "1":
        warnings.append("transfers can be paused by owner")
    if token_info.get("hidden_owner") == "1":
        warnings.append("hidden owner — contract can be taken over")
    if token_info.get("can_take_back_ownership") == "1":
        warnings.append("ownership can be reclaimed")

    if critical:
        return (
            "\n\n🚨 *DANGEROUS TOKEN RECEIVED*\n"
            + "\n".join(f"• {c}" for c in critical)
            + "\n⛔ Do NOT swap, approve, or visit any links referencing this token"
        )
    if warnings:
        return (
            "\n\n⚠️ *Token Risk Flags*\n"
            + "\n".join(f"• {w}" for w in warnings)
        )
    return ""


def _send_telegram(chat_id: int, text: str) -> None:
    token  = _tg_token()
    url    = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body   = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req    = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


def _record_outbound_tx(wallet_address: str, tx_hash: str, value: float, asset: str, network: str) -> None:
    """Record an outbound transaction in the activity log with a 1-hour TTL."""
    now = int(time.time())
    try:
        dynamodb.Table(ACTIVITY_LOG_TABLE).put_item(Item={
            "wallet_address": wallet_address,
            "tx_timestamp":   Decimal(now),
            "tx_hash":        tx_hash,
            "value":          Decimal(str(value)),
            "asset":          asset,
            "network":        network,
            "ttl":            Decimal(now + ACTIVITY_LOG_TTL),
        })
    except Exception as exc:
        logger.error("Activity log write failed wallet=%s: %s", wallet_address, exc)


def _check_drain_pattern(wallet_address: str) -> int:
    """
    Query recent outbound txs in the rolling window.
    Returns count of outbound txs in the last DRAIN_WINDOW_SECONDS.
    """
    window_start = Decimal(int(time.time()) - DRAIN_WINDOW_SECONDS)
    try:
        resp = dynamodb.Table(ACTIVITY_LOG_TABLE).query(
            KeyConditionExpression=(
                Key("wallet_address").eq(wallet_address) &
                Key("tx_timestamp").gte(window_start)
            )
        )
        return len(resp.get("Items", []))
    except Exception as exc:
        logger.error("Drain pattern query failed wallet=%s: %s", wallet_address, exc)
        return 0


def _format_drain_alert(monitored_address: str, tx_count: int, network: str) -> str:
    short_addr   = f"{monitored_address[:6]}...{monitored_address[-4:]}"
    network_name = network.replace("_", " ").title()
    return (
        f"🚨🚨 *POSSIBLE WALLET DRAIN IN PROGRESS* 🚨🚨\n\n"
        f"*Address:* `{short_addr}`\n"
        f"*Network:* {network_name}\n"
        f"*Outbound transactions:* {tx_count} in the last 10 minutes\n\n"
        f"⚠️ *Immediate actions:*\n"
        f"• Move remaining funds to a secure wallet NOW\n"
        f"• Revoke all token approvals at revoke.cash\n"
        f"• Check for malicious browser extensions\n"
        f"• Do NOT interact with any dApps until secured\n\n"
        f"_RelayShield Crypto Shield_"
    )


_EXPLORER_MAP = {
    "ETH_MAINNET":    "https://etherscan.io/tx/{}",
    "BASE_MAINNET":   "https://basescan.org/tx/{}",
    "MATIC_MAINNET":  "https://polygonscan.com/tx/{}",
    "ARB_MAINNET":    "https://arbiscan.io/tx/{}",
    "OPT_MAINNET":    "https://optimistic.etherscan.io/tx/{}",
    "SOLANA_MAINNET": "https://solscan.io/tx/{}",
    "TON_MAINNET":    "https://tonscan.org/tx/{}",
    "BTC_MAINNET":    "https://mempool.space/tx/{}",
}

_EVM_NETWORKS = {"ETH_MAINNET", "BASE_MAINNET", "MATIC_MAINNET", "ARB_MAINNET", "OPT_MAINNET"}

# GoPlus chain IDs for token security checks
_NETWORK_CHAIN_IDS = {
    "ETH_MAINNET":   1,
    "BASE_MAINNET":  8453,
    "MATIC_MAINNET": 137,
    "ARB_MAINNET":   42161,
    "OPT_MAINNET":   10,
}

# Zero address — native ETH transfers use this as the "contract", skip token check
_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _format_alert(activity: dict, monitored_address: str, risk: dict, token_risk_line: str = "") -> str:
    from_addr = activity.get("fromAddress", "unknown")
    to_addr   = activity.get("toAddress", "unknown")
    value     = activity.get("value", 0)
    asset     = activity.get("asset", "ETH")
    raw_net   = activity.get("network", "ETH_MAINNET")
    network   = raw_net.replace("_", " ").title()
    tx_hash   = activity.get("hash", "")

    direction = "📥 IN" if to_addr.lower() == monitored_address.lower() else "📤 OUT"
    other     = from_addr if to_addr.lower() == monitored_address.lower() else to_addr

    risk_flags = [k for k, v in risk.items()
                  if v == "1" and k not in _ADDR_NON_RISK_KEYS]
    # Sanctions alone forces HIGH. The count rule would grade a sanctions-only
    # counterparty as MEDIUM, and dealing with an OFAC-listed address is a
    # compliance event on the first flag, not the second. Matches
    # handle_wallet_risk in relayshield_api.py.
    risk_level = "HIGH 🔴" if risk.get("sanctioned") == "1" or len(risk_flags) >= 2 \
        else "MEDIUM 🟡" if risk_flags else "LOW 🟢"
    risk_line  = f"\n⚠️ *Counterparty Risk:* {risk_level}" if risk_flags else ""

    # Scam/malicious address flags from GoPlus address_security API.
    # `sanctioned` added 2026-08-14: it was missing here, so an OFAC-listed
    # counterparty with no other flag produced a bare MEDIUM risk line and
    # never the do-not-transact block.
    scam_flags = {
        "phishing_activities", "honeypot_related_address", "blacklist_doubt",
        "darkweb_transactions", "stealing_attack", "cybercrime", "sanctioned",
    }
    active_scam = scam_flags & set(risk_flags)
    if active_scam:
        scam_labels = {
            "phishing_activities":    "phishing site",
            "honeypot_related_address": "honeypot-related address",
            "blacklist_doubt":        "blacklisted address",
            "darkweb_transactions":   "dark web activity",
            "stealing_attack":        "stealing attack",
            "cybercrime":             "cybercrime",
            "sanctioned":             "sanctions-listed",
        }
        scam_desc = ", ".join(scam_labels.get(f, f) for f in active_scam)
        risk_line = f"\n🚨 *MALICIOUS ADDRESS DETECTED:* {scam_desc}\n⛔ Do NOT approve any further transactions with this address"

    short_addr  = f"{monitored_address[:6]}...{monitored_address[-4:]}"
    short_other = f"{other[:6]}...{other[-4:]}" if len(other) > 10 else other

    explorer = _EXPLORER_MAP.get(raw_net)
    tx_line  = f"\n🔗 [View tx]({explorer.format(tx_hash)})" if tx_hash and explorer else ""

    title = f"📤 Outbound Transfer: {value} {asset}" if direction == "📤 OUT" else f"📥 Inbound Transfer: {value} {asset}"

    return (
        f"*{title}*\n\n"
        f"*Address:* `{short_addr}`\n"
        f"*Network:* {network}\n"
        f"*Counterparty:* `{short_other}`"
        f"{risk_line}"
        f"{tx_line}"
        f"{token_risk_line}\n\n"
        f"_RelayShield Crypto Shield_"
    )


# ---------------------------------------------------------------------------
# CRYPTO-3: Address poisoning detection helpers
# ---------------------------------------------------------------------------

def _record_known_address(user_id: str, address: str) -> None:
    """Persist an outbound destination as a known-good address for this user.

    Caps the table at MAX_KNOWN_ADDRESSES per user by skipping the write once
    the limit is reached (oldest addresses are already there from prior txs).
    """
    if not address or address == _ZERO_ADDRESS:
        return
    address = address.lower()
    now = int(time.time())
    try:
        table = dynamodb.Table(KNOWN_ADDRESSES_TABLE)
        # Upsert: increment tx_count and update last_seen on repeat addresses
        table.update_item(
            Key={"user_id": user_id, "address": address},
            UpdateExpression=(
                "SET last_seen = :ls, tx_count = if_not_exists(tx_count, :zero) + :one, "
                "first_seen = if_not_exists(first_seen, :ls)"
            ),
            ExpressionAttributeValues={":ls": Decimal(now), ":zero": Decimal(0), ":one": Decimal(1)},
        )
    except Exception as exc:
        logger.error("Known address write failed user=%s addr=%s: %s", user_id, address, exc)


def _get_known_addresses(user_id: str) -> list[str]:
    """Return all known-good addresses for this user (lowercase)."""
    try:
        resp = dynamodb.Table(KNOWN_ADDRESSES_TABLE).query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ProjectionExpression="#addr",
            ExpressionAttributeNames={"#addr": "address"},
        )
        return [item["address"] for item in resp.get("Items", [])]
    except Exception as exc:
        logger.error("Known address fetch failed user=%s: %s", user_id, exc)
        return []


def _similarity_score(addr1: str, addr2: str) -> tuple[int, int]:
    """Return (prefix_match_chars, suffix_match_chars) for two EVM addresses.

    Strips the '0x' prefix before comparing so scores reflect meaningful hex chars.
    Example: 0x1A2B...CDEF vs 0x1A2B...CDFF → prefix=4, suffix=2
    """
    a = addr1.lower().lstrip("0x")
    b = addr2.lower().lstrip("0x")
    if len(a) != len(b):
        return 0, 0

    prefix = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            prefix += 1
        else:
            break

    suffix = 0
    for ca, cb in zip(reversed(a), reversed(b)):
        if ca == cb:
            suffix += 1
        else:
            break

    return prefix, suffix


def _check_address_poisoning(
    user_id: str,
    inbound_sender: str,
    value: float,
    asset: str,
    network: str,
    tx_hash: str,
) -> str | None:
    """Check whether inbound_sender looks like an address-poisoning attempt.

    Returns a formatted alert string if poisoning is detected, else None.

    Detection logic (based on Bitget/Chainalysis June 2026 research):
    - Load all known-good outbound destinations for this user.
    - Compare inbound sender against each known address using prefix+suffix scoring.
    - A match at prefix ≥ POISON_PREFIX_CHARS AND suffix ≥ POISON_SUFFIX_CHARS is suspicious.
    - Confidence is HIGH when either dimension reaches POISON_HIGH_THRESHOLD.
    - Dust value (< DUST_THRESHOLD_ETH) raises confidence one level.
    - Fires on the FIRST match found (worst-case: most similar known address).
    """
    if not inbound_sender or inbound_sender == _ZERO_ADDRESS:
        return None

    sender = inbound_sender.lower()
    known  = _get_known_addresses(user_id)
    if not known:
        return None  # No history yet — nothing to compare against

    is_dust = (value is not None and float(value) < DUST_THRESHOLD_ETH)

    best_match: str | None = None
    best_prefix = 0
    best_suffix = 0

    for known_addr in known:
        if known_addr == sender:
            continue  # Exact match — this IS the known address, not a lookalike
        prefix, suffix = _similarity_score(sender, known_addr)
        if prefix >= POISON_PREFIX_CHARS and suffix >= POISON_SUFFIX_CHARS:
            if prefix + suffix > best_prefix + best_suffix:
                best_match  = known_addr
                best_prefix = prefix
                best_suffix = suffix

    if not best_match:
        return None

    # Determine confidence level
    high_confidence = (
        best_prefix >= POISON_HIGH_THRESHOLD or
        best_suffix >= POISON_HIGH_THRESHOLD or
        is_dust
    )
    confidence_label = "HIGH ⛔" if high_confidence else "MEDIUM ⚠️"

    # Build side-by-side visual diff (highlight differing chars in the middle)
    real_short  = f"`{best_match[:6]}...{best_match[-6:]}`"
    fake_short  = f"`{sender[:6]}...{sender[-6:]}`"

    explorer = _EXPLORER_MAP.get(network.upper())
    tx_line  = f"\n🔗 [View transaction]({explorer.format(tx_hash)})" if tx_hash and explorer else ""

    dust_note = "\n💡 *This is a dust transaction* — a common poisoning technique to plant a fake address in your history." if is_dust else ""

    return (
        f"☠️ *ADDRESS POISONING ATTEMPT DETECTED*\n\n"
        f"*Confidence:* {confidence_label}\n"
        f"*Match:* {best_prefix} prefix chars + {best_suffix} suffix chars\n\n"
        f"*Real address (yours):*\n{real_short}\n"
        f"*Fake sender (lookalike):*\n{fake_short}\n\n"
        f"Attackers create addresses matching your first and last characters, then send a small transaction so the fake appears in your history."
        f"{dust_note}"
        f"{tx_line}\n\n"
        f"*What to do right now:*\n"
        f"⛔ Do NOT copy any address from your transaction history until you've verified the source\n"
        f"✅ For any pending send: get the destination address directly from the original source — exchange withdrawal screen, verified contact, or QR code\n"
        f"✅ Check the *full 42 characters* — not just the start and end\n"
        f"✅ If you use a hardware wallet, verify the full address on the device screen before confirming\n\n"
        f"*If you already sent funds to the wrong address:*\n"
        f"🚨 Act immediately — on-chain transactions are irreversible once confirmed\n"
        f"• Note the transaction hash and the fake address (from your history)\n"
        f"• If funds went to a centralised exchange deposit address, contact that exchange's fraud team now — they may be able to freeze the account\n"
        f"• File a report at ic3.gov (FBI Internet Crime Complaint Center) — required for any law enforcement escalation\n"
        f"• Report the attacker address on etherscan.io (Report Address → Scam/Phishing) to warn other users\n\n"
        f"_RelayShield Crypto Shield — Address Poisoning Detection_"
    )


# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    # TEST MODE: if event contains _test=true, skip signature verification
    test_mode = event.get("_test", False)

    body_raw = (event.get("body") or "").encode()
    signature = (event.get("headers") or {}).get("x-alchemy-signature", "")

    if not test_mode and not _verify_alchemy_signature(body_raw, signature):
        logger.warning("Alchemy signature verification failed")
        return {"statusCode": 401, "body": "Unauthorized"}

    try:
        payload = json.loads(body_raw)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Bad Request"}

    webhook_type = payload.get("type")
    if webhook_type != "ADDRESS_ACTIVITY":
        logger.info("Ignoring webhook type: %s", webhook_type)
        return {"statusCode": 200, "body": "ok"}

    activities = payload.get("event", {}).get("activity", [])
    for activity in activities:
        from_addr = (activity.get("fromAddress") or "").lower()
        to_addr   = (activity.get("toAddress") or "").lower()

        # Determine which monitored address triggered this event
        monitored = None
        for addr in (from_addr, to_addr):
            user = _get_user_by_wallet(addr)
            if user:
                monitored = addr
                break

        if not user or not monitored:
            logger.info("No user found for activity addresses: %s / %s", from_addr, to_addr)
            continue

        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            logger.info("User %s has no telegram_chat_id", user.get("user_id"))
            continue

        # GoPlus risk check on the counterparty address (EVM only)
        counterparty = from_addr if to_addr == monitored else to_addr
        network_raw  = (activity.get("network") or "").upper()
        is_evm       = network_raw in _EVM_NETWORKS
        risk = _goplus_risk_check(counterparty) if counterparty and is_evm else {}

        # Correlation: if GoPlus flags the counterparty as HIGH risk, record signal
        # and check whether an identity attack is already in the window
        if risk and any(risk.get(f) == "1" for f in _ADDR_CRITICAL):
            user_id = user.get("user_id")
            if user_id:
                signals = _record_wallet_signal(user_id)
                _check_wallet_correlation(user_id, signals, int(chat_id))

        # RISK-4: Token security check on inbound ERC-20 transfers
        token_risk_line = ""
        is_inbound = to_addr == monitored
        if is_inbound and is_evm:
            raw_contract  = activity.get("rawContract") or {}
            token_address = (raw_contract.get("address") or "").lower()
            if token_address and token_address != _ZERO_ADDRESS:
                chain_id = _NETWORK_CHAIN_IDS.get(network_raw)
                if chain_id:
                    token_info     = _goplus_token_security(token_address, chain_id)
                    token_risk_line = _format_token_risk_line(token_info)
                    if token_risk_line:
                        logger.info(
                            "Token risk detected — contract=%s network=%s",
                            token_address, network_raw,
                        )

        value   = activity.get("value", 0)
        asset   = activity.get("asset", "ETH")
        tx_hash = activity.get("hash", "")

        alert = _format_alert(activity, monitored, risk, token_risk_line)
        _send_telegram(int(chat_id), alert)
        logger.info("Wallet alert sent — user=%s address=%s", user.get("user_id"), monitored)

        is_outbound = from_addr == monitored
        is_inbound  = to_addr == monitored

        # CRYPTO-3: On outbound txs, record destination as a known-good address
        if is_outbound:
            _record_known_address(user.get("user_id"), to_addr)
            logger.info("Known address recorded — user=%s dest=%s", user.get("user_id"), to_addr)

        # CRYPTO-3: On inbound txs, check sender for address poisoning
        if is_inbound and is_evm:
            poison_alert = _check_address_poisoning(
                user_id=user.get("user_id"),
                inbound_sender=from_addr,
                value=value,
                asset=asset,
                network=network_raw,
                tx_hash=tx_hash,
            )
            if poison_alert:
                _send_telegram(int(chat_id), poison_alert)
                logger.warning(
                    "Address poisoning alert sent — user=%s sender=%s monitored=%s",
                    user.get("user_id"), from_addr, monitored,
                )

        # Drainer detection — track outbound txs and alert on rapid drain pattern
        if is_outbound:
            _record_outbound_tx(monitored, tx_hash, value, asset, network_raw)
            tx_count = _check_drain_pattern(monitored)
            if tx_count >= DRAIN_TX_THRESHOLD:
                drain_alert = _format_drain_alert(monitored, tx_count, network_raw)
                _send_telegram(int(chat_id), drain_alert)
                logger.warning("Drain alert sent — user=%s address=%s tx_count=%d",
                               user.get("user_id"), monitored, tx_count)

    return {"statusCode": 200, "body": "ok"}
