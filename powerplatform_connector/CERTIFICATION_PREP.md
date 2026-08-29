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
| Description | 30 to 500 chars, English, no product names | ✅ 228 chars, corrected 2026-08-16 |
| Auth type | OAuth2, anonymous, API key or basic | ✅ API key, header |
| Support contact | Required | ✅ `support@relayshield.net` |
| Operation summaries | Under 80 chars, alphanumeric and parentheses only | ✅ all 12 |
| Response schemas | Exact, no empty schemas, no empty operations | ✅ |
| Swagger validity | OpenAPI 2.0 | ✅ generated, 0 leftover 3.x constructs |
| Production host URL | No staging or dev hosts | ✅ `api.relayshield.net` |
| Icon | See below | ✅ **re-cut 2026-08-16, all 11 rules pass** |
| 10 successful calls per operation | 120 calls total | ❌ needs a metered key |
| Solution Checker run | Required | ❌ not run |
| `intro.md` | Required | ❌ not written |
| Package zip + SAS URI | 15 day validity minimum | ❌ needs an Azure storage account |
| `ConnectorPackageValidator.ps1` | Required | ❌ needs PowerShell on macOS |

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

## The step that will actually take time

> *"You tested your custom connector to ensure the operations work as expected (**at least 10
> successful calls per operation**)."*

**12 operations means 120 successful calls**, and they must succeed, so they need a real API key with
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
