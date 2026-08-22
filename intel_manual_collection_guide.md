# Collecting channel lists by hand — what to grab, and what happens to it

*Written 2026-08-22. Answers "show me what I need to pull from my browser, and do you build a script
for it." The script is `tools/import_channels.py`. Yes.*

## Why this is a manual step at all

Three sources publish running lists of criminal Telegram channels. **All three are blocked by the
dev sandbox's egress proxy**, so nothing in a Claude session can read them:

| Source | Status here | Automatable? |
|---|---|---|
| `ransomlook.io` | 403 on CONNECT | ✅ **Already automated** — see below |
| `socradar.io` | 403 on CONNECT | ❌ Blog posts, no API. Manual |
| `breachsense.com` | 403 on CONNECT | ❌ Curated page, no API. Manual |

They are ordinary websites in your browser. Ten minutes of copying replaces a research problem.

---

## 1. RansomLook — already wired, nothing to do by hand

`ingest_ransomlook_channels()` in `relayshield_intel_discovery.py` now calls their public API on
every discovery run and queues what it finds as `pending_review`.

**Contract taken from their source, not guessed** — `RansomLook/RansomLook`,
`website/web/api/telegramapi.py`:

    GET /api/telegram/channels        -> ["channelname", ...]
    GET /api/telegram/channel/<name>  -> [group, posts]   (group.meta is the description)

⚠️ **Never exercised against the live service from here.** It is written to fail soft and to add
nothing on an unexpected response shape, so the worst case is a no-op run and a log line. **Confirm
the first real discovery run's admin digest** — it now prints a "channels queued from RansomLook"
block. If it says nothing, check the Lambda logs for `RansomLook fetch failed`.

Sanity-check the endpoint yourself in one line:

    curl -sS "https://www.ransomlook.io/api/telegram/channels" | head -c 500

Switch it off with `RANSOMLOOK_INGEST=0` if it ever misbehaves; tune with `RANSOMLOOK_MAX` (200) and
`RANSOMLOOK_MAX_DETAIL` (40).

---

## 2. SOCRadar — what to copy

**Pages worth having open:**
* `socradar.io/blog/top-stealer-log-telegram-channels/`
* `socradar.io/blog/the-top-10-dark-web-telegram-chat-groups-and-channels/`

**What to take, and only this:**
* The **channel name or `@handle`** exactly as printed.
* The **one-line description**, if there is one. It is what the classifier reasons about, so it is
  worth the extra seconds.

**What to ignore:** screenshots, member counts, "last seen" dates. Member counts get re-measured by
the discovery crawl, and a stale one in the description is worse than none.

**Do not visit the channels.** You are copying names off a blog. Nothing here requires opening
Telegram, and the pipeline resolves them itself.

## 3. Breachsense — what to copy

**Pages:**
* `breachsense.com/infostealer-channels/`
* `breachsense.com/threat-actor-channels/`

Same rule: name or handle, plus the description. The threat-actor page is the more valuable of the
two — it names **operators**, which is the category with no public-feed competition at all, and
those go to the operator table rather than the channel table (see below).

---

## 4. The format to paste into

One entry per line, in a plain text file. `@` optional, `t.me/` links are handled, `#` comments and
blank lines ignored, an optional comma-separated note becomes the description:

    # from socradar, top stealer log channels, 2026-08-22
    @example_logs_channel, daily stealer log drops
    https://t.me/another_channel
    third_channel

## 5. Running it

    python3 -m venv /tmp/rsvenv && /tmp/rsvenv/bin/pip install boto3
    cd ~/"Side SaaS Hustle"

    # dry run first — prints what it would do, writes nothing
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py channels.txt --source socradar

    # commit
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py channels.txt --source socradar --apply

**Operator handles instead** (the Breachsense threat-actor page, `@bjorkanesiaaaa`, etc.):

    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py operators.txt \
        --operators --source breachsense --apply

## 6. What the script does and does not do

**Does:**
* Strips `@` and `t.me/` prefixes, lower-cases, validates against the Telegram username rules.
* **Reports every rejected line with its number.** A silently-dropped line is a channel you think
  you added and did not.
* Collapses duplicates.
* **Skips anything already in the table**, printing why — an active channel is being monitored and a
  rejected one was rejected on purpose; re-queueing either makes the classifier re-pay for a verdict
  it already reached.
* Writes channels as `category="pending_review"`, `active=False`.

**Does not:**
* **Activate anything, ever.** An approve flips `active=True` with no undo, and a hand-typed list is
  exactly where a typo enters. The OSINT-2 classifier decides, not the import.
* Resolve channels through Telegram. The discovery crawl does that on its next run.

## 7. Then triage

    GitHub → Actions → INTEL Channel Classifier (OSINT-2) → Run workflow

Leave `apply` unchecked for the first pass and **read the verdicts**. On the one prior data point
(2026-07-24) the classifier rejected 138 of 141 candidates, so a low approval count is the expected
result, not a broken run.

---

## Cadence

Do this **once a fortnight, alongside the automated OSINT sweep** (1st and 15th, Routine
`trig_012eVHz4xEby12AJAXQRG8N2`). The sweep produces keywords and structural findings; this produces
handles. They are complementary, and neither replaces the other.

**Record what came of it** in `intel_channel_recommendations.md`'s scoreboard. A source that has
produced nothing after two rounds should be dropped rather than kept out of habit.
