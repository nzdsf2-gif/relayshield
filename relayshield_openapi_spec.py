"""OpenAPI 3.1 specification for the RelayShield public API.

Why this file exists
--------------------
Until 2026-08-04 the spec served at /openapi.json was synthesised from
PAYG_DESCRIPTIONS: every endpoint got the same untyped request body
(`additionalProperties: true`) and the same untyped `data` object, with the
real field names living only in prose on the /developers page. That is
exactly the gap Zapier's partner review flagged on 2026-08-03 -- endpoints
and prices were published, parameters, attributes and error handling were
not.

Two further defects came with the old generator, both fixed here:

1. It emitted a `/v1/metered/<name>` twin for EVERY PAYG path. Seven of those
   names have no metered route at all (nft-security, scan-file, scan-url,
   scan-wallet, token-security, wallet-risk, wallet-screen-batch -- they are
   subscription routes under bare `/v1/`, never `/v1/metered/`). A client
   generated from that spec would call a documented endpoint and get
   `404 unknown metered endpoint`.
2. Six live metered endpoints were missing entirely (asset-intel,
   threat-actor, ioc-pivot, brand-monitor, card-exposure, crypto-intel,
   bulk-ioc, secret-scan-text), as were both free account endpoints.

Every schema below was read off the handler in relayshield_api.py, not
inferred from the marketing copy. When a handler's request or response
changes, change it here in the same commit -- this file is the contract we
hand to partner reviewers, so a spec that drifts is worse than no spec.

Kept as its own module rather than inlined into relayshield_api.py because it
is pure data with no AWS dependencies, which makes it importable by the docs
build, testable on its own, and diffable without scrolling a 10k-line Lambda.
It is a local import of relayshield_api.py, so it MUST be included in that
function's deployment zip (see .claude/skills/relayshield-deploy).
"""

SPEC_VERSION = "1.1.0"

# Severity vocabulary used by every scoring endpoint. Documented once and
# referenced, so a caller can switch on it without reading 20 descriptions.
_SEVERITY = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def _str(desc, **kw):
    s = {"type": "string", "description": desc}
    s.update(kw)
    return s


def _int(desc, **kw):
    s = {"type": "integer", "description": desc}
    s.update(kw)
    return s


def _num(desc, **kw):
    s = {"type": "number", "description": desc}
    s.update(kw)
    return s


def _bool(desc):
    return {"type": "boolean", "description": desc}


def _arr(desc, items):
    return {"type": "array", "description": desc, "items": items}


def _obj(desc, props, required=None):
    s = {"type": "object", "description": desc, "properties": props}
    if required:
        s["required"] = required
    return s


def _sev(desc):
    return {"type": "string", "enum": _SEVERITY, "description": desc}


def _nullable_sev(desc):
    return {"type": ["string", "null"], "enum": _SEVERITY + [None], "description": desc}


def _ts(desc="ISO 8601 UTC timestamp of when this check ran."):
    return {"type": "string", "format": "date-time", "description": desc}


# ---------------------------------------------------------------------------
# Shared response fragments
# ---------------------------------------------------------------------------

_CHECKED_AT = _ts()

_LOOKALIKE = _obj(
    "One active lookalike domain, enriched with intent signals.",
    {
        "domain": _str("The lookalike domain that resolves."),
        "gsb_flagged": {
            "type": ["boolean", "null"],
            "description": "True if Google Safe Browsing lists it. null when enrichment timed out.",
        },
        "registration_age_days": {
            "type": ["integer", "null"],
            "description": "Days since registration via RDAP. Under 30 is a strong phishing signal. null when unavailable.",
        },
        "cert_count": {
            "type": ["integer", "null"],
            "description": "Certificates seen in Certificate Transparency logs.",
        },
        "cert_recent": {
            "type": ["boolean", "null"],
            "description": "True if a certificate was issued recently, indicating the lookalike is being stood up now.",
        },
        "latest_cert_issued": {
            "type": ["string", "null"],
            "description": "Issue date of the most recent certificate.",
        },
    },
)

_VENDOR_RESULT = _obj(
    "Per-vendor risk assessment.",
    {
        "domain": _str("The vendor domain assessed."),
        "breach_count": _int("Number of known breach events affecting this domain."),
        "breached_accounts": _int("Accounts from this domain found across those breaches."),
        "breach_names": _arr("Breach names, capped at 10.", _str("Breach name.")),
        "infostealer_found": _bool("True if credentials for this domain appear in infostealer logs."),
        "infostealer_count": _int("Infostealer log entries for this domain."),
        "infostealer_dates": _arr(
            "Compromise dates, present only when infostealer_found is true.",
            _str("Date the device was compromised."),
        ),
        "risk_level": {
            "type": "string",
            "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAN"],
            "description": "Overall vendor risk rating.",
        },
        "risk_factors": _arr("Plain-English reasons behind risk_level.", _str("One contributing factor.")),
        "recommendation": _str("Recommended action for this vendor."),
        "dark_web_score": _int("Composite exposure score 0-100. Results are sorted by this, descending.", minimum=0, maximum=100),
    },
)

_STOLEN_SESSION = _obj(
    "One stolen session or credential record from the criminal corpus.",
    {
        "domain": _str("Service the stolen session belongs to."),
        "session_type": _str("`cookie` for a session cookie, `credential` for a username/password or token pair."),
        "cookie_name": _str("Cookie or credential name. Never the value."),
        "severity": _sev("Severity derived from the service category."),
        "service_category": _str("Category of the affected service, e.g. cloud_console, identity_provider, productivity."),
        "channel_source": _str("Criminal channel or archive the record was collected from."),
        "ingested_at": _str("When RelayShield ingested the record."),
    },
)

_NHI_FINDING = _obj(
    "One non-human identity credential found in the stealer log corpus.",
    {
        "domain": _str("Domain the finding was matched against."),
        "type": _str("Credential type, e.g. aws_access_key, github_pat, stripe_secret_key, private_key."),
        "description": _str("What the credential grants and why it matters."),
        "severity": _sev("Severity of this credential type."),
        "preview": _str("Redacted context. Never the full secret value."),
        "source": _str("Channel or archive the record came from."),
        "ingested_at": _str("When RelayShield ingested the record."),
    },
)

_IOC_SUMMARY = _obj(
    "One indicator of compromise.",
    {
        "ioc_value": _str("The indicator itself."),
        "ioc_type": _str("Indicator type: ip, domain, url, hash, email, wallet, image_text."),
        "source": _str("Feed or criminal channel it was observed in."),
        "malware": _str("Malware family it was observed alongside, lowercase. Empty when unattributed."),
        "last_seen": _str("Most recent sighting timestamp."),
    },
)


# ---------------------------------------------------------------------------
# Endpoint definitions
#
# price_cents mirrors METERED_CREDIT_COSTS in relayshield_api.py. Keep the two
# in step -- this value is published, so a mismatch is a pricing claim we do
# not honour.
# ---------------------------------------------------------------------------

