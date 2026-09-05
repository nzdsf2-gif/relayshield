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


---

# Session 2026-08-20, part 2 — shipped, plus a finding that changes the plan

## The biggest win was already in the code and being thrown away

`extract_iocs()` has always extracted **five** indicator types that `_store_iocs()`'s `type_map`
never listed, so **not one of them was ever written to the table**:

| Extracted as | Now stored as | Why it matters |
|---|---|---|
| `tg_mentions` | `tg_handle` | **The scam-operator-handle category.** Highest uniqueness available |
| `onions` | `onion` | Tor infrastructure; thin in public feeds |
| `md5` | `hash_md5` | Older samples are still md5-referenced |
| `sha1` | `hash_sha1` | Same |
| `ransomware_victims` | **deliberately NOT stored** | See below |

This is the **identical defect** to the `cves` entry, whose own code comment records that CVEs
"had been extracted from every monitored message all along" and never persisted. It happened twice
because `extract_iocs()` and `type_map` are two lists that must agree and nothing checks that they
do.

**Fixed 2026-08-20.** Four types added. This is pure upside: the collection already happened, the
parsing already happened, and the results were being discarded at the last step.

**Worth a test that fails when they diverge again.** Two lists that must agree, no assertion tying
them together, and it has now silently broken twice.

### `ransomware_victims` excluded — the concrete reason

The earlier wording here was too abstract to act on. Plainly:

**Every other row in `relayshield_intel_iocs` answers "this thing is dangerous."** A wallet that
drains people. A domain that phishes. A hash that is malware. The whole table is a list of things
you should not touch, and everything downstream treats it that way.

**`ransomware_victims` answers a different question: "this company got attacked."** Acme Corp
appearing on a leak site does not make Acme Corp dangerous. It makes them a victim.

Why mixing them breaks things, concretely:

1. **It would fire false alerts.** The watchlist matches customer assets against this table. Put
   "Acme Corp" in it, and a customer who monitors `acmecorp.com` gets an alert saying their domain
   appears in the criminal IOC corpus — with `_remediation()` telling them to rotate credentials.
   The correct message is the opposite in tone and content: *your vendor was breached, here is what
   that means for you.*
2. **It would corrupt the exclusivity metric.** `measured_exclusive_share` is meant to say what
   share of our *threat* indicators appear in no public feed. Victim names are published on the leak
   sites themselves, so they would inflate volume while being trivially public — the same error
   that nearly went out to TRM and Merkle Science.
3. **It changes what a hit means.** Anyone consuming the corpus — us, a customer, a partner —
   reasonably reads "in RelayShield's IOC corpus" as an accusation. For a victim organisation that
   is defamatory-adjacent and simply wrong.

**This is not "throw the data away."** Ransomware victim tracking is genuinely valuable — it is
early warning for a customer's suppliers. It wants its own table, its own matcher, and its own alert
copy. **BUILT 2026-08-20 — see below.**

### Supplier-breach watch, built 2026-08-20

* **`relayshield_ransomware_victims`** — own table, `victim_name` + `seen_ts`, TTL matching the IOC
  table. Every row carries `confidence: "unverified"`, because `_RE_RANSOM_VICTIM` takes capitalised
  words after "hacked"/"leaked"/"victim" and will contain noise. **Storage is unconditional**; it is
  a lead list.
* **`_match_supplier_breach()`** — **opt-in only.** It reads `supplier_watchlist`, an explicit list
  the customer entered, and infers suppliers from nothing else. Telling someone "your vendor was
  breached" off a loose regex would be worse than silence: they would act on it.
* **Exact normalised-key matching, not substring.** Substring matching on company names produces
  absurd hits ("co" inside "cisco"). Keys are lowercased, stripped of non-alphanumerics, and
  generated both with and without the corporate suffix, so "Acme Corp." matches `acme` *and*
  `acmecorp` — a company may use either in its domain and there is no way to know which.
* **`_format_supplier_breach_alert()`** — deliberately different copy. The IOC alert says "your
  credential is in criminal hands, rotate it". This one says a supplier was attacked, *you are not
  compromised*, rotate the credentials **you issued to them**, and watch for invoice fraud and
  impersonation — the most common follow-on. It closes by saying the extraction is unverified and to
  confirm with the supplier before treating it as fact.

**A bug the tests caught before it shipped:** the first version floored match keys at 4 characters,
which silently dropped every three-letter supplier — IBM, SAP, AWS, EDF. A customer watching IBM
could never have been alerted about IBM. Since matching is exact key equality rather than substring,
short keys were never the risk the floor was guarding against; bare corporate suffixes were, and
those are now excluded by name. Floor is 3.

