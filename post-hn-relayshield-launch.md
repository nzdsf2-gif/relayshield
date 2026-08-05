> **STATUS: DRAFT — Ready to post**
> **Target: Hacker News — Show HN**

---

## TITLE (under 80 chars):
**Show HN: RelayShield – Breach, SIM swap, infostealer and IOC lookup via API**

---

## BODY (HN text field, ~300 words, plain text):

I spent 25 years in telecom security and kept watching the same attack chain succeed: leaked credential → infostealer log → SIM swap → account takeover. The telemetry to detect it earlier exists inside carrier and dark web intelligence networks — it just wasn't accessible via API for the teams who could actually do something with it.

RelayShield is what I built to close that gap.

**Six endpoints:**

- `/v1/metered/breach` — email breach exposure check
- `/v1/metered/infostealer` — checks criminal infostealer log markets for credential exposure (24–72h ahead of public aggregators)
- `/v1/metered/sim-swap` — carrier-level SIM swap / port-out detection
- `/v1/metered/domain` — typosquat and lookalike domain scan
- `/v1/metered/oauth-watchlist` — OAuth supply chain exposure for breached credentials
- `/v1/intel/telegram` — IOC lookup across 1.4M+ indicators (Telegram channels, ThreatFox, URLhaus)
- `/v1/intel/cve` — CISA KEV lookup by CVE ID or keyword, cross-referenced for ransomware activity

**Stack:** Python on AWS Lambda, DynamoDB, API Gateway. TI feed pulls from 20+ criminal Telegram channels plus abuse.ch feeds continuously.

**Integrations:** Just went live as a verified node in n8n (search `n8n-nodes-relayshield`). REST API works with Tines, Make, or anything that can POST JSON.

**Pricing:** Metered pay-per-call for the detection endpoints. $499/month for 10K TI API calls (in-house security teams and lean SOC environments), $999/month unlimited (MSSPs and multi-client enrichment pipelines).

**What I'm looking for:** Feedback from people doing SOAR work, threat intel, or running detection workflows. Specifically interested in what enrichment data points would make the IOC lookup more useful for your pipeline.

API docs and free tier: https://api.relayshield.net/developers

---

## COMMENT RESPONSES TO PREPARE FOR:

**"Why not just use HaveIBeenPwned?"**
HIBP is breach database lookups — it covers the same breach check endpoint. The differentiated value is the infostealer log market coverage (HIBP doesn't have it), carrier-level SIM swap detection (no public equivalent), and the live Telegram-sourced IOC feed. Different threat surface.

**"How fresh is the infostealer data?"**
Continuously ingested from monitored criminal channels. By the time a log drop propagates to public aggregators, it's been in our database for 24–72 hours. We're monitoring the source channels, not downstream aggregators.

**"How do you handle false positives on SIM swap?"**
Carrier-level query — it's a binary signal from the carrier record, not a heuristic. The number either has a recent port event or it doesn't.

**"Is this GDPR/privacy compliant?"**
The breach and infostealer endpoints take an email, hash it before querying, and return only whether exposure was found — not the underlying record. SIM swap takes a phone number and returns a boolean. We don't store query inputs.

**"Solo founder?"**
Yes. 25 years telecom security background. This is what happens when you spend two decades watching SIM swap fraud evolve and finally decide to do something about the tooling gap.
