# Fourth-Party Exposure (Privy/Metabase): Distribution Package

Everything below is **exact paste content**. Nothing here needs rewriting before it goes out.

---

## Canonical (LIVE, published 2026-08-17)

**URL:** https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

Worker version `e5b1f92c`. Verified HTTP 200 and rendering, listed on the blog index, and confirmed
free of the internal checklist that was appended to the source file.

**Post body source:** `blog_source/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard.md`
Everything below the `<!-- NOT FOR PUBLICATION -->` marker in that file is internal and `build_blog.py`
now strips it. That file is the paste source for any channel that needs the whole body.

### Metadata

- **Display title:** Your Wallet Provider Had a Vendor, and That Vendor Had a Dashboard
- **SEO title** (~60 char budget): Fourth-Party Risk: When Your Vendor's Vendor Leaks
- **Meta description** (150 limit): A Kraken notice about Privy about a vendor's Metabase. My email was four parties from the company I signed up with, and that is where it went.
- **Slug:** `your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard`
- **Cover image:** none generated. A four-node chain (You, Kraken, Privy, Vendor, Metabase) with the
  last node circled would carry the whole argument. **Do not block publishing on it.**

### Attribution keys (REGISTERED AND DEPLOYED 2026-08-17, all 8 verified live)

Each renders the fourth-party banner on `/developers`. An unregistered key renders nothing and logs
`unmatched:`. Verified key by key after deploy; a control key correctly rendered nothing.

> **These are CTA links that go inside a post. None of them is ever the URL you import, paste into a
> share box, or hand to a syndication tool.** The canonical above is the only URL that represents the
> article.

| Channel | Link to use |
|---|---|
| Blog CTA (already in post) | `https://api.relayshield.net/developers?source=blog-fourth-party` |
| Medium | `https://api.relayshield.net/developers?source=fourth-party-medium` |
| LinkedIn | `https://api.relayshield.net/developers?source=fourth-party-linkedin` |
| Telegram | `https://api.relayshield.net/developers?source=fourth-party-telegram` |
| Mastodon | `https://api.relayshield.net/developers?source=fourth-party-mastodon` |
| Farcaster | `https://api.relayshield.net/developers?source=fourth-party-farcaster` |
| Reddit | `https://api.relayshield.net/developers?source=fourth-party-reddit` |

**Referer matching also covers this post**, so a click still attributes even when a platform strips
the query string (Medium does exactly this). **Do not invent a new key** without adding it to
`_SOURCE_ALIASES` in `relayshield_developer_signup.py` and redeploying.

---

## 1. Medium

**Import, do not paste.** Use Medium's Import Story tool with the canonical URL above. Pasting breaks
code blocks and loses the canonical link, which costs the SEO value of the syndication.

**Import URL:** `https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard`

**Subtitle** (paste under the title after import):

```
I got a security notice from Kraken this week. It was not about Kraken.
```

**Tags (maximum 5, Medium ranks on them):**

```
Cybersecurity
Crypto
Vendor Risk
Phishing
Supply Chain Security
```

**After import, one edit:** change the closing CTA link to
`https://api.relayshield.net/developers?source=fourth-party-medium`. Expect Medium to strip the query
string from the rendered href. That is known and fine, because referer matching catches it.

---

## 2. LinkedIn

Post as text, link in the first comment. LinkedIn suppresses posts with outbound links in the body.

**Post body:**

```
I got a security notice from Kraken this week. It was not about Kraken.

It was about Privy, which provides the embedded wallets behind Kraken's DEX trading and DeFi Earn.
And it was not really about Privy either. It was about Metabase, an analytics tool operated by one
of Privy's vendors, compromised through a previously unknown vulnerability.

Count the hops. I have a relationship with Kraken. Kraken has one with Privy. Privy has one with a
vendor. That vendor runs Metabase. My email address was four parties away from the company I
actually signed up with, sitting in a business intelligence dashboard, and that is where it was
taken from.

Nothing was drained. No wallet infrastructure was touched. Both companies disclosed quickly and in
plain language, which is better than the median.

So on the surface this is a nothing event. A dashboard leaked some email addresses.

I think it is the opposite, and precisely because no wallet was touched.

An attacker who wants your crypto does not need to break your wallet if they can get your email
address plus the knowledge that you hold crypto. A generic email dump is worth very little. A list
of addresses known to belong to people with funded wallets on a specific exchange is worth a great
deal, because it turns a spray campaign into a targeted one.

There is no exploit in that attack. The theft, if it happens, occurs weeks later in someone's inbox
and looks like a completely unrelated event.

Plenty of organisations screen their suppliers. Some screen their suppliers' suppliers. Almost
nobody screens their suppliers' suppliers' internal tooling choices.

I could not have told you before this week that Privy used Metabase, and there is no reasonable
process by which I should have known.

Full write-up in the comments.

#CyberSecurity #VendorRisk #ThirdPartyRisk #SupplyChainSecurity #Crypto #Phishing #InfoSec
```

**First comment (post immediately):**

```
Full post: https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

It also covers the concentration problem underneath this, which is the part I find harder to
dismiss than the incident itself.
```

**Hashtag notes:** 7 is within LinkedIn's useful range. `#VendorRisk` and `#ThirdPartyRisk` are the
two that reach risk and procurement people rather than only security people, which is the audience
this post is actually for.