ENDPOINTS = [
    # ---------------- Identity exposure ----------------
    {
        "path": "/v1/metered/breach",
        "price_cents": 10,
        "tag": "Identity exposure",
        "summary": "Check an email address against known data breaches",
        "description": (
            "Looks the address up across 13B+ compromised accounts and returns every breach it "
            "appears in, with the date and the classes of data exposed. Call it before trusting a "
            "new user identity or granting elevated access."
        ),
        "request": {
            "props": {
                "email": _str(
                    "Email address to check. Case-insensitive; whitespace is trimmed. Must contain '@'.",
                    format="email",
                    examples=["user@example.com"],
                ),
            },
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "email": _str("The normalised address that was checked."),
                "record_type": _str("Always `credential_exposure`. Lets a SIEM route every identity finding on one field."),
                "breach_count": _int("Number of breaches the address appears in. 0 means no known exposure."),
                "breaches": _arr(
                    "One entry per breach, unordered.",
                    _obj("A single breach.", {
                        "name": _str("Breach identifier, e.g. `LinkedIn`."),
                        "domain": _str("Domain of the breached service. May be empty."),
                        "breach_date": _str("Date of the breach, YYYY-MM-DD."),
                        "data_classes": _arr("Data types exposed.", _str("e.g. `Email addresses`, `Passwords`.")),
                        "is_verified": _bool("Whether the breach has been verified as genuine."),
                    }),
                ),
            },
            "example": {
                "email": "user@example.com",
                "record_type": "credential_exposure",
                "breach_count": 2,
                "breaches": [
                    {
                        "name": "LinkedIn",
                        "domain": "linkedin.com",
                        "breach_date": "2021-06-22",
                        "data_classes": ["Email addresses", "Passwords"],
                        "is_verified": True,
                    },
                    {
                        "name": "Dropbox",
                        "domain": "dropbox.com",
                        "breach_date": "2012-07-01",
                        "data_classes": ["Email addresses", "Passwords"],
                        "is_verified": True,
                    },
                ],
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "429": "Upstream breach database rate limit reached. Retry in a few seconds.",
            "502": "Upstream breach database unavailable or returned an unexpected status.",
        },
    },
    {
        "path": "/v1/metered/infostealer",
        "price_cents": 50,
        "tag": "Identity exposure",
        "summary": "Check an email address against infostealer malware logs",
        "description": (
            "A single infected device exposes every saved password at once: banking, card autofill, "
            "email, SaaS, and live session cookies that bypass 2FA. This returns the infection "
            "records tied to the address, including when the device was compromised and how many "
            "corporate and personal services were on it."
        ),
        "request": {
            "props": {"email": _str("Email address to check.", format="email")},
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "record_type": _str("Always `credential_exposure`."),
                "email": _str("The normalised address that was checked."),
                "found": _bool("True when at least one infection record exists."),
                "stealer_count": _int("Number of distinct infected devices."),
                "stealers": _arr(
                    "One entry per infected device.",
                    _obj("A single infostealer infection.", {
                        "date_compromised": _str("When the device was infected."),
                        "computer_name": _str("Hostname recorded by the malware."),
                        "operating_system": _str("OS string recorded by the malware."),
                        "malware_path": _str("Filesystem path the stealer ran from."),
                        "total_corporate_services": _int("Corporate credentials found on the device."),
                        "total_user_services": _int("Personal credentials found on the device."),
                    }),
                ),
            },
            "example": {
                "record_type": "credential_exposure",
                "email": "user@example.com",
                "found": True,
                "stealer_count": 1,
                "stealers": [{
                    "date_compromised": "2026-03-14",
                    "computer_name": "DESKTOP-4K1P8Q",
                    "operating_system": "Windows 10 Pro",
                    "malware_path": "C:\\Users\\user\\AppData\\Local\\Temp\\setup.exe",
                    "total_corporate_services": 7,
                    "total_user_services": 42,
                }],
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "502": "Upstream infostealer corpus unavailable.",
        },
    },
    {
        "path": "/v1/metered/sim-swap",
        "price_cents": 25,
        "tag": "Identity exposure",
        "summary": "Detect a recent SIM swap or carrier port",
        "description": (
            "Queries live carrier data for the number. A recent swap is a strong signal of an "
            "account-takeover attempt against SMS-based 2FA, so call this before trusting an SMS "
            "OTP from a number you have not seen before."
        ),
        "request": {
            "props": {
                "phone": _str(
                    "Phone number in E.164 format. Must start with '+'. Rejected without it -- "
                    "national formats are ambiguous across carriers.",
                    examples=["+14155551234"],
                ),
            },
            "required": ["phone"],
            "example": {"phone": "+14155551234"},
        },
        "response": {
            "props": {
                "phone": _str("The number that was checked, echoed as supplied."),
                "swapped": _bool("True when the carrier reports a SIM swap or port in the lookback period."),
                "swap_timestamp": _str("When the swap occurred. Empty string when no swap is reported."),
                "carrier": _str("Current carrier name. Empty when the carrier does not disclose it."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "phone": "+14155551234",
                "swapped": True,
                "swap_timestamp": "2026-08-03T09:12:44Z",
                "carrier": "T-Mobile USA",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "`phone` is missing or not in E.164 format (must start with '+').",
            "502": "Carrier lookup provider unavailable or returned an unexpected status.",
        },
    },
    {
        "path": "/v1/metered/session-risk",
        "price_cents": 30,
        "tag": "Identity exposure",
        "summary": "Detect stolen session cookies before they are used",
        "description": (
            "Searches criminal stealer-log archives for live session cookies belonging to the "
            "address. This is the AiTM case that password rotation does not fix: a stolen cookie "
            "bypasses 2FA and stays valid until the session is explicitly invalidated."
        ),
        "request": {
            "props": {"email": _str("Email address to check.", format="email")},
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "email": _str("The normalised address that was checked."),
                "record_type": _str("`credential_exposure`. Present on the not-found response."),
                "found": _bool("True when at least one stolen session exists."),
                "session_count": _int("Number of stolen session records."),
                "highest_severity": _nullable_sev("Highest severity across all sessions. null when none found."),
                "sessions": _arr("Sessions, sorted most severe first.", _STOLEN_SESSION),
                "action_required": _str("Remediation text. Present only when found is true."),
            },
            "example": {
                "email": "user@example.com",
                "found": True,
                "session_count": 2,
                "highest_severity": "CRITICAL",
                "sessions": [{
                    "domain": "console.aws.amazon.com",
                    "session_type": "cookie",
                    "cookie_name": "aws-userInfo",
                    "severity": "CRITICAL",
                    "service_category": "cloud_console",
                    "channel_source": "@redline_logs_cloud",
                    "ingested_at": "2026-07-29T04:11:56Z",
                }],
                "action_required": "IMMEDIATE: Log out of all listed services from a clean device and revoke active sessions. Changing your password alone is insufficient - stolen session cookies bypass 2FA and remain valid until explicitly invalidated.",
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "500": "Session corpus query failed.",
        },
    },
    {
        "path": "/v1/metered/oauth-watchlist",
        "price_cents": 30,
        "tag": "Identity exposure",
        "summary": "Find exposed OAuth tokens and SaaS credentials",
        "description": (
            "Combines breach history against a watchlist of OAuth-capable apps with a live search "
            "of the stealer-log corpus. Returns matched apps with direct revoke links, plus any "
            "stolen credentials, category-scored: cloud consoles and code repositories CRITICAL, "
            "identity providers and payment processors HIGH, productivity SaaS MEDIUM."
        ),
        "request": {
            "props": {"email": _str("Email address to check.", format="email")},
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "email": _str("The normalised address that was checked."),
                "matched_count": _int("OAuth-capable apps matched via breach history."),
                "matched_apps": _arr(
                    "Apps matched from breach history.",
                    _obj("A matched OAuth app.", {
                        "app": _str("App or service name."),
                        "source": _str("Always `breach_history` for this list."),
                        "breach_date": _str("Date of the breach, YYYY-MM-DD."),
                        "data_classes": _arr("Data types exposed.", _str("Data class.")),
                        "revoke_url": _str("Direct link to the app's revoke-access page."),
                    }),
                ),
                "stolen_token_count": _int("Credential records found in the stealer corpus."),
                "stolen_tokens": _arr("Stolen credentials, sorted most severe first.", _STOLEN_SESSION),
                "highest_severity": {
                    "type": "string",
                    "enum": _SEVERITY + ["NONE"],
                    "description": "Highest severity across both signals. `NONE` when nothing was found.",
                },
                "recommendation": _str("Remediation text derived from the most severe signal present."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "email": "user@example.com",
                "matched_count": 1,
                "matched_apps": [{
                    "app": "Dropbox",
                    "source": "breach_history",
                    "breach_date": "2012-07-01",
                    "data_classes": ["Email addresses", "Passwords"],
                    "revoke_url": "https://www.dropbox.com/account/connected_apps",
                }],
                "stolen_token_count": 0,
                "stolen_tokens": [],
                "highest_severity": "HIGH",
                "recommendation": "Revoke OAuth access for matched apps immediately using the revoke_url for each. Also audit all connected apps at myaccount.google.com/permissions and myapps.microsoft.com.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "429": "Upstream breach database rate limit reached.",
            "502": "Upstream breach database unavailable.",
        },
        "notes": (
            "The stealer-corpus half of this check is non-fatal: if that query fails, breach-history "
            "results are still returned rather than failing the whole call."
        ),
    },
    {
        "path": "/v1/metered/identity-graph",
        "price_cents": 35,
        "tag": "Identity exposure",
        "summary": "Correlate an email to phones and domains seen alongside it",
        "description": (
            "Pivot from one compromised identifier to every other identifier that appeared next to "
            "it in criminal channel dumps. Correlated values are stored encrypted and decrypted per "
            "request."
        ),
        "request": {
            "props": {"email": _str("Anchor email address.", format="email")},
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "email": _str("The anchor address."),
                "found": _bool("True when at least one correlated identifier exists."),
                "correlated_identifiers": _int("Total correlated phones plus domains."),
                "correlated_phones": _arr("Phone numbers seen alongside this address.", _str("Phone number.")),
                "correlated_domains": _arr("Domains seen alongside this address.", _str("Domain.")),
                "sources": _arr("Dumps or channels the correlations came from.", _str("Source name.")),
                "recommendation": _str("Remediation text. Present only when found is true."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "email": "user@example.com",
                "found": True,
                "correlated_identifiers": 2,
                "correlated_phones": ["+14155551234"],
                "correlated_domains": ["example-corp.com"],
                "sources": ["@combolist_daily"],
                "recommendation": "All listed identifiers were found alongside this email in criminal channel dumps. Treat each as potentially compromised - change passwords and check accounts linked to any of the correlated phone numbers or domains.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "500": "Identity graph query failed.",
        },
    },
    {
        "path": "/v1/metered/card-exposure",
        "price_cents": 30,
        "tag": "Identity exposure",
        "summary": "Check a card against the stolen-card corpus",
        "description": (
            "Pass a client-computed SHA-256 of the digit-only card number, a 6-8 digit BIN, or "
            "both. RelayShield never accepts or stores a raw card number, and a rejected value is "
            "never logged."
        ),
        "request": {
            "props": {
                "pan_hash": _str(
                    "64-character lowercase SHA-256 hex digest of the digit-only card number "
                    "(no spaces, no dashes). Computed client-side.",
                    pattern="^[a-f0-9]{64}$",
                ),
                "bin": _str("6 to 8 digit Bank Identification Number.", pattern="^[0-9]{6,8}$"),
            },
            "any_of": ["pan_hash", "bin"],
            "example": {"bin": "424242"},
        },
        "response": {
            "props": {
                "card_exposed": _bool("True when the exact card hash is in the corpus. Present only when pan_hash was supplied."),
                "last4": _str("Last 4 digits of the exposed card. Present only on a pan_hash hit."),
                "first_seen": _str("When the card was first seen. Present only on a pan_hash hit."),
                "bin_exposed_card_count": _int("Exposed cards sharing this BIN. Present only when bin was supplied."),
                "bin_last_seen": {
                    "type": ["string", "null"],
                    "description": "Most recent sighting for this BIN. null when none.",
                },
            },
            "example": {"bin_exposed_card_count": 1183, "bin_last_seen": "2026-08-01T22:14:03Z"},
        },
        "errors": {
            "400": "Neither `pan_hash` nor `bin` supplied, `pan_hash` is not a 64-char SHA-256 hex digest, or `bin` is not 6-8 digits.",
            "500": "Stolen-card corpus lookup failed.",
        },
    },

    # ---------------- Domain and infrastructure ----------------
    {
        "path": "/v1/metered/domain",
        "price_cents": 30,
        "tag": "Domain and infrastructure",
        "summary": "Scan a domain for active phishing lookalikes",
        "description": (
            "Generates typosquat, homoglyph and phishing-prefix permutations, keeps the ones that "
            "actually resolve, then enriches each with Safe Browsing status, registration age and "
            "Certificate Transparency activity. A lookalike registered in the last 30 days with a "
            "fresh certificate is being stood up right now."
        ),
        "request": {
            "props": {
                "domain": _str(
                    "Domain to protect. A scheme or leading `www.` is stripped for you.",
                    examples=["acme.com"],
                ),
            },
            "required": ["domain"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domain": _str("The normalised domain that was scanned."),
                "lookalikes_found": _int("Permutations that resolve."),
                "lookalikes": _arr("One entry per active lookalike.", _LOOKALIKE),
                "candidates_checked": _int("Permutations generated and tested."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domain": "acme.com",
                "lookalikes_found": 2,
                "lookalikes": [{
                    "domain": "acnne.com",
                    "gsb_flagged": True,
                    "registration_age_days": 11,
                    "cert_count": 2,
                    "cert_recent": True,
                    "latest_cert_issued": "2026-07-29",
                }],
                "candidates_checked": 214,
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {"400": "`domain` is missing or contains no '.'."},
        "notes": (
            "Enrichment is bounded to 15 seconds. A lookalike whose enrichment does not finish in "
            "time is still returned, with its enrichment fields set to null rather than omitted -- "
            "null means unknown here, never 'clean'."
        ),
    },
    {
        "path": "/v1/metered/cert-expiry",
        "price_cents": 5,
        "tag": "Domain and infrastructure",
        "summary": "Check TLS certificate expiry from CT logs",
        "description": (
            "Reads Certificate Transparency logs and reports days remaining on the certificate "
            "most likely deployed right now (the unexpired entry with the latest not_before). "
            "Relevant as CA/Browser Forum rules shrink standard certificate lifetimes toward 47 "
            "days by 2029."
        ),
        "request": {
            "props": {"domain": _str("Domain to check. A leading `www.` is stripped.", examples=["acme.com"])},
            "required": ["domain"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domain": _str("The normalised domain."),
                "cert_found": _bool("True when CT logs hold any certificate for the domain."),
                "expires_at": {"type": ["string", "null"], "description": "Expiry timestamp. null when no live certificate."},
                "days_remaining": {"type": ["integer", "null"], "description": "Days until expiry. null when no live certificate."},
                "risk_level": {
                    "type": ["string", "null"],
                    "enum": _SEVERITY + [None],
                    "description": "CRITICAL at 7 days or fewer, HIGH at 14, MEDIUM at 30, otherwise LOW. null when no certificates exist at all.",
                },
                "issued_at": {"type": ["string", "null"], "description": "Issue timestamp of the live certificate."},
                "recommendation": _str("Plain-English action."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domain": "acme.com",
                "cert_found": True,
                "expires_at": "2026-08-19T23:59:59+00:00",
                "days_remaining": 15,
                "risk_level": "MEDIUM",
                "issued_at": "2026-05-21T00:00:00+00:00",
                "recommendation": "Certificate renews in 15 days - no action needed yet, but confirm your renewal automation is configured.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "`domain` is missing or contains no '.'.",
            "502": "Certificate Transparency log lookup failed.",
        },
        "notes": (
            "`cert_found: true` with `days_remaining: null` and `risk_level: CRITICAL` means "
            "historical certificates exist but none are currently valid -- distinct from "
            "`cert_found: false`, which means the domain has never appeared in CT logs."
        ),
    },
    {
        "path": "/v1/metered/ip-intel",
        "price_cents": 10,
        "tag": "Domain and infrastructure",
        "summary": "Passive DNS and reputation for a domain or IP",
        "description": (
            "Pass a domain for its historical IP resolutions, or an IP for reverse resolutions, AS "
            "owner and country. RelayShield's own IOC corpus is consulted first; a hit there is a "
            "stronger signal than a third-party vote count and short-circuits the external lookup."
        ),
        "request": {
            "props": {
                "domain": _str("Domain to look up. A leading `www.` is stripped."),
                "ip": _str("IP address to look up. Takes precedence when both are supplied."),
            },
            "any_of": ["domain", "ip"],
            "example": {"domain": "example.com"},
        },
        "response": {
            "props": {
                "queried": _str("The value that was looked up."),
                "query_type": {"type": "string", "enum": ["domain", "ip"], "description": "Which lookup ran."},
                "found": _bool("True when the value is known to any source."),
                "reputation": {"type": ["integer", "null"], "description": "Reputation score. null on a RelayShield-corpus hit or when not found."},
                "malicious_votes": {"type": ["integer", "null"], "description": "Engines flagging it malicious. On a corpus hit this is the corpus hit count."},
                "suspicious_votes": {"type": ["integer", "null"], "description": "Engines flagging it suspicious."},
                "source": _str("Present and set to `relayshield_ioc_corpus` when the answer came from RelayShield's own corpus."),
                "resolutions": _arr(
                    "Up to 10 historical resolutions, newest first.",
                    _obj("One resolution record.", {
                        "date": {"type": ["string", "null"], "description": "When the resolution was observed."},
                        "hostname": _str("Present when query_type is `ip`."),
                        "ip_address": _str("Present when query_type is `domain`."),
                    }),
                ),
                "as_owner": _str("Autonomous system owner. Present only when query_type is `ip`."),
                "country": _str("Two-letter country code. Present only when query_type is `ip`."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "queried": "93.184.216.34",
                "query_type": "ip",
                "found": True,
                "reputation": -4,
                "malicious_votes": 2,
                "suspicious_votes": 1,
                "resolutions": [{"date": "2026-06-02T00:00:00+00:00", "hostname": "example.com"}],
                "as_owner": "EDGECAST",
                "country": "US",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "Neither `domain` nor `ip` supplied.",
            "502": "Upstream reputation provider unavailable.",
        },
        "notes": "Responses are cached, so repeat lookups of the same value within the cache window are served from cache.",
    },

    # ---------------- Secrets and non-human identity ----------------
    {
        "path": "/v1/metered/secret-scan",
        "price_cents": 35,
        "tag": "Secrets and non-human identity",
        "summary": "Find published secrets across six public artifact sources",
        "description": (
            "Scans GitHub repositories plus npm, PyPI, Docker Hub, Hugging Face and Postman "
            "public workspaces and collections for "
            "secrets already published against your domain. Secrets ship inside released packages "
            "and images constantly, and repo-only scanners never see them. Every hit is verified "
            "against the matching credential pattern before it is reported, so a docs example or a "
            "placeholder is not billed to you as a CRITICAL."
        ),
        "request": {
            "props": {
                "domain": _str("Your own domain."),
                "vendor_domains": _arr("Additional supply-chain domains.", _str("Domain.")),
                "include_artifact_sources": _bool(
                    "When false, only GitHub is scanned. Defaults to true. Set false for a faster, "
                    "repo-only scan."
                ),
            },
            "any_of": ["domain", "vendor_domains"],
            "example": {"domain": "acme.com", "vendor_domains": ["vendor-one.com"]},
        },
        "response": {
            "props": {
                "domains_checked": _int("Domains actually scanned. Capped at 5 after deduplication."),
                "found": _bool("True when at least one verified secret was found."),
                "findings": _arr(
                    "Findings, sorted most severe first.",
                    _obj("One verified secret.", {
                        "source": {"type": "string", "enum": ["github", "npm", "pypi", "dockerhub", "huggingface"], "description": "Artifact source it was found in."},
                        "type": _str("Credential type, e.g. aws_access_key, github_pat, stripe_secret_key."),
                        "description": _str("What the credential grants."),
                        "severity": _sev("Severity of the credential type."),
                        "repo": _str("Repository or package the secret is in."),
                        "file": _str("Path within the artifact."),
                        "url": _str("Direct link to the match."),
                        "preview": _str("Redacted context. Never the secret value."),
                        "domain": _str("Which supplied domain this finding belongs to."),
                        "surfaced_by": _str("Present only when the query that surfaced the hit differs from the credential type finally classified."),
                    }),
                ),
                "highest_severity": _nullable_sev("Highest severity across findings. null when none."),
                "coverage": _arr(
                    "Per-domain scan coverage, reported so a caller can tell a fresh all-clear from a stale one.",
                    _obj("Coverage for one domain.", {
                        "domain": _str("Domain."),
                        "cached": _bool("True when served from the 24-hour cache rather than freshly scanned."),
                        "sources": _arr("Sources that actually ran for this domain.", _str("Source name.")),
                    }),
                ),
                "recommendation": _str("Remediation text."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domains_checked": 1,
                "found": True,
                "highest_severity": "CRITICAL",
                "findings": [{
                    "source": "pypi",
                    "type": "aws_access_key",
                    "description": "AWS IAM access key ID with matching secret",
                    "severity": "CRITICAL",
                    "repo": "acme-sdk",
                    "file": "acme_sdk/config.py",
                    "url": "https://pypi.org/project/acme-sdk/",
                    "preview": "Match in acme_sdk/config.py",
                    "domain": "acme.com",
                }],
                "coverage": [{"domain": "acme.com", "cached": False, "sources": ["github", "npm", "pypi", "dockerhub", "huggingface"]}],
                "recommendation": "CRITICAL: 1 high-value secret(s) found in public repositories. Rotate these credentials immediately - GitHub repos are indexed and may already have been scraped by automated secret hunters.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {"400": "Neither `domain` nor `vendor_domains` supplied."},
        "notes": (
            "Artifact discovery runs under a 75-second budget. If it is exhausted, remaining "
            "sources are skipped and `coverage[].sources` reports exactly what ran -- reduced "
            "coverage is stated rather than returned as a false all-clear. A partial scan is never "
            "cached, so a rate-limited moment cannot be frozen in as a 24-hour clean result."
        ),
    },
    {
        "path": "/v1/metered/secret-scan-text",
        "price_cents": 5,
        "tag": "Secrets and non-human identity",
        "summary": "Scan supplied text or a diff for secrets",
        "description": (
            "Pattern-scans content you send, with no external lookups. Built for pre-commit hooks "
            "and CI: send a unified diff and only added lines are scanned, so pre-existing secrets "
            "in a file do not block every commit that touches it. Priced well below secret-scan "
            "because this fires on every commit."
        ),
        "request": {
            "props": {
                "content": _str("Raw file content to scan. Mutually exclusive with `diff`."),
                "diff": _str("Unified diff. Only added lines are scanned. Mutually exclusive with `content`."),
                "filename": _str("Optional filename, echoed on each finding as `file`. Used with `content`."),
            },
            "any_of": ["content", "diff"],
            "example": {"diff": "--- a/config.py\n+++ b/config.py\n@@ -1,2 +1,3 @@\n import os\n+AWS_SECRET = \"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\"\n"},
        },
        "response": {
            "props": {
                "found": _bool("True when at least one secret was detected."),
                "bytes_scanned": _int("UTF-8 byte length of the payload."),
                "findings": _arr(
                    "Findings, sorted by severity then line number.",
                    _obj("One detected secret.", {
                        "type": _str("Credential type."),
                        "description": _str("What the credential grants."),
                        "severity": _sev("Severity of the credential type."),
                        "line": _int("1-indexed line number in the payload."),
                        "byte_offset": _int("Byte offset of the match."),
                        "length": _int("Length of the matched value."),
                        "fingerprint": _str("Stable non-reversible fingerprint of the value. Lets you dedupe across runs without transmitting the secret."),
                        "llm_provider": _str("LLM or AI provider when the credential is provider-attributable, otherwise empty."),
                        "file": _str("The `filename` you supplied, or the path parsed from the diff."),
                    }),
                ),
                "findings_count": _int("Total findings."),
                "severity_counts": _obj("Counts keyed by severity.", {}),
                "highest_severity": _nullable_sev("Highest severity found. null when clean."),
                "recommendation": _str("Remediation text."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "found": True,
                "bytes_scanned": 142,
                "findings": [{
                    "type": "aws_secret_key",
                    "description": "AWS IAM secret access key",
                    "severity": "CRITICAL",
                    "line": 3,
                    "byte_offset": 74,
                    "length": 40,
                    "fingerprint": "b7f0a2c914e6",
                    "llm_provider": "",
                    "file": "config.py",
                }],
                "findings_count": 1,
                "severity_counts": {"CRITICAL": 1},
                "highest_severity": "CRITICAL",
                "recommendation": "CRITICAL secrets detected. Do not commit. Rotate any credential that has already left this machine, then remove it from the working tree.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "Neither `content` nor `diff` supplied, both supplied, or either is not a string.",
            "413": "Payload exceeds 1,048,576 bytes (1 MiB). Split the scan into smaller batches -- the payload is rejected, never silently truncated.",
        },
        "notes": (
            "The scanned content never reaches RelayShield's logs: only pattern names and counts "
            "are logged. Findings carry a fingerprint rather than the matched value."
        ),
    },
    {
        "path": "/v1/metered/nhi-exposure",
        "price_cents": 40,
        "tag": "Secrets and non-human identity",
        "summary": "Find machine credentials in stealer logs",
        "description": (
            "Scans the stealer-log corpus for non-human identity credentials tied to your domains: "
            "AWS IAM keys, GitHub PATs, Stripe secrets, private keys and Slack tokens. This is not "
            "a repo scan -- it is the criminal side, where leaked keys are already circulating."
        ),
        "request": {
            "props": {
                "domain": _str("Your own domain."),
                "vendor_domains": _arr("Additional supply-chain domains.", _str("Domain.")),
            },
            "any_of": ["domain", "vendor_domains"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domains_checked": _int("Domains scanned. Capped at 10 after deduplication."),
                "found": _bool("True when at least one credential was found."),
                "findings": _arr("Findings, sorted most severe first.", _NHI_FINDING),
                "highest_severity": _nullable_sev("Highest severity found. null when none."),
                "recommendation": _str("Remediation text."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domains_checked": 1,
                "found": True,
                "highest_severity": "CRITICAL",
                "findings": [{
                    "domain": "acme.com",
                    "type": "aws_access_key",
                    "description": "AWS IAM access key",
                    "severity": "CRITICAL",
                    "preview": "AKIA****************",
                    "source": "@cloud_creds_daily",
                    "ingested_at": "2026-07-30T18:22:41Z",
                }],
                "recommendation": "CRITICAL: 1 high-value credential(s) detected. Rotate immediately - API keys and private keys found in stealer logs may be actively exploited. Check your cloud provider IAM access logs for unauthorised activity.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {"400": "Neither `domain` nor `vendor_domains` supplied."},
    },
    {
        "path": "/v1/metered/llm-credential-exposure",
        "price_cents": 40,
        "tag": "Secrets and non-human identity",
        "summary": "Find exposed LLM and AI provider API keys",
        "description": (
            "The LLMjacking case: a stolen inference key is an uncapped billing liability, not just "
            "a data exposure. Covers 14 providers including OpenAI, Anthropic, Google Gemini, xAI, "
            "Amazon Bedrock, Groq, Replicate, LangSmith, Hugging Face, NVIDIA NIM, DeepSeek, "
            "Moonshot, Qwen and Alibaba Cloud -- four of which the most widely deployed open-source "
            "secret scanner ships no detection rules for at all.\n\n"
            "Available pay-per-call on any metered key at $0.40, or under a dedicated unlimited "
            "license ($39/mo or $399/yr) that covers this endpoint only."
        ),
        "request": {
            "props": {
                "domain": _str("Your own domain."),
                "vendor_domains": _arr("Additional supply-chain domains.", _str("Domain.")),
            },
            "any_of": ["domain", "vendor_domains"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domains_checked": _int("Domains scanned. Capped at 10 after deduplication."),
                "found": _bool("True when at least one key was found."),
                "findings": _arr(
                    "Findings, sorted most severe first.",
                    _obj("One exposed LLM provider key.", {
                        "domain": _str("Domain the finding was matched against."),
                        "type": _str("Credential type."),
                        "llm_provider": _str("Provider the key belongs to, e.g. openai, anthropic, deepseek."),
                        "description": _str("What the key grants."),
                        "severity": _sev("Severity."),
                        "preview": _str("Redacted context. Never the key value."),
                        "source": _str("Channel or archive the record came from."),
                        "ingested_at": _str("When RelayShield ingested the record."),
                    }),
                ),
                "highest_severity": _nullable_sev("Highest severity found. null when none."),
                "providers_affected": _arr("Distinct providers with an exposed key, sorted.", _str("Provider name.")),
                "recommendation": _str("Remediation text."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domains_checked": 1,
                "found": True,
                "highest_severity": "CRITICAL",
                "providers_affected": ["anthropic", "openai"],
                "findings": [{
                    "domain": "acme.com",
                    "type": "llm_credential",
                    "llm_provider": "openai",
                    "description": "OpenAI API key",
                    "severity": "CRITICAL",
                    "preview": "sk-****",
                    "source": "@ai_keys_market",
                    "ingested_at": "2026-08-01T06:40:12Z",
                }],
                "recommendation": "CRITICAL: 2 exposed LLM/AI provider API key(s) detected (anthropic, openai). This is a live, uncapped billing liability, not just a data exposure - rotate immediately and check your provider's usage dashboard for anomalous spend right now, don't wait for the invoice.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {"400": "Neither `domain` nor `vendor_domains` supplied."},
        "notes": (
            "A clean result is scoped, not absolute: this covers keys with a recognisable "
            "LLM-provider format. An exposed AWS key with Bedrock access also enables LLMjacking "
            "and surfaces under nhi-exposure instead."
        ),
    },

    # ---------------- Vendor and organisation risk ----------------
    {
        "path": "/v1/metered/supply-chain",
        "price_cents": 10,
        "tag": "Vendor and organisation risk",
        "summary": "Assess breach and infostealer risk across vendors",
        "description": (
            "One call covers up to 10 vendor domains. Each gets a breach and infostealer "
            "assessment plus a 0-100 dark-web composite; results come back sorted worst-first."
        ),
        "request": {
            "props": {
                "vendor_domains": _arr("Vendor domains to assess.", _str("Domain.")),
                "vendor_emails": _arr(
                    "Vendor email addresses. The domain part is extracted and assessed, so you can "
                    "pass a contact list directly.",
                    _str("Email address.", format="email"),
                ),
            },
            "any_of": ["vendor_domains", "vendor_emails"],
            "example": {"vendor_domains": ["vendor-one.com", "vendor-two.com"], "vendor_emails": ["ops@vendor-three.com"]},
        },
        "response": {
            "props": {
                "domains_checked": _int("Distinct domains assessed after deduplication."),
                "highest_risk": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAN"],
                    "description": "Worst risk_level across all vendors.",
                },
                "critical_vendors": _arr("Domains rated CRITICAL.", _str("Domain.")),
                "high_risk_vendors": _arr("Domains rated HIGH.", _str("Domain.")),
                "results": _arr("Per-vendor detail, sorted by dark_web_score descending.", _VENDOR_RESULT),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domains_checked": 2,
                "highest_risk": "HIGH",
                "critical_vendors": [],
                "high_risk_vendors": ["vendor-one.com"],
                "results": [{
                    "domain": "vendor-one.com",
                    "breach_count": 3,
                    "breached_accounts": 41,
                    "breach_names": ["LinkedIn", "Dropbox", "Adobe"],
                    "infostealer_found": True,
                    "infostealer_count": 2,
                    "risk_level": "HIGH",
                    "risk_factors": ["2 devices with credentials for this domain found in infostealer logs"],
                    "recommendation": "High risk. This vendor has significant breach and/or infostealer exposure. Audit their access to your systems, enforce MFA on any shared portals, and consider reducing their permission scope.",
                    "dark_web_score": 72,
                }],
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "Neither `vendor_domains` nor `vendor_emails` yielded a domain, or more than 10 distinct domains were supplied.",
        },
    },
    {
        "path": "/v1/metered/identity-risk-score",
        "price_cents": 35,
        "tag": "Vendor and organisation risk",
        "summary": "Score a domain 0-100 across six identity dimensions",
        "description": (
            "A security credit score for any domain: breach exposure, infostealer density, IOC "
            "corpus presence, ransomware victim listing, active session exposure and CVE exposure. "
            "Returns the per-dimension breakdown as well as the total, so the score is auditable "
            "rather than a black box. MSPs embed this in QBRs, insurance renewals and onboarding "
            "assessments."
        ),
        "request": {
            "props": {"domain": _str("Domain to score.", examples=["acme.com"])},
            "required": ["domain"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domain": _str("The normalised domain."),
                "risk_score": _int("Total 0-100. Higher is worse.", minimum=0, maximum=100),
                "risk_level": {"type": "string", "enum": _SEVERITY, "description": "CRITICAL at 70+, HIGH at 45+, MEDIUM at 22+, otherwise LOW."},
                "grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"], "description": "F at 70+, D at 45+, C at 25+, B at 10+, otherwise A."},
                "dimension_scores": _obj(
                    "Per-dimension contribution to the total.",
                    {
                        "breach_exposure": _int("0-25, scaled by accounts affected."),
                        "infostealer_density": _int("0-25, scaled by stealer-log hit volume."),
                        "ioc_presence": _int("0-15, attributed IOCs referencing the brand."),
                        "ransomware_victim": _int("0 or 20."),
                        "session_exposure": _int("0-10, stolen session records."),
                        "cve_exposure": _int("0-25, weighted toward ransomware-linked KEV entries."),
                    },
                ),
                "max_score": _int("Always 100."),
                "risk_factors": _arr("Plain-English reasons, one per contributing dimension.", _str("One factor.")),
                "summary": _str("One-line summary of score, grade and dimensions triggered."),
                "recommendation": _str("Recommended action."),
            },
            "example": {
                "domain": "acme.com",
                "risk_score": 48,
                "risk_level": "HIGH",
                "grade": "D",
                "dimension_scores": {
                    "breach_exposure": 15,
                    "infostealer_density": 10,
                    "ioc_presence": 0,
                    "ransomware_victim": 0,
                    "session_exposure": 5,
                    "cve_exposure": 18,
                },
                "max_score": 100,
                "risk_factors": ["Breach exposure: 3 known breach event(s), 2,410,000 accounts affected"],
                "summary": "Domain acme.com scores 48/100 (D - HIGH) across 4 of 6 monitored identity signal dimensions.",
                "recommendation": "MEDIUM: Elevated risk signals across multiple surfaces. Review breach history, enforce MFA, and monitor for escalation.",
            },
        },
        "errors": {"400": "`domain` is missing or contains no '.'."},
    },
    {
        "path": "/v1/metered/bulk-identity-risk",
        "price_cents": 200,
        "tag": "Vendor and organisation risk",
        "summary": "Score up to 10 organisations and their agent identities",
        "description": (
            "Hierarchical scoring built for MSP weekly client sweeps and AI agent governance. Each "
            "domain is scored across the same six dimensions as identity-risk-score, and up to 5 "
            "agent or service-account identities per domain are scored across breach, infostealer "
            "and stolen-session signals. A CRITICAL agent automatically elevates its organisation "
            "to at least HIGH."
        ),
        "request": {
            "props": {
                "targets": _arr(
                    "Up to 10 target objects.",
                    _obj("One organisation and its agent identities.", {
                        "domain": _str("Organisation domain."),
                        "agents": _arr("Up to 5 agent or service-account emails.", _str("Email address.", format="email")),
                    }, ["domain"]),
                ),
            },
            "required": ["targets"],
            "example": {"targets": [{"domain": "client-one.com", "agents": ["ci-bot@client-one.com"]}, {"domain": "client-two.com"}]},
        },
        "response": {
            "props": {
                "queried": _int("Targets processed."),
                "critical_count": _int("Targets with a CRITICAL domain or agent."),
                "high_count": _int("Targets with a HIGH domain or agent."),
                "results": _arr(
                    "One entry per target, in the order supplied.",
                    _obj("Scored target.", {
                        "domain": _str("Organisation domain. `invalid` when the target could not be parsed."),
                        "error": _str("Present only when the domain was rejected."),
                        "domain_score": _int("0-100."),
                        "domain_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"], "description": "Letter grade."},
                        "domain_risk": {"type": "string", "enum": _SEVERITY, "description": "Domain risk level."},
                        "dimension_scores": _obj("Per-dimension breakdown, same keys as identity-risk-score.", {}),
                        "domain_factors": _arr("Reasons behind the domain score.", _str("One factor.")),
                        "agents": _arr(
                            "Scored agent identities.",
                            _obj("One agent identity.", {
                                "identity": _str("The agent email."),
                                "risk_score": _int("0-100."),
                                "grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"], "description": "Letter grade."},
                                "risk_level": {"type": "string", "enum": _SEVERITY, "description": "Agent risk level."},
                                "risk_factors": _arr("Reasons behind the agent score.", _str("One factor.")),
                            }),
                        ),
                        "agent_count": _int("Agents scored for this domain."),
                        "highest_agent_risk": {"type": ["string", "null"], "enum": _SEVERITY + [None], "description": "Worst agent risk level. null when no agents were supplied."},
                    }),
                ),
                "summary": _str("One-line roll-up across all targets."),
            },
            "example": {
                "queried": 2,
                "critical_count": 0,
                "high_count": 1,
                "results": [{
                    "domain": "client-one.com",
                    "domain_score": 52,
                    "domain_grade": "D",
                    "domain_risk": "HIGH",
                    "dimension_scores": {"breach_exposure": 20, "infostealer_density": 10, "ioc_presence": 0, "ransomware_victim": 0, "session_exposure": 5, "cve_exposure": 17},
                    "domain_factors": ["3 actively exploited CVEs affecting Client-one products (1 ransomware-linked)"],
                    "agents": [{"identity": "ci-bot@client-one.com", "risk_score": 30, "grade": "C", "risk_level": "MEDIUM", "risk_factors": ["1 stolen session record(s) in criminal corpus"]}],
                    "agent_count": 1,
                    "highest_agent_risk": "MEDIUM",
                }],
                "summary": "0 CRITICAL, 1 HIGH risk identities across 2 domains.",
            },
        },
        "errors": {
            "400": "`targets` is missing, not a list, empty, or holds more than 10 entries.",
        },
        "notes": (
            "A target whose domain is unparseable does not fail the call: it comes back as an "
            "entry carrying `error`, and the remaining targets are still scored."
        ),
    },
    {
        "path": "/v1/metered/target-risk",
        "price_cents": 50,
        "tag": "Vendor and organisation risk",
        "summary": "Score how likely a domain is to be targeted",
        "description": (
            "Correlates six signals -- ransomware victim listing, stealer-log hits, breach "
            "exposure, criminal channel mentions, high-EPSS CVEs and pre-ransomware credentials -- "
            "into a 0-100 score with a four-tier rating. Every contributing signal is returned with "
            "its weight, so the score can be explained to whoever has to act on it."
        ),
        "request": {
            "props": {"domain": _str("Domain to score. A leading `www.` is stripped.", examples=["acme.com"])},
            "required": ["domain"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "record_type": _str("Always `threat_prediction`."),
                "domain": _str("The normalised domain."),
                "target_risk_score": _int("0-100. Higher is worse.", minimum=0, maximum=100),
                "probability_tier": {"type": "string", "enum": _SEVERITY, "description": "CRITICAL at 60+, HIGH at 35+, MEDIUM at 15+, otherwise LOW."},
                "signals": _arr(
                    "Only the signals that fired, each with the points it contributed.",
                    _obj("One contributing signal.", {
                        "signal": {
                            "type": "string",
                            "enum": ["ransomware_victim", "stealer_log_hits", "breach_exposure", "criminal_channel_mention", "high_epss_cves_active"],
                            "description": "Signal identifier.",
                        },
                        "weight": _int("Points this signal added to the total."),
                        "detail": _str("Plain-English explanation."),
                    }),
                ),
                "recommendation": _str("Recommended action for the tier."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "record_type": "threat_prediction",
                "domain": "acme.com",
                "target_risk_score": 45,
                "probability_tier": "HIGH",
                "signals": [
                    {"signal": "breach_exposure", "weight": 10, "detail": "6 breaches, 214 accounts exposed"},
                    {"signal": "criminal_channel_mention", "weight": 15, "detail": "Domain observed in criminal Telegram channels"},
                    {"signal": "high_epss_cves_active", "weight": 20, "detail": "5 CVE(s) with >=50% exploitation probability active globally - CVE-2026-21042 (Remote code execution)"},
                ],
                "recommendation": "HIGH risk: acme.com shows significant exposure signals. Rotate credentials, audit vendor access, and increase monitoring frequency.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {"400": "`domain` is missing or contains no '.'."},
        "notes": (
            "Each of the six signal lookups is independently fault-tolerant: one failing source "
            "lowers the score rather than failing the request, so treat a LOW score as "
            "'no signals fired', not as a guarantee."
        ),
    },
    {
        "path": "/v1/metered/ransomware-risk",
        "price_cents": 40,
        "tag": "Vendor and organisation risk",
        "summary": "Check a domain against ransomware leak sites",
        "description": (
            "Queries 100+ active ransomware group leak sites for a victim listing, and counts "
            "credentials for the domain that appeared in stealer logs before the incident -- the "
            "pre-attack reconnaissance signal."
        ),
        "request": {
            "props": {"domain": _str("Domain to check. A leading `www.` is stripped.", examples=["acme.com"])},
            "required": ["domain"],
            "example": {"domain": "acme.com"},
        },
        "response": {
            "props": {
                "domain": _str("The normalised domain."),
                "on_victim_list": _bool("True when claimed by at least one ransomware group."),
                "victim_groups": _arr("Groups claiming the victim.", _str("Group name.")),
                "first_seen": _str("Earliest listing date. Empty when not listed."),
                "pre_ransomware_ioc_count": _int("Credentials for this domain seen in stealer logs before the incident."),
                "risk_level": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "CLEAN"],
                    "description": "CRITICAL when listed, HIGH when only pre-ransomware credentials exist, otherwise CLEAN.",
                },
                "recommendation": _str("Recommended action."),
                "checked_at": _CHECKED_AT,
            },
            "example": {
                "domain": "acme.com",
                "on_victim_list": False,
                "victim_groups": [],
                "first_seen": "",
                "pre_ransomware_ioc_count": 4,
                "risk_level": "HIGH",
                "recommendation": "4 credential(s) for acme.com appeared in criminal stealer logs before a ransomware incident was associated with this domain. These credentials may indicate pre-attack reconnaissance. Rotate any shared credentials with this organisation.",
                "checked_at": "2026-08-04T11:02:07.481923+00:00",
            },
        },
        "errors": {
            "400": "`domain` is missing or contains no '.'.",
            "500": "Ransomware victim query failed.",
        },
    },
    {
        "path": "/v1/metered/brand-monitor",
        "price_cents": 35,
        "tag": "Vendor and organisation risk",
        "summary": "Find brand abuse across the IOC corpus",
        "description": (
            "Scans the full IOC corpus for your brand name and classifies what it finds into "
            "phishing domains, malware C2 infrastructure, dark web mentions, and logo or image "
            "mentions extracted by OCR from infostealer-archive screenshots."
        ),
        "request": {
            "props": {"brand": _str("Brand name to search for. Minimum 3 characters, matched case-insensitively.", minLength=3)},
            "required": ["brand"],
            "example": {"brand": "acme"},
        },
        "response": {
            "props": {
                "brand": _str("The lowercased brand searched."),
                "matched": _bool("True when any mention was found."),
                "total_mentions": _int("Total corpus hits, capped at 500."),
                "phishing_domains": _int("Hits classified as phishing domains or URLs."),
                "malware_c2": _int("Hits carrying a malware family attribution."),
                "dark_web_mentions": _int("Hits from criminal channels or credential dumps."),
                "image_logo_mentions": _int("Hits from OCR of screenshots in infostealer archives."),
                "hits": _obj(
                    "Up to 20 sample hits per category.",
                    {
                        "phishing": _arr("Phishing samples.", _IOC_SUMMARY),
                        "malware_c2": _arr("Malware C2 samples.", _IOC_SUMMARY),
                        "dark_web": _arr("Dark web samples.", _IOC_SUMMARY),
                        "image_logo": _arr("Logo/image samples.", _IOC_SUMMARY),
                    },
                ),
                "recommendation": _str("Recommended action."),
            },
            "example": {
                "brand": "acme",
                "matched": True,
                "total_mentions": 27,
                "phishing_domains": 14,
                "malware_c2": 6,
                "dark_web_mentions": 5,
                "image_logo_mentions": 2,
                "hits": {
                    "phishing": [{"ioc_value": "acme-login-secure.com", "ioc_type": "domain", "source": "phishtank", "malware": "", "last_seen": "2026-08-02T14:31:00Z"}],
                    "malware_c2": [],
                    "dark_web": [],
                    "image_logo": [],
                },
                "recommendation": "CRITICAL: active brand abuse detected in criminal infrastructure",
            },
        },
        "errors": {"400": "`brand` is missing or shorter than 3 characters."},
    },

    # ---------------- Threat intelligence ----------------
    {
        "path": "/v1/metered/bulk-ioc",
        "price_cents": 50,
        "tag": "Threat intelligence",
        "summary": "Enrich up to 100 indicators in one call",
        "description": (
            "Built for SIEM log-enrichment pipelines. Submit up to 100 indicators of any type and "
            "get malware family, threat actor, confidence and first/last seen for each. Priced per "
            "batch, not per indicator."
        ),
        "request": {
            "props": {
                "iocs": _arr(
                    "1 to 100 indicators. Values are lowercased and trimmed; empty entries are dropped.",
                    _str("An IP, domain, URL, hash, email or wallet address."),
                ),
            },
            "required": ["iocs"],
            "example": {"iocs": ["185.220.101.44", "evil-c2.example", "d41d8cd98f00b204e9800998ecf8427e"]},
        },
        "response": {
            "props": {
                "queried": _int("Indicators actually processed after dropping empties."),
                "matched": _int("Indicators found in the corpus."),
                "results": _arr(
                    "One entry per indicator, in the order supplied.",
                    _obj("Enrichment for one indicator.", {
                        "ioc_value": _str("The normalised indicator."),
                        "matched": _bool("True when found in the corpus."),
                        "ioc_type": _str("Indicator type. Present only on a match."),
                        "source": _str("Feed or channel it was seen in. Present only on a match."),
                        "malware": _str("Malware family. Present only on a match."),
                        "threat_actor": _str("Attributed actor. Present only on a match."),
                        "confidence_score": _num("0.0 to 1.0. Present only on a match."),
                        "first_seen": _str("Earliest sighting. Present only on a match."),
                        "last_seen": _str("Most recent sighting. Present only on a match."),
                        "hit_count": _int("Distinct sightings, capped at 5. Present only on a match."),
                        "error": _str("`query_failed` when this one indicator's lookup errored. Present only on failure."),
                    }),
                ),
            },
            "example": {
                "queried": 3,
                "matched": 1,
                "results": [
                    {"ioc_value": "185.220.101.44", "matched": True, "ioc_type": "ip", "source": "@botnet_c2_feed", "malware": "mirai", "threat_actor": "", "confidence_score": 0.85, "first_seen": "2026-07-11T02:00:00Z", "last_seen": "2026-08-03T19:44:12Z", "hit_count": 4},
                    {"ioc_value": "evil-c2.example", "matched": False},
                    {"ioc_value": "d41d8cd98f00b204e9800998ecf8427e", "matched": False},
                ],
            },
        },
        "errors": {"400": "`iocs` is missing, not a list, empty, or holds more than 100 entries."},
        "notes": (
            "A single indicator whose lookup fails is returned with `matched: false` and "
            "`error: query_failed` rather than failing the batch."
        ),
    },
    {
        "path": "/v1/metered/ioc-pivot",
        "price_cents": 20,
        "tag": "Threat intelligence",
        "summary": "Discover infrastructure related to one indicator",
        "description": (
            "Given one known-malicious indicator, returns every related indicator sharing the same "
            "malware family -- surfacing a full C2 network from a single starting point."
        ),
        "request": {
            "props": {
                "ioc": _str("The indicator to pivot from."),
                "ioc_value": _str("Accepted as an alias for `ioc`. Use `ioc` for new integrations."),
            },
            "any_of": ["ioc", "ioc_value"],
            "example": {"ioc": "185.220.101.44"},
        },
        "response": {
            "props": {
                "ioc_value": _str("The normalised pivot indicator."),
                "matched": _bool("False when the pivot indicator is not in the corpus. `related` is then empty."),
                "pivot_on": {"type": "string", "enum": ["malware_family", "source_feed"], "description": "What the pivot was performed on. Falls back to source feed when the seed carries no malware family."},
                "pivot_value": _str("The family or feed name pivoted on."),
                "seed_ioc_type": _str("Indicator type of the seed."),
                "seed_source": _str("Feed or channel the seed came from."),
                "seed_malware": _str("Malware family of the seed. Empty when unattributed."),
                "related_count": _int("Total related indicators found."),
                "related": _arr("Up to 50 related indicators.", _IOC_SUMMARY),
            },
            "example": {
                "ioc_value": "185.220.101.44",
                "matched": True,
                "pivot_on": "malware_family",
                "pivot_value": "mirai",
                "seed_ioc_type": "ip",
                "seed_source": "@botnet_c2_feed",
                "seed_malware": "mirai",
                "related_count": 38,
                "related": [{"ioc_value": "185.220.101.71", "ioc_type": "ip", "source": "@botnet_c2_feed", "malware": "mirai", "last_seen": "2026-08-03T20:02:55Z"}],
            },
        },
        "errors": {"400": "`ioc` (or `ioc_value`) is missing or empty, or the corpus lookup failed."},
    },
    {
        "path": "/v1/metered/threat-actor",
        "price_cents": 30,
        "tag": "Threat intelligence",
        "summary": "Exploit chatter and threat actor lookup",
        "description": (
            "Two actions on one endpoint, selected with `action`.\n\n"
            "`exploit-chatter` detects pre-publication CVE proof-of-concept discussion in criminal "
            "channels, with EPSS score and CISA KEV status.\n\n"
            "`actor-lookup` (the default) resolves a threat actor or malware campaign to its MITRE "
            "ATT&CK group, associated malware, and live indicators from RelayShield's corpus."
        ),
        "request": {
            "props": {
                "action": {"type": "string", "enum": ["actor-lookup", "exploit-chatter"], "default": "actor-lookup", "description": "Which lookup to run."},
                "cve_id": _str("Required when action is `exploit-chatter`. Format CVE-YYYY-NNNNN, case-insensitive.", pattern="^[Cc][Vv][Ee]-[0-9]{4}-[0-9]+$"),
                "actor": _str("Actor or campaign name. Used when action is `actor-lookup`."),
                "actors": _arr("Up to 5 actor names, used when `actor` is not supplied.", _str("Actor name.")),
            },
            "any_of": ["cve_id", "actor", "actors"],
            "example": {"action": "actor-lookup", "actor": "APT29"},
        },
        "response": {
            "props": {
                "results": _arr(
                    "actor-lookup only. One entry per search term.",
                    _obj("Lookup result for one term.", {
                        "term": _str("The term searched."),
                        "found": _bool("True when indicators or a MITRE group were resolved."),
                        "ioc_count": _int("Indicators found across the actor's associated malware."),
                        "ioc_breakdown": _obj("Counts keyed by indicator type.", {}),
                        "sources": _arr("Channels the indicators came from.", _str("Channel.")),
                        "latest_ioc": _str("Most recent sighting timestamp."),
                        "mitre": _obj("MITRE ATT&CK group detail.", {
                            "group_name": _str("Canonical group name."),
                            "aliases": _arr("Known aliases.", _str("Alias.")),
                            "techniques": _arr("Up to 10 technique IDs.", _str("Technique ID, e.g. T1078.")),
                            "description": _str("Group description, truncated to 300 characters."),
                        }),
                        "associated_malware": _arr("Malware and tool names resolved via MITRE.", _str("Malware name.")),
                        "sample_iocs": _arr("Up to 5 example indicators.", _obj("Sample indicator.", {
                            "value": _str("Indicator value."),
                            "type": _str("Indicator type."),
                            "malware": _str("Malware family."),
                            "seen_ts": _str("Sighting timestamp."),
                        })),
                    }),
                ),
                "terms_searched": _int("actor-lookup only. Number of terms processed."),
                "cve_id": _str("exploit-chatter only. The uppercased CVE ID."),
                "found": _bool("exploit-chatter only. True when chatter or linked indicators exist."),
                "risk_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "exploit-chatter only. HIGH with chatter, MEDIUM with only linked indicators, otherwise LOW."},
                "chatter_count": _int("exploit-chatter only. Distinct chatter records."),
                "chatter_sources": _arr("exploit-chatter only. Up to 5 source names.", _str("Source.")),
                "first_seen": _str("exploit-chatter only. Earliest chatter timestamp."),
                "ioc_hits": _int("exploit-chatter only. Indicators referencing the CVE."),
                "in_kev": _bool("exploit-chatter only. True when the CVE is in CISA KEV."),
                "epss_score": _num("exploit-chatter only. EPSS exploitation probability, 0.0 to 1.0."),
                "kev_date_added": _str("exploit-chatter only. Date added to KEV."),
                "note": _str("exploit-chatter only. Interpretation of the result."),
            },
            "example": {
                "results": [{
                    "term": "APT29",
                    "found": True,
                    "ioc_count": 46,
                    "ioc_breakdown": {"domain": 28, "ip": 18},
                    "sources": ["@apt_tracking"],
                    "latest_ioc": "2026-08-02T11:19:00Z",
                    "mitre": {"group_name": "APT29", "aliases": ["Cozy Bear", "Midnight Blizzard"], "techniques": ["T1078", "T1566.002"], "description": "APT29 is a threat group attributed to Russia's Foreign Intelligence Service."},
                    "associated_malware": ["cobaltstrike", "wellmess"],
                    "sample_iocs": [{"value": "cdn-update.example", "type": "domain", "malware": "wellmess", "seen_ts": "2026-08-02T11:19:00Z"}],
                }],
                "terms_searched": 1,
            },
        },
        "errors": {
            "400": "action is `exploit-chatter` and `cve_id` is missing or malformed, or action is `actor-lookup` and neither `actor` nor `actors` was supplied.",
        },
    },
    {
        "path": "/v1/metered/cve-identity-risk",
        "price_cents": 40,
        "tag": "Threat intelligence",
        "summary": "Correlate a CVE with a specific organisation's exposure",
        "description": (
            "Closes the loop from vulnerability to live identity exposure. Combines CISA KEV "
            "status, EPSS, infostealer corpus hits for the exploiting malware families, ransomware "
            "victim listing and exploit chatter into one 0-100 score for a specific domain."
        ),
        "request": {
            "props": {
                "cve_id": _str("CVE identifier. Format CVE-YYYY-NNNNN, case-insensitive.", pattern="^[Cc][Vv][Ee]-[0-9]{4}-[0-9]+$"),
                "domain": _str("Domain to correlate against."),
            },
            "required": ["cve_id", "domain"],
            "example": {"cve_id": "CVE-2026-21042", "domain": "acme.com"},
        },
        "response": {
            "props": {
                "cve_id": _str("The uppercased CVE ID."),
                "domain": _str("The lowercased domain."),
                "risk_score": _int("0-100. Higher is worse.", minimum=0, maximum=100),
                "risk_level": {"type": "string", "enum": _SEVERITY, "description": "CRITICAL at 75+, HIGH at 50+, MEDIUM at 25+, otherwise LOW."},
                "in_kev": _bool("True when the CVE is in CISA KEV."),
                "epss_score": _num("EPSS exploitation probability, 0.0 to 1.0."),
                "ransomware_linked": _bool("True when the CVE is linked to known ransomware campaigns."),
                "affected_product": _str("Product named on the KEV record."),
                "exploiting_families": _arr("Malware families known to exploit this CVE.", _str("Family name.")),
                "stealer_corpus_hits": _arr(
                    "Where an exploiting family and the domain co-occur in the corpus.",
                    _obj("One family correlation.", {
                        "family": _str("Malware family."),
                        "ioc_count": _int("Indicators matched."),
                        "latest": _str("Most recent sighting."),
                    }),
                ),
                "on_ransomware_victim_list": _bool("True when the domain appears on a ransomware leak site."),
                "victim_groups": _arr("Groups claiming the domain.", _str("Group name.")),
                "exploit_chatter_count": _int("Pre-publication chatter signals for this CVE."),
                "risk_factors": _arr("One line per signal that contributed, with its reasoning.", _str("One factor.")),
                "recommendation": _str("Recommended action for the score band."),
            },
            "example": {
                "cve_id": "CVE-2026-21042",
                "domain": "acme.com",
                "risk_score": 55,
                "risk_level": "HIGH",
                "in_kev": True,
                "epss_score": 0.62,
                "ransomware_linked": True,
                "affected_product": "Acme Gateway",
                "exploiting_families": ["lockbit"],
                "stealer_corpus_hits": [],
                "on_ransomware_victim_list": False,
                "victim_groups": [],
                "exploit_chatter_count": 0,
                "risk_factors": [
                    "CVE is in CISA KEV - confirmed active exploitation",
                    "EPSS score 0.62 - top exploitation probability tier",
                    "CVE is linked to known ransomware campaigns",
                ],
                "recommendation": "HIGH PRIORITY: Multiple correlated signals indicate elevated exploitation risk for this domain. Verify patch status and review infostealer exposure.",
            },
        },
        "errors": {
            "400": "`cve_id` is missing or malformed, or `domain` is missing.",
        },
    },
    {
        "path": "/v1/metered/tech-stack-cve",
        "price_cents": 20,
        "tag": "Threat intelligence",
        "summary": "Find CVEs actively targeting your declared stack",
        "description": (
            "Pass the products you run, or a domain whose stored stack RelayShield already holds, "
            "and get back the KEV and high-EPSS CVEs that match. Covers AI agent orchestration "
            "frameworks (Langflow, LangChain, AutoGPT, CrewAI, Flowise, self-hosted n8n) and their "
            "common companion infrastructure, which is the exact vector used in the first "
            "documented autonomous-AI-agent ransomware operation."
        ),
        "request": {
            "props": {
                "tech_stack": _arr("Product names. Entries shorter than 3 characters are ignored.", _str("Product name, e.g. `langflow`.")),
                "domain": _str("Domain whose stored tech stack should be used. Only consulted when `tech_stack` is absent."),
            },
            "any_of": ["tech_stack", "domain"],
            "example": {"tech_stack": ["langflow", "minio", "nacos"]},
        },
        "response": {
            "props": {
                "tech_stack_queried": _arr("The stack actually used, whether supplied or loaded from the domain.", _str("Product name.")),
                "total_matches": _int("CVEs matching the stack."),
                "critical_count": _int("Matches that are in KEV or ransomware-linked."),
                "summary": _str("One-line roll-up."),
                "critical_cves": _arr("Up to 10 KEV or ransomware-linked matches.", _obj("A matched CVE.", {
                    "cve_id": _str("CVE identifier."),
                    "matched_product": _str("Which stack entry matched."),
                    "epss_score": _num("EPSS exploitation probability."),
                    "in_kev": _bool("True when in CISA KEV."),
                    "ransomware_campaign": _bool("True when linked to a ransomware campaign."),
                    "cvss_score": {"type": ["number", "null"], "description": "CVSS base score. null when unscored."},
                    "description": _str("Description, truncated to 200 characters."),
                    "published": _str("Publication or KEV-addition date."),
                    "poc_available": _bool("Present on up to 3 non-KEV matches: whether a public proof-of-concept exists."),
                })),
                "all_matches": _arr("Up to 25 matches, sorted KEV first, then ransomware-linked, then by EPSS.", _obj("A matched CVE.", {})),
            },
            "example": {
                "tech_stack_queried": ["langflow", "minio", "nacos"],
                "total_matches": 6,
                "critical_count": 2,
                "summary": "2 CRITICAL CVEs actively targeting your stack (KEV/ransomware-linked)",
                "critical_cves": [{
                    "cve_id": "CVE-2025-3248",
                    "matched_product": "langflow",
                    "epss_score": 0.94,
                    "in_kev": True,
                    "ransomware_campaign": False,
                    "cvss_score": 9.8,
                    "description": "Langflow code validation endpoint permits unauthenticated remote code execution.",
                    "published": "2025-04-09",
                }],
                "all_matches": [],
            },
        },
        "errors": {
            "400": "`tech_stack` is missing or not a list and no stored stack was found for `domain`.",
        },
        "notes": (
            "The proof-of-concept lookup is deliberately bounded to the top 3 non-KEV matches. A "
            "CVE already in KEV is being exploited in the wild, which is a strictly stronger signal "
            "than a public PoC existing."
        ),
    },
    {
        "path": "/v1/metered/asset-intel",
        "price_cents": 15,
        "tag": "Threat intelligence",
        "summary": "Register assets and sweep them against the IOC corpus",
        "description": (
            "A watchlist scoped to your API key. `register` adds domains and IPs, `sweep` checks "
            "them against the 4.6M+ indicator corpus, `list` returns what is registered, `remove` "
            "deletes entries. Once a webhook is configured, new matches against registered assets "
            "are pushed to you automatically."
        ),
        "request": {
            "props": {
                "action": {
                    "type": "string",
                    "enum": ["sweep", "register", "list", "remove"],
                    "default": "sweep",
                    "description": "Operation to perform. Defaults to `sweep`.",
                },
                "assets": _arr(
                    "Domains or IPs. Required for `register`. Optional for `sweep` -- when omitted, "
                    "your registered watchlist is swept instead. `register` caps at 50 per call.",
                    _str("Domain or IP address."),
                ),
            },
            "example": {"action": "register", "assets": ["acme.com", "203.0.113.15"]},
        },
        "response": {
            "props": {
                "matches": _arr(
                    "sweep only. One entry per asset found in the corpus.",
                    _obj("A matched asset.", {
                        "asset": _str("The registered asset that matched."),
                        "ioc_type": _str("Indicator type."),
                        "source": _str("Feed or channel."),
                        "malware": _str("Malware family. Empty when unattributed."),
                        "confidence": _num("0.0 to 1.0."),
                        "first_seen": _str("Earliest sighting."),
                        "threat_actor": _str("Attributed actor. Empty when unattributed."),
                    }),
                ),
                "assets_checked": _int("sweep only. Assets swept."),
                "match_count": _int("sweep only. Assets that matched."),
                "clean_count": _int("sweep only. Assets that did not match."),
                "registered": _arr("register only. Assets successfully added.", _str("Asset.")),
                "count": _int("register and list. Number of assets."),
                "assets": _arr("list only. Registered assets.", _str("Asset.")),
                "removed": _arr("remove only. Assets requested for removal.", _str("Asset.")),
                "note": _str("Present on register, and on a sweep with an empty watchlist."),
            },
            "example": {"registered": ["acme.com", "203.0.113.15"], "count": 2, "note": "Push alerts will fire via your registered webhook when new IOCs match these assets."},
        },
        "errors": {
            "400": "action is `register` and `assets` is empty.",
            "500": "Watchlist read or write failed.",
        },
        "notes": (
            "The watchlist is keyed on your API key, so a rotated key starts with an empty "
            "watchlist. Configure delivery with /v1/webhook/configure before registering assets if "
            "you want push alerts."
        ),
    },

    # ---------------- Crypto ----------------
    {
        "path": "/v1/metered/crypto-intel",
        "price_cents": 30,
        "tag": "Crypto",
        "summary": "Screen an EVM address and optionally a token contract",
        "description": (
            "Screens an EVM address for phishing, sanctions and cybercrime associations, and "
            "optionally screens a token contract for honeypot, mintable-supply, hidden-owner and "
            "sell-tax risk. Returns a composite rating plus cross-surface advisories pointing at "
            "the identity checks that pair with the finding."
        ),
        "request": {
            "props": {
                "address": _str("EVM address: `0x` followed by 40 hex characters.", pattern="^0x[0-9a-fA-F]{40}$"),
                "chain_id": _str("EVM chain ID as a string. Defaults to `1` (Ethereum mainnet).", default="1"),
                "token_address": _str("Optional token contract to screen alongside the address. Same format as `address`."),
            },
            "required": ["address"],
            "example": {"address": "0x0000000000000000000000000000000000000000", "chain_id": "1"},
        },
        "response": {
            "props": {
                "address": _str("The lowercased address."),
                "chain_id": _str("The chain ID used."),
                "composite_risk": {"type": "string", "enum": _SEVERITY, "description": "CRITICAL on a critical address or token flag, HIGH on any address flag or token warning, MEDIUM on a warning-tier address flag, otherwise LOW."},
                "address_flags": _arr("Raw risk flags returned for the address.", _str("Flag name, e.g. `phishing_activities`, `sanctioned`.")),
                "correlation_advisories": _arr("Cross-surface guidance naming the identity endpoints to call next.", _str("One advisory.")),
                "token_risk": _obj("Present only when `token_address` was supplied and screening succeeded.", {
                    "contract_address": _str("The token contract screened."),
                    "token_name": _str("Token name."),
                    "token_symbol": _str("Token symbol."),
                    "critical_flags": _arr("Deal-breaker flags: honeypot, airdrop scam, fake token, sell tax at or above 50%.", _str("Flag label.")),
                    "warning_flags": _arr("Caution flags: pausable transfers, mintable supply, hidden owner, sell tax 10-49%.", _str("Flag label.")),
                }),
            },
            "example": {
                "address": "0x0000000000000000000000000000000000000000",
                "chain_id": "1",
                "composite_risk": "LOW",
                "address_flags": [],
                "correlation_advisories": ["No risk signals detected on this address. For complete protection, monitor the associated email via /v1/metered/breach and phone via /v1/metered/sim-swap."],
            },
        },
        "errors": {
            "400": "`address` is missing or is not a valid EVM address.",
        },
        "notes": (
            "If the upstream screening provider is unreachable, the call still succeeds with empty "
            "flags rather than erroring. Treat an empty `address_flags` as 'no signal', not as a "
            "verified clean address."
        ),
    },

    # ---------------- Agent and MCP security ----------------
    #
    # These two are served by relayshield_agentic_api.py, a deliberately
    # isolated Lambda, on the same host and the same /v1/metered/ prefix. Three
    # behavioural differences from every endpoint above, all documented on the
    # operations themselves because a caller cannot see the Lambda boundary:
    #   1. Authentication accepts X-API-Key as well as X-RS-API-KEY, and does
    #      NOT accept Authorization: Bearer.
    #   2. There is no credit check, so no 402 -- see the note on each.
    #   3. Verdicts are explicitly non-conclusive; both endpoints return a
    #      `note` saying so, and the descriptions repeat it.
    {
        "path": "/v1/metered/mcp-registry-risk",
        "price_cents": 35,
        "tag": "Agent and MCP security",
        "summary": "Check an MCP server or package for registry risk",
        "description": (
            "Reputation for the MCP ecosystem, where dedicated security tooling is still minimal "
            "industry-wide. Checks an MCP server URL or package name against RelayShield's criminal "
            "IOC corpus, runs typosquat and near-miss detection against well-known MCP domains "
            "(edit distance 2 or less), and checks domain registration age via RDAP.\n\n"
            "**A LOW verdict means no red flags, not verified safe.** Each check can only find what "
            "it looks for, and a brand-new malicious server that has not yet been reported will "
            "return LOW. When `findings` is empty the response carries a `note` saying exactly this."
        ),
        "request": {
            "props": {
                "server_url": _str(
                    "Full MCP server URL. The hostname is extracted and a leading `www.` stripped. "
                    "Supplying this enables all three checks.",
                    format="uri",
                    examples=["https://mcp.example-tools.io/sse"],
                ),
                "package_name": _str(
                    "Package name, used when there is no server URL. Package-name-only checks are "
                    "limited to the IOC corpus, which has no dedicated MCP package coverage yet, so "
                    "a name-only call always returns at least a `package_name_only` finding "
                    "recording that reduced coverage."
                ),
            },
            "any_of": ["server_url", "package_name"],
            "example": {"server_url": "https://mcp.example-tools.io/sse"},
        },
        "response": {
            "props": {
                "queried": _str("The `server_url` you supplied, or `package_name` when no URL was given."),
                "domain": _str("Hostname extracted from `server_url`. Empty on a package-name-only call."),
                "verdict": {
                    "type": "string",
                    "enum": _SEVERITY,
                    "description": "Highest finding severity, or `LOW` when there are none. `LOW` means nothing was found, not that the server is safe.",
                },
                "findings": _arr(
                    "Every check that fired. Empty when nothing was found.",
                    _obj("One finding.", {
                        "type": {
                            "type": "string",
                            "enum": ["known_malicious_ioc", "typosquat_suspected", "newly_registered_domain", "package_name_only"],
                            "description": (
                                "`known_malicious_ioc` (CRITICAL) the domain is in RelayShield's criminal IOC corpus. "
                                "`typosquat_suspected` (HIGH) within edit distance 2 of a well-known MCP domain. "
                                "`newly_registered_domain` (MEDIUM) registered under 30 days ago. "
                                "`package_name_only` (LOW) not a risk signal, a coverage warning that no URL was supplied."
                            ),
                        },
                        "severity": _sev("Severity of this finding."),
                        "detail": _str("Plain-English explanation, including the matched domain or edit distance."),
                    }),
                ),
                "note": {
                    "type": ["string", "null"],
                    "description": "Present and non-null only when `findings` is empty, stating that absence of findings means unknown rather than verified safe. null when there are findings.",
                },
            },
            "example": {
                "queried": "https://mcp.example-tools.io/sse",
                "domain": "mcp.example-tools.io",
                "verdict": "MEDIUM",
                "findings": [{
                    "type": "newly_registered_domain",
                    "severity": "MEDIUM",
                    "detail": "mcp.example-tools.io was registered 12 days ago",
                }],
                "note": None,
            },
        },
        "errors": {
            "400": "Neither `server_url` nor `package_name` supplied.",
            "429": "A shared demo key's daily quota is exhausted. Does not apply to your own key.",
        },
        "auth": ["ApiKeyAuth", "ApiKeyAuthAlt"],
        "no_credit_check": True,
        "notes": (
            "Each of the three checks is independently fault-tolerant: an unreachable RDAP or IOC "
            "lookup is skipped rather than failing the call, so it lowers the verdict instead of "
            "raising an error. Combined with the point above, treat `LOW` as 'nothing found by the "
            "checks that ran'. Also billed as an AWS Marketplace Bundle D dimension for bundle "
            "customers."
        ),
    },
    {
        "path": "/v1/metered/prompt-injection-breach",
        "price_cents": 35,
        "tag": "Agent and MCP security",
        "summary": "Find exposure from breaches that look AI-agent-sourced",
        "description": (
            "Returns stolen session and credential records for an address where the source dump's "
            "own announcement text suggests an AI agent, rather than a traditional phishing or "
            "malware campaign, was involved in obtaining it.\n\n"
            "**This is a heuristic, not an attribution.** It is a keyword classifier over "
            "dump-announcement text, with no labelled ground truth. A match is a reason to look "
            "closer, and no match does not rule out an AI-agent-involved breach. For unfiltered "
            "stolen-session exposure on the same address, use `/v1/metered/session-risk`."
        ),
        "request": {
            "props": {"email": _str("Email address to check.", format="email")},
            "required": ["email"],
            "example": {"email": "user@example.com"},
        },
        "response": {
            "props": {
                "email": _str("The normalised address that was checked."),
                "found": _bool("True when at least one record carries the suspected-agentic-source marker."),
                "session_count": _int("Number of matching records."),
                "sessions": _arr(
                    "Matching records. Unordered.",
                    _obj("One record.", {
                        "domain": _str("Service the stolen session or credential belongs to."),
                        "severity": _sev("Severity derived from the service category."),
                        "service_category": _str("Category of the affected service, e.g. cloud_console, identity_provider, productivity."),
                        "channel_source": _str("Criminal channel or archive the record was collected from."),
                        "ingested_at": _str("When RelayShield ingested the record."),
                    }),
                ),
                "note": _str("Present only when `found` is false. States that a non-match does not rule out an AI-agent-involved breach."),
                "action_required": _str("Present only when `found` is true. Remediation guidance."),
            },
            "example": {
                "email": "user@example.com",
                "found": True,
                "session_count": 1,
                "sessions": [{
                    "domain": "app.example-saas.com",
                    "severity": "HIGH",
                    "service_category": "productivity",
                    "channel_source": "@agent_dumps",
                    "ingested_at": "2026-07-27T15:03:22Z",
                }],
                "action_required": "This exposure surfaced from a dump whose own announcement text suggests an AI agent (rather than a traditional phishing/malware campaign) was involved in obtaining it. Treat with the same urgency as an active session hijack - revoke sessions and rotate credentials for the listed services.",
            },
        },
        "errors": {
            "400": "`email` is missing or contains no '@'.",
            "429": "A shared demo key's daily quota is exhausted. Does not apply to your own key.",
            "500": "Stolen-session corpus query failed.",
        },
        "auth": ["ApiKeyAuth", "ApiKeyAuthAlt"],
        "no_credit_check": True,
        "notes": (
            "Reads the same corpus as `/v1/metered/session-risk`, filtered to records the ingestion "
            "pipeline flagged as suspected-agentic-source. Also billed as an AWS Marketplace "
            "Bundle D dimension for bundle customers."
        ),
    },

    # ---------------- Account ----------------
    {
        "path": "/v1/account/info",
        "price_cents": 0,
        "tag": "Account",
        "summary": "Return the account behind an API key",
        "description": (
            "Free and unmetered. Used to confirm a key is live and to label a connected account. "
            "This is the endpoint RelayShield's own Zapier, n8n and Make integrations call to test "
            "a connection."
        ),
        "request": {
            "props": {},
            "example": {},
            "body_note": "Send an empty JSON object.",
        },
        "response": {
            "props": {
                "plan": _str("Plan name on the key, e.g. `personal`."),
                "intel_access": _bool("True when the key carries a Threat Intelligence subscription."),
                "calls_this_month": _int("Metered calls made in the current month."),
                "customer_id": _str("Billing customer ID. Empty for AWS Marketplace keys."),
                "email": _str("Account email."),
                "active": _bool("False when the key has been deactivated."),
            },
            "example": {
                "plan": "personal",
                "intel_access": False,
                "calls_this_month": 148,
                "customer_id": "cus_QexampleID",
                "email": "dev@acme.com",
                "active": True,
            },
        },
        "errors": {"401": "The API key is missing, invalid or inactive."},
    },
    {
        "path": "/v1/siem/configure",
        "price_cents": 0,
        "tag": "Account",
        "summary": "Register a SIEM or SOAR push destination",
        "description": (
            "Free and unmetered. Configure one destination and real-time findings from breach, "
            "domain, infostealer, SIM swap, OAuth and dark-web-channel monitoring dispatch to it "
            "automatically, with no polling. Send a body with neither `format` nor `url` to "
            "disable delivery."
        ),
        "request": {
            "props": {
                "format": {
                    "type": "string",
                    "enum": ["splunk_hec", "cef", "xsoar_webhook"],
                    "description": "Wire format. `splunk_hec` for Splunk HTTP Event Collector, `cef` for QRadar and other CEF consumers, `xsoar_webhook` for Cortex XSOAR's Generic Webhook incident shape.",
                },
                "url": _str("Destination URL. Must be http:// or https://.", format="uri"),
                "auth_token": _str("Token sent to the destination, e.g. a Splunk HEC token. Optional."),
                "enabled": _bool("Whether delivery is active. Defaults to true."),
            },
            "any_of": ["format", "url"],
            "example": {"format": "splunk_hec", "url": "https://splunk.example.com:8088/services/collector", "auth_token": "your-hec-token", "enabled": True},
        },
        "response": {
            "props": {
                "format": _str("The registered format. Absent on a clear."),
                "url": _str("The registered URL. Absent on a clear."),
                "enabled": _bool("Whether delivery is active. Absent on a clear."),
                "status": {"type": "string", "enum": ["registered", "cleared"], "description": "`cleared` when the body carried neither format nor url."},
            },
            "example": {"format": "splunk_hec", "url": "https://splunk.example.com:8088/services/collector", "enabled": True, "status": "registered"},
        },
        "errors": {
            "400": "`format` is not one of the three supported values, `url` is not an http:// or https:// URL, or the API key has no account email on file.",
            "500": "Storing the destination failed.",
        },
        "notes": "The destination is keyed on the account email behind your API key, so one destination is held per account, not per key.",
    },
    {
        "path": "/v1/webhook/configure",
        "price_cents": 0,
        "tag": "Account",
        "summary": "Register a webhook for pushed findings",
        "description": (
            "Free and unmetered. Registers one URL to receive findings (breach, infostealer, "
            "session hijack, ransomware victim listing, asset-intel matches) as they are detected, "
            "instead of polling. Post an empty `webhook_url` to clear the registration."
        ),
        "request": {
            "props": {
                "webhook_url": _str("An `https://` URL to receive findings. Send an empty string to clear.", format="uri"),
            },
            "required": ["webhook_url"],
            "example": {"webhook_url": "https://hooks.example.com/relayshield"},
        },
        "response": {
            "props": {
                "webhook_url": _str("The registered URL, or an empty string after clearing."),
                "status": {"type": "string", "enum": ["registered", "cleared"], "description": "`cleared` when an empty URL was posted."},
            },
            "example": {"webhook_url": "https://hooks.example.com/relayshield", "status": "registered"},
        },
        "errors": {
            "400": "`webhook_url` is non-empty but is not an http:// or https:// URL.",
            "500": "Storing the registration failed.",
        },
        "notes": (
            "Delivery is best-effort and fired inline with the originating call under a 6-second "
            "budget. A slow or failing endpoint never fails the API call that triggered it, so do "
            "not treat the webhook as a guaranteed-delivery channel -- poll for anything you must "
            "not miss."
        ),
    },
]


# ---------------------------------------------------------------------------
# Spec assembly
# ---------------------------------------------------------------------------

_ERROR_SCHEMA_REF = {"$ref": "#/components/schemas/Error"}

_STANDARD_ERROR_TEXT = {
    "400": "Invalid request. The `error` string names the offending field.",
    "401": "Missing or invalid API key.",
    "402": "No credits and no active subscription. The response carries `topup_url`.",
    "404": "Unknown endpoint.",
    "405": "Wrong HTTP method. Every endpoint is POST.",
    "413": "Request payload too large.",
    "429": "Upstream rate limit reached. Retry after a short delay.",
    "500": "Internal error.",
    "502": "An upstream data provider was unavailable.",
}


def _operation(ep):
    metered = ep["path"].startswith("/v1/metered/")
    # Derived from the whole path, not the last segment: /v1/siem/configure and
    # /v1/webhook/configure both end in "configure", and a duplicate
    # operationId makes the document fail 3.1 validation outright.
    op_id = ep["path"].removeprefix("/v1/").replace("/", "_").replace("-", "_")

    req_schema = {
        "type": "object",
        "properties": ep["request"]["props"],
        # Deliberately NOT additionalProperties: false. The handlers read
        # parameters with params.get() and ignore anything they do not
        # recognise, so an unknown field is accepted, not rejected. Declaring
        # it forbidden would be a constraint we do not actually enforce -- and
        # a generated strict client would start rejecting requests the API
        # would have served.
    }
    if ep["request"].get("required"):
        req_schema["required"] = ep["request"]["required"]
    if ep["request"].get("any_of"):
        # Stated in the description rather than as `anyOf: [{required: [x]}, ...]`.
        # Those branches carry no `type`, so swagger-ui renders the whole body
        # as "object | (any | any)" with an empty "Any of" block -- actively
        # confusing on the one page whose job is to make parameters obvious.
        # The handler enforces this with its own 400, documented below.
        fields = ep["request"]["any_of"]
        req_schema["description"] = "At least one of: " + ", ".join(f"`{f}`" for f in fields) + "."
    if ep["request"].get("body_note"):
        req_schema["description"] = ep["request"]["body_note"]

    data_schema = {"type": "object", "properties": ep["response"]["props"]}

    description = ep["description"]
    if metered and ep.get("no_credit_check"):
        # These endpoints are served by the isolated agentic Lambda, which
        # meters on success but performs no pre-call credit check. Saying
        # "charged against prepaid credits" here would be wrong, and promising
        # a 402 that can never fire would be worse.
        price = f"${ep['price_cents'] / 100:.2f}"
        description += (
            f"\n\n**Billing.** {price} per successful call, metered to your card. Failed calls are "
            "never billed. Threat Intelligence subscribers and AWS Marketplace bundle customers "
            "call this at no extra charge. Unlike the other metered endpoints this one does not "
            "check a prepaid credit balance before running, so it never returns `402`."
        )
    elif metered:
        price = f"${ep['price_cents'] / 100:.2f}"
        description += (
            f"\n\n**Billing.** {price} per successful call. Failed calls are never billed. "
            "Charged against prepaid credits when the balance covers it, otherwise metered to "
            "your card. Threat Intelligence subscribers and AWS Marketplace bundle customers "
            "call this at no extra charge."
        )
    else:
        description += "\n\n**Billing.** Free. This endpoint is not metered."
    if ep.get("notes"):
        description += "\n\n**Note.** " + ep["notes"]

    responses = {
        "200": {
            "description": "Success. `ok` is true and `data` holds the result.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["ok", "data"],
                        "properties": {
                            "ok": {"type": "boolean", "const": True},
                            "data": data_schema,
                        },
                    },
                    "example": {"ok": True, "data": ep["response"]["example"]},
                }
            },
        }
    }

    # Endpoint-specific errors first, then the ones every route can return.
    codes = dict(ep.get("errors") or {})
    if metered:
        codes.setdefault("401", _STANDARD_ERROR_TEXT["401"])
        if not ep.get("no_credit_check"):
            codes.setdefault("402", _STANDARD_ERROR_TEXT["402"])
    codes.setdefault("405", _STANDARD_ERROR_TEXT["405"])

    for code in sorted(codes):
        example_error = {"ok": False, "error": codes[code]}
        if code == "402":
            example_error = {
                "ok": False,
                "error": "Insufficient credits and no active subscription.",
                "topup_url": "https://api.relayshield.net/developer/topup",
            }
        responses[code] = {
            "description": codes[code],
            "content": {"application/json": {"schema": _ERROR_SCHEMA_REF, "example": example_error}},
        }

    op = {
        "operationId": op_id,
        "summary": ep["summary"],
        "description": description,
        "tags": [ep["tag"]],
        # Per-endpoint, not global: the agentic Lambda accepts X-API-Key as
        # well as X-RS-API-KEY but does NOT accept Authorization: Bearer, so
        # advertising Bearer on those two would hand a caller a 401.
        "security": [{s: []} for s in ep.get("auth", ["ApiKeyAuth", "BearerAuth"])],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": req_schema, "example": ep["request"]["example"]}},
        },
        "responses": responses,
    }
    if metered:
        op["x-price-usd"] = round(ep["price_cents"] / 100, 2)
        op["x-billing-unit"] = "call"
    return {"post": op}



# ---------------------------------------------------------------------------
# x402 pay-per-call surface (/v1/payg/*)
#
# These are the same checks as the metered routes, paid per call in USDC over
# x402 instead of with an API key. They are documented here because the
# discovery-spec requirement for registries such as x402scan is an OpenAPI
# document carrying `x-payment-info` on every payable operation. Before this
# existed the published spec had 32 operations, ALL of them `/v1/metered`, and
# `x-payment-info` appeared nowhere -- the x402 surface the agent audience
# actually cares about was undocumented.
#
# Every schema, example and price below was harvested from the LIVE 402
# challenges on 2026-08-06, not hand-written, and every price was cross-checked
# against `PAYG_PRICE_UNITS` in relayshield_api.py with zero mismatches.
#
# `price_units` here is a FALLBACK only. `build_spec()` takes the live price
# table from relayshield_api.py as an argument, so the served document cannot
# drift from what the 402 challenge actually charges. The two agentic paths
# (`mcp-registry-risk`, `prompt-injection-breach`) are priced in
# relayshield_agentic_api.py, a separate Lambda that this one does not import,
# so those two fall back to the values below.
# ---------------------------------------------------------------------------

PAYG_ENDPOINTS: dict[str, dict] = {
    '/v1/payg/breach': {
        'summary': 'Check an email address against known data breaches',
        'description': 'Check whether an email address appears in known data breaches. Returns breach count, source names, dates, and exposed data types (passwords, emails, etc). Call before trusting a new user identity or granting elevated access.',
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string', 'description': 'Email address to check'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True,
 'data': {'email': 'user@example.com',
          'breach_count': 3,
          'breaches': [{'name': 'ExampleBreach',
                        'domain': 'example.com',
                        'breach_date': '2023-06-01',
                        'data_classes': ['Passwords', 'Email addresses'],
                        'is_verified': True}]}},
    },
    '/v1/payg/bulk-identity-risk': {
        'summary': 'Score up to 10 organisations and their agent identities',
        'description': 'Score up to 10 organizational domains, each with up to 5 associated agent/employee emails, for combined breach/infostealer/session/CVE risk in one call. Built for enterprise AI-governance platforms scoring many identities per customer in one pass, the recommended entry point for agent-governance and identity-posture integrations.',
        'price_units': 2000000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'targets': {'type': 'array',
                            'description': 'Up to 10 domains, each with up to 5 agent emails',
                            'items': {'type': 'object',
                                      'properties': {'domain': {'type': 'string'},
                                                     'agents': {'type': 'array',
                                                                'items': {'type': 'string'}}},
                                      'required': ['domain']}}},
 'required': ['targets']},
        'example': {'targets': [{'domain': 'acme.com', 'agents': ['ceo@acme.com']}]},
        'output_example': {'ok': True,
 'data': {'queried': 1,
          'critical_count': 0,
          'high_count': 0,
          'results': [{'domain': 'acme.com',
                       'domain_score': 10,
                       'domain_grade': 'A',
                       'agent_count': 1}]}},
    },
    '/v1/payg/cert-expiry': {
        'summary': 'Check TLS certificate expiry from CT logs',
        'description': "Check how many days remain before a domain's TLS certificate expires, via Certificate Transparency logs. Call to catch a lapsing certificate before it causes an outage, especially relevant as CA/Browser Forum rules shrink standard certificate lifespans toward 47 days by 2029.",
        'price_units': 50000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string',
                           'description': 'Domain to check TLS certificate expiry for'}},
 'required': ['domain']},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domain': 'acme.com',
          'cert_found': True,
          'expires_at': '2026-09-05T00:00:00+00:00',
          'days_remaining': 46,
          'risk_level': 'MEDIUM',
          'issued_at': '2026-06-07T00:00:00+00:00',
          'recommendation': 'Certificate renews in 46 days, no action needed yet, but confirm '
                            'your renewal automation is configured.'}},
    },
    '/v1/payg/domain': {
        'summary': 'Scan a domain for active phishing lookalikes',
        'description': "Scan a domain for phishing lookalikes: typosquats, homoglyphs, and common phishing registration patterns. Returns matched lookalike domains found in the wild. Call to detect brand-impersonation phishing campaigns targeting a company before they're reported elsewhere.",
        'price_units': 500000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string',
                           'description': 'Root domain to scan for lookalikes'}},
 'required': ['domain']},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domain': 'acme.com',
          'lookalikes_found': 2,
          'lookalikes': [{'domain': 'acrne.com'}, {'domain': 'acme-login.com'}],
          'candidates_checked': 30,
          'checked_at': '2026-05-19T10:00:00+00:00'}},
    },
    '/v1/payg/identity-graph': {
        'summary': 'Correlate an email to phones and domains seen alongside it',
        'description': 'Correlate an email address against the criminal breach/stealer corpus to surface linked phone numbers, secondary domains, and other identifiers tied to the same compromised identity. Call to map the blast radius of a known compromise across an organization.',
        'price_units': 350000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string',
                          'description': 'Email address to correlate against the criminal dump '
                                         'corpus'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True,
 'data': {'email': 'user@example.com',
          'found': False,
          'correlated_identifiers': 0,
          'correlated_phones': [],
          'correlated_domains': [],
          'sources': []}},
    },
    '/v1/payg/identity-risk-score': {
        'summary': 'Score a domain 0-100 across six identity dimensions',
        'description': 'Return a 0-100 domain security score across 6 identity-risk dimensions (breach exposure, infostealer density, ransomware exposure, session exposure, CVE exposure, threat-actor targeting) with a letter grade and plain-English risk factors. Call as a single-number identity health check before onboarding, financing, or partnering with a domain.',
        'price_units': 350000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string', 'description': 'Root domain to score'}},
 'required': ['domain']},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domain': 'acme.com',
          'risk_score': 10,
          'risk_level': 'LOW',
          'grade': 'A',
          'dimension_scores': {'breach_exposure': 5,
                               'infostealer_density': 0,
                               'threat_actor_targeting': 0,
                               'ransomware_exposure': 0,
                               'session_exposure': 0,
                               'cve_exposure': 5},
          'max_score': 100,
          'risk_factors': ['Breach exposure: 1 known breach event(s), 50,000 accounts '
                           'affected'],
          'summary': 'Domain acme.com scores 10/100 (A, LOW) across 2 of 6 monitored identity '
                     'signal dimensions.'}},
    },
    '/v1/payg/infostealer': {
        'summary': 'Check an email address against infostealer malware logs',
        'description': "Check whether an email address's credentials were harvested by infostealer malware and appear in a criminal stealer-log marketplace, detected 24-72 hours ahead of public breach databases. Call to catch device-level compromise before stolen session cookies or saved passwords are used for account takeover.",
        'price_units': 150000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string',
                          'description': 'Email address to check for infostealer compromise'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True,
 'data': {'email': 'user@example.com', 'found': False, 'stealer_count': 0, 'stealers': []}},
    },
    '/v1/payg/ip-intel': {
        'summary': 'Passive DNS and reputation for a domain or IP',
        'description': 'Look up passive DNS resolution history and reputation for a domain or IP address. For a domain: which IPs it has resolved to over time. For an IP: which hostnames have resolved to it, plus malicious/suspicious vendor detection counts. Call to pivot from an indicator to its infrastructure history during an investigation.',
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string',
                           'description': 'Domain to look up (returns reputation + passive DNS '
                                          'resolution history)'},
                'ip': {'type': 'string',
                       'description': 'Alternative: IP address to look up (returns reputation '
                                      '+ reverse passive DNS)'}}},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'queried': 'acme.com',
          'query_type': 'domain',
          'reputation': 0,
          'malicious_votes': 0,
          'suspicious_votes': 0,
          'resolutions': [{'ip_address': '93.184.216.34',
                           'date': '2026-06-01T00:00:00+00:00'}]}},
    },
    '/v1/payg/llm-credential-exposure': {
        'summary': 'Find exposed LLM and AI provider API keys',
        'description': "Check whether a domain's LLM/AI provider API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate) appear exposed in criminal stealer logs. This is LLMjacking, a fast-growing threat where a leaked key becomes a live, uncapped billing liability rather than just a data exposure. Call to catch an exposed key before the drain, not after the invoice.",
        'price_units': 400000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string', 'description': 'Your own domain'},
                'vendor_domains': {'type': 'array',
                                   'items': {'type': 'string'},
                                   'description': 'Optional: vendor/supply-chain domains, up '
                                                  'to 10'}}},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domains_checked': 1,
          'found': False,
          'findings': [],
          'highest_severity': None,
          'providers_affected': []}},
    },
    '/v1/payg/mcp-registry-risk': {
        'summary': 'Check an MCP server or package for registry risk',
        'description': 'Assess an MCP server URL for supply-chain and registry risk before your agent connects to it or grants it tool-calling access: flags unverified publishers, known-malicious servers, and other trust signals. Call before an autonomous agent adds a new MCP server to its toolset.',
        'price_units': 350000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'server_url': {'type': 'string',
                               'description': 'URL of the MCP server to assess for '
                                              'registry/supply-chain risk'}},
 'required': ['server_url']},
        'example': {'server_url': 'https://example-mcp-server.com'},
        'output_example': {'ok': True, 'data': {'verdict': 'LOW', 'findings': []}},
    },
    '/v1/payg/nft-security': {
        'summary': 'Screen an NFT contract for known scam, wash-trading, or malicious-approval risk signals before your agent buys, bids on, or approves it',
        'description': 'Screen an NFT contract for known scam, wash-trading, or malicious-approval risk signals before your agent buys, bids on, or approves it. Returns risk level and risk flags plus basic collection metadata. Call before an autonomous agent interacts with an unfamiliar NFT contract.',
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'contract_address': {'type': 'string', 'description': 'NFT contract address'},
                'chain_id': {'type': 'string',
                             'description': 'EVM chain ID (default: 1 for Ethereum)'}},
 'required': ['contract_address']},
        'example': {'contract_address': '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d', 'chain_id': '1'},
        'output_example': {'ok': True,
 'data': {'contract_address': '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d',
          'chain_id': '1',
          'risk_level': 'LOW',
          'risk_flags': [],
          'nft_name': 'Bored Ape Yacht Club',
          'nft_symbol': 'BAYC',
          'raw': {}}},
    },
    '/v1/payg/nhi-exposure': {
        'summary': 'Find machine credentials in stealer logs',
        'description': 'Check whether API keys or tokens tied to a domain, used by non-human identities like AI agents, service accounts, or CI/CD, appear exposed in criminal stealer logs. Call to audit whether the credentials an autonomous agent relies on have already been compromised upstream.',
        'price_units': 400000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string', 'description': 'Your own domain'},
                'vendor_domains': {'type': 'array',
                                   'items': {'type': 'string'},
                                   'description': 'Optional: vendor/supply-chain domains, up '
                                                  'to 10'}}},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domains_checked': 1, 'found': False, 'findings': [], 'highest_severity': None}},
    },
    '/v1/payg/oauth-watchlist': {
        'summary': 'Find exposed OAuth tokens and SaaS credentials',
        'description': 'Check whether an email address has OAuth-connected app credentials exposed in a known SaaS breach (GitHub, Slack, Notion, Zapier, and 30+ other high-risk OAuth-capable apps). Returns matched apps and direct revoke-access links. Call to detect supply-chain credential exposure via connected apps.',
        'price_units': 300000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string',
                          'description': 'Email address to check for OAuth exposure'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True,
 'data': {'email': 'user@example.com',
          'matched_count': 1,
          'matched_apps': [{'app': 'GitHub',
                            'breach_date': '2023-01-15',
                            'data_classes': ['Usernames', 'Email addresses'],
                            'revoke_url': 'https://github.com/settings/applications'}],
          'recommendation': 'Revoke OAuth access for matched apps immediately.',
          'checked_at': '2026-05-19T10:00:00+00:00'}},
    },
    '/v1/payg/prompt-injection-breach': {
        'summary': 'Find exposure from breaches that look AI-agent-sourced',
        'description': "Check whether an email address tied to an AI agent session has an active stolen session or credential exposure that could enable a prompt-injection-driven account takeover. Call to audit whether an agent's own session integrity has already been compromised upstream, not just what the agent is being asked to do.",
        'price_units': 350000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string',
                          'description': 'Email address to check for agent-session compromise '
                                         'from a prompt-injection-driven breach'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True, 'data': {'found': False, 'session_count': 0}},
    },
    '/v1/payg/ransomware-risk': {
        'summary': 'Check a domain against ransomware leak sites',
        'description': "Check whether a domain appears on a known ransomware group's victim/leak-site list, and whether pre-ransomware credential harvesting was detected beforehand. Call to assess active ransomware exposure for a domain, not just historical breach history.",
        'price_units': 400000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string',
                           'description': 'Domain to check against the ransomware victim '
                                          'list'}},
 'required': ['domain']},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domain': 'acme.com', 'on_victim_list': False, 'pre_ransomware_credential_count': 0}},
    },
    '/v1/payg/scan-file': {
        'summary': "Scan a file (via its public download URL) for malware using VirusTotal's multi-engine analysis",
        'description': "Scan a file (via its public download URL) for malware using VirusTotal's multi-engine analysis. Returns an async analysis ID to poll. Call before an agent downloads, opens, or executes a file attachment from an untrusted source.",
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'file_url': {'type': 'string',
                             'description': 'Publicly accessible download URL'},
                'filename': {'type': 'string',
                             'description': 'Optional filename hint for AV engines'}},
 'required': ['file_url']},
        'example': {'file_url': 'https://cdn.example.com/invoice.pdf', 'filename': 'invoice.pdf'},
        'output_example': {'ok': True,
 'data': {'status': 'pending',
          'target': 'https://cdn.example.com/invoice.pdf',
          'filename': 'invoice.pdf',
          'analysis_id': 'f-abc123def456',
          'poll_endpoint': '/v1/result/f-abc123def456',
          'note': 'Poll /v1/result/{analysis_id} every 5s until status is completed'}},
    },
    '/v1/payg/scan-url': {
        'summary': 'Scan a URL for phishing or malware using heuristic signals (Google Safe Browsing, RDAP domain age, known IOC corpus) plus VirusTotal multi-engine analysis',
        'description': 'Scan a URL for phishing or malware using heuristic signals (Google Safe Browsing, RDAP domain age, known IOC corpus) plus VirusTotal multi-engine analysis. Returns an async analysis ID to poll. Call before an agent clicks, fetches, or shares a link from an untrusted source.',
        'price_units': 50000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'url': {'type': 'string',
                        'description': 'URL to scan (must start with http:// or https://)'}},
 'required': ['url']},
        'example': {'url': 'https://suspicious-site.example.com'},
        'output_example': {'ok': True,
 'data': {'status': 'pending',
          'target': 'https://suspicious-site.example.com',
          'analysis_id': 'u-abc123def456',
          'poll_endpoint': '/v1/result/u-abc123def456',
          'note': 'Poll /v1/result/{analysis_id} every 5s until status is completed'}},
    },
    '/v1/payg/scan-wallet': {
        'summary': 'Screen an EVM wallet address for known scam, exploit, or sanctions-list association before your agent transacts with it',
        'description': 'Screen an EVM wallet address for known scam, exploit, or sanctions-list association before your agent transacts with it. Returns a risk level and specific risk flags. Call before an autonomous agent sends funds to or interacts with an unfamiliar wallet.',
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'address': {'type': 'string',
                            'description': 'EVM wallet address (0x + 40 hex chars)'},
                'chain_id': {'type': 'string',
                             'description': 'EVM chain ID: 1=ETH, 8453=Base, 137=Polygon'}},
 'required': ['address']},
        'example': {'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045', 'chain_id': '1'},
        'output_example': {'ok': True,
 'data': {'address': '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',
          'chain_id': '1',
          'risk_level': 'LOW',
          'risk_flags': [],
          'raw': {}}},
    },
    '/v1/payg/secret-scan': {
        'summary': 'Find published secrets across six public artifact sources',
        'description': 'Scan public GitHub repositories, npm and PyPI packages, Docker Hub images, Hugging Face models and Spaces, and Postman public workspaces and collections for API keys, tokens and credentials already published against a domain. Repo-only scanners miss credentials shipped inside released packages and images. Every hit is verified against the credential pattern before it is reported.',
        'price_units': 350000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string', 'description': 'Your own domain'},
                'vendor_domains': {'type': 'array',
                                   'items': {'type': 'string'},
                                   'description': 'Optional: vendor domains, up to 5'}}},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domains_checked': 1, 'found': False, 'findings': [], 'highest_severity': None}},
    },
    '/v1/payg/secret-scan-text': {
        'summary': 'Scan supplied text or a diff for secrets',
        'description': '',
        'price_units': 50000,
        'x402_version': 1,
        'body': {'type': 'object',
 'properties': {'content': {'type': 'string',
                            'description': 'Raw file content to scan. Mutually exclusive with '
                                           '`diff`.'},
                'diff': {'type': 'string',
                         'description': 'Unified diff. Only added lines are scanned. Mutually '
                                        'exclusive with `content`.'},
                'filename': {'type': 'string',
                             'description': 'Optional filename, echoed on each finding as '
                                            '`file`. Used with `content`.'}}},
        'example': {'diff': '--- a/config.py\n'
         '+++ b/config.py\n'
         '@@ -1,2 +1,3 @@\n'
         ' import os\n'
         '+AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'},
        'output_example': {'ok': True, 'data': {}},
    },
    '/v1/payg/session-risk': {
        'summary': 'Detect stolen session cookies before they are used',
        'description': 'Check whether an email address has an active stolen session cookie circulating in a criminal archive, a signal of account takeover that bypasses password resets and 2FA entirely. Call to detect AiTM/session-hijack attacks before an authenticated agent session is trusted.',
        'price_units': 300000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'email': {'type': 'string',
                          'description': 'Email address to check for active session/AiTM '
                                         'exposure'}},
 'required': ['email']},
        'example': {'email': 'user@example.com'},
        'output_example': {'ok': True,
 'data': {'email': 'user@example.com',
          'found': False,
          'session_count': 0,
          'highest_severity': None,
          'sessions': []}},
    },
    '/v1/payg/sim-swap': {
        'summary': 'Detect a recent SIM swap or carrier port',
        'description': 'Check whether a phone number has had a SIM swap or carrier port in the last 24 hours via real-time carrier lookup. A recent swap is a strong signal of an active account-takeover attempt targeting SMS-based 2FA. Call before trusting an SMS OTP from this number.',
        'price_units': 250000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'phone': {'type': 'string', 'description': 'Phone number in E.164 format'}},
 'required': ['phone']},
        'example': {'phone': '+14155551234'},
        'output_example': {'ok': True,
 'data': {'phone': '+14155551234',
          'swapped': True,
          'swap_timestamp': '2026-05-18T14:23:00Z',
          'carrier': 'T-Mobile',
          'checked_at': '2026-05-19T10:00:00+00:00'}},
    },
    '/v1/payg/supply-chain': {
        'summary': 'Assess breach and infostealer risk across vendors',
        'description': 'Check up to 10 vendor domains for combined breach, infostealer, and dark-web risk exposure in one call. Returns a composite risk score per vendor. Call to assess third-party API/vendor risk before an agent integrates with or continues calling an external service.',
        'price_units': 100000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'vendor_domains': {'type': 'array',
                                   'items': {'type': 'string'},
                                   'description': 'Up to 10 vendor domains'},
                'vendor_emails': {'type': 'array',
                                  'items': {'type': 'string'},
                                  'description': 'Alternative: vendor contact emails, domain '
                                                 'extracted automatically'}}},
        'example': {'vendor_domains': ['acme.com', 'vendor2.com']},
        'output_example': {'ok': True,
 'data': {'domains_checked': 1,
          'highest_risk': 'LOW',
          'results': [{'domain': 'acme.com',
                       'risk_level': 'LOW',
                       'breach_count': 0,
                       'infostealer_found': False}]}},
    },
    '/v1/payg/target-risk': {
        'summary': 'Score how likely a domain is to be targeted',
        'description': "Score a domain's probability of being an active or upcoming cyberattack target using a 6-signal correlation model (breach, infostealer, ransomware, session, CVE, and threat-actor targeting history). Call for proactive risk triage, not just after-the-fact breach checking.",
        'price_units': 500000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'domain': {'type': 'string', 'description': 'Domain to score (e.g. acme.com)'}},
 'required': ['domain']},
        'example': {'domain': 'acme.com'},
        'output_example': {'ok': True,
 'data': {'domain': 'acme.com',
          'target_risk_score': 0,
          'probability_tier': 'LOW',
          'signals': []}},
    },
    '/v1/payg/tech-stack-cve': {
        'summary': 'Find CVEs actively targeting your declared stack',
        'description': 'Check a declared technology stack (e.g. nginx, WordPress, Cisco IOS) against actively-exploited CVEs (CISA KEV) and high-EPSS-score vulnerabilities. Call before deploying or continuing to run a given technology stack in production.',
        'price_units': 200000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'tech_stack': {'type': 'array',
                               'items': {'type': 'string'},
                               'description': 'Declared technology product names'},
                'domain': {'type': 'string',
                           'description': 'Alternative: pull tech_stack from a stored user '
                                          'profile by domain'}}},
        'example': {'tech_stack': ['nginx', 'wordpress', 'cisco ios']},
        'output_example': {'ok': True, 'data': {'tech_stack_queried': ['nginx'], 'matched_cves': [], 'critical_count': 0}},
    },
    '/v1/payg/token-security': {
        'summary': 'Screen an ERC-20/BEP-20 token contract for honeypot, mintable-supply, hidden-owner, and other rug-pull risk signals before your agent trades it',
        'description': 'Screen an ERC-20/BEP-20 token contract for honeypot, mintable-supply, hidden-owner, and other rug-pull risk signals before your agent trades it. Returns risk level, specific critical/warning flags, and basic token metadata. Call before an autonomous trading agent buys or approves spending on an unfamiliar token.',
        'price_units': 50000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'contract_address': {'type': 'string',
                                     'description': 'EVM token contract address'},
                'chain_id': {'type': 'string',
                             'description': 'EVM chain ID (default: 1 for Ethereum)'}},
 'required': ['contract_address']},
        'example': {'contract_address': '0x6982508145454ce325ddbe47a25d4ec3d2311933', 'chain_id': '1'},
        'output_example': {'ok': True,
 'data': {'contract_address': '0x6982508145454ce325ddbe47a25d4ec3d2311933',
          'chain_id': '1',
          'risk_level': 'HIGH',
          'critical_flags': ['honeypot'],
          'warning_flags': ['mintable supply'],
          'token_name': 'Example Token',
          'token_symbol': 'EXT',
          'holder_count': '12345',
          'raw': {}}},
    },
    '/v1/payg/wallet-risk': {
        'summary': 'Screen a wallet address across EVM, Solana, TON, or Bitcoin for known scam, exploit, drainer, or sanctions-list association before your agent transacts with it',
        'description': 'Screen a wallet address across EVM, Solana, TON, or Bitcoin for known scam, exploit, drainer, or sanctions-list association before your agent transacts with it. Returns a risk level and specific risk flags. The recommended first call for any autonomous trading or DeFi agent before interacting with a new counterparty wallet.',
        'price_units': 50000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'address': {'type': 'string',
                            'description': 'Wallet address: EVM (0x), Solana (base58), TON '
                                           '(EQ.../UQ...), or Bitcoin'}},
 'required': ['address']},
        'example': {'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'},
        'output_example': {'ok': True,
 'data': {'address': '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',
          'chain': 'evm',
          'risk_level': 'LOW',
          'risk_flags': [],
          'metadata': {}}},
    },
    '/v1/payg/wallet-screen-batch': {
        'summary': 'Screen up to 10 wallet addresses (any chain: EVM, Solana, TON, Bitcoin) for known scam or exploit association in a single call',
        'description': 'Screen up to 10 wallet addresses (any chain: EVM, Solana, TON, Bitcoin) for known scam or exploit association in a single call. Returns per-address risk level and flags. Use for bulk counterparty screening in trading or portfolio-monitoring agent workflows.',
        'price_units': 500000,
        'x402_version': 2,
        'body': {'type': 'object',
 'properties': {'addresses': {'type': 'array',
                              'items': {'type': 'string'},
                              'maxItems': 10,
                              'description': 'Up to 10 wallet addresses (any chain: EVM, '
                                             'Solana, TON, Bitcoin)'}},
 'required': ['addresses']},
        'example': {'addresses': ['0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
               '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM']},
        'output_example': {'ok': True,
 'data': {'screened': 2,
          'high_risk': 0,
          'results': [{'address': '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',
                       'chain': 'evm',
                       'risk_level': 'LOW',
                       'risk_flags': [],
                       'error': None},
                      {'address': '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM',
                       'chain': 'solana',
                       'risk_level': 'LOW',
                       'risk_flags': [],
                       'error': None}]}},
    },
}

