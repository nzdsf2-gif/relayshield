# The Telegram Mini App: why it is not reachable yet, and the four steps that make it reachable

Written 2026-09-09, in answer to "I ran the merge that deployed the Tg miniApp in the last session.
How do I access the miniApp on Tg?"

**The short answer: the merge did not deploy it, and even a successful deploy would not have made it
reachable from Telegram.** Those are two separate blockers with two separate fixes, and both are
below. Neither is a defect in the Mini App code, which builds, embeds a current widget and passes its
ten tests.

---

## Blocker 1: the merge never reached GitHub -- RESOLVED 2026-09-09

`origin/main` is now `c66c49b` and carries all three files; the deploy ran green. What follows
is the diagnosis as written, kept because the second edge of it is worth keeping.

### The diagnosis

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

### Step 1 -- DONE 2026-09-09. `origin/main` is at `c66c49b` and carries the Mini App.

**The merge conflicted in CLAUDE.md and this block did not say what to do about that** -- see the
correction in CLAUDE.md, section A. Andrew resolved it and pushed; the deploy ran green. Kept below
as the record of what was run.

#### The block as it was sent

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

### Step 3 -- app.relayshield.net DID NOT RESOLVE, AND THE FIX IS A ONE-LINE CONFIG CHANGE

**CORRECTED 2026-09-09.** He ran the check and got exactly what the previous version of this file
warned about:

    curl: (6) Could not resolve host: app.relayshield.net

**That warning should have been a fix, and it is now.** A zone route attaches a Worker to a hostname;
it does not create the hostname. `blog`, `badge`, `partners`, `pricing` and `support` all use the
zone-route form and all work, because those subdomains already had proxied DNS records. `app` was
new, so there was no record for the route to attach to -- and wrangler reported a successful deploy
regardless, which is why the *Deploy Telegram Mini App* run went green over a hostname that does not
exist.

`wrangler.miniapp.toml` now uses the form that CREATES the record:

    routes = [
      { pattern = "app.relayshield.net", custom_domain = true }
    ]

The `/*` and the `zone_name` are gone on purpose: a custom domain is a hostname, not a path pattern,
and wrangler rejects the combination.

**ANDREW RUNS THIS**, after merging this branch:

```zsh
cd ~/dev/relayshield
git --no-pager log --oneline -1 -- wrangler.miniapp.toml
curl -sS -o /dev/null -w "%{http_code}\n" https://app.relayshield.net/
```

EXPECT: the log line names this session's commit, and the curl prints `200`.
STOP IF: the curl prints `000` with `Could not resolve host` -- the deploy has not re-run yet. The
merge itself triggers it, because `wrangler.miniapp.toml` is in the workflow's `paths:` filter, so
give the run a minute and re-check. DNS on a fresh Cloudflare custom domain can take a few minutes
beyond that.
STOP IF: the *Deploy Telegram Mini App* run goes red naming DNS or authentication -- the deploy token
lacks DNS edit on the zone. Say so and add an `app` CNAME to the zone apex by hand, PROXIED (orange
cloud). **UNVERIFIED:** the same token already created the `badge.relayshield.net` custom-domain
binding, so the permission is very likely present, but I cannot test a Cloudflare token from this
container.

---

### Step 4 -- BotFather. THE PREVIOUS VERSION OF THIS STEP WAS DANGEROUS. READ THIS FIRST.

**Andrew caught it and he was right.** The earlier draft told him to run `/newapp` with short name
`app` and then `/setmenubutton`. `@relayshield_bot` **already carries the Telegram TI monitoring
app**, and:

- **`/setmenubutton` REPLACES the bot's existing menu button. It does not add a second one.**
  Running it would have removed a live customer-facing surface, and nothing in this repo records
  what that button currently points at, so there would have been no way to put it back.
- **`app` is a generic short name on a bot that already has apps.**

I wrote a registration procedure for a surface whose contents I had never listed. The corrected
procedure reads before it writes, and it is two steps, not one.

