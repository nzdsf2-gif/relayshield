// RelayShield Telegram Mini App v1 — app.relayshield.net
//
// ONE JOB, DONE WELL. Paste a link or a wallet address, get a verdict. That is
// the whole app, and it is deliberate: miniapp_discovery_and_stripe_choice.md
// records that "a Mini App with one job done well is the only version that gets
// recommended onward, which is the one channel that compounds."
//
// IT IMPORTS THE WIDGET'S CHECK RATHER THAN REIMPLEMENTING IT. widget/relayshield-widget.js
// already carries the chain detection, the keyless endpoint calls and the verdict
// shaping, all pinned by tests. This repo already has four copies of one pattern
// table and does not need a fifth, so the module is SERVED from here and imported
// by the page. One implementation, one set of tests, two surfaces.
//
// KEYLESS BY CONSTRUCTION. /v1/link-check and /v1/wallet-risk are both in
// KEYLESS_SCAN_ENDPOINTS, capped per source IP. So a first-time user gets an
// answer with no signup, no key and no wallet connect, which is the only version
// of this that a stranger opening a Telegram link will actually complete.
//
// ATTRIBUTION, AND THE ORDER MATTERS. Telegram's startapp parameter arrives as
// `?startapp=<key>` and Telegram surfaces it to the page as
// `Telegram.WebApp.initDataUnsafe.start_param`. Every link we publish carries its
// own key, and each one is registered in _SOURCE_BANNERS BEFORE the link ships.
// FD-8 is four months of unattributed arrivals from skipping exactly that step.
//
// WHAT IT DOES NOT DO, on purpose:
//   * No wallet connect. TON Connect is a v2 question and would gate the first
//     answer behind a wallet, which is the opposite of the point.
//
// INITDATA IS SENT AND IS VERIFIED SERVER-SIDE. An earlier version of this
// header said signature verification was unnecessary "because nothing here is
// user-specific" -- true until the watchlist existed, and exactly the kind of
// comment that goes stale silently. The watchlist is per-user, so the page sends
// Telegram's SIGNED initData and relayshield_watchlist.py takes the user id from
// the verified payload. The raw id is never sent and would not be trusted if it
// were: a per-user store that believes a client-supplied id has no access
// control at all.
//   * No analytics beyond the ?source= key the API already logs.

const API_BASE = "https://api.relayshield.net";
const DEVELOPERS = API_BASE + "/developers";
// THE MONITORING BOT, and this constant was DECLARED AND NEVER USED until
// 2026-09-10. The only call to action in the whole app was the developer link
// in the footer, so a consumer who had just been shown a flagged scam was being
// sold an API. The stickiness plan's own mechanism -- "the Mini App creates bot
// subscribers rather than the bot's tiny audience carrying the Mini App" --
// requires a path from here to there, and there was none.
//
// SRC_ is the bot's existing acquisition-source deep link
// (relayshield_telegram_webhook.py, handle_start). It takes a free-form channel
// label, logs it and stores it once on the user record, so unlike _SOURCE_BANNERS
// this needs no key registered in advance and cannot log `unmatched:`. First
// touch wins there, deliberately.
const BOT = "https://t.me/relayshield_bot?start=SRC_miniapp";

/* THE WHATSAPP FRONT DOOR. WORKER SCOPE, and it stays here: the page reads it
   only through the __WA_LINK__ substitution above.

   Bare digits, no "+" and no spaces. wa.me answers a malformed number with a
   200 and a "phone number shared via url is invalid" page rather than a 404,
   so a wrong value produces a link that passes every probe and reaches
   nobody -- which is why waLink() returns the EMPTY STRING when this is unset
   and the footer paragraph simply does not render.

   The number lives in Secrets Manager (relayshield/twilio_whatsapp_number)
   and nowhere else, and a Worker cannot read Secrets Manager. Fill it from:
     AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/wa_front_door_link.py
   The same value goes in cloudflare_worker_blog.js and a test pins them
   equal. */
const WA_NUMBER = "";
const WA_SOURCE = "wa-miniapp";

function waLink() {
  if (!WA_NUMBER) return "";
  return '<p class="inline-footer">On WhatsApp instead? '
    + '<a href="https://wa.me/' + WA_NUMBER + '?text=SRC_' + WA_SOURCE + '">'
    + 'Message RelayShield there</a> and we will monitor your email, phone '
    + 'and wallets for breaches, infostealer logs and SIM-swap attempts, and '
    + 'alert you in that chat.</p>';
}

/* THE SLOT NUMBERS, SUBSTITUTED INTO STATIC COPY AT REQUEST TIME.

   They exist here because the watch tab's pricing was rendered ENTIRELY from
   the /v1/watchlist/list response, so a user who was not verified, or whose
   list call failed, saw no mention of the paid tier at all -- and that reads
   exactly like a product that has no paid tier. What we charge for is a fact
   about our own product and must not depend on a network call succeeding.

   They are NOT page-scope constants: the page and the Worker run in different
   processes and share nothing but these __TOKEN__ substitutions, which is the
   INLINE_TEXT defect recorded in CLAUDE.md. Substituting into the HTML keeps
   one source and no cross-scope read.

   AND THEY MUST AGREE WITH relayshield_watchlist.py, which is the authority:
   FREE_WATCH_SLOTS, PAID_WATCH_SLOTS, SLOTS_PRICE_STARS, SLOTS_DURATION_DAYS.
   test_miniapp_routes.py fails if they drift. Copy shown to a buyer that
   disagrees with what the server will actually grant is worse than no copy. */
const FREE_SLOTS = "3";
const PAID_SLOTS = "25";
const SLOTS_STARS = "50";
const SLOTS_DAYS = "90";

// Keys the Mini App may pass through as ?source=. An unknown start_param is
// dropped rather than forwarded: an unregistered key logs `unmatched:` and
// renders no banner, so forwarding junk would look like attribution and be none.
/* The ?startapp= values this app will honour. Anything else falls back to the
   generic "tg-miniapp", so a key missing from HERE is attribution that looks
   like it worked: the app opens, the call is logged, and the route is gone.

   miniapp_routes.json is the source of truth and test_miniapp_routes.py fails
   if this set and _SOURCE_ALIASES in relayshield_developer_signup.py do not
   both cover it. Three lists that must agree with nothing checking that they
   do is the shape that produced run 134's red probe.

   ONE KEY PER DESTINATION, not per category. "tg-miniapp-channel" used to
   cover all five announcement channels, which made the 3.9M-subscriber one
   and the 9,671-subscriber one indistinguishable -- and which of those works
   is the whole question the funnel exists to answer. It is kept below only so
   links already published with it still resolve. */
const ALLOWED_SOURCES = new Set([
  "tg-miniapp",
  "tg-miniapp-blog",
  "tg-miniapp-trendingapps",
  "tg-miniapp-web3botx",
  "tg-miniapp-findminiapp",
  // The findmini.app WEB directory, distinct from the @findminiapp channel
  // above. Same operation very probably; still two destinations, because a
  // channel post is one impression and a directory listing is a standing shelf.
  "tg-miniapp-findminiweb",
  // minitelegram.com, the second web directory. Registered before the
  // submission, never after: an unregistered key is downgraded here.
  "tg-miniapp-minitelegram",
  // Three more catalogue destinations, registered 2026-09-14 BEFORE any of them
  // is submitted to. tonapp is the TON ecosystem's own catalogue; tgapp is a
  // general Telegram apps directory; awesome is the GitHub curated list, whose
  // audience is developers rather than consumers.
  "tg-miniapp-tonapp",
  "tg-miniapp-tgapp",
  "tg-miniapp-tgboard",
  "tg-miniapp-awesome",
  // Two destinations registered 2026-09-19, BEFORE either is submitted to.
  // dappradar is a dapp catalogue whose audience holds TON, which is the one
  // audience for whom a TON-only Check tab is the headline. producthunt is
  // deliberately NOT a catalogue: a launch is one day, so it is ranked last
  // and spent only after a listing has proved the copy.
  "tg-miniapp-dappradar",
  "tg-miniapp-producthunt",
  "tg-miniapp-onclicka",
  "tg-miniapp-telegtapps",
  "tg-miniapp-tapps",
  "tg-miniapp-directory",
  "tg-miniapp-ton",
  // Not routes. The share card is the compounding loop and the bot
  // commands reach people who already have the bot, so both are counted
  // separately rather than credited to a submission we made.
  "tg-miniapp-share",
  "tg-miniapp-bot",
  // Outbound, not an arrival -- but it must be here anyway, because a developer
  // who follows the link and later opens the app from it would otherwise be
  // downgraded to the generic key and the flywheel would read as zero.
  "tg-miniapp-bottoken",
  // Retired. Links published before 2026-09-11 carry it, and dropping it
  // would break attribution on every one of them at once.
  "tg-miniapp-channel",
]);

function sourceFor(startParam) {
  return ALLOWED_SOURCES.has(startParam) ? startParam : "tg-miniapp";
}

