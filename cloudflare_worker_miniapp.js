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
//   * No initData signature verification, because nothing here is
//     user-specific and there is no account to impersonate. If v2 ever stores
//     anything per user, that check becomes mandatory before it does.
//   * No wallet connect. TON Connect is a v2 question and would gate the first
//     answer behind a wallet, which is the opposite of the point.
//   * No analytics beyond the ?source= key the API already logs.

const API_BASE = "https://api.relayshield.net";
const DEVELOPERS = API_BASE + "/developers";
const BOT = "https://t.me/relayshield_bot";

// Keys the Mini App may pass through as ?source=. An unknown start_param is
// dropped rather than forwarded: an unregistered key logs `unmatched:` and
// renders no banner, so forwarding junk would look like attribution and be none.
const ALLOWED_SOURCES = new Set([
  "tg-miniapp",
  "tg-miniapp-channel",
  "tg-miniapp-directory",
  "tg-miniapp-blog",
  "tg-miniapp-bot",
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
    margin: 0; padding: 16px;
    background: var(--bg); color: var(--text);
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  h1 { font-size: 1.15rem; margin: 0 0 4px; }
  .sub { color: var(--hint); font-size: .85rem; margin: 0 0 18px; }
  textarea {
    width: 100%; min-height: 84px; padding: 12px; resize: vertical;
    background: var(--card); color: var(--text);
    border: 1px solid rgba(148,163,184,.25); border-radius: 12px;
    font: inherit; font-size: 16px;
  }
  textarea:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  button.go {
    width: 100%; margin-top: 12px; padding: 14px;
    background: var(--accent); color: var(--accent-text);
    border: 0; border-radius: 12px; font: inherit; font-weight: 600;
  }
  button.go[disabled] { opacity: .5; }
  .verdict {
    margin-top: 18px; padding: 14px; border-radius: 12px;
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
  footer { margin-top: 26px; text-align: center; font-size: .8rem; }
  footer a { color: var(--accent); text-decoration: none; }
  .hidden { display: none; }
</style>
</head>
<body>
  <h1>Check a link or wallet address</h1>
  <p class="sub">Paste anything you were sent. No signup, no wallet connect.</p>

  <textarea id="in" placeholder="https://... or 0x... or a TON, Solana or Bitcoin address"
            autocapitalize="off" autocorrect="off" spellcheck="false"></textarea>
  <button class="go" id="go">Check it</button>

  <div class="verdict hidden" id="out" data-level="unknown">
    <p class="head" id="head"></p>
    <p class="target" id="target"></p>
    <ul id="reasons"></ul>
    <p class="caveat" id="caveat"></p>
  </div>

  <footer>
    <a id="more" href="__DEVELOPERS__" target="_blank" rel="noopener">Run this check from your own bot or agent</a>
  </footer>

<script type="module">
import { check } from "/relayshield-widget.js";

const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }

// Telegram hands the deep link's startapp value to the page here. An
// unregistered value is dropped server-side, so this only ever forwards a key
// that renders a banner.
const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || "";
const SOURCE = "__SOURCE__";
const source = /^[a-z0-9-]{1,40}$/.test(startParam) ? startParam : SOURCE;
document.getElementById("more").href = "__DEVELOPERS__?source=" + encodeURIComponent(source);

const HEADS = {
  critical: "Do not proceed",
  high:     "Do not proceed",
  medium:   "Treat with caution",
  low:      "Nothing known against it",
  unknown:  "Could not complete the check",
};

const inEl = document.getElementById("in");
const goEl = document.getElementById("go");
const outEl = document.getElementById("out");

function haptic(level) {
  if (!tg || !tg.HapticFeedback) return;
  const map = { critical: "error", high: "error", medium: "warning", low: "success" };
  if (map[level]) tg.HapticFeedback.notificationOccurred(map[level]);
}

async function run() {
  const value = inEl.value.trim();
  if (!value) return;
  goEl.disabled = true;
  goEl.textContent = "Checking...";
  let v;
  try {
    v = await check(value, { source });
  } catch (e) {
    // check() is documented never to throw, so this is belt and braces: a
    // thrown error here would leave the user with a spinner and no answer,
    // which is worse than a stated "could not complete".
    v = { level: "unknown", target: value, reasons: ["The check did not complete."] };
  }
  const level = HEADS[v.level] ? v.level : "unknown";

  outEl.dataset.level = level;
  document.getElementById("head").textContent = HEADS[level];
  document.getElementById("target").textContent = v.target || value;

  const ul = document.getElementById("reasons");
  ul.textContent = "";
  for (const r of (v.reasons || [])) {
    const li = document.createElement("li");
    li.textContent = r;            // textContent, never innerHTML: the reasons
    ul.appendChild(li);            // can quote attacker-supplied strings.
  }

  // The ceiling is "nothing known against it". Saying "safe" is the one thing
  // this product does not do, and the caveat is part of the answer rather than
  // small print, exactly as the endpoints' own responses state it.
  document.getElementById("caveat").textContent =
    level === "low"
      ? "This means nothing known against it, which is not the same as safe."
      : level === "unknown"
        ? "No verdict was reached. Treat that as unknown, not as clear."
        : "Based on indicators seen in criminal channels and public feeds.";

  outEl.classList.remove("hidden");
  haptic(level);
  goEl.disabled = false;
  goEl.textContent = "Check it";
}

goEl.addEventListener("click", run);
inEl.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
});
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