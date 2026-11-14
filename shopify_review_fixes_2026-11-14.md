# RelayShield Order Screening: Shopify review fixes (2026-11-14)

Branch: `claude/admiring-cerf-f26xi5`. Not merged, not deployed. Nothing below is live until you do the steps at the end.

## What Shopify flagged, and what changed

The screenshot showed the reviewer's wording for item 1 only. For items 2 to 4 I had the titles and not the reviewer's text (it is not in the repo or the mailbox I can read), so those three were built from what Shopify's requirement titles ask for. Paste the reviewer's text for 2 to 4 and I will check each fix against it.

| # | Item | Status | What I did |
|---|---|---|---|
| 1 | UI merchants can interact with | Built, tested in a real browser | The reviewer saw a dashboard with "no merchant-usable buttons, links, or inputs". It now has: a plan panel with a **View or change plan** button, a **Screening settings** form (two checkboxes and **Save settings**), a verdict **filter**, a **Refresh** button, order numbers that open the order in Shopify Admin, and Support and Privacy links. These render signed in or out. |
| 2 | Allow pricing plan changes | Code done, needs your Partner Dashboard step | The **View or change plan** button goes to Shopify's hosted plan page, where the merchant upgrades, downgrades or cancels without contacting us. That page exists only once Managed Pricing is switched on (step 3 below). |
| 3 | Implement App Pricing / Billing API correctly | Code done, needs your Partner Dashboard step | You chose Managed Pricing. The app creates no charges itself (a test fails if it ever calls `appSubscriptionCreate`). It reads the shop's active subscription and shows it, or shows "unavailable" if Shopify cannot be reached, never a guess. |
| 4 | Synchronize data accurately | Built from the title, UNCONFIRMED against the reviewer's text | Four real gaps closed: (a) `app/uninstalled` webhook now deletes the token, screening history and settings, so a reinstall starts clean (before, the dead token and old history survived a reinstall); (b) a 401 from the Admin API now drops the stored token so the next load re-exchanges a fresh one; (c) `shop/redact` now deletes settings too, through the same helper; (d) shops installed before today get the uninstall webhook registered once, on their next load. |

## What I did not do, on purpose

* **No billing gate.** Screening still runs for a shop with no paid plan. Gating it now risks the reviewer's test store being screened for nothing and flagged again. Recommendation: add the gate after approval, behind a Worker flag that ships off.
* **The app handle is a guess.** The plan link uses `relayshield-order-screening`. If your app's handle in the Partner Dashboard differs, set the Worker variable `SHOPIFY_APP_HANDLE` (step 4).
* The plan-page URL shape and the `currentAppInstallation.activeSubscriptions` query follow Shopify's documented Managed Pricing, but shopify.dev is blocked from here, so **both are UNVERIFIED against a live shop.** The dev store test in step 5 is what proves them.

## How it was checked

* `node shopify/test_worker_session.mjs`: 13 checks pass (was 5). `python3 test_shopify_worker.py` passes.
* Six bugs were planted one at a time (medium-risk gate, settings deletion, stale-token drop, settings validation, webhook backfill, order link target). The first run caught five and missed one (settings validation never tested a bad `add_note`). I added the case and it is caught now.
* The dashboard's own JavaScript was run in headless Chromium: the filter hides rows, Save posts `{"tag_medium":false,"add_note":true}`, no page errors. Polaris CSS could not load from this container, so the look in Shopify Admin is unchecked.

## Steps for you, in order

**1. ANDREW RUNS THIS** (merge and test)

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/admiring-cerf-f26xi5
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
node shopify/test_worker_session.mjs
```

EXPECT: the last line is `13 passed`.
STOP IF: "Automatic merge failed" naming only `docs/claude_memory/LOG_CURRENT.md`: run `python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`, then `git add docs/claude_memory/LOG_CURRENT.md` and `git commit --no-edit`. A conflict in any `.js` or `.py` file means another session edited the same code; stop and tell me which file.

**2. ANDREW CLICKS THIS** (Partner Dashboard, `partners.shopify.com`): open RelayShield Order Screening and find the pricing settings for the listing. Turn on **Managed pricing** and create one recurring plan at **$29 / 30 days** (add a free trial if you want one). I cannot see that screen and have given menu paths from memory wrongly before, so if it is not where you expect, send me a screenshot before changing anything. Switching to Managed Pricing is the step that makes the plan page, and so items 2 and 3, real.

**3. ANDREW CLICKS THIS**: find the app's **handle** (the URL slug in the app's settings, shown in the Dev Dashboard under the app's Settings). If it is not `relayshield-order-screening`, tell me, or set it yourself in Cloudflare, Workers, `relayshield-order-screening`, Settings, Variables: `SHOPIFY_APP_HANDLE` = the handle.

**4. ANDREW RUNS THIS** (deploy). The KV id goes into the local copy of `wrangler.toml` only and is reverted afterwards. `--keep-vars` stops the deploy wiping dashboard variables such as `SHOPIFY_APP_HANDLE`.

```zsh
cd ~/dev/relayshield/shopify
npx wrangler login
sed -i '' 's/PASTE_KV_NAMESPACE_ID_HERE/d95c371db8754acd9e8e791e0a558915/' wrangler.toml
npx wrangler deploy --keep-vars
git checkout -- wrangler.toml
cd ..
git --no-pager status --short shopify
```

EXPECT: wrangler prints `Deployed relayshield-order-screening` and a version id; the last command prints nothing.
STOP IF: the last command lists `shopify/wrangler.toml`: the placeholder was not restored, run `git checkout -- shopify/wrangler.toml` from `~/dev/relayshield`. UNVERIFIED: this block has not run in your state; the KV id is the one recorded on 2026-10-17.

**5. ANDREW CLICKS THIS** (prove it on a dev store): open the app in `relayshield-test` Admin. You should see the plan panel, the settings form, the filter and the Refresh button. Click **View or change plan** and confirm it opens Shopify's plan page (a 404 there means step 2 is not done or the handle in step 3 is wrong). Untick **Tag medium-risk orders**, press **Save settings**, press **Refresh**, and confirm the box is still unticked.

**6. ANDREW CLICKS THIS** (reply to the reviewer): for each item in the Partner dashboard, choose **Show resolved state** and paste a URL. The field wants a link, not a file, so upload a screenshot or short screen recording from step 5 somewhere with a shareable link and use that. One recording can serve all four. Then resubmit.

Open question for you: what does the reviewer's text say for items 2, 3 and 4? That decides whether the guesses above are enough.
