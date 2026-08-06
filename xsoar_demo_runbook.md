# XSOAR demo, click-by-click runbook

Companion to `xsoar_demo_script.md`. That file is **what to say**; this one is **what to click**.
Written for a first-time XSOAR tenant.

**Convention below:** anything in a `>` block is a line to read aloud. Everything else is an action.

---

## Part 0: before you open the recorder

### 0.1 Confirm the tenant is real

Log in to the Cortex XSOAR tenant. You should land on a dark UI with a **left sidebar**. The items
you need are all in that sidebar:

- **Settings** (gear icon, usually bottom-left)
- **Playground** (under Incidents, or via the search bar at top)

If the tenant is a Cortex XSIAM or Cortex Cloud console rather than classic XSOAR, the demo still
works but menu names differ. Tell Moshe which one you got, because his instructions assume classic.

### 0.2 Install the pack from the PR, not from Marketplace

This matters. The Marketplace copy is not your PR.

1. Sidebar, **Marketplace**.
2. There is no published RelayShield pack yet, so you cannot install it there.
3. Instead use the **contribution flow**: Marketplace, then look for **"Contribute"** or install by
   uploading the pack zip built from the PR branch.

**If that path is unclear in the UI, this is question one for Moshe.** He does pack demos constantly
and will tell you the fastest route to get a PR's pack onto a tenant. Do not burn an hour guessing.

### 0.3 Have these ready in a text file, to paste

```
https://api.relayshield.net
```

Your real API key, and a deliberately broken one:

```
rs_live_invalidkeyfortesting0000000
```

Three commands:

```
!relayshield-mcp-registry-risk server_url=https://api.relayshield.net
!relayshield-cert-expiry domain=relayshield.net
!relayshield-supply-chain domains=relayshield.net,example.com
```

### 0.4 Dry run every command once, recorder OFF

Run all three. Confirm each returns data rather than an error. If one misbehaves you want to find
out now.

### 0.5 Re-verify the two numbers you will say out loud

```bash
AWS_PROFILE=relayshield aws dynamodb describe-table --table-name relayshield_intel_iocs --query 'Table.ItemCount'
```

On 2026-08-05 that was 5,027,104, so "roughly 5 million". Channel count was 85 from that day's
monitor run. **Do not read these from any listing or the MSP brief**; four of those surfaces were
wrong until today.

---

## Part 1: configure the integration (record this)

**Click path:** Settings, then **Integrations**, then **Instances** tab. Search `RelayShield` in the
search box. Click **Add instance**.

A right-hand panel slides out with the configuration form. It has four fields, matching the YAML:

| Field | What to enter |
|---|---|
| Server URL | `https://api.relayshield.net` |
| API Key | your real key (this is a credentials field, so it renders masked) |
| Trust any certificate | leave **unchecked** |
| Use system proxy | leave **unchecked** |

> This is the whole configuration. Server URL and an API key. The key field is a credentials type, so
> XSOAR stores it encrypted and never displays it back.
>
> You get a key from api.relayshield.net/developers. There is a free tier of twenty calls with no
> card, which means a reviewer or a customer can validate this pack end to end without talking to
> sales first.

Click **Test**. Wait for the green **Success** toast.

> Test passes, so the credential works and the API is reachable.

**Do not click Save and exit yet.** The next section reuses this panel.

---

## Part 2: error handling on invalid credentials (record this)

**This is the section reviewers care most about. Do not skip or rush it.**

In the same panel, select the API Key field, delete the value, paste the broken key, click **Test**.

You should see a red failure banner carrying the API's own message:

```
Invalid or missing API key. Pass your key as X-RS-API-KEY header.
```

> A bad key produces the API's own message, not a stack trace and not a 500. The error names the
> header it expected and points at the docs. That is what an analyst sees if the key is rotated or
> mistyped.

Now restore the real key, click **Test** again, show green, then click **Save & exit**.

> Back to a working instance.

---

## Part 3: run the three commands (record this)

**Click path:** sidebar, **Playground**. If you cannot see it, use the top search bar and type
"Playground". You get a chat-style box at the bottom, labelled something like "Type a message".

For **each** of the three commands:

1. Paste the command, press Enter.
2. Wait for the result card to render.
3. Read the human-readable output on screen.
4. **Click the `{}` context icon**, or the "War Room" / "Context Data" toggle in that result card, to
   expand the raw context. This is the bit reviewers want to see, because it proves the context paths
   match the YAML.

### Command 1

```
!relayshield-mcp-registry-risk server_url=https://api.relayshield.net
```

> This is the check an AI agent should run before it connects to an MCP server. Is it a typosquat,
> newly registered, or already in a criminal IOC corpus. Context lands under
> RelayShield.MCPRegistryRisk, with queried, verdict and findings.

### Command 2

```
!relayshield-cert-expiry domain=relayshield.net
```

> TLS certificate expiry from Certificate Transparency logs. Context is
> RelayShield.CertExpiry: domain, days_remaining, risk_level.

### Command 3

```
!relayshield-supply-chain domains=relayshield.net,example.com
```

> Up to ten vendor domains in one call, combined breach and infostealer risk. Context is
> RelayShield.SupplyChain: domains_checked, highest_risk, critical_vendors.

Then say once, covering all three:

> Every argument and every output is described in the YAML and documented in the README. Outputs are
> namespaced under RelayShield dot command name, so nothing collides with another pack's context.

---

## Part 4: scope statement (record this, no clicking)

> One thing worth saying explicitly rather than waiting to be asked. This pack has no
> fetch-incidents, no playbooks, no layouts and no mirroring. It is deliberately a reputation and
> enrichment pack, three commands, following the one-pack-per-PR guidance. More commands are a
> natural fast-follow once this lands.

---

## Part 5: close (record this)

> That is the pack. All thirty-nine review threads are resolved and docs-approved is applied. The one
> red check, check_docs_approved_label_job, ran before that label existed, so a re-run should clear
> it. Happy to take anything else over the DFIR Slack.

Stop recording.

---

## Part 6: after

1. Watch it back once. Check the API key is never visible in plaintext.
2. Post it in the PR thread and on the PANW DFIR Slack.
3. Ask Moshe to re-run `check_docs_approved_label_job`.
4. Keep the file. It is reusable as collateral for the XSOAR listing.

---

## Things that could go wrong, and what to do

| Symptom | Cause | Fix |
|---|---|---|
| Cannot find RelayShield in Integrations | Pack not installed, or installed from Marketplace instead of the PR | See 0.2, ask Moshe |
| Test fails with a working key | Tenant egress restrictions | Try the command in Playground anyway; some tenants block the Test path but allow runtime |
| Command returns 402 | Key has no credits and is not on a subscription | Use a key with the TI plan, or top up |
| Command returns 429 | Free-tier 20 calls exhausted | Use your own full key, not a demo key |
| Context panel not visible | Wrong toggle | Look for `{}`, "Context Data", or expand the War Room entry |

## Not needed

The CLA question in the earlier script is **resolved**. `license/cla` reports
"Contributor License Agreement is signed." Ignore that paragraph.
