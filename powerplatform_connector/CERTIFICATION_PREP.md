# Power Platform connector certification: prep and gaps

Verified publisher track. Sourced from Microsoft's certification, submission and package docs on
2026-08-16, then checked against what we actually have rather than assumed.

**Gate:** everything below is blocked until the Partner Center **seller account is verified** and
enrolled in the **Microsoft 365 and Copilot** program. That is a different enrolment from MS-3's
Commercial Marketplace, but both hang off the same verified seller account, so the verification is
done once.

---

## Where we stand

| Requirement | Rule | Us |
|---|---|---|
| Title | Under 30 chars, no "API", "Connector" or product names | ✅ `RelayShield`, 11 chars |
| Description | 30 to 500 chars, English, no product names | ✅ 211 chars, re-corrected 2026-08-17 (dropped the phone claim with sim-swap) |
| Auth type | OAuth2, anonymous, API key or basic | ✅ API key, header |
| Support contact | Required | ✅ `support@relayshield.net` |
| Operation summaries | Under 80 chars, alphanumeric and parentheses only | ✅ all 11 |
| Response schemas | Exact, no empty schemas, no empty operations | ✅ |
| Swagger validity | OpenAPI 2.0 | ✅ generated, 0 leftover 3.x constructs |
| Production host URL | No staging or dev hosts | ✅ `api.relayshield.net` |
| Icon | See below | ✅ re-cut, **committed 2026-08-18** (was never committed on 08-16) |
| 10 successful calls per operation | **110 calls total (11 ops)** | ✅ **110/110 PASSED 2026-08-17** |
| Solution Checker run | Required | ✅ run 2026-08-18: 0 critical, 0 high, 1 medium (fixed), 0 low |
| `intro.md` | Required | ✅ written, in the package |
| Package zip + SAS URI | 15 day validity minimum | ❌ needs an Azure storage account |
| `ConnectorPackageValidator.ps1` | Required | ❌ needs PowerShell on macOS |

## CheckSimSwap REMOVED, 2026-08-17. Founder decision.

Measured, not assumed: a full 10-calls-per-operation run on 2026-08-17 returned **110/120**, with
**CheckSimSwap failing all 10** on `HTTP 503 "SIM swap data unavailable from the carrier (code
60606)"`. Twilio ticket **#28883049** has been open since 2026-08-08; their 2026-08-17 reply says
they are still "coordinating with the carriers", with no ETA.

Microsoft requires 10 **successful** calls per operation, so the connector could not have passed with
this operation present. It was removed from `relayshield_swagger2.json` rather than blocking MS-4 on
a third party indefinitely.

**The `info.description` was corrected at the same time.** It still promised "phone numbers", and no
remaining operation accepts one. An inaccurate description is itself a certification failure.

**Re-adding it later is a connector UPDATE, not a new submission.** If Twilio clears, restore the
path from `swagger2.bak.json`, re-run 10 calls against it, and publish an update.


## Two things that need fixing before anything else

### 1. The description overclaimed, and it is now corrected

The generated description read *"...against breach, infostealer and **criminal-marketplace** data"*.

Measured 2026-08-16: **98.3% of the corpus comes from public feeds** (abuse.ch, OpenPhish,
blocklist.de, PhishTank) and **1.67% from monitored Telegram channels**. Shipping the marketplace
framing into Microsoft's certified connector catalogue would put an overclaim somewhere permanent,
public and outside our control.

Now reads: *"...against breach records, infostealer logs and aggregated threat feeds"*. True, and it
still describes something worth buying. Fixed in the generator, so it cannot drift back.

### 2. The icon: FIXED 2026-08-16

The first attempt was a straight downscale of `relayshield_discord_app_icon_1024.png`. It was 1:1
and the right size, but the shield filled nearly the whole frame and sat on the source's **gradient**,
failing both the under-70% rule and the consistent-background rule.

Re-cut and verified against all eleven rules:

| | |
|---|---|
| Frame | 192x192, 1:1, inside the 100 to 230 range |
| Logo extent | **51% x 60%**, rule is under 70% |
| Background | flat `#6c63ff`, uniform on all four corners, opaque, not white, not `#007ee5` |
| Size | 11,582 bytes |

