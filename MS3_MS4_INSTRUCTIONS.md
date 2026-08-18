# MS-3 and MS-4: what is done, and what only you can do

Written 2026-08-18. Supersedes the 08-17 prep notes, which were lost with that session.

Sources checked this session:
[Security Store certification](https://learn.microsoft.com/en-us/security/store/partners/security-store-certification),
[publishing a Security Copilot agent](https://learn.microsoft.com/en-us/security/store/partners/publish-a-security-copilot-agent-or-analytics-solution-in-security-store),
[connector certification submission](https://learn.microsoft.com/en-us/connectors/custom-connectors/certification-submission),
[verified publisher process](https://learn.microsoft.com/en-us/connectors/custom-connectors/submit-for-certification).
`learn.microsoft.com` is blocked by this container's egress proxy, so these were read through search
result summaries and the mirrored `microsoft/PowerPlatformConnectors` README. **Confirm the exact
click paths against the live pages before you submit.**

---

## MS-4, Power Platform certification

### Correction, and it matters

**The requirement is not "120 API calls". It is at least 10 successful calls per operation.** The
connector has 12 operations, so 12 x 10 = 120. Those are not interchangeable: 120 calls spread
unevenly, or all against `/breach`, does **not** satisfy it and is a common cause of resubmission,
which is exactly the failure you wanted to avoid.

`certification_calls.py` issues exactly 10 per operation, with 10 distinct inputs each so they read
as genuine use rather than one payload replayed.

### Done this session

`powerplatform-connector/` is a complete, valid submission package:

| File | State |
|---|---|
| `apiDefinition.swagger.json` | 12 operations, valid Swagger 2.0, verified with `openapi-spec-validator` |
| `apiProperties.json` | API key auth, `iconBrandColor` `#0D0917` |
| `settings.json` | `paconn` settings |
| `icon.png` | 230x230, solid background matching the brand colour, no transparency |
| `intro.md` | The certification submission document |
| `README.md` | How the definition is derived, and how to regenerate it |
| `certcheck.py` | 0 failures, 0 warnings |
| `certification_calls.py` | Written, dry run confirmed, not executed |
| `generate_swagger.py` | Regenerates the definition from the live API contract |

The definition is **derived from `relayshield_openapi_spec.py`**, whose schemas are read off the real
handlers, so it cannot drift the way the old synthesised spec did. Regenerate, do not hand-edit.

**`ransomware-risk` is deliberately excluded from the 12.** Its upstream feed has been archived since
June 2025 and serves no 2026 records (INTEL-4-SOURCE). Shipping it into a Microsoft certification
review would mean submitting a knowingly dead data product. Do not add it back before the
`api.ransomware.live` migration lands.

### The 12 operations

breach, sim-swap, domain, oauth-watchlist, infostealer, supply-chain, secret-scan-text, session-risk,
identity-risk-score, cert-expiry, card-exposure, ip-intel.

Chosen for the Power Automate audience, which is IT operations rather than developers. **If the lost
08-17 package used a different 12, tell me and I will regenerate.** This set is a reconstruction that
reconciles to your 120 figure, not a recovered fact.

### Yours to run

**1. The 120 calls. Do this first, it gates everything else.**

```bash
cd powerplatform-connector
export RELAYSHIELD_API_KEY=<your key>
python3 certification_calls.py            # dry run, prints the plan
python3 certification_calls.py --run      # 120 billable calls, ~2 minutes at 1s spacing
```

**These are metered endpoints and every successful call is billable to your own account.** At
published PAYG rates the 12 operations span roughly $0.10 to $0.40 a call, so budget on the order of
$25 to $30. The script prints a per-operation tally at the end and exits non-zero if any operation is
short of 10, so you get a clear pass or fail rather than a guess.

**2. `paconn validate`.** I installed `paconn` 0.0.20 and ran it. **It requires a Power Platform
login**, so this is yours, not mine, contrary to the earlier split:

```bash
paconn login
cd powerplatform-connector
paconn validate --api-def apiDefinition.swagger.json
```

`certcheck.py` already passes and covers the offline rules, but it is not a substitute.

**3. Solution Checker.** Power Platform admin centre, on the solution containing the connector.

**4. Package zip and SAS URI.** Structure per Microsoft's docs: the two solutions go in a folder
named `PkgAssets`, that folder is zipped as `Packages.zip`, and `Packages.zip` plus `intro.md` go
into the final submission zip. Upload to Azure Blob Storage and generate a read-only SAS URI.
**No `az` CLI here and this container's cloud credentials are invalid**, so the upload is yours.
Use the portal if you would rather not install the CLI.

**5. The Premium tier decision. Irreversible.** Your prep doc flagged it: "The Premium tier can't be
removed or changed at any time." Decide deliberately before submitting, because it cannot be walked
back. Given every operation requires a paid API key, Premium is the consistent choice, but make it a
decision rather than a default.

---

## MS-3, Security Copilot agent in Security Store

Higher value than MS-4 and worth the sequencing priority. It puts RelayShield inside Microsoft's own
security surface, in front of SOC teams that already hold budget and a procurement path, and it is
the same buyer as Sentinel and QRadar, so it reinforces the enterprise motion instead of scattering
it.

### The chain, in order

1. **Partner Center account**, then **enrol in the Microsoft AI Cloud Partner Program (MAICPP)**.
   Your submitted MS Sales Partner application is very likely this step. **Confirm which programme
   it was**, because MAICPP enrolment is the actual gate and a different partner application will not
   substitute for it.
2. **Entra app registration**, giving the App ID the agent authenticates with.
3. **A SaaS offer in Partner Center.** Security Store lists solutions using the **SaaS offer type**.
4. **In Offer Setup, tick that the solution integrates with Microsoft Security services.** This is
   the step people miss. It reveals a Security Store metadata page that does not otherwise appear.
   Choosing **Deployable solution** makes the license management fields mandatory.
5. **Package the agent** as a `.zip` containing the agent manifest, plus any Sentinel Data Lake
   notebooks and Azure resources the agent needs.
6. **Certification.** Functional and quality tests: it must deploy, set up and run in a way that
   matches its description, use the Security Copilot agent platform properly, and meet Responsible AI
   standards.

### What I need from you to go further

The agent manifest is the real build and I cannot start it blind. Tell me:

- **Which programme the pending application actually is** (MAICPP or something else), and whether the
  Partner Center account already exists.
- **Which capabilities the agent should expose.** My recommendation is a deliberately narrow first
  agent over three operations, breach, session-risk and oauth-watchlist, since those are the three a
  SOC analyst would actually invoke mid-investigation, and a narrow agent passes functional review
  more easily than a broad one.
- **Whether an Entra app registration already exists**, and its App ID if so.

With those three answers the manifest and the offer metadata are both things I can draft.

---

## Blocked, and honestly so

Both tracks now converge on things that need an authenticated browser session as you, which this
container does not have and cannot get. The engineering is done as far as it can go without a login.
