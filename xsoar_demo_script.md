# XSOAR demo recording script, PR #45206

**For MosheEichler, Palo Alto Networks. He confirmed a recording is acceptable, so record it rather
than booking a live session.** Agenda below follows `xsoar.pan.dev/docs/contributing/demo-prep`
item by item, in their order, so nothing gets asked afterwards.

## PR state, verified 2026-08-05

| | |
|---|---|
| Review threads | **39 total, 0 unresolved** |
| `docs-approved` label | **applied** (the old open item is closed) |
| Current label | **`pending-demo`** — this recording is the only gate |
| Failing check | `check_docs_approved_label_job`, **stale**: it ran before the label existed and has not re-run |
| Last activity | 2026-08-02, so it has been quiet three days |

**The one thing to look at before recording:** the CLA check shows no conclusion. Three of the four
commits are authored from `nzdsf2-gif@users.noreply.github.com`, but **"Add CONTRIBUTORS.json for
RelayShield pack" is authored from `nzdsf2@gmail.com`**. CLA-Assistant matches on commit email, and
an unlinked address is exactly how it silently fails to register a signature. Either add
`nzdsf2@gmail.com` to your GitHub account's verified emails, or re-sign the CLA. Worth resolving
before the demo so it does not become the next blocker.

---

## BLOCKER: you need a tenant, and only you can create it

The demo is performed **on a Cortex XSOAR instance running the pack**. RelayShield has no tenant.

**Sign up for Cortex XSOAR Community Edition** (free, 30-day full trial then a capped free tier):
`start.paloaltonetworks.lat/sign-up-for-community-edition`

This is an account signup, so it is yours to do. Everything below is ready the moment the tenant
exists.

Worth one question to Moshe first: **item 69's "Technical Partner" status may grant a better tenant
than Community Edition.** That was never researched, and asking costs one Slack message.

---

## What the pack actually contains

Three commands. Reputation-style commands only. **No fetch-incidents, no playbooks, no layouts, no
mirroring** — say this explicitly on the recording rather than waiting to be asked, since demo-prep
lists those and their absence is a deliberate scope choice, not an omission.

| Command | Arguments | Context outputs |
|---|---|---|
| `relayshield-mcp-registry-risk` | `server_url` **or** `package_name`, neither individually required | `RelayShield.MCPRegistryRisk.{queried,verdict,findings}` |
| `relayshield-cert-expiry` | `domain` | `RelayShield.CertExpiry.{domain,days_remaining,risk_level}` |
| `relayshield-supply-chain` | up to 10 vendor domains or emails | `RelayShield.SupplyChain.{domains_checked,highest_risk,critical_vendors}` |

Integration config: **Server URL**, **API Key** (type 9, credentials), **Trust any certificate**,
**Use system proxy**. Docker `demisto/python3:3.11.10.115186`, `fromversion: 6.8.0`.

**All three routes verified healthy in production 2026-08-05**: each returns HTTP 401 unauthenticated,
so the route exists and auth is enforced.

---

## Recording script

Target is well under the "up to an hour" they allow. Aim for 12 to 15 minutes. Screen share the
XSOAR UI throughout.

### 1. Product overview and use cases (about 2 min)

> RelayShield is a threat intelligence and identity risk API. This pack brings three checks into
> XSOAR that an analyst would otherwise do by hand or not at all.
>
> The use cases are deliberately narrow. First, before an AI agent connects to an MCP server, is that
> server a typosquat, newly registered, or already in a criminal IOC corpus. Second, is a domain's
> TLS certificate about to lapse. Third, given a list of vendor domains, which of them show breach or
> infostealer exposure right now.
>
> The backing corpus is roughly 5 million indicators with around 85 monitored criminal Telegram
> channels behind it.

**Verify both of those figures on the day.** Live count on 2026-08-05 was 5,027,104 and the monitor
reported 85 channels. Four public surfaces still quote between 4.4M and 4.9M, so do not read from
those.

### 2. Instance configuration, including credential retrieval (about 3 min)

Show the configuration screen and fill it in live.

> Server URL is `https://api.relayshield.net`. The API key goes in the credentials field, which is
> type 9, so XSOAR stores it encrypted and it is never echoed back.
>
> A key comes from `api.relayshield.net/developers`. There is a free tier of 20 calls with no card,
> which means a reviewer or a customer can validate this pack end to end without a commercial
> conversation.

Then click **Test** and show it going green.

### 3. Error handling on invalid credentials (about 2 min)

**Do not skip this. It is called out explicitly in demo-prep and it is the single most common reason
a pack demo gets a second round.**

Paste a deliberately wrong key, hit **Test**, and show the failure surfacing cleanly in the UI.

The API's actual response, verified 2026-08-05:

```json
{"ok": false, "error": "Invalid or missing API key. Pass your key as X-RS-API-KEY header.",
 "docs": "https://api.relayshield.net/developers"}
```

> The integration surfaces the API's own message rather than a stack trace, and it points at the docs
> URL. A wrong key produces a readable error, not a 500.

Then restore the good key and re-test to green.

### 4. The commands, one at a time (about 6 min)

For each: run it in the playground, show the human-readable output, then **expand the context data**
so they can see the paths match the YAML.

```
!relayshield-mcp-registry-risk server_url=https://api.relayshield.net
!relayshield-cert-expiry domain=relayshield.net
!relayshield-supply-chain domains=relayshield.net,example.com
```

Call out for each one:

> Arguments match the YAML. Outputs are namespaced under `RelayShield.<Command>` so they do not
> collide with any other pack's context. Every argument and every output has a description in the
> YAML, and the README documents the same set.

**Run these against production once before recording.** If any returns something odd, you want to
know before the camera is on, not during.

### 5. What this pack deliberately does not do (about 1 min)

> No fetch-incidents, no playbooks, no layouts, no mirroring. This is a reputation-and-enrichment
> pack, scoped to three commands on purpose. Following the one-pack-per-PR guidance, additional
> commands are a natural fast-follow once this lands.

### 6. Close

> Threads are all resolved, docs-approved is applied. Happy to take anything else over the DFIR
> Slack. The `check_docs_approved_label_job` failure is stale, it ran before the label was added and
> a re-run should clear it.

---

## Before you hit record

- Tenant exists and the pack is installed at its **latest** version from the PR.
- Both figures re-verified: IOC count and channel count.
- All three commands run clean against production with the real key.
- Good key and bad key both to hand, for section 3.
- CLA email question resolved, or at least a known answer if he asks.

## After

Post the recording in the PR thread and on the PANW DFIR Slack, and ask him to re-run
`check_docs_approved_label_job`. **Keep the file.** It is reusable as sales collateral for the
XSOAR listing, which is half the reason recording beats a live call.
