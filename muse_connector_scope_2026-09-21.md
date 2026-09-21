# Meta Muse connector: the two keyless endpoints. Not the MCP server.

**Answer: `/v1/link-check` and `/v1/wallet-risk`, as one narrow connector. Nothing else.**

**UNVERIFIED THROUGHOUT.** `muse.ai`, `techcrunch.com` and every write-up of the connector
platform are egress-blocked from this container, so everything about Muse below comes from
search summaries. What is stated about OUR assets is read out of the code and is not.

---

## Why not the HuggingFace MCP server, which is the obvious candidate

It is hosted, it is live, it already answers at a URL AWS Marketplace and Smithery both
register, and Muse reportedly accepts MCP servers. It is still the wrong one.

**Its fourteen tools, read out of `hf-space-mcp-server/app.py`:**

    check_mcp_server_risk        check_prompt_injection_breach
    check_tech_stack_cve         check_bulk_identity_risk
    check_oauth_watchlist        check_supply_chain
    check_session_risk           check_nhi_exposure
    check_secret_scan            check_llm_credential_exposure
    check_agent_risk_summary     get_stix_indicators
    check_server_status

**Not one of those is a question a consumer asks.** Muse's users have Gmail, a calendar and
a music subscription. They do not ask an assistant to check a CVE against their declared
tech stack or to scan a package registry for leaked non-human identities.

**Listing it would be ranking a surface by how it performs in general rather than by how it
performs for us**, which is the error this repo has already recorded twice: the bot's menu
button ranked top for a bot with almost no users, and `@telegtapps` ranked on subscriber
count. The audience decides, not the asset's quality.

## Why the two keyless endpoints, and why exactly two

**They answer questions a person actually asks in plain language.** "Is this link safe?" and
"is this wallet address a scam?" Those are the only two of ours that survive translation into
a consumer assistant.

**They need no OAuth, and that is the single biggest reduction in scope.** Meta's submission
packet reportedly wants a product description, an API docs URL, an OAuth app, a SKILL draft
and a security contact. Keyless removes one of the five outright: there is no account, no
token exchange and no consent screen to review, because `KEYLESS_SCAN_ENDPOINTS` in
`relayshield_api.py` lists both and the dispatcher serves them with no key.

**They sell nothing, which is the compliance trap avoided rather than managed.** FD-14 found
that selling digital goods inside the host is not permitted on OpenAI's side, and the same
shape is the reason Telegram Stars exists. **A connector over two free endpoints has no
billing surface at all**, so there is nothing to review and nothing that can get us
restricted. The paid rails stay outside the host, reached the way every other API customer
reaches them.

**The API docs URL field is already satisfied.** `api.relayshield.net/openapi.json` is
OpenAPI 3.1, served by `relayshield_api.py`, and explicitly allowed in our own robots.txt.
Muse reportedly writes integration code for any service with a public API, so the spec is
the integration.

## Why this fits Muse specifically, rather than being a generic listing

Muse acts on a person's behalf across their mail and, through the Stripe partnership,
their money. **An agent that can pay is an agent that can be defrauded**, and nothing in a
connector platform answers "is the counterparty this agent is about to trust real".

That is the same gap we take to Rain and Routavo, in front of a far larger deployment, and
it is the one place our thesis and a consumer assistant's actual risk surface are the same
thing. `/v1/link-check` is the check that belongs in front of "the agent is about to follow
this link", which for a Gmail-reading agent is most of what it does.

---

## THE BLOCKER, AND IT IS OURS. NAME IT BEFORE SUBMITTING, NOT AFTER APPROVAL.

**`KEYLESS_IP_DAILY_CAP = 300`, per source IP.**

Every call from Muse would arrive from Meta's egress addresses, so a consumer platform at
any scale throttles the connector against itself on its first busy hour. The cap's own
comment says what it is for: *"This stops the endpoints being an unmetered upstream proxy;
it is not a substitute for authentication."*

**THIS IS THE THIRD TIME THIS EXACT PROBLEM HAS DECIDED A DESIGN HERE.**
`relayshield_watchlist_monitor.py` imports its handler rather than calling the public
endpoint because every invocation would arrive from one NAT address. The WhatsApp front
door's `keyless_check()` carries the same limit, written down on 2026-09-21. **A partner
platform is the same shape with a much larger multiplier.**

**So a Muse connector needs a partner key before it needs anything else**, and that is a
small build rather than a new product: an API key issued to the connector, sent as
`X-RS-API-KEY`, which lifts the per-IP cap and makes the traffic countable per partner
instead of vanishing into one bucket. Half a day. **It does not make the endpoints paid**
and must not: the whole argument above rests on them staying free.

## The order, and reading is genuinely the first task

1. **Register `?source=muse` before anything is submitted.** An unregistered key is sent,
   accepted and never logged, which is FD-8 and four months of it. Not done yet, on purpose:
   there is nothing to attribute until there is a submission.
2. **Read the actual requirements at `muse.ai/platform`.** Three questions decide the rest,
   and none can be answered from here: is the portal open or a waitlist; can a connector
   serve anonymous keyless calls or is an OAuth app mandatory; and what are the terms, which
   are reported as undisclosed. **If OAuth is mandatory, the whole scope above changes** and
   this document is the wrong plan.
3. **Issue the partner key** and lift the cap for it.
4. **Submit** the two-endpoint connector with the OpenAPI URL.

**Do not scope the build before step 2.** FD-2 cost a day on a destination whose own page
said the submission would be closed unread, and FD-14 turned up a rule that changed the
answer entirely. **Reading is the task.**
