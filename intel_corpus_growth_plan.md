# Growing the indicator corpus: volume, uniqueness, quality

*Written 2026-08-20, in response to the finding that killed the Segment 1 outreach.*

## The problem, stated precisely

The corpus is ~511K indicators. The **exclusive** part — collected by us, not ingested from a public
feed — is roughly 4,700 wallet addresses plus scam URLs. Everything else is abuse.ch (URLhaus,
ThreatFox, Feodo) and CISA KEV, which every buyer in the blockchain-analytics segment already
ingests.

So the number to grow is not 511K. **It is the exclusive slice, per category.** Growing total
volume by ingesting another public feed makes the headline number better and the product worse.

Three axes, and they are not the same thing:

* **Volume** — how many exclusive indicators.
* **Uniqueness** — what share appears in no feed a buyer already has. Already measured per run by
  `tools/export_intel_sample.py` as `measured_exclusive_share`. **Make this the KPI.**
* **Quality** — is the indicator actionable, current, and correctly typed. A wallet address with no
  first-seen date and no context is volume, not quality.

---

## Ranked by leverage

### 1. Triage the 75 pending_review channels — decided, costed, still unbuilt

The single cheapest win available. `relayshield_intel_monitor.py`'s `_queue_discovered_channels()`
has been auto-discovering channels into `category=pending_review` and **nothing has ever triaged
them**. 75 channels sit there, against 122 currently active.

The decision is already made and the cost already established: Claude Haiku 4.5 via Bedrock,
**~$0.17 one-time** for the backfill and ~$0.03/month ongoing. Same AWS IAM as everything else, no
new vendor, no new secret. It has been "decided, not implemented" since 2026-07-23.

**Potential upside: up to +60% on active collection surface, for under a dollar.** Nothing else on
this list has that ratio. Build it.

### 2. Operator identity indicators — the category where we would be uniquely strong

This is the highest-uniqueness idea here, and it is a category we do not currently produce.

Nobody in the public-feed ecosystem publishes **scam operator handles**: Telegram usernames, channel
IDs, Discord handles and invite codes, bot handles, the display names that recur across campaigns.
abuse.ch publishes infrastructure. It does not publish people.

We already ingest the raw material — the monitor is reading these channels every day. Extracting
`@handle`, channel ID and invite code as first-class indicator types would create a category that is
**~100% exclusive by construction**, because no feed we compete with collects it.

Caveats to design in from the start: handles are reused and recycled, so first-seen/last-seen dates
matter more than for infrastructure; and a handle is a person, so the same care that keeps
`/exposure` from printing credentials applies here.

### 3. Pivot enrichment — turn one collected indicator into a cluster

Derived indicators inherit the exclusivity of their seed. Two pivots, both on infrastructure that
already exists:

* **Wallet → counterparties.** One collected drainer address has transaction counterparties. Those
  addresses are ours by derivation, not from a feed. `relayshield_alchemy_webhook.py` and the
  monitors already touch this data.
* **Domain → siblings.** Certificate transparency and passive DNS pivot from one collected scam
  domain to the rest of the campaign's infrastructure. `relayshield_cert_monitor.py` and
  `relayshield_domain_monitor.py` already exist.

**Quality risk, and it is the real one:** a pivot without a confidence decay produces a large volume
of weakly-associated indicators, which is exactly the thing that would make a technical buyer
distrust the whole corpus. Every derived indicator needs its derivation path and a confidence lower
than its seed. Do not let a pivot silently inherit "confirmed malicious."

### 4. The consumer bots are a collection surface nobody else has

`/scan` submissions across Telegram, WhatsApp and now Discord are **real victims pasting real
attacks in real time** — typically before the domain reaches any feed. That is the freshest
possible signal and it is structurally exclusive.

Two things make it usable: log every submission with its verdict, then **re-check the unknowns on a
delay**. A link that returned "no known flags" on Monday and is flagged everywhere by Friday was an
exclusive indicator on Monday, and we saw it first. That gap is provable, and it is a far better
outreach claim than corpus size.

This also converts the gaming-Discord outreach from a marketing channel into a collection channel,
which changes how much that pipeline is worth.

### 5. Cooperating-admin access to closed rooms

The Discord bot workstream's ceiling is that we cannot get onto adversarial servers. But the flip
side of the gaming outreach is that a **cooperating admin can grant legitimate access** to rooms
where scam traffic actually lands. That is a genuinely new, genuinely exclusive surface, and it
arrives as a by-product of outreach already planned.

Keep it honest and consensual: this is a partner sharing their own server's abuse reports, not
covert collection. That distinction is the entire difference between an asset and a liability.

### 6. Under-served categories worth deliberate investment

The exclusive slice is crypto-wallet heavy. Categories where we have the pipeline but thin output:

* **NHI / machine credentials** from stealer logs — `/v1/metered/nhi-exposure` exists. API keys and
  tokens in criminal markets are higher-value and rarer in public feeds than passwords.
* **SIM-swap and scam phone infrastructure** — `relayshield_sim_swap_monitor.py` exists. Phone
  numbers are barely represented in public IOC feeds.

---

## What NOT to do

* **Do not ingest another public feed to grow the number.** It moves the headline and lowers
  `measured_exclusive_share`, which is the metric that actually sells.
* **Do not trade the exclusive slice into a feed exchange.** Trading is how exclusivity dies, and
  exclusivity is the whole asset.
* **Do not report total corpus size in outreach again.** That is the mistake that nearly went out
  to TRM, Chainalysis, Elliptic and Merkle Science.

## Measurement, so this does not repeat

Add to `relayshield_weekly_metrics.py`: **exclusive indicators by category, trailing 30 days**, and
`measured_exclusive_share` per category. One number per category, tracked over time.

The gate for restarting Segment 1 outreach should be a number on that report, not a feeling that
the corpus has grown.
