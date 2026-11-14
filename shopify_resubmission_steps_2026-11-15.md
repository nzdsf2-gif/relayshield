# Shopify resubmission steps (2026-11-15)

Background and what changed: `shopify_review_fixes_2026-11-14.md`. This file is only the steps.
Nothing in step 1 has run on your Mac. It was trial-merged here against the current `origin/main` with no conflicts and `26 passed`.

## Step 1. ANDREW RUNS THIS: merge, test, and deploy only if the test passes

Each line runs only if the one before it succeeded, so a failure stops everything after it, including the deploy. It discards your local `shopify/worker.js` edits (your patch is on GitHub; the first check refuses to continue if it is not). It leaves `wrangler.toml` and your other modified files alone.

```zsh
cd ~/dev/relayshield &&
git checkout main &&
git --no-pager fetch origin recover/shopify-live-2026-11-14 &&
[ "$(git --no-pager show FETCH_HEAD:shopify/local_uncommitted_2026-11-14.diff | wc -l | tr -d ' ')" = "307" ] &&
git checkout -- shopify/worker.js &&
git --no-pager fetch origin claude/admiring-cerf-f26xi5 &&
git -c pull.rebase=false merge --no-edit FETCH_HEAD &&
node shopify/test_worker_session.mjs 2>/dev/null | tail -1 | grep -q "^26 passed" &&
echo "TESTS PASSED, deploying" &&
cd shopify &&
npx wrangler login &&
npx wrangler deploy --keep-vars
```

EXPECT: a merge summary, then `TESTS PASSED, deploying`, a Cloudflare login page in your browser (approve it), then wrangler printing a deployed message with a version id.
STOP IF, by where it stopped:
* Nothing printed after `fetch`, or the next line is your prompt: the 307-line check failed, so the patch is not on GitHub. Do not continue; tell me.
* "would be overwritten by merge" or "Automatic merge failed": paste me the file names. If only `docs/claude_memory/LOG_CURRENT.md` is named, run `python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`, then `git add docs/claude_memory/LOG_CURRENT.md`, then `git commit --no-edit`, then run the block again from the top.
* It stops right after the merge with no `TESTS PASSED` line: the tests did not print `26 passed`. Run `node shopify/test_worker_session.mjs 2>&1 | tail -20` and paste me the output. Nothing was deployed.
* A wrangler error: paste it. If the app misbehaves after a successful deploy, `npx wrangler rollback` from `~/dev/relayshield/shopify` undoes it.

After a deploy, this should print only ` M shopify/wrangler.toml` (your local KV id, which is never committed):

```zsh
cd ~/dev/relayshield && git --no-pager status --short shopify
```

EXPECT: ` M shopify/wrangler.toml` and nothing else. STOP IF it lists `shopify/worker.js`: the merge did not complete.

## Step 2. ANDREW CLICKS THIS: check `relayshield-test`, while recording

Menu paths below come from memory of Shopify's screens and my notes from 2026-10-17, because I cannot open Shopify from here. If a screen does not match, stop and send me a screenshot rather than guessing at a button on a live store.

**Start the recording first.** On your Mac press Command + Shift + 5, choose **Record Selected Portion** (drag over the browser window), click **Options** and choose **Microphone: Built-in** if you want to speak, then click **Record**. Press the stop button in the menu bar when finished. The file is saved on your Desktop as a `.mov`.

Do these in order. Say each item number out loud as you start it, so the reviewer can follow:

1. **Item 1, interface.** Open the Shopify Admin of `relayshield-test`, then Apps, RelayShield Order Screening. Show the page: the plan panel ("Current plan: Free. N of 100 free checks used"), the Screening settings checkboxes, the filter menu, Sync orders and Refresh. Pick "High risk" in the filter, then back to "All". Untick the order-note box, click **Save settings**, click **Refresh**, and show it is still unticked.
2. **Items 2 and 3, plan changes and billing.** Click **View or change plan**. Shopify's plan page should open (a 404 here means the app handle is wrong: read it from the address bar after `/apps/` and tell me). Choose **Paid**. On a dev store this should create a $0 test charge. Return to the app and Refresh: it should say "Current plan: Paid". Then change back to **Free** the same way and show it says Free again. If the Paid plan still shows as Free, stop recording and tell me: the code only treats a subscription named exactly `Paid` as paid.
3. **Item 4, data sync.** In the Admin go to Settings, then Apps and sales channels, click RelayShield Order Screening, and **Uninstall**. Then go to the Dev Dashboard at `dev.shopify.com/dashboard`, open the RelayShield Order Screening app, and on its Overview click **Install app** (top right), choosing `relayshield-test`. Shopify may ask you to pick a plan: choose Free. Open the app from Admin. Show that your existing orders appear in the table instead of "No orders screened yet". It may take a few seconds and the page reloads once by itself.
4. Stop the recording.

If the orders do not appear, or the page says it could not read your orders, stop and tell me what it says. The likely cause is a Partner Dashboard setting for protected customer data, not code.

## Step 3. ANDREW CLICKS THIS: turn the recording into a link

Shopify's "Proof of resolution" box takes a web address, not a file.

1. Open `drive.google.com`, click **New**, **File upload**, and choose the `.mov` from your Desktop.
2. Right-click the uploaded file, click **Share**, under General access choose **Anyone with the link**, role **Viewer**, click **Copy link**, then **Done**.
3. Check it: open the link in a private browser window. If it asks you to sign in, the sharing step did not take.

Check the video plays before pasting: the reviewer will not be signed in as you.

## Step 4. ANDREW CLICKS THIS: paste the link into each of the four items and resubmit

1. Go to `partners.shopify.com`, open RelayShield Order Screening, and go to the App Store review page that showed "0/4" (the page in your screenshots, titled with the app name, with the four items listed down the left side).
2. Click the first item, **Have a user interface (UI) that merchants can interact with**.
3. Under **Show resolved state**, click into **Proof of resolution** and paste the link. Click **Mark resolved**.
4. Repeat for the other three items in the left list: **Allow pricing plan changes**, **Implement Shopify App Pricing or the Shopify Billing API correctly**, and **Synchronize data accurately**. The same link goes in all four.
5. When the counter at the top left reads **4/4**, click **Back** (top left, "When you're done, return to the previous screen and resubmit for review") and use the resubmit button on that screen.

If the box rejects the link, tell me what it says. The earlier "Ask a question" option under each item is there if Shopify's wording on any item is unclear to you.
