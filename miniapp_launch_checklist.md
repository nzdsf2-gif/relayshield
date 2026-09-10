# The Telegram Mini App: why it is not reachable yet, and the four steps that make it reachable

Written 2026-09-09, in answer to "I ran the merge that deployed the Tg miniApp in the last session.
How do I access the miniApp on Tg?"

**The short answer: the merge did not deploy it, and even a successful deploy would not have made it
reachable from Telegram.** Those are two separate blockers with two separate fixes, and both are
below. Neither is a defect in the Mini App code, which builds, embeds a current widget and passes its
ten tests.

---

## Blocker 1: the merge never reached GitHub, so the deploy workflow has never had a reason to run

This is the LOCAL MERGE IS NOT A PUSH rule, in the direction that costs a deploy.

Verified here, not recalled. `origin/main` is at `556b4f1`, and it does not carry any of the three
files the Mini App needs:

    git ls-tree origin/main --name-only | grep -E "miniapp"
    # returns miniapp_discovery_and_stripe_choice.md and
    # telegram_miniapp_and_app_inventory_scope.md -- the DOCS. Not
    # cloudflare_worker_miniapp.js and not wrangler.miniapp.toml.

`cloudflare_worker_miniapp.js`, `wrangler.miniapp.toml` and `.github/workflows/deploy_miniapp.yml`
are all still only on `claude/tg-miniapp-rs-ide-widget-ltz7e3`.

**Two consequences, and the second one is the trap.**

`deploy_miniapp.yml` triggers on `push: branches: [main]` with a `paths:` filter. A merge on the Mac
produces no push, so there was no event and there is no run. That much is the ordinary case.

**The trap: the workflow file itself is not on the default branch either, so it also cannot be
dispatched from the Actions UI.** GitHub only offers *Run workflow* for workflows present on the
default branch. So the usual fallback -- "Claude cannot dispatch, Andrew clicks Run workflow" -- is
not available here. There is no route to deploying this that does not begin with pushing `main`.

---

## Blocker 2: a deployed Worker is a web page, not a Mini App

`app.relayshield.net` being live would mean the page loads in a browser. Telegram does not serve an
arbitrary URL as a Mini App. **A Mini App exists only after it is registered against the bot in
@BotFather**, and that registration is what mints the `t.me/relayshield_bot/<short_name>` link.

Until `/newapp` has been run, there is no Telegram URL to open, no menu-button target, and nothing
for `?startapp=` to attach to -- which means the five attribution keys the Worker is careful to
validate have nowhere to arrive from.

**This step is not in the repo, and could not be.** It is a conversation with a bot, not a file. Its
absence from the Mini App v1 work is a genuine gap, and writing it down here is the fix: the next
session reads this rather than rediscovering that the Worker alone is not enough.

---

## The four steps, in order

Each one is labelled with who does it and what interpreter it is for.

