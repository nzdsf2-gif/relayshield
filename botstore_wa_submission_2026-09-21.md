# botstore.info: submit the WhatsApp bot. Not the Telegram one.

**botstore.info is Dotgo's Bot Store: "World's First and Only Open and Global Directory of
RCS and WhatsApp Bots."** Read off its own homepage rather than inferred.

**THE TELEGRAM BOT DOES NOT GO HERE.** A Telegram bot is neither an RCS bot nor a WhatsApp
Business bot, and submitting it is the type-check failing in the same way `@telegtapps`
did. `@relayshield_bot` belongs on tg.app, tgboard and StoreBot, where it already is or is
queued.

**I WAS WRONG ABOUT THE SIGNUP FORM AND THIS CORRECTS IT.** I called it the consumer signup
and said finishing it would not let you list anything. Dotgo's own launch announcement
describes the flow the other way round: *"A brand can select the option to 'Submit a bot',
create an account for themselves, and upload information for their RCS and/or WhatsApp
bot."* **The account is the PREREQUISITE, not a detour.** The mobile-number-as-user-id and
the carrier field are just their account model, and they apply to a brand as much as to a
browser.

I inferred "consumer form" from the fields on it, which is reading a layout as a rule, the
same mistake as reading tg.app's sidebar as four permitted listings per bot. **A form's
fields tell you what it collects. They never tell you what it unlocks.**

**"Do You Develop Bots?" is not clickable**, which you found and I could not: `botstore.info`
is egress-blocked from the container, so I have never seen that page. It is a heading over
the **"Become an RBM Partner"** button beside it, not a link of its own.

---

## STEP 1 -- ANDREW RUNS THIS. Get the number, and fill it everywhere.

The listing needs the WhatsApp number, and `WA_NUMBER` is still the empty string in both
Workers, so every front-door link we own currently renders as nothing.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield python3 tools/wa_front_door_link.py --write

EXPECT: the number printed in E.164, and `cloudflare_worker_blog.js`,
`cloudflare_worker_miniapp.js` and the developers page reported as updated.
STOP IF: `ExpiredToken` or `AccessDenied` -- a fact about the AWS session, not about the
secret. Re-auth and re-run.
STOP IF: it refuses to print a link. It refuses anything that is not E.164 rather than
emitting one that would pass a probe and reach nobody: **`wa.me` answers a malformed number
with HTTP 200 and an "invalid" page**, so a broken front door looks live to every check we
own.

**It never prints the raw SecretString**, only the number, so this is safe to run with the
terminal visible.

## STEP 1b -- ANDREW RUNS THIS. Commit the THREE files it wrote, and know which deploy.

**CORRECTED 2026-09-21. The file list I gave in chat was wrong.** `--write` fills the number
only in the files that hold it as a COMMITTED CONSTANT, and `relayshield_developer_signup.py`
is deliberately not one: it is a Lambda, so it reads the number from Secrets Manager at
request time and needs no edit. The three it writes are:

    cloudflare_worker_blog.js
    cloudflare_worker_miniapp.js
    cloudflare_worker_checkemail.js

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    git --no-pager diff --stat cloudflare_worker_blog.js cloudflare_worker_miniapp.js cloudflare_worker_checkemail.js
    git add cloudflare_worker_blog.js cloudflare_worker_miniapp.js cloudflare_worker_checkemail.js
    git commit --no-edit -m "Fill WA_NUMBER so the front-door links render"
    git push -u origin main

EXPECT: three files changed, one line each.
STOP IF: more than one changed line per file. Send the diff before pushing.
Stage only these three by name: a wildcard add in your tree picks up the two embedded git
repositories.

**THE PUSH DEPLOYS TWO OF THE THREE, AND NOTHING IN ITS OUTPUT SAYS SO.**

| File | Deployed by |
|---|---|
| `cloudflare_worker_blog.js` | `deploy_blog.yml`, on push |
| `cloudflare_worker_miniapp.js` | `deploy_miniapp.yml`, on push |
| `cloudflare_worker_checkemail.js` | **nothing. No workflow mentions it.** |

`grep -rln checkemail .github/workflows/` returns nothing, so **every live version of the
checkemail Worker was pushed by hand.** This commit changes the repo copy and not what is
served: the blog and the Mini App would start rendering the WhatsApp link and the
email-check reply footer would not, with no error anywhere. That is the quiet-alarm shape.

**Recover it BEFORE deploying it.** A hand-deployed Worker is exactly where an uncommitted
edit survives, and `wrangler deploy` would replace it with the repo copy and print success:

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    sh tools/recover_live_worker.sh relayshield-checkemail cloudflare_worker_checkemail.js

EXPECT: `IDENTICAL`, or a diff showing only the `WA_NUMBER` line you just changed.
STOP IF: `THEY DIFFER` on anything else. Live holds something no commit does; send the diff
and it goes into git first. That is the 2026-08-17 rule, on the component class that still
has no automated path.

Only once that is clean:

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    npx wrangler deploy --config wrangler.checkemail.toml

EXPECT: a deployment id and the name `relayshield-checkemail`.
STOP IF: it asks you to log in. Run `npx wrangler login` first; a block driving an
authenticated CLI carries its auth step every time.


## STEP 2 -- ANDREW CLICKS THIS. Sign up first, then Submit a bot.