_PAYG_TAG = "x402 pay-per-call"

_PAYG_DESCRIPTION_SUFFIX = """

**Billing.** {price} in USDC per call over x402, on Base or Solana. No API key, no signup and no
subscription. Send the request with no payment header, take the `402` challenge that comes back,
pay it, and repeat the request. Only successful calls are charged.
"""


def _payg_operation(path, ep, price_units):
    """Build the operation for one x402 pay-per-call route.

    Kept separate from `_operation` rather than folded into it: these routes
    carry no `security` at all, and conflating "no auth" with "auth optional"
    is the kind of thing that makes a generated client send an empty API key
    header and get a confusing answer.
    """
    op_id = "payg_" + path.removeprefix("/v1/payg/").replace("-", "_")
    price_usd = round(price_units / 1_000_000, 6)
    price_str = f"${price_usd:.2f}"

    req_schema = dict(ep["body"] or {"type": "object", "properties": {}})

    responses = {
        "200": {
            "description": "Payment settled and the check ran. `ok` is true and `data` holds the result.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["ok", "data"],
                        "properties": {"ok": {"type": "boolean", "const": True},
                                       "data": {"type": "object"}},
                    },
                    "example": ep["output_example"],
                }
            },
        },
        "400": {
            "description": "A required field is missing or malformed. Never billed.",
            "content": {"application/json": {"schema": _ERROR_SCHEMA_REF,
                                             "example": {"ok": False, "error": "address is required"}}},
        },
        # The 402 is the point of this surface, not an error path. It is the
        # payment challenge an x402 client is expected to receive, pay and retry.
        "402": {
            "description": (
                f"Payment required. The body carries a complete x402 version {ep['x402_version']} "
                "challenge with the accepted networks, the amount in USDC base units, and the "
                "recipient. Pay it and repeat the request with the payment header."
            ),
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["ok", "error", "x402"],
                        "properties": {
                            "ok": {"type": "boolean", "const": False},
                            "error": {"type": "string", "const": "Payment required"},
                            "price": _str("Human-readable price, e.g. `$0.05 USDC (Base or Solana)`."),
                            "x402": _obj(
                                "The x402 payment challenge.",
                                {
                                    "x402Version": _int("Protocol version of this challenge."),
                                    "resource": _obj("What is being paid for.", {}),
                                    "accepts": _arr("One entry per accepted network.", {"type": "object"}),
                                    "extensions": _obj("Discovery metadata, including the Bazaar input and output schemas.", {}),
                                },
                            ),
                        },
                    },
                    "example": {
                        "ok": False,
                        "error": "Payment required",
                        "price": f"{price_str} USDC (Base or Solana)",
                    },
                }
            },
        },
        "405": {
            "description": _STANDARD_ERROR_TEXT["405"],
            "content": {"application/json": {"schema": _ERROR_SCHEMA_REF,
                                             "example": {"ok": False, "error": _STANDARD_ERROR_TEXT["405"]}}},
        },
    }

    return {
        "post": {
            "operationId": op_id,
            "summary": ep["summary"],
            "description": ep["description"] + _PAYG_DESCRIPTION_SUFFIX.format(price=price_str),
            "tags": [_PAYG_TAG],
            # Explicitly empty: this route takes no credentials of any kind.
            "security": [],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": req_schema, "example": ep["example"]}},
            },
            "responses": responses,
            # The discovery contract registries read. `price` is structured
            # rather than a display string so an agent can compare offers
            # without parsing currency symbols out of prose.
            # x402scan's discovery spec is explicit that `currency` is "USD"
            # and `amount` is decimal USD, while the runtime x402 challenge
            # carries token atomic units. They are deliberately different
            # units, so both are published: `amount` for the registry, and
            # `amount_base_units` alongside it so nothing has to infer the
            # USDC conversion. Their fields are a superset of the IETF API
            # payment spec and do not collide.
            "x-payment-info": {
                "price": {"mode": "fixed", "currency": "USD", "amount": f"{price_usd:.2f}",
                          "amount_base_units": price_units, "asset": "USDC", "decimals": 6},
                "protocols": [{"x402": {}}],
                "networks": ["eip155:8453", "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"],
                "x402_version": ep["x402_version"],
                "payment_required_status": 402,
            },
            "x-price-usd": price_usd,
            "x-billing-unit": "call",
        }
    }