const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>RelayShield</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #17212b);
    --text: var(--tg-theme-text-color, #f5f5f5);
    --hint: var(--tg-theme-hint-color, #94a3b8);
    --card: var(--tg-theme-secondary-bg-color, #202b38);
    --accent: var(--tg-theme-button-color, #3b82f6);
    --accent-text: var(--tg-theme-button-text-color, #ffffff);
    --crit: #ef4444; --high: #f97316; --med: #eab308;
    --low: #22c55e; --unknown: #94a3b8;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px 16px 32px;
    background: var(--bg); color: var(--text);
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  h1 { font-size: 1.15rem; margin: 0 0 4px; }
  .sub { color: var(--hint); font-size: .85rem; margin: 0 0 16px; }
  nav { display: flex; gap: 6px; margin: 0 0 16px; }
  nav button {
    flex: 1; padding: 9px 6px; font: inherit; font-size: .88rem;
    background: var(--card); color: var(--hint);
    border: 1px solid transparent; border-radius: 10px;
  }
  nav button[aria-selected="true"] { color: var(--text); border-color: var(--accent); }
  .cta { margin-top:14px; padding-top:12px; border-top:1px solid rgba(148,163,184,.25);
         font-size:.9rem; color:var(--hint); line-height:1.45; }
  .cta a { display:inline-block; margin-top:6px; color:var(--accent);
           text-decoration:none; font-weight:600; }
  textarea {
    width: 100%; min-height: 80px; padding: 12px; resize: vertical;
    background: var(--card); color: var(--text);
    border: 1px solid rgba(148,163,184,.25); border-radius: 12px;
    font: inherit; font-size: 16px;
  }
  textarea:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  button.go, button.ghost {
    width: 100%; margin-top: 10px; padding: 13px;
    border: 0; border-radius: 12px; font: inherit; font-weight: 600;
  }
  button.go { background: var(--accent); color: var(--accent-text); }
  button.ghost {
    background: transparent; color: var(--accent);
    border: 1px solid var(--accent);
  }
  button[disabled] { opacity: .5; }
  .verdict {
    margin-top: 16px; padding: 14px; border-radius: 12px;
    background: var(--card); border-left: 4px solid var(--unknown);
  }
  .verdict[data-level="critical"] { border-left-color: var(--crit); }
  .verdict[data-level="high"]     { border-left-color: var(--high); }
  .verdict[data-level="medium"]   { border-left-color: var(--med); }
  .verdict[data-level="low"]      { border-left-color: var(--low); }
  .head { font-weight: 700; margin: 0 0 6px; }
  .target {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: .8rem; color: var(--hint);
    word-break: break-all; margin: 0 0 8px;
  }
  ul { margin: 8px 0 0; padding-left: 18px; }
  li { margin: 2px 0; font-size: .92rem; }
  .caveat { color: var(--hint); font-size: .78rem; margin-top: 12px; }
  .row {
    display: flex; align-items: center; gap: 10px;
    padding: 11px 12px; margin-bottom: 8px;
    background: var(--card); border-radius: 10px;
    border-left: 3px solid var(--unknown);
  }
  .row[data-level="critical"], .row[data-level="high"] { border-left-color: var(--high); }
  .row[data-level="medium"] { border-left-color: var(--med); }
  .row[data-level="low"]    { border-left-color: var(--low); }
  .row .t {
    flex: 1; min-width: 0; font-size: .85rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .row .x { background: none; border: 0; color: var(--hint); font-size: 1.1rem; padding: 0 4px; }
  .empty { color: var(--hint); font-size: .9rem; padding: 18px 2px; }
  .example { color: var(--hint); font-size: .82rem; margin: 10px 2px 0; }
  .boot {
    margin: 0 0 12px; padding: 10px 12px; border-radius: 8px;
    background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.35);
    color: var(--text); font-size: .82rem;
  }
  .build { color: var(--hint); font-size: .7rem; opacity: .7; margin-top: 10px; }
  .linkish {
    background: none; border: 0; padding: 0; font: inherit; font-size: .82rem;
    color: var(--accent); text-decoration: underline; cursor: pointer;
  }
  .watch-intro { color: var(--hint); font-size: .85rem; margin: 4px 2px 10px; }
  input.watch-in {
    width: 100%; padding: 12px;
    background: var(--card); color: var(--text);
    border: 1px solid rgba(148,163,184,.25); border-radius: 12px;
    /* 16px, NOT inherited. iOS Safari zooms the whole page on focus for any
       input under 16px, and a Mini App that jumps when the keyboard opens
       reads as broken. The textarea above carries the same rule. */
    font: inherit; font-size: 16px;
  }
  input.watch-in:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .watch-msg { color: var(--hint); font-size: .82rem; margin: 8px 2px 0; }
  .watch-kinds { margin: 0 0 14px; padding-left: 18px; }
  .watch-kinds li { font-size: .85rem; margin: 6px 0; color: var(--text); }
  .upsell {
    margin-top: 14px; padding: 14px; border-radius: 10px;
    background: var(--card); border: 1px solid rgba(148,163,184,.25);
  }
  .upsell p { margin: 0 0 10px; font-size: .9rem; }
  .upsell button { width: 100%; }
  .quiz-opt {
    display: block; width: 100%; text-align: left; margin-bottom: 8px;
    padding: 14px; border-radius: 10px; font: inherit; font-size: .95rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    background: var(--card); color: var(--text);
    border: 1px solid rgba(148,163,184,.25);
  }
  .quiz-opt[data-state="right"] { border-color: var(--low); }
  .quiz-opt[data-state="wrong"] { border-color: var(--crit); }
  .score { color: var(--hint); font-size: .85rem; }
  /* Two links, stacked. Inline they ran together as one unreadable sentence:
     "Monitor my email, phone and wallets Run this check from your own bot or
     agent". The consumer link is first and carries the weight, because a
     consumer who just checked a scam is the majority arrival here and the
     developer page was the only call to action this app had until 2026-09-10. */
  footer { margin-top: 24px; text-align: center; font-size: .8rem;
           display: flex; flex-direction: column; gap: 10px; }
  footer a { color: var(--accent); text-decoration: none; }
  footer a#botlink { font-weight: 600; }
  footer a#more { color: var(--hint); }
  .inline-footer { color: var(--hint); font-size: .78rem; line-height: 1.45;
                   margin: 0; }
  .inline-footer code { color: var(--fg); background: rgba(255,255,255,.07);
                        border-radius: 4px; padding: 1px 5px;
                        font-size: .78rem; }
  .hidden { display: none; }
  canvas { width: 100%; border-radius: 12px; margin-top: 12px; }
</style>
</head>
<body>
  <h1>RelayShield</h1>
  <p class="sub" id="sub">Check a link or address. No signup, no wallet connect.</p>

  <nav role="tablist">
    <button role="tab" id="tab-check" aria-selected="true">Check</button>
    <button role="tab" id="tab-watch" aria-selected="false">Watching</button>
    <button role="tab" id="tab-learn" aria-selected="false">Spot the fake</button>
  </nav>

  <p id="boot" class="boot" hidden></p>

  <section id="pane-check">
    <textarea id="in" placeholder="Paste a link, a TON address (EQ... / UQ... / 0:...), or your bot&#39;s @handle"
              autocapitalize="off" autocorrect="off" spellcheck="false"></textarea>
    <button class="go" id="go">Check it</button>
    <p class="example">Not sure what to paste?
      <button class="linkish" id="try-bad">Try a link that gets flagged</button></p>
    <!-- THE RECOGNISER WITHOUT THE PROMPT IS A FEATURE NOTHING POINTS AT, and
         that is exactly what shipped on 2026-09-13: BOT_HANDLE matched, the
         developer card rendered correctly, and no developer could ever have
         discovered it because the placeholder said "a link, or a TON address".
         Reported as "What I dont see though is the new copy you were going to
         add to the Check tab to prompt Dev's to paste a link to their bot."

         Same shape as inline mode -- complete, live, and mentioned nowhere --
         which this repo recorded as a lesson two days earlier and I repeated.
         A capability the user cannot find is not shipped. -->
    <p class="example" id="dev-tip">Build a Telegram bot?
      <button class="linkish" id="try-bot">Check what we watch for bot developers</button></p>
    <p class="example" id="inline-tip"></p>

    <div class="verdict hidden" id="out" data-level="unknown">
      <p class="head" id="head"></p>
      <p class="target" id="target"></p>
      <ul id="reasons"></ul>
      <p class="caveat" id="caveat"></p>
      <button class="ghost" id="watch">Tell me if this changes</button>
      <button class="ghost" id="share">Share this result</button>
      <canvas id="card" class="hidden" width="800" height="418"></canvas>
      <p class="cta hidden" id="cta"><span id="cta-line"></span>
        <a id="cta-link" href="__BOT__">Open the monitoring bot</a></p>
    </div>

    <h1 id="hist-h" class="hidden" style="margin-top:22px;font-size:.95rem">Recent checks</h1>
    <div id="hist"></div>
  </section>

  <section id="pane-watch" class="hidden">
    <p class="watch-intro">Watching re-checks a TON address every few hours and
      messages you the moment the answer changes. It covers anything on TON that
      can hold or move your money:</p>
    <ul class="watch-kinds">
      <li><b>Jettons and tokens</b> &mdash; liquidity pulled, price collapsed, or
        newly flagged as a scam.</li>
      <li><b>Wallets</b> &mdash; a balance that was there and is not any more.</li>
      <li><b>Vaults and DeFi contracts</b> &mdash; an address that was not running
        code when you sent to it, and is now.</li>
      <li><b>NFT collections</b> &mdash; the collection address flagged after you
        bought.</li>
    </ul>
    <p class="watch-intro">All of them are accounts on TON, so all of them get the
      same checks: TON&rsquo;s own account data, DEX liquidity, and our indicator
      corpus collected from criminal Telegram channels.</p>

    <p class="watch-intro" id="watch-tiers"><b>__FREE_SLOTS__ addresses free</b>,
      alerted immediately and in full. <b>__SLOTS_STARS__ Stars</b> raises it to
      __PAID_SLOTS__ addresses for __SLOTS_DAYS__ days. Stars buy more slots and
      nothing else: the free alerts are identical.</p>

    <!-- THE PRICE NEEDS SOMETHING TO PRESS. The tier line above named a price
         with no tap target, because the only buy control was rendered from the
         /v1/watchlist/list response beside the slot meter -- so a user whose
         list call had not returned, or had failed, read what we charge and had
         no way to pay it. Buying does not depend on the list: the invoice call
         needs initData and nothing else. -->
    <button class="ghost" id="watch-buy">Get __PAID_SLOTS__ addresses for __SLOTS_STARS__ Stars</button>

    <!-- THE WATCHING TAB HAD NO WAY TO ADD A WATCH, reported in those words.
         The only route was: Check tab, paste, check, then press "Tell me if
         this changes" on the verdict card. So the tab that explains watching,
         names the price and carries the buy button was the one place you could
         not use a slot, and somebody who had just bought 25 of them had
         nowhere to spend them.

         IT STILL RUNS THE CHECK. This is not a second, looser add path: the
         same off-chain gate refuses the same addresses, and the same check()
         call establishes the baseline the monitor diffs against. A watch added
         without one is a row whose first re-check reads as "changed from
         nothing", which is the alert-everybody-at-once failure the monitor's
         first-run rule exists to prevent. -->
    <div class="watch-add">
      <input id="watch-in" class="watch-in" type="text"
             placeholder="Paste a TON address to watch (EQ... / UQ... / 0:...)"
             autocapitalize="off" autocorrect="off" spellcheck="false">
      <button class="ghost" id="watch-add">Watch it</button>
    </div>
    <p class="watch-msg" id="watch-add-msg"></p>

    <div id="watchlist"></div>
    <div id="upsell" class="upsell" hidden></div>
  </section>

  <section id="pane-learn" class="hidden">
    <p class="sub">One of these is a lookalike. The other is real. Which is fake?</p>
    <div id="quiz"></div>
    <p class="score" id="score"></p>
    <button class="ghost" id="next">Next pair</button>
  </section>

  <footer>
    <button class="ghost hidden" id="pin">Add to home screen</button>
    <a id="botlink" href="__BOT__">Monitor my email, phone and wallets</a>
    <a id="more" href="__DEVELOPERS__" target="_blank" rel="noopener">Run this check from your own bot or agent</a>

    <!-- INLINE MODE, NAMED ON EVERY TAB, AND IT IS STATIC MARKUP ON PURPOSE.

         teachInline() already writes INLINE_TEXT into #inline-tip, and that
         line only ever reaches somebody who is already standing in the Check
         tab with nothing pasted. The people who most need to know are the ones
         reading Spot the fake or looking at a watchlist, and the footer is the
         one element on screen from all three.

         STATIC, for the reason the tier line is static: what our own bot can do
         is a fact about our own product and must not depend on a network call,
         on initData, or on switchInlineQuery being available. A user who reads
         this and types the handle by hand gets the full behaviour; the one-tap
         button in the Check tab is a convenience on top of it, not the route.

         The handle sits in a <code> span rather than bold because it is a
         string the reader is being asked to TYPE, and because Telegram
         linkifies a bare @handle in some contexts and not others. -->
    <p class="inline-footer">In any Telegram chat, type
      <code>@relayshield_bot</code> followed by a link or a TON address. The
      verdict posts straight into that conversation, so you can check something
      in the group where it was shared without adding a bot to it or leaving
      the chat.</p>

    <!-- THE WHATSAPP FRONT DOOR, SUBSTITUTED RATHER THAN READ FROM PAGE SCOPE.

         __WA_LINK__ is filled by the Worker at request time and is the EMPTY
         STRING when WA_NUMBER is unset, so this paragraph disappears entirely
         rather than shipping a wa.me/ link with a hole in it. wa.me answers a
         malformed number with a 200 and an "invalid" page, so a broken link
         here would look live to every probe we have.

         Substituted as a __TOKEN__ and not declared in the page for the reason
         INLINE_TEXT was moved: the page and the Worker are different scopes on
         different machines, and anything the page reads from the Worker's own
         scope is a ReferenceError at load that node --check cannot see. -->
    __WA_LINK__

    <p class="build">Build __BUILD__</p>
  </footer>

<script>
/* A CLASSIC script, deliberately, and it must stay above the module.

   THE MINI APP HAS NO CONSOLE. On a phone there is no way to see a JavaScript
   error, so every failure of the code below presents identically: the static
   HTML renders, the buttons do nothing, and the tabs do not switch. That is
   indistinguishable from a CSS problem, a cache problem, or a bug in a handler,
   and on 2026-09-11 it cost a round trip in which the code turned out to parse,
   load and run correctly against every check available in the container.

   A module that fails to parse, fails to IMPORT, or throws on its first line
   never runs its own error handler -- so the watchdog cannot live inside it.
   This script runs regardless, records anything the page throws, and after
   three seconds says so on the page itself if the module never checked in. */
window.__rsErr = "";
window.__rsBoot = false;
window.addEventListener("error", function (e) {
  window.__rsErr = (e && (e.message || String(e.error))) || "script error";
});
window.addEventListener("unhandledrejection", function (e) {
  window.__rsErr = "unhandled rejection: " + (e && e.reason);
});
setTimeout(function () {
  if (window.__rsBoot) return;
  var d = document.getElementById("boot");
  if (!d) return;
  d.hidden = false;
  d.textContent = "This app's code did not start. "
    + (window.__rsErr || "No error was reported, which usually means the script "
       + "was blocked or could not be fetched.")
    + " Build __BUILD__.";
}, 3000);
</script>

<script type="module">
import { check } from "/relayshield-widget.js";
/* The heartbeat the watchdog above waits for. First statement after the import
   on purpose: if the import resolves, this runs, and anything that throws LATER
   is reported by the error listener rather than by the silence. */
window.__rsBoot = true;

const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || "";
/* Plain prose, no parse mode, no formatting: it renders into textContent here
   and is the wording the share card and the bot should use too, so it has to
   survive being copied anywhere.

   DEFINED HERE, INSIDE THE PAGE SCRIPT, AND THAT IS NOT A STYLE CHOICE. The
   first version of this constant sat in the Worker's own scope alongside BOT,
   forty lines up and outside the template literal. Both syntax checks passed
   and the browser would have thrown ReferenceError on load -- the same class as
   the stray backtick, and invisible to a parser for the same reason:
   syntactically valid, runtime dead. Anything the page reads is declared in
   the page. */
const INLINE_TEXT = "In any chat, type @relayshield_bot then paste a link. The "
  + "check posts into that conversation, without anyone leaving it.";
const SOURCE = "__SOURCE__";
// A web_app BUTTON CARRIES NO start_param. Telegram sets initDataUnsafe.start_param
// only for direct links (t.me/<bot>/<app>?startapp=...). When the Mini App is
// launched from an inline web_app button in the bot chat there is no such field,
// so a bot-launched session would have been indistinguishable from a bare
// arrival. The bot passes ?s= on the button URL instead, and it is validated
// against exactly the same allowlist -- an unregistered key is dropped rather
// than forwarded, because a key that logs unmatched: looks like attribution
// and is none.
const urlSource = new URLSearchParams(location.search).get("s") || "";
const raw = startParam || urlSource;
const source = /^[a-z0-9-]{1,40}$/.test(raw) ? raw : SOURCE;
const API = "__API__";
document.getElementById("more").href = "__DEVELOPERS__?source=" + encodeURIComponent(source);

/* The SIGNED string. initDataUnsafe is used only to decide whether to show the
   watchlist UI at all; every request carries initData and the server derives the
   user id from its signature. */
const initData = (tg && tg.initData) || "";
const uid = initData ? true : null;

const HEADS = {
  critical: "Do not proceed",
  high:     "Do not proceed",
  medium:   "Treat with caution",
  low:      "Nothing known against it",
  unknown:  "No match in any source we check",
};

/* "unknown" CARRIES TWO OPPOSITE MEANINGS AND THE PAGE COLLAPSED THEM INTO ONE.
   check() returns level "unknown" both for a target that WAS screened against
   all three sources and matched none of them -- the MOST COMMON outcome for an
   ordinary URL, as the caveat below has said all along -- and for a call that
   never completed. Verdict.ok is the discriminator and the widget uses it;
   this page read only .level, so every clean URL rendered the heading
   "Could not complete the check" directly above body copy naming exactly what
   had been checked. The two halves of one card contradicted each other, on the
   outcome most users see, and the share image carried the same heading out of
   the app into somebody else's chat.

   Same shape as the widget's own split, which is why HEAD_UNCHECKED is a
   separate constant rather than a second table: there is one failure wording
   and it must not be reachable from a completed check. */
/* WHEN THE SERVER SAID WHY, SAY WHY. check() keeps the response body on
   Verdict.raw, and the page threw it away -- so a daily keyless cap, which is
   a limit the reader can act on, rendered identically to an outage, which is
   not. "It failed" is a round trip; "it failed and here is who answered" is a
   fix, and that rule applies to the user's screen exactly as it applies to a
   diagnostic. textContent renders it, so a hostile string is inert. */
function serverReason(v) {
  const raw = v && v.raw;
  const msg = raw && typeof raw.error === "string" ? raw.error.trim() : "";
  return msg && msg.length <= 300 ? msg : "";
}

const HEAD_UNCHECKED = "Could not complete the check";
function headFor(level, ok) {
  return level === "unknown" && !ok ? HEAD_UNCHECKED : HEADS[level];
}

/* THE WIDGET'S 4-SECOND DEFAULT IS CORRECT FOR A BOT AND WRONG FOR THIS SCREEN,
   and until now this page inherited it by calling check() with no timeoutMs.
   Its own docstring says why 4000: "this runs inside a Telegram handler, and a
   bot that stalls is worse than a bot that says it could not check." That is a
   statement about a HANDLER, where a reply arriving late is a reply nobody is
   waiting for. Here a person is looking at a button that says "Checking..."
   and would rather wait eight seconds than be told the check failed.

   IT IS SET HERE RATHER THAN IN widget/relayshield-widget.js, deliberately.
   That file is copied into other people's bots, where 4000 is the right
   number; changing it there would raise the stall ceiling in every one of
   them to fix a screen they do not have.

   AND THE COST OF BEING WRONG IS ASYMMETRIC. A slow answer costs seconds. A
   premature abort renders "Could not complete the check" over a target the
   API was about to return a real verdict for -- and with no body to read, the
   card cannot even say why, so a first-time user is told the product does not
   work. /v1/wallet-risk on a TON address calls TON Center and DexScreener, on
   a Lambda that may be cold, over a phone's network; 4000ms has no headroom
   for the slowest of those and 12000 has plenty. */
const CHECK_TIMEOUT_MS = 12000;

const $ = (id) => document.getElementById(id);
let last = null;

function haptic(level) {
  if (!tg || !tg.HapticFeedback) return;
  const map = { critical: "error", high: "error", medium: "warning", low: "success" };
  if (map[level]) tg.HapticFeedback.notificationOccurred(map[level]);
}

/* ---- Tabs ---------------------------------------------------------- */
const panes = { check: "pane-check", watch: "pane-watch", learn: "pane-learn" };
function show(name) {
  for (const [k, id] of Object.entries(panes)) {
    $(id).classList.toggle("hidden", k !== name);
    $("tab-" + k).setAttribute("aria-selected", String(k === name));
  }
  if (name === "watch") loadWatches();
  if (name === "learn" && !$("quiz").childElementCount) newPair();
}
for (const k of Object.keys(panes)) $("tab-" + k).addEventListener("click", () => show(k));

/* ---- Scan history: LOCAL ONLY -------------------------------------- */
/* Deliberately localStorage and never the server. A server-side record of what
   somebody checked is a profile of their financial anxieties, and the watchlist
   is the one thing that legitimately needs to leave the device. */
const HKEY = "rs.history.v1";
function readHistory() {
  try { return JSON.parse(localStorage.getItem(HKEY) || "[]"); } catch (e) { return []; }
}
function pushHistory(entry) {
  try {
    const h = readHistory().filter((x) => x.target !== entry.target);
    h.unshift(entry);
    localStorage.setItem(HKEY, JSON.stringify(h.slice(0, 20)));
  } catch (e) { /* private mode, or storage disabled. Not worth an error. */ }
  renderHistory();
}
function renderHistory() {
  const h = readHistory();
  $("hist-h").classList.toggle("hidden", h.length === 0);
  const box = $("hist");
  box.textContent = "";
  for (const e of h) {
    const row = document.createElement("div");
    row.className = "row";
    row.dataset.level = e.level;
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = e.target;                 // textContent, never innerHTML
    row.appendChild(t);
    row.addEventListener("click", () => { $("in").value = e.target; show("check"); run(); });
    box.appendChild(row);
  }
}

/* ---- Check --------------------------------------------------------- */
/* ---- TON ONLY, AND THAT IS A HOST RULE RATHER THAN A PRODUCT LIMIT --------
   A Telegram Mini App lives inside Telegram's rules, and TON is the chain
   Telegram ships. Screening Ethereum, Solana or Bitcoin addresses from inside
   one is a fight with the host we have no reason to pick, and the founder's
   instruction is explicit. So this surface checks LINKS and TON, full stop.

   THE RESTRICTION LIVES HERE AND NOT IN widget/relayshield-widget.js, on
   purpose. That file is copied into other people's bots and called from servers
   that are not Telegram at all, where every chain is fine; /v1/wallet-risk
   still answers for EVM, Solana and Bitcoin and nothing about the API changes.
   Putting the gate in the shared file would break every other caller to satisfy
   one host's terms.

   A rejected address is NOT redirected anywhere. Pointing an Ethereum address
   at another one of our surfaces from in here would be the same rule broken one
   link further out, which is exactly how the Stars-to-Stripe trap works.

   UNVERIFIED from the container: core.telegram.org is egress-blocked, so the
   precise clause has not been read here. This implements the founder's
   instruction, which is the conservative direction regardless of what the
   clause turns out to say. */
/* EVERY BACKSLASH IN HERE IS DOUBLED, AND THAT IS NOT STYLE. This code lives
   inside the PAGE template literal, so the Worker evaluates its escapes ONCE
   before the browser ever sees it: a single-backslash \\d arrives as a bare d,
   and a single-backslash \\/ arrives as a bare /.

   The second one is fatal rather than merely wrong. /^(?:https?:\\/\\/ served
   as /^(?:https?:// ENDS THE REGEX LITERAL at the second slash, so the browser
   sees /^(?:https?:/ and throws "Invalid regular expression: missing )" while
   parsing the module -- which means the module never runs, no handler is ever
   registered, and the app renders as static HTML with dead tabs and dead
   buttons. That is exactly what shipped on 2026-09-11.

   Every OTHER regex in this file was already written with doubled backslashes.
   The convention existed; these two lines broke it. */
const TON_ADDR = /^(?:-?\\d+:[0-9a-fA-F]{64}|[A-Za-z0-9_-]{48})$/;
const LOOKS_URL = /^(?:https?:\\/\\/|[a-z0-9-]+(?:\\.[a-z0-9-]+)+)/i;
/* A TELEGRAM BOT HANDLE, WHICH IS A DIFFERENT VISITOR ASKING A DIFFERENT
   QUESTION. Founder, 2026-09-13: "you need to modify the copy on Check screen
   to distinguish bot links from others for devs."

   "@name_bot", "t.me/name_bot" or a bare "name_bot". Telegram requires a bot
   username to end in "bot" (case-insensitive) and to be 5-32 characters, which
   is what makes this recognisable at all without a network call.

   NO BACKTICKS IN THIS COMMENT, AND THAT IS NOT STYLE. Everything here lives
   inside the PAGE template literal, so one backtick ends the template and the
   browser receives a broken module that registers no handlers at all. That has
   shipped a dead app three times; node --check caught this one before it left
   the container.

   IT IS TESTED BEFORE LOOKS_URL, and the order is the whole trick: "t.me/x_bot"
   matches LOOKS_URL, so testing it second would send every bot developer down
   the link-check path and they would get a verdict about t.me. Same ordering
   hazard as TON's 48-char form sitting inside Solana's base58 range, which cost
   this file a silent refusal of every address it exists to check. */
const BOT_HANDLE = /^(?:https?:\\/\\/)?(?:t\\.me\\/|@)?([A-Za-z0-9_]{4,31}[Bb][Oo][Tt])$/;

const OTHER_CHAINS = [
  [/^0x[0-9a-fA-F]{40}$/, "an Ethereum or EVM address"],
  [/^ronin:0x[0-9a-fA-F]{40}$/i, "a Ronin address"],
  [/^(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,87}$/, "a Bitcoin address"],
  [/^[1-9A-HJ-NP-Za-km-z]{32,44}$/, "a Solana address"],
];

/** "", or a plain sentence naming what was pasted and why it is not checked. */
function offChainReason(value) {
  const t = String(value || "").trim();
  if (!t || LOOKS_URL.test(t) || TON_ADDR.test(t)) return "";
  for (const [re, name] of OTHER_CHAINS) {
    // TON's 48-char friendly form and Solana's base58 range overlap, so the TON
    // test above has to win first -- which it does, because it returns early.
    if (re.test(t)) {
      return "That looks like " + name + ". This app checks links and TON "
           + "addresses.";
    }
  }
  return "";
}

async function run() {
  const value = $("in").value.trim();
  if (!value) return;

  /* A BOT HANDLE IS A DEVELOPER, AND THIS BRANCH IS BEFORE THE GATE ON PURPOSE.
     "t.me/x_bot" matches LOOKS_URL, so running the gate first sends every bot
     developer down the link-check path and hands them a verdict about t.me.

     IT ASSERTS NOTHING ABOUT THEIR BOT. We saw a handle and nothing else, and
     the reader arrived from a security check so they are primed to read a
     capability as a finding. That is the outreach rule -- never diagnose a
     prospect from their own front page -- applied to a screen instead of an
     email, and it matters more here.

     ONE ACTION, AND IT IS A LIVE ONE. Token watching is not offered yet: the
     pattern shipped on 2026-09-13 and the corpus has not collected any, so a
     watch button here would either do nothing or answer "nothing known" to
     every visitor forever. A control that does nothing is the defect this file
     has already paid for. The API is real today, so the API is the offer. */
  const bot = BOT_HANDLE.exec(value);
  if (bot) {
    last = null;
    $("out").classList.remove("hidden");
    $("out").dataset.level = "unknown";
    $("head").textContent = "That is a Telegram bot.";
    $("target").textContent = "@" + bot[1];
    $("reasons").textContent = "";
    for (const line of [
      "Your bot token is the whole of its security: anyone holding it reads "
      + "every message sent to your bot and can impersonate it.",
      "It is closer to a session than to a key, so the fix is /revoke in "
      + "BotFather. Rotating anything else does nothing.",
      "RelayShield watches criminal Telegram channels and infostealer dumps "
      + "for leaked credentials, and bot tokens are one of the shapes we look "
      + "for.",
    ]) {
      const li = document.createElement("li");
      li.textContent = line;
      $("reasons").appendChild(li);
    }
    $("caveat").textContent = "We have not looked at your bot. This is what we "
      + "check for, not a finding about you.";
    for (const id of ["watch", "share"]) $(id).classList.add("hidden");
    $("cta").classList.remove("hidden");
    $("cta-line").textContent = "The checks your own bot can call are open, "
      + "keyless and free to start: screen a link a user pastes, or an address "
      + "before your bot sends to it.";
    const link = $("cta-link");
    link.textContent = "Open the developer docs";
    link.href = "__DEVELOPERS__?source=tg-miniapp-bottoken";
    haptic("unknown");
    return;
  }

  const off = offChainReason(value);
  if (off) {
    // Rendered through the ordinary verdict card rather than an alert, so it
    // reads as an answer and not as an error. The stored verdict is cleared
    // too, so nothing off-chain can be watched or shared.
    last = null;
    $("out").classList.remove("hidden");
    $("out").dataset.level = "unknown";
    $("head").textContent = "Not checked here.";
    $("target").textContent = value;
    $("reasons").textContent = "";
    $("caveat").textContent = off;
    for (const id of ["watch", "share", "cta"]) $(id).classList.add("hidden");
    haptic("unknown");
    return;
  }
  for (const id of ["watch", "share"]) $(id).classList.remove("hidden");

  $("go").disabled = true;
  $("go").textContent = "Checking...";
  let v;
  try { v = await check(value, { source, timeoutMs: CHECK_TIMEOUT_MS }); }
  catch (e) { v = { level: "unknown", target: value, reasons: ["The check did not complete."] }; }

  const level = HEADS[v.level] ? v.level : "unknown";
  /* STRICTLY === true. The catch above builds a plain object with no ok field,
     and check() only ever sets ok on a call that came back, so anything other
     than an explicit true is an unchecked target. */
  const ok = v.ok === true;
  last = { target: v.target || value, level, ok, reasons: v.reasons || [] };

  $("out").dataset.level = level;
  $("head").textContent = headFor(level, ok);
  $("target").textContent = last.target;
  const ul = $("reasons");
  ul.textContent = "";
  for (const r of last.reasons) {
    const li = document.createElement("li");
    li.textContent = r;
    ul.appendChild(li);
  }
  $("caveat").textContent =
    level === "low"
      ? "This means nothing known against it, which is not the same as safe."
      : level === "unknown"
        ? (ok
            ? "Checked against our criminal-channel indicator corpus, Google Safe Browsing and domain age. None of them knows this one. That is an absence of evidence, not proof it is safe."
            : serverReason(v)
              ? "The check did not complete: " + serverReason(v) + " Treat this as unchecked, not as safe."
              : "The check did not complete, so this was not screened at all. Treat it as unchecked, not as safe, and try it again in a moment.")
        : "Based on indicators seen in criminal channels and public feeds.";

  // The offer is made AFTER a result, because that is when it is relevant, and
  // the wording follows the finding. Pitching monitoring to somebody who has
  // just been told "nothing known against it" in the same words used for a
  // confirmed scam is how a real product starts reading as an advert.
  // COPY CORRECTED 2026-09-10 after Andrew asked "what credential do we use to
  // derive verdict from a breached account?" -- the honest answer is NONE. The
  // first draft said "attacks like this start from a breached account", which
  // asserts a causal story this check never established. A link check reads a
  // URL against three sources and knows nothing whatever about the reader.
  // Claiming otherwise in a product that refuses to say "safe" on an absence of
  // evidence is the same failure pointed the other way.
  //
  // "unknown" gets its OWN line and it is the most important one, because it is
  // the MOST COMMON outcome. _link_check_level returns "unknown" for anything
  // not in the IOC corpus, not on Safe Browsing and older than 30 days, which
  // is every ordinary URL. Rendering that as a dead end is what makes the app
  // feel like it failed; naming what was checked turns it into an answer.
  $("cta-line").textContent =
    level === "critical" || level === "high"
      ? "Flagged. If a link like this reached you, it is worth knowing whether your own email or phone is already exposed."
      : level === "unknown" && ok
        ? "Not in any source we check. That is not the same as safe, and it says nothing about you. Checking your own email is a separate question with a definite answer."
        : level === "unknown"
          ? "Nothing was established either way here. Whether your own email or phone is already exposed is a separate question, and that one has a definite answer."
          : "RelayShield can watch your email, phone and wallets for breaches, SIM swaps and stolen sessions.";
  /* RESTORE THE CTA LINK. The bot-handle branch above repoints it at the
     developer docs, and without this the NEXT check -- an ordinary URL, by an
     ordinary user -- would still offer them developer documentation. A shared
     element that one branch mutates and another does not reset is a state bug
     that only appears on the second use, which is exactly the kind nobody
     tests by hand. */
  const ctaLink = $("cta-link");
  ctaLink.textContent = "Open the monitoring bot";
  ctaLink.href = "__BOT__";
  $("cta").classList.remove("hidden");

  $("card").classList.add("hidden");
  $("watch").textContent = "Tell me if this changes";
  $("watch").disabled = false;
  $("out").classList.remove("hidden");
  haptic(level);
  pushHistory({ target: last.target, level });
  $("go").disabled = false;
  $("go").textContent = "Check it";
}
// A BARE t.me ANCHOR INSIDE A MINI APP OPENS A BROWSER, NOT THE CHAT. Telegram
// runs this page in a webview, so an ordinary link navigates the webview or
// hands the URL to the system browser, and the user lands on a t.me web page
// asking them to open Telegram -- from inside Telegram. openTelegramLink is the
// documented route: it closes the Mini App and opens the bot chat directly.
//
// The href stays real so the link still works if the SDK is missing, which is
// also how it behaves when the page is opened in an ordinary browser.
for (const id of ["cta-link", "botlink"]) {
  const el = $(id);
  if (!el) continue;
  el.addEventListener("click", (e) => {
    /* CHECK THE HREF, NOT THE ELEMENT ID. openTelegramLink is documented for
       t.me links; handing it an api.relayshield.net URL is undefined and the
       likely result is a tap that does nothing -- and cta-link now carries a
       developer-docs URL on the bot-handle branch. openLink is the documented
       method for an external URL, and is feature-detected because this page
       loads the unversioned SDK and an older client may not have it. */
    const isTelegram = /^https?:\/\/t\.me\//i.test(el.href);
    if (!tg) return;
    if (isTelegram && typeof tg.openTelegramLink === "function") {
      e.preventDefault();
      tg.openTelegramLink(el.href);
    } else if (!isTelegram && typeof tg.openLink === "function") {
      e.preventDefault();
      tg.openLink(el.href);
    }
    // Otherwise the anchor navigates normally, which is correct in a browser
    // and correct in a client whose SDK lacks the method.
  });
}

/* ---- Getting back in ------------------------------------------------
 * A DIRECT-LINK MINI APP LEAVES NO WAY BACK, and the founder hit this on
 * 2026-09-10: t.me/<bot>/<app> opens the app WITHOUT creating a bot chat, so
 * there is nothing in the chat list to pin and nothing in Telegram's Apps tab
 * for a brand-new app nobody has used. He could not find his own Mini App.
 *
 * That is the retention hole underneath everything in miniapp_stickiness_plan.md:
 * the watchlist, the history and the digest all assume the user can RETURN, and
 * an arrival from an announcement channel had no route to.
 *
 * Two routes now exist. The bot CTA creates a real chat (?start= triggers the
 * bot's welcome), which is pinnable. And this puts an icon on the device home
 * screen, which is Telegram's own answer to exactly this.
 *
 * FEATURE-DETECTED AND SILENT WHEN ABSENT. addToHomeScreen and
 * checkHomeScreenStatus arrived in a later Bot API than some installed clients
 * run, and this page loads the unversioned SDK, so the method may simply not be
 * there. A button that does nothing is worse than no button, so it stays hidden
 * unless the method exists AND the app is not already installed.
 */
if (tg && typeof tg.addToHomeScreen === "function") {
  const showPin = () => {
    $("pin").classList.remove("hidden");
    $("pin").addEventListener("click", () => {
      try { tg.addToHomeScreen(); } catch (e) { /* client refused; nothing to do */ }
    });
  };
  if (typeof tg.checkHomeScreenStatus === "function") {
    try {
      // 'added' means it is already on the home screen, so offering again is
      // noise. Anything else -- including 'unknown' -- is worth offering, since
      // the cost of a redundant prompt is far lower than no route back at all.
      tg.checkHomeScreenStatus((status) => { if (status !== "added") showPin(); });
    } catch (e) { showPin(); }
  } else {
    showPin();
  }
}

/* ---- The example ---------------------------------------------------------
   An empty box asking for input is the worst possible first screen for this
   product: the most common honest answer is "nothing known", so a first-time
   user who pastes something clean learns nothing about what the app is for.

   THE EXAMPLE IS A REAL CHECK, NOT A CANNED CARD. It fills the box and runs the
   same code path a user runs, so whatever comes back is true at the moment they
   press it. A screenshot of a verdict we rendered ourselves would be a claim
   about our own product that nobody could check, and it would go stale silently
   the first time the underlying answer changed.

   AND THE URL IS ONE THAT IS FLAGGED BY CONSTRUCTION RATHER THAN BY OUR SAY-SO.
   testsafebrowsing.appspot.com is GOOGLE'S OWN test host, published so that
   anyone integrating Safe Browsing can prove their integration fires. Our
   /v1/link-check consults Safe Browsing, so this is a genuine detection rather
   than a demo mode -- and it is not a real criminal's domain, which matters
   because the alternative is shipping a live malicious link inside our own app
   and inviting people to tap it.

   UNVERIFIED from the container: api.relayshield.net and Google are both
   egress-blocked here, so this has not been run end to end from this machine.
   That is exactly why it is wired as a live check with an honest failure path
   rather than as a promise -- if Safe Browsing ever stops flagging it, the user
   sees a real "nothing known" verdict and the app is still telling the truth,
   instead of a broken screenshot. One command settles it on the Mac:
     curl -sS -X POST https://api.relayshield.net/v1/link-check
       -H 'content-type: application/json'
       -d '{"url":"http://testsafebrowsing.appspot.com/s/malware.html"}'
   (one line, joined -- a trailing backslash here is a template-literal line
   continuation and would silently weld these three lines together) */
/* ---- Teach inline mode, which is the only surface that reaches the moment of
   need ----------------------------------------------------------------------
   The honest problem with a checker is that nobody opens one. The scam arrives
   in a group chat while you are thinking about something else, and an app you
   have to remember, find and open has already lost.

   @relayshield_bot has had INLINE MODE the whole time: type the bot's username
   then a link, in ANY chat, and the verdict posts into that conversation.
   handle_inline_query is built, rate-limited and live. NOTHING TELLS ANYONE IT
   EXISTS -- not the Mini App, not the share card, not the bot's own welcome.
   That is a finished feature with no route to it, which is the same shape as
   the watchlist that could not alert.

   switchInlineQuery is the one-tap version, and it is FEATURE-DETECTED rather
   than assumed: Telegram documents it as available only to Mini Apps launched
   from a keyboard or inline button, and ours is launched from a direct link, so
   it may simply be absent here. UNVERIFIED from the container --
   core.telegram.org is egress-blocked. The text fallback is therefore the path
   that must work, and it is written to be useful on its own rather than as an
   apology for a missing button. */
const EXAMPLE_URL = "http://testsafebrowsing.appspot.com/s/malware.html";

(function teachInline() {
  const tip = $("inline-tip");
  if (!tip) return;
  const canSwitch = tg && typeof tg.switchInlineQuery === "function";
  if (canSwitch) {
    tip.textContent = "Checking something in a group chat? ";
    const b = document.createElement("button");
    b.className = "linkish";
    b.textContent = "Check it without leaving the chat";
    b.addEventListener("click", () => {
      try {
        tg.switchInlineQuery(last && last.target ? last.target : "",
                             ["users", "groups"]);
      } catch (e) {
        // Documented as restricted by launch type, so a throw here is expected
        // rather than exceptional. Degrade to the instruction, never to nothing.
        tip.textContent = INLINE_TEXT;
      }
    });
    tip.appendChild(b);
  } else {
    tip.textContent = INLINE_TEXT;
  }
})();

$("try-bad").addEventListener("click", () => {
  $("in").value = EXAMPLE_URL;
  run();
});

/* OUR OWN BOT, DELIBERATELY, AND IT IS THE SAME REASONING AS THE FLAGGED-LINK
   EXAMPLE. Prefilling a stranger's bot handle would be pointing our own app at
   somebody else's product and rendering a card about it, which is the thing the
   outreach rules forbid in an email and is worse on a screen. @relayshield_bot
   is ours, so the card it produces is a claim about us and nobody else.

   It runs the REAL path, not a canned card: whatever the developer branch says
   is true at the moment they press it. */
$("try-bot").addEventListener("click", () => {
  $("in").value = "@relayshield_bot";
  run();
});

$("go").addEventListener("click", run);
$("in").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
});

/* ---- Watchlist ----------------------------------------------------- */
async function post(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

/* ONE ADD PATH, USED BY BOTH CONTROLS. The verdict card's button and the
   Watching tab's own box call this, so the slots-full upsell, the wording and
   the error handling cannot drift between them -- which is what two copies of
   this block would have done by the second change to either. */
async function addWatch(target, level) {
  try {
    const res = await post("/v1/watchlist/add", {
      init_data: initData, target: target, level: level,
    });
    if (res && res.ok) {
      return { ok: true, text: isTon(target)
        ? "Watching. We will message you the moment it changes."
        : "Saved. Live re-checks cover TON addresses and tokens today." };
    }
    if (res && res.error === "slots_full") {
      offerUpgrade(res.data || {});
      return { ok: false, text: "Free slots are full." };
    }
    return { ok: false, text: (res && res.error) || "Could not save that." };
  } catch (e) {
    return { ok: false, text: "Could not save that." };
  }
}

$("watch").addEventListener("click", async () => {
  if (!last) return;
  if (!uid) {
    $("watch").textContent = "Open this inside Telegram to watch";
    return;
  }
  $("watch").disabled = true;
  $("watch").textContent = "Saving...";
  const r = await addWatch(last.target, last.level);
  $("watch").textContent = r.text;
  if (!r.ok) $("watch").disabled = false;
});

/* The Watching tab's own add box. Same gate, same check, same add. */
const watchAddBtn = $("watch-add");
if (watchAddBtn) {
  const say = (t) => { const el = $("watch-add-msg"); if (el) el.textContent = t; };
  const doAdd = async () => {
    const value = ($("watch-in").value || "").trim();
    if (!value) return;
    if (!uid) {
      say("Open this from Telegram to keep a watchlist.");
      return;
    }
    /* THE SAME REFUSAL AS THE CHECK TAB, and it has to be here rather than
       left to the server: watching an EVM or Solana address would write a row
       the TON monitor will never re-check, which is a promise nothing keeps --
       the exact defect the monitor was built to end, re-created one screen
       earlier. */
    const off = offChainReason(value);
    if (off) { say(off); return; }
    watchAddBtn.disabled = true;
    const was = watchAddBtn.textContent;
    watchAddBtn.textContent = "Checking...";
    say("");
    let v;
    try { v = await check(value, { source, timeoutMs: CHECK_TIMEOUT_MS }); }
    catch (e) { v = null; }
    if (!v) {
      say("Could not check that just now, so it has not been watched. "
        + "Nothing has been saved.");
      watchAddBtn.disabled = false;
      watchAddBtn.textContent = was;
      return;
    }
    watchAddBtn.textContent = "Saving...";
    const level = HEADS[v.level] ? v.level : "unknown";
    const r = await addWatch(v.target || value, level);
    say(r.text);
    watchAddBtn.disabled = false;
    watchAddBtn.textContent = was;
    if (r.ok) { $("watch-in").value = ""; loadWatches(); }
  };
  watchAddBtn.addEventListener("click", doAdd);
  $("watch-in").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); doAdd(); }
  });
}

