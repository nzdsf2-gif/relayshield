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

## Steps for you, in order

**1. ANDREW RUNS THIS** (read-only: download the live Worker and look for the reviewer's strings). It will ask for a Cloudflare API token (hidden input). The token needs "Workers Scripts: Read".

```zsh
cd ~/dev/relayshield
sh tools/recover_live_worker.sh relayshield-order-screening shopify/worker.js
grep -c "Plan status unknown" "${TMPDIR:-/tmp}/live-worker-relayshield-order-screening.js"
grep -c "check your plan" "${TMPDIR:-/tmp}/live-worker-relayshield-order-screening.js"
```

EXPECT: the script reports it downloaded the Worker, then the two `grep -c` lines each print a number. Tell me both numbers and anything the script printed under "THEY DIFFER".
STOP IF: the script prints a 404 or "no deployed script by that name": the Worker has another name; open Cloudflare, Workers & Pages, and tell me the names you see. A grep number of `0` for both means the reviewer tested something else, and I need to know which URL the app uses (step 3).
UNVERIFIED: this block has not run in your state.

**2. ANDREW RUNS THIS** (after step 1: put the live copy on a branch so I can read it). It stages only the one file.

```zsh
cd ~/dev/relayshield
git checkout main
git checkout -b recover/shopify-live-2026-11-14
cp "${TMPDIR:-/tmp}/live-worker-relayshield-order-screening.js" shopify/live_worker_2026-11-14.js
git add shopify/live_worker_2026-11-14.js
git commit -m "Recover the live relayshield-order-screening Worker, 2026-11-14"
git push -u origin recover/shopify-live-2026-11-14
```

EXPECT: the push prints `recover/shopify-live-2026-11-14 -> recover/shopify-live-2026-11-14`.
STOP IF: `cp` says no such file: step 1 did not finish. Do not continue to the deploy.

**3. ANDREW CLICKS THIS** (Dev Dashboard, `dev.shopify.com/dashboard`, the RelayShield Order Screening app, its configuration/versions page): read the **App URL** and tell me what it says. It should be the `relayshield-order-screening` Worker's address. If it points anywhere else, that is where the reviewer's strings came from. I cannot see this screen, so send a screenshot if the labels differ.

**4. ANDREW CLICKS THIS** (Partner Dashboard, `partners.shopify.com`, the listing's pricing settings): confirm **Managed pricing** is on and that the plans listed are exactly what you intend. You told me the price is a flat $29 per month; the reviewer's text mentions a "Free" plan too, so check whether a Free plan is still defined. If it is not what you want, change it there. Send me a screenshot of the plans if unsure.

**5. After I have merged the live copy with my branch, I will give you the deploy block.** It is a separate step on purpose: a deploy over unrecovered code is the one move here that cannot be undone from git. Then you check `relayshield-test` in the Shopify Admin: the plan panel, **View or change plan** opens Shopify's plan page, the settings box stays unticked after Save and Refresh, and an uninstall then reinstall shows the existing orders instead of "No orders screened yet".

**6. ANDREW CLICKS THIS** (reply to the reviewer, after step 5): for each item choose **Show resolved state** and paste a URL. The field wants a link, not a file, so upload a short screen recording or screenshots from step 5 somewhere with a shareable link; one recording of the reinstall path can serve all four. Then resubmit.