**How, because a luminance threshold alone was not enough.** Cutting on brightness kept a detached
patch of the source gradient that happened to be bright, which showed as a rectangle beside the
shield. A flood fill from the borders failed the other way and consumed the shield entirely, because
the gradient blends into it with no hard edge. What worked was building the luminance mask and then
keeping only the **largest connected component**: the shield is one contiguous mark, the artifact is
a separate blob, and connectivity separates them where a threshold could not.

## MS-4b: `CheckRansomwareRisk` was backed by a dead feed. FIXED 2026-08-18.

Found 2026-08-18, while re-checking the package after the session recovery.

`/v1/metered/ransomware-risk` is one of the 11 operations. It is backed by
`relayshield_intel_ransomware.py`, whose `RANSOMWATCH_URL` still points at
`joshhighet/ransomwatch`, **which is archived**. Its `posts.json` still serves 16,072 records so
every fetch returns HTTP 200, but the newest `discovered` value is **2025-06-16**. There are zero
2026 posts. None of the 37 recovered commits touched it, so INTEL-4-SOURCE is still open.

**This is the same class of problem as the criminal-marketplace overclaim, and it is worse.** That
one was a description that promised more than the corpus held. This is an operation that returns
`200 OK` with confident-looking output computed against data that stopped moving 14 months ago. A
certification reviewer will not catch it, because it responds correctly. Customers will not catch
it, because a stale feed looks exactly like a quiet week. It would sit in Microsoft's certified
catalogue, permanent and public and outside our control, which is precisely the reason the
description was corrected.

**Three options, in order of preference:**

1. **Migrate the feed first.** `https://api.ransomware.live/v2/recentvictims` is verified live and
   returned same-day records when checked. Swap the URL, map the response to
   `_extract_victim_domain`, keep the watermark logic unchanged. Then the operation is honest and
   the 11 stay 11.
2. **Remove the operation**, exactly as `CheckSimSwap` was removed, and re-add it as a connector
   update once the migration lands. Costs 10 of the 110 verified calls and drops to 10 operations.
3. **Ship it as is.** Not recommended. It also has revenue exposure beyond MS-4: `ransomware-risk`
   is a Bundle C dimension billed at $0.40 a call against the same dead feed.

**Option 1 was taken.** `relayshield_intel_ransomware.py` now reads
`https://api.ransomware.live/v2/recentvictims`, normalising `group`/`victim` onto the
`group_name`/`post_title` names the rest of the module already used, so the watermark, the alert
text and the DynamoDB writes are untouched.

Two things came with it:

- **A staleness guard.** `_warn_if_stale` logs an ERROR when the newest record is more than 14 days
  old. Record *count* is what made the dead feed look healthy; record *age* is the signal that
  actually distinguishes a live source from an archived one. Run against the old ransomwatch data it
  fires at 428 days.
- **A silent false negative, found while migrating.** `_find_monitored_users` matches
  `monitored_domain` with `eq()`, an exact compare, but `_extract_victim_domain` returned the
  hostname as written. A victim listed as `https://www.acme.com` produced `www.acme.com`, which never
  equals the `acme.com` a customer registered, so the CRITICAL ransomware alert did not fire.
  `_canonical_domain` now strips a leading `www.`. This affected every victim record with a `www`
  website, on the highest-severity path in the module.

`test_intel_ransomware.py` covers both, plus the field mapping and the `attackdate` fallback.

**Still to verify against the live endpoint:** this container's egress policy blocks
`api.ransomware.live`, so the field names come from the published API documentation rather than a
response we read. **Run the Lambda once and confirm `feed freshness OK` appears in the logs before
relying on it**, and confirm the record count looks sane.

## MS-4c: generator drift, found 2026-08-18 by running Solution Checker

Solution Checker returned **0 critical, 0 high, 1 medium, 0 low**. The medium was
`RequiredPropertyMissing`: `x-ms-connector-metadata` absent. Added at root level with Website,
Privacy policy and Categories `Security;IT Operations`, the same pair SOCRadar and Webhood URL Scan
use in `microsoft/PowerPlatformConnectors`.