/* Mirrors _is_valid_ton_address in relayshield_api.py and _normalise in
   relayshield_watchlist.py. Three copies is one too many, and this one earns
   its place: it decides the wording of a sentence, never a verdict, so a
   disagreement here is cosmetic where a disagreement there would be wrong. */
function isTon(v) {
  const t = String(v || "").trim();
  return /^-?\d+:[0-9a-fA-F]{64}$/.test(t) || /^[A-Za-z0-9_-]{48}$/.test(t);
}

/* ---- Stars ----------------------------------------------------------
   Stars are the ONLY compliant way to charge a consumer inside a Mini App:
   Telegram requires digital goods to be paid in Stars to satisfy Apple's and
   Google's IAP rules. Linking out to Stripe, x402 or the developers page for a
   digital good is the route that gets a bot restricted, and all three exist one
   link away, so the temptation is real and the answer is no.

   WHAT IS SOLD IS SLOTS, NOT CHECKS AND NOT ALERTS. Checking stays free and
   unlimited. An alert is never held back for payment: charging at the moment
   somebody's money is moving would make the free tier's promise a lie. */
function offerUpgrade(d) {
  const box = $("upsell");
  if (!box) return;
  box.textContent = "";
  const p = document.createElement("p");
  p.textContent = d.message || "Free watch slots are full.";
  const b = document.createElement("button");
  b.className = "primary";
  b.textContent = "\u2B50 " + (d.upgrade_stars || 50) + " Stars \u2014 "
    + (d.upgrade_slots || 25) + " slots for " + (d.upgrade_days || 90) + " days";
  b.addEventListener("click", () => buySlots(b));
  box.appendChild(p);
  box.appendChild(b);
  box.hidden = false;
}

