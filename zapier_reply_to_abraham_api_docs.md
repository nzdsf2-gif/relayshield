# Reply to Abraham D. (Zapier Developer Support) — API documentation

**Status:** DRAFT, pending founder review. Do not send until approved.
**Thread:** Zapier Partners Support, re: RelayShield integration review.
**Their ask (2026-08-03):** `api.relayshield.net/developers` lists endpoints and per-call prices
but does not describe endpoints, parameters, error handling or attributes. They pointed at
`petstore.swagger.io/?docExpansion=full` as the reference standard.

**Verified live before sending:**
- `https://api.relayshield.net/docs` — HTTP 200, 32 operations across 8 groups, renders in browser
- `https://api.relayshield.net/openapi.json` — HTTP 200, OpenAPI 3.1, passes `openapi-spec-validator`

---

Hi Abraham,

Thanks for the specific pointer — that was the right call, and the petstore link made it clear
exactly what was missing.

We have published a full API reference:

**https://api.relayshield.net/docs**

It is Swagger UI over an OpenAPI 3.1 specification, so it is the same format as the example you
sent. For each of the 32 endpoints it documents:

- every request parameter, with type, format, constraints and a description
- every response attribute, including nested objects and arrays
- every error status the endpoint can return, each with a worked example body
- a runnable request and response example

The machine-readable specification is at **https://api.relayshield.net/openapi.json** if you would
prefer to review it or generate a client from it.

A few things that may be useful while you review:

- **Authentication.** `X-RS-API-KEY: <key>` or `Authorization: Bearer <key>`. The two are
  equivalent, and header names are matched case-insensitively.
- **Response envelope.** Every response is `{"ok": true, "data": {...}}` or
  `{"ok": false, "error": "..."}`. The `ok` field and the HTTP status always agree.
- **The two endpoints our Zapier app uses** are both free and unmetered, and are now documented:
  `POST /v1/account/info` (connection test and account labelling) and
  `POST /v1/webhook/configure` (alert delivery registration).
- **Errors** are documented per endpoint and summarised in a table at the top of the page. Only
  successful calls are billed — a `4xx` or `5xx` never charges the account.

Reviewing this also surfaced two problems in what we had previously published, both now fixed: the
old specification described seven endpoints that did not exist at the paths given, and omitted
fourteen that did. The reference now matches the live routing table exactly.

Please let me know if there is anything else you would like documented, or covered differently, and
I will get it done.

Best regards,

Andrew Gibbs
RelayShield LLC
support@relayshield.net
