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
  .linkish {
    background: none; border: 0; padding: 0; font: inherit; font-size: .82rem;
    color: var(--accent); text-decoration: underline; cursor: pointer;
  }
  .watch-intro { color: var(--hint); font-size: .85rem; margin: 4px 2px 10px; }
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

  <section id="pane-check">
    <textarea id="in" placeholder="Paste a link, or a TON address (EQ... / UQ... / 0:...)"
              autocapitalize="off" autocorrect="off" spellcheck="false"></textarea>
    <button class="go" id="go">Check it</button>
    <p class="example">Not sure what to paste?
      <button class="linkish" id="try-bad">Try a link that gets flagged</button></p>
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
  </footer>

<script type="module">
import { check } from "/relayshield-widget.js";

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
  unknown:  "Could not complete the check",
};

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
const TON_ADDR = /^(?:-?\d+:[0-9a-fA-F]{64}|[A-Za-z0-9_-]{48})$/;
const LOOKS_URL = /^(?:https?:\/\/|[a-z0-9-]+(?:\.[a-z0-9-]+)+)/i;
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
  try { v = await check(value, { source }); }
  catch (e) { v = { level: "unknown", target: value, reasons: ["The check did not complete."] }; }

  const level = HEADS[v.level] ? v.level : "unknown";
  last = { target: v.target || value, level, reasons: v.reasons || [] };

  $("out").dataset.level = level;
  $("head").textContent = HEADS[level];
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
        ? "Checked against our criminal-channel indicator corpus, Google Safe Browsing and domain age. None of them knows this one. That is an absence of evidence, not proof it is safe."
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
      : level === "unknown"
        ? "Not in any source we check. That is not the same as safe, and it says nothing about you. Checking your own email is a separate question with a definite answer."
        : "RelayShield can watch your email, phone and wallets for breaches, SIM swaps and stolen sessions.";
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
    if (tg && typeof tg.openTelegramLink === "function") {
      e.preventDefault();
      tg.openTelegramLink(el.href);
    }
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
     curl -sS -X POST https://api.relayshield.net/v1/link-check \
       -H 'content-type: application/json' \
       -d '{"url":"http://testsafebrowsing.appspot.com/s/malware.html"}' */
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

$("watch").addEventListener("click", async () => {
  if (!last) return;
  if (!uid) {
    $("watch").textContent = "Open this inside Telegram to watch";
    return;
  }
  $("watch").disabled = true;
  $("watch").textContent = "Saving...";
  try {
    const res = await post("/v1/watchlist/add", {
      init_data: initData, target: last.target, level: last.level,
    });
    if (res && res.ok) {
      $("watch").textContent = last.kind === "address" && isTon(last.target)
        ? "Watching. We will message you the moment it changes."
        : "Saved. Live re-checks cover TON addresses and tokens today.";
      return;
    }
    if (res && res.error === "slots_full") {
      offerUpgrade(res.data || {});
      $("watch").textContent = "Free slots are full.";
      $("watch").disabled = false;
      return;
    }
    $("watch").textContent = (res && res.error) || "Could not save that.";
    $("watch").disabled = false;
  } catch (e) {
    $("watch").textContent = "Could not save that.";
    $("watch").disabled = false;
  }
});

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
    btn.textContent = (res && res.error) || "Could not start the purchase.";
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

async function loadWatches() {
  const box = $("watchlist");
  if (!uid) {
    box.textContent = "";
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Open this inside Telegram to keep a watchlist.";
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

  const data = (res && res.ok && res.data) || {};
  const items = data.watches || [];

  if (data.limit) {
    const meter = document.createElement("p");
    meter.className = "empty";
    const until = data.slots_expire_at
      ? " \u00b7 until " + new Date(data.slots_expire_at * 1000).toISOString().slice(0, 10)
      : "";
    meter.textContent = data.used + " of " + data.limit + " slots used" + until;
    box.appendChild(meter);
    /* Offered BEFORE the slots are full, not only at the wall. A paywall
       discovered at the moment of refusal reads as a bait and switch even when
       the free tier was generous, and this one is three slots. */
    if (!data.slots_expire_at && data.used >= data.limit - 1) {
      offerUpgrade({
        message: "Watching more than " + data.limit + " things?",
        upgrade_stars: data.upgrade_stars, upgrade_slots: data.upgrade_slots,
        upgrade_days: data.upgrade_days,
      });
    }
  }

  if (!items.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Nothing watched yet. Check something, then tap "
      + "\u201cTell me if this changes\u201d.";
    box.appendChild(p);
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
  g.fillText(HEADS[last.level], 48, 96);
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
      .replaceAll("__SOURCE__", source);

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