async function buySlots(btn) {
  if (!tg || !tg.openInvoice) {
    btn.textContent = "Update Telegram to buy with Stars";
    return;
  }
  btn.disabled = true;
  const was = btn.textContent;
  btn.textContent = "Opening...";
  let res;
  try { res = await post("/v1/watchlist/invoice", { init_data: initData }); }
  catch (e) { res = null; }
  if (!res || !res.ok || !res.data || !res.data.invoice_link) {
    /* TWO DIFFERENT FAILURES USED TO READ THE SAME ON SCREEN. Our handler's
       own message is "could not start the purchase, try again"; this fallback
       said "Could not start the purchase." So a Telegram refusal and a request
       that never arrived were one capital letter apart, and the screen could
       not tell you which side to look at. Name the side. */
    btn.textContent = (res && res.error)
      || "Could not reach RelayShield to start the purchase.";
    btn.disabled = false;
    return;
  }
  /* The status callback is the ONLY place the result is known. Telegram does
     not resolve a promise here and the payment completes on ITS side, so the
     entitlement is credited by the bot webhook's successful_payment handler,
     never by this button. All this does is refresh what we display. */
  tg.openInvoice(res.data.invoice_link, (status) => {
    btn.disabled = false;
    btn.textContent = was;
    if (status === "paid") {
      $("upsell").hidden = true;
      loadWatches();
    } else if (status === "failed") {
      btn.textContent = "That did not go through.";
    }
  });
}

