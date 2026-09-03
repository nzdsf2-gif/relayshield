"""RelayShield check for Telegram bots. One function, no dependencies.

    from relayshield_widget import check

    v = check(user_text)
    if v.blocked:
        await message.reply(v.text, parse_mode="Markdown")

Works with aiogram, python-telegram-bot, pyTelegramBotAPI or a raw webhook: it
is a plain function over stdlib, not a framework integration. Python 3.9+.

WHAT IT CHECKS, AND WHAT IT COSTS
---------------------------------
A URL goes to POST /v1/link-check, which answers immediately from RelayShield's
criminal IOC corpus, Google Safe Browsing and domain registration age. A wallet
address goes to POST /v1/wallet-risk, which covers EVM, Solana, TON and Bitcoin.

Both are KEYLESS. There is no signup, no key and no card for the first call, and
a per-IP daily cap rather than a bill. Pass api_key= once you have one and the
cap stops applying:

    https://api.relayshield.net/developers?source=tg-widget

THE TWO RULES THIS FILE IS BUILT AROUND
---------------------------------------
1. IT NEVER RAISES. A bot that crashes because our API had a bad minute gets
   uninstalled that week, and rightly. Every failure path returns a Verdict with
   level "unknown" and a message that says the check did not complete. A timeout
   is not a clean result and is never rendered as one.

2. IT NEVER SAYS "SAFE". The link check is an absence of evidence across three
   sources, not proof of safety, so the ceiling on a clean URL is "nothing known
   against it". Telling someone else's users that a link is safe, in someone
   else's product, is a promise we cannot keep and cannot withdraw.

TELEGRAM MARKDOWN, WHICH IS A TRAP
----------------------------------
Telegram's legacy "Markdown" parse mode HAS NO ESCAPE SYNTAX. A backslash before
an underscore is not an escape there, it is a backslash, and an unclosed entity
makes Telegram reject the whole message with a 400 -- so a URL containing an
underscore can silently drop your reply, verdict and all. RelayShield shipped
that bug and spent a session finding it.

So `.text` puts every attacker-controlled value inside a CODE SPAN, which legacy
Markdown treats as literal, and strips the one character that could close it. If
you prefer HTML, use `.html` with parse_mode="HTML".
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

__all__ = ["check", "Verdict", "API_BASE", "SOURCE"]

API_BASE = "https://api.relayshield.net"
SOURCE = "tg-widget"
UPSELL = "https://api.relayshield.net/developers?source=tg-widget"

# Matches _detect_chain_api in relayshield_api.py. Deliberately duplicated: this
# file is copied into other people's repositories and cannot import ours. The
# server detects the chain again anyway, so a disagreement here costs one
# rejected call, never a wrong verdict.
_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TON = re.compile(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$")
_BTC = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$")
_SOL = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# ronin:0x… is how Ronin addresses are written everywhere in that ecosystem, and
# every wallet-address regex in the world rejects them, ours included. Stripping
# the prefix is one line and turns a rejected message into a checked one.
_RONIN = re.compile(r"^ronin:(0x[0-9a-fA-F]{40})$", re.I)

_BARE_DOMAIN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?:[/?#].*)?$", re.I
)

_HIGH = ("high", "critical")


@dataclass
class Verdict:
    """What the bot needs to answer with, and nothing it has to interpret."""

    target: str
    kind: str = "unsupported"          # "url" | "address" | "unsupported"
    level: str = "unknown"             # critical | high | medium | low | unknown
    ok: bool = False                   # False when the check did not complete
    reasons: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        """True only for blocklist-grade findings. Never true on a failure."""
        return self.level in _HIGH

    @property
    def text(self) -> str:
        """A ready-to-send reply for parse_mode="Markdown"."""
        head = {
            "critical": "⛔ *Critical risk.* Do not proceed.",
            "high": "⚠️ *High risk.* Do not proceed.",
            "medium": "⚠️ *Treat with caution.*",
            "low": "No known red flags.",
            "unknown": "Nothing known against it."
            if self.ok
            else "*Check did not complete.* Treat this as unchecked, not as safe.",
        }[self.level]
        lines = [head, "", f"`{_code_safe(self.target)}`"]
        if self.reasons:
            lines.append("")
            lines += [f"• {_code_safe(r)}" for r in self.reasons]
        if self.level in ("low", "unknown") and self.ok:
            lines += ["", "_An absence of flags is not proof of safety._"]
        lines += ["", f"_Checked with [RelayShield]({UPSELL})._"]
        return "\n".join(lines)

    @property
    def html(self) -> str:
        """The same reply for parse_mode="HTML"."""
        head = {
            "critical": "⛔ <b>Critical risk.</b> Do not proceed.",
            "high": "⚠️ <b>High risk.</b> Do not proceed.",
            "medium": "⚠️ <b>Treat with caution.</b>",
            "low": "No known red flags.",
            "unknown": "Nothing known against it."
            if self.ok
            else "<b>Check did not complete.</b> Treat this as unchecked, not as safe.",
        }[self.level]
        lines = [head, "", f"<code>{_html_escape(self.target)}</code>"]
        if self.reasons:
            lines.append("")
            lines += [f"• {_html_escape(r)}" for r in self.reasons]
        if self.level in ("low", "unknown") and self.ok:
            lines += ["", "<i>An absence of flags is not proof of safety.</i>"]
        lines += ["", f'<i>Checked with <a href="{UPSELL}">RelayShield</a>.</i>']
        return "\n".join(lines)


def _code_safe(value: str) -> str:
    """Legacy Markdown has no escapes, so the only defence inside a code span is
    removing the one character that can close it."""
    return str(value).replace("`", "")


def _html_escape(value: str) -> str:
    return (
        str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def classify(target: str) -> tuple:
    """(kind, normalised_target). Pure, no network. Exposed for testing."""
    raw = (target or "").strip()
    if not raw:
        return "unsupported", raw

    ronin = _RONIN.match(raw)
    if ronin:
        return "address", ronin.group(1)

    if raw.lower().startswith(("http://", "https://")):
        return "url", raw
    for pattern in (_EVM, _TON, _BTC, _SOL):
        if pattern.match(raw):
            return "address", raw
    # A bare domain is what a user actually pastes. Checked AFTER the address
    # patterns: some Solana addresses are 32-44 base58 characters and would
    # otherwise have to be excluded by hand.
    if _BARE_DOMAIN.match(raw) and " " not in raw:
        return "url", "https://" + raw
    return "unsupported", raw


def check(
    target: str,
    *,
    timeout: float = 4.0,
    api_key: str = "",
    source: str = SOURCE,
    api_base: str = API_BASE,
    _transport=None,
) -> Verdict:
    """Screen one URL or wallet address. Returns a Verdict; never raises.

    timeout defaults to 4 seconds because this runs inside a Telegram handler
    and a bot that stalls is worse than a bot that says it could not check.
    """
    kind, normalised = classify(target)
    if kind == "unsupported":
        return Verdict(target=(target or "").strip(), kind=kind, ok=True, level="unknown")

    if kind == "url":
        path, payload = "/v1/link-check", {"url": normalised, "source": source}
    else:
        path, payload = "/v1/wallet-risk", {"address": normalised, "source": source}

    post = _transport or _post
    try:
        body = post(api_base + path, payload, timeout, api_key)
    except Exception:
        # Deliberately bare. Anything at all going wrong out here -- DNS, TLS,
        # a proxy, a JSON change -- must produce an unchecked verdict rather
        # than an exception inside somebody else's message handler.
        return Verdict(target=normalised, kind=kind, ok=False, level="unknown")

    if not isinstance(body, dict) or not body.get("ok"):
        return Verdict(target=normalised, kind=kind, ok=False, level="unknown",
                       raw=body if isinstance(body, dict) else {})

    data = body.get("data") or {}
    if kind == "url":
        level = str(data.get("level") or "unknown").lower()
        reasons = list(data.get("reasons") or [])
    else:
        level = str(data.get("risk_level") or "unknown").lower()
        if level == "clean":
            level = "low"
        reasons = [str(f).replace("_", " ") for f in (data.get("risk_flags") or [])]

    if level not in ("critical", "high", "medium", "low", "unknown"):
        level = "unknown"
    return Verdict(target=normalised, kind=kind, ok=True, level=level,
                   reasons=reasons, raw=data)


def _post(url: str, payload: dict, timeout: float, api_key: str) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": "relayshield-widget/1.0"}
    if api_key:
        headers["X-RS-API-KEY"] = api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 429 is the daily keyless cap and is a real answer, not an outage. It
        # still returns ok=False, because an unchecked target is unchecked
        # whatever the reason.
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"HTTP {exc.code}"}
