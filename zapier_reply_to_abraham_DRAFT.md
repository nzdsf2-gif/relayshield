# DRAFT reply to Abraham D. — Zapier Developer Support

**SENT 2026-08-01 by founder. Live version is 1.0.5.**

The reply as sent referenced **1.0.5**. The first push had to be 1.0.4 (Zapier requires
sequential versions and 1.0.4 had never been uploaded), so 1.0.5 was pushed immediately after
with identical content to make the sent statement accurate. 1.0.4 remains as a harmless
intermediate. No correction email was needed.

Note the CLI package is `zapier-platform-cli`, not `zapier`:
`npx --yes zapier-platform-cli@latest push`

Version **1.0.5** (pushed 2026-08-01 03:06 UTC). `zapier validate`: 28 checks passed, 0 failed, 0 publishing warnings, 0 general
warnings.

---

Hi Abraham,

Thanks for the detailed review — that was genuinely useful, and one of the items pointed at a
real problem on our side rather than just a convention mismatch. All five are addressed in
version 1.0.5, which I've pushed.

**1 — Application API is documented**

Confirmed, and I found a gap while checking. The integration calls 14 endpoints. Twelve were
already documented at https://api.relayshield.net/developers, but two were not: `/v1/account/info`
(used by the authentication test) and `/v1/webhook/configure` (used by the New Security Alert
trigger). Both are now documented there with request and response shapes and working curl examples,
under "Account & integration endpoints". All 14 endpoints the integration uses are now covered.

**2 — Integration uses production APIs**
**3 — Developer owns or has permission to use all APIs**

These had the same root cause, and you were right to flag it. The integration was pointing at
`https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod` — the raw AWS API Gateway URL behind
our API. It is our production environment, but there is no way to tell that from the outside, which
is exactly why it read as both a staging environment and a third-party domain.

It now points at `https://api.relayshield.net`, our production custom domain, which resolves to the
same service. I verified all 14 endpoints route correctly on that hostname before switching.

On ownership: I'm the founder of RelayShield and own the API outright — it is our own service, not
a third-party API we're wrapping. `api.relayshield.net` and `relayshield.net` are both ours, and the
developer portal, documentation and API key issuance all run on that domain. Happy to provide any
further confirmation you need.

**4 — Integration requests authentication credentials appropriately**

The API key is only requested through the Authentication configuration — no trigger or action asks
for credentials. The field was declared as `type: 'string'`, so it wasn't being masked in the UI or
redacted from logs. It's now `type: 'password'`.

If your check is specifically looking for the field *key* to be `password` rather than the field
*type*, let me know and I'll rename it — the app isn't published yet, so there are no existing
connections to break.

**5 — Integration follows naming conventions**

All 12 actions renamed to verb-first form ("Check Breach Exposure", "Scan Lookalike Domains",
"Look Up Threat Indicator", and so on). All 13 descriptions now begin with a third-person verb,
end with a period, and no longer contain "RelayShield". The trigger keeps the "Triggers when…"
format with the app name removed.

One question on this item: our 12 actions are all read-only lookups — they fetch risk data for an
email, domain or phone number and create nothing. They're currently registered as `creates`. Reading
your naming guide, these may belong as `searches` instead. I've left them as `creates` for now
rather than make a structural change you didn't ask for, but I'm happy to convert them if that's
what you'd prefer — just let me know before I do.

I've also taken the opportunity to correct a stale figure in one action description, which
advertised an older corpus size than we currently hold.

Everything above is live in 1.0.5. Let me know if anything needs another pass.

Best,
Andrew