/* Filled in by loadWatches when the real numbers arrive. Empty means the static
   fallbacks inside offerUpgrade are used, which is why they exist there. */
const liveTiers = {};

/* Wired at module load, NOT inside loadWatches, and that is the point: the buy
   path must not depend on a call that can fail. Telegram's invoice needs the
   signed initData and nothing else, so the only thing the list response adds
   here is better numbers, and those already have static fallbacks. */
const buyBtn = $("watch-buy");
if (buyBtn) {
  buyBtn.addEventListener("click", () => offerUpgrade({
    message: "Watch up to " + (liveTiers.slots || __PAID_SLOTS__) + " TON "
           + "addresses for " + (liveTiers.days || __SLOTS_DAYS__) + " days. "
           + "Your free slots keep working exactly as they do now.",
    upgrade_stars: liveTiers.stars, upgrade_slots: liveTiers.slots,
    upgrade_days: liveTiers.days,
  }));
}

async function loadWatches() {
  const box = $("watchlist");
  if (!uid) {
    box.textContent = "";
    const p = document.createElement("p");
    p.className = "empty";
    /* Name the CAUSE. "Open this inside Telegram" and "we could not reach the
       server" are different problems with different fixes, and until today
       both of them, plus an empty list, rendered as the same nothing. */
    p.textContent = "Open this from Telegram to keep a watchlist \u2014 a watch "
      + "is tied to your Telegram account, so we cannot load one here.";
    box.appendChild(p);
    return;
  }
  box.textContent = "";
  const loading = document.createElement("p");
  loading.className = "empty";
  loading.textContent = "Loading...";
  box.appendChild(loading);

  let res;
  try { res = await post("/v1/watchlist/list", { init_data: initData }); }
  catch (e) { res = null; }
  box.textContent = "";

  /* A FAILED LIST IS NOT AN EMPTY LIST, and it used to render as one. Both
     collapsed to data = {}, which printed "Nothing watched yet" over a
     watchlist that might be full -- and which took every slot and price line
     down with it, because all of that copy was built from this response. */
  if (!res || !res.ok) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = res && res.error
      ? "Could not load your watchlist: " + res.error
      : "Could not reach the watchlist just now. Nothing has been lost \u2014 "
        + "pull the app closed and open it again.";
    box.appendChild(p);
    return;
  }

  const data = res.data || {};
  const items = data.watches || [];

  /* The static tier line is the fallback, not the truth. Once the real numbers
     are in, say them, and drop the upsell entirely for somebody who has
     already paid: continuing to sell a tier to its own buyer is the fastest
     way to make a paid product feel like an advertisement. */
  const tiersLine = $("watch-tiers");
  if (data.upgrade_stars) {
    liveTiers.stars = data.upgrade_stars;
    liveTiers.slots = data.upgrade_slots;
    liveTiers.days = data.upgrade_days;
  }
  if (buyBtn) buyBtn.hidden = Boolean(data.slots_expire_at);
  if (tiersLine && data.limit) {
    if (data.slots_expire_at) {
      tiersLine.textContent = data.limit + " watch slots, alerted immediately "
        + "and in full, until "
        + new Date(data.slots_expire_at * 1000).toISOString().slice(0, 10) + ".";
    } else {
      tiersLine.textContent = data.limit + " addresses free, alerted "
        + "immediately and in full. " + data.upgrade_stars + " Stars raises it "
        + "to " + data.upgrade_slots + " addresses for " + data.upgrade_days
        + " days. Stars buy more slots and nothing else: the free alerts are "
        + "identical.";
    }
  }

  if (data.limit) {
    const meter = document.createElement("p");
    meter.className = "empty";
    const until = data.slots_expire_at
      ? " \u00b7 until " + new Date(data.slots_expire_at * 1000).toISOString().slice(0, 10)
      : "";
    meter.textContent = data.used + " of " + data.limit + " slots used" + until;

    /* THE UPGRADE IS VISIBLE AT EVERY SLOT COUNT, NOT ONLY NEAR THE WALL.
       The previous condition was 'used >= limit - 1' with a comment above it
       claiming the offer came BEFORE the slots were full. The comment and the
       code disagreed: two of three IS nearly the wall, and a user with zero or
       one watch never learned the paid tier existed at all.

       That is the same defect as inline mode in a new place -- a capability
       that is built, live, and pointed at by nothing. A paid tier nobody can
       see is a paid tier nobody buys, and the people watching addresses their
       money is actually in are exactly the ones for whom this is worth buying.

       QUIET AT LOW COUNTS, PROMINENT AT THE WALL. An inline link next to the
       meter is information; a card that dominates the screen before somebody
       has watched anything is an advertisement, and it converts worse because
       they have not felt the value yet. The big card still fires when the
       slots are actually full, from add_watch's slots_full branch. */
    if (!data.slots_expire_at) {
      meter.appendChild(document.createTextNode(" \u00b7 "));
      const more = document.createElement("button");
      more.className = "linkish";
      more.textContent = data.upgrade_stars + " Stars for " + data.upgrade_slots;
      more.addEventListener("click", () => offerUpgrade({
        message: "Watch up to " + data.upgrade_slots + " TON addresses for "
               + data.upgrade_days + " days. Your free slots keep working "
               + "exactly as they do now.",
        upgrade_stars: data.upgrade_stars, upgrade_slots: data.upgrade_slots,
        upgrade_days: data.upgrade_days,
      }));
      meter.appendChild(more);
    }
    box.appendChild(meter);
  }

  if (!items.length) {
    /* The empty state has to sell WATCHING, not apologise for being empty.
       It used to say "Nothing watched yet" and return, so the tab that carries
       the only paid product in the app said nothing about what it does or what
       it costs to anyone who had not already used it. */
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Nothing watched yet. Check a TON address or a link, then "
      + "tap \u201cTell me if this changes\u201d and we will message you here "
      + "the moment it does.";
    box.appendChild(p);
    /* The tier line is no longer rendered here. It is STATIC markup above the
       list (#watch-tiers), so it is on screen before this call is made and
       survives the call failing -- which is the whole reason the pricing was
       invisible. What we charge NEVER implies the paid alerts are better,
       faster or more complete: they are identical, and the only thing Stars
       buy is more slots, because a slot is the only thing with a marginal
       cost -- a recurring TON Center call, a DexScreener call and a corpus
       query, forever. */
    return;
  }
  for (const w of items) {
    const row = document.createElement("div");
    row.className = "row";
    row.dataset.level = w.last_level || "unknown";
    const t = document.createElement("span");
    t.className = "t";
    /* An honest label, because the alternative is a promise we do not keep.
       The monitor re-checks TON and only TON, so a domain or an EVM address in
       this list is stored and not watched. Showing them identically would be
       the quiet-alarm shape with a user on the end of it. */
    t.textContent = w.monitored ? w.target : w.target + "  \u00b7 not re-checked yet";
    const x = document.createElement("button");
    x.className = "x";
    x.textContent = "\u00d7";
    x.setAttribute("aria-label", "Stop watching");
    x.addEventListener("click", async () => {
      x.disabled = true;
      await post("/v1/watchlist/remove", { init_data: initData, watch_id: w.watch_id });
      loadWatches();
    });
    row.appendChild(t);
    row.appendChild(x);
    box.appendChild(row);
  }
}

