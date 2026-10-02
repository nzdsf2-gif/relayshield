# Channel distribution: Cortex XSOAR content pack post

Canonical: `https://blog.relayshield.net/cortex-xsoar-dbotscore-good` (LIVE, confirmed 2026-10-02).
Each version is written to ITS OWN limit rather than truncated from the one above it.
No em-dashes anywhere. Corpus figures only where the canonical already carries them (123 channels,
8.3M citations, both as of 2026-09-30); short versions carry none.

## What this post is, and who it is for

The pack is live on `demisto/content` master and in the Cortex Marketplace (listing confirmed by
screenshot 2026-09-30; integration reference at
`xsoar.pan.dev/docs/reference/integrations/relay-shield`). The audience is a SOC or MSSP engineer
who already runs XSOAR, XSIAM or the Cortex platform. They do not need convincing that threat intel
matters; they need to know (1) it works with the playbooks they already have, and (2) there is
something in it they do not already get.

**Three claims, in the order a reader should meet them, and the order is the same on every channel:**
1. It is the standard `domain` / `ip` / `email` reputation shape, so an existing enrichment
   playbook picks it up when the integration is enabled. No rewiring.
2. Three commands screen the agentic attack surface (`relayshield-mcp-registry-risk`,
   `relayshield-cert-expiry`, `relayshield-supply-chain`).
3. A clean result is DBotScore Unknown (0), never Good (1). This is the hook for the technical
   audience, not the headline: it is a design decision they will have an opinion about.

**Do NOT claim, anywhere:**
- A Palo Alto "Release Notes" entry. Moshe Eichler promised one in writing; it has NOT been
  confirmed (their docs hosts are egress-blocked from the container). Say "live in the Cortex
  Marketplace" and link the integration reference, which is verified.
- "Nothing else in the marketplace does this." The canonical says it; I could not check the whole
  marketplace from here, and a short post has no room to qualify it. Say what OURS does.
- Any corpus headline in the short versions. Measurement doctrine.
- "Certified" or "Palo Alto partner". The pack is a contributed pack; the Tech Alliance is a
  separate, unfinished thing.

## Attribution keys (REGISTERED 2026-10-02 in `relayshield_developer_signup.py`, before posting)

One key per DESTINATION, so the funnel can tell channels apart. Each is an alias to the existing
`xsoar-post` banner; the RAW key is what gets logged.

| Channel | Key |
|---|---|
| Medium | `xsoar-medium` |
| dev.to | `xsoar-devto` |
| LinkedIn | `xsoar-linkedin` |
| Telegram channel | `xsoar-telegram` |
| Farcaster | `xsoar-farcaster` |
| Mastodon | `xsoar-mastodon` |
| Reddit (if posted) | `xsoar-reddit` |
| Palo Alto LIVEcommunity (if posted) | `xsoar-livecommunity` |

The links below go to `api.relayshield.net/developers?source=<key>`. The `?source=` belongs on
`/developers`, never on the bare host.

**Merge and push BEFORE posting.** A key registered on a branch is downgraded to `unmatched:` at
the live edge, which is attribution that looks like it worked.

---

## Order of publication

1. Blog (done) -> 2. Medium import -> 3. dev.to -> 4. LinkedIn -> 5. Telegram -> 6. Farcaster ->
7. Mastodon -> 8. LIVEcommunity / Reddit, only after reading each one's self-promotion rules.

Medium and dev.to carry the long form, LinkedIn is the professional audience for this topic and
should go the same day as the blog was shared, and the three short channels are brief pointers.
LinkedIn and LIVEcommunity matter most for this post: they are where XSOAR practitioners are.
Medium, dev.to and the short channels are secondary reach for a topic they do not live on.

---

## 1. Medium

**Import with the canonical URL. Never paste. Medium has no Markdown paste.**
The import is a SNAPSHOT: the canonical is final, so import now. Switch the one API link in the
body to `?source=xsoar-medium`.

Title: `Why our Cortex XSOAR pack never says a domain is safe`
Subtitle: `A clean result maps to DBotScore Unknown, not Good. Here is why, and what else the pack does.`

(Medium reads the imported title from the canonical's `<h1>`. If the import keeps the canonical
title, that is fine; the alternative above is only for hand-editing after import.)

