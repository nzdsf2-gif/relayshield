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

#### 4a -- DONE 2026-09-10. The bot has NO web apps, and one of my two warnings was wrong.

    /myapps  ->  "You currently have no web apps."
    /mybots  ->  "@relayshield_bot"

**So the short-name collision I warned about did not exist.** `app` was free all along; I described a
hazard I had still not looked up, which is the same defect the warning was about.

**The destructive half was real, and the mechanism is the MENU, not a registered app.**
`@relayshield_bot` runs the TI monitoring product through its menu button, and Andrew's instruction
is that **the menu keeps the prominent control**. `/setmenubutton` replaces what is there, so the
step would have taken it down. Right warning, wrong evidence -- and only the listing could say which.

#### 4b -- APPROVED. Yes, write it with these values.

Nothing collides, so this is clear to run.

```text
/newapp
```

1. **Which bot** -- `@relayshield_bot`
2. **Title** -- `RelayShield IDCheck`
3. **Short description** -- `Check a link or a wallet address before you trust it.`
4. **Photo** -- 640x360. Required; it cannot be skipped.
5. **GIF** -- optional. Reply `/empty`.
6. **Web App URL** -- `https://app.relayshield.net`
7. **Short name** -- `idcheck`

Giving `t.me/relayshield_bot/idcheck`.

**One note, not an objection, and the decision stands either way.** "IDCheck" reads slightly toward
IDENTITY verification, while the app checks links and wallet addresses. That is a small expectation
gap rather than a wrong name, it is short and brandable, and RelayShield does sell identity and
breach checks, so it is defensible. **Say so before any link ships if you want to change it** -- the
short name is in every published deep link and each announcement channel gives one first impression,
so it is cheap to change today and expensive next week.

**CLAUDE ALREADY DID THIS:** every planned deep link now reads
`t.me/relayshield_bot/idcheck?startapp=<source>` -- in `miniapp_discovery_and_stripe_choice.md` §2,
CLAUDE.md item 1 and route (4), and the `TOP_15_2026-09-09.md` snapshot. Nothing still says `/app`.

#### 4c -- THE MENU BUTTON STAYS WITH TI MONITORING. Settled, not deferred.

Andrew's instruction: the existing menu is the TI monitoring product's and **it should keep the
prominent control**. So `/setmenubutton` is not part of this launch and is not a later step either.

The Mini App does not need it. `t.me/relayshield_bot/idcheck` is a direct link that works on its own,
and item 1 already ranks the menu button fifth of six discovery routes -- cheap rather than
high-reach. Nothing is lost by leaving it where it is.

## What "it works" looks like

Open `https://t.me/relayshield_bot/idcheck` on a phone with Telegram
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