/* ---- Share card ---------------------------------------------------- */
/* The growth loop: someone posts a scam link in a group, one member checks it,
   and forwards a card. Telegram's native surface is forwarding, and a security
   verdict is one of the few things people genuinely forward.
   It NEVER renders "safe" -- a forwarded false reassurance is the worst
   artefact this product could produce. */
$("share").addEventListener("click", () => {
  if (!last) return;
  const c = $("card");
  const g = c.getContext("2d");
  const colours = { critical: "#ef4444", high: "#f97316", medium: "#eab308",
                    low: "#22c55e", unknown: "#94a3b8" };
  g.fillStyle = "#0f172a"; g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = colours[last.level] || "#94a3b8"; g.fillRect(0, 0, 12, c.height);
  g.fillStyle = "#f8fafc";
  g.font = "bold 44px -apple-system, system-ui, sans-serif";
  g.fillText(headFor(last.level, last.ok), 48, 96);
  g.fillStyle = "#94a3b8";
  g.font = "24px ui-monospace, Menlo, monospace";
  const shown = last.target.length > 46 ? last.target.slice(0, 45) + "\u2026" : last.target;
  g.fillText(shown, 48, 148);
  g.fillStyle = "#cbd5e1";
  g.font = "22px -apple-system, system-ui, sans-serif";
  let y = 208;
  for (const r of last.reasons.slice(0, 3)) {
    g.fillText("\u2022 " + (r.length > 52 ? r.slice(0, 51) + "\u2026" : r), 48, y);
    y += 34;
  }
  /* TWO FOOTER LINES, AND THE SECOND ONE IS THE COMPOUNDING HALF.
     A forwarded verdict lands in front of somebody who is, right then, in the
     conversation where the scam was posted. The old single line named the bot
     and left them to work out what to do with it, which means opening a new
     chat, finding the app and pasting -- three steps away from the moment they
     are actually in. Naming the inline mechanic turns a card that advertises
     us into a card that teaches the reader to do the check themselves, in the
     chat they are already looking at.

     Kept to one short sentence because it is rendered into a fixed-width
     canvas at 20px and there is no wrapping: a longer line silently runs off
     the edge of the image, which is the kind of defect that only shows up in a
     screenshot somebody already forwarded. */
  g.fillStyle = "#64748b";
  g.font = "20px -apple-system, system-ui, sans-serif";
  g.fillText("Check one yourself: type @relayshield_bot in any chat", 48, 362);
  g.fillText("Checked with RelayShield \u00b7 t.me/relayshield_bot", 48, 392);
  c.classList.remove("hidden");
  $("share").textContent = "Press and hold the image to forward it";
});

