"""
RelayShield — shared forward-analysis core.

Imported by BOTH bot handlers (relayshield_telegram_webhook.py and
relayshield_whatsapp_webhook.py). It is not a Lambda handler and has no
entry point; deploy_lambdas.yml's import walk pulls it into both packages
because both handlers import it by name at module level.


WHAT THIS MODULE IS FOR
-----------------------
Forwarding a message to the bot is the single most natural thing a worried
person does with a suspicious message, and until now both bots ignored the
fact that it WAS a forward. The text got analysed; the provenance — who sent
it, how many hands it has passed through — was thrown away.

This module owns the provenance half only. The content half (brand
impersonation, urgency language, credential lures, embedded-URL checks) already
exists on each platform and is deliberately NOT duplicated here:

    Telegram  handle_analyze()          in relayshield_telegram_webhook.py
    WhatsApp  _build_msgscan_response() in relayshield_whatsapp_webhook.py

So one forward produces two things: a provenance block from here, and the
existing content analysis from there. This module never sends a message, never
touches Twilio or the Telegram API, and holds no platform SDK.


THE ASYMMETRY, WHICH IS THE WHOLE REASON FOR THE SHAPE OF THIS FILE
------------------------------------------------------------------
The two platforms do not give us the same thing, and pretending otherwise
would mean shipping copy on WhatsApp that implies we checked a sender we
never saw.

    Telegram   Message.forward_origin (Bot API 7.0+) is a tagged union:
                 type="user"         -> sender_user, a full User with an id
                                        and usually a username. THIS is what
                                        makes a sender lookup possible at all.
                 type="hidden_user"  -> sender_user_name ONLY. The user has
                                        forward privacy on and Telegram has
                                        deliberately withheld the account.
                                        A display name is not an identity.
                 type="chat"         -> sender_chat (a group).
                 type="channel"      -> chat + message_id.

    WhatsApp   Twilio's inbound webhook sets Forwarded="true" and, separately,
               FrequentlyForwarded="true". That is the entire forwarding
               surface: two booleans. There is NO original sender, no id, no
               name, no handle — not withheld by a privacy setting, simply not
               carried by the WhatsApp Business API at all. The same is true
               of Meta's Cloud API (context.forwarded / frequently_forwarded),
               so this does not change if the transport is ever swapped.

Therefore: sender-side analysis runs ONLY when the origin is genuinely
identifiable, and every attribution state has its own copy. `ATTR_PLATFORM_BLIND`
exists so the WhatsApp reply says, in plain words, that it cannot tell who sent
the message — rather than falling silent and letting the content verdict read
as though a sender had been cleared.

Rendering lives here, in one renderer keyed on attribution state, rather than
in each adapter. Two hand-maintained copies of a caveat is how a caveat goes
missing on one platform: the honest-limits wording is exactly the text that
must not be allowed to drift.


THE OPERATOR-IDENTITY LOOKUP IS A LEAD, AND IS FILTERED ACCORDINGLY
------------------------------------------------------------------
When a Telegram forward does carry a username, it is checked against
relayshield_operator_identities — handles seen in the criminal channels the
intel monitor collects from.

That table is a LEAD LIST, not a verdict, and its own collector says so:
`_RE_TG_CHANNEL` in relayshield_intel_monitor.py matches ANY @mention, person
or channel alike, so ordinary English words have been recorded as operator
handles (`catching`, `normanonrock` are both really in there). At the time of
writing it holds 7 rows, every one at sightings=1.

Telling a user "the person who sent you this appears in criminal channels" on
the strength of a single loose regex match would be an accusation about a
named third party, generated from a row that may only exist because someone
typed an ordinary word after an @. So this module applies the corroboration
filter that CLAUDE.md's A8 entry proposes for collection, at the point of
CONSUMPTION, where the cost of being wrong is highest:

    a hit is surfaced only at >= MIN_SIGHTINGS sightings AND across
    >= MIN_CHANNELS distinct channels.

Below that threshold the lookup stays silent — it does not downgrade the
wording, it says nothing at all, because a hedged accusation is still an
accusation. A surfaced hit is worded as a lead and says outright that a match
can be a coincidence.

Nothing here quotes a corpus size, a row count, or an exclusive-share figure
to the user; per the measurement doctrine those are not defensible at this
volume, and a per-user reply is the worst possible place to put an
undefendable number.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORM_TELEGRAM = "telegram"
PLATFORM_WHATSAPP = "whatsapp"

# Telegram MessageOrigin discriminators, plus one of our own for WhatsApp,
# which has no origin type because it carries no origin.
ORIGIN_USER = "user"
ORIGIN_HIDDEN_USER = "hidden_user"
ORIGIN_CHAT = "chat"
ORIGIN_CHANNEL = "channel"
ORIGIN_UNATTRIBUTED = "unattributed"

# Attribution states. These drive the copy, and they are the reason the
# renderer is a lookup rather than an if-chain in each adapter.
ATTR_SENDER_KNOWN = "sender_known"        # TG: an account we can actually check
ATTR_SENDER_HIDDEN = "sender_hidden"      # TG: forward privacy on, name only
ATTR_CHANNEL = "channel"                  # TG: from a channel or group
ATTR_PLATFORM_BLIND = "platform_blind"    # WA: the platform never tells us

OPERATORS_TABLE = "relayshield_operator_identities"

# Corroboration thresholds — see the module docstring. Raising these makes the
# lookup quieter and more defensible; lowering them starts producing
# accusations out of single loose regex matches.
MIN_SIGHTINGS = 2
MIN_CHANNELS = 2

# Telegram usernames: 5-32 chars, letter first, letters/digits/underscore.
# Same shape the intel monitor's collector uses, so a handle from a forward
# and a handle from a channel scrape normalise to the same key.
_RE_USERNAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$")


# ---------------------------------------------------------------------------
# Normalised origin
# ---------------------------------------------------------------------------

@dataclass
class ForwardOrigin:
    """One forward's provenance, normalised across platforms.

    Absent information is None or False — never a placeholder string. A caller
    must not be able to mistake "WhatsApp did not tell us" for a sender name.
    """
    platform: str
    origin_type: str = ORIGIN_UNATTRIBUTED
    sender_id: str | None = None
    sender_username: str | None = None       # normalised: lowercase, no leading @
    sender_display_name: str | None = None
    origin_title: str | None = None          # channel or group title
    origin_username: str | None = None       # channel or group @name, no @
    forward_date: int | None = None
    frequently_forwarded: bool = False

    @property
    def sender_identifiable(self) -> bool:
        """True only when there is an actual account behind the forward.

        A display name alone (Telegram's hidden_user) is NOT identifiable: it
        is a string the sender chose, checkable against nothing.
        """
        return bool(self.sender_id or self.sender_username)

    @property
    def attribution(self) -> str:
        if self.platform == PLATFORM_WHATSAPP:
            return ATTR_PLATFORM_BLIND
        if self.origin_type in (ORIGIN_CHANNEL, ORIGIN_CHAT):
            return ATTR_CHANNEL
        if self.sender_identifiable:
            return ATTR_SENDER_KNOWN
        return ATTR_SENDER_HIDDEN


@dataclass
class OperatorLead:
    """A corroborated operator-identity hit. Only ever constructed for handles
    that cleared MIN_SIGHTINGS and MIN_CHANNELS — see the module docstring."""
    handle: str
    sightings: int
    channels: int
    categories: list[str] = field(default_factory=list)


@dataclass
class ForwardFindings:
    origin: ForwardOrigin
    sender_checked: bool = False             # did a lookup actually run?
    leads: list[OperatorLead] = field(default_factory=list)
    lookup_failed: bool = False              # a lookup ran and errored


# ---------------------------------------------------------------------------
# Platform parsers — the two thin ends of the adapter
# ---------------------------------------------------------------------------

def _clean_username(raw) -> str | None:
    """Normalise a Telegram username to the form the operator table is keyed on:
    lowercase, no leading @. Returns None for anything not username-shaped, so a
    junk value can never become a lookup key."""
    if not raw:
        return None
    candidate = str(raw).strip().lstrip("@")
    if not _RE_USERNAME.match(candidate):
        return None
    return candidate.lower()


def parse_telegram_forward(message: dict) -> ForwardOrigin | None:
    """Read Telegram's forward metadata off a Message.

    Returns None when the message is not a forward — callers use that to leave
    ordinary messages on their existing path untouched.

    Reads forward_origin (Bot API 7.0+) first and falls back to the pre-7.0
    fields. The fallback is cheap and means a Bot API downgrade, or a library
    that still populates the old shape, degrades to working rather than to
    silently treating every forward as an ordinary message.
    """
    if not isinstance(message, dict):
        return None

    origin = message.get("forward_origin")
    if isinstance(origin, dict):
        otype = str(origin.get("type") or "").strip()

        if otype == ORIGIN_USER:
            sender = origin.get("sender_user") or {}
            first = str(sender.get("first_name") or "").strip()
            last = str(sender.get("last_name") or "").strip()
            return ForwardOrigin(
                platform=PLATFORM_TELEGRAM,
                origin_type=ORIGIN_USER,
                sender_id=str(sender.get("id")) if sender.get("id") else None,
                sender_username=_clean_username(sender.get("username")),
                sender_display_name=(" ".join(p for p in (first, last) if p) or None),
                forward_date=origin.get("date"),
            )

        if otype == ORIGIN_HIDDEN_USER:
            # sender_user_name is a DISPLAY NAME and nothing else. It is
            # deliberately not put in sender_username: that field is a lookup
            # key, and this string is not one.
            return ForwardOrigin(
                platform=PLATFORM_TELEGRAM,
                origin_type=ORIGIN_HIDDEN_USER,
                sender_display_name=(str(origin.get("sender_user_name") or "").strip() or None),
                forward_date=origin.get("date"),
            )

        if otype == ORIGIN_CHANNEL:
            chat = origin.get("chat") or {}
            return ForwardOrigin(
                platform=PLATFORM_TELEGRAM,
                origin_type=ORIGIN_CHANNEL,
                origin_title=(str(chat.get("title") or "").strip() or None),
                origin_username=_clean_username(chat.get("username")),
                forward_date=origin.get("date"),
            )

        if otype == ORIGIN_CHAT:
            chat = origin.get("sender_chat") or {}
            return ForwardOrigin(
                platform=PLATFORM_TELEGRAM,
                origin_type=ORIGIN_CHAT,
                origin_title=(str(chat.get("title") or "").strip() or None),
                origin_username=_clean_username(chat.get("username")),
                forward_date=origin.get("date"),
            )

        # An origin type Telegram added after this was written. It IS a
        # forward, so say so and analyse it; just claim nothing about who.
        logger.info("Unknown forward_origin type=%r — treating as unattributed", otype)
        return ForwardOrigin(
            platform=PLATFORM_TELEGRAM,
            origin_type=ORIGIN_UNATTRIBUTED,
            forward_date=origin.get("date"),
        )

    # --- Pre-Bot-API-7.0 fallback ---
    legacy_user = message.get("forward_from")
    if isinstance(legacy_user, dict):
        first = str(legacy_user.get("first_name") or "").strip()
        last = str(legacy_user.get("last_name") or "").strip()
        return ForwardOrigin(
            platform=PLATFORM_TELEGRAM,
            origin_type=ORIGIN_USER,
            sender_id=str(legacy_user.get("id")) if legacy_user.get("id") else None,
            sender_username=_clean_username(legacy_user.get("username")),
            sender_display_name=(" ".join(p for p in (first, last) if p) or None),
            forward_date=message.get("forward_date"),
        )

    legacy_chat = message.get("forward_from_chat")
    if isinstance(legacy_chat, dict):
        return ForwardOrigin(
            platform=PLATFORM_TELEGRAM,
            origin_type=ORIGIN_CHANNEL,
            origin_title=(str(legacy_chat.get("title") or "").strip() or None),
            origin_username=_clean_username(legacy_chat.get("username")),
            forward_date=message.get("forward_date"),
        )

    if message.get("forward_sender_name"):
        return ForwardOrigin(
            platform=PLATFORM_TELEGRAM,
            origin_type=ORIGIN_HIDDEN_USER,
            sender_display_name=str(message["forward_sender_name"]).strip() or None,
            forward_date=message.get("forward_date"),
        )

    return None


def _twilio_bool(raw) -> bool:
    """Twilio sends these as the STRING "true", and omits the parameter
    entirely when false — so absence is false, and any parsing must be
    case-insensitive rather than a truthiness test on a non-empty string
    (which would make the literal string "false" read as True)."""
    return str(raw or "").strip().lower() == "true"


def parse_whatsapp_forward(params) -> ForwardOrigin | None:
    """Read WhatsApp forward metadata off Twilio's form-encoded webhook params.

    Returns None when the message is not a forward.

    Both accepted shapes are handled so the transport can change without this
    breaking: Twilio's `Forwarded` / `FrequentlyForwarded`, and Meta Cloud
    API's `context.forwarded` / `context.frequently_forwarded` should the bot
    ever move off Twilio. NEITHER carries an original sender, which is why
    every branch here produces an origin with no sender fields set at all.
    """
    if not params:
        return None

    forwarded = _twilio_bool(params.get("Forwarded"))
    frequently = _twilio_bool(params.get("FrequentlyForwarded"))

    # Cloud API shape, if it is ever the transport.
    context = params.get("context")
    if isinstance(context, dict):
        forwarded = forwarded or bool(context.get("forwarded"))
        frequently = frequently or bool(context.get("frequently_forwarded"))

    # frequently_forwarded implies forwarded, and WhatsApp has been observed
    # setting the second without the first. Treat either as a forward.
    if not (forwarded or frequently):
        return None

    return ForwardOrigin(
        platform=PLATFORM_WHATSAPP,
        origin_type=ORIGIN_UNATTRIBUTED,
        frequently_forwarded=frequently,
    )


# ---------------------------------------------------------------------------
# Sender lookup
# ---------------------------------------------------------------------------

_ddb_resource = None


def _operators_table():
    """Lazy DynamoDB handle. Built on first use so importing this module costs
    nothing and a unit test that injects its own lookup never touches AWS."""
    global _ddb_resource
    if _ddb_resource is None:
        import boto3
        _ddb_resource = boto3.resource("dynamodb")
    return _ddb_resource.Table(OPERATORS_TABLE)


def default_operator_lookup(handle: str) -> dict | None:
    """Fetch one operator-identity row, or None.

    Returns the RAW row. The corroboration filter deliberately lives in
    analyze_forward(), not here, so that a caller cannot get an unfiltered hit
    by calling the lookup directly and skipping the threshold.
    """
    resp = _operators_table().get_item(Key={"handle": handle, "platform": "telegram"})
    return resp.get("Item")


def _to_int(value, default: int = 0) -> int:
    """DynamoDB numbers come back as Decimal."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def analyze_forward(origin: ForwardOrigin, operator_lookup=None) -> ForwardFindings:
    """Provenance analysis for one forward.

    Does NOT analyse the message text — that is each platform's existing
    analyser, and duplicating it here is how two verdicts start disagreeing.

    A sender lookup runs only when origin.sender_identifiable is True, which is
    false for every WhatsApp forward and for Telegram forwards whose sender has
    forward privacy on. A hit is kept only if it clears both corroboration
    thresholds; see the module docstring for why the filter is this strict.
    """
    findings = ForwardFindings(origin=origin)

    if not origin.sender_identifiable:
        return findings

    handle = origin.sender_username
    if not handle:
        # An id with no username. Nothing in the corpus is keyed on numeric
        # ids, so there is genuinely nothing to look up — say nothing rather
        # than reporting a clean check that never happened.
        return findings

    lookup = operator_lookup or default_operator_lookup
    findings.sender_checked = True

    try:
        row = lookup(handle)
    except Exception as exc:
        # A failed lookup must never render as "not found". The renderer keys
        # on this to stay silent about the sender rather than imply a clean
        # result we do not have.
        logger.warning("Operator identity lookup failed handle=%s: %s", handle, exc)
        findings.sender_checked = False
        findings.lookup_failed = True
        return findings

    if not row:
        return findings

    sightings = _to_int(row.get("sightings"))
    channels = row.get("channels") or set()
    categories = row.get("categories") or set()
    try:
        channel_count = len(channels)
    except TypeError:
        channel_count = 0

    if sightings < MIN_SIGHTINGS or channel_count < MIN_CHANNELS:
        logger.info(
            "Operator hit below corroboration threshold handle=%s sightings=%d channels=%d",
            handle, sightings, channel_count,
        )
        return findings

    findings.leads.append(OperatorLead(
        handle=handle,
        sightings=sightings,
        channels=channel_count,
        categories=sorted(str(c) for c in categories),
    ))
    return findings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Per-platform command names, so the one renderer can tell a user what to do
# next in their own bot's vocabulary.
_COMMANDS = {
    PLATFORM_TELEGRAM: {
        "scan_link": "/scan <link>",
        "quickstart": "/quickstart",
    },
    PLATFORM_WHATSAPP: {
        "scan_link": "*SCAN* <link>",
        "quickstart": "*QUICKSTART*",
    },
}

# The sentence that runs after a sender lookup found nothing. It exists because
# "no match" reads as "safe" to a worried person, and on this corpus it is
# nowhere near that: most scam accounts are days old and have never appeared
# anywhere we collect from.
_NO_MATCH = (
    "That account has not come up in the criminal channels we monitor. "
    "That is not a clean bill of health — most scam accounts are new and have "
    "never been seen anywhere."
)


def _md(value) -> str:
    """Escape a value that came from the platform, not from us.

    The Telegram adapter sends with parse_mode="Markdown", and a display name
    or username is attacker-controlled text. Telegram usernames legitimately
    contain underscores, so `@john_doe` alone is enough to leave an unclosed
    italic entity, and Telegram answers an unparseable message with a 400 —
    which drops the ENTIRE reply, verdict included. A scam analysis that fails
    to send because of a character in the scammer's own display name is a
    denial of exactly the answer the user needed, triggerable on demand.
    """
    text = str(value or "")
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def _render_lead(lead: OperatorLead) -> str:
    times = "once" if lead.sightings == 1 else f"{lead.sightings} times"
    line = (
        f"⚠️ *{_md(lead.handle)}* has come up {times}, across {lead.channels} different "
        "criminal channels we monitor."
    )
    if lead.categories:
        line += f" Channels dealing in: {', '.join(_md(c) for c in lead.categories)}."
    line += (
        "\n\nTreat that as a lead, not proof. Handles are collected loosely from "
        "channel chatter, so a match can be a coincidence — but a repeat match "
        "across separate channels is worth taking seriously."
    )
    return line


def render_forward_note(findings: ForwardFindings) -> str:
    """The provenance block, prepended to whatever the platform's own content
    analysis produces.

    One renderer, four attribution states. The honest-limits wording for
    WhatsApp lives here rather than in the WhatsApp adapter on purpose: kept in
    the adapter it is one hurried edit away from being dropped on one platform
    only, and a missing caveat is invisible in review precisely because the
    reply still reads fine.
    """
    origin = findings.origin
    cmds = _COMMANDS.get(origin.platform, _COMMANDS[PLATFORM_TELEGRAM])
    attribution = origin.attribution
    parts: list[str] = ["📨 *Forwarded message*"]

    if attribution == ATTR_SENDER_KNOWN:
        who = _md(origin.sender_display_name) if origin.sender_display_name else "someone"
        handle = f" (@{_md(origin.sender_username)})" if origin.sender_username else ""
        parts.append(f"Telegram says this was originally sent by *{who}*{handle}.")
        if findings.leads:
            parts.append("\n\n".join(_render_lead(l) for l in findings.leads))
        elif findings.sender_checked:
            parts.append(_NO_MATCH)
        # lookup_failed: say nothing about the sender. A check that errored is
        # not a check that passed.

    elif attribution == ATTR_SENDER_HIDDEN:
        name = origin.sender_display_name
        if name:
            parts.append(
                f"The original sender has forward privacy switched on, so Telegram passes "
                f"on the name *{_md(name)}* and no account behind it. Anyone can set that "
                "name, so there is nothing here I can check."
            )
        else:
            parts.append(
                "The original sender is hidden — Telegram passes on no account and no name, "
                "so there is nothing here I can check."
            )

    elif attribution == ATTR_CHANNEL:
        title = _md(origin.origin_title) if origin.origin_title else "a channel"
        handle = f" (@{_md(origin.origin_username)})" if origin.origin_username else ""
        parts.append(
            f"This came from *{title}*{handle}, not from a person. Anything posted to a "
            "channel was written for everyone in it, so a message that seems to know "
            "something about you personally is a strong warning sign."
        )

    else:  # ATTR_PLATFORM_BLIND
        parts.append(
            "WhatsApp tells me this message was forwarded, but *not who originally "
            "sent it*. The WhatsApp Business API does not pass the original sender "
            "on to a business account at all, so — unlike on Telegram — there is no "
            "account for me to check. Everything below is about the message text "
            "alone."
        )

    if origin.frequently_forwarded:
        parts.append(
            "⚠️ WhatsApp also marks this as *frequently forwarded* — it has been passed "
            "along through many hands before reaching you. That is the shape of a chain "
            "message, and it means the person who sent it to you almost certainly did "
            "not write it and cannot vouch for it."
        )

    parts.append(
        f"A screenshot or a forward hides where a link actually goes. If there is a "
        f"link in this, send it to me with {cmds['scan_link']} for a proper check."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Quickstart hints
# ---------------------------------------------------------------------------

def paste_hint(platform: str) -> str:
    """The one-line "you do not need a command" hint.

    Sent as its OWN message immediately before the WhatsApp tappable menu,
    because that menu is a Twilio Content resource: its "Page 1 of 4 - tap a
    command" text lives in Twilio, not in this repo, and cannot be edited from
    here. HELP previously sent only that card, so every word of help copy in
    msg_help() was unreachable -- it is only shown by HELPTEXT, behind a button
    on the last page of the menu.

    Leads with PASTE, not forward. Forwarding is a gesture the user has to know
    AND it needs RelayShield already saved as a contact, or the final "pick
    RelayShield" step has nothing to pick. Pasting needs neither, works
    identically for a text copied out of email or SMS, and is one instruction
    long.
    """
    if platform == PLATFORM_WHATSAPP:
        return (
            "\U0001F4E8 *Before the menu - you do not need a command.*\n\n"
            "*Copy any suspicious message and paste it here.* That is the whole "
            "thing: copy, paste, send. It works for a text, an email, a link, or "
            "a message from someone already in your contacts.\n\n"
            "Forwarding works too if you know how, and so does a screenshot. "
            "Pasting is the one that always works.\n\n"
            "_WhatsApp does not tell me who originally sent a forwarded message, "
            "so I read the text but can never check the sender._"
        )
    return (
        "\U0001F4E8 *You do not need a command.*\n\n"
        "*Copy any suspicious message and paste it here*, or forward it to "
        "@relayshield\\_bot. Works for a text, an email, a link, or a message "
        "from someone already in your contacts."
    )


def quickstart_text(platform: str) -> str:
    """The Quickstart card.

    Deliberately about ACTIONS, not commands. The existing help surfaces on
    both bots already list commands well; what neither said is that you do not
    need a command at all — you can forward the thing, or send the screenshot,
    and it gets analysed. That is the fastest useful action available and it
    was undiscoverable, which also made the forward handler undiscoverable.

    Kept to three actions on purpose. A fourth turns a card someone reads in a
    panic into a list they skim.
    """
    if platform == PLATFORM_WHATSAPP:
        return (
            "🚀 *Quick start — three things you can do right now*\n\n"
            "*1. Forward me anything that looks off.*\n"
            "A text, a link, a WhatsApp message — including one from someone "
            "already in your contacts. Press and hold the message, tap *Forward*, "
            "and pick RelayShield. No command needed. *A message from a name you "
            "know is exactly the case worth forwarding*: a hijacked account still "
            "shows up as your friend.\n"
            "I read it for impersonation, urgency tactics and credential lures, "
            "and I check every link in it.\n"
            "_WhatsApp does not tell me who originally sent a forwarded message, "
            "so I can analyse the text but never the sender._\n\n"
            "*2. Paste a screenshot of a suspicious text.*\n"
            "Send the picture with the caption *MSGSCAN* and I will read the text "
            "out of it. Best for an SMS you cannot forward into WhatsApp. A "
            "screenshot hides where its buttons really link, so send the link "
            "itself too if you can.\n\n"
            "*3. Check a link before you click it.*\n"
            "*SCAN* <link> — checked against our own criminal-source corpus, "
            "Google Safe Browsing and VirusTotal.\n\n"
            "Reply *HELP* for the full command list."
        )

    return (
        "🚀 *Quick start — three things you can do right now*\n\n"
        "*1. Forward me anything that looks off.*\n"
        "A text, a link, a Telegram message — including one from someone already "
        "in your contacts. Tap the message, choose *Forward*, and search for "
        "*@relayshield\\_bot*. No command needed. *A message from a name you know "
        "is exactly the case worth forwarding*: a hijacked account still shows up "
        "as your friend.\n"
        "I read it for impersonation, urgency tactics and credential lures, I "
        "check every link in it, and — because Telegram passes on who sent a "
        "forward — I check that account too, unless they have forward privacy "
        "switched on.\n\n"
        "*2. Paste a screenshot of a suspicious text.*\n"
        "Send the picture on its own, no caption needed. Best for an SMS you "
        "cannot forward into Telegram. A screenshot hides where its buttons "
        "really link, so send the link itself too if you can.\n\n"
        "*3. Check a link before you click it.*\n"
        "`/scan <link>` — checked against our own criminal-source corpus, "
        "Google Safe Browsing and VirusTotal.\n\n"
        "Type /help for the full command list."
    )