_TAG_DESCRIPTIONS = [
    ("Identity exposure", "Whether a person's credentials, sessions or payment cards are already circulating."),
    ("Domain and infrastructure", "Lookalike domains, certificate expiry, passive DNS and reputation."),
    ("Secrets and non-human identity", "API keys, tokens and machine credentials -- in your own artifacts and in criminal corpora."),
    ("Vendor and organisation risk", "Scoring an organisation, its vendors and its agent identities."),
    ("Threat intelligence", "Indicator enrichment, pivoting, actor attribution and CVE correlation."),
    ("Crypto", "Wallet address and token contract screening."),
    ("Agent and MCP security", "MCP server reputation and AI-agent-sourced breach exposure. These two authenticate slightly differently -- see each operation."),
    ("Account", "Free, unmetered endpoints for key validation and webhook delivery."),
    (_PAYG_TAG, "The same checks paid per call in USDC over x402, on Base or Solana. No API key and no signup: send the request, take the 402 challenge, pay it, repeat. Discoverable in the CDP Bazaar."),
]

_DESCRIPTION = """
Identity-compromise and threat-intelligence checks over a plain REST API. Every endpoint is
`POST`, takes a JSON body, and returns a JSON envelope.

## Authentication

Send your API key in either header. They are equivalent -- use whichever your HTTP client
handles more comfortably.

```
X-RS-API-KEY: rs_live_your_key_here
Authorization: Bearer rs_live_your_key_here
```

Header names are matched case-insensitively, so a client that normalises `X-RS-API-KEY` to
`X-Rs-Api-Key` still authenticates.

**One exception.** The two **Agent and MCP security** endpoints accept `X-RS-API-KEY` or
`X-API-Key`, and do **not** accept `Authorization: Bearer`. They are served by a separately
isolated backend. `X-RS-API-KEY` works everywhere, so use it and the distinction never matters.

Get a key at [api.relayshield.net/developers](https://api.relayshield.net/developers). AWS
Marketplace subscribers are provisioned a key automatically when the subscription activates.

## Response envelope

Every response, success or failure, is one of these two shapes:

```json
{ "ok": true,  "data": { } }
{ "ok": false, "error": "email is required and must be a valid address" }
```

Branch on the HTTP status code, or on `ok` -- they always agree. `error` is a human-readable
sentence naming the offending field; it is meant to be logged and read, not pattern-matched.

## Errors

| Status | Meaning | What to do |
|---|---|---|
| `400` | A required field is missing or malformed. | Fix the request. Retrying unchanged will fail identically. |
| `401` | API key missing, invalid, or deactivated. | Check the header name and the key value. |
| `402` | No credits and no active subscription. | Response carries `topup_url`. Add credits or subscribe. Not returned by the two Agent and MCP security endpoints, which do not check credits. |
| `404` | Unknown endpoint. | Check the path. Every metered route is under `/v1/metered/`. |
| `405` | Wrong method. | Every endpoint is `POST`, including those that take no parameters. |
| `413` | Payload too large. | Only `secret-scan-text` returns this, at 1 MiB. Split the batch. |
| `429` | An upstream provider rate-limited us. | Retry after a few seconds. Not billed. |
| `500` | Internal error. | Retry. If it persists, contact support with the timestamp. |
| `502` | An upstream data provider was unavailable. | Retry. Not billed. |

**Only successful calls are billed.** A `4xx` or `5xx` never deducts credits and never emits a
metering event, so a retry loop against a malformed request costs nothing but time.

## Rate limits

There is no fixed per-key request rate limit on metered endpoints; you are limited by credits or
subscription. Threat Intelligence Starter is capped at 10,000 calls/month (about 333/day);
Unlimited is uncapped. A `429` therefore reflects an upstream provider's limit, not ours.

## Timeouts and partial results

Several endpoints query many sources and are explicitly bounded in wall-clock time rather than
allowed to run long and be killed mid-flight. Where that applies, the response says so instead of
returning a shorter list that reads like a clean result -- `secret-scan` reports `coverage[].sources`,
and `domain` returns `null` enrichment fields for lookalikes it could not finish assessing. In this
API `null` means "not determined", never "clean".

## Conventions

- Emails and domains are lowercased and trimmed; a leading `www.` and any URL scheme are stripped.
- Phone numbers must be E.164 (`+14155551234`).
- Timestamps are ISO 8601 UTC.
- Severity is always one of `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`. Vendor risk adds `CLEAN`, and
  `oauth-watchlist` adds `NONE`.
- Risk scores run 0-100 where higher is worse.

## Other surfaces

The same corpus is also available as a STIX 2.1 / TAXII 2.1 feed at `/v1/intel/taxii/`, a
MISP-compatible REST surface at `/v1/intel/misp`, and an x402 pay-per-call surface under
`/v1/payg/` that needs no API key. Those are documented separately at
[api.relayshield.net/developers](https://api.relayshield.net/developers).
""".strip()


