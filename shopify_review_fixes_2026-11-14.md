# RelayShield Order Screening: Shopify review fixes (updated 2026-11-15)

Branch `claude/admiring-cerf-f26xi5` on `nzdsf2-gif/relayshield`. Not merged, not deployed. This file was sent to you in the Claude app; it has not been sent to Shopify. Shopify only gets what you paste into "Proof of resolution".

## What your saved patch showed

Your uncommitted local `shopify/worker.js` (saved as `shopify/local_uncommitted_2026-11-14.diff` on branch `recover/shopify-live-2026-11-14`, 307 lines) is a billing implementation written on 2026-11-03 in a local session and never committed. It contains the exact words the reviewer quoted: **"Plan status unknown"** and **"Refresh this page to check your plan"**. That is strong evidence it is what is deployed (not proof: reading the live Worker needs a Cloudflare token with Workers Scripts, Read). It has:

* a billing gate: Free 100 screenings a month, Paid 2000 a month, checked before each order is screened;
* a plan card that shows "Plan status unknown" whenever the billing check throws for any reason, with no button to do anything about it, which is what the reviewer saw;
* a fix I had only suspected: Shopify has no endpoint for apps to write timeline comments, so the screening line is written into the **order note** instead (kept, merged);
* routes `/billing/status` and `/webhooks/app-subscriptions-update`.

## What I did: merged it with my work, and changed three things on purpose

Merged into `shopify/worker.js`, 26 tests pass (5 at the start of this work), 12 bugs planted in the billing code and all caught.

1. **Free allowance is now 100 checks per shop for its lifetime** (your decision: "try before you buy", a monthly reset invites abuse). Paid stays 2000 per calendar month.
2. **The lifetime counter survives uninstall** and is keyed by a hash of the shop domain, so reinstalling does not give a fresh 100. Uninstall still wipes everything else.
3. **The subscription query is simpler.** The live copy also asked Shopify for plan price details that nothing used. If Shopify refuses any part of a query the whole check throws, and that is one plausible cause of "Plan status unknown". UNVERIFIED as the cause.

Other changes in the merge: the plan panel now always has the **View or change plan** button and, if the plan cannot be read, says so and still offers the button (no "refresh and wait"); a billing outage uses Free limits and can never grant Paid; the sync also respects the allowance and tells the merchant when the limit is reached; `app_subscriptions/update` now reads the shop from Shopify's header (the live copy read a field Shopify does not send, so it never did anything).

## The four items

| # | Item | Fix |
|---|---|---|
| 1 | 2.1.3 UI | Plan button, settings form, verdict filter, Sync orders, Refresh, order links, Support and Privacy links |
| 2 | 1.2.3 plan changes | View or change plan opens Shopify's hosted plan page. Always present, whatever the status |
| 3 | 1.2.2 billing | Shopify App Pricing only, no charge created by the app; plan and usage shown; reinstall handled by Shopify's screens |
| 4 | 2.1.4 sync | Existing orders are screened on first signed-in load and by Sync orders; uninstall then reinstall shows them again |

## Things you should know before you deploy

* **Clean orders now get a note too.** The live code writes the RelayShield line into the order note for every screened order, including no-flag ones (tags only for medium and high). I kept that. The "Add a RelayShield line to the order note" checkbox in settings turns it off per shop.
* **The free limit is already enforced live** if the deployed Worker is your local one. Shops past 100 a month stop being screened today.
* **Privacy policy.** The lifetime counter is a small record kept after uninstall. It should be mentioned in section 6 of the privacy policy (`cloudflare_worker_privacy.js`, a separate Worker). Not done; your call, my recommendation is yes, before approval.
* **UNVERIFIED against a real shop:** the subscription query, the orders GraphQL query, the plan-page URL, and that the subscription for the Paid plan is named exactly `Paid` (the code treats only a subscription named `Paid` as paid; your listing's display name is "Paid"). The dev-store check (step 3) proves them.

## Steps, in order

**1. ANDREW RUNS THIS** (merge and test). Your patch is safe on GitHub, so this discards your local `worker.js` edits. It does not touch `wrangler.toml` or your other modified files.

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin recover/shopify-live-2026-11-14
git --no-pager show FETCH_HEAD:shopify/local_uncommitted_2026-11-14.diff | wc -l
git checkout -- shopify/worker.js
git --no-pager fetch origin claude/admiring-cerf-f26xi5
git -c pull.rebase=false merge --no-edit FETCH_HEAD
node shopify/test_worker_session.mjs 2>&1 | tail -1
```

EXPECT: the first number printed is `307`, the merge ends with a summary of changed files, and the last line is `26 passed`.
STOP IF: the number is not 307 (the patch is not on GitHub: do not continue); or the merge says "Your local changes to the following files would be overwritten" (paste me the file names); or "Automatic merge failed" naming only `docs/claude_memory/LOG_CURRENT.md` (run `python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`, then `git add docs/claude_memory/LOG_CURRENT.md` and `git commit --no-edit`); a conflict in a `.js` or `.py` file means stop and paste me the file name.
UNVERIFIED: not run in your state. Your `shopify/wrangler.toml` keeps its local KV id on purpose.

**2. ANDREW RUNS THIS** (deploy, only after step 1 printed `26 passed`). `--keep-vars` keeps variables set in the Cloudflare dashboard.

```zsh
cd ~/dev/relayshield/shopify
npx wrangler login
npx wrangler deploy --keep-vars
cd ..
git --no-pager status --short shopify
```

EXPECT: wrangler prints a deployed message with a version id. The last command prints ` M shopify/wrangler.toml` and nothing else (your local KV id, which is never committed).
STOP IF: the last command lists `shopify/worker.js`: the merge in step 1 did not complete; do not deploy again. UNVERIFIED: not run in your state. Rollback if the app misbehaves: `npx wrangler rollback` from `shopify/`.

**3. ANDREW CLICKS THIS** (prove it on `relayshield-test`): open the app. You should see the plan panel ("Current plan: Free. N of 100 free checks used"), the settings form, the filter, Sync orders and Refresh. Then: click **View or change plan** (it must open Shopify's plan page; a 404 means the app handle is wrong, so read it from the address bar after `/apps/` and tell me); untick the order-note box, Save, Refresh, confirm it stays unticked; **uninstall the app and reinstall it** and confirm your existing orders appear instead of "No orders screened yet". Record your screen while you do this.

**4. ANDREW CLICKS THIS** (reply to the reviewer): in the Partner dashboard, for each of the four items choose **Show resolved state** and paste a link to that recording (the field takes a URL, not a file). One recording of step 3 can serve all four. Then resubmit.

If step 3 shows the dashboard cannot read your orders, the likely cause is protected customer data access, which is a Partner Dashboard setting and not code. Tell me what the page says.
