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
const ALLOWED_SOURCES = new Set([
  "tg-miniapp",
  "tg-miniapp-channel",
  "tg-miniapp-directory",
  "tg-miniapp-blog",
  "tg-miniapp-bot",
  "tg-miniapp-share",
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
    <textarea id="in" placeholder="https://... or 0x... or a TON, Solana or Bitcoin address"
              autocapitalize="off" autocorrect="off" spellcheck="false"></textarea>
    <button class="go" id="go">Check it</button>

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
    <div id="watchlist"></div>
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
const SOURCE = "__SOURCE__";
const source = /^[a-z0-9-]{1,40}$/.test(startParam) ? startParam : SOURCE;
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
async function run() {
  const value = $("in").value.trim();
  if (!value) return;
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
    $("watch").textContent = res && res.ok
      ? "Watching. We will message you if it changes."
      : (res && res.error) || "Could not save that.";
  } catch (e) {
    $("watch").textContent = "Could not save that.";
    $("watch").disabled = false;
  }
});

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

  const items = (res && res.ok && res.data && res.data.watches) || [];
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
    t.textContent = w.target;
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
  g.fillStyle = "#64748b";
  g.font = "20px -apple-system, system-ui, sans-serif";
  g.fillText("Checked with RelayShield \u00b7 t.me/relayshield_bot", 48, 386);
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