**Known limitation:** "Northwind" will not match a supplier entered as "Northwind Traders Global".
Enter suppliers as they appear on leak sites. Loosening this to substring matching would reintroduce
exactly the false positives the design exists to avoid.

**The table must be created before the next intel deploy** — see `lambda_recovery_and_deploy.md` §6.
Until it exists, victim writes fail as logged warnings; collection continues and victims are dropped.

### Honest limit on `tg_handle`

`_RE_TG_CHANNEL` is `@([a-zA-Z][a-zA-Z0-9_]{4,31})` — it matches **any** @mention, including
entirely legitimate ones. So this is a **lead list, not a verdict.** Its value is that every row
carries the source channel and that channel's category, so a handle seen in an `infostealer` room
is distinguishable from one mentioned in passing.

**Do not export this as "known scam operators" without a filter.** Sending a list that includes
legitimate handles to a prospect would be the same class of error as the abuse.ch corpus mistake:
technically derived from real data, trivially disproved on inspection.

## 95 vs 122: the count was never measuring what it claimed

**Nothing in the codebase ever set a channel's `active` back to `False`.** Every `active=False`
write is at row *creation* (newly-discovered or pending). There is no deactivation path anywhere.

So 122 → 95 is not attrition being recorded. It is the difference between two numbers that were
never compared:

* **`active=True`** = "we intend to monitor this."
* **channels actually read on a run** = what the collection surface really is.

When `get_entity()` raised `ChannelPrivateError` or `ValueError` — deleted channel, gone private,
account banned — the code did a bare `continue`. The channel stayed `active=True` forever, produced
nothing, and **counted as healthy in every metric we report.** The gap was invisible because nothing
wrote it down.

This is the same defect family as the false-clean bugs fixed repeatedly here: a number that looks
fine while the thing underneath has degraded.

**Fixed 2026-08-20**, three parts:

1. `_record_channel_failure()` writes `last_error`, `last_error_detail`, `last_error_at` and
   increments `consecutive_failures` on every unreachable channel.
2. `_clear_channel_failure()` resets the counter when a channel reads successfully again.
3. The digest now reports **`Channels checked: 95 of 122 active  ⚠️ 27 unreachable`** instead of
   `Channels checked: 95`. Same run, and now the degradation is legible.

**Nothing auto-deactivates.** A channel can go private for a week and come back; silently shrinking
the corpus on one bad run is the more expensive mistake. It records and counts, and a human decides
when `consecutive_failures` is high and stable.

**These fields are empty until the patched monitor has run.** An all-zero `consecutive_failures`
column proves nothing yet — read the digest's new `X of Y` line instead.

## The 75 pending channels: needs AWS, script provided

This could not be done from the dev sandbox — no AWS credentials, and the backlog lives in
DynamoDB. `tools/triage_channels.py` answers both questions from the founder's Mac:

    python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py --pending

Read-only by default; `--apply` is required to write. It prints the active/failing split (the
122-vs-95 answer), the category breakdown, and the pending backlog **sorted by member count**, then
activates a chosen list:

    ... --activate name1,name2 --apply

**Judge by what the room is for, not by size.** The active set is infostealer/credential_dump
shaped; a large off-theme room is noise that costs a Telegram fetch every run.

## New ToDos

* **Pivot enrichment.** Wallet → transaction counterparties, domain → certificate-transparency and
  passive-DNS siblings. `relayshield_alchemy_webhook.py`, `relayshield_cert_monitor.py` and
  `relayshield_domain_monitor.py` already reach this data. **Every derived indicator must carry its
  derivation path and a confidence strictly below its seed** — a pivot that silently inherits
  "confirmed malicious" would flood the corpus with weak associations and cost more credibility
  than the volume is worth.
* **Re-check unknowns on a delay.** Log every consumer-bot `/scan` submission with its verdict,
  then re-check the `unknown` ones after 24h / 72h / 7d. A link clean on Monday and flagged
  everywhere by Friday **was an exclusive indicator on Monday, and we saw it first.** That gap is
  provable and is a far better outreach claim than corpus size. It also turns the Telegram,
  WhatsApp and Discord bots from a marketing channel into a collection channel.
* **Add a test that fails when `extract_iocs()` and `type_map` diverge.** Twice now.


---

## Running the channel triage (2026-08-20)

`tools/triage_channels.py` is committed and needs AWS, so it runs on the founder's Mac:

    cd "$HOME/Side SaaS Hustle"
    git pull origin main
    python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3   # once
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py --pending