### Step 1 -- ANDREW RUNS THIS: push main

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/tg-miniapp-rs-ide-widget-ltz7e3
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
git --no-pager log --oneline -1
git push -u origin main
```

EXPECT: the log line names the Mini App commit or something after it, and the push reports a ref
update ending `-> main`.
STOP IF: `Everything up-to-date` on the push AND the log does not name the Mini App commit -- that
means the merge did not take, not that you are current. Send the output.
STOP IF: `error: You have not concluded your merge (MERGE_HEAD exists)` -- run `git commit --no-edit`
first, then re-run the block.

### Step 2 -- CLAUDE ALREADY DID THIS, then the push does the rest

The two checks the deploy workflow runs before it touches Cloudflare were both run here and both
pass: `python3 tools/build_miniapp.py --check` reports `IN SYNC: embedded widget matches
widget/relayshield-widget.js (8384 chars)`, and `test_miniapp.py` runs 10 tests OK.

So the push in step 1 should reach the deploy step without stopping at either gate. Watch the run;
it is *Deploy Telegram Mini App* in the Actions tab.

### Step 3 -- ANDREW CHECKS THIS: does `app.relayshield.net` resolve

**This is the most likely first failure and it fails quietly.** `wrangler.miniapp.toml` uses the
zone-route form, the same one `blog`, `badge`, `partners`, `pricing` and `support` all use and which
works for all five:

```toml
routes = [
  { pattern = "app.relayshield.net/*", zone_name = "relayshield.net" }
]
```

A zone route attaches to a hostname; it does not create one. If `app` has no proxied DNS record in
the `relayshield.net` zone, **wrangler will report a successful deploy and the hostname will not
resolve.** That is the deploy-succeeded-and-nothing-works shape this repo has now hit in three
different systems.

I cannot check it from here: `app.relayshield.net` is egress-blocked from the container, and the 403
that came back is the proxy's policy denial, which is a fact about my request and not about the
hostname.

ANDREW RUNS THIS:

```zsh
curl -sS -o /dev/null -w "%{http_code}\n" https://app.relayshield.net/
```

EXPECT: `200`.
STOP IF: `000` with a DNS error, or a Cloudflare 1000-series error page -- the record is missing. Add
an `app` record in the Cloudflare dashboard for `relayshield.net`, proxied (orange cloud); a CNAME to
the zone apex is enough, since the Worker route intercepts before origin. Then re-check.
STOP IF: `404` or Carrd's own not-found page -- that is the CS-BADGE-2 pattern, where zone-level
routes lost to a custom-hostname setup. The fix there was `custom_domain = true`; say so and it can
be changed in one line.

### Step 4 -- ANDREW TYPES THIS IN TELEGRAM, to @BotFather

Not a shell block. These are messages sent to @BotFather in the Telegram app.

```text
/newapp
```

BotFather then asks, in this order:

1. **Which bot** -- choose `@relayshield_bot`.
2. **Title** -- `RelayShield`.
3. **Short description** -- `Check a link or a wallet address before you trust it.`
4. **Photo** -- 640x360. Required; it cannot be skipped.
5. **GIF** -- optional. Reply `/empty`.
6. **Web App URL** -- `https://app.relayshield.net`
7. **Short name** -- `app`

The short name is what appears in the URL, so `app` gives `t.me/relayshield_bot/app`, which is the
form `miniapp_discovery_and_stripe_choice.md` §2 and CLAUDE.md item 1 both already assume for the
attributed deep links. **Choose `app` rather than anything longer**, or every published link in those
plans is wrong before it ships.

Then, so it is reachable from inside the bot as well:

```text
/setmenubutton
```

Choose `@relayshield_bot`, then supply the same URL and a button label such as `Check a link`.

**UNVERIFIED:** the BotFather prompt sequence above is from the Bot API's documented `/newapp` flow.
I cannot run BotFather from this container, so if the order of the prompts differs, follow what
BotFather actually asks -- the values are what matter, not the sequence.

---

## What "it works" looks like

Open `https://t.me/relayshield_bot/app` on a phone with Telegram installed. The app opens inside
Telegram, in Telegram's own colours (the Worker reads `--tg-theme-*`), with one input. Paste
`0x0000000000000000000000000000000000000000` or any URL and a verdict comes back with no signup, no
key and no wallet connect, because `/v1/link-check` and `/v1/wallet-risk` are both keyless.

**Then check attribution actually flows**, because that is the half that fails silently:

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 7 --key tg-miniapp
```

EXPECT: a non-zero count against `tg-miniapp` after opening
`https://t.me/relayshield_bot/app?startapp=tg-miniapp-blog` once.
STOP IF: an `unmatched:` row appears -- a link is carrying a key that is not registered. All five
keys the Worker forwards are registered today, pinned by `test_source_arrivals.py`, so an unmatched
row means a link was hand-written with a sixth.

---

## Do not submit anywhere until step 4 is done

CLAUDE.md item 1 is explicit and it is the whole risk: each announcement channel gives **one** first
impression, and `@trendingapps` is 3.9M of them. A submission that lands while `t.me/relayshield_bot/app`
still 404s spends that impression on a broken link. Build, deploy, register, open it yourself on a
phone, and only then submit.