/* ---- Spot the fake ------------------------------------------------- */
/* The one game that earns its place: the skill it teaches IS the product's
   skill. Points, streaks and leaderboards were rejected because they move DAU
   by attracting people who want points, and that audience does not buy a
   security subscription. Getting better at spotting a homoglyph makes the user
   safer, which is the test every idea here had to pass. */
const REAL = ["binance.com", "metamask.io", "ledger.com", "uniswap.org", "coinbase.com",
              "trustwallet.com", "phantom.app", "opensea.io", "tonkeeper.com", "kraken.com"];
function fakeOf(d) {
  const tricks = [
    (s) => s.replace("l", "1"), (s) => s.replace("o", "0"),
    (s) => s.replace("i", "l"), (s) => s.replace("m", "rn"),
    (s) => s.replace(".", "-") + ".com", (s) => s.split(".")[0] + "-wallet." + s.split(".")[1],
  ];
  for (let i = 0; i < 12; i++) {
    const f = tricks[Math.floor(Math.random() * tricks.length)](d);
    if (f !== d) return f;
  }
  return d.split(".")[0] + "-app." + d.split(".").slice(1).join(".");
}
let right = 0, asked = 0;
function newPair() {
  const real = REAL[Math.floor(Math.random() * REAL.length)];
  const fake = fakeOf(real);
  const opts = Math.random() < 0.5 ? [fake, real] : [real, fake];
  const box = $("quiz");
  box.textContent = "";
  for (const o of opts) {
    const b = document.createElement("button");
    b.className = "quiz-opt";
    b.textContent = o;
    b.addEventListener("click", () => {
      if (box.dataset.done) return;
      box.dataset.done = "1";
      asked += 1;
      const correct = o === fake;
      if (correct) right += 1;
      for (const child of box.children) {
        child.dataset.state = child.textContent === fake ? "right" : "wrong";
      }
      $("score").textContent = correct
        ? \`Right. "\${fake}" is the lookalike. \${right}/\${asked}\`
        : \`Not this time. "\${fake}" was the lookalike. \${right}/\${asked}\`;
      haptic(correct ? "low" : "medium");
    });
    box.appendChild(b);
  }
  delete box.dataset.done;
}
$("next").addEventListener("click", newPair);

renderHistory();
</script>
</body>
</html>`;

/* A SHORT, VISIBLE BUILD ID, AND IT ANSWERS A QUESTION THAT KEEPS COSTING ROUNDS.
   "I cannot see your changes" has three causes that look identical from a phone:
   the deploy did not run, Telegram served a cached page, or the change is live
   and something else is wrong. Nothing on the page could tell them apart, so
   every report started with a round trip to establish which one it was.

   Computed from the page AND the embedded widget, so it moves whenever either
   does. FNV-1a rather than crypto: this is a cache-buster and a version label,
   not a checksum anyone is defending, and it must be cheap enough to run once
   at Worker load with no async. */
/* LAZY, AND THAT IS NOT AN OPTIMISATION. The first version of this was an IIFE
   that ran at module load and read WIDGET_JS, which is declared FIFTY LINES
   FURTHER DOWN -- `const` is not initialised until its own line is reached, so
   that is a temporal-dead-zone ReferenceError at Worker startup and every
   request 500s. `node --check` passes it: the syntax is perfect.

   Third instance of one family in two days. A stray backtick, a constant in the
   wrong SCOPE, and now a constant in the wrong ORDER -- all syntactically
   valid, all runtime dead, none visible to a parser. The guard for the whole
   family is to EXECUTE the module, which test_miniapp_routes.py now does. */
let _build = "";
function buildId() {
  if (_build) return _build;
  let h = 0x811c9dc5;
  const src = PAGE + WIDGET_JS;
  for (let i = 0; i < src.length; i++) {
    h ^= src.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  _build = h.toString(16).padStart(8, "0");
  return _build;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // The widget module, served so the page can import it. ONE copy in the repo.
    if (url.pathname === "/relayshield-widget.js") {
      return new Response(WIDGET_JS, {
        headers: {
          "content-type": "application/javascript; charset=utf-8",
          "cache-control": "public, max-age=300",
        },
      });
    }

    if (url.pathname === "/health") {
      return new Response("ok", { headers: { "content-type": "text/plain" } });
    }

    const source = sourceFor(url.searchParams.get("startapp") || "");
    const body = PAGE
      .replaceAll("__DEVELOPERS__", DEVELOPERS)
      .replaceAll("__BOT__", BOT)
      .replaceAll("__API__", API_BASE)
      .replaceAll("__BUILD__", buildId())
      .replaceAll("__FREE_SLOTS__", FREE_SLOTS)
      .replaceAll("__PAID_SLOTS__", PAID_SLOTS)
      .replaceAll("__SLOTS_STARS__", SLOTS_STARS)
      .replaceAll("__SLOTS_DAYS__", SLOTS_DAYS)
      .replaceAll("__SOURCE__", source)
      .replaceAll("__WA_LINK__", waLink());

    return new Response(body, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        // Telegram renders the Mini App in an iframe, so a DENY here would
        // show a blank app. Restrict to Telegram's own origins instead.
        "content-security-policy":
          "default-src 'self'; " +
          "script-src 'self' 'unsafe-inline' https://telegram.org; " +
          "style-src 'self' 'unsafe-inline'; " +
          "connect-src https://api.relayshield.net; " +
          "frame-ancestors https://web.telegram.org https://telegram.org;",
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "cache-control": "public, max-age=60",
      },
    });
  },
};

// Injected at build time by tools/build_miniapp.py from widget/relayshield-widget.js.
// Do not edit below this line.
const WIDGET_JS = "/**\n * RelayShield check for Telegram bots. One function, no dependencies.\n *\n *   import { check } from \"./relayshield-widget.js\";\n *\n *   bot.on(\"message:text\", async (ctx) => {\n *     const v = await check(ctx.message.text);\n *     if (v.blocked) await ctx.reply(v.text, { parse_mode: \"Markdown\" });\n *   });\n *\n * Works with grammY, Telegraf, node-telegram-bot-api or a raw webhook: it is a\n * plain async function over global fetch, not a framework integration.\n * Node 18+ (fetch and AbortSignal.timeout are built in).\n *\n * This is a direct port of widget/relayshield_widget.py and the two files must\n * stay in step. The rules they are both built around:\n *\n *   1. IT NEVER THROWS. A bot that crashes because our API had a bad minute\n *      gets uninstalled that week. Every failure path resolves to a verdict\n *      with level \"unknown\" and a message saying the check did not complete.\n *\n *   2. IT NEVER SAYS \"SAFE\". The link check is an absence of evidence across\n *      three sources, not proof of safety. The ceiling on a clean URL is\n *      \"nothing known against it\".\n *\n * Telegram's legacy \"Markdown\" parse mode HAS NO ESCAPE SYNTAX, so an\n * underscore in a URL can make Telegram reject the whole message with a 400 and\n * your verdict never arrives. Attacker-controlled values therefore go inside a\n * code span, which legacy Markdown treats as literal. Use .html with\n * parse_mode \"HTML\" if you prefer.\n *\n * Both endpoints are KEYLESS: no signup, no key, no card for the first call,\n * with a per-IP daily cap rather than a bill. Pass apiKey once you have one:\n * https://api.relayshield.net/developers?source=tg-widget\n */\n\nexport const API_BASE = \"https://api.relayshield.net\";\nexport const SOURCE = \"tg-widget\";\nconst UPSELL = \"https://api.relayshield.net/developers?source=tg-widget\";\n\n// Mirrors _detect_chain_api in relayshield_api.py. Duplicated deliberately:\n// this file is copied into other people's repositories. The server detects the\n// chain again, so a disagreement costs one rejected call, never a wrong verdict.\nconst EVM = /^0x[0-9a-fA-F]{40}$/;\nconst TON = /^[EUeu][Qq][A-Za-z0-9_-]{46}$/;\nconst BTC = /^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$/;\nconst SOL = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;\n\n// ronin:0x\u2026 is how Ronin addresses are written, and every wallet regex rejects\n// them. Stripping the prefix turns a rejected message into a checked one.\nconst RONIN = /^ronin:(0x[0-9a-fA-F]{40})$/i;\n\nconst BARE_DOMAIN = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,24}(?:[/?#].*)?$/i;\n\nconst HIGH = new Set([\"high\", \"critical\"]);\nconst LEVELS = new Set([\"critical\", \"high\", \"medium\", \"low\", \"unknown\"]);\n\n/** Legacy Markdown has no escapes, so the only defence inside a code span is\n *  removing the one character that can close it. */\nfunction codeSafe(value) {\n  return String(value).split(\"`\").join(\"\");\n}\n\nfunction htmlEscape(value) {\n  return String(value).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");\n}\n\nexport class Verdict {\n  constructor({ target, kind = \"unsupported\", level = \"unknown\", ok = false, reasons = [], raw = {} }) {\n    this.target = target;\n    this.kind = kind;\n    this.level = level;\n    this.ok = ok;\n    this.reasons = reasons;\n    this.raw = raw;\n  }\n\n  /** True only for blocklist-grade findings. Never true on a failure. */\n  get blocked() {\n    return HIGH.has(this.level);\n  }\n\n  get text() {\n    const heads = {\n      critical: \"\u26d4 *Critical risk.* Do not proceed.\",\n      high: \"\u26a0\ufe0f *High risk.* Do not proceed.\",\n      medium: \"\u26a0\ufe0f *Treat with caution.*\",\n      low: \"No known red flags.\",\n      unknown: this.ok\n        ? \"Nothing known against it.\"\n        : \"*Check did not complete.* Treat this as unchecked, not as safe.\",\n    };\n    const lines = [heads[this.level], \"\", \"`\" + codeSafe(this.target) + \"`\"];\n    if (this.reasons.length) {\n      lines.push(\"\");\n      for (const r of this.reasons) lines.push(\"\u2022 \" + codeSafe(r));\n    }\n    if ((this.level === \"low\" || this.level === \"unknown\") && this.ok) {\n      lines.push(\"\", \"_An absence of flags is not proof of safety._\");\n    }\n    lines.push(\"\", `_Checked with [RelayShield](${UPSELL})._`);\n    return lines.join(\"\\n\");\n  }\n\n  get html() {\n    const heads = {\n      critical: \"\u26d4 <b>Critical risk.</b> Do not proceed.\",\n      high: \"\u26a0\ufe0f <b>High risk.</b> Do not proceed.\",\n      medium: \"\u26a0\ufe0f <b>Treat with caution.</b>\",\n      low: \"No known red flags.\",\n      unknown: this.ok\n        ? \"Nothing known against it.\"\n        : \"<b>Check did not complete.</b> Treat this as unchecked, not as safe.\",\n    };\n    const lines = [heads[this.level], \"\", \"<code>\" + htmlEscape(this.target) + \"</code>\"];\n    if (this.reasons.length) {\n      lines.push(\"\");\n      for (const r of this.reasons) lines.push(\"\u2022 \" + htmlEscape(r));\n    }\n    if ((this.level === \"low\" || this.level === \"unknown\") && this.ok) {\n      lines.push(\"\", \"<i>An absence of flags is not proof of safety.</i>\");\n    }\n    lines.push(\"\", `<i>Checked with <a href=\"${UPSELL}\">RelayShield</a>.</i>`);\n    return lines.join(\"\\n\");\n  }\n}\n\n/** [kind, normalisedTarget]. Pure, no network. Exported for testing. */\nexport function classify(target) {\n  const raw = String(target ?? \"\").trim();\n  if (!raw) return [\"unsupported\", raw];\n\n  const ronin = RONIN.exec(raw);\n  if (ronin) return [\"address\", ronin[1]];\n\n  if (/^https?:\\/\\//i.test(raw)) return [\"url\", raw];\n  for (const pattern of [EVM, TON, BTC, SOL]) {\n    if (pattern.test(raw)) return [\"address\", raw];\n  }\n  // Checked AFTER the address patterns: some Solana addresses are 32-44 base58\n  // characters and would otherwise have to be excluded by hand.\n  if (BARE_DOMAIN.test(raw) && !raw.includes(\" \")) return [\"url\", \"https://\" + raw];\n  return [\"unsupported\", raw];\n}\n\n/**\n * Screen one URL or wallet address. Resolves to a Verdict; never rejects.\n *\n * timeoutMs defaults to 4000 because this runs inside a Telegram handler, and a\n * bot that stalls is worse than a bot that says it could not check.\n */\nexport async function check(target, opts = {}) {\n  const {\n    timeoutMs = 4000,\n    apiKey = \"\",\n    source = SOURCE,\n    apiBase = API_BASE,\n    transport = null,\n  } = opts;\n\n  const [kind, normalised] = classify(target);\n  if (kind === \"unsupported\") {\n    return new Verdict({ target: String(target ?? \"\").trim(), kind, ok: true, level: \"unknown\" });\n  }\n\n  const path = kind === \"url\" ? \"/v1/link-check\" : \"/v1/wallet-risk\";\n  const payload = kind === \"url\" ? { url: normalised, source } : { address: normalised, source };\n\n  let body;\n  try {\n    body = await (transport || post)(apiBase + path, payload, timeoutMs, apiKey);\n  } catch {\n    // Deliberately catch-all. Anything going wrong out here must produce an\n    // unchecked verdict rather than an exception in someone else's handler.\n    return new Verdict({ target: normalised, kind, ok: false, level: \"unknown\" });\n  }\n\n  if (!body || typeof body !== \"object\" || Array.isArray(body) || !body.ok) {\n    return new Verdict({\n      target: normalised, kind, ok: false, level: \"unknown\",\n      raw: body && typeof body === \"object\" && !Array.isArray(body) ? body : {},\n    });\n  }\n\n  const data = body.data || {};\n  let level;\n  let reasons;\n  if (kind === \"url\") {\n    level = String(data.level ?? \"unknown\").toLowerCase();\n    reasons = Array.isArray(data.reasons) ? data.reasons.map(String) : [];\n  } else {\n    level = String(data.risk_level ?? \"unknown\").toLowerCase();\n    if (level === \"clean\") level = \"low\";\n    reasons = Array.isArray(data.risk_flags)\n      ? data.risk_flags.map((f) => String(f).split(\"_\").join(\" \"))\n      : [];\n  }\n  if (!LEVELS.has(level)) level = \"unknown\";\n\n  return new Verdict({ target: normalised, kind, ok: true, level, reasons, raw: data });\n}\n\nasync function post(url, payload, timeoutMs, apiKey) {\n  const headers = { \"Content-Type\": \"application/json\", \"User-Agent\": \"relayshield-widget/1.0\" };\n  if (apiKey) headers[\"X-RS-API-KEY\"] = apiKey;\n  const resp = await fetch(url, {\n    method: \"POST\",\n    headers,\n    body: JSON.stringify(payload),\n    signal: AbortSignal.timeout(timeoutMs),\n  });\n  // A 429 is the daily keyless cap and is a real answer, not an outage, so the\n  // body is read either way. It still resolves to ok:false, because an\n  // unchecked target is unchecked whatever the reason.\n  return await resp.json();\n}\n\nexport default { check, classify, Verdict, API_BASE, SOURCE };\n";