#### 4a -- READ. ANDREW TYPES THIS IN TELEGRAM, to @BotFather

Not a shell block. This is a message sent to @BotFather in the Telegram app. **It only lists things.
It changes nothing.**

```text
/myapps
```

This returns the web apps already registered against your bots. **Send back what it lists for
`@relayshield_bot`** -- the short names in particular. Two things get decided from that output and
neither can be decided without it: which short name is free, and what the TI monitoring app is
called so the new one is clearly distinct from it.

While you are there, the menu button's current target is worth knowing too. `/mybots` ->
`@relayshield_bot` -> *Bot Settings* -> *Menu Button* shows it without changing it.

#### 4b -- WRITE. Only after 4a's output has been read

```text
/newapp
```

BotFather then asks, in this order:

1. **Which bot** -- `@relayshield_bot`.
2. **Title** -- `RelayShield Check`. Distinct from the TI monitoring app in the app list.
3. **Short description** -- `Check a link or a wallet address before you trust it.`
4. **Photo** -- 640x360. Required; it cannot be skipped.
5. **GIF** -- optional. Reply `/empty`.
6. **Web App URL** -- `https://app.relayshield.net`
7. **Short name** -- **`linkcheck`**, unless 4a shows it taken.

**Why `linkcheck` and not `app`.** It describes what the thing does, it is unlikely to collide with
anything a TI monitoring product would be called, and it reads correctly in the URL it produces:
`t.me/relayshield_bot/linkcheck`. **It is a proposal, not a decision** -- 4a's output is what
settles it, and if you prefer something else, say so and everything downstream is updated to match
rather than the other way round.

**THE ONE THING THAT MUST BE UPDATED IF THE SHORT NAME CHANGES.** `miniapp_discovery_and_stripe_choice.md`
and CLAUDE.md item 1 both write the deep links as `t.me/<bot>/app?startapp=<source>`. That `app` was
written when nobody had checked what the bot already had. **Whatever 4b actually registers is the
name those links must carry**, and they are the links that go to `@trendingapps` and the
directories -- each of which gives one first impression. Tell me the final short name and I will
correct every planned link in one commit.

#### 4c -- THE MENU BUTTON: DO NOT TOUCH IT YET

`/setmenubutton` is **not** part of this launch. It replaces what is there, the TI monitoring app may
be using it, and **the Mini App does not need it**: `t.me/relayshield_bot/<short_name>` is a direct
link that works on its own, and item 1 ranks the menu button fifth of six discovery routes anyway --
cheap rather than high-reach.

Decide it separately, once 4a has said what the button currently does. If the answer turns out to be
"nothing", it is free and worth taking. If it is the TI app, that is a product decision about which
surface owns the bot's single most prominent control, and it is not a step in a launch checklist.

---

## What "it works" looks like

Open `https://t.me/relayshield_bot/<the short name 4b registered>` on a phone with Telegram
installed. The app opens inside Telegram, in Telegram's own colours (the Worker reads
`--tg-theme-*`), with one input. Paste `0x0000000000000000000000000000000000000000` or any URL and a
verdict comes back with no signup, no key and no wallet connect, because `/v1/link-check` and
`/v1/wallet-risk` are both keyless.

**Then check attribution actually flows**, because that is the half that fails silently:

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 7 --key tg-miniapp
```

EXPECT: a non-zero count against `tg-miniapp` after opening the app once with `?startapp=tg-miniapp-blog`.
STOP IF: an `unmatched:` row appears -- a link is carrying a key that is not registered. Every key
the Worker forwards is registered today, pinned by `test_source_arrivals.py`, so an unmatched row
means a link was hand-written with one that is not.

---

## Do not submit anywhere until 4b is done and the link opens on a phone

CLAUDE.md item 1 is explicit and it is the whole risk: each announcement channel gives **one** first
impression, and `@trendingapps` is 3.9M of them. A submission that lands while the link 404s spends
that impression on a broken link.