def build_spec(base_url="https://api.relayshield.net", payg_prices=None):
    """Return the complete OpenAPI 3.1 document as a dict.

    `payg_prices` is `PAYG_PRICE_UNITS` from relayshield_api.py, passed in by
    the caller rather than imported here because relayshield_api imports THIS
    module and the reverse import would be circular. Passing it in is what
    stops the published price drifting from the price the 402 challenge
    actually charges, which has been a real defect on other public surfaces.
    Paths absent from it (the two agentic routes, which live in a different
    Lambda) fall back to the table above.
    """
    paths = {}
    for ep in ENDPOINTS:
        paths[ep["path"]] = _operation(ep)
    for path, ep in PAYG_ENDPOINTS.items():
        price = (payg_prices or {}).get(path, ep["price_units"])
        paths[path] = _payg_operation(path, ep, price)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "RelayShield API",
            "version": SPEC_VERSION,
            "summary": "Identity-compromise and threat-intelligence checks for developers, MSPs and AI agents.",
            "description": _DESCRIPTION,
            "contact": {
                "name": "RelayShield Support",
                "email": "support@relayshield.net",
                "url": "https://api.relayshield.net/developers",
            },
            "termsOfService": "https://relayshield.carrd.co/terms",
            "x-guidance": (
                "Two ways to call this API. With an API key, every route under `/v1/metered/` is "
                "charged against prepaid credits or a subscription; get a key at "
                "https://api.relayshield.net/developers, and the first 20 calls are free. Without "
                "an API key, the same checks are under `/v1/payg/` and are paid per call in USDC "
                "over x402 on Base or Solana: send the request, take the `402` challenge, pay it, "
                "repeat. Agents should prefer `/v1/payg/`, which needs no signup and no key "
                "custody. Every endpoint is POST with a JSON body and returns "
                "`{ok, data}` or `{ok, error}`. Only successful calls are billed."
            ),
        },
        "servers": [{"url": base_url, "description": "Production"}],
        "tags": [{"name": n, "description": d} for n, d in _TAG_DESCRIPTIONS],
        "security": [{"ApiKeyAuth": []}, {"BearerAuth": []}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-RS-API-KEY",
                    "description": "Your RelayShield API key, e.g. `rs_live_...`.",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "The same API key sent as `Authorization: Bearer <key>`. Equivalent to "
                        "X-RS-API-KEY. Accepted everywhere except the two Agent and MCP security "
                        "endpoints, which take X-RS-API-KEY or X-API-Key only."
                    ),
                },
                "ApiKeyAuthAlt": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": (
                        "The same API key under an alternative header name, accepted only by the "
                        "Agent and MCP security endpoints. X-RS-API-KEY works there too and is the "
                        "spelling to prefer for consistency with the rest of the API."
                    ),
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "description": "Failure envelope. Returned for every non-2xx response.",
                    "required": ["ok", "error"],
                    "properties": {
                        "ok": {"type": "boolean", "const": False},
                        "error": _str("Human-readable description of what went wrong, naming the offending field where there is one."),
                        "topup_url": _str("Present only on 402. Where to add credits."),
                        "docs": _str("Present on 401. Link to the developer documentation."),
                    },
                },
            },
        },
        "paths": paths,
    }


