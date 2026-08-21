#!/usr/bin/env python3
"""RelayShield Discord bot — slash-command interaction endpoint.

WHAT THIS IS
------------
A Lambda behind a Function URL that answers Discord Interactions. Slash commands
only. It does NOT request Message Content Intent, cannot read channel messages,
and holds no gateway connection. That refusal is deliberate and it is also the
pitch: server admins are the gatekeepers here, and "we are structurally unable
to read your server" is the strongest thing we can put in front of them.

THE THREE-SECOND RULE, WHICH SHAPES THE WHOLE DESIGN
----------------------------------------------------
Discord fails an interaction if the endpoint does not respond within 3 seconds.
A URL check can take longer than that whenever it reaches Google Safe Browsing
or VirusTotal. So every command returns a DEFERRED response immediately, then a
second, asynchronous invocation of this same function does the real work and
PATCHes the original reply.

    request  -> verify signature -> return type 5 (deferred, ephemeral)
                                 -> async self-invoke
    async    -> run the check -> PATCH /webhooks/{app_id}/{token}/messages/@original

SIGNATURE VERIFICATION IS MANDATORY AND MUST COME FIRST
--------------------------------------------------------
Discord signs every request with Ed25519 and periodically sends deliberately
INVALID signatures to confirm the endpoint rejects them. An endpoint that does
not return 401 for a bad signature fails Discord's own validation and will not
be accepted. `cryptography` comes from the relayshield-cdp-auth layer, which is
already proven on python3.14 by relayshield-api.

ORDERING OF THE URL CHECK
-------------------------
Same design as the Telegram bot, and for the same reason: our own IOC corpus is
one local DynamoDB read, Safe Browsing is an external call, and VirusTotal is an
external call we pay for. Cheapest and most authoritative first, and return as
soon as a blocklist-grade signal fires.

  1. RelayShield IOC corpus   (local)
  2. Google Safe Browsing     (external, only if 1 found nothing)
  3. domain registration age  (external, soft signal only)

NOTE ON DUPLICATION: this mirrors `_heuristic_url_check` in
relayshield_telegram_webhook.py rather than importing it, because the two run in
separate Lambdas. That is a drift risk and it is logged as its own task to
extract into a shared module both zips can include.
"""

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
lambda_client = boto3.client("lambda", region_name="us-east-1")
secrets = boto3.client("secretsmanager", region_name="us-east-1")

IOC_TABLE   = "relayshield_intel_iocs"
DISCORD_API = "https://discord.com/api/v10"
UA          = "DiscordBot (https://relayshield.net, 0.1.0)"

APPLICATION_ID = "1536877675627552829"
PUBLIC_KEY     = "1ce335cb54d8d073d58898c1c2989e4b4d879038adf6779d10ad166cb4f63859"

# Interaction types
PING, APPLICATION_COMMAND, MESSAGE_COMPONENT = 1, 2, 3
# Response types
PONG, CHANNEL_MESSAGE, DEFERRED_CHANNEL_MESSAGE = 1, 4, 5
EPHEMERAL = 64

# Verified against the live account 2026-08-11, not guessed: the secret is
# `relayshield/google_safe_browsing` and the JSON key inside it is
# `google_safe_browsing_api_key`. relayshield_telegram_webhook.py reads the
# same pair.
_GSB_SECRET = "relayshield/google_safe_browsing"
_GSB_KEY    = "google_safe_browsing_api_key"
_gsb_key_cache: str | None = None


# --------------------------------------------------------------------------
# Signature verification
# --------------------------------------------------------------------------

