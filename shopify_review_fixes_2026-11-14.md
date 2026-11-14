# RelayShield Order Screening: Shopify review fixes (2026-11-14, updated after the reviewer's full text)

Branch: `claude/admiring-cerf-f26xi5` on `nzdsf2-gif/relayshield`. Not merged, not deployed. The file you are reading was sent to you by me in the Claude app and is also committed on that branch. It has not been sent to Shopify; Shopify only gets what you paste into the "Proof of resolution" boxes.

## STOP: do not deploy yet. The live Worker is not the code in the repo.

The reviewer quoted two screens: **"Plan status unknown"** and **"Refresh this page to check your plan"**. Neither string exists anywhere in this repo, on any branch, in any commit. So what Shopify tested is not what I read. Most likely the live Worker was changed and deployed from your Mac without being committed (the DRIFT RULE in CLAUDE.md, a fourth time). `wrangler deploy` of my branch would then erase that code with no error. Recover the live copy first (steps 1 and 2) so I can merge the two instead of overwriting one.

## The four items, with the reviewer's words

| # | Item | What the reviewer saw | What changed |
|---|---|---|---|
| 1 | 2.1.3 UI merchants can interact with | Dashboard loaded, "no merchant-usable buttons, links, or inputs" | Plan button, settings form (two checkboxes and Save), verdict filter, **Sync orders**, Refresh, order links to Shopify Admin, Support and Privacy links. Run in a real browser. |
| 2 | 1.2.3 Allow pricing plan changes | No control to move between Free and Paid; stayed on "Plan status unknown" after reload | **View or change plan** opens Shopify's hosted plan page (Managed Pricing), so upgrade, downgrade and the charge history page are Shopify's. The button shows whatever the plan status is. If the status cannot be read, the page now says so and still shows the button, with no "refresh and wait" dead end. |
| 3 | 1.2.2 Implement App Pricing correctly | After reinstall, no plan-selection or resubscription control; "Plan status unknown" | Same Managed Pricing design, so accept, decline and re-approval on reinstall are Shopify's screens. The app creates no charge itself (a test fails if it tries). |
| 4 | 2.1.4 Synchronize data accurately | Six orders in Shopify; after reinstall the dashboard showed zero and "No orders screened yet" | **My first pass missed this.** The Worker only screened orders created after install, and my uninstall cleanup made a reinstall start empty. Now the first signed-in load reads the shop's recent orders (last 60 days Shopify returns, newest 50) and screens them in batches of 8, once each, with the same tags a new order gets. There is a **Sync orders** button too. Uninstall still wipes everything, and the sync refills it on reinstall. |

Other sync fixes from the first pass still stand: the `app/uninstalled` webhook wipes token, history and settings; a 401 from Shopify's Admin API drops the dead token; older installs get the webhook registered once.

## Things I cannot verify from here, and a suspicion

* **UNVERIFIED: the Shopify calls.** The plan-status query (`currentAppInstallation.activeSubscriptions`), the plan-page URL shape, and the orders query (`orders(...) { legacyResourceId name email }`) follow Shopify's docs, but shopify.dev is blocked from this container. The dev-store check in step 5 is what proves them.
* **UNVERIFIED: buyer emails on a reviewer's store.** Reading an order's `email` needs Shopify's protected customer data access. If it is not granted, the orders read is refused: the page then says it could not read the orders, and nothing breaks. If step 5 shows that message, the fix is in the Partner Dashboard (protected customer data access), not in code.
* **Suspicion, not checked:** the Worker writes the "timeline note" through `POST /orders/<id>/events.json`. I believe Shopify's REST Events resource is read-only, so that note may never have been written (tags are written first, so tags are unaffected). Nothing in the repo proves a note was ever written (the 2026-10-17 record says the tag and note write was never proven). It is not part of these four items and I did not change it. My recommendation: check an order in `relayshield-test` for the note after step 5, and tell me what you see.
* **App handle is a guess.** The plan link uses `relayshield-order-screening`. If your app's handle differs, set the Worker variable `SHOPIFY_APP_HANDLE`.
* **No billing gate.** Screening still runs with no paid plan, so the reviewer's test store is not left empty. I would add a gate after approval, behind a flag that ships off. That is your call because it decides who gets the product free.

## How it was checked