Tags (5 max): `Cybersecurity`, `Threat Intelligence`, `SOAR`, `Infosec`, `AI Agents`
UNVERIFIED: Medium tag popularity is not checkable from here. `Cybersecurity` and `Infosec` are
established; swap `SOAR` for `Security Automation` if it shows no followers when typed.

---

## 2. dev.to

File: `blog-cortex-xsoar-dbotscore-good-devto.md` (GENERATED, committed beside this one).
Send it with the script, never the web editor:

    python3 tools/publish_devto.py blog-cortex-xsoar-dbotscore-good-devto.md --dry-run
    python3 tools/publish_devto.py blog-cortex-xsoar-dbotscore-good-devto.md --publish

It ships `published: false`. The canonical is live, so `--publish` flips it.

Tags (4 max, must already exist): `security`, `devops`, `ai`, `opensource`.
The pack is contributed to `demisto/content`, which is open, so `opensource` is honest. A tag that
does not exist returns a 422 naming it; drop it and re-run with three.

---

## 3. LinkedIn (3000 limit)

If you run Cortex XSOAR or XSIAM, there is a new content pack in the Marketplace: RelayShield.

The part I would check first is how it plugs in. It implements the generic domain, ip and email
reputation commands, so an enrichment playbook that already calls those three picks it up the
moment the integration is enabled and a reliability weight is set. No new playbook logic and no
custom integration to write and review.

Behind those commands is intelligence collected from monitored criminal Telegram marketplaces and
infostealer log dumps, which is the half of the picture a standard TAXII subscription does not
reach. The email command checks breach exposure and active stolen-session risk, which is the thing
a password reset does not fix.

Three more commands are specific to the agentic attack surface:
- relayshield-mcp-registry-risk screens an MCP server URL or package name before an agent
  connects to it
- relayshield-cert-expiry checks TLS certificate expiry risk on infrastructure an agent depends on
- relayshield-supply-chain checks up to ten vendor domains or emails in one call

One design decision is worth arguing about, and I would like to hear where practitioners land. A
clean result maps to DBotScore Unknown (0), never Good (1). "No known finding" means nothing was
flagged in the sources we query. That is a narrower claim than verified-safe, and a reputation
integration that conflates the two is telling an analyst something it does not know.

Verdict mapping: CRITICAL and HIGH are 3 (Bad), MEDIUM and LOW are 2 (Suspicious), no known
finding is 0 (Unknown).

Full write-up, including setup:
https://blog.relayshield.net/cortex-xsoar-dbotscore-good

Integration reference: https://xsoar.pan.dev/docs/reference/integrations/relay-shield

Free-tier API key: https://api.relayshield.net/developers?source=xsoar-linkedin

#CortexXSOAR #SOAR #ThreatIntelligence #SecOps #CyberSecurity

**Hashtags:** five, at the end, as above. `#CortexXSOAR` and `#SOAR` are where the audience
follows; LinkedIn does not reward more than five. Do not tag Palo Alto Networks' company page:
the pack is contributed content, and an unprompted tag reads as implied endorsement.

**First comment (post it yourself):** the DBotScore table from the canonical, as plain text. A
comment gets read by people who stop at the first screen of the post.

---

## 4. Telegram (4096 limit), channel `t.me/RelayShield`

**RelayShield is now a Cortex XSOAR content pack**

If your SOC runs Cortex XSOAR, XSIAM or the Cortex platform, you can pull RelayShield intelligence
into an incident without building anything.

It implements the generic domain, ip and email reputation commands, so any enrichment playbook
already calling those picks it up the moment the integration is enabled. Plus three commands for
the agentic attack surface:

- relayshield-mcp-registry-risk: screen an MCP server or package before an agent connects
- relayshield-cert-expiry: TLS expiry risk on infrastructure an agent depends on
- relayshield-supply-chain: up to ten vendor domains or emails in one call

One decision worth knowing: a clean result maps to DBotScore Unknown, never Good. "No known finding"
is not "verified safe", and we do not tell an analyst otherwise.

Full post and setup:
blog.relayshield.net/cortex-xsoar-dbotscore-good

