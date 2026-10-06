/* RelayShield Shopify App : Cloudflare Worker (P0: order screening)
 *
 * Flow: orders/create webhook (HMAC-verified) -> extract buyer email + store
 * domain -> POST keyless /v1/composite-check -> map verdict to Admin API tags
 * and a timeline note -> embedded Polaris dashboard.
 *
 * Hard rules enforced here:
 *  - never auto-cancel or auto-refund an order (tag and note only)
 *  - never call an order "safe" (best case: "no known red flags", with caveats)
 *  - never persist raw buyer PII (emails are SHA-256 hashed at rest)
 *  - fail open: any screening error means no tags, never a block
 */

const API_VERSION = "2026-07";
const RS_COMPOSITE_URL =
  "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/composite-check";
const OAUTH_SCOPES = "read_orders,write_orders";
const SCREEN_TIMEOUT_MS = 15000;
const SCREENINGS_CAP = 100;
/* Buyer screening records (email stored only as SHA-256 hash) expire after
 * 90 days so personal data is never kept longer than needed. */
const SCREENINGS_TTL_SECONDS = 90 * 24 * 60 * 60;

/* ------------------------------------------------------------------ */
/* crypto helpers (Web Crypto; works in Workers and in Node >= 18)    */
/* ------------------------------------------------------------------ */

const te = new TextEncoder();

async function hmacSha256(secret, data) {
  const key = await crypto.subtle.importKey(
    "raw", te.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, te.encode(data)));
}

