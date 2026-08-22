# Merge and deploy — step by step

*Written 2026-08-22. Follow top to bottom. Every step says exactly what to click.*

---

## Step 1 — Merge the branch (this is what you asked for)

**In your browser, on the repo:**

1. Click the **Pull requests** tab (top of the repo, next to Issues).
2. Click the green **New pull request** button.
3. You get two dropdowns reading `base: main` ← `compare: main`.
   Leave the **left** one as `main`. Click the **right** one (`compare`) and pick
   **`claude/daily-todo-summary-7zpsvv`**.
4. The page fills with the diff. Click **Create pull request**, then **Create pull request** again
   on the next screen.
5. On the PR page, click **Merge pull request** → **Confirm merge**.

That is it. Nothing gets renamed, nothing in Settings is touched.

**From the Mac instead, if you prefer:**

    cd ~/"Side SaaS Hustle"
    git fetch origin
    git checkout main
    git -c pull.rebase=false pull origin main
    git merge --no-ff origin/claude/daily-todo-summary-7zpsvv
    git push origin main

**What merging triggers automatically:** `relayshield-api` and `rs-discord-bot` redeploy via
`deploy_lambdas.yml`. Watch the **Actions** tab; it takes a couple of minutes.

---

## About the drift check "failure" — it was not a failure

Run **32601363705** did exactly what it is built to do. **The workflow exits 1 when it finds drift**
— that is the alarm, not a malfunction. A green run would mean live and `main` agree.

**One thing did not go as intended:** the run shows `head_branch: main`. The branch selector in
**Run workflow ▾** was left on `main`, so it ran `main`'s copy of the workflow — the old one that
truncates the diff at 60 lines and produces no artifact.

**You do not need to redo it.** The diff it printed is the same drift already known and already
ported onto the branch: the illustrative-prices header block. Once you merge, `main` gets the fixed
workflow, and the next scheduled run (13:00 UTC daily) writes the full diff **and a copy of every
live handler** into a downloadable `drift-diffs` artifact automatically.

**After merging, watch for one thing.** The next drift run should come back **green** for
`relayshield-api`. If it is still red, the remainder of the diff — the part the old 60-line cut hid
— is real drift that was never ported. Download the artifact and send it to me.

---

## Step 2 — Create the missing tables

**The Mac clone is currently stuck** (unfinished merge — see `MAC_CLONE_RESCUE.md`), so use the
standalone copy. The script is self-contained and needs no checkout:

    curl -sSL -o /tmp/rs_setup.sh \
      https://raw.githubusercontent.com/nzdsf2-gif/relayshield/claude/daily-todo-summary-7zpsvv/tools/setup_pending_tables.sh

    AWS_PROFILE=relayshield DRY_RUN=1 bash /tmp/rs_setup.sh    # look first
    AWS_PROFILE=relayshield bash /tmp/rs_setup.sh

Once the clone is healthy again, `bash tools/setup_pending_tables.sh` from the repo root does the
same thing.

Creates all three outstanding tables, enables TTL, seeds `@bjorkanesiaaaa`, finds both Lambda role
names and attaches the IAM policies, then prints a verification table. It refuses to run against any
account other than 239677749008.

---

## Step 3 — Deploy the Cloudflare Worker

**Do this AFTER step 2.** The Ransomware Victims tab renders a "not yet available" state until the
victim table exists, so deploying first makes the demo look broken.

    cd ~/"Side SaaS Hustle"
    npx wrangler deploy --config wrangler.ti-demo.toml

If it asks you to log in, it opens a browser window; approve and it continues.

### Then make this the last time you do it by hand

**`deploy_workers.yml` is now in the repo** and deploys any changed Worker on push to `main` — all
eleven of them, none of which had a CI path before. It needs two repo secrets, once:

1. **Cloudflare dashboard** → click your profile icon (top right) → **My Profile** → **API Tokens** →
   **Create Token** → use the **"Edit Cloudflare Workers"** template → **Continue to summary** →
   **Create Token**. Copy the token — it is shown once.
2. **Cloudflare dashboard** → **Workers & Pages** → the **Account ID** in the right-hand sidebar. Copy it.
3. **GitHub repo** → **Settings** → **Secrets and variables** → **Actions** → **New repository
   secret**, twice:
   * Name `CLOUDFLARE_API_TOKEN`, value = the token from (1)
   * Name `CLOUDFLARE_ACCOUNT_ID`, value = the ID from (2)

After that, editing `cloudflare_worker_ti_demo.js` and pushing deploys it. No wrangler, no laptop.

**Worker secrets (`DEMO_KEY`, `DEMO_TOKEN`) are deliberately not managed by CI** — `wrangler deploy`
leaves them untouched, so the demo keeps working, and putting them in GitHub too would double the
number of places they could leak from for no benefit.

---

## Step 4 — Check the demo

`https://relayshield-ti-demo.relayshieldadmin.workers.dev/?token=rs-demo-2026`

A **Ransomware Victims** tab should appear between "Trending Threats" and "Agentic Identity Risk".

**It will show "Ransomware victim collection is not yet available" until an intel monitor run has
populated the table.** That is correct behaviour, not a bug — the table is created empty in step 2
and fills on the next scheduled run. Check again after one.

---

## Step 5 — Housekeeping

* **GitGuardian incident #36505440** — mark **false positive**. It flagged a made-up hex string in a
  docstring; there is no credential and nothing to revoke. Already fixed in the code.
