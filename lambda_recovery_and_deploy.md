# Recovering the lost Telegram code, and deploying the intel monitor

*Written 2026-08-20.*

## 1. Is a faithful restore possible? Yes — three places to look, in this order

My earlier "not recoverable" was about **git**, and that part stands: the file entered the repo on
2026-07-30 with four commits, so no earlier help menu exists in history. But git is not the only
copy. Try these before accepting the reconstruction.

### (a) The Mac's own working tree — most likely, check first

`~/dev/relayshield` **is** the local clone. If the enhancements were edited there and never
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
`~/dev/relayshield/relayshield_telegram_webhook.py` from before 2026-08-19 is the last copy that
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

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
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
    python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3     # once
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py --pending

Read-only. Then activate the worthwhile ones:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py \
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

---

## 7. Cloudflare Worker drift — the TI demo (added 2026-08-23)

**The same drift class as the Lambdas, and there is no drift check for Workers at all.**

The deployed `relayshield-ti-demo` worker has **nine** tabs, including **Ransomware Victims**.
`cloudflare_worker_ti_demo.js` on `main` has **eight**, no `data-tab` attributes and no leak-site
markup. The tab was written and deployed by hand and never committed.

The red "The corpus-wide listing needs the next API deploy" banner is text in that **deployed**
worker, not in the repo and not in the API. It will keep showing until the worker is updated, no
matter what the API does.

### Recover the live worker before anything redeploys over it

Same rule as the Lambdas: `wrangler deploy` publishes from the repo and would delete whatever else
is live in that worker. **Do not deploy `cloudflare_worker_ti_demo.js` until the live copy is in
git.**

The sandbox cannot reach `*.workers.dev` (egress 403 on CONNECT), so this runs on the Mac:

    # Option 1 — Cloudflare API. Returns the deployed script body.
    curl -sS "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/relayshield-ti-demo" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -o live_ti_demo.js

    # Option 2 — dashboard, no token needed.
    # Workers & Pages -> relayshield-ti-demo -> Edit code -> select all -> save as live_ti_demo.js

Then diff it against the repo copy and commit the live version first:

    diff -u cloudflare_worker_ti_demo.js live_ti_demo.js | head -100

Commit the live bytes verbatim as their own commit, exactly as `relayshield_api.py` was recovered
on 2026-08-23, and only then apply changes on top.

### What the API now expects

`handle_ransomware_risk` supports the corpus-wide listing as of `fa83bb5`. Once the worker source
is in git, its `/demo/*` route for this tab needs to call the API with an empty or non-domain
`domain` and render:

    { "mode": "corpus_listing", "listing_available": bool, "count": n, "window_days": n,
      "victims": [ { "name", "seen_ts", "channel", "category", "confidence" } ],
      "confidence": "unverified", "disclaimer": "...", "truncated": bool }

`listing_available: false` means the victims table does not exist yet (see §6) — render
"nothing collected yet", not an error. The `disclaimer` field must be shown: every row is an
unverified lead, not a confirmed breach.

### Also worth doing

Extend `lambda_drift_check.yml`, or add a sibling, to diff deployed Workers against the repo. The
Lambda check would not have caught this because it only knows about Lambda functions, and the
worker drifted for the same reason the API did.
