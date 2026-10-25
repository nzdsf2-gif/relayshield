/**
 * relayshield-webcheck: free, no-signup web scam check at relayshield.net/check.
 *
 * A visitor pastes a link, wallet address, or email address, or uploads an
 * image (QR code or screenshot), and gets a RelayShield verdict card, free,
 * with no account. The verdict renders the same card format the bots send.
 *
 * Backend: the existing keyless API endpoints, the same ones the WhatsApp
 * front-door check uses. No new Lambda endpoints.
 *   link   -> POST https://api.relayshield.net/v1/link-check  {url, source}
 *   wallet -> POST https://api.relayshield.net/v1/wallet-risk {address, source}
 *   email  -> POST https://api.relayshield.net/v1/email-check {from_address, source}
 * Responses carry the API's own envelope {ok, data} or {ok: false, error}.
 *
 * Abuse controls: Cloudflare Turnstile on submit (when the secret is set)
 * plus per-IP rate limiting in KV (when the binding is present). Both fail
 * OPEN when unconfigured, following the checkemail Worker: a missing binding
 * or secret must never turn a working page into a broken one. /check/health
 * reports which controls are live, never their values.
 *
 * Attribution: the bot buttons on the verdict card point at /check/go, which
 * counts the click and then 302s to the real deep link. The deep links carry
 * payloads the bots already log: Telegram ?start=SRC_webcheck (the bot's
 * /start handler logs SRC_ acquisition sources), WhatsApp
 * ?text=SRC_webcheck (house convention, same as the blog and checkemail
 * workers), miniApp ?startapp=webcheck (the miniApp worker honours
 * startapp values). A bare ?start=webcheck must NOT be used: the bot
 * upper-cases the payload and a bare 8-letter word would hit the legacy
 * Coinbase charge-code branch before falling through.
 *
 * Uploaded images: the page first tries to decode a QR code in the browser
 * (jsQR from CDN, full browser image support). Only if that fails does the
 * file reach this Worker, where it is validated (size, magic bytes) and run
 * through server-side QR decode first (jsQR over a PNG/JPEG pixel pipeline
 * below), then screenshot OCR (AWS Rekognition DetectText, the same engine
 * the bots' MSGSCAN path uses) if no QR code is found. Any link, wallet, or
 * email found in the decoded text is checked. GIF and WebP uploads skip the
 * QR step (no decoder for those formats here) and go straight to OCR.
 *
 * Submitted items are checked, not stored. KV holds counts only: check
 * totals by type and verdict, conversion clicks by destination, and daily
 * buckets for the weekly report. No input, no image, no IP is persisted
 * beyond the rate-limit window.
 *
 * npm dependencies: jsqr (QR decode) and jpeg-js (JPEG pixels). PNG pixels
 * come from a small decoder in this file (DecompressionStream inflate).
 * package.json at the repo root pins both; node_modules is never committed.
 * The browser page still loads jsQR from CDN for its own decode path.
 */

import jsQR from "jsqr";
import jpeg from "jpeg-js";

const API_BASE_DEFAULT = "https://api.relayshield.net";
const CHECK_TIMEOUT_MS = 15000;
const MAX_INPUT_CHARS = 2000;
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const RATE_LIMIT_PER_MINUTE = 20;
const RATE_LIMIT_UPLOADS_PER_MINUTE = 5;
const RATE_LIMIT_PER_DAY = 200;

const CARD_HEADER = "RelayShield Verdict";
const CARD_FOOTER =
  "Checked against a growing threat intelligence corpus with over 129 monitored marketplaces.";

const GO_LINKS = {
  tg: {
    label: "Try it yourself on Telegram",
    deep: "https://t.me/relayshield_bot?start=SRC_webcheck",
  },
  wa: {
    label: "Try it yourself on WhatsApp",
    deep: "https://wa.me/17407373961?text=SRC_webcheck",
  },
  miniapp: {
    label: "Try it yourself in the miniApp",
    deep: "https://t.me/relayshield_bot/idcheck?startapp=webcheck",
  },
};

const BADGES = {
  threat: "THREAT DETECTED",
  suspicious: "SUSPICIOUS",
  clean: "NO FLAGS FOUND",
  unchecked: "UNCHECKED",
};

const FORWARD_LINES = {
  link: "Forward this verdict to anyone who received the same link.",
  wallet: "Forward this verdict to anyone who received the same wallet address.",
  email: "Forward this verdict to anyone who received mail from this sender.",
};

const ACTIONS = {
  link: {
    threat: "Do not click this link. Delete the message if it was sent to you.",
    suspicious:
      "Do not click this link until you have verified the sender another way.",
    clean:
      "No suspicious scam signals detected in this check. That is not a guarantee: new scam pages appear daily.",
    unchecked: "Treat this as potentially risky until verified.",
  },
  wallet: {
    threat: "Do NOT swap, approve, or interact with this wallet.",
    suspicious:
      "Do not send funds to this wallet until you have verified the owner another way.",
    clean:
      "No critical flags detected for this wallet. That is not a guarantee: a wallet's risk profile can change.",
    unchecked: "Treat this as potentially risky until verified.",
  },
  email: {
    threat:
      "Do not reply to mail from this sender, and do not click anything in it.",
    suspicious:
      "Treat mail from this sender with suspicion. Verify through another channel before acting.",
    clean:
      "No flags found for this sender. That is not a guarantee: new scam senders appear daily. Suspicious mail can be forwarded to checkemail@relayshield.net.",
    unchecked: "Treat this as potentially risky until verified.",
  },
};

/** Escape text for HTML insertion. Card targets and reasons are user input
 *  and API output; they must never be inserted raw. */
export function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function truncateTarget(target, maxLen) {
  const t = String(target);
  if (t.length <= maxLen) return t;
  return t.slice(0, maxLen - 3) + "...";
}

function shortAddress(address) {
  const a = String(address);
  if (a.length <= 16) return a;
  return a.slice(0, 6) + "..." + a.slice(-4);
}