Free-tier key:
api.relayshield.net/developers?source=xsoar-telegram

#CortexXSOAR #SOAR #ThreatIntel

**Do not post this to the bot's own subscribers.** It is a blog-channel post. Most `@relayshield_bot`
users are consumers checking links, and an XSOAR announcement is noise to them.

---

## 5. Farcaster (~1024 bytes)

RelayShield is now a Cortex XSOAR content pack.

Implements the generic domain / ip / email reputation commands, so an existing enrichment playbook
picks it up when the integration is enabled. No rewiring. Plus three commands for the agentic
attack surface: MCP server risk, TLS expiry, and a ten-vendor supply chain check.

One design call: a clean result maps to DBotScore Unknown, never Good. "No known finding" is a
narrower claim than "safe".

blog.relayshield.net/cortex-xsoar-dbotscore-good

**Channel:** `/infosec` if it exists for you, otherwise your default feed. UNVERIFIED: channel names
cannot be checked from the container, and a post to a channel with no audience is a wasted impression.

---

## 6. Mastodon (500 limit)

RelayShield is now a Cortex XSOAR content pack. Generic domain/ip/email reputation commands, so an
existing enrichment playbook picks it up on enable, plus three agentic attack surface commands.

A clean result maps to DBotScore Unknown, never Good.

blog.relayshield.net/cortex-xsoar-dbotscore-good

#CortexXSOAR #SOAR #infosec #ThreatIntel

(Four hashtags, all lower-risk. Mastodon hashtags are how people find posts here, so they are
worth the space.)

---

## 7. Palo Alto LIVEcommunity (optional, read their rules first)

`live.paloaltonetworks.com` hosts the Cortex XSOAR community boards. This is the single channel
most likely to reach the exact audience, and also the one most likely to remove a post that reads
as an advertisement. **UNVERIFIED from the container: the host is egress-blocked, so the board
name, the self-promotion rules and the posting flow have NOT been read.** Read them first; the
FD-2 lesson is that a route can be closed by its own published rules.

If it is allowed, the post is a question rather than an announcement, because that is the form
the community rewards:

Title: `A reputation integration that returns DBotScore 0 (Unknown) for a clean result, never 1 (Good). Reasonable or not?`

Body: two sentences on the design decision (the mapping table, why "no known finding" is not
"verified safe"), one line saying the integration is RelayShield's content pack and linking the
integration reference, and the canonical for the rest. Ask practitioners whether they would prefer
Good for a clean result from a corpus that is not a safelist. Disclose affiliation in the first line.

Key: `xsoar-livecommunity`.

**POSTED 2026-10-02**: https://live.paloaltonetworks.com/t5/cortex-xsoar-discussions/should-a-reputation-integration-return-dbotscore-0-unknown-for-a/m-p/1265516#M4277
No tagged link was included, so the key logs nothing; judge by replies.

---

## 8. Reddit (optional, strict rules, probably skip)

Candidates, ALL UNVERIFIED from here (reddit.com is not reachable from the container): the XSOAR /
Cortex community subreddit if one exists, `r/cybersecurity`, `r/netsec`. `r/netsec` is for technical
content and will remove product announcements; `r/cybersecurity` limits self-promotion by ratio.

**Recommendation: skip Reddit for this post.** The first post from a new account about its own
product is the pattern both communities remove, and the benefit (a few clicks) does not justify a
ban on an account we may want later for a technical post. If it is ever done, post the DBotScore
argument as a discussion, from an account with prior non-promotional history, with disclosure.
Key if used: `xsoar-reddit`.

---

## Measurement

Take a baseline before the first post and compare after:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 14 --key xsoar-post

That counts the landing-page banner, which every `xsoar-*` key resolves to. UNVERIFIED that the
tool reads aliased keys separately by raw key; it prints `unmatched:` rows first if any key above
failed to register.

**What a zero means:** more likely that this audience reads the blog and goes straight to their own
tenant than that the post failed. An XSOAR engineer's next action is "search RelayShield in my
Marketplace tab", which logs nothing on our side. So judge this post by the `?source=xsoar-*`
arrivals AND by whether any support inbound or key signup mentions XSOAR. A low arrival count is
expected for a topic whose conversion happens inside the reader's own tenant.