That prints the active/failing split (the 122-vs-95 answer), the category breakdown, and the 75
pending channels sorted by member count. Then activate the worthwhile ones:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py \
      --activate name1,name2,name3 --apply

**Read-only without `--apply`.** Run it once without to see what it would do.

**The `consecutive_failures` column is empty until the patched monitor has run at least once.** An
all-zero column right now means "no data yet", not "no attrition".

---

# Session 2026-08-26 — the Android category, and why the obvious way to build it is wrong

## Where this came from

The ToxicPanda 2.0 post published today reports a measurement: we searched the `malware-index` for
ToxicPanda and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook,
Medusa), plus an 80,000-record sample of every distinct family label the corpus carries, and found
**zero hits on all of them**. The 42 families in that sample are Windows infostealers, RATs,
Mirai-class botnets and ransomware loaders. Android banking trojans are not a thin category here.
They are an absent one.

Having published that, we now have a public, dated, checkable claim that the gap exists. Closing it
is a ToDo, not an emergency, but leaving it open indefinitely while quoting the post is worse than
never having measured.

## ToDo: build the Android category

Four sources, in the order they should be evaluated:

1. **MalwareBazaar** — abuse.ch, already an ingested source family for other categories. Filter on
   Android tags (`apk`, `android`, family tags). Cheapest possible start: the ingestion path exists.
2. **Koodous** — Android-specific, community rulesets and APK analyses. New integration.
3. **VirusTotal mobile-focused rules** — Retrohunt/LiveHunt on Android-specific YARA. Requires the
   VT tier that permits hunting, which is the cost question to answer before design.
4. **Dedicated Telegram channels** — Android malware and mobile-fraud rooms, added to the intel
   channel table like any other collection channel.

## Read this before building any of it

**The first three are public feeds. The doctrine in CLAUDE.md says growing total volume by
ingesting another public feed makes the headline better and the product worse, and that nearly
killed the Segment 1 outreach.** That warning applies here in full, with one qualification worth
being precise about.

The KPI is `measured_exclusive_share`, per category. An Android category built entirely from
MalwareBazaar, Koodous and VT would land at or near **0% exclusive share**: every indicator in it is
one a target buyer already has, and the only honest thing we could say is "we carry the same Android
IOCs everyone else does." That is a coverage checkbox, not a product claim, and it must never be
quoted as one.

Source 4 is the one that can produce exclusive share, for the same structural reason the corpus is
strong on infostealer credential material: closed and semi-closed rooms are where material appears
before it reaches a public feed. So:

- Build 1 and 2 for **coverage**, so the honest answer to "do you cover Android" stops being no.
- Build 4 for **exclusivity**, and measure it separately from day one.
- Do not quote an Android number of any kind until `tools/exclusive_share_by_category.py` has run on
  the category and it clears **100 collected indicators**, per the standing rule.
- 3 is gated on the VT tier question. Answer the cost before designing around it.

## Explicitly not part of this

Seeding anything for ToxicPanda specifically off the back of the blog post. The post commits to that
in writing. Zimperium's published IOC set is a legitimate ingestion candidate on its own merits, as
a decision made deliberately and separately, and if it is ingested the post's measurement stays true
as written because it is dated 2026-08-25.

---

# 2026-08-26 — the channel count is a public claim, and four surfaces disagree with each other

## What prompted this

The 2026-08-26 13:50 UTC digest reported **`Channels checked: 12`**. The founder's reaction is the
correct one: we market the monitored-channel count, the number quoted recently was 99, and 12 is not
a rounding error against 99. Channel attrition is real, Telegram channels get banned and go private
constantly, but attrition is an explanation for a declining number, not for a number four surfaces
disagree about.

## The claims, as they stand today

| Surface | Claim | Where |
|---|---|---|
| **Production API** | "collected from **95 monitored channels** and 20 authoritative feeds" | `relayshield_api.py`, TAXII 2.1 discovery description |
| **Production API** | "from **95 monitored channels** and 20 authoritative threat feeds" | `relayshield_api.py`, collection description |
| Twilio marketplace listing | "**87** Telegram channels", re-counted live 2026-08-06 | `twilio_marketplace_listing_request.md` |
| SOCRadar benchmark | "**122** channels, **95** reachable" | `socradar_competitive_benchmark.md` |
| PDF generator | "**37+** monitored channels" | `generate_pdfs.py` |
| Live digest | **12** checked | Telegram, 2026-08-26 |