const EVM_RE = /^0x[0-9a-fA-F]{40}$/;
const TON_RE = /^[EU]Q[0-9A-Za-z_-]{46}$/;
const SOLANA_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;
const BTC_RE = /^(bc1[qp][0-9a-z]{38,58}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const URL_SCHEME_RE = /^https?:\/\//i;
const DOMAIN_RE = /^[^\s/:]+\.[a-z]{2,}(:\d+)?(\/\S*)?$/i;
const FIND_URL_RE = /https?:\/\/[^\s"'<>]+/i;
const FIND_EMAIL_RE = /[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+/;
const FIND_WALLET_RE = /0x[0-9a-fA-F]{40}|[EU]Q[0-9A-Za-z_-]{46}|[1-9A-HJ-NP-Za-km-z]{32,44}/;

/**
 * Classify a pasted input. Returns {kind, value} or {kind: "unknown"}.
 * Order matters: scheme URLs first, then email, then bare domains (a domain
 * has a dot; a Solana address does not), then wallets.
 */
export function classifyInput(raw) {
  const input = String(raw == null ? "" : raw).trim();
  if (!input || input.length > MAX_INPUT_CHARS) return { kind: "unknown" };
  if (/\s/.test(input)) return { kind: "unknown" };
  if (URL_SCHEME_RE.test(input)) return { kind: "link", value: input };
  if (EMAIL_RE.test(input)) return { kind: "email", value: input };
  if (DOMAIN_RE.test(input)) return { kind: "link", value: "https://" + input };
  if (EVM_RE.test(input) || TON_RE.test(input) || BTC_RE.test(input)) {
    return { kind: "wallet", value: input };
  }
  if (SOLANA_RE.test(input)) return { kind: "wallet", value: input };
  return { kind: "unknown" };
}

/** Map an API verdict to a card badge key. */
export function badgeFor(kind, apiResult) {
  if (!apiResult || apiResult.ok === false) return "unchecked";
  const data = apiResult.data || {};
  if (kind === "link") {
    if (data.checked === false) return "unchecked";
    const level = String(data.level || "unknown").toLowerCase();
    if (level === "critical" || level === "high") return "threat";
    if (level === "medium") return "suspicious";
    if (level === "low" || level === "clean") return "clean";
    return "unchecked";
  }
  if (kind === "wallet") {
    const level = String(data.risk_level || "").toUpperCase();
    if (level === "CRITICAL" || level === "HIGH") return "threat";
    if (level === "MEDIUM") return "suspicious";
    if (level === "LOW") return "clean";
    return "unchecked";
  }
  if (kind === "email") {
    const risk = String(data.risk || "").toLowerCase();
    if (risk === "high") return "threat";
    if (risk === "medium") return "suspicious";
    if (risk === "low") return "clean";
    return "unchecked";
  }
  return "unchecked";
}

/** Why lines: the API's own reasons/flags only, max 2, never invented. */
export function whyFor(kind, apiResult) {
  const data = (apiResult && apiResult.data) || {};
  let reasons = [];
  if (kind === "link") reasons = data.reasons || [];
  else if (kind === "wallet") reasons = data.risk_flags || [];
  else if (kind === "email") reasons = data.flags || [];
  const lines = reasons
    .map((r) => String(r).trim())
    .filter(Boolean)
    .slice(0, 2);
  if (lines.length > 0) return lines;
  if (apiResult && apiResult.ok === false) {
    return ["The check could not be completed. Try again shortly."];
  }
  return ["No further detail returned."];
}

/**
 * Build the verdict card object the page renders. Target display follows
 * the bot card rule: wallets truncated first6/last4, everything else shown
 * in full up to 100 chars. Bot links point at /check/go so clicks count;
 * the deep links behind them carry the attribution payloads.
 */
export function buildCard(kind, target, apiResult, via) {
  const badge = badgeFor(kind, apiResult);
  const displayTarget =
    kind === "wallet" ? shortAddress(target) : truncateTarget(target, 100);
  return {
    header: CARD_HEADER,
    badge: BADGES[badge],
    badgeKey: badge,
    target: displayTarget,
    targetFull: String(target),
    why: whyFor(kind, apiResult),
    action: ACTIONS[kind][badge],
    footer: CARD_FOOTER,
    forward: FORWARD_LINES[kind],
    via: via || "paste",
    botLinks: [
      { dest: "tg", label: GO_LINKS.tg.label, href: "/check/go?to=tg" },
      { dest: "wa", label: GO_LINKS.wa.label, href: "/check/go?to=wa" },
      {
        dest: "miniapp",
        label: GO_LINKS.miniapp.label,
        href: "/check/go?to=miniapp",
      },
    ],
  };
}

/** Card for a check that could not run at all. Never a 500 for the visitor. */
export function uncheckedCard(kind, target, note, via) {
  return {
    header: CARD_HEADER,
    badge: BADGES.unchecked,
    badgeKey: "unchecked",
    target:
      kind === "wallet" ? shortAddress(target) : truncateTarget(target, 100),
    targetFull: String(target),
    why: [note || "The check could not be completed. Try again shortly."],
    action: ACTIONS[kind] ? ACTIONS[kind].unchecked : "Treat this as potentially risky until verified.",
    footer: CARD_FOOTER,
    forward: FORWARD_LINES[kind] || FORWARD_LINES.link,
    via: via || "paste",
    botLinks: [
      { dest: "tg", label: GO_LINKS.tg.label, href: "/check/go?to=tg" },
      { dest: "wa", label: GO_LINKS.wa.label, href: "/check/go?to=wa" },
      {
        dest: "miniapp",
        label: GO_LINKS.miniapp.label,
        href: "/check/go?to=miniapp",
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* KV helpers: rate limiting and counts-only metrics.                  */
/* Every KV access is best-effort and swallowed: a missing binding or  */
/* a KV error must never break a check (checkemail fail-open pattern). */
/* Counts are approximate under concurrent load: KV has no atomic      */
/* increment, so read-modify-write can lose a count when two requests  */
/* land in the same moment. That is acceptable for a weekly report.    */
/* ------------------------------------------------------------------ */

function clientIp(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    (request.headers.get("X-Forwarded-For") || "").split(",")[0].trim() ||
    "unknown"
  );
}

function minuteBucket(date) {
  return date.toISOString().slice(0, 16).replace(/[^0-9]/g, "");
}

function dayBucket(date) {
  return date.toISOString().slice(0, 10);
}

async function kvGet(kv, key) {
  if (!kv) return null;
  try {
    const value = await kv.get(key);
    return value == null ? null : parseInt(value, 10) || 0;
  } catch {
    return null;
  }
}

async function kvIncr(kv, key, ttlSeconds) {
  if (!kv) return;
  try {
    const current = (await kvGet(kv, key)) || 0;
    await kv.put(key, String(current + 1), { expirationTtl: ttlSeconds });
  } catch {
    /* counts are best-effort */
  }
}

/** True when the IP is over either limit. Fails open without KV. */
export async function isRateLimited(kv, ip, now, isUpload) {
  if (!kv) return false;
  const perMinute = isUpload ? RATE_LIMIT_UPLOADS_PER_MINUTE : RATE_LIMIT_PER_MINUTE;
  const minuteKey = `rl:${ip}:${minuteBucket(now)}`;
  const dayKey = `rl-day:${ip}:${dayBucket(now)}`;
  const [minuteCount, dayCount] = await Promise.all([
    kvGet(kv, minuteKey),
    kvGet(kv, dayKey),
  ]);
  if ((minuteCount || 0) >= perMinute) return true;
  if ((dayCount || 0) >= RATE_LIMIT_PER_DAY) return true;
  try {
    await Promise.all([
      kv.put(minuteKey, String((minuteCount || 0) + 1), { expirationTtl: 180 }),
      kv.put(dayKey, String((dayCount || 0) + 1), { expirationTtl: 172800 }),
    ]);
  } catch {
    /* fail open */
  }
  return false;
}

/** Record a finished check and a conversion click. Best-effort. */
export async function recordCheck(kv, kind, badgeKey, now) {
  if (!kv) return;
  const day = dayBucket(now);
  const keys = [
    ["m:checks:total", 0],
    [`m:checks:${kind}`, 0],
    [`m:verdict:${badgeKey}`, 0],
    [`m:d:${day}:checks`, 172800],
    [`m:d:${day}:checks:${kind}`, 172800],
    [`m:d:${day}:verdict:${badgeKey}`, 172800],
  ];
  await Promise.all(keys.map(([k, ttl]) => kvIncr(kv, k, ttl || 31536000)));
}

export async function recordConversion(kv, dest, now) {
  if (!kv) return;
  const day = dayBucket(now);
  await Promise.all([
    kvIncr(kv, `m:conv:${dest}`, 31536000),
    kvIncr(kv, `m:d:${day}:conv:${dest}`, 172800),
  ]);
}

/** Shape returned by GET /check/metrics. */
export async function readMetrics(kv, now) {
  if (!kv) return { available: false };
  const dayKeys = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(now.getTime() - i * 86400000);
    dayKeys.push(dayBucket(d));
  }
  const get = (k) => kvGet(kv, k);
  const [total, byLink, byWallet, byEmail, byUpload, convTg, convWa, convMini] =
    await Promise.all([
      get("m:checks:total"),
      get("m:checks:link"),
      get("m:checks:wallet"),
      get("m:checks:email"),
      get("m:checks:upload"),
      get("m:conv:tg"),
      get("m:conv:wa"),
      get("m:conv:miniapp"),
    ]);
  const days = [];
  for (const day of dayKeys) {
    const [checks, tg, wa, mini] = await Promise.all([
      get(`m:d:${day}:checks`),
      get(`m:d:${day}:conv:tg`),
      get(`m:d:${day}:conv:wa`),
      get(`m:d:${day}:conv:miniapp`),
    ]);
    days.push({
      day,
      checks: checks || 0,
      conv_tg: tg || 0,
      conv_wa: wa || 0,
      conv_miniapp: mini || 0,
    });
  }
  const last7Checks = days.reduce((a, d) => a + d.checks, 0);
  const last7Conv =
    days.reduce((a, d) => a + d.conv_tg + d.conv_wa + d.conv_miniapp, 0);
  return {
    available: true,
    checks_total: total || 0,
    checks_by_type: {
      link: byLink || 0,
      wallet: byWallet || 0,
      email: byEmail || 0,
      upload: byUpload || 0,
    },
    conversions_total: {
      tg: convTg || 0,
      wa: convWa || 0,
      miniapp: convMini || 0,
    },
    last_7_days: {
      checks: last7Checks,
      conversions: last7Conv,
      conversions_by_dest: {
        tg: days.reduce((a, d) => a + d.conv_tg, 0),
        wa: days.reduce((a, d) => a + d.conv_wa, 0),
        miniapp: days.reduce((a, d) => a + d.conv_miniapp, 0),
      },
      conversion_rate:
        last7Checks > 0 ? Math.round((last7Conv / last7Checks) * 1000) / 10 : 0,
      days,
    },
  };
}

/* ------------------------------------------------------------------ */
/* Turnstile verification.                                             */
/* ------------------------------------------------------------------ */

/** Verify a Turnstile token. Returns {ok} or {skipped} when no secret is
 *  configured. An explicit invalid token fails closed; a verification
 *  service error fails open (the rate limiter is the backstop) so a
 *  Cloudflare outage does not take the page down. */
export async function verifyTurnstile(secret, token, ip, fetchFn) {
  if (!secret) return { skipped: true };
  if (!token) return { ok: false, reason: "missing-token" };
  try {
    const body = new URLSearchParams({
      secret,
      response: token,
      remoteip: ip || "",
    });
    const resp = await fetchFn(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      },
    );
    const data = await resp.json();
    if (data && data.success === true) return { ok: true };
    return { ok: false, reason: "invalid-token" };
  } catch {
    return { ok: true, degraded: true };
  }
}

/* ------------------------------------------------------------------ */
/* API client: the keyless endpoints.                                  */
/* ------------------------------------------------------------------ */

async function postJson(url, payload, fetchFn) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHECK_TIMEOUT_MS);
  try {
    const resp = await fetchFn(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "relayshield-webcheck/1.0",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const text = await resp.text();
    try {
      return JSON.parse(text);
    } catch {
      return { ok: false, error: "unparseable-response" };
    }
  } catch {
    return { ok: false, error: "api-unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

/** Run one classified input through its keyless endpoint. */
export async function runCheck(kind, value, apiBase, fetchFn) {
  const base = (apiBase || API_BASE_DEFAULT).replace(/\/$/, "");
  if (kind === "link") {
    return postJson(`${base}/v1/link-check`, { url: value, source: "webcheck" }, fetchFn);
  }
  if (kind === "wallet") {
    return postJson(`${base}/v1/wallet-risk`, { address: value, source: "webcheck" }, fetchFn);
  }
  if (kind === "email") {
    return postJson(
      `${base}/v1/email-check`,
      { from_address: value, source: "webcheck" },
      fetchFn,
    );
  }
  return { ok: false, error: "unknown-kind" };
}

/* ------------------------------------------------------------------ */
/* Uploads: validation, QR decode, Rekognition OCR fallback.            */
/* ------------------------------------------------------------------ */

export function sniffImageType(bytes) {
  if (!bytes || bytes.length < 12) return null;
  if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return "png";
  }
  if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "jpeg";
  }
  if (bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46) {
    return "gif";
  }
  if (
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
  ) {
    return "webp";
  }
  return null;
}

/** Validate an uploaded file. Returns {ok} or {ok: false, reason}. */
export function validateUpload(bytes, fileName) {
  if (!bytes || bytes.length === 0) return { ok: false, reason: "empty-file" };
  if (bytes.length > MAX_UPLOAD_BYTES) {
    return { ok: false, reason: "too-large" };
  }
  const type = sniffImageType(bytes);
  if (!type) return { ok: false, reason: "not-an-image" };
  return { ok: true, type, fileName: String(fileName || "upload") };
}

/**
 * Server-side QR decode: image bytes to QR text, or null. Never throws:
 * any failure here must fall through to the OCR path below, not fail the
 * upload. Order in handleUpload is QR first, then OCR.
 *
 * Pipeline: PNG pixels come from decodePngToRgba in this file (pure JS:
 * chunk walk, DecompressionStream inflate, all five row filters, color
 * types 0/2/3/4/6, bit depths 1/2/4/8/16). JPEG pixels come from jpeg-js.
 * GIF and WebP have no decoder here and return null. Interlaced
 * (Adam7) PNGs return null; the browser decode path covers those, since
 * canvas decodes every PNG shape. Large images are box-averaged down to
 * a 1600px max dimension before jsQR, so a phone screenshot cannot blow
 * the Worker's CPU budget on a 4000px decode.
 */
const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const MAX_QR_DIMENSION = 1600;

async function inflateZlib(data) {
  const stream = new Blob([data])
    .stream()
    .pipeThrough(new DecompressionStream("deflate"));
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

/**
 * Decode PNG bytes to RGBA. Returns {data, width, height} or null.
 * Non-interlaced only; see the block comment above for the covered set.
 */
export async function decodePngToRgba(bytes) {
  if (!bytes || bytes.length < 8) return null;
  for (let i = 0; i < 8; i++) {
    if (bytes[i] !== PNG_SIGNATURE[i]) return null;
  }
  let pos = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let palette = null;
  let trns = null;
  const idat = [];
  while (pos + 8 <= bytes.length) {
    const len =
      (bytes[pos] << 24) | (bytes[pos + 1] << 16) | (bytes[pos + 2] << 8) | bytes[pos + 3];
    const type = String.fromCharCode(
      bytes[pos + 4],
      bytes[pos + 5],
      bytes[pos + 6],
      bytes[pos + 7],
    );
    const start = pos + 8;
    const end = start + len;
    if (end + 4 > bytes.length) return null;
    const chunk = bytes.subarray(start, end);
    if (type === "IHDR") {
      width =
        (chunk[0] << 24) | (chunk[1] << 16) | (chunk[2] << 8) | chunk[3];
      height =
        (chunk[4] << 24) | (chunk[5] << 16) | (chunk[6] << 8) | chunk[7];
      bitDepth = chunk[8];
      colorType = chunk[9];
      if (chunk[10] !== 0 || chunk[11] !== 0) return null;
      if (chunk[12] !== 0) return null; // interlaced (Adam7): not supported
    } else if (type === "PLTE") {
      palette = chunk;
    } else if (type === "tRNS") {
      trns = chunk;
    } else if (type === "IDAT") {
      idat.push(chunk);
    } else if (type === "IEND") {
      break;
    }
    pos = end + 4;
  }
  if (!width || !height || !bitDepth) return null;
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType];
  if (!channels) return null;
  if (![1, 2, 4, 8, 16].includes(bitDepth)) return null;
  if (colorType === 3 && !palette) return null;

  const total = idat.reduce((n, c) => n + c.length, 0);
  const compressed = new Uint8Array(total);
  let off = 0;
  for (const c of idat) {
    compressed.set(c, off);
    off += c.length;
  }
  let raw;
  try {
    raw = await inflateZlib(compressed);
  } catch {
    return null;
  }
  const bitsPerPixel = channels * bitDepth;
  const rowBytes = Math.ceil((width * bitsPerPixel) / 8);
  const stride = rowBytes + 1;
  if (raw.length < height * stride) return null;

  // Unfilter in place, row by row.
  const bpp = Math.max(1, Math.floor(bitsPerPixel / 8));
  const rows = new Uint8Array(height * rowBytes);
  let prev = null;
  for (let y = 0; y < height; y++) {
    const filter = raw[y * stride];
    const row = raw.subarray(y * stride + 1, y * stride + 1 + rowBytes);
    const out = rows.subarray(y * rowBytes, (y + 1) * rowBytes);
    if (filter === 0) {
      out.set(row);
    } else if (filter === 1) {
      for (let i = 0; i < rowBytes; i++) {
        const a = i >= bpp ? out[i - bpp] : 0;
        out[i] = (row[i] + a) & 0xff;
      }
    } else if (filter === 2) {
      for (let i = 0; i < rowBytes; i++) {
        const b = prev ? prev[i] : 0;
        out[i] = (row[i] + b) & 0xff;
      }
    } else if (filter === 3) {
      for (let i = 0; i < rowBytes; i++) {
        const a = i >= bpp ? out[i - bpp] : 0;
        const b = prev ? prev[i] : 0;
        out[i] = (row[i] + Math.floor((a + b) / 2)) & 0xff;
      }
    } else if (filter === 4) {
      for (let i = 0; i < rowBytes; i++) {
        const a = i >= bpp ? out[i - bpp] : 0;
        const b = prev ? prev[i] : 0;
        const c = i >= bpp && prev ? prev[i - bpp] : 0;
        out[i] = (row[i] + paeth(a, b, c)) & 0xff;
      }
    } else {
      return null;
    }
    prev = out;
  }

  const rgba = new Uint8ClampedArray(width * height * 4);
  const maxSample = (1 << bitDepth) - 1;
  const readSample = (rowData, px, ch) => {
    if (bitDepth === 8) return rowData[px * channels + ch];
    if (bitDepth === 16) return rowData[(px * channels + ch) * 2];
    const bitPos = px * bitsPerPixel + ch * bitDepth;
    const byte = rowData[bitPos >> 3];
    const shift = 8 - bitDepth - (bitPos & 7);
    return (byte >> shift) & maxSample;
  };
  const scale = (v) => (bitDepth === 8 ? v : Math.round((v * 255) / maxSample));
  for (let y = 0; y < height; y++) {
    const rowData = rows.subarray(y * rowBytes, (y + 1) * rowBytes);
    for (let x = 0; x < width; x++) {
      const o = (y * width + x) * 4;
      if (colorType === 0) {
        const g = scale(readSample(rowData, x, 0));
        rgba[o] = g;
        rgba[o + 1] = g;
        rgba[o + 2] = g;
        rgba[o + 3] = 255;
        if (trns && trns.length >= 2) {
          const t = (trns[0] << 8) | trns[1];
          if (readSample(rowData, x, 0) === t) rgba[o + 3] = 0;
        }
      } else if (colorType === 2) {
        const r = scale(readSample(rowData, x, 0));
        const g = scale(readSample(rowData, x, 1));
        const b = scale(readSample(rowData, x, 2));
        rgba[o] = r;
        rgba[o + 1] = g;
        rgba[o + 2] = b;
        rgba[o + 3] = 255;
        if (trns && trns.length >= 6) {
          const tr = (trns[0] << 8) | trns[1];
          const tg = (trns[2] << 8) | trns[3];
          const tb = (trns[4] << 8) | trns[5];
          if (
            readSample(rowData, x, 0) === tr &&
            readSample(rowData, x, 1) === tg &&
            readSample(rowData, x, 2) === tb
          ) {
            rgba[o + 3] = 0;
          }
        }
      } else if (colorType === 3) {
        const idx = readSample(rowData, x, 0);
        const pi = idx * 3;
        if (pi + 2 >= palette.length) return null;
        rgba[o] = palette[pi];
        rgba[o + 1] = palette[pi + 1];
        rgba[o + 2] = palette[pi + 2];
        rgba[o + 3] = trns && idx < trns.length ? trns[idx] : 255;
      } else if (colorType === 4) {
        const g = scale(readSample(rowData, x, 0));
        const a = scale(readSample(rowData, x, 1));
        rgba[o] = g;
        rgba[o + 1] = g;
        rgba[o + 2] = g;
        rgba[o + 3] = a;
      } else if (colorType === 6) {
        rgba[o] = scale(readSample(rowData, x, 0));
        rgba[o + 1] = scale(readSample(rowData, x, 1));
        rgba[o + 2] = scale(readSample(rowData, x, 2));
        rgba[o + 3] = scale(readSample(rowData, x, 3));
      }
    }
  }
  return { data: rgba, width, height };
}

/** Decode JPEG bytes to RGBA via jpeg-js. Returns null on failure. */
export function decodeJpegToRgba(bytes) {
  try {
    const img = jpeg.decode(bytes);
    return {
      data: new Uint8ClampedArray(img.data),
      width: img.width,
      height: img.height,
    };
  } catch {
    return null;
  }
}

/** Box-average downscale so jsQR never sees a huge image. */
export function downscaleRgba(data, width, height) {
  const maxDim = Math.max(width, height);
  if (maxDim <= MAX_QR_DIMENSION) return { data, width, height };
  const factor = Math.ceil(maxDim / MAX_QR_DIMENSION);
  const nw = Math.floor(width / factor);
  const nh = Math.floor(height / factor);
  const out = new Uint8ClampedArray(nw * nh * 4);
  for (let y = 0; y < nh; y++) {
    for (let x = 0; x < nw; x++) {
      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      let n = 0;
      for (let dy = 0; dy < factor; dy++) {
        for (let dx = 0; dx < factor; dx++) {
          const sx = x * factor + dx;
          const sy = y * factor + dy;
          if (sx >= width || sy >= height) continue;
          const o = (sy * width + sx) * 4;
          r += data[o];
          g += data[o + 1];
          b += data[o + 2];
          a += data[o + 3];
          n++;
        }
      }
      const o = (y * nw + x) * 4;
      out[o] = Math.round(r / n);
      out[o + 1] = Math.round(g / n);
      out[o + 2] = Math.round(b / n);
      out[o + 3] = Math.round(a / n);
    }
  }
  return { data: out, width: nw, height: nh };
}

/** Decode any supported image bytes to RGBA, or null. */
export async function decodeImageToRgba(bytes, contentType) {
  try {
    if (contentType === "png") return await decodePngToRgba(bytes);
    if (contentType === "jpeg") return decodeJpegToRgba(bytes);
    return null;
  } catch {
    return null;
  }
}

export async function decodeQrServerSide(bytes, contentType) {
  try {
    const img = await decodeImageToRgba(bytes, contentType);
    if (!img) return null;
    const scaled = downscaleRgba(img.data, img.width, img.height);
    const code = jsQR(scaled.data, scaled.width, scaled.height);
    return code ? code.data : null;
  } catch {
    return null;
  }
}

/** AWS SigV4 signing for one Rekognition DetectText call. */
async function hmacSha256(key, data) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    cryptoKey,
    typeof data === "string" ? new TextEncoder().encode(data) : data,
  );
  return new Uint8Array(sig);
}

function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return hex(new Uint8Array(digest));
}

/** Sign a Rekognition request. Returns the Authorization header value. */
export async function signRekognitionRequest(
  accessKey,
  secretKey,
  region,
  amzDate,
  payloadHash,
  target,
) {
  const host = `rekognition.${region}.amazonaws.com`;
  const canonicalHeaders = `content-type:application/x-amz-json-1.1\nhost:${host}\nx-amz-date:${amzDate}\nx-amz-target:${target}\n`;
  const signedHeaders = "content-type;host;x-amz-date;x-amz-target";
  const canonicalRequest = [
    "POST",
    "/",
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");
  const scope = `${amzDate.slice(0, 8)}/${region}/rekognition/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    scope,
    await sha256Hex(canonicalRequest),
  ].join("\n");
  const enc = new TextEncoder();
  let k = await hmacSha256(enc.encode("AWS4" + secretKey), amzDate.slice(0, 8));
  k = await hmacSha256(k, region);
  k = await hmacSha256(k, "rekognition");
  k = await hmacSha256(k, "aws4_request");
  const signature = hex(await hmacSha256(k, stringToSign));
  return `AWS4-HMAC-SHA256 Credential=${accessKey}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;
}

/**
 * Screenshot OCR via Rekognition DetectText (the bots' MSGSCAN engine).
 * Returns recognised text (LINE detections joined with spaces, mirroring
 * the bots) or null when OCR is unconfigured or fails. Never throws.
 */
export async function ocrImageText(bytes, env, fetchFn) {
  if (!env.AWS_ACCESS_KEY_ID || !env.AWS_SECRET_ACCESS_KEY) return null;
  try {
    const base64 = b64encode(bytes);
    const body = JSON.stringify({ Image: { Bytes: base64 } });
    const now = new Date();
    const amzDate = now
      .toISOString()
      .replace(/[-:]/g, "")
      .replace(/\.\d+Z$/, "Z");
    const payloadHash = await sha256Hex(body);
    const auth = await signRekognitionRequest(
      env.AWS_ACCESS_KEY_ID,
      env.AWS_SECRET_ACCESS_KEY,
      "us-east-1",
      amzDate,
      payloadHash,
      "RekognitionService.DetectText",
    );
    const resp = await fetchFn("https://rekognition.us-east-1.amazonaws.com/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Date": amzDate,
        "X-Amz-Target": "RekognitionService.DetectText",
        Authorization: auth,
      },
      body,
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const lines = (data.TextDetections || [])
      .filter((d) => d.Type === "LINE" && d.DetectedText)
      .map((d) => d.DetectedText);
    return lines.join(" ");
  } catch {
    return null;
  }
}

function b64encode(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** Find the first checkable item in OCR text, URL first, then wallet, then email. */
export function findCheckableInText(text) {
  const t = String(text || "");
  const url = t.match(FIND_URL_RE);
  if (url) return classifyInput(url[0]);
  const wallet = t.match(FIND_WALLET_RE);
  if (wallet) {
    const c = classifyInput(wallet[0]);
    if (c.kind === "wallet") return c;
  }
  const email = t.match(FIND_EMAIL_RE);
  if (email) {
    const c = classifyInput(email[0]);
    if (c.kind === "email") return c;
  }
  return { kind: "unknown" };
}

/* ------------------------------------------------------------------ */
/* HTTP layer.                                                         */
/* ------------------------------------------------------------------ */

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

function bg(ctx, promise) {
  try {
    if (ctx && typeof ctx.waitUntil === "function") {
      ctx.waitUntil(promise.catch(() => {}));
      return;
    }
  } catch {
    /* fall through to await */
  }
  return promise.catch(() => {});
}

function pageResponse(env) {
  const siteKey = env.TURNSTILE_SITE_KEY || "";
  const html = PAGE_HTML.replaceAll("__TURNSTILE_SITE_KEY__", escapeHtml(siteKey));
  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

async function handleCheck(request, env, ctx) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ ok: false, error: "bad-json" }, 400);
  }
  const input = String(body.input || "");
  if (!input.trim()) return jsonResponse({ ok: false, error: "empty" }, 400);
  if (input.length > MAX_INPUT_CHARS) {
    return jsonResponse({ ok: false, error: "too-long" }, 400);
  }
  const ip = clientIp(request);
  const turnstile = await verifyTurnstile(
    env.TURNSTILE_SECRET_KEY,
    body.turnstileToken || "",
    ip,
    fetch,
  );
  if (turnstile.ok === false) {
    return jsonResponse({ ok: false, error: "turnstile-failed" }, 403);
  }
  const now = new Date();
  if (await isRateLimited(env.WEBCHECK_KV, ip, now, false)) {
    return jsonResponse({ ok: false, error: "rate-limited" }, 429);
  }
  const classified = classifyInput(input);
  if (classified.kind === "unknown") {
    return jsonResponse({ ok: false, error: "unclassifiable" }, 400);
  }
  const apiResult = await runCheck(
    classified.kind,
    classified.value,
    env.API_BASE,
    fetch,
  );
  const card = buildCard(classified.kind, classified.value, apiResult, "paste");
  bg(ctx, recordCheck(env.WEBCHECK_KV, classified.kind, card.badgeKey, now));
  return jsonResponse({ ok: true, card });
}

