# RelayShield Order Screening: embedded app checks stuck "pending"

Written 2026-10-17. The Partner dashboard, shopify.dev and the community forum are all unreachable from the
build container, so Shopify's behaviour below comes from search snippets of forum posts and staff replies, not
from reading their pages. Treat those parts as secondary evidence.

## What the evidence says

1. **The checks were never failing, they have no data.** Both rows show an empty dotted circle, not a red one.
   Shopify's own instruction under the row is "Log in and interact with your app on a dev store to generate
   session data". Staff in the community threads say the checks are telemetry that fires when App Bridge
   initialises inside the Admin iframe under a real shop session, run every 2 hours, and can lag up to 2 days.
   They are not a crawler that loads the App URL.
2. **The app itself works in that iframe.** Your screenshot (relayshield-test.myshopify.com, dev store, admin.shopify.com)
   shows the dashboard with the shop name filled in. The shop name is only rendered when the Worker has verified an
   App Bridge session token (HS256, signed with the API secret, `dest` a myshopify.com domain), so Shopify is
   delivering a valid token and the server accepts it. The page is not the problem.
3. **What that screenshot cannot prove:** that App Bridge initialised in the page. The server verifies the
   `id_token` URL parameter Shopify appends to the iframe URL, which works with no App Bridge at all. The two
   checks need `shopify.idToken()` to run and an `Authorization: Bearer` request to reach our backend. Our page
   does both, but only if the `<meta name="shopify-api-key">` value equals the app's Client ID. A wrong or empty
   key fails silently and produces exactly "pending, no data".
4. **A real defect, found while looking, not proven to be the cause.** The app config uses managed installation
   (`use_legacy_install_flow = false`). Shopify then never calls `/auth` or `/auth/callback`, and those were the
   only places the Worker obtained an access token or registered the `orders/create` webhook. The existing dev
   store works because it was installed under the old flow (orders #1004 to #1010 were screened Oct 4 to 10). A
   store installed fresh, which is what a reviewer does, would get an empty dashboard and no screening. The Worker
   now exchanges the session token for an offline token on first authenticated load.
5. **A code comment was wrong.** It said Shopify's automated checks "load the App URL directly (no session token)".
   That is not how the checks work (point 1). The comment is corrected.

## The one check that settles it (ANDREW, 2 minutes)

1. Open a Chrome profile with no extensions (a guest window, or a new profile). Your current browser shows several
   extensions and an assistant sidebar, and Shopify staff advise a clean browser because extensions interfere with
   the detection.
2. Admin of relayshield-test, Apps, RelayShield Order Screening. Right-click inside the app, Inspect, Console.
   Type `RelayShield` in the filter box.
3. Read the lines:

| You see | Meaning | Next |
|---|---|---|
| `session token acquired` then `session auth check: 200` | App Bridge ran and the backend saw the Bearer header. The code is fine. | Interact for a minute (open the page, reload twice), wait one 2-hour cycle, then escalate with the text below. |
| `session token unavailable: ...` or `App Bridge not ready after retries` | App Bridge is not initialising. | Compare the meta key to the Client ID (below). |
| No `[RelayShield]` lines at all | The deployed Worker is not this code. | Run the drift read before anything else. |
| `session auth check: 401` | The header arrived but the secret or token is wrong. | Check `SHOPIFY_API_SECRET` is the app's current secret. |

4. Network tab, filter `session`: the request `/api/session` should show `authorization: Bearer ey...` and status 200.
5. Compare the key: view the frame source and read `<meta name="shopify-api-key" content="...">`, then compare it with
   Client ID on the app's Settings page in the Dev Dashboard. They must be identical.

## Deploying the Worker change (not yet done)

The change is in `shopify/worker.js` (token exchange, a `data-shop` flag, one reload with the token, a log line
visible in `wrangler tail`). Tests: `node shopify/test_worker_session.mjs` (5 passing, each guard proven by
reintroducing its defect) and `python3 test_shopify_worker.py`. The dev store that already has a token is left
alone, so nothing changes for it.

Hand-deployed Worker, so read the live copy first (the drift rule):

    sh tools/recover_live_worker.sh relayshield-order-screening shopify/worker.js

Only `IDENTICAL` makes a deploy safe. `shopify/wrangler.toml` on `main` holds a placeholder KV id
(`PASTE_KV_NAMESPACE_ID_HERE`), so deploying it as it stands will fail. Read the real id with
`npx wrangler kv namespace list` from the `shopify` folder, put it in your local copy only, deploy, then
`git checkout shopify/wrangler.toml` so the placeholder is not committed with a real id. Secrets survive a deploy.
`APP_URL` in that file is unused by the code.

Redeploying the Worker does not touch Shopify's check; it only keeps a fresh install from being empty.

## If the console is clean and it is still pending after a full day

Shopify staff have said they cannot pass these checks by hand, but forum threads report support unblocking them
after verification, and this one has been stuck ten days. Post in the community thread for "Embedded app checks
stuck" and open a Partner Support ticket with this text, filling in the App ID from the Dev Dashboard:

> App: RelayShield Order Screening, version relayshield-order-screening-4, released 2026-10-10. Embedded app
> checks have been pending for ten days. The app is installed on the dev store relayshield-test.myshopify.com
> and opened inside the Admin iframe from a clean browser profile. App Bridge is loaded from
> https://cdn.shopify.com/shopifycloud/app-bridge.js as the first script in head, with the shopify-api-key meta
> tag set to the Client ID. `shopify.idToken()` resolves and our backend receives `Authorization: Bearer`
> session tokens (HTTP 200 on /api/session). We use managed installation with token exchange. The checks show no
> data rather than a failure. Please re-run them or tell us what telemetry is missing.

Also run `/shopify-app-store-review` from the Shopify AI Toolkit, which the last row of that page offers.

## Sources (secondary)

- [Embedded app checks stuck 48h+ despite App Bridge from CDN (first in head) + session tokens](https://community.shopify.dev/t/embedded-app-checks-stuck-48h-despite-app-bridge-from-cdn-first-in-head-session-tokens-working-requesting-manual-verification/36010)
- [Embedded app checks stuck on pending for 4+ days despite multiple fresh installs](https://community.shopify.dev/t/embedded-app-checks-stuck-on-pending-for-4-days-despite-multiple-fresh-installs-and-confirmed-session-token-activity/36495)
- [Shopify app submission - Embedded app checks](https://community.shopify.dev/t/shopify-app-submission-embedded-app-checks/29323/2)
- [Set up embedded app authorization](https://shopify.dev/docs/apps/build/authentication-authorization/set-embedded-app-authorization?extension=javascript)