**Fixing it exposed something worse.** `relayshield_swagger2.json` had been hand-edited on 08-17 and
`tools/build_powerplatform_connector.py` had not. Regenerating would have silently:

- **put `CheckSimSwap` back**, the operation removed because it failed all 10 calls on HTTP 503, and
- **restored "phone numbers"** to `info.description`, the overclaim removed with it.

The note above saying the description was "fixed in the generator, so it cannot drift back" was
wrong. It was fixed in the output only. Both are now fixed in the generator, and a regeneration
reproduces the shipped swagger byte for byte apart from the intended metadata addition.

`apiProperties.json` had the same problem in the other direction: `publisher` and `stackOwner` were
added by hand and would have been erased by the next run. Both now come from the generator.

**Root cause worth naming: the generator fetched the live spec over HTTP and nothing else.** That
made it unrunnable anywhere without egress to `api.relayshield.net`, so editing the output by hand
was the path of least resistance. It now falls back to `relayshield_openapi_spec.build_spec()`, the
same source the API serves from, and takes `--local` to force it.

`tools/check_powerplatform_connector.py` now asserts the metadata block, so this specific finding no
longer needs a cloud round-trip to catch.

## The step that will actually take time

> *"You tested your custom connector to ensure the operations work as expected (**at least 10
> successful calls per operation**)."*

**11 operations means 110 successful calls** (was 12/120 before CheckSimSwap was removed), and they must succeed, so they need a real API key with
an active metered subscription. Worth scripting rather than clicking, and worth doing early because
any operation that fails here is a resubmission.

## Package structure

Not a hand-assembled folder. Microsoft wants a solution export:

1. Create the custom connector **inside a solution** (not the standalone one we built today)
2. Run **Solution Checker** against it
3. Export the connector solution
4. Build a **test flow** using the connector, add it to a solution, export that too
5. Combine both solutions into a package
6. Write **`intro.md`**
7. Zip it in Microsoft's prescribed layout
8. Upload to **Azure blob storage** and generate a **SAS URI valid at least 15 days**
9. Submit in Partner Center: **Marketplace offers → Microsoft 365 and Copilot → New offer →
   Connectors & Agents in Microsoft Copilot Studio**

**Note the rework:** the connector we created today is standalone. Certification needs it created
inside a solution. Not wasted, since the swagger imports identically, but it is a re-do.

**New dependency:** an Azure storage account for the SAS URI. Small, but it is Azure spend that
survives the MS-1b teardown, so decide deliberately rather than discovering it.

**macOS:** the validator is PowerShell. `ConnectorPackageValidator.ps1` needs PowerShell installed
on macOS. Same class of environment friction as the Snap build path.

## `intro.md` outline

Model it on the AzureKeyVault Readme in the PowerPlatformConnectors repo. Sections:

- What RelayShield is, in two sentences, matching the corrected description
- **Prerequisites**: a RelayShield API key with a metered subscription, and where to get one
- **How to get credentials**: the developer signup path
- **Actions**: all 12, one line each, matching the swagger summaries
- **Known issues and limitations**: Microsoft explicitly recommends this section. Be straight here.
  Candidates: PAYG endpoints are not exposed by this connector because they settle in USDC; the
  connector is Premium tier, which is not optional and cannot later be changed
- Links to any walkthrough content we publish

## Open-sourcing

Submission requires opening the connector files in
`github.com/microsoft/PowerPlatformConnectors`. Only the connector artifacts, not the API. We get
CODEOWNERS on our own connector, so future updates stay ours.

## Timeline, once verification clears

| Stage | Duration |
|---|---|
| Package prep and 120 test calls | Ours |
| Microsoft review | 24 to 48 hours |
| Preview environment testing | **48 business hours only**, be ready |
| Go live to all regions | 10 to 14 days, deployments start Friday PST |

**Realistically 3 to 4 weeks** from verification to live everywhere.

**Irreversible:** *"The Premium tier can't be removed or changed at any time."* Customers will need
a Power Automate Premium licence, permanently.