async function handleUpload(request, env, ctx) {
  let form;
  try {
    form = await request.formData();
  } catch {
    return jsonResponse({ ok: false, error: "bad-form" }, 400);
  }
  const file = form.get("file");
  const token = form.get("turnstileToken") || "";
  if (!file || typeof file.arrayBuffer !== "function") {
    return jsonResponse({ ok: false, error: "no-file" }, 400);
  }
  const ip = clientIp(request);
  const turnstile = await verifyTurnstile(env.TURNSTILE_SECRET_KEY, token, ip, fetch);
  if (turnstile.ok === false) {
    return jsonResponse({ ok: false, error: "turnstile-failed" }, 403);
  }
  const now = new Date();
  if (await isRateLimited(env.WEBCHECK_KV, ip, now, true)) {
    return jsonResponse({ ok: false, error: "rate-limited" }, 429);
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  const validation = validateUpload(bytes, file.name);
  if (!validation.ok) {
    return jsonResponse({ ok: false, error: validation.reason }, 400);
  }
  const qrText = await decodeQrServerSide(bytes, validation.type);
  if (qrText) {
    const classified = classifyInput(qrText);
    if (classified.kind !== "unknown") {
      const apiResult = await runCheck(
        classified.kind,
        classified.value,
        env.API_BASE,
        fetch,
      );
      const card = buildCard(classified.kind, classified.value, apiResult, "upload-qr");
      bg(ctx, recordCheck(env.WEBCHECK_KV, "upload", card.badgeKey, now));
      return jsonResponse({ ok: true, card });
    }
  }
  const ocrText = await ocrImageText(bytes, env, fetch);
  if (ocrText == null) {
    const card = uncheckedCard(
      "link",
      validation.fileName,
      "Image text reading is not configured on this page yet. Paste the link, wallet, or email directly instead.",
      "upload-ocr",
    );
    bg(ctx, recordCheck(env.WEBCHECK_KV, "upload", "unchecked", now));
    return jsonResponse({ ok: true, card });
  }
  const found = findCheckableInText(ocrText);
  if (found.kind === "unknown") {
    const card = uncheckedCard(
      "link",
      validation.fileName,
      "No link, wallet, or email found in the image text.",
      "upload-ocr",
    );
    bg(ctx, recordCheck(env.WEBCHECK_KV, "upload", "unchecked", now));
    return jsonResponse({ ok: true, card });
  }
  const apiResult = await runCheck(found.kind, found.value, env.API_BASE, fetch);
  const card = buildCard(found.kind, found.value, apiResult, "upload-ocr");
  bg(ctx, recordCheck(env.WEBCHECK_KV, "upload", card.badgeKey, now));
  return jsonResponse({ ok: true, card });
}

async function handleGo(request, env, ctx) {
  const to = new URL(request.url).searchParams.get("to");
  const link = GO_LINKS[to];
  if (!link) return jsonResponse({ ok: false, error: "unknown-destination" }, 400);
  bg(ctx, recordConversion(env.WEBCHECK_KV, to, new Date()));
  return Response.redirect(link.deep, 302);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    if (path === "/" ) {
      return Response.redirect("/check", 302);
    }
    if (path === "/check" && request.method === "GET") {
      return pageResponse(env);
    }
    if (path === "/check/health" && request.method === "GET") {
      return jsonResponse({
        ok: true,
        worker: "relayshield-webcheck",
        kv: Boolean(env.WEBCHECK_KV),
        turnstile: Boolean(env.TURNSTILE_SECRET_KEY),
        ocr: Boolean(env.AWS_ACCESS_KEY_ID && env.AWS_SECRET_ACCESS_KEY),
      });
    }
    if (path === "/check/metrics" && request.method === "GET") {
      return jsonResponse(await readMetrics(env.WEBCHECK_KV, new Date()));
    }
    if (path === "/check/go" && request.method === "GET") {
      return handleGo(request, env, ctx);
    }
    if (path === "/check/api/check" && request.method === "POST") {
      return handleCheck(request, env, ctx);
    }
    if (path === "/check/api/upload" && request.method === "POST") {
      return handleUpload(request, env, ctx);
    }
    return jsonResponse({ ok: false, error: "not-found" }, 404);
  },
};