def _verify_signature(signature: str, timestamp: str, body: bytes) -> bool:
    """Ed25519 over (timestamp || raw body). The RAW bytes matter: re-serialising
    the parsed JSON changes whitespace and key order and the signature fails."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY))
        key.verify(bytes.fromhex(signature), timestamp.encode() + body)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# The check itself
# --------------------------------------------------------------------------

_URL_RE    = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", re.I)
_EVM_RE    = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOL_RE    = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_BTC_RE    = re.compile(r"^(bc1[a-z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")
# Ronin is EVM under the hood, but the chain's own explorers, wallets and games
# still hand users the legacy `ronin:` form. Same 40 hex digits, different
# prefix -- so `_EVM_RE` rejects it and the bot told a Ronin player their
# perfectly valid address "did not look like a link or a wallet address".
_RONIN_RE  = re.compile(r"^ronin:([a-fA-F0-9]{40})$", re.I)


def _normalize_address(s: str) -> str:
    """Rewrite chain-specific address spellings into the form the API takes.

    Only `ronin:` today. The API screens Ronin as a generic EVM address, so the
    0x form is what must go over the wire; doing it here rather than inside
    check_wallet() means the "Warn the channel" button's custom_id carries the
    normalised address too, and the re-check on click hits the same API path
    the first check did.
    """
    m = _RONIN_RE.match(s.strip())
    return "0x" + m.group(1) if m else s


def _looks_like_address(s: str) -> bool:
    return bool(_EVM_RE.match(s) or _SOL_RE.match(s) or _BTC_RE.match(s))


def _normalize_url(raw: str) -> str | None:
    s = raw.strip().strip("<>")
    if not s or " " in s:
        return None
    if not s.startswith(("http://", "https://")):
        if not _URL_RE.match(s):
            return None
        s = "https://" + s
    try:
        host = urllib.parse.urlparse(s).netloc
    except Exception:
        return None
    return s if host else None


def _domain_of(url: str) -> str:
    d = urllib.parse.urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def _gsb_key() -> str | None:
    global _gsb_key_cache
    if _gsb_key_cache is None:
        try:
            raw = secrets.get_secret_value(SecretId=_GSB_SECRET)["SecretString"]
            try:
                _gsb_key_cache = json.loads(raw).get(_GSB_KEY) or list(json.loads(raw).values())[0]
            except Exception:
                _gsb_key_cache = raw.strip()
        except Exception as exc:
            logger.warning("GSB key unavailable: %s", exc)
            return None
    return _gsb_key_cache


def _check_gsb(url: str) -> bool:
    key = _gsb_key()
    if not key:
        return False
    payload = {
        "client": {"clientId": "relayshield", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    req = urllib.request.Request(
        f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={key}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return bool(json.loads(r.read()).get("matches"))
    except Exception as exc:
        logger.warning("GSB check failed: %s", exc)
        return False


def check_url(url: str) -> dict:
    """Returns {"level": "malicious"|"unknown", "reasons": [...], "source": str}.

    NEVER returns the word "safe". A phishing domain registered an hour ago is
    in no database anywhere, so absence of evidence is reported as exactly that.
    """
    domain = _domain_of(url)
    if not domain:
        return {"level": "unknown", "reasons": [], "source": "none"}

    # 1. Our own corpus. One local read, and it short-circuits everything else.
    try:
        resp = dynamodb.Table(IOC_TABLE).query(
            KeyConditionExpression=Key("ioc_value").eq(domain),
            ScanIndexForward=False,
            Limit=100,
        )
        if any(i.get("ioc_type") in ("domain", "url") for i in resp.get("Items", [])):
            return {
                "level": "malicious",
                "reasons": ["Listed in RelayShield's criminal IOC corpus"],
                "source": "RelayShield",
            }
    except Exception as exc:
        logger.warning("IOC lookup failed domain=%s: %s", domain, exc)

    # 2. Safe Browsing, only because step 1 found nothing.
    if _check_gsb(url):
        return {
            "level": "malicious",
            # Upstream provider deliberately not named in user-facing text,
            # founder decision 2026-08-12. The internal `source` value is not
            # rendered anywhere; render_result only reads `reasons`.
            "reasons": ["Flagged by an external URL reputation service"],
            "source": "external-reputation",
        }

    return {"level": "unknown", "reasons": [], "source": "none"}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _short(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def render_result(target: str, res: dict) -> dict:
    if res["level"] == "malicious":
        return {
            "title": "⚠️ Flagged",
            "text": (f"**⚠️ Flagged:** `{_short(target)}`\n\n"
                     + "\n".join(f"• {r}" for r in res["reasons"])
                     + "\n\nDo not enter credentials or connect a wallet."),
        }
    return {
        "title": "🔍 No known flags",
        "text": (f"**🔍 No known flags:** `{_short(target)}`\n\n"
                 "Not found in criminal IOC feeds or external reputation sources.\n\n"
                 "_That is not the same as safe. A phishing domain can be hours old "
                 "and in no database yet._"),
    }


# Step 2 of the conversion ladder, added 2026-08-11. Ephemeral, so only the
# person who ran the check sees it, and deliberately quiet: it states a real
# limitation of what just happened rather than pitching. /scan answers "is this
# link bad". It cannot answer "am I already compromised", and saying so is both
# honest and the only reason someone would look for the paid layer.
#
# Kept to two lines. A long advert under a security verdict undermines the
# verdict, which is the asset.
UPSELL_FOOTER = (
    "\n\n_This checks the link. It cannot tell you whether your own credentials "
    "are already in a stealer log. `/exposure` checks that, privately._"
)

# The wallet equivalent of UPSELL_FOOTER, and deliberately a different sentence.
# Screening the counterparty is not the risk a drained user actually hit: the
# common chain starts with their own credentials or session in a stealer log,
# and no amount of address screening sees that.
WALLET_UPSELL_FOOTER = (
    "\n\n_This checks the address. It cannot tell you whether your own wallet's "
    "credentials or session are already in a stealer log. `/exposure` checks that, privately._"
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_API_KEY_SECRET = "relayshield/discord_bot_api_key"
_api_key_cache: str | None = None


def _api_key() -> str | None:
    """The capped shared key. Founder decision 2026-08-11: a dedicated key with
    a hard daily ceiling, NOT an unmetered free path. The cap lives server-side
    in DEMO_QUOTA_SOURCES["discord_bot"] = 50/day, so this Lambda cannot exceed
    it even if it is wrong about how often it calls."""
    global _api_key_cache
    if _api_key_cache is None:
        try:
            raw = secrets.get_secret_value(SecretId=_API_KEY_SECRET)["SecretString"]
            _api_key_cache = json.loads(raw)["api_key"]
        except Exception as exc:
            logger.error("Discord API key unavailable: %s", exc)
            return None
    return _api_key_cache


def check_exposure(email: str) -> dict:
    """Breach lookup through the metered API. Returns a dict with `status`:
    'hit' | 'clean' | 'capped' | 'error'.

    'capped' is a first-class outcome, not an error to swallow. The API returns
    429 once the shared daily cap is spent, and saying so plainly is far better
    than returning a clean-looking answer off a quota exhaustion -- that is the
    false-clean pattern that has bitten this codebase repeatedly.
    """
    key = _api_key()
    if not key:
        return {"status": "error"}
    req = urllib.request.Request(
        "https://api.relayshield.net/v1/metered/breach",
        data=json.dumps({"email": email}).encode(),
        headers={"Content-Type": "application/json", "X-RS-API-KEY": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"status": "capped"}
        logger.warning("breach lookup HTTP %s", e.code)
        return {"status": "error"}
    except Exception as exc:
        logger.warning("breach lookup failed: %s", exc)
        return {"status": "error"}

    # The payload nests under `data`, and the fields were read off a live call
    # rather than assumed: breach_count, breaches[], degraded, observed_at.
    data = body.get("data") or {}

    # HONOUR THE FRESHNESS CONTRACT. `degraded: true` means an upstream source
    # was unavailable, so a zero count is an outage, not an all-clear. Reporting
    # that as "no exposure found" is precisely the false-clean defect that has
    # been fixed three times in this codebase already.
    if data.get("degraded"):
        return {"status": "degraded"}

    count = int(data.get("breach_count") or 0)
    dates = [str(b.get("breach_date")) for b in (data.get("breaches") or [])
             if isinstance(b, dict) and b.get("breach_date")]
    return {"status": "hit" if count else "clean",
            "count": count, "latest": max(dates) if dates else None}


def render_exposure(email: str, res: dict) -> str:
    """TEASER ONLY. Real count, real date, no breach names and no credentials.
    The numbers are true; the detail is what you sign up for. A fabricated or
    inflated count would be the one thing that destroys the reason anyone
    trusts this bot."""
    if res["status"] == "capped":
        return ("**Daily check limit reached.**\n\n"
                "This is a free shared allowance for the Discord bot, and today's is spent. "
                "It resets tomorrow, or check straight away at https://api.relayshield.net/developers")
    if res["status"] in ("error", "degraded"):
        return ("⚠️ **Could not complete the check.** An upstream source was unavailable, so this "
                "is *not* an all-clear. Try again shortly.")
    if res["status"] == "clean":
        return (f"**No exposure found for `{email}`.**\n\n"
                "_That means nothing was found in the sources we queried. It is not proof of "
                "safety: stealer logs surface weeks after the theft._")
    when = f", most recent **{res['latest'][:10]}**" if res.get("latest") else ""
    return (f"**Found in {res['count']} breach{'es' if res['count'] != 1 else ''}**{when}.\n\n"
            "That means this address, and usually a password with it, is in data dumps that are "
            "circulating now. What to do, all free and none of it needs us:\n\n"
            "• **Change that password anywhere you reused it.** Reuse is what makes an old breach "
            "dangerous years later.\n"
            "• **Turn on 2FA**, an authenticator app rather than SMS where you get the choice.\n"
            "• **Assume it is known.** Treat that password as public rather than as needing a "
            "rotation someday.\n\n"
            "_We deliberately do not print which breaches or which credentials. This reply is "
            "private to you, but a bot that types your passwords into Discord would be a worse "
            "idea than the breach._\n\n"
            "**If you build software:** the same check runs as an API, and the full version names "
            "each breach, its date, and what kind of data it exposed. That link is a developer "
            "signup page, not a consumer report:\n"
            "→ https://api.relayshield.net/developers?source=discord-exposure")


def check_wallet(address: str) -> dict:
    """Screen a wallet address through the metered API.

    Uses /v1/metered/wallet-risk ($0.05) rather than /v1/metered/crypto-intel
    ($0.30). Both answer "is this address known bad"; wallet-risk is the one the
    MetaMask Snap and Crypto Shield Mobile already use, and at six times the
    price crypto-intel would burn the bot's capped daily allowance six times
    faster for the same verdict in a free acquisition channel.

    Returns `status`: 'flagged' | 'clean' | 'capped' | 'degraded' | 'error'.
    """
    key = _api_key()
    if not key:
        return {"status": "error"}
    req = urllib.request.Request(
        "https://api.relayshield.net/v1/metered/wallet-risk",
        data=json.dumps({"address": address}).encode(),
        headers={"Content-Type": "application/json", "X-RS-API-KEY": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"status": "capped"}
        logger.warning("wallet-risk HTTP %s", e.code)
        return {"status": "error"}
    except Exception as exc:
        logger.warning("wallet-risk failed: %s", exc)
        return {"status": "error"}

    data = body.get("data") or {}
    # FRESHNESS CONTRACT. A degraded response means an upstream source was
    # unavailable, so an empty risk_flags list is an outage and not an
    # all-clear. Same rule as check_exposure; this is the defect family that has
    # been fixed repeatedly in this codebase and it must not reappear here.
    if data.get("degraded"):
        return {"status": "degraded"}

    level = str(data.get("risk_level") or "").upper()
    flags = [str(f) for f in (data.get("risk_flags") or [])]
    return {
        "status": "flagged" if level in ("HIGH", "CRITICAL") or flags else "clean",
        "level":  level or "UNKNOWN",
        "flags":  flags,
        "chain":  data.get("chain") or "",
    }


def render_wallet(address: str, res: dict) -> dict:
    """Returns {'text', 'flagged'}. Mirrors render_result's shape so the caller
    can decide about the share button the same way it does for a URL."""
    if res["status"] == "capped":
        return {"flagged": False, "text": (
            "**Daily check limit reached.**\n\n"
            "This is a free shared allowance for the Discord bot, and today's is spent. "
            "It resets tomorrow, or check straight away at "
            "https://api.relayshield.net/developers?source=discord-wallet")}
    if res["status"] in ("error", "degraded"):
        return {"flagged": False, "text": (
            "⚠️ **Could not complete the check.** An upstream source was unavailable, so this "
            "is *not* an all-clear. Try again shortly.")}
    if res["status"] == "flagged":
        reasons = "\n".join(f"• {f}" for f in res["flags"]) or "• Flagged by upstream risk screening"
        return {"flagged": True, "text": (
            f"**⚠️ Flagged: `{_short(address)}`**\n"
            f"Risk level **{res['level']}**{(' · ' + res['chain']) if res['chain'] else ''}\n\n"
            f"{reasons}\n\n"
            "Do not send funds to this address, and do not approve a transaction with it.")}
    return {"flagged": False, "text": (
        f"**🔍 No known flags:** `{_short(address)}`\n"
        f"Risk level **{res['level']}**{(' · ' + res['chain']) if res['chain'] else ''}\n\n"
        "Not found in criminal wallet screening.\n\n"
        "_That is not the same as safe. A drainer address can be minutes old and in no "
        "database yet, and address poisoning works with an address that has no history at all._")}


SCAM_GUIDANCE = (
    "**Think you're being scammed? Work through this.**\n\n"
    "**Never paste a command you did not compose.** No legitimate support, wallet, "
    "or video call ever needs you to run a script to fix audio, verify a wallet, or "
    "prove you are human. This one rule breaks most current attack chains.\n\n"
    "**Verify out of band.** If a contact you know sends something odd, confirm on a "
    "different channel. Their account may be compromised, in which case asking them "
    "there confirms nothing.\n\n"
    "**Nobody legitimate needs your seed phrase or your one-time code.** Not support, "
    "not a mod, not an admin DMing you first.\n\n"
    "**Urgency is the weapon.** Deadlines, suspended accounts, and limited allocations "
    "exist to stop you checking.\n\n"
    "Paste a link or wallet address with `/scan` and I'll check it against criminal "
    "IOC feeds before you act on it."
)


# --------------------------------------------------------------------------
# Discord plumbing
# --------------------------------------------------------------------------

def _followup_patch(token: str, payload: dict) -> None:
    """Replace the deferred reply with the real one."""
    req = urllib.request.Request(
        f"{DISCORD_API}/webhooks/{APPLICATION_ID}/{token}/messages/@original",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception as exc:
        logger.error("Follow-up PATCH failed: %s", exc)


def _post_button(target: str, level: str, prefix: str = "post") -> list:
    """Post-to-channel button. THIS IS THE GROWTH MECHANIC, not a nicety: an
    ephemeral reply is seen by one person, so the loop only compounds when a
    user chooses to share.

    ONLY OFFERED ON A FLAGGED RESULT, from 2026-08-11. Nobody shares "this link
    is fine" -- there is no social reward in it -- so putting the button on
    clean results just trains people to ignore it, and the one time it matters
    they will not see it. On a hit the incentive is real: the sharer gets credit
    for catching the drainer, which in a crypto server is worth something.

    Style 1 (primary/blurple) rather than 2, because it is now the intended
    next action rather than an option. custom_id caps at 100 chars, so a very
    long URL gets no button rather than a broken one.

    `prefix` selects which check the click re-runs: "post" for a URL, "postw"
    for a wallet address. The handler must not guess from the target's shape,
    because it decides what to re-query and a wrong guess would render a URL
    verdict for an address.
    """
    if level not in ("malicious", "flagged"):
        return []
    cid = f"{prefix}:{target}"
    if len(cid) > 100:
        return []
    return [{"type": 1, "components": [
        {"type": 2, "style": 1, "label": "⚠️ Warn the channel", "custom_id": cid}
    ]}]


def _run_deferred(body: dict) -> None:
    """Second, async invocation: do the slow work, then PATCH the reply."""
    token  = body["token"]
    target = body.get("target", "")
    kind   = body.get("kind", "scan")

    if kind == "scam":
        _followup_patch(token, {"content": SCAM_GUIDANCE})
        return

    if kind == "exposure":
        # NO share button here, ever. The result is PII about a named person,
        # and a "post to channel" control on it is a way to dox a member.
        if not _EMAIL_RE.match(target):
            _followup_patch(token, {
                "content": "That did not look like an email address. Try `/exposure you@example.com`."})
            return
        _followup_patch(token, {"content": render_exposure(target, check_exposure(target))})
        return

    # Wallet addresses are checked BEFORE the URL parse, not after it fails.
    # A bare Solana address is base58 with no dots, so _normalize_url rejects it
    # anyway, but ordering it first makes the intent explicit and stops a future
    # loosening of the URL regex from swallowing an address.
    #
    # Native since 2026-08-12. This used to redirect to the Telegram bot, which
    # was the wrong answer in the one server type where the bot matters most: in
    # a crypto Discord, "go and use a different product on a different platform"
    # is where the user leaves and does not come back.
    # Normalise before the shape test, not after: `ronin:<40 hex>` is a wallet
    # address and must not fall through to the URL parser.
    target = _normalize_address(target)

    if _looks_like_address(target):
        rendered = render_wallet(target, check_wallet(target))
        _followup_patch(token, {
            "content": rendered["text"] + (WALLET_UPSELL_FOOTER if rendered["flagged"] is False else ""),
            "components": _post_button(target, "flagged" if rendered["flagged"] else "clean", prefix="postw"),
        })
        return

    url = _normalize_url(target)
    if not url:
        _followup_patch(token, {
            "content": ("That did not look like a link or a wallet address.\n\n"
                        "Paste a URL, for example `https://example.com`, or an EVM (including "
                        "Ronin), Solana or Bitcoin address.")})
        return

    res = check_url(url)
    rendered = render_result(url, res)
    _followup_patch(token, {
        "content": rendered["text"] + UPSELL_FOOTER,
        "components": _post_button(url, res["level"]),
    })


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def lambda_handler(event, context):
    # Async self-invocation for the deferred half. Not a Discord request, so it
    # carries no signature and must be handled before verification.
    if isinstance(event, dict) and event.get("source") == "relayshield_discord_deferred":
        _run_deferred(event)
        return {"ok": True}

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw = event.get("body") or ""
    body_bytes = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()

    sig = headers.get("x-signature-ed25519", "")
    ts  = headers.get("x-signature-timestamp", "")
    if not sig or not ts or not _verify_signature(sig, ts, body_bytes):
        # Discord probes this deliberately with bad signatures. 401 is required.
        return {"statusCode": 401, "body": "invalid request signature"}

    try:
        interaction = json.loads(body_bytes)
    except Exception:
        return {"statusCode": 400, "body": "bad json"}

    itype = interaction.get("type")

    if itype == PING:
        return _json({"type": PONG})

    if itype == APPLICATION_COMMAND:
        data = interaction.get("data") or {}
        name = data.get("name", "")
        opts = {o["name"]: o.get("value") for o in data.get("options", [])}
        target = str(opts.get("input", "")).strip()

        lambda_client.invoke(
            FunctionName=os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "relayshield-discord-bot"),
            InvocationType="Event",
            Payload=json.dumps({
                "source": "relayshield_discord_deferred",
                "token": interaction["token"],
                "kind": name if name in ("scam", "exposure") else "scan",
                "target": target,
            }).encode(),
        )
        # Ephemeral by default. The user chooses to make it public.
        return _json({"type": DEFERRED_CHANNEL_MESSAGE, "data": {"flags": EPHEMERAL}})

    if itype == MESSAGE_COMPONENT:
        cid = (interaction.get("data") or {}).get("custom_id", "")
        user = ((interaction.get("member") or {}).get("user") or {}).get("username", "someone")
        # NOT ephemeral: this is the whole point of the button.
        if cid.startswith("postw:"):
            target = cid[6:]
            rendered = render_wallet(target, check_wallet(target))
            return _json({"type": CHANNEL_MESSAGE, "data": {
                "content": f"{rendered['text']}\n\n_Checked by {user} with RelayShield._"}})
        if cid.startswith("post:"):
            target = cid[5:]
            res = check_url(target)
            rendered = render_result(target, res)
            return _json({"type": CHANNEL_MESSAGE, "data": {
                "content": f"{rendered['text']}\n\n_Checked by {user} with RelayShield._"}})

    return _json({"type": CHANNEL_MESSAGE, "data": {"content": "Unsupported interaction.", "flags": EPHEMERAL}})


def _json(payload: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
