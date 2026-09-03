/**
 * RelayShield check for Telegram bots. One function, no dependencies.
 *
 *   import { check } from "./relayshield-widget.js";
 *
 *   bot.on("message:text", async (ctx) => {
 *     const v = await check(ctx.message.text);
 *     if (v.blocked) await ctx.reply(v.text, { parse_mode: "Markdown" });
 *   });
 *
 * Works with grammY, Telegraf, node-telegram-bot-api or a raw webhook: it is a
 * plain async function over global fetch, not a framework integration.
 * Node 18+ (fetch and AbortSignal.timeout are built in).
 *
 * This is a direct port of widget/relayshield_widget.py and the two files must
 * stay in step. The rules they are both built around:
 *
 *   1. IT NEVER THROWS. A bot that crashes because our API had a bad minute
 *      gets uninstalled that week. Every failure path resolves to a verdict
 *      with level "unknown" and a message saying the check did not complete.
 *
 *   2. IT NEVER SAYS "SAFE". The link check is an absence of evidence across
 *      three sources, not proof of safety. The ceiling on a clean URL is
 *      "nothing known against it".
 *
 * Telegram's legacy "Markdown" parse mode HAS NO ESCAPE SYNTAX, so an
 * underscore in a URL can make Telegram reject the whole message with a 400 and
 * your verdict never arrives. Attacker-controlled values therefore go inside a
 * code span, which legacy Markdown treats as literal. Use .html with
 * parse_mode "HTML" if you prefer.
 *
 * Both endpoints are KEYLESS: no signup, no key, no card for the first call,
 * with a per-IP daily cap rather than a bill. Pass apiKey once you have one:
 * https://api.relayshield.net/developers?source=tg-widget
 */

export const API_BASE = "https://api.relayshield.net";
export const SOURCE = "tg-widget";
const UPSELL = "https://api.relayshield.net/developers?source=tg-widget";

// Mirrors _detect_chain_api in relayshield_api.py. Duplicated deliberately:
// this file is copied into other people's repositories. The server detects the
// chain again, so a disagreement costs one rejected call, never a wrong verdict.
const EVM = /^0x[0-9a-fA-F]{40}$/;
const TON = /^[EUeu][Qq][A-Za-z0-9_-]{46}$/;
const BTC = /^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$/;
const SOL = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

// ronin:0x… is how Ronin addresses are written, and every wallet regex rejects
// them. Stripping the prefix turns a rejected message into a checked one.
const RONIN = /^ronin:(0x[0-9a-fA-F]{40})$/i;

