# Check the app on relayshield-test, silent, as three short clips (2026-11-15)

The new version is already deployed (Cloudflare version `41037aa4`). Nothing below needs your voice. Each clip is its own file, named for the Shopify items it answers, so the reviewer needs no narration.

Menu paths for Shopify screens are from memory, because I cannot open Shopify from here. If a screen does not match, stop and send me a screenshot.

## Before recording: a 30-second sanity check (not recorded)

1. In your browser open `https://relayshield-order-screening.relayshieldadmin.workers.dev/healthz`. It should show the single word `ok`.
2. Open `https://admin.shopify.com/store/relayshield-test/apps`. This is the Admin of your test store. If it asks you to sign in, sign in with the account you use for the Partner Dashboard. You can also reach it from `partners.shopify.com`, then **Stores**, then `relayshield-test`, then **Log in**.
3. In the left menu, under **Apps**, click **RelayShield Order Screening**. The app opens inside the Admin. Do one practice run of the clips below first, without recording.

## How to record, with no sound

Press Command + Shift + 5. Click **Options** and set **Microphone** to **None**. Choose **Record Selected Portion**, drag over the browser window, click **Record**. Stop with the stop button in the menu bar (top right). The video lands on your Desktop. Rename each one as shown.

## Clip A, named `Item 1 - UI.mov`

1. Open the app from the Admin (step 3 above). Pause three seconds on the full page: the plan panel, the settings box, the filter, Sync orders, Refresh.
2. In the **Show** menu choose **High risk**, pause two seconds, choose **All screened orders**.
3. Untick **Add a RelayShield line to the order note**, click **Save settings**, wait for "Saved.".
4. Click **Refresh**. When the page reloads, pause three seconds on the unticked box. Stop recording.

## Clip B, named `Items 2 and 3 - Plan changes.mov`

1. Open the app. Pause three seconds on the plan panel (it should say "Current plan: Free").
2. Click **View or change plan**. Shopify's plan page opens. Pause three seconds on it. Choose **Paid** and confirm. On a test store this should be a $0 test charge.
3. Go back to the app (left menu, Apps, RelayShield Order Screening), click **Refresh**. It should say "Current plan: Paid". Pause three seconds.
4. Click **View or change plan** again, choose **Free**, confirm. Go back, **Refresh**, pause three seconds on "Current plan: Free". Stop recording.

If the plan page shows an error page (404): do not record. Look at the address bar when the app is open: the text after `/apps/` is the app handle. Tell me what it is.
If you chose Paid and the app still says Free after Refresh: stop and tell me. The code only counts a plan named exactly `Paid`.

## Clip C, named `Item 4 - Data sync.mov`

1. In the Admin, click **Settings** (bottom left, gear icon), then **Apps**. Click **RelayShield Order Screening**, then **Uninstall**, and confirm. Start recording just before this step and pause three seconds on the uninstall confirmation.
2. Open a new tab at `dev.shopify.com/dashboard`, open the RelayShield Order Screening app, click **Install app** (top right), choose `relayshield-test`, confirm. If Shopify asks you to choose a plan, choose **Free**.
3. Open the app from the Admin again. Wait up to 15 seconds: the page reloads by itself once and your existing orders appear in the table. Pause five seconds on the filled table. Stop recording.

If it still says "No orders screened yet" after 30 seconds: click **Sync orders** once and wait. If that fails, stop and tell me exactly what the status line next to the buttons says. The most likely cause is a Partner Dashboard setting for protected customer data, not code.

## Make each clip a link

1. Go to `drive.google.com`, click **New**, **File upload**, and choose the three `.mov` files.
2. For each file: right-click, **Share**, under General access choose **Anyone with the link**, role **Viewer**, **Copy link**, **Done**. Keep the three links in a note, labelled A, B and C.
3. Open each link in a private browser window to confirm it plays without signing in.

## Paste the links into the four items and resubmit

1. Go to `partners.shopify.com`, open **RelayShield Order Screening**, and go to the review page with the "0/4" counter and the four items listed down the left side.
2. Click **Have a user interface (UI) that merchants can interact with**. Under **Show resolved state**, click into **Proof of resolution**, paste **link A**, click **Mark resolved**.
3. Click **Allow pricing plan changes**. Paste **link B**, click **Mark resolved**.
4. Click **Implement Shopify App Pricing or the Shopify Billing API correctly**. Paste **link B** again, click **Mark resolved**.
5. Click **Synchronize data accurately**. Paste **link C**, click **Mark resolved**.
6. When the counter reads **4/4**, click **Back** (top left) and use the resubmit button on that screen.
