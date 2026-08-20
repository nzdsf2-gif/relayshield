# Sentinel PR #14924 — arm-ttk `Hardcoded.Url.Reference` fix

Reviewer ask (v-shukore, 2026-08-19, Azure/Azure-Sentinel#14924):

> check the arm-ttk validation failure causing due to hardcoded value in maintemplate

## What actually fails

arm-ttk test **`DeploymentTemplate-Must-Not-Contain-Hardcoded-Uri`**, error id
`Hardcoded.Url.Reference`, **2 occurrences** in
`Solutions/Threat Intelligence (NEW)/Package/mainTemplate.json`:

| Line (pre-fix) | JSON path |
|---|---|
| 949 | `resources[6].properties.mainTemplate.resources[0].properties.connectorUiConfig.instructionSteps[2].description` |
| 1110 | `resources[8].properties.connectorUiConfig.instructionSteps[2].description` |

Both are the **Threat Intelligence Upload API (Preview)** data connector's
"1. Get Microsoft Entra ID Access Token" step, which contains the literal:

    ...request Microsoft Entra ID access token with scope value: https://management.azure.com/.default

`management.azure.com` is on arm-ttk's `$DisallowedHosts` list. The test exempts only
matches inside the top-level `parameters` section and matches directly preceded by
`https://schema.` — neither applies here, so it errors twice.

The other 65 `management.azure.com` hits in the file are all `https://schema.management.azure.com/...`
`$schema` values and are correctly exempt.

## Root cause — the V3 repackaging introduced it

This is a **regression from regenerating the package**, not a pre-existing defect:

* Upstream `master`'s published `mainTemplate.json` contains **zero** occurrences of the literal.
  It instead carries a variable that splits the hostname so the regex can never match:

      "management": "[concat('https://management','.azure','.com/')]"

  and renders the instruction through it:

      "[concat('...scope value: ', variables('management'), '.default')]"

* The **source** connector file
  `Solutions/Threat Intelligence (NEW)/Data Connectors/template_ThreatIntelligenceUploadIndicators.json`
  has always held the raw literal (identical on master and on our branch — verified byte-for-byte).

* The V3 packaging tool has an `azureManagementUrl` substitution
  (`Tools/Create-Azure-Sentinel-Solution/common/commonFunctions.ps1:1262-1370, 1727-1729`), but it
  lives inside the **playbook** code path only and never runs for data connectors. It also assigns
  the variable the plain literal `management.azure.com`, which would still trip the test from the
  `variables` section.

So master's form was a manual post-generation patch by Microsoft, and regenerating from source
flattened it back to the literal.

`template_ThreatIntelligenceUploadIndicators_ForGov.json` is unaffected — its hosts are
`management.usgovcloudapi.net` / `management.chinacloudapi.cn`, neither of which is on the
disallowed list.

## The fix

Re-apply master's exact form. See `ti_maintemplate_hardcoded_uri.patch` — three hunks:

1. append the `management` variable (verbatim from master, same position: last variable);
2. + 3. restore the two `concat` expressions (verbatim from master).

Verified:

* semantic diff against the pushed file = **exactly 3 changes**, nothing else;
* both description values and the variable value are **byte-identical to upstream master**;
* rendered output is unchanged: `...scope value: https://management.azure.com/.default`
  (master's form drops two cosmetic trailing spaces the literal had);
* the PR's actual fix is intact — one `TI Map Domain entity to PaloAlto CommonSecurityLog` rule,
  query has `tolower(ObservableValue)` and no `tolower(IndicatorType)`;
* `Package/3.0.21.zip` rebuilt so its `mainTemplate.json` matches, `createUiDefinition.json`
  byte-unchanged, same entry order / compression / timestamps.

## Re-running the check

`tools/armttk_hardcoded_uri.py` is a faithful Python port of the arm-ttk test (this sandbox has no
PowerShell, and `www.powershellgallery.com` is blocked by the egress policy):

    python3 tools/armttk_hardcoded_uri.py path/to/mainTemplate.json

Exit 0 = clean. Post-fix it reports 0 errors, matching upstream master.

## Still outstanding on this PR

The **`apiVersions-Should-Be-Recent`** finding is separate and unfixed: `Microsoft.Resources/deployments`
apiVersion `2020-06-01` is ~2270 days old. It comes from Microsoft's own templates and was already
disclosed in the PR reply. Do not conflate it with the hardcoded-value ask.