const BARE_DOMAIN = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?:[/?#].*)?$/i;

const HIGH = new Set(["high", "critical"]);
const LEVELS = new Set(["critical", "high", "medium", "low", "unknown"]);

/** Legacy Markdown has no escapes, so the only defence inside a code span is
 *  removing the one character that can close it. */
function codeSafe(value) {
  return String(value).split("`").join("");
}

function htmlEscape(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export class Verdict {
  constructor({ target, kind = "unsupported", level = "unknown", ok = false, reasons = [], raw = {} }) {
    this.target = target;
    this.kind = kind;
    this.level = level;
    this.ok = ok;
    this.reasons = reasons;
    this.raw = raw;
  }

  /** True only for blocklist-grade findings. Never true on a failure. */
  get blocked() {
    return HIGH.has(this.level);
  }

  get text() {
    const heads = {
      critical: "⛔ *Critical risk.* Do not proceed.",
      high: "⚠️ *High risk.* Do not proceed.",
      medium: "⚠️ *Treat with caution.*",
      low: "No known red flags.",
      unknown: this.ok
        ? "Nothing known against it."
        : "*Check did not complete.* Treat this as unchecked, not as safe.",
    };
    const lines = [heads[this.level], "", "`" + codeSafe(this.target) + "`"];
    if (this.reasons.length) {
      lines.push("");
      for (const r of this.reasons) lines.push("• " + codeSafe(r));
    }
    if ((this.level === "low" || this.level === "unknown") && this.ok) {
      lines.push("", "_An absence of flags is not proof of safety._");
    }
    lines.push("", `_Checked with [RelayShield](${UPSELL})._`);
    return lines.join("\n");
  }

  get html() {
    const heads = {
      critical: "⛔ <b>Critical risk.</b> Do not proceed.",
      high: "⚠️ <b>High risk.</b> Do not proceed.",
      medium: "⚠️ <b>Treat with caution.</b>",
      low: "No known red flags.",
      unknown: this.ok
        ? "Nothing known against it."
        : "<b>Check did not complete.</b> Treat this as unchecked, not as safe.",
    };
    const lines = [heads[this.level], "", "<code>" + htmlEscape(this.target) + "</code>"];
    if (this.reasons.length) {
      lines.push("");
      for (const r of this.reasons) lines.push("• " + htmlEscape(r));
    }
    if ((this.level === "low" || this.level === "unknown") && this.ok) {
      lines.push("", "<i>An absence of flags is not proof of safety.</i>");
    }
    lines.push("", `<i>Checked with <a href="${UPSELL}">RelayShield</a>.</i>`);
    return lines.join("\n");
  }
}

/** [kind, normalisedTarget]. Pure, no network. Exported for testing. */
export function classify(target) {
  const raw = String(target ?? "").trim();
  if (!raw) return ["unsupported", raw];

  const ronin = RONIN.exec(raw);
  if (ronin) return ["address", ronin[1]];

  if (/^https?:\/\//i.test(raw)) return ["url", raw];
  for (const pattern of [EVM, TON, BTC, SOL]) {
    if (pattern.test(raw)) return ["address", raw];
  }
  // Checked AFTER the address patterns: some Solana addresses are 32-44 base58
  // characters and would otherwise have to be excluded by hand.
  if (BARE_DOMAIN.test(raw) && !raw.includes(" ")) return ["url", "https://" + raw];
  return ["unsupported", raw];
}

/**
 * Screen one URL or wallet address. Resolves to a Verdict; never rejects.
 *
 * timeoutMs defaults to 4000 because this runs inside a Telegram handler, and a
 * bot that stalls is worse than a bot that says it could not check.
 */
export async function check(target, opts = {}) {
  const {
    timeoutMs = 4000,
    apiKey = "",
    source = SOURCE,
    apiBase = API_BASE,
    transport = null,
  } = opts;

  const [kind, normalised] = classify(target);
  if (kind === "unsupported") {
    return new Verdict({ target: String(target ?? "").trim(), kind, ok: true, level: "unknown" });
  }

  const path = kind === "url" ? "/v1/link-check" : "/v1/wallet-risk";
  const payload = kind === "url" ? { url: normalised, source } : { address: normalised, source };

  let body;
  try {
    body = await (transport || post)(apiBase + path, payload, timeoutMs, apiKey);
  } catch {
    // Deliberately catch-all. Anything going wrong out here must produce an
    // unchecked verdict rather than an exception in someone else's handler.
    return new Verdict({ target: normalised, kind, ok: false, level: "unknown" });
  }

  if (!body || typeof body !== "object" || Array.isArray(body) || !body.ok) {
    return new Verdict({
      target: normalised, kind, ok: false, level: "unknown",
      raw: body && typeof body === "object" && !Array.isArray(body) ? body : {},
    });
  }

  const data = body.data || {};
  let level;
  let reasons;
  if (kind === "url") {
    level = String(data.level ?? "unknown").toLowerCase();
    reasons = Array.isArray(data.reasons) ? data.reasons.map(String) : [];
  } else {
    level = String(data.risk_level ?? "unknown").toLowerCase();
    if (level === "clean") level = "low";
    reasons = Array.isArray(data.risk_flags)
      ? data.risk_flags.map((f) => String(f).split("_").join(" "))
      : [];
  }
  if (!LEVELS.has(level)) level = "unknown";

  return new Verdict({ target: normalised, kind, ok: true, level, reasons, raw: data });
}

async function post(url, payload, timeoutMs, apiKey) {
  const headers = { "Content-Type": "application/json", "User-Agent": "relayshield-widget/1.0" };
  if (apiKey) headers["X-RS-API-KEY"] = apiKey;
  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(timeoutMs),
  });
  // A 429 is the daily keyless cap and is a real answer, not an outage, so the
  // body is read either way. It still resolves to ok:false, because an
  // unchecked target is unchecked whatever the reason.
  return await resp.json();
}

export default { check, classify, Verdict, API_BASE, SOURCE };