---

## 3. Telegram

Post to the RelayShield channel. Telegram renders the link preview from the canonical, so no image
needed.

```
**Your wallet provider had a vendor, and that vendor had a dashboard**

I got a security notice from Kraken this week. It was not about Kraken.

It was about Privy, who provide the embedded wallets behind Kraken's DEX trading and DeFi Earn. And
not really about Privy either: about Metabase, an analytics tool run by one of Privy's vendors,
compromised through a previously unknown vulnerability.

Four hops from me to the dashboard my email was sitting in.

Nothing was drained, and both companies disclosed quickly. Which is exactly why it is worth reading.
An attacker who wants your crypto does not need your wallet if they have your email plus the
knowledge that you hold crypto. That combination turns a spray campaign into a targeted one, and the
actual theft happens weeks later in your inbox looking like an unrelated event.

Almost nobody screens their suppliers' suppliers' tooling choices. I could not have told you that
Privy used Metabase, and there is no reasonable process by which I should have known.

https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

#infosec #crypto #vendorrisk #phishing
```

---

## 4. Mastodon

500 character limit. **This is 451 characters, measured, with 49 to spare.** An earlier draft of
this section claimed 497 and was actually 519, which would have failed at paste time. The canonical
URL alone is 94 characters, so leave the headroom rather than adding a sentence.

```
A security notice from Kraken that was not about Kraken.

It was about Privy, who run their embedded wallets. And not really Privy either: about Metabase, an analytics tool at one of Privy's vendors.

Four hops from me to the dashboard holding my email.

No funds touched. That is the point: email plus "owns crypto" is a targeting list.

https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

#infosec #crypto
```

---

## 5. Farcaster

**Farcaster counts BYTES, not characters, and the limit is 320.** Check before posting:

```bash
python3 -c "print(len(open('farcaster_fourth_party.txt','rb').read()), 'bytes')"
```

Cast (**279 bytes, measured**, 41 to spare). The URL is 94 of those bytes, so do not extend it.

```
Kraken emailed me about Privy. Privy's notice was about a vendor. That vendor ran Metabase.

Four hops from me to the dashboard my email was in. No funds moved, and that is the point.

https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard
```

**Channel:** post to `/security`, and cross-post to `/crypto` only if the first lands well.
Farcaster does not use hashtags the way the others do; the channel is the tag.

---

## 6. Reddit, worth it for this post specifically

This is a first-person account of a notice many people received, not a product announcement, which
is the only reason it is postable at all. **Check each subreddit's self-promotion rule first**, and
**disclose the affiliation in the body**. That is the lesson from the Discord work on 2026-08-13.

**Target:** r/CryptoCurrency first. r/ethdev only if the first goes well.

**Title:**

```
Kraken sent me a breach notice about their wallet provider's vendor's analytics tool. Four hops.
```

**Body:**

```
I got a security notice from Kraken this week that was not about Kraken.

It was about Privy, who provide the embedded wallets behind Kraken's DEX trading and DeFi Earn. And
it was not really about Privy either. It was about Metabase, an analytics and support tool operated
by one of Privy's vendors, compromised through a previously unknown vulnerability.

Count the hops: me, Kraken, Privy, Privy's vendor, that vendor's Metabase instance. My email address
was four parties away from the company I signed up with.

Nothing was drained. Kraken says accounts, credentials and funds were unaffected, and Privy told
them Metabase had no access to wallet infrastructure. Both disclosed quickly and clearly, which I
want to state plainly before arguing anything on top of it.

What I keep thinking about is that the attacker did not need the wallet. A generic email dump is
worth very little. A list of addresses known to belong to people with funded embedded wallets on a
specific exchange is worth a lot, because it turns a spray campaign into a targeted one. The phisher
already knows which product you use and what subject line will not look out of place.

The theft, if it happens, occurs weeks later in someone's inbox and will look like a completely
separate event.

I wrote it up properly here, including the concentration problem underneath it:
https://blog.relayshield.net/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

Disclosure: I run RelayShield, which works on identity exposure. The post explicitly says we would
not have caught this one, because we would not have.
```

**No hashtags on Reddit.** Flair as `SECURITY` on r/CryptoCurrency.

---

## Do not post

- **X / Twitter.** `@RelayShieldHQ` is suspended.
- **Hashnode.** Retired, standing instruction. Never publish there again.
- **HackerNoon.** Paid for company domains, abandoned 2026-08-11.

---

## Sequencing

1. **Medium import** first, so the canonical has a syndication partner indexed early.
2. **LinkedIn** next, weekday morning, link in first comment.
3. **Telegram** and **Mastodon** same day, any time.
4. **Farcaster** same day, byte count checked.
5. **Reddit** last and only after reading the current rules, because it is the one that can go wrong.

## Two things that are still the founder's call

1. **Re-read the Kraken notice against the post.** Every factual claim comes from it. If a detail is
   not in the notice, cut the sentence rather than rewording it.
2. **Check whether Privy has published its own statement.** If it has, link it and reconcile any
   difference. If its account differs from Kraken's relay, use Privy's.

The post has shipped, so if either check fails, edit `blog_source/` and re-run
`python3 build_blog.py && npx wrangler deploy --config wrangler.blog.toml`.
