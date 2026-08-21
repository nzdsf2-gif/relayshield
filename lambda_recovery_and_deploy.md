# Recovering the lost Telegram code, and deploying the intel monitor

*Written 2026-08-20.*

## 1. Is a faithful restore possible? Yes — three places to look, in this order

My earlier "not recoverable" was about **git**, and that part stands: the file entered the repo on
2026-07-30 with four commits, so no earlier help menu exists in history. But git is not the only
copy. Try these before accepting the reconstruction.

### (a) The Mac's own working tree — most likely, check first

`~/Side SaaS Hustle` **is** the local clone. If the enhancements were edited there and never
committed, the changes may literally still be sitting in the working tree, a stash, or a dangling
commit.

    cd "$HOME/Side SaaS Hustle"

    # uncommitted edits still on disk?
    git status --short relayshield_telegram_webhook.py
    git diff -- relayshield_telegram_webhook.py | head -100

    # stashed?
    git stash list
    git stash show -p 2>/dev/null | head -100

    # committed locally but never pushed?
    git log --oneline origin/main..HEAD -- relayshield_telegram_webhook.py

    # orphaned by a checkout/reset — the reflog remembers what branches forget
    git reflog --date=short | head -40
    git fsck --lost-found 2>/dev/null | grep commit | head

If any of those show the shortcut code, that IS the faithful restore.

### (b) The live Lambda's own package — only helps if it predates the overwrite

Lambda keeps the *current* `$LATEST` package, plus any **published versions**. CI never publishes
(`update-function-code` runs without `--publish`), so versions exist only if they were published by
hand.

    AWS_PROFILE=relayshield aws lambda list-versions-by-function \
      --function-name relayshield-telegram-webhook \
      --region us-east-1 --query 'Versions[].[Version,LastModified]' --output table

If that shows anything other than just `$LATEST`, download the one dated **before 2026-08-19**:

    AWS_PROFILE=relayshield aws lambda get-function \
      --function-name relayshield-telegram-webhook:<VERSION> \
      --region us-east-1 --query 'Code.Location' --output text
    # then curl that URL and unzip

**Caveat, and it is the whole ballgame:** `$LATEST` was overwritten on 2026-08-19 and again by
today's deploy. Only a *published version* preserves older code. If the list shows `$LATEST` alone,
Lambda has nothing older and this route is closed.

### (c) Time Machine / local backups on the Mac

If (a) and (b) come up empty, a Time Machine snapshot of
`~/Side SaaS Hustle/relayshield_telegram_webhook.py` from before 2026-08-19 is the last copy that
could exist.

**If all three are empty, the reconstruction now on `main` is the only version there is** — which is
why it is worth checking against memory rather than assumed correct.

## 2. Telegram: DEPLOYED

Merge `ce1a6fe` → run **32413731965**, `✅ relayshield-telegram-webhook imports cleanly`. Live now.

## 3. Intel monitor: NOT deployed, and it has no CI path at all

**`relayshield_intel_monitor.py` is not in `deploy_lambdas.yml`** — not in the path filter, not in
the function map. The function `relayshield-intel-monitor` exists (other workflows read its logs and
invoke it), but **nothing in CI has ever deployed its code**. It is hand-deployed, which is exactly
the condition that produced the Telegram loss.

I did not add it to the workflow blind. `update-function-code --zip-file` **replaces the entire
package**, so if that function vendors its third-party deps (telethon) inside the zip rather than
using a layer, an automated handler-only deploy would delete them and break live intel collection.
That is not a risk worth taking unverified.

### FIRST: you were pointed at the wrong AWS account

The `ResourceNotFoundException` on 2026-08-20 named
`arn:aws:lambda:us-east-1:**620534471984**:function:relayshield-intel-monitor`.

**RelayShield's Lambdas are in account `239677749008`** — that is the account in
`deploy_lambdas.yml`'s OIDC role ARN, in the KMS key ARNs, and on the AWS Marketplace listing.
`620534471984` is a different account that your *default* credentials resolve to.

**The function is not missing. You were looking in the wrong account.** Prefix with the profile —
the same one the handoff uses everywhere else:

    AWS_PROFILE=relayshield aws sts get-caller-identity     # expect Account: 239677749008

Once that returns `239677749008`, re-run the real check:

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
      --function-name relayshield-intel-monitor --region us-east-1 \
      --query '{Layers:Layers[].Arn, Runtime:Runtime, CodeSize:CodeSize}'

**Add `AWS_PROFILE=relayshield` to every command in this file.** The earlier ones omitted it, which
is what produced the error.

### Then check the packaging

    aws lambda get-function-configuration \
      --function-name relayshield-intel-monitor --region us-east-1 \
      --query '{Layers:Layers[].Arn, Runtime:Runtime, CodeSize:CodeSize}'

* **Layers listed and CodeSize small (< ~1 MB)** → deps are in a layer. Safe to deploy the handler
  alone, and safe to add to CI.
* **No layers and CodeSize large (tens of MB)** → deps are vendored in the package. A handler-only
  deploy would break it; the zip must be rebuilt with the deps included.