/* ------------------------------------------------------------------ */
/* Page template. Single-file page, no framework. The inline script    */
/* uses string concatenation only (no template literals, no backticks) */
/* so it can live inside this Worker's template literal. Card text is  */
/* inserted escaped, never raw: targets and reasons are user input.    */
/* ------------------------------------------------------------------ */

const PAGE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield free check</title>
<script src="https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js"></script>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<style>
body { font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; padding: 24px 16px; background: #141414; color: #eaeaea; }
#matrix { position: fixed; inset: 0; width: 100%; height: 100%; z-index: 0; opacity: 0.13; pointer-events: none; }
.scanlines { position: fixed; inset: 0; z-index: 60; pointer-events: none; opacity: 0.35; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.28) 0 1px, transparent 1px 3px); }
body > :not(#matrix):not(.scanlines) { position: relative; z-index: 1; }
h1 { font-size: 26px; margin-bottom: 4px; }
.sub { color: #a6a6a6; margin-top: 0; }
input[type=text] { width: 100%; padding: 10px; font-size: 16px; box-sizing: border-box; background: #1f1f1f; color: #eaeaea; border: 1px solid #7c3aed; border-radius: 6px; }
button { padding: 10px 18px; font-size: 16px; cursor: pointer; margin-top: 10px; background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff; border: none; border-radius: 6px; }
.card { border: 2px solid #7c3aed; border-radius: 8px; padding: 16px; margin-top: 20px; background: #1f1f1f; }
.badge-threat { color: #ff5252; }
.badge-suspicious { color: #ffb020; }
.badge-clean { color: #00ff41; }
.badge-unchecked { color: #a6a6a6; }
.botlinks a { display: inline-block; margin: 6px 8px 0 0; padding: 8px 12px; background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff; text-decoration: none; border-radius: 6px; }
.note { color: #a6a6a6; font-size: 13px; margin-top: 24px; }
.error { color: #ff5252; margin-top: 12px; }
a { color: #00ff41; }
</style>
</head>
<body>
<canvas id="matrix"></canvas>
<div class="scanlines"></div>
<h1>RelayShield free check</h1>
<p class="sub">Paste a link, wallet address, or email address. Or upload a QR code or screenshot. No signup, no account.</p>
<label for="checkInput">Link, wallet, or email</label><br>
<input type="text" id="checkInput" placeholder="https://example.com/page, 0x..., or name@example.com" autocomplete="off"><br>
<div id="turnstileWrap" style="margin-top:10px"></div>
<button id="checkBtn" type="button">Check it</button>
<p style="margin-top:20px">Or upload an image:</p>
<input type="file" id="fileInput" accept="image/png,image/jpeg,image/gif,image/webp">
<button id="uploadBtn" type="button">Check image</button>
<div id="error" class="error"></div>
<div id="result"></div>
<p class="note">Checked, not stored. This page keeps counts only: how many checks ran and how many visitors continued to the bots. It never keeps what you pasted or uploaded.</p>
<script>
var SITE_KEY = "__TURNSTILE_SITE_KEY__";
var turnstileWidgetId = null;
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function showError(msg) {
  document.getElementById("error").textContent = msg;
}
function badgeClass(key) {
  if (key === "threat") return "badge-threat";
  if (key === "suspicious") return "badge-suspicious";
  if (key === "clean") return "badge-clean";
  return "badge-unchecked";
}
function renderCard(card) {
  var why = "";
  for (var i = 0; i < card.why.length; i++) {
    why += "<p>Why: " + esc(card.why[i]) + "</p>";
  }
  var bots = "";
  for (var j = 0; j < card.botLinks.length; j++) {
    var b = card.botLinks[j];
    bots += '<a href="' + esc(b.href) + '">' + esc(b.label) + "</a>";
  }
  var html = '<div class="card">'
    + "<p><strong>" + esc(card.header) + "</strong></p>"
    + '<p class="' + badgeClass(card.badgeKey) + '"><strong>' + esc(card.badge) + "</strong></p>"
    + "<p>Target: " + esc(card.target) + "</p>"
    + why
    + "<p>" + esc(card.action) + "</p>"
    + "<p>" + esc(card.footer) + "</p>"
    + "<p>" + esc(card.forward) + "</p>"
    + '<div class="botlinks">' + bots + "</div>"
    + "</div>";
  document.getElementById("result").innerHTML = html;
}
function turnstileToken() {
  try {
    if (window.turnstile && turnstileWidgetId !== null) {
      return window.turnstile.getResponse(turnstileWidgetId) || "";
    }
  } catch (e) {}
  return "";
}
function resetTurnstile() {
  try {
    if (window.turnstile && turnstileWidgetId !== null) {
      window.turnstile.reset(turnstileWidgetId);
    }
  } catch (e) {}
}
async function runCheck(input) {
  showError("");
  document.getElementById("result").innerHTML = "<p>Checking...</p>";
  var resp = await fetch("/check/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: input, turnstileToken: turnstileToken() }),
  });
  var data = await resp.json();
  resetTurnstile();
  if (!resp.ok || !data.ok) {
    document.getElementById("result").innerHTML = "";
    if (data.error === "unclassifiable") {
      showError("Could not tell what that is. Paste a link, wallet address, or email address.");
    } else if (data.error === "rate-limited") {
      showError("Too many checks from this address just now. Wait a minute and try again.");
    } else if (data.error === "turnstile-failed") {
      showError("Verification failed. Reload the page and try again.");
    } else {
      showError("Something went wrong. Try again shortly.");
    }
    return;
  }
  renderCard(data.card);
}
async function runUpload(file) {
  showError("");
  document.getElementById("result").innerHTML = "<p>Checking image...</p>";
  var form = new FormData();
  form.append("file", file);
  form.append("turnstileToken", turnstileToken());
  var resp = await fetch("/check/api/upload", { method: "POST", body: form });
  var data = await resp.json();
  resetTurnstile();
  if (!resp.ok || !data.ok) {
    document.getElementById("result").innerHTML = "";
    if (data.error === "too-large") {
      showError("That image is over 5 MB. Try a smaller screenshot.");
    } else if (data.error === "not-an-image") {
      showError("That file is not a PNG, JPEG, GIF, or WebP image.");
    } else if (data.error === "rate-limited") {
      showError("Too many uploads from this address just now. Wait a minute and try again.");
    } else {
      showError("Something went wrong. Try again shortly.");
    }
    return;
  }
  renderCard(data.card);
}
function decodeQrInBrowser(file) {
  return new Promise(function (resolve) {
    if (typeof jsQR === "undefined") { resolve(null); return; }
    var img = new Image();
    var url = URL.createObjectURL(file);
    img.onload = function () {
      try {
        var canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        var ctx2d = canvas.getContext("2d", { willReadFrequently: true });
        ctx2d.drawImage(img, 0, 0);
        var imageData = ctx2d.getImageData(0, 0, canvas.width, canvas.height);
        var code = jsQR(imageData.data, imageData.width, imageData.height);
        resolve(code && code.data ? code.data : null);
      } catch (e) {
        resolve(null);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = function () { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}
document.getElementById("checkBtn").addEventListener("click", function () {
  var input = document.getElementById("checkInput").value;
  if (!input.trim()) { showError("Paste a link, wallet address, or email address first."); return; }
  runCheck(input);
});
document.getElementById("checkInput").addEventListener("keydown", function (e) {
  if (e.key === "Enter") { document.getElementById("checkBtn").click(); }
});
document.getElementById("uploadBtn").addEventListener("click", async function () {
  var files = document.getElementById("fileInput").files;
  if (!files || files.length === 0) { showError("Choose an image file first."); return; }
  var file = files[0];
  var decoded = await decodeQrInBrowser(file);
  if (decoded) {
    document.getElementById("checkInput").value = decoded;
    runCheck(decoded);
    return;
  }
  runUpload(file);
});
if (SITE_KEY) {
  var wrap = document.getElementById("turnstileWrap");
  var div = document.createElement("div");
  div.setAttribute("data-sitekey", SITE_KEY);
  wrap.appendChild(div);
  var poll = setInterval(function () {
    try {
      if (window.turnstile) {
        turnstileWidgetId = window.turnstile.render(div);
        clearInterval(poll);
      }
    } catch (e) {}
  }, 500);
}
</script>
<script>
/* Matrix code rain, same treatment as the relayshield.net landing page.
   Decorative only and failure isolated: a missing canvas or drawing
   context stops this block and never touches the check flow above. */
(function () {
  var canvas = document.getElementById('matrix');
  if (!canvas) { return; }
  var ctx = null;
  try { ctx = canvas.getContext('2d'); } catch (e) { ctx = null; }
  if (!ctx) { return; }
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var chars = 'アイウエオカキクケコサシスセソタチツテト0123456789ABCDEF$#@%&';
  var fontSize = 18, columns = 0, drops = [];
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    columns = Math.floor(canvas.width / fontSize);
    drops = [];
    for (var i = 0; i < columns; i++) { drops[i] = Math.random() * -100; }
  }
  function draw() {
    ctx.fillStyle = 'rgba(20,20,20,0.08)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#00ff41';
    ctx.font = fontSize + 'px monospace';
    for (var i = 0; i < columns; i++) {
      var ch = chars.charAt(Math.floor(Math.random() * chars.length));
      ctx.fillText(ch, i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) { drops[i] = 0; }
      drops[i]++;
    }
  }
  window.addEventListener('resize', resize);
  resize();
  if (!reduce) { setInterval(draw, 66); }
})();
</script>
</body>
</html>
`;
