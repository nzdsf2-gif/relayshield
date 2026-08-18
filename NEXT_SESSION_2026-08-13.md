# Next session, 2026-08-13

## 1. XSOAR demo. BLOCKED ON MOSHE, do not start building.

**Deadline is Friday 21 AUGUST, not 14 August.** Both are Fridays, which caused a scare on
2026-08-12. The commitment on the PR record, in the founder's own words, is "I will have the
recording to you by Friday 21 August". Nine days from 2026-08-12.

### The blocker, found 2026-08-12 and it is decisive

**Cortex XSOAR Community Edition was discontinued on 15 August 2024.** Pinned announcement in the
Cortex DFIR Community Slack, `#general`, from Synthanee Humbert: Community Edition was built on
XSOAR 6, Palo Alto moved to XSOAR 8, and they stopped offering it two years ago.

The founder's 2026-08-09 comment on the PR says he "signed up for Community Edition to have
somewhere to run it". **Whatever that was, it is not a tenant this pack can be installed on. There
is currently nowhere to record the demo.**

This is the exact thing `xsoar_demo_runbook.md` section 0.2 said to ask Moshe about rather than
guess at. **A Slack DM to MosheEichler went out 2026-08-12 asking what route an external
contributor should use.** Wait for that reply before doing anything else on this item. Building
against an assumption here wastes an evening.

### The PR itself is clean, verified live 2026-08-12

| | |
|---|---|
| Review threads | **39 total, 0 unresolved** |
| `check_docs_approved_label_job` | **SUCCESS** (the notes had this as stale and failing) |
| All other checks | passing |
| Labels | `docs-approved`, `pending-demo`, `pending-contributor` |
| CLA | no blocking check present |

Moshe, 2026-08-09: "Recording the demo and sending it via Slack on DFIR sounds good. Thank you for
your great work :)" **The recording is the only gate. There is no code work left.**

### It does not have to be one sitting

Split it: get the pack onto a tenant one evening, configure and run the commands another, record
last. The recording itself can be several clips stitched; demo-prep does not require a single take.
Rough shape once a tenant exists: 30 to 60 min to install, 20 min to configure and test, 20 to 30
min to record, 10 min to send.

Scope is already written in `xsoar_demo_script.md`: product overview, each command run against a
live instance, instance configuration, error handling on bad credentials, and command verification
against the standards. Reputation commands only, so no fetch-incidents, playbooks or layouts, and
the script already says so up front.

## 2. `rsscan --deps` and the Hugging Face article.

**This is one task, not two.** The HF article cannot be published without the tool, and that is the
whole reason it is sequenced this way.

### Why the tool has to ship first

Hugging Face requires a blog article to be one of exactly two things:

1. explore an AI science or engineering concept, or
2. **announce the release of an open source artifact** (model, dataset, or tool)

The npm worm post is neither. It announces a paid closed API, so it does not qualify, and I was
wrong on 2026-08-12 when I called it "the best post we have had for HF" before checking the
guidelines. Same shape of error as the HackerNoon one: check the constraint before building the
submission.

`rsscan` **is** an open source tool. MIT licensed, currently v0.1.3, already on PyPI, GitHub, Docker
Hub, the GitHub Marketplace and the CircleCI orb registry. A new capability in it is a legitimate
open-source release announcement under rule 2.

**We already have HF PRO** (`isPro: true`, verified live), so there is no paywall. The blocker was
never money, unlike HackerNoon.

### Build: `rsscan --deps`, Phase 1 from `angle2_maintainer_watch_scope.md`

Deliberately small, and deliberately **counts only, no screening**:

- read `package.json` / `package-lock.json` from the current directory
- resolve each package to its publisher accounts via `registry.npmjs.org/<pkg>/latest`
  (**not** the full package document, which is 11 MB for `@types/node`, and **not** the abbreviated
  `application/vnd.npm.install-v1+json` document, which omits `maintainers` entirely and silently
  returns zero for every package)
- report counts: *"412 dependencies, 1,140 maintainer accounts, 96 of them personal webmail
  addresses"*
- runs locally, no account, no API key, no network call to us

The resolver, role-address filter and manifest parser already exist and are tested in
`relayshield_api.py` (`_npm_maintainer_emails`, `_is_role_address`, `_packages_from_manifest`).
Port them; do not rewrite them.

**It closes on what it cannot see:** whether any of those accounts are actually exposed. That is the
same construction as `rsscan --report` and it is the founder-approved funnel unchanged.

### Then the article

Structure it as the tool release, with the worm mechanism as motivation rather than as the pitch.
Reuse the body from `blog_source/the-npm-worm-does-not-start-with-malicious-code.md` and **include
the HF-specific section already drafted** in `blog-npm-worm-DISTRIBUTION.md` under "Hugging Face
blog", the one about `hf_` tokens riding in the same stealer log as npm publish tokens. That section
is the reason to post on HF at all, and a canonical import would not carry it, so this is a full
paste.

Set the canonical line to the blog post. CTA key `npm-worm-hf` is already registered and verified.

**Caveat to hold onto:** we have **0 followers** on HF, so an HF *Post* has no organic reach. The
article is the durable, indexed artifact. Do the article, skip the Post.

---

## Also still open, from 2026-08-12

- **Discord server outreach.** Target list and the big-vs-mid-size method are in
  `discord_server_targets.md`. **First move: post to the Solana Mobile Community Discord aimed at
  admins in the audience, not at Solana Mobile themselves.** MetaMask is deliberately held until the
  Snap review closes around 8 September. The mid-size install list still needs about an hour of
  research; check `relayshield_intel_discord_channels` first, it already holds harvested leads with
  guild names and member counts.

- **Bundle D listing text.** Text-only `UpdateInformation` change set: add the dependency-risk
  capability copy so buyers can see it, and fix the metrics from 5.0M to 5.4M. Carries **no
  pricing**, so an audit failure cannot roll the live listing back to placeholder prices. This is
  the low-risk path that came out of the founder's correction: no new AWS dimension, the capability
  is included flat in Bundle D.
- **Bundle A listing metrics.** `prod-f5qkfsxlxs4qg` still says 5.1M+ and 87 channels. Should be
  5.4M+ and 89. Same `UpdateInformation` mechanism.
- **CPPO + the MSP target list.** Not started. Both listings are live so the precondition is met.
- **C2IntelFeeds is dead.** Both URLs 404, writing `fetched=0 written=0` every run. Also
  `_ingest_phishtank` and `_ingest_hagezi` are defined but never invoked, and PhishTank is named in
  public copy on `/developers`.
- **top.gg submission.** Founder working it. Server rename and permanent invite in
  `discord_support_server_setup.md`.
- **GSB in the Telegram bot.** Removed from the Discord bot's user-facing strings on 2026-08-12.
  `relayshield_telegram_webhook.py` has the same attribution and was not touched. Decide whether it
  should match.