### Deploy it (after the check says layers)

    cd "$HOME/Side SaaS Hustle"
    git pull origin main
    zip -j /tmp/intel.zip relayshield_intel_monitor.py
    AWS_PROFILE=relayshield aws lambda update-function-code \
      --function-name relayshield-intel-monitor \
      --zip-file fileb:///tmp/intel.zip --region us-east-1
    AWS_PROFILE=relayshield aws lambda wait function-updated --function-name relayshield-intel-monitor --region us-east-1

Then import-probe it, the same way CI does — a successful upload only means the bytes landed:

    AWS_PROFILE=relayshield aws lambda invoke --function-name relayshield-intel-monitor \
      --payload '{"dry_run":true}' --cli-binary-format raw-in-base64-out \
      --region us-east-1 /tmp/out.json >/dev/null
    grep -qi "ImportModuleError\|No module named" /tmp/out.json \
      && echo "BROKEN — roll back" || echo "imports cleanly"

**Then add it to CI.** Once the check above confirms layers, add
`relayshield_intel_monitor.py` to `deploy_lambdas.yml`'s path filter and to its `FUNCS` map as
`relayshield-intel-monitor`, so it never has to be hand-deployed again.

## 4. Triage the 75 pending channels

    cd "$HOME/Side SaaS Hustle" && git pull origin main
    python3 -m venv /tmp/rsvenv && /tmp/rsvenv/bin/pip install boto3     # once
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/triage_channels.py --pending

Read-only. Then activate the worthwhile ones:

    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/triage_channels.py \
      --activate name1,name2,name3 --apply

## 5. How this stops happening — `lambda_drift_check.yml`

Added and on `main`. Daily at 13:00 UTC it pulls each live function's deployment package, diffs the
handler against `main`, and **opens an issue on any mismatch**. It covers `relayshield-intel-monitor`
deliberately, precisely because that one has no CI deploy and is therefore the likeliest to drift.

The failure was never the deploy. It was that live and repo code could disagree for weeks with
nothing anywhere saying so. Now the disagreement surfaces within a day, and the issue text says to
**recover from the live function before anything redeploys over it.**

**One thing to confirm:** the OIDC role `relayshield-github-deploy` needs `lambda:GetFunction` and
`lambda:GetFunctionConfiguration`. It has deploy rights, so it very likely has these, but the first
scheduled run will log a warning per function if not.


---

## 6. Create the ransomware victim table (2026-08-20)

The victim-tracking code is on `main` and writes to `relayshield_ransomware_victims`, which does not
exist yet. Create it before the next intel deploy, or every write fails (logged as a warning, not a
crash — collection continues, victims are simply dropped).

    AWS_PROFILE=relayshield aws dynamodb create-table \
      --table-name relayshield_ransomware_victims \
      --attribute-definitions AttributeName=victim_name,AttributeType=S \
                              AttributeName=seen_ts,AttributeType=S \
      --key-schema AttributeName=victim_name,KeyType=HASH \
                   AttributeName=seen_ts,KeyType=RANGE \
      --billing-mode PAY_PER_REQUEST \
      --region us-east-1

    AWS_PROFILE=relayshield aws dynamodb update-time-to-live \
      --table-name relayshield_ransomware_victims \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --region us-east-1

Same key shape and TTL attribute as `relayshield_intel_iocs`, so the exporter and any future tooling
behave the same way against it.

Confirm it went ACTIVE before moving on:

    AWS_PROFILE=relayshield aws dynamodb describe-table \
      --table-name relayshield_ransomware_victims \
      --region us-east-1 \
      --query "Table.TableStatus"

### 6a. Grant the two IAM permissions — creating the table does NOT grant them

**Both failure modes are silent.** The monitor logs a warning and keeps collecting, so victims are
dropped with a green run; the API returns an error the demo renders as "temporarily unavailable".
Neither looks like a permissions problem from the outside, so do both now and verify both.

The role names are not written down anywhere, so read them off the functions rather than guessing:

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
      --function-name relayshield-intel-monitor --region us-east-1 --query Role --output text

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
      --function-name relayshield-api --region us-east-1 --query Role --output text

Each prints an ARN ending in `role/<NAME>`. Use that `<NAME>` below.

**Write, for the intel monitor** — policy body in `iam_ransomware_victims_policy.json`:

    AWS_PROFILE=relayshield aws iam put-role-policy \
      --role-name <INTEL_MONITOR_ROLE_NAME> \
      --policy-name relayshield-ransomware-victims-write \
      --policy-document file://iam_ransomware_victims_policy.json

**Read, for the API** — needed by `/v1/intel/ransomware`, which the TI demo's Ransomware Victims tab
calls. Policy body in `iam_api_read_victims_policy.json`:

    AWS_PROFILE=relayshield aws iam put-role-policy \
      --role-name <API_ROLE_NAME> \
      --policy-name relayshield-ransomware-victims-read \
      --policy-document file://iam_api_read_victims_policy.json

Both policies are scoped to the one table ARN in account `239677749008`. They add nothing else.

### 6b. Verify — do not trust a clean deploy