The first two are the serious ones. They are **served by the production API to customers and to any
TAXII client that connects**, and if the true actively-polled number is 12, they are wrong right now,
in production, in a machine-readable feed description. This is the 511K headline failure mode with a
different number in it: a figure that a prospect can check, quoted on a surface we control.

## Before changing any of them: measure, and settle what the word means

Nothing here gets edited to a new number until it is measured, per the standing rule. But the
measurement is not one number, it is three, and conflating them is what produced the disagreement:

1. **Channels in the collection set** — rows in `relayshield_intel_channels`. Was 122.
2. **Channels active** — `active == True`, which is the only set the monitor ever scans.
3. **Channels successfully polled in the last 7 days** — what "monitored" honestly means to a buyer.

A public claim should quote **3**, and should say so in words: "N channels polled in the last 7
days" beats a bare "N monitored channels" precisely because it cannot be read as a stock figure that
never decays. Then a channel dying reduces the number honestly instead of silently making the claim
false.

Command (his Mac, zsh, needs AWS):

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py --pending

That prints the active/failing split and the pending backlog. Read-only.

## A second thing the digest is telling us: the deployed monitor is older than the repo

The repo's digest line reads:

    f"Channels checked: {stats['channels_checked']} of {stats['channels_attempted']} active"

The screenshot reads `Channels checked: 12`, with no "of N active" and no unreachable count. That
format was added on 2026-08-20 specifically because "Channels checked: 95" on its own looks healthy
while "95 of 122 active, 27 unreachable" tells you the collection surface is degrading.

**The live Lambda appears to predate that change**, which means it is running code older than the
repo, and it also means the 12 cannot be interpreted yet: we do not know from that message whether
12 is the whole active set or 12 out of a larger attempted set. Check `lambda_drift_check.yml` and
any open `lambda-drift` issues for `relayshield-intel-monitor` before drawing conclusions from the
digest, and recover the live handler into git first if it has drifted.

## Order of work

1. Check intel-monitor drift; recover the live artifact into git if it has drifted.
2. Run the triage script. Get the three numbers.
3. Activate the worthwhile part of the pending backlog. This is Top 10 item 3, and it is what
   actually raises the number rather than restating it.
4. Only then, correct every surface in the table above to the measured 7-day figure, production API
   first, and use the same wording on all of them.

---

# 2026-08-26 — decided: the live operator-identities function supersedes the pivot module

## The collision

Two independent implementations of one idea exist:

- **`relayshield_intel_pivot.py`**, committed 2026-08-23 with tests. Imported by nothing, listed in
  no deploy map, absent from every deployed package, invoked by no workflow. **It has never run.**
- **`_store_operator_identities()`**, inlined in the deployed intel monitor, dated A4 2026-08-25.
  Runs hourly. Existed in no repository until it was recovered today.

The live function's own docstring records how this happened: its author went looking for
`relayshield_intel_pivot.py` because a roadmap described it as "module merged", could not find it,
and rebuilt the capability. Whatever the sequencing, the outcome is two of the same thing.

## The decision, founder's call, 2026-08-26

**The live `_store_operator_identities()` wins.** It was written to fix what the earlier approach
never did, and unlike the module it is actually running against live channel traffic. It stays as
it is, and gets a few days to prove it is collecting real data rather than empty leads.

`relayshield_intel_pivot.py` is **superseded, not deleted**. It keeps its tests and stays in the
repo as a reference implementation of the delayed-recheck logic, which the live function does not
have. It must not be wired in: importing it would put a second writer on
`relayshield_operator_identities` and double-count sightings, which is worse than either design
alone.

## Verification before this is called done

Watch the digest line **`Operator identity sightings recorded (A4)`** over several runs. It has
been 0 in the runs seen so far, which is consistent with either "working, nothing to record yet" or
"silently not working". Two things separate those:

- A non-zero count on any run settles it affirmatively.
- A continuing zero means checking `relayshield_operator_identities` directly for row count and
  most recent write, on the Mac, since the sightings are written even when no alert fires.

If it is still zero after a few days of hourly runs while channels are producing messages, that is
a bug to find, not a quiet feature. Note the live function's own stated stance: `_RE_TG_CHANNEL`
matches ANY @mention, so this is a lead list rather than a verdict, and the value is cross-channel
correlation over time. Expect noise; measure the correlations, not the raw count.

## The reason this is worth the care

The cross-category correlation it produces is exclusive by derivation: the same handle appearing in
a ransomware channel one month and a phaas channel the next is a cluster no single-sighting feed can
produce. That is the kind of indicator `measured_exclusive_share` is supposed to reward, unlike
another public feed ingest.