* `node shopify/test_worker_session.mjs`: 18 checks pass (5 before today). `python3 test_shopify_worker.py` passes.
* Planted bugs: 14 across the two passes. Three survived their first run (a validation branch, the sync's token exchange, and the buyer email reaching the screening call). A test was added for each and all 14 are caught now.
* The dashboard's JavaScript was run in headless Chromium: filter, Save, and a signed-in first load that syncs in two rounds and reloads to show all six orders. The look inside Shopify Admin is unchecked (Polaris CSS is blocked here).

## What happened to steps 1 and 2 (my error, kept here so it is not repeated)

Step 1 returned `403: the token cannot read Workers Scripts`. The recovery script saves whatever Cloudflare answers into its output file, so that file held the 403 error message, and the two `grep -c` zeros counted a error message, not the Worker. My step 2 copied that file and pushed it to `recover/shopify-live-2026-11-14`, because my block had no guard for a failed step 1. The branch file `shopify/live_worker_2026-11-14.js` is that error text. It is removed in step A below.

The App URL screenshot you sent settles one thing: the app's App URL is `https://relayshield-order-screening.relayshieldadmin.workers.dev`, so it points at the `relayshield-order-screening` Worker, version `relayshield-order-screening-5` (UNVERIFIED from here: workers.dev is blocked from my container).

It also showed something more useful. Your `git checkout main` printed `M shopify/worker.js` and `M shopify/wrangler.toml`: you have **uncommitted local edits to the Shopify Worker on your Mac**. That is the likeliest home of the "Plan status unknown" code, and it needs saving before anything else.

## Update 2026-11-15

* **Fixed in code:** a merchant on the Free plan has no active subscription in Shopify's billing, and the dashboard said "No active plan yet". It now says "Current plan: Free". Tests: 18 pass.
* **Your step A result has not reached GitHub.** The recovery branch still ends at the first, bad commit, so I cannot see your patch. Rerun step A (it is safe to repeat) and paste what it prints.

## Steps for you, in order

**A. ANDREW RUNS THIS** (save your uncommitted Shopify edits as a patch file on the recovery branch, and remove the error file). It stages only the two files it names.

```zsh
cd ~/dev/relayshield
git checkout recover/shopify-live-2026-11-14
git rm -q shopify/live_worker_2026-11-14.js
git --no-pager diff HEAD --stat -- shopify/worker.js shopify/wrangler.toml
git --no-pager diff HEAD -- shopify/worker.js shopify/wrangler.toml > shopify/local_uncommitted_2026-11-14.diff
wc -l shopify/local_uncommitted_2026-11-14.diff
git add shopify/local_uncommitted_2026-11-14.diff
git commit -m "Save uncommitted local edits to the Shopify Worker, 2026-11-14"
git push
```

EXPECT: the stat lines show `shopify/worker.js` with a number of changed lines, `wc -l` prints a number above 0, and the push prints `recover/shopify-live-2026-11-14 -> recover/shopify-live-2026-11-14`.
STOP IF: `wc -l` prints `0`: your local `worker.js` matches `main`, so the "Plan status unknown" code was deployed from somewhere else, and the only way left to read the live Worker is a Cloudflare token that can read Workers Scripts (step B). UNVERIFIED: this block has not run in your state.

**B. ANDREW CLICKS THIS, only if A printed 0 or you want proof of what is deployed** (Cloudflare dashboard, My Profile, API Tokens, Create Token, Create Custom Token): permission **Account, Workers Scripts, Read**, account `Relayshieldadmin@gmail.com's Account`. Use that token when `tools/recover_live_worker.sh` asks. The earlier token returned 403, so it lacked that permission.

**C. DONE, nothing to do.** Pricing stays as you found it: a Free plan and a Paid plan at $29/month, "approval to charge outside the Shopify Billing API" unchecked. Earlier versions of this file told you to delete the Free plan; that was my wrong guess and is withdrawn. The Free plan allows 100 free checks, counted **per shop for its lifetime** ("try before you buy", your decision, 2026-11-15), not per month. The limit is not built yet and is deliberately not part of this resubmission.

**D. ANDREW CLICKS THIS** (the app handle): open RelayShield Order Screening from the `relayshield-test` Shopify Admin and read the browser address bar. The part after `/apps/` is the app handle. Tell me what it is. If it is not `relayshield-order-screening`, the plan link needs it (Worker variable `SHOPIFY_APP_HANDLE`).

**E. I will merge your saved patch with my branch, then give you the deploy block.** Do not deploy before that: a deploy over unsaved code cannot be undone from git.

**F. ANDREW CLICKS THIS** (after the deploy, on `relayshield-test`): the plan panel shows, **View or change plan** opens Shopify's plan page, the settings box stays unticked after Save and Refresh, and an uninstall then reinstall shows the existing orders instead of "No orders screened yet".

**G. ANDREW CLICKS THIS** (reply to the reviewer, after F): for each item choose **Show resolved state** and paste a URL. The field wants a link, not a file, so upload a short screen recording or screenshots from F somewhere with a shareable link; one recording of the reinstall path can serve all four. Then resubmit.