Prove the write path end to end, rather than waiting for the next scheduled run to maybe work:

    AWS_PROFILE=relayshield aws dynamodb put-item \
      --table-name relayshield_ransomware_victims \
      --item '{"victim_name":{"S":"rs-selftest"},"seen_ts":{"S":"2026-08-21T00:00:00+00:00"},"display_name":{"S":"RS Selftest"},"match_keys":{"L":[{"S":"rsselftest"}]},"channel":{"S":"selftest"},"category":{"S":"ransomware"},"confidence":{"S":"unverified"}}' \
      --region us-east-1

    AWS_PROFILE=relayshield aws dynamodb delete-item \
      --table-name relayshield_ransomware_victims \
      --key '{"victim_name":{"S":"rs-selftest"},"seen_ts":{"S":"2026-08-21T00:00:00+00:00"}}' \
      --region us-east-1

Then, after the next intel run, confirm real rows are landing:

    AWS_PROFILE=relayshield aws dynamodb scan \
      --table-name relayshield_ransomware_victims \
      --region us-east-1 --select COUNT

The admin digest's `Ransomware victims named: N (M stored)` line is the other read on this. **N large
and M zero is the permissions failure**, not a quiet week.

### 6c. The TI demo tab

`/v1/intel/ransomware` and the demo's **Ransomware Victims** tab ship with the repo (API in
`relayshield_api.py`, tab in `cloudflare_worker_ti_demo.js`). The API deploys through
`deploy_lambdas.yml`; the Worker does not, and needs:

    npx wrangler deploy --config wrangler.ti-demo.toml

The tab is behind the same `DEMO_TOKEN` gate as every other `/demo/*` route — no new ungated path
was added. **It shows nothing until the table has data**, so run the steps above first; before then
it renders the "not yet available" state rather than an empty list, which is the honest answer but
not a demo.

**The panel leads with an unverified-leads caveat and it must stay there.** Extraction is a regex
over leak-site posts; the list will contain false positives, and a prospect screenshotting the tab
must screenshot the caveat with it.

## 7. Create the operator identity table (2026-08-21)

Growth plan item 2. Same silent-failure shape as the victim table — writes log a warning and
collection continues, so the first sign of trouble is a digest line stuck at zero.

    AWS_PROFILE=relayshield aws dynamodb create-table \
      --table-name relayshield_operator_identities \
      --attribute-definitions AttributeName=handle,AttributeType=S \
                              AttributeName=platform,AttributeType=S \
      --key-schema AttributeName=handle,KeyType=HASH \
                   AttributeName=platform,KeyType=RANGE \
      --billing-mode PAY_PER_REQUEST \
      --region us-east-1

    AWS_PROFILE=relayshield aws dynamodb update-time-to-live \
      --table-name relayshield_operator_identities \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --region us-east-1

Then grant the intel monitor's role `dynamodb:UpdateItem` on it — **UpdateItem, not PutItem**: the
writer uses `if_not_exists` + `ADD` so DynamoDB maintains `first_seen` and the counters server-side.
Role discovery is in §6a.

    AWS_PROFILE=relayshield aws iam put-role-policy \
      --role-name <INTEL_MONITOR_ROLE_NAME> \
      --policy-name relayshield-operator-identities-write \
      --policy-document file://iam_operator_identities_policy.json

Confirm with the digest's `Operator identities: N updated` line after the next run.

## 8. Switching on pivot enrichment (2026-08-21)

Growth plan item 3, and **off unless you turn it on**. It is the only outbound call this monitor
makes to a host other than Telegram, so a slow crt.sh inside the run budget costs collection.

    AWS_PROFILE=relayshield aws lambda update-function-configuration \
      --function-name relayshield-intel-monitor \
      --environment "Variables={PIVOT_ENRICHMENT=1}" \
      --region us-east-1

**`update-function-configuration --environment` REPLACES the whole variable map.** Read the current
one first and merge, or you will silently drop every other variable the function needs:

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
      --function-name relayshield-intel-monitor --region us-east-1 --query Environment.Variables

Tunable, all optional: `PIVOT_MAX_SEEDS` (15), `PIVOT_MAX_DERIVED` (25), `PIVOT_TIME_BUDGET` (60s).

**Watch the first two runs for total duration**, then check that derived rows carry
`provenance="derived"` and `confidence_score` 0.5. If run time moves materially, turn it back off —
collection is the job.

### Opting a customer into supplier-breach alerts

Alerts are **off unless a customer explicitly lists suppliers**. There is no inference — nothing is
derived from their domain or company name, deliberately.

    AWS_PROFILE=relayshield aws dynamodb update-item \
      --table-name relayshield_users \
      --key '{"user_id":{"S":"<USER_ID>"}}' \
      --update-expression "SET supplier_watchlist = :s" \
      --expression-attribute-values '{":s":{"L":[{"S":"Acme Corp"},{"S":"Contoso"}]}}' \
      --region us-east-1

Enter each supplier **as its name appears on leak sites**. Matching is exact on a normalised key,
with corporate suffixes stripped, so "Acme Corp" matches "Acme", "Acme Corp." and "Acme
Corporation" — but *not* "Acme Technologies", which is a different company. A longer, more
descriptive name than the leak site uses will not match.
