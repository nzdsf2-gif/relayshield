"""Is this actually a way to reach a human who wants to hear from us?

Shared by tools/prospect_bots_wide.py (which extracts contacts) and
tools/generate_outreach.py (which is the last thing standing between a bad
extraction and a sent message). Both import it, so a rule fixed once is fixed
in both places.

WHY THIS EXISTS, and every example below is from a real sweep on 2026-09-03:

    root@203.0.113.4          an RFC 5737 documentation IP out of a README
    trial@telegram.bot        a placeholder in an example config
    k7m2q9x1a3@yourdomain.com a fill-in-your-own-domain line
    esbuild@0.24.0            a package version, which is email-shaped to a regex
    you@gmail.com             a real domain and a local part meaning "put yours here"
    john@acme.com             the textbook example domain
    https://t.me/d2_schedule_bot        the bot itself, not a contact channel
    https://youtu.be/M-IRuWRrVUg        a demo video
    https://github.com/owner/repo       the repo, which is the GitHub channel

The first three are addresses nobody reads, and mailing them is how a sending
domain gets a spam reputation. The last three are not contact channels at all,
and counting them as "reachable" inflates the only number that decides whether
this outreach channel is worth continuing.

A false negative here costs one prospect. A false positive costs the domain.
"""

import re

__all__ = ["usable_email", "usable_site", "reject_reason"]

# Local parts and domains that appear in READMEs as examples, never as people.
_PLACEHOLDER_TOKENS = (
    "example", "sample", "placeholder", "yourdomain", "your-domain", "youremail",
    "your-email", "changeme", "change-me", "dummy", "foobar", "yourname",
    "your-name", "test@", "trial@", "demo@", "noreply", "no-reply", "donotreply",
)
_PLACEHOLDER_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "email.com", "mail.example", "test.com", "telegram.bot", "bot.local",
    "localhost", "sentry.io",
    # acme.com is the textbook example domain in half the world's READMEs, and
    # the 2026-09-03 sweep duly offered john@acme.com as a contact.
    "acme.com", "acme.org", "company.com", "mysite.com", "site.com",
    "gmail.example", "abc.com",
}

# Local parts that are a role or a stand-in rather than a person. "you@gmail.com"
# came back as a top-25 contact on the second sweep: a real domain, so every
# domain-based rule passed it, and a local part that means "put yours here".
_PLACEHOLDER_LOCALS = {
    "you", "me", "your", "youremail", "yourname", "john", "jane", "johndoe",
    "janedoe", "someone", "somebody", "username", "user", "name", "firstname",
    "lastname", "foo", "bar", "baz", "abc", "xyz",
}
# An email whose domain is an IP literal is a config example every time.
_IP_DOMAIN = re.compile(r"@\d{1,3}(?:\.\d{1,3}){3}$")
# Matched inside README prose, so it can swallow a filename or a badge URL.
_LOOKS_LIKE_FILE = re.compile(r"\.(png|jpg|jpeg|svg|gif|webp|md|txt|json|yml|yaml)$", re.I)

# Hosts that are a link to the thing, not a way to reach its author.
_NOT_A_CONTACT_HOST = (
    "t.me", "telegram.me", "telegram.dog", "youtube.com", "youtu.be",
    "twitter.com", "x.com", "discord.gg", "discord.com", "vercel.app",
    "onrender.com", "herokuapp.com", "railway.app", "ngrok.io",
)


def reject_reason(value, kind):
    """Why this contact is unusable, or "" when it is fine. kind: email|site."""
    v = (value or "").strip()
    if not v:
        return "empty"
    low = v.lower()

    if kind == "email":
        if "@" not in low or _LOOKS_LIKE_FILE.search(low):
            return "not an address"
        if _IP_DOMAIN.search(low):
            return "IP-literal domain, so a documentation example"
        local, domain = low.rsplit("@", 1)[0], low.rsplit("@", 1)[-1]
        if domain in _PLACEHOLDER_DOMAINS:
            return f"placeholder domain {domain}"
        if local in _PLACEHOLDER_LOCALS:
            return f"placeholder local part {local!r}"
        # A version string swallowed out of a README reads as an address to any
        # regex: "esbuild@0.24.0" was offered as a contact on the second sweep.
        # A real TLD is alphabetic, so this is exact rather than a heuristic.
        tld = domain.rsplit(".", 1)[-1]
        if not tld.isalpha() or len(tld) < 2:
            return f"'{domain}' has no alphabetic TLD, so it is a version string or a path"
        for token in _PLACEHOLDER_TOKENS:
            if token in low:
                return f"placeholder token {token!r}"
        if "." not in domain:
            return "domain has no dot"
        return ""

    if kind == "site":
        if not low.startswith(("http://", "https://")):
            return "not a URL"
        host = low.split("//", 1)[-1].split("/", 1)[0].split("@")[-1]
        host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        for bad in _NOT_A_CONTACT_HOST:
            if host == bad or host.endswith("." + bad):
                return f"{bad} is the product or a demo, not a contact channel"
        if host.startswith("github.com"):
            # Not a rejection of the prospect: it just belongs in the github
            # field, where it is ranked last, rather than counting as a website.
            return "github.com is the GitHub channel, not a website"
        if any(t in host for t in ("example", "yourdomain", "localhost")):
            return "placeholder host"
        if "." not in host:
            return "host has no dot"
        return ""

    raise ValueError(f"unknown kind {kind!r}")


def usable_email(value):
    return not reject_reason(value, "email")


def usable_site(value):
    return not reject_reason(value, "site")