# ---------------------------------------------------------------------------
# Rendered reference page
#
# Swagger UI loaded from its own CDN, which is what Zapier's reviewer pointed
# at (petstore.swagger.io) and what partner reviewers expect to be handed.
# Pinned to an exact version with SRI-free integrity by version pin only --
# unpkg serves immutable versioned paths.
# ---------------------------------------------------------------------------

_SWAGGER_VERSION = "5.17.14"

DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield API Reference</title>
<meta name="description" content="Full REST reference for the RelayShield API: request parameters, response attributes, error handling and live examples for every endpoint.">
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@__V__/swagger-ui.css">
<style>
  body { margin: 0; background: #fff; }
  .rs-header {
    background: #0b1220; color: #fff; padding: 18px 24px;
    font: 15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    display: flex; flex-wrap: wrap; gap: 16px; align-items: center; justify-content: space-between;
  }
  .rs-header a { color: #7fd1ff; text-decoration: none; }
  .rs-header a:hover { text-decoration: underline; }
  .rs-title { font-weight: 600; font-size: 17px; }
  .rs-links { display: flex; flex-wrap: wrap; gap: 18px; font-size: 14px; }
  .swagger-ui .topbar { display: none; }
  .swagger-ui .info { margin: 28px 0; }
</style>
</head>
<body>
<div class="rs-header">
  <span class="rs-title">RelayShield API Reference</span>
  <span class="rs-links">
    <a href="/developers">Get an API key</a>
    <a href="/openapi.json">openapi.json</a>
    <a href="/guides/microsoft-sentinel">Sentinel guide</a>
    <a href="/guides/elastic-security">Elastic guide</a>
    <a href="mailto:support@relayshield.net">support@relayshield.net</a>
  </span>
</div>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@__V__/swagger-ui-bundle.js" crossorigin></script>
<script src="https://unpkg.com/swagger-ui-dist@__V__/swagger-ui-standalone-preset.js" crossorigin></script>
<script>
window.onload = function () {
  window.ui = SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: "#swagger-ui",
    deepLinking: true,
    docExpansion: "list",
    // -1 hides the trailing "Schemas" section (every schema here is inline,
    // so it would only repeat itself). defaultModelExpandDepth is the
    // separate, singular setting for inline models: at its default of 1 every
    // field's description collapses behind an "Expand all" link, which buries
    // exactly the attribute documentation this page exists to show.
    defaultModelsExpandDepth: -1,
    defaultModelExpandDepth: 5,
    defaultModelRendering: "example",
    // Deliberately NOT tryItOutEnabled. With try-it-out on by default the
    // request body renders straight into an editable textarea and swagger-ui
    // hides the "Example Value / Schema" tabs -- which is exactly where a
    // reader looks to find out what parameters an endpoint takes. Off by
    // default shows the documented schema; the "Try it out" button is still
    // one click away on every operation.
    persistAuthorization: true,
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
    plugins: [SwaggerUIBundle.plugins.DownloadUrl],
    layout: "StandaloneLayout"
  });
};
</script>
</body>
</html>
""".replace("__V__", _SWAGGER_VERSION)