**1. Finish the account form you were already on.** It is the prerequisite, not the wrong
turn. The number you use becomes the login id.

**2. Signed in, look for "Submit a bot"** in the account area, the top-right user menu, or
where "Sign in / Sign up" used to be on the home page. Dotgo describes the flow as create an
account, then select the option to Submit a bot, so it should appear once you are
authenticated and not before.

**3. If it is nowhere, open `botstore.info/Whatsapp`** before anything else. That is a real
page on their site and it is the WhatsApp-specific one, which is the likeliest place a
WhatsApp listing route lives.

**4. Only if all three fail, email them.** There is a contact on `botstore.info/botstore-tos`
and `botstore.info/botstore-pp`. One message: *"We run a WhatsApp Business bot and would like
to list it. Where do we submit?"* A directory that cannot answer that in one reply is not
worth a third round.

**DO NOT click "Become an RBM Partner" to get a listing.** RBM is Google's RCS Business
Messaging: a carrier-side onboarding programme with a commercial process attached, not a
directory form. It is a far larger commitment than a catalogue row.

**UNVERIFIED, and it is why this is a search rather than a link.** `botstore.info` is
egress-blocked from this container, so all of the above comes from Dotgo's own launch
announcement and their indexed page list, never from the pages themselves. Your browser is
the primary source here, and it has already corrected me once today.


## STEP 3 -- the listing copy

**Link to give them**

```text
https://wa.me/<the number from step 1, digits only>?text=SRC_wa-botstore
```

Replace `<...>` with the digits. **That is a placeholder in a document, never in a command**
-- which is why step 1 prints it rather than this file carrying it.

**The `?text=SRC_wa-botstore` suffix is not optional.** WhatsApp has no deep-link payload,
so the token rides in the prefilled message body, and `parse_wa_source` reads it BEFORE the
user lookup and strips it from the message. There is **no allowlist** on that side, so the
key needs no registration anywhere -- but a listing pointing at a bare `wa.me/<number>` logs
nothing, leaves no `unmatched:` row to find later, and is indistinguishable from organic
traffic forever. **Omission is the unrecoverable mistake here.**

**Name**

```text
RelayShield | Scam & Breach Checker
```

**Category:** Security, or Utilities. Not Finance.

**Short description**

```text
Send a link or a wallet address and get a risk verdict back. Free, no account.
```

**Full description**

```text
RelayShield checks the things people are about to trust, and monitors the things an attacker needs to take over an account.

Send it a link or a cryptocurrency wallet address and it answers in seconds, free and with no account: the link is checked against Google Safe Browsing, a criminal indicator corpus and domain age, and the address is checked for drainer and scam-token signals across EVM, Solana, TON, Bitcoin and XRP.

It will never tell you something is safe. The most it says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training you to trust the one it misses.

For people who want ongoing cover, it also monitors your email, phone number and wallets for data breaches, infostealer malware logs and SIM-swap attempts, and messages you here the moment something surfaces. It then walks you through the fix step by step: close the email backdoors, revoke the stolen sessions, and only then reset the password, which is the order that actually works.

Built by a telecom security professional with 25 years on the carrier side.
```

**Tags:** `security`, `scam-detection`, `anti-phishing`, `cryptocurrency`, `data-breach`,
`identity-protection`

---

## WHAT CHANGED SO THIS LISTING IS WORTH HAVING

**Until today the bot answered a stranger with "your account isn't set up yet, visit
relayshield.net".** Listing a bot that bounces everyone who arrives is worse than not being
listed: a directory row is a standing shelf, and the first impression is the only one.

**It now runs the check.** `keyless_check()` in `relayshield_whatsapp_webhook.py` sends a
link to `/v1/link-check` and an address to `/v1/wallet-risk`, both of which are keyless by
design -- no signup, no card, capped per source IP rather than billed -- so there was never
a commercial reason to refuse. It simply was not wired.

Two rules are inherited from `widget/relayshield_widget.py` and neither is negotiable:

- **It never raises.** Every failure path returns a string. A stranger's first message must
  not produce a stack trace and silence.
- **It never says "safe".** The ceiling on a clean answer is "nothing known against it".

And when there is nothing checkable in the message, the greeting **leads with the
capability and puts the signup last**. A test asserts that ordering, because leading with a
wall is what this branch used to do.

**KNOWN LIMIT, recorded rather than discovered later:** the keyless cap is per source IP and
every call leaves through the Lambda's egress address, so heavy use could throttle the whole
WhatsApp front door against itself. That is the same NAT problem that decided
`relayshield_watchlist_monitor.py` imports its handler instead of calling the public
endpoint. The 429 is handled explicitly and says "busy, treat it as unchecked" rather than
folding into a generic failure, so the log distinguishes the cap from an outage. **The fix,
if it ever fires, is an internal API key from Secrets Manager, not a retry.**

**AND A MEASUREMENT GAP, stated so it is not read as a zero later:** the API-side
`source=wa-frontdoor` on those calls lands in `/aws/lambda/relayshield-api` and is counted
by **neither** `tools/miniapp_funnel.py`'s CHECKED stage (it filters `tg-miniapp*`) nor
`tools/source_arrivals.py`'s two surfaces. The arrival-side `SRC_wa-botstore` IS counted, by
the funnel's WHATSAPP stage. So the number of people who arrive is measurable today and the
number of checks they run is not.