function b64encode(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function hmacSha256Hex(secret, data) {
  const mac = await hmacSha256(secret, data);
  return [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function verifyShopifyQueryHmac(secret, params, providedHex) {
  if (!secret || !providedHex) return false;
  return timingSafeEqual(await hmacSha256Hex(secret, params), providedHex.trim());
}

export async function verifyShopifyHmac(secret, rawBody, providedB64) {
  if (!secret || !providedB64) return false;
  const mac = await hmacSha256(secret, rawBody);
  return timingSafeEqual(b64encode(mac), providedB64.trim());
}

export async function sha256Hex(data) {
  const digest = await crypto.subtle.digest("SHA-256", te.encode(data));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function hashBuyerEmail(email) {
  return sha256Hex(String(email || "").trim().toLowerCase());
}

export function isValidShopDomain(shop) {
  return /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(String(shop || "").toLowerCase());
}

function randomHex(n) {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

/* ------------------------------------------------------------------ */
/* KV helpers (env.RS_KV is a Workers KV namespace)                   */
/* ------------------------------------------------------------------ */

async function kvGet(env, key) {
  try {
    const raw = await env.RS_KV.get(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

async function kvPut(env, key, value, ttlSeconds) {
  const opts = ttlSeconds ? { expirationTtl: ttlSeconds } : undefined;
  await env.RS_KV.put(key, JSON.stringify(value), opts);
}

async function kvDelete(env, key) {
  try { await env.RS_KV.delete(key); } catch { /* best effort */ }
}

const shopKey = (shop) => `shop:${shop}`;
const screeningsKey = (shop) => `screenings:${shop}`;
const oauthStateKey = (state) => `oauth_state:${state}`;

/* ------------------------------------------------------------------ */
/* per-shop RelayShield key provisioning (design; P0 = keyless)       */
/* ------------------------------------------------------------------ */

export async function getShopRecord(env, shop) {
  return kvGet(env, shopKey(shop));
}

/* P0: every shop screens on the keyless tier with a channel marker so
 * RelayShield can measure the Shopify surface. Paid upgrade path: call the
 * existing partner-key provisioning flow, store the returned key on the
 * shop record, and flip rs_key_mode to "keyed". screenOrder() then sends
 * it as X-RS-API-KEY. The mint call itself is Andrew's server-side step;
 * this function documents the exact handoff. */
export async function provisionShopKey(env, shop) {
  const rec = (await getShopRecord(env, shop)) || {};
  if (rec.rs_api_key) return { mode: "keyed", key: rec.rs_api_key };
  // Keyless P0. To upgrade a shop: POST the partner-key provisioning
  // endpoint (same flow as relayshield_developer_signup.py) with
  // {shop, channel: "shopify-app"}, store the returned key as
  // rec.rs_api_key, set rec.rs_key_mode = "keyed", and save the record.
  return { mode: "keyless", key: null };
}

/* ------------------------------------------------------------------ */
/* RelayShield screening                                               */
/* ------------------------------------------------------------------ */

export function extractOrderSignals(order, shop) {
  const email = order.email || order.contact_email || "";
  return {
    email: { from_address: email },
    url: `https://${shop}`,
    source: "shopify-app",
  };
}

/* DEV-ONLY FIXTURE. Returns a canned risk verdict for synthetic test
 * addresses, used to produce tagged orders + timeline notes for App Store
 * screenshots. Cannot leak to production: requires BOTH the dev shop domain
 * AND an @relayshield.net fixture address. Real shops and real customers
 * can never satisfy both conditions. */
const FIXTURE_SHOP = "relayshield-test.myshopify.com";
const FIXTURE_DOMAIN = "@relayshield.net";
const FIXTURE_PREFIX = "fixture-";
export function fixtureVerdict(signals) {
  const email = String(signals?.email?.from_address || "").toLowerCase();
  const shop = String(signals?.url || "").replace(/^https?:\/\//, "").split("/")[0].toLowerCase();
  if (shop !== FIXTURE_SHOP || !email.endsWith(FIXTURE_DOMAIN)) return null;
  if (!email.split("@")[0].startsWith(FIXTURE_PREFIX)) return null;
  const level = email.startsWith("fixture-high-") ? "high" : "medium";
  return {
    level,
    score: level === "high" ? 85 : 55,
    signals: [{ reasons: [`Fixture: synthetic ${level}-risk address for App Store screenshots`] }],
  };
}

export async function screenOrder(signals, shopKeyInfo) {
  const fixture = fixtureVerdict(signals);
  if (fixture) return fixture;
  const headers = { "Content-Type": "application/json" };
  if (shopKeyInfo && shopKeyInfo.mode === "keyed" && shopKeyInfo.key) {
    headers["X-RS-API-KEY"] = shopKeyInfo.key;
  }
  const resp = await fetch(RS_COMPOSITE_URL, {
    method: "POST",
    headers,
    body: JSON.stringify(signals),
    signal: AbortSignal.timeout(SCREEN_TIMEOUT_MS),
  });
  const body = await resp.json();
  if (!resp.ok || !body.ok) throw new Error("composite-check failed");
  return body.data;
}

/* Verdict -> merchant-visible actions. Unknown never tags. Nothing here
 * cancels, refunds, or holds an order; that stays a merchant decision. */
export function verdictActions(level) {
  if (level === "high") return { tags: ["relayshield-high-risk"], note: true };
  if (level === "medium") return { tags: ["relayshield-review"], note: true };
  return { tags: [], note: false };
}

export function buildTimelineNote(orderName, level, score, reasons) {
  const lines = [
    `RelayShield screened order ${orderName}.`,
    `Composite risk score: ${score}/100 (${level}).`,
  ];
  const shown = (reasons || []).filter(Boolean).slice(0, 5);
  if (shown.length) lines.push(`Signals: ${shown.join("; ")}.`);
  lines.push(
    "A clean result means no known red flags were found, not proof of safety. " +
    "Nothing was changed on this order automatically; review before fulfilling if anything looks off."
  );
  return lines.join(" ");
}

/* ------------------------------------------------------------------ */
/* Shopify Admin API                                                   */
/* ------------------------------------------------------------------ */

function adminBase(shop) {
  return `https://${shop}/admin/api/${API_VERSION}`;
}

export async function adminApi(shop, token, path, method = "GET", body) {
  const resp = await fetch(adminBase(shop) + path, {
    method,
    headers: {
      "X-Shopify-Access-Token": token,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Admin API ${method} ${path} -> ${resp.status}: ${text.slice(0, 200)}`);
  }
  return resp.json();
}

export async function applyVerdictToOrder(shop, token, order, level, score, reasons) {
  const actions = verdictActions(level);
  if (!actions.tags.length && !actions.note) return { skipped: true };
  const results = {};
  if (actions.tags.length) {
    const current = await adminApi(shop, token, `/orders/${order.id}.json`);
    const existing = String(current.order.tags || "")
      .split(",").map((t) => t.trim()).filter(Boolean);
    const merged = [...new Set([...existing, ...actions.tags])];
    await adminApi(shop, token, `/orders/${order.id}.json`, "PUT", {
      order: { id: order.id, tags: merged.join(", ") },
    });
    results.tags = merged;
  }
  if (actions.note) {
    await adminApi(shop, token, `/orders/${order.id}/events.json`, "POST", {
      event: { message: buildTimelineNote(order.name, level, score, reasons) },
    });
    results.note = true;
  }
  return results;
}

async function recordScreening(env, shop, record) {
  const list = (await kvGet(env, screeningsKey(shop))) || [];
  list.unshift(record);
  await kvPut(env, screeningsKey(shop), list.slice(0, SCREENINGS_CAP), SCREENINGS_TTL_SECONDS);
}

/* ------------------------------------------------------------------ */
/* route handlers                                                      */
/* ------------------------------------------------------------------ */

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function handleInstall(request, env, url) {
  const shop = url.searchParams.get("shop") || "";
  if (!isValidShopDomain(shop)) return new Response("Invalid shop parameter", { status: 400 });
  const state = randomHex(16);
  await kvPut(env, oauthStateKey(state), { shop }, 600);
  const redirectUri = `${url.origin}/auth/callback`;
  const authorize = `https://${shop}/admin/oauth/authorize?` + new URLSearchParams({
    client_id: env.SHOPIFY_API_KEY,
    scope: OAUTH_SCOPES,
    redirect_uri: redirectUri,
    state,
  });
  return Response.redirect(authorize.toString(), 302);
}

async function handleCallback(request, env, url) {
  const shop = url.searchParams.get("shop") || "";
  const code = url.searchParams.get("code") || "";
  const state = url.searchParams.get("state") || "";
  const hmac = url.searchParams.get("hmac") || "";
  if (!isValidShopDomain(shop) || !code || !state) {
    return new Response("Invalid OAuth callback", { status: 400 });
  }
  const params = [...url.searchParams.entries()]
    .filter(([k]) => k !== "hmac" && k !== "signature")
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([k, v]) => `${k}=${v}`)
    .join("&");
  if (!(await verifyShopifyQueryHmac(env.SHOPIFY_API_SECRET, params, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  const stored = await kvGet(env, oauthStateKey(state));
  if (!stored || stored.shop !== shop) return new Response("Invalid state", { status: 401 });
  await kvDelete(env, oauthStateKey(state));

  // Shopify mandates expiring offline access tokens (since 2026-04):
  // the exchange must send expiring=1 and returns a short-lived access
  // token plus a rotating refresh token. Non-expiring tokens 403.
  const tokenResp = await fetch(`https://${shop}/admin/oauth/access_token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.SHOPIFY_API_KEY,
      client_secret: env.SHOPIFY_API_SECRET,
      code,
      expiring: "1",
    }),
  });
  if (!tokenResp.ok) return new Response("Token exchange failed", { status: 502 });
  const tokenData = await tokenResp.json();
  if (!tokenData.access_token) return new Response("Token exchange failed", { status: 502 });

  await kvPut(env, shopKey(shop), {
    access_token: tokenData.access_token,
    refresh_token: tokenData.refresh_token || null,
    token_expires_at: Date.now() + (tokenData.expires_in || 3600) * 1000,
    rs_key_mode: "keyless",
    installed_at: new Date().toISOString(),
  });
  await registerWebhooks(url.origin, shop, tokenData.access_token);
  return Response.redirect(`https://${shop}/admin/apps/${env.SHOPIFY_API_KEY}`, 302);
}

/* orders/create is the only topic registered via the Admin API.
 * The three GDPR compliance webhooks (customers/data_request,
 * customers/redact, shop/redact) cannot be created via the REST API
 * (404); they are configured in the dashboard under Privacy compliance.
 * Subscribing to orders/create requires protected customer data access
 * approval; until granted, registration logs the 403 and continues. */
const WEBHOOK_TOPICS = [
  ["orders/create", "/webhooks/orders-create"],
];

async function registerWebhooks(appOrigin, shop, token) {
  for (const [topic, path] of WEBHOOK_TOPICS) {
    try {
      await adminApi(shop, token, "/webhooks.json", "POST", {
        webhook: { topic, address: appOrigin + path, format: "json" },
      });
    } catch (e) {
      console.log(`webhook register failed topic=${topic}: ${e.message}`);
    }
  }
}

/* Expiring offline tokens: the access token lives ~1h and must be
 * refreshed before expiry. Shopify rotates the refresh token on every
 * use and invalidates the old one immediately, so the rotated pair is
 * persisted before it is used. */
const TOKEN_REFRESH_BUFFER_MS = 5 * 60 * 1000;

export async function refreshShopToken(env, shop, rec) {
  const resp = await fetch(`https://${shop}/admin/oauth/access_token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: env.SHOPIFY_API_KEY,
      client_secret: env.SHOPIFY_API_SECRET,
      refresh_token: rec.refresh_token,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`token refresh -> ${resp.status}: ${text.slice(0, 120)}`);
  }
  const data = await resp.json();
  if (!data.access_token) throw new Error("token refresh returned no access token");
  const updated = {
    ...rec,
    access_token: data.access_token,
    refresh_token: data.refresh_token || rec.refresh_token,
    token_expires_at: Date.now() + (data.expires_in || 3600) * 1000,
  };
  await kvPut(env, shopKey(shop), updated);
  return updated;
}

export async function getFreshAccessToken(env, shop) {
  const rec = await getShopRecord(env, shop);
  if (!rec || !rec.access_token) throw new Error("Shop not installed");
  const needsRefresh =
    rec.refresh_token &&
    rec.token_expires_at &&
    Date.now() > rec.token_expires_at - TOKEN_REFRESH_BUFFER_MS;
  if (needsRefresh) return (await refreshShopToken(env, shop, rec)).access_token;
  return rec.access_token;
}

async function readRawBody(request) {
  return request.text();
}

async function handleOrdersCreate(request, env) {
  const raw = await readRawBody(request);
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  const shop = request.headers.get("X-Shopify-Shop-Domain") || "";
  if (!isValidShopDomain(shop)) return new Response("Bad shop header", { status: 400 });
  const rec = await getShopRecord(env, shop);
  if (!rec || !rec.access_token) return new Response("Shop not installed", { status: 401 });

  let order;
  try { order = JSON.parse(raw); } catch { return new Response("Bad JSON", { status: 400 }); }

  // Idempotency: skip if we already screened this order (webhook redelivery).
  const existing = (await kvGet(env, screeningsKey(shop))) || [];
  if (existing.some((s) => s.order_id === order.id)) {
    return json({ ok: true, deduped: true });
  }

  const signals = extractOrderSignals(order, shop);
  let verdict;
  try {
    const keyInfo = await provisionShopKey(env, shop);
    verdict = await screenOrder(signals, keyInfo);
  } catch (e) {
    console.log(`screening failed order=${order.id}: ${e.message}`);
    return json({ ok: true, screened: false, error: "screening unavailable" });
  }

  const level = ["high", "medium", "unknown"].includes(verdict.level) ? verdict.level : "unknown";
  const reasons = (verdict.signals || []).flatMap((s) => s.reasons || []);
  let token = rec.access_token;
  try {
    token = await getFreshAccessToken(env, shop);
  } catch (e) {
    console.log(`token refresh failed order=${order.id}: ${e.message}`);
  }
  try {
    await applyVerdictToOrder(shop, token, order, level, verdict.score, reasons);
  } catch (e) {
    console.log(`admin action failed order=${order.id}: ${e.message}`);
  }
  await recordScreening(env, shop, {
    order_id: order.id,
    order_name: order.name,
    email_hash: await hashBuyerEmail(signals.email.from_address),
    level,
    score: verdict.score,
    top_reason: reasons[0] || null,
    screened_at: new Date().toISOString(),
  });
  return json({ ok: true, screened: true, level, score: verdict.score });
}

/* GDPR: we store only hashed buyer emails plus screening metadata keyed by
 * shop. Data requests return that metadata; redaction deletes it. */
async function handleGdpr(request, env, kind) {
  const raw = await readRawBody(request);
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  let payload = {};
  try { payload = JSON.parse(raw); } catch { /* ignore */ }
  const shop = payload.shop_domain || request.headers.get("X-Shopify-Shop-Domain") || "";
  if (kind === "shop-redact" && isValidShopDomain(shop)) {
    await kvDelete(env, shopKey(shop));
    await kvDelete(env, screeningsKey(shop));
  }
  if ((kind === "customers-redact" || kind === "customers-data-request") && payload.customer && payload.customer.email) {
    const emailHash = await hashBuyerEmail(payload.customer.email);
    const list = (await kvGet(env, screeningsKey(shop))) || [];
    const mine = list.filter((s) => s.email_hash === emailHash);
    if (kind === "customers-redact") {
      await kvPut(env, screeningsKey(shop), list.filter((s) => s.email_hash !== emailHash));
    }
    if (kind === "customers-data-request") {
      return json({ ok: true, records: mine });
    }
  }
  return json({ ok: true });
}

/* ------------------------------------------------------------------ */
/* embedded dashboard (Polaris)                                        */
/* ------------------------------------------------------------------ */

function base64UrlDecode(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

export async function verifySessionToken(env, bearer) {
  // App Bridge session token: JWT HS256 signed with the API secret.
  try {
    const parts = String(bearer || "").split(".");
    if (parts.length !== 3) return null;
    const signingInput = `${parts[0]}.${parts[1]}`;
    const sig = base64UrlDecode(parts[2]);
    const expected = await hmacSha256(env.SHOPIFY_API_SECRET, signingInput);
    if (sig.length !== expected.length) return null;
    let d = 0;
    for (let i = 0; i < sig.length; i++) d |= sig[i] ^ expected[i];
    if (d !== 0) return null;
    const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));
    const now = Math.floor(Date.now() / 1000);
    if (!payload.exp || payload.exp < now) return null;
    const dest = String(payload.dest || "");
    const m = dest.match(/^https:\/\/([a-z0-9][a-z0-9-]*\.myshopify\.com)/);
    if (!m || !isValidShopDomain(m[1])) return null;
    return m[1];
  } catch {
    return null;
  }
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderDashboard(shop, screenings, apiKey, host) {
  const counts = { high: 0, medium: 0, unknown: 0 };
  for (const s of screenings) if (counts[s.level] !== undefined) counts[s.level]++;
  const rows = screenings.map((s) => `
      <tr>
        <td>${esc(s.order_name)}</td>
        <td>${esc(s.screened_at)}</td>
        <td><span class="badge badge-${esc(s.level)}">${esc(s.level)}</span></td>
        <td>${esc(s.score)}/100</td>
        <td>${esc(s.top_reason || "no flags found")}</td>
      </tr>`).join("");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield Order Screening</title>
<script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
<script>
  (function() {
    try {
      // App Bridge 4.x: window.shopify.idToken() returns a session token promise
      if (window.shopify && typeof window.shopify.idToken === "function") {
        window.shopify.idToken().then(function(token) {
          console.log("[RelayShield] App Bridge session token acquired");
          // Prove session-token auth: call backend with token in Authorization header
          fetch("/api/session", {
            headers: { "Authorization": "Bearer " + token },
          }).then(function(r) {
            console.log("[RelayShield] session auth check:", r.status);
          }).catch(function(e) {
            console.log("[RelayShield] session auth call failed:", e && e.message);
          });
        }).catch(function(e) {
          console.log("[RelayShield] session token unavailable:", e && e.message);
        });
      } else {
        console.log("[RelayShield] App Bridge not ready");
      }
    } catch (e) {
      console.log("[RelayShield] App Bridge init skipped:", e && e.message);
    }
  })();
</script>
<link rel="stylesheet" href="https://unpkg.com/@shopify/polaris@12/build/esm/styles.css">
<style>
  body { padding: 24px; background: #f6f6f7; }
  .wrap { max-width: 1100px; margin: 0 auto; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .badge-high { background: #fed3d1; color: #8c1d18; }
  .badge-medium { background: #ffebc7; color: #7a4a00; }
  .badge-unknown { background: #e4e5e7; color: #4d4d4f; }
  .cards { display: flex; gap: 16px; margin: 16px 0; }
  .card { background: #fff; border-radius: 8px; padding: 16px 20px; flex: 1; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
  .card .n { font-size: 28px; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
  th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid #eee; font-size: 14px; }
  .note { color: #5c5f62; font-size: 13px; margin-top: 16px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>RelayShield Order Screening</h1>
  <p>Screening orders for <strong>${esc(shop)}</strong> against the RelayShield threat-intelligence corpus.</p>
  <div class="cards">
    <div class="card"><div class="n">${counts.high}</div><div>High risk (tagged relayshield-high-risk)</div></div>
    <div class="card"><div class="n">${counts.medium}</div><div>Needs review (tagged relayshield-review)</div></div>
    <div class="card"><div class="n">${counts.unknown}</div><div>No flags found (no tag)</div></div>
  </div>
  <table>
    <thead><tr><th>Order</th><th>Screened</th><th>Verdict</th><th>Score</th><th>Top signal</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="5">No orders screened yet.</td></tr>'}</tbody>
  </table>
  <p class="note">A result of "no flags found" means nothing is known against the order right now, not proof of safety. RelayShield never blocks, cancels, or refunds orders; high-risk orders are tagged for your review before fulfillment.</p>
</div>
</body>
</html>`;
}

async function handleDashboard(request, env) {
  const url = new URL(request.url);
  const auth = request.headers.get("Authorization") || "";
  const bearer = auth.startsWith("Bearer ")
    ? auth.slice(7)
    : url.searchParams.get("id_token") || "";
  const shop = await verifySessionToken(env, bearer);
  if (!shop) return new Response("Unauthorized", { status: 401 });
  const screenings = (await kvGet(env, screeningsKey(shop))) || [];
  const host = url.searchParams.get("host") || "";
  return new Response(renderDashboard(shop, screenings, env.SHOPIFY_API_KEY, host), {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

/* ------------------------------------------------------------------ */
/* router                                                              */
/* ------------------------------------------------------------------ */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/auth" && request.method === "GET") {
        return handleInstall(request, env, url);
      }
      if (url.pathname === "/auth/callback" && request.method === "GET") {
        return handleCallback(request, env, url);
      }
      if (url.pathname === "/webhooks/orders-create" && request.method === "POST") {
        return handleOrdersCreate(request, env);
      }
      if (url.pathname === "/webhooks/gdpr" && request.method === "POST") {
        const topic = request.headers.get("X-Shopify-Topic") || "";
        const kind =
          topic === "customers/data_request"
            ? "customers-data-request"
            : topic === "customers/redact"
              ? "customers-redact"
              : topic === "shop/redact"
                ? "shop-redact"
                : "";
        if (!kind) return new Response("Unknown topic", { status: 400 });
        return handleGdpr(request, env, kind);
      }
      if ((url.pathname === "/webhooks/gdpr/customers-data-request" || url.pathname === "/webhooks/gdpr/customers/data-request") && request.method === "POST") {
        return handleGdpr(request, env, "customers-data-request");
      }
      if ((url.pathname === "/webhooks/gdpr/customers-redact" || url.pathname === "/webhooks/gdpr/customers/redact") && request.method === "POST") {
        return handleGdpr(request, env, "customers-redact");
      }
      if ((url.pathname === "/webhooks/gdpr/shop-redact" || url.pathname === "/webhooks/gdpr/shop/redact") && request.method === "POST") {
        return handleGdpr(request, env, "shop-redact");
      }
      if (url.pathname === "/" && request.method === "GET") {
        return handleDashboard(request, env);
      }
      if (url.pathname === "/api/session" && request.method === "GET") {
        const auth = request.headers.get("Authorization") || "";
        const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
        const shop = await verifySessionToken(env, bearer);
        if (!shop) return new Response(JSON.stringify({ ok: false }), {
          status: 401, headers: { "Content-Type": "application/json" },
        });
        return new Response(JSON.stringify({ ok: true, shop }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/healthz") return new Response("ok");
      return new Response("Not found", { status: 404 });
    } catch (e) {
      console.log(`unhandled: ${e.message}`);
      return new Response("Internal error", { status: 500 });
    }
  },
};
