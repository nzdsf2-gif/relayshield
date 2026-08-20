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

    aws lambda list-versions-by-function \
      --function-name relayshield-telegram-webhook \
      --region us-east-1 --query 'Versions[].[Version,LastModified]' --output table

If that shows anything other than just `$LATEST`, download the one dated **before 2026-08-19**:

    aws lambda get-function \
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

### Check first (one command)

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
    aws lambda update-function-code \
      --function-name relayshield-intel-monitor \
      --zip-file fileb:///tmp/intel.zip --region us-east-1
    aws lambda wait function-updated --function-name relayshield-intel-monitor --region us-east-1

Then import-probe it, the same way CI does — a successful upload only means the bytes landed:

    aws lambda invoke --function-name relayshield-intel-monitor \
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
