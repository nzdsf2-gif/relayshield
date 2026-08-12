# Medium draft repair: agent counterparty post

## Why it happened

`cloudflare_worker_blog.js:95` hardcodes the OG image for **every page on the blog**:

```js
<meta property="og:image" content="${SITE}/og.png">
```

There is no per-post image. The post schema in `blog_posts.js` is `date, excerpt, html, slug,
source, title` and nothing else, so every RelayShield post advertises the identical 1200x630 shield
card. `blog.relayshield.net/favicon.ico` also **404s**, so there is no smaller icon for anything to
fall back to.

Medium takes `og:image` for the featured image, and renders each `relayshield.net` link it finds as
a preview card, which fetches the same `og:image` again. The post has 3 relayshield links plus the
"Originally published at" footer Medium adds itself. Same shield, over and over.

The tables are a separate, unrelated Medium limitation: **Medium has no table support at all.** The
article has 2 tables. The stats table was dropped silently and the endpoints table was flattened so
every cell became its own paragraph.

## Do not re-import

The import already set "Originally published at https://blog.relayshield.net on August 5, 2026",
which is the canonical link. That part worked. Re-importing would only reproduce the same damage.
Repair the existing draft in the editor.

---

## Fix 1: the images

Delete every shield card in the body. Keep **one** as the featured image at the top, or replace it
with something specific to this post. There should be no RelayShield logo mid-article.

## Fix 2: the stats table, which vanished entirely

It sat between "We pulled these from x402scan on 5 August 2026, past 30 days across the whole x402
ecosystem:" and "Twelve million autonomous payments in a month." Paste this in that gap as a
bulleted list:

```
Transactions: 12,080,000
Volume: $767,290
Buyers: 18,670
Sellers: 83,000
```

## Fix 3: the endpoints table, which flattened into loose lines

Delete the run of orphaned lines from `/v1/payg/wallet-risk` through "Is this service a typosquat,
newly registered, or in a criminal IOC corpus". Replace with this, as a bulleted list with the
endpoint and price bolded:

```
wallet-risk, $0.05: is this address associated with known criminal activity
scan-wallet, $0.10: deeper wallet history and exposure
token-security, $0.05: is this token contract a honeypot or a fake mint
wallet-screen-batch, $0.50: screen many counterparties in one call
mcp-registry-risk, $0.35: is this service a typosquat, newly registered, or in a criminal IOC corpus
```

## Fix 4: the code block

The import collapsed the curl onto one line and left two empty code fences behind. Delete both
empty fences. Replace the curl with a Medium code block, triple backtick then paste, so the line
continuations survive:

```
curl -X POST https://api.relayshield.net/v1/payg/wallet-risk \
  -H 'Content-Type: application/json' \
  -d '{"address":"0x..."}'
```

## Fix 5: check the smart quotes

The imported text shows curly quotes in "we should buy this" and "money left the account". That is
correct and matches the source, so leave it. It only matters for AWS listing copy, which rejects
them.

---

## The root fix, so the next post does not do this

Two changes, both small:

1. **Per-post OG image.** Add an optional `image` field to the post objects in `blog_posts.js` and
   change `cloudflare_worker_blog.js:95` to `${post.image || SITE + '/og.png'}`. The pattern already
   exists as a one-off: `relayshield_session_hijack_cover.png` was built for the session-hijack post
   but the worker had no way to serve it per post.
2. **Add a favicon.** `/favicon.ico` currently 404s, which is why every icon slot falls through to
   the 134 KB shield card.

Neither is needed to fix today's draft. Both stop this recurring, which it has now done across
several sessions.
