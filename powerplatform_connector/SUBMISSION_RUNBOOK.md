# MS-4 submission runbook: Solution Checker, package zip, SAS URI

Written 2026-08-18. The three steps that need an authenticated session as you, in order. Steps 1 and
2 are Power Platform, step 3 is Azure.

**Gate, unchanged:** none of this can be submitted until the Partner Center seller account is
verified and enrolled in **Microsoft 365 and Copilot**. You can still do steps 1 to 3 while waiting,
and should, because step 1 uncovers rework.

**Verify the click paths against the live docs as you go.** `learn.microsoft.com` is blocked by this
container's egress policy, so the sequence below comes from the 2026-08-16 research in
`CERTIFICATION_PREP.md` plus the package layout Microsoft publishes. Menu labels drift.

---

## Step 0: the rework you already know about

The connector we built is **standalone**. Certification needs it created **inside a solution**. The
swagger imports identically so nothing is wasted, but it is a re-do and it comes first.

1. [make.powerapps.com](https://make.powerapps.com), pick the target environment (top right).
2. **Solutions** → **New solution**.
   - Display name: `RelayShield Connector`
   - Publisher: create one if you have none. **Use a real prefix, not `cr` or `new`** — the default
     `CDS Default Publisher` looks unfinished to a reviewer. Something like `relayshield` / `rsh`.
   - Version: `1.0.0.0`
3. Inside the solution: **New** → **Automation** → **Custom connector**.
4. In the connector editor, use the menu at the top right → **Import from OpenAPI file**, and select
   `powerplatform_connector/relayshield_swagger2.json`.
5. On the **General** tab, upload `powerplatform_connector/icon.png` and set the background colour to
   `#6c63ff` so it matches `apiProperties.json`.
6. **Security** tab: API key, header, parameter name `x-api-key`.
7. **Create connector**, then create a connection with a real key and run one operation from the
   **Test** tab to confirm the import worked end to end.

---

## Step 1: Solution Checker

Solution Checker runs against a **solution**, which is why step 0 comes first.

1. **Solutions** list → select `RelayShield Connector` (tick the row, do not open it).
2. Command bar → **Solution checker** → **Run**.
3. It queues, then takes a few minutes. The row shows a status; wait for it to finish rather than
   navigating away.
4. When it completes, **download the results** (`.sarif`, opens as a report). Keep the file: it is
   evidence for the submission, and you want the before/after if anything needs fixing.

**What it will and will not flag.** Solution Checker is aimed at apps, flows and plugins, so a
solution containing only a custom connector usually comes back clean or with informational notices.
**Treat any Critical or High as blocking.** Medium and Low are judgement calls; note them in the
submission rather than silently ignoring them.

If it reports nothing at all, confirm the run actually executed against the right solution. A check
that passes having inspected nothing is the failure mode this project keeps meeting.

---

## Step 2: the package zip

Microsoft wants **two** solutions, not one: the connector, and a flow that demonstrates it.

### 2a. Build the demonstration flow

1. **Solutions** → **New solution**, display name `RelayShield Connector Sample`, same publisher.
2. Inside it: **New** → **Automation** → **Cloud flow** → **Instant**.
3. Trigger: **Manually trigger a flow**, with a text input named `Email`.
4. Action: **RelayShield** → **Check an email for data breach exposure**, passing that input.
5. Add a terminating action a reviewer can read — a **Compose** on the response, or a condition that
   branches on the verdict. Something that shows the output being used, not just called.
6. **Save**, then **Test** it once so it has a successful run in its history.

Keep it genuinely small. This is a demonstration a reviewer runs, not a product.

### 2b. Export both

For each of the two solutions: select it → **Export solution** → **Managed** → **Export**. You get
two `.zip` files. **Managed, not Unmanaged** — this is the usual re-do.

### 2c. Assemble the layout

Microsoft's prescribed structure, exactly:

```
PkgAssets/
  RelayShieldConnector_1_0_0_0_managed.zip
  RelayShieldConnectorSample_1_0_0_0_managed.zip
```

Then:

```bash
# from the folder containing PkgAssets/
zip -r Packages.zip PkgAssets
zip -j RelayShield_submission.zip Packages.zip powerplatform_connector/intro.md
```

So the final artefact contains exactly two entries: `Packages.zip` and `intro.md`. Verify before
uploading:

```bash
unzip -l RelayShield_submission.zip     # expect: Packages.zip, intro.md
unzip -l Packages.zip                   # expect: PkgAssets/ with the two managed solutions
```

The `-j` on the second zip matters: without it `intro.md` lands under a
`powerplatform_connector/` path and the submission is rejected for a missing `intro.md`.

---

## Step 3: Azure blob and the SAS URI

New dependency. It is Azure spend that outlives the MS-1b teardown, so decide it deliberately: a
storage account holding one zip is pennies a month, but it is a live account to remember.

### Portal route, no CLI needed

1. [portal.azure.com](https://portal.azure.com) → **Storage accounts** → **Create**.
   - Resource group: new, `relayshield-marketplace`
   - Name: globally unique, lowercase, e.g. `relayshieldmp`
   - Redundancy: **LRS** is fine, this is a transient artefact
   - Leave the rest at defaults, **Review + create**
2. Open the account → **Containers** → **+ Container** → name `submissions` →
   access level **Private**. Private is correct: the SAS is what grants access.
3. Open the container → **Upload** → select `RelayShield_submission.zip`.
4. Click the blob → **Generate SAS** tab.
   - Permissions: **Read** only. Not Write, not Delete, not List.
   - Start: now, or a few minutes back if your clock might skew
   - Expiry: **at least 15 days**. Give it **30** — a resubmission inside a 15-day window would
     otherwise expire mid-review, and re-issuing means re-editing the offer.
   - Allowed protocols: **HTTPS only**
5. **Generate SAS token and URL**, copy the **Blob SAS URL** (the full `https://…?sv=…&sig=…`).

**Test it before pasting it into Partner Center**, from somewhere not signed into Azure:

```bash
curl -sSL -o /tmp/sas_check.zip "<paste the Blob SAS URL>"
unzip -l /tmp/sas_check.zip
```

If that fails, the URL is wrong and the reviewer will hit the same wall. This is the single most
common stall in the whole submission.

### CLI route, if you would rather

```bash
az storage blob generate-sas \
  --account-name relayshieldmp --container-name submissions \
  --name RelayShield_submission.zip \
  --permissions r --expiry "$(date -u -v+30d '+%Y-%m-%dT%H:%MZ')" \
  --https-only --full-uri --auth-mode login --as-user
```

`date -u -v+30d` is BSD date, correct on macOS. Requires the Azure CLI, which is not installed in
this container.

---

## Step 4: submit

Partner Center → **Marketplace offers** → **Microsoft 365 and Copilot** → **New offer** →
**Connectors & Agents in Microsoft Copilot Studio**. Paste the SAS URL, attach `intro.md` in the
activity control section, and submit.

**Then be ready.** Per the timeline in `CERTIFICATION_PREP.md`: Microsoft review is 24 to 48 hours,
then the preview environment is open for **48 business hours only**. Go-live to all regions runs 10
to 14 days after that, with deployments starting Friday PST. Do not start this the day before you
travel.

---

## The checks worth running before you begin

```bash
python3 tools/check_powerplatform_connector.py   # 11 rules, expects 0 failures
```

And two decisions that cannot be walked back once submitted:

- **Premium tier is permanent.** *"The Premium tier can't be removed or changed at any time."*
  Customers will need a Power Automate Premium licence, forever.
- **MS-4b.** `CheckRansomwareRisk` was migrated to a live feed on 2026-08-18, but the field mapping
  has not been confirmed against a real response. **Run the Lambda once and confirm
  `feed freshness OK` in the logs before this operation goes into a certified catalogue.**
