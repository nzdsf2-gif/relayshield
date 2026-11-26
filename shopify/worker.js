/* RelayShield Shopify App : Cloudflare Worker (P1: hold-before-ship enhancements, 2026-11-26)
 *
 * Flow: orders/create webhook (HMAC-verified) -> extract buyer email + store
 * domain -> POST keyless /v1/composite-check -> map verdict to Admin API tags
 * and a timeline note -> embedded Polaris dashboard.
 *
 * Hard rules enforced here:
 *  - never auto-cancel or auto-refund an order (a hold is a fulfillment hold for merchant review, never a cancel or refund)
 *  - never call an order "safe" (best case: "no known red flags", with caveats)
 *  - never persist raw buyer PII (emails are SHA-256 hashed at rest)
 *  - fail open: any screening error means no tags, never a block
 *
 * P1 enhancements (2026-11-26, RS-ENH-2026-11-26-V2):
 *  - 0-100 score with merchant thresholds (default hold >= 70, flag 40-69)
 *  - hold-before-ship via fulfillmentOrderHold (HIGH_RISK_OF_FRAUD), $49 Prevention tier only
 *  - Shopify Flow trigger (flowTriggerReceive) + Flow action endpoint (/flow/hold-order)
 *  - custom rules / blocklists / allowlist, buyer-identifying values stored hashed
 *  - device fingerprint reuse check via KV; phone/email vendor enrichment is a stub (corpus-first)
 *  - $49/mo Prevention tier via Managed Pricing (a "Prevention" plan in the
 *    Partner Dashboard); $29 stays tag-only
 *  - a hold never cancels or refunds; hold/release errors fail open to tag + note
 */

const API_VERSION = "2026-07";
const RS_COMPOSITE_URL =
  "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/composite-check";
/* P1 (RS-ENH-2026-11-26-V2): fulfillment scopes power hold/release;
 * write_flow_actions powers the Flow trigger. Adding scopes requires
 * existing shops to re-authorize; new installs get them automatically. */
const OAUTH_SCOPES = "read_orders,write_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders,write_flow_actions";
const SCREEN_TIMEOUT_MS = 15000;
/* Managed Pricing: plans are defined in the Partner Dashboard and Shopify hosts
 * the plan picker, so the app never creates charges itself. The handle is the
 * app's URL handle from the Partner Dashboard; override with the
 * SHOPIFY_APP_HANDLE variable if it differs from this default. */
const DEFAULT_APP_HANDLE = "relayshield-order-screening";
const SUPPORT_URL = "https://support.relayshield.net";
const PRIVACY_URL = "https://privacy.relayshield.net";
const SCREENINGS_CAP = 100;
/* Buyer screening records (email stored only as SHA-256 hash) expire after
 * 90 days so personal data is never kept longer than needed. */
const SCREENINGS_TTL_SECONDS = 90 * 24 * 60 * 60;

/* P1 enhancements (RS-ENH-2026-11-26-V2): score thresholds and plan tiers.
 * Default: hold at 70 and above, flag 40-69, pass below 40. The merchant
 * can change both thresholds in the dashboard. */
const DEFAULT_HOLD_THRESHOLD = 70;
const DEFAULT_FLAG_THRESHOLD = 40;
/* Tiers (Managed Pricing): the plan name comes from the live Shopify
 * subscription. "Prevention" is the $49/mo plan defined in the Partner
 * Dashboard; "Paid" is the $29/mo plan; no active subscription is Free.
 * A tier is never stored on the shop record; it is re-read from Shopify. */
const TIER_FREE = "free";
const TIER_STANDARD = "standard"; /* $29/mo: screen + tag, as before */
const TIER_PREVENTION = "prevention"; /* $49/mo: hold, Flow, rules, fingerprinting, enrichment */
const PREVENTION_PLAN_NAME = "Prevention"; /* Partner Dashboard plan name for the $49 tier */
/* Flow trigger handle (must match the handle in extensions/flow-trigger/shopify.extension.toml). */
const FLOW_TRIGGER_HANDLE = "relayshield-high-risk-order";
const FLOW_ACTION_HANDLE = "relayshield-hold-order";
/* One hold handle per fulfillment order; a duplicate handle is rejected by
 * Shopify, so a re-screened order reuses the same handle and is treated
 * as already held. */
const HOLD_HANDLE = "relayshield-fraud-review";

const holdSettingsKey = (shop) => `hold_settings:${shop}`;
const rulesKey = (shop) => `rules:${shop}`;
const allowlistKey = (shop) => `allowlist:${shop}`;
const flowStateKey = (shop) => `flow:${shop}`;
const fingerprintKey = (hash) => `fp:${hash}`;
const flowActionKey = (runId) => `flow_action:${runId}`;

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
const settingsKey = (shop) => `settings:${shop}`;

/* Everything stored for a shop; used by uninstall and shop/redact so the two
 * can never drift apart. */
async function deleteShopData(env, shop) {
  await kvDelete(env, shopKey(shop));
  await kvDelete(env, screeningsKey(shop));
  await kvDelete(env, settingsKey(shop));
}

/* Merchant-editable behaviour. Both default on, which is what the app did
 * before settings existed, so an existing shop sees no change. */
export const DEFAULT_SETTINGS = { tag_medium: true, add_note: true };

export function normalizeSettings(input) {
  const src = input && typeof input === "object" ? input : {};
  return {
    tag_medium: typeof src.tag_medium === "boolean" ? src.tag_medium : DEFAULT_SETTINGS.tag_medium,
    add_note: typeof src.add_note === "boolean" ? src.add_note : DEFAULT_SETTINGS.add_note,
  };
}

export async function getSettings(env, shop) {
  return normalizeSettings(await kvGet(env, settingsKey(shop)));
}

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
  const phone = order.phone || order.billing_address?.phone || order.shipping_address?.phone || "";
  const noteAttrs = Array.isArray(order.note_attributes) ? order.note_attributes : [];
  const fpAttr = noteAttrs.find((a) => a && a.name === "relayshield_device_fingerprint");
  const deviceFingerprint = fpAttr ? String(fpAttr.value || "") : "";
  const clientIp = order.client_details?.browser_ip || "";
  const country = order.shipping_address?.country_code || order.billing_address?.country_code || "";
  return {
    email: { from_address: email },
    phone,
    device_fingerprint: deviceFingerprint,
    client_ip: clientIp,
    country,
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
export function verdictActions(level, settings) {
  const cfg = normalizeSettings(settings);
  if (level === "high") return { tags: ["relayshield-high-risk"], note: cfg.add_note };
  if (level === "medium" && cfg.tag_medium) return { tags: ["relayshield-review"], note: cfg.add_note };
  // Unknown, or medium with tagging off: no tag, but the score line still goes in the order note
  // (merged from the live Worker's 2026-11-03 behaviour).
  return { tags: [], note: cfg.add_note };
}

/* The order note is the only merchant-visible field an app can write that
 * Shopify turns into a timeline entry. The REST Event resource is GET-only:
 * there is no POST /orders/{id}/events.json endpoint, and timeline comments
 * are read-only for apps. So the screening line goes into the order note,
 * appended to any merchant note already there, never overwriting it.
 * (Recovered from the live Worker's uncommitted 2026-11-03 edits.) */
export function buildOrderNoteLine(orderName, level, score, reasons) {
  const shown = (reasons || []).filter(Boolean).slice(0, 3);
  let line = `RelayShield screened order ${orderName}: composite risk ${score}/100 (${level}).`;
  if (shown.length) line += ` Signals: ${shown.join("; ")}.`;
  line += " This is a risk signal, not proof of safety; review before fulfilling. Nothing was changed automatically.";
  return line;
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

export async function applyVerdictToOrder(shop, token, order, level, score, reasons, settings) {
  const actions = verdictActions(level, settings);
  if (!actions.tags.length && !actions.note) return { skipped: true };
  const results = {};
  // One GET gives both the current tags and the current merchant note; one PUT writes both.
  const current = ((await adminApi(shop, token, `/orders/${order.id}.json`)) || {}).order || {};
  const orderBody = { id: order.id };
  if (actions.tags.length) {
    const existing = String(current.tags || "").split(",").map((t) => t.trim()).filter(Boolean);
    const merged = [...new Set([...existing, ...actions.tags])];
    orderBody.tags = merged.join(", ");
    results.tags = merged;
  }
  if (actions.note) {
    const noteLine = buildOrderNoteLine(order.name, level, score, reasons);
    const existingNote = String(current.note || "");
    orderBody.note = existingNote.includes(noteLine)
      ? existingNote
      : existingNote ? `${existingNote}\n${noteLine}` : noteLine;
    results.note = true;
  }
  await adminApi(shop, token, `/orders/${order.id}.json`, "PUT", { order: orderBody });
  return results;
}

async function recordScreening(env, shop, record) {
  const list = (await kvGet(env, screeningsKey(shop))) || [];
  list.unshift(record);
  await kvPut(env, screeningsKey(shop), list.slice(0, SCREENINGS_CAP), SCREENINGS_TTL_SECONDS);
}

/* ------------------------------------------------------------------ */
/* P1 enhancements (RS-ENH-SECTION)                                   */
/* Hold-before-ship, Flow, rules, fingerprinting, $49 Prevention tier */
/* ------------------------------------------------------------------ */

async function adminGraphql(shop, token, query, variables) {
  const resp = await fetch(adminBase(shop) + "/graphql.json", {
    method: "POST",
    headers: { "X-Shopify-Access-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`GraphQL -> ${resp.status}: ${text.slice(0, 200)}`);
  }
  const body = await resp.json();
  if (body.errors && body.errors.length) {
    throw new Error(`GraphQL errors: ${JSON.stringify(body.errors).slice(0, 200)}`);
  }
  return body.data;
}

/* --- tiers (Managed Pricing) --------------------------------------- */
/* The tier is read from the live Shopify subscription, never from the
 * shop record. getShopPlan(active, usage) in the base file returns a
 * plan object; v2 adds a `tier` field to it (see the P7b patch below).
 * "prevention" is the $49/mo plan named "Prevention" in the Partner
 * Dashboard; "standard" is the $29/mo "Paid" plan; "free" is no
 * subscription. A billing error fails open to "free", so an outage can
 * never grant Prevention holds. */

export function tierOfPlan(plan) {
  if (!plan) return TIER_FREE;
  if (plan.tier) return plan.tier;
  if (plan.plan === PREVENTION_PLAN_NAME) return TIER_PREVENTION;
  return plan.isPaid ? TIER_STANDARD : TIER_FREE;
}

export function isPreventionPlan(plan) {
  return tierOfPlan(plan) === TIER_PREVENTION;
}

/* --- hold thresholds (separate KV key from the tag/note settings) --- */
/* The base file stores tag_medium/add_note under settingsKey. Hold
 * thresholds live under holdSettingsKey so the two never clobber each
 * other in the same KV key. */

export async function getHoldSettings(env, shop) {
  const saved = (await kvGet(env, holdSettingsKey(shop))) || {};
  return {
    hold_threshold: Number.isFinite(saved.hold_threshold) ? saved.hold_threshold : DEFAULT_HOLD_THRESHOLD,
    flag_threshold: Number.isFinite(saved.flag_threshold) ? saved.flag_threshold : DEFAULT_FLAG_THRESHOLD,
    hold_enabled: saved.hold_enabled !== false,
  };
}

export async function saveHoldSettings(env, shop, patch) {
  const current = await getHoldSettings(env, shop);
  const next = { ...current };
  if (Number.isFinite(patch.hold_threshold)) next.hold_threshold = Math.max(0, Math.min(100, Math.round(patch.hold_threshold)));
  if (Number.isFinite(patch.flag_threshold)) next.flag_threshold = Math.max(0, Math.min(100, Math.round(patch.flag_threshold)));
  if (next.flag_threshold > next.hold_threshold) next.flag_threshold = next.hold_threshold;
  if (typeof patch.hold_enabled === "boolean") next.hold_enabled = patch.hold_enabled;
  await kvPut(env, holdSettingsKey(shop), next);
  return next;
}

/* --- rules / allowlist -------------------------------------------- */
/* Rule values that identify a buyer (email, phone, device fingerprint,
 * address) are stored only as SHA-256 hashes, like buyer emails. Country
 * and IP are stored plain: neither identifies a buyer on its own. */

export function hashRuleValue(type, value) {
  const raw = String(value || "").trim().toLowerCase();
  if (type === "phone") return raw.replace(/[^0-9]/g, "");
  return raw;
}

export async function hashRuleStored(type, value) {
  const norm = hashRuleValue(type, value);
  if (type === "email" || type === "phone" || type === "device" || type === "address") {
    return sha256Hex(norm);
  }
  return norm;
}

export function ruleSignalValue(type, order, signals) {
  if (type === "email") return signals.email.from_address;
  if (type === "phone") return signals.phone;
  if (type === "device") return signals.device_fingerprint;
  if (type === "ip") return signals.client_ip;
  if (type === "country") return signals.country;
  if (type === "address") {
    const a = order.shipping_address || order.billing_address || {};
    return [a.address1, a.city, a.zip, a.country_code].filter(Boolean).join(" ");
  }
  return "";
}

export async function matchRules(rules, order, signals) {
  for (const rule of rules || []) {
    if (!rule || rule.enabled === false) continue;
    const candidate = ruleSignalValue(rule.type, order, signals);
    if (!candidate) continue;
    const stored = await hashRuleStored(rule.type, candidate);
    if (stored && stored === rule.value) return rule;
  }
  return null;
}

export async function isAllowlisted(allowlist, order, signals) {
  return (await matchRules(allowlist, order, signals)) !== null;
}

export async function getShopRules(env, shop) {
  return (await kvGet(env, rulesKey(shop))) || [];
}

export async function getShopAllowlist(env, shop) {
  return (await kvGet(env, allowlistKey(shop))) || [];
}

/* --- hold decision (pure; unit-testable) --------------------------- */

export function decideHold(input) {
  const { tier, settings, score, ruleMatch, allowlisted, fingerprintReuse } = input;
  if (tier !== TIER_PREVENTION) return { hold: false, reason: null };
  if (!settings.hold_enabled) return { hold: false, reason: null };
  if (allowlisted) return { hold: false, reason: null };
  if (fingerprintReuse) return { hold: true, reason: "device fingerprint previously seen on a held order" };
  if (ruleMatch) {
    if (ruleMatch.action === "hold") return { hold: true, reason: `matched rule ${ruleMatch.type}` };
    return { hold: false, reason: `matched rule ${ruleMatch.type} (flag only)` };
  }
  if (typeof score === "number" && score >= settings.hold_threshold) {
    return { hold: true, reason: `score ${score}/100 at or above hold threshold ${settings.hold_threshold}` };
  }
  return { hold: false, reason: null };
}

/* --- device fingerprint enrichment (corpus-first) ------------------ */
/* A fingerprint seen on a prior held order is a strong signal even when
 * the email and address are new. Fingerprints are stored only as hashes,
 * keyed fp:<sha256>, with a count of held orders. Vendor phone/email
 * enrichment (carrier, line type, domain age, disposable, breach) is NOT
 * wired yet: the corpus-first path above ships first, and a vendor call
 * belongs in enrichSignals() below when Andrew picks one. */

export async function checkFingerprintReuse(env, signals) {
  const fp = String(signals.device_fingerprint || "");
  if (!fp) return false;
  const rec = await kvGet(env, fingerprintKey(await sha256Hex(fp)));
  return Boolean(rec && rec.held_count > 0);
}

export async function noteFingerprintHold(env, signals, orderName) {
  const fp = String(signals.device_fingerprint || "");
  if (!fp) return;
  const key = fingerprintKey(await sha256Hex(fp));
  const rec = (await kvGet(env, key)) || { held_count: 0 };
  rec.held_count = (rec.held_count || 0) + 1;
  rec.last_held_order = orderName || null;
  rec.last_seen = new Date().toISOString();
  await kvPut(env, key, rec);
}

export async function enrichSignals(env, signals) {
  const reasons = [];
  const fingerprintReuse = await checkFingerprintReuse(env, signals);
  if (fingerprintReuse) reasons.push("Device fingerprint previously seen on a held order");
  return { reasons, fingerprintReuse };
}

/* --- fulfillment hold (GraphQL; $49 Prevention tier only) ---------- */
/* Hold = fulfillment hold for merchant review. It never cancels or
 * refunds an order, and it never blocks checkout. Any failure here fails
 * open: the order keeps its tag + timeline note and the webhook still
 * returns 200. Requires write_merchant_managed_fulfillment_orders (and
 * read_merchant_managed_fulfillment_orders for the lookup). */

const FO_QUERY = `query orderFulfillmentOrders($id: ID!) {
  order(id: $id) {
    fulfillmentOrders(first: 10) {
      nodes { id status fulfillmentHolds { id handle reason } }
    }
  }
}`;

const HOLD_MUTATION = `mutation fulfillmentOrderHold($id: ID!, $fulfillmentHold: FulfillmentOrderHoldInput!) {
  fulfillmentOrderHold(id: $id, fulfillmentHold: $fulfillmentHold) {
    fulfillmentHold { id reason reasonNotes handle }
    fulfillmentOrder { id status }
    userErrors { field message }
  }
}`;

const RELEASE_MUTATION = `mutation fulfillmentOrderReleaseHold($id: ID!, $holdIds: [ID!]) {
  fulfillmentOrderReleaseHold(id: $id, holdIds: $holdIds) {
    fulfillmentOrder { id status }
    userErrors { field message }
  }
}`;

export async function holdFulfillmentOrders(shop, token, order, score, reasons) {
  const data = await adminGraphql(shop, token, FO_QUERY, { id: `gid://shopify/Order/${order.id}` });
  const nodes = (data && data.order && data.order.fulfillmentOrders && data.order.fulfillmentOrders.nodes) || [];
  const held = [];
  const errors = [];
  for (const fo of nodes) {
    if (fo.status !== "OPEN") continue;
    const already = (fo.fulfillmentHolds || []).find((h) => h.handle === HOLD_HANDLE);
    if (already) { held.push({ fulfillmentOrderId: fo.id, holdId: already.id, already: true }); continue; }
    const note = (score == null ? "RelayShield hold." : `RelayShield score ${score}/100. `) + (reasons || []).slice(0, 3).join("; ");
    try {
      const res = await adminGraphql(shop, token, HOLD_MUTATION, {
        id: fo.id,
        fulfillmentHold: { reason: "HIGH_RISK_OF_FRAUD", reasonNotes: note.slice(0, 500), handle: HOLD_HANDLE, notifyMerchant: true },
      });
      const errs = (res.fulfillmentOrderHold && res.fulfillmentOrderHold.userErrors) || [];
      if (errs.length) { errors.push(errs.map((e) => e.message).join("; ")); continue; }
      const h = res.fulfillmentOrderHold.fulfillmentHold;
      held.push({ fulfillmentOrderId: fo.id, holdId: h ? h.id : null, already: false });
    } catch (e) {
      errors.push(e.message);
    }
  }
  return { held, errors };
}

export async function releaseOrderHold(shop, token, orderId) {
  const data = await adminGraphql(shop, token, FO_QUERY, { id: `gid://shopify/Order/${orderId}` });
  const nodes = (data && data.order && data.order.fulfillmentOrders && data.order.fulfillmentOrders.nodes) || [];
  const released = [];
  const errors = [];
  for (const fo of nodes) {
    const ours = (fo.fulfillmentHolds || []).filter((h) => h.handle === HOLD_HANDLE);
    if (!ours.length) continue;
    try {
      const res = await adminGraphql(shop, token, RELEASE_MUTATION, { id: fo.id, holdIds: ours.map((h) => h.id) });
      const errs = (res.fulfillmentOrderReleaseHold && res.fulfillmentOrderReleaseHold.userErrors) || [];
      if (errs.length) { errors.push(errs.map((e) => e.message).join("; ")); continue; }
      released.push(fo.id);
    } catch (e) {
      errors.push(e.message);
    }
  }
  return { released, errors };
}

/* --- Shopify Flow -------------------------------------------------- */
/* Trigger: the app fires flowTriggerReceive with handle
 * relayshield-high-risk-order when a Prevention-tier order scores high or
 * is held. The trigger extension is declared in
 * extensions/flow-trigger/shopify.extension.toml (created with
 * `shopify app generate extension`, type Flow Trigger); the handle there
 * must match FLOW_TRIGGER_HANDLE. Payload keys: order_id is the fixed key
 * of the order_reference field (numeric legacy id); the rest are
 * sentence-case custom fields declared in the TOML.
 * The lifecycle callback (/flow/lifecycle) records whether any merchant
 * has an enabled workflow using the trigger, so the mutation is only sent
 * where it is used. An empty userErrors array means Flow accepted the
 * event, not that a workflow ran: treat it as fire-and-forget.
 * Action: Flow calls POST /flow/hold-order (runtime_url in the Flow Action
 * extension) with an HMAC-signed JSON payload; the handler verifies the
 * HMAC with the app secret, dedupes by action_run_id, and holds the order.
 * Both endpoints fail open: a Flow failure never fails the webhook. */

const FLOW_TRIGGER_MUTATION = `mutation FireTrigger($handle: String, $payload: JSON) {
  flowTriggerReceive(handle: $handle, payload: $payload) {
    userErrors { field message }
  }
}`;

export async function sendFlowTrigger(env, shop, token, order, level, score, reasons) {
  const state = (await kvGet(env, flowStateKey(shop))) || {};
  if (!state.has_enabled_flow) return { sent: false, reason: "no enabled workflow" };
  const data = await adminGraphql(shop, token, FLOW_TRIGGER_MUTATION, {
    handle: FLOW_TRIGGER_HANDLE,
    payload: {
      order_id: Number(order.id),
      "Risk score": Number(score),
      "Risk level": String(level),
      "Top signal": String((reasons && reasons[0]) || "no flags found"),
    },
  });
  const errs = (data.flowTriggerReceive && data.flowTriggerReceive.userErrors) || [];
  if (errs.length) throw new Error(errs.map((e) => e.message).join("; "));
  return { sent: true };
}

export async function handleFlowLifecycle(request, env) {
  const raw = await request.text();
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  let body = {};
  try { body = JSON.parse(raw); } catch { return new Response("Bad JSON", { status: 400 }); }
  const shop = String(body.shopify_domain || "");
  if (!isValidShopDomain(shop)) return new Response("Bad shop", { status: 400 });
  const prev = (await kvGet(env, flowStateKey(shop))) || {};
  const seenAt = body.timestamp || new Date().toISOString();
  if (prev.updated_at && prev.updated_at > seenAt) return json({ ok: true, stale: true });
  await kvPut(env, flowStateKey(shop), {
    has_enabled_flow: Boolean(body.has_enabled_flow),
    flow_trigger_definition_id: body.flow_trigger_definition_id || null,
    updated_at: seenAt,
  });
  return json({ ok: true });
}

export async function handleFlowAction(request, env) {
  const raw = await request.text();
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  let body = {};
  try { body = JSON.parse(raw); } catch { return new Response("Bad JSON", { status: 400 }); }
  if (body.handle && body.handle !== FLOW_ACTION_HANDLE) {
    return json({ ok: false, error: "unknown action handle" }, 400);
  }
  const shop = String(body.shopify_domain || "");
  if (!isValidShopDomain(shop)) return new Response("Bad shop", { status: 400 });
  const runId = String(body.action_run_id || "");
  if (runId) {
    if (await kvGet(env, flowActionKey(runId))) return json({ ok: true, deduped: true });
    await kvPut(env, flowActionKey(runId), { shop, at: new Date().toISOString() }, 7 * 24 * 60 * 60);
  }
  const rawOrderId = body.order_id || body.orderId || body.Order || (body.order && body.order.id) || null;
  if (!rawOrderId) return json({ ok: false, error: "no order_id in payload" }, 400);
  const orderId = Number(String(rawOrderId).replace(/^gid:\/\/shopify\/Order\//, ""));
  if (!Number.isFinite(orderId)) return json({ ok: false, error: "bad order_id in payload" }, 400);
  const rec = await getShopRecord(env, shop);
  if (!rec || !rec.access_token) return json({ ok: false, error: "shop not installed" }, 401);
  if (!isPreventionPlan(await loadPlan(env, shop))) return json({ ok: false, error: "Prevention tier required" }, 402);
  let token = rec.access_token;
  try { token = await getFreshAccessToken(env, shop); } catch (e) { console.log(`flow action token refresh failed: ${e.message}`); }
  const order = { id: orderId, name: `#${orderId}` };
  try {
    const res = await holdFulfillmentOrders(shop, token, order, null, ["Held by a Shopify Flow workflow"]);
    return json({ ok: true, held: res.held });
  } catch (e) {
    console.log(`flow action hold failed order=${orderId}: ${e.message}`);
    return json({ ok: false, error: "hold failed" }, 502);
  }
}

/* --- $49 Prevention tier (Managed Pricing) ------------------------- */
/* The $29 tier stays tag-only. The $49 Prevention tier is a second plan
 * defined in the Partner Dashboard (name "Prevention", $49/mo, every 30
 * days). Shopify hosts plan selection: the merchant picks the plan in
 * the plan picker at pricingPlansUrl(), and the app re-reads the live
 * subscription on every dashboard load. The app NEVER creates charges
 * itself: no appSubscriptionCreate, no Stripe, no external checkout.
 * That is the base file's deliberate design, and v2 keeps it.
 * The $49 tier is a pricing change, so it needs advance notice to
 * existing merchants per Shopify billing rules. The plan must exist in
 * the Partner Dashboard before any merchant can pick it; until then the
 * tier reads as "free" or "standard" and no holds happen.
 * LIVE VERIFICATION OWED: confirm the "Prevention" plan exists in the
 * Partner Dashboard and pick it on the dev shop before telling
 * merchants about the tier. */

export async function loadPlanForApi(env, shop) {
  const plan = await loadPlan(env, shop);
  return { plan, tier: tierOfPlan(plan) };
}

/* --- dashboard API (session-token authed) -------------------------- */

export async function requireSessionShop(request, env, url) {
  const auth = request.headers.get("Authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : url.searchParams.get("id_token") || "";
  return verifySessionToken(env, bearer);
}

async function readJsonBody(request) {
  try { return await request.json(); } catch { return {}; }
}

/* Thresholds live on /api/hold-settings, NOT /api/settings: the base
 * file's /api/settings serves the tag/note settings (tag_medium,
 * add_note) and returns 400 on a thresholds body, so a separate
 * endpoint keeps the two from colliding. */
export async function handleApiHoldSettings(request, env, shop) {
  if (request.method === "GET") return json({ ok: true, settings: await getHoldSettings(env, shop) });
  if (request.method === "POST") {
    const body = await readJsonBody(request);
    const saved = await saveHoldSettings(env, shop, {
      hold_threshold: Number(body.hold_threshold),
      flag_threshold: Number(body.flag_threshold),
      hold_enabled: body.hold_enabled,
    });
    return json({ ok: true, settings: saved });
  }
  return new Response("Method not allowed", { status: 405 });
}

export async function handleApiRules(request, env, shop) {
  if (request.method === "GET") return json({ ok: true, rules: await getShopRules(env, shop) });
  if (request.method === "POST") {
    const body = await readJsonBody(request);
    const type = String(body.type || "");
    const action = body.action === "hold" ? "hold" : "flag";
    if (!["email", "phone", "ip", "device", "country", "address"].includes(type)) {
      return json({ ok: false, error: "bad rule type" }, 400);
    }
    if (!String(body.value || "").trim()) return json({ ok: false, error: "empty rule value" }, 400);
    const rules = await getShopRules(env, shop);
    const rule = { id: randomHex(8), type, action, value: await hashRuleStored(type, body.value), enabled: true, created_at: new Date().toISOString() };
    rules.push(rule);
    await kvPut(env, rulesKey(shop), rules);
    return json({ ok: true, rule: { id: rule.id, type, action, enabled: true } });
  }
  if (request.method === "DELETE") {
    const id = new URL(request.url).searchParams.get("id") || "";
    const rules = (await getShopRules(env, shop)).filter((r) => r.id !== id);
    await kvPut(env, rulesKey(shop), rules);
    return json({ ok: true });
  }
  return new Response("Method not allowed", { status: 405 });
}

export async function handleApiAllowlist(request, env, shop) {
  if (request.method === "GET") return json({ ok: true, allowlist: await getShopAllowlist(env, shop) });
  if (request.method === "POST") {
    const body = await readJsonBody(request);
    const type = String(body.type || "");
    if (!["email", "phone", "device", "country"].includes(type)) {
      return json({ ok: false, error: "bad allowlist type" }, 400);
    }
    if (!String(body.value || "").trim()) return json({ ok: false, error: "empty allowlist value" }, 400);
    const list = await getShopAllowlist(env, shop);
    const entry = { id: randomHex(8), type, action: "allow", value: await hashRuleStored(type, body.value), enabled: true, created_at: new Date().toISOString() };
    list.push(entry);
    await kvPut(env, allowlistKey(shop), list);
    return json({ ok: true, entry: { id: entry.id, type, enabled: true } });
  }
  if (request.method === "DELETE") {
    const id = new URL(request.url).searchParams.get("id") || "";
    const list = (await getShopAllowlist(env, shop)).filter((r) => r.id !== id);
    await kvPut(env, allowlistKey(shop), list);
    return json({ ok: true });
  }
  return new Response("Method not allowed", { status: 405 });
}

export async function handleApiRelease(request, env, shop) {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const body = await readJsonBody(request);
  const orderId = body.order_id;
  if (!orderId) return json({ ok: false, error: "no order_id" }, 400);
  const rec = await getShopRecord(env, shop);
  if (!rec || !rec.access_token) return json({ ok: false, error: "shop not installed" }, 401);
  let token = rec.access_token;
  try { token = await getFreshAccessToken(env, shop); } catch (e) { console.log(`release token refresh failed: ${e.message}`); }
  try {
    const res = await releaseOrderHold(shop, token, orderId);
    if (res.released.length) {
      const list = (await kvGet(env, screeningsKey(shop))) || [];
      const row = list.find((s) => String(s.order_id) === String(orderId));
      if (row) { row.released_at = new Date().toISOString(); await kvPut(env, screeningsKey(shop), list, SCREENINGS_TTL_SECONDS); }
    }
    return json({ ok: true, released: res.released, errors: res.errors });
  } catch (e) {
    console.log(`release failed order=${orderId}: ${e.message}`);
    return json({ ok: false, error: "release failed; release the hold from the Shopify admin order page" }, 502);
  }
}

/* Plan is read-only here: Managed Pricing means the merchant picks the
 * plan in Shopify's plan picker (the dashboard links to it). The app
 * never creates or cancels a subscription. GET returns the live plan
 * (re-read from Shopify) and the plans URL. */
export async function handleApiPlan(request, env, shop, url) {
  if (request.method !== "GET") return new Response("Method not allowed", { status: 405 });
  const { plan, tier } = await loadPlanForApi(env, shop);
  return json({ ok: true, plan, tier, plansUrl: pricingPlansUrl(shop, env.SHOPIFY_APP_HANDLE) });
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
  ["app/uninstalled", "/webhooks/app-uninstalled"],
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

/* Managed installation (use_legacy_install_flow = false, which is what this
 * app's Shopify config uses): Shopify installs the app itself and loads the
 * App URL in the Admin iframe with a session token. /auth and /auth/callback
 * are NEVER called, so the authorization-code route above cannot be the only
 * way a shop gets an access token. Token exchange swaps the App Bridge session
 * token for an expiring offline access token on first load, then registers the
 * orders/create webhook exactly as the legacy callback did.
 * UNVERIFIED against a live shop from the build container (shopify.dev is
 * egress-blocked): parameter names follow Shopify's token-exchange reference,
 * and `expiring` mirrors the authorization-code exchange above. */
export async function exchangeSessionToken(env, shop, idToken) {
  const resp = await fetch(`https://${shop}/admin/oauth/access_token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: new URLSearchParams({
      client_id: env.SHOPIFY_API_KEY,
      client_secret: env.SHOPIFY_API_SECRET,
      grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
      subject_token: idToken,
      subject_token_type: "urn:ietf:params:oauth:token-type:id_token",
      requested_token_type: "urn:shopify:params:oauth:token-type:offline-access-token",
      expiring: "1",
    }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`token exchange -> ${resp.status}: ${text.slice(0, 120)}`);
  }
  const data = await resp.json();
  if (!data.access_token) throw new Error("token exchange returned no access token");
  return data;
}

function shopNeedsToken(rec) {
  if (!rec || !rec.access_token) return true;
  // An expired token with no refresh token can only be replaced by a new exchange.
  return Boolean(rec.token_expires_at && Date.now() > rec.token_expires_at && !rec.refresh_token);
}

/* Never throws: a failed exchange must not break the dashboard, and the reason
 * is logged, not returned to the browser. */
export async function ensureInstalled(env, shop, idToken, appOrigin) {
  try {
    const rec = await getShopRecord(env, shop);
    if (!shopNeedsToken(rec)) {
      // Shops installed before app/uninstalled existed never registered it.
      // Registering twice is harmless (Shopify answers 422, which is logged).
      if (!rec.webhooks_v2) {
        try {
          const token = await getFreshAccessToken(env, shop);
          await registerWebhooks(appOrigin, shop, token);
          await kvPut(env, shopKey(shop), { ...(await getShopRecord(env, shop)), webhooks_v2: true });
        } catch (e) {
          console.log(`webhook backfill failed shop=${shop}: ${e.message}`);
        }
      }
      return { installed: true, fresh: false };
    }
    const data = await exchangeSessionToken(env, shop, idToken);
    await kvPut(env, shopKey(shop), {
      ...(rec || {}),
      access_token: data.access_token,
      refresh_token: data.refresh_token || null,
      token_expires_at: Date.now() + (data.expires_in || 3600) * 1000,
      rs_key_mode: (rec && rec.rs_key_mode) || "keyless",
      installed_at: (rec && rec.installed_at) || new Date().toISOString(),
      install_flow: "token_exchange",
      webhooks_v2: true,
    });
    await registerWebhooks(appOrigin, shop, data.access_token);
    return { installed: true, fresh: true };
  } catch (e) {
    console.log(`ensureInstalled failed shop=${shop}: ${e.message}`);
    return { installed: false, fresh: false };
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

async function dropStaleToken(env, shop) {
  const rec = await getShopRecord(env, shop);
  if (!rec) return;
  const { access_token, refresh_token, token_expires_at, ...rest } = rec;
  await kvPut(env, shopKey(shop), rest);
}

/* ------------------------------------------------------------------ */
/* plan status (Managed Pricing)                                       */
/* ------------------------------------------------------------------ */

export function pricingPlansUrl(shop, handle) {
  const store = String(shop || "").replace(/\.myshopify\.com$/i, "");
  return `https://admin.shopify.com/store/${store}/charges/${handle || DEFAULT_APP_HANDLE}/pricing_plans`;
}

/* ------------------------------------------------------------------ */
/* billing: Shopify App Pricing, read-only                             */
/* ------------------------------------------------------------------ */
/* Recovered from the live Worker's uncommitted 2026-11-03 edits and changed in
 * three ways, each deliberate:
 *  1. The FREE allowance is 100 screenings per shop for its LIFETIME (Andrew,
 *     2026-11-15: "try before you buy"; a monthly reset invites abuse). The
 *     PAID allowance stays 2000 per calendar month.
 *  2. The lifetime counter is keyed by a hash of the shop domain and is NOT
 *     deleted by uninstall, so reinstalling does not buy a fresh 100.
 *  3. The subscription query asks only for id, name and status. The live copy
 *     also asked for lineItems.plan.pricingDetails, which nothing used, and a
 *     refused query there threw and produced "Plan status unknown".
 * No appSubscriptionCreate, no Stripe, no external checkout: Shopify hosts plan
 * selection. On any billing error the gate fails open to FREE limits, never to
 * paid, so an outage cannot grant paid screening. */
export const FREE_SCREENING_LIMIT = 100;
export const PAID_SCREENING_LIMIT = 2000;
const PAID_PLAN_NAME = "Paid";
const MONTHLY_COUNT_TTL_SECONDS = 62 * 24 * 60 * 60;

function billingMonthKey(d) {
  const dt = d || new Date();
  return dt.getUTCFullYear() + "-" + String(dt.getUTCMonth() + 1).padStart(2, "0");
}
const monthlyCountKey = (shop, month) => `screenings-count:${shop}:${month}`;
const lifetimeCountKey = async (shop) => `screenings-total:${await sha256Hex(String(shop).toLowerCase())}`;

async function readCount(env, key) {
  try {
    const raw = await env.RS_KV.get(key);
    const n = raw ? JSON.parse(raw).count : 0;
    return typeof n === "number" && n >= 0 ? n : 0;
  } catch { return 0; }
}

export async function getUsage(env, shop) {
  return {
    month: await readCount(env, monthlyCountKey(shop, billingMonthKey())),
    lifetime: await readCount(env, await lifetimeCountKey(shop)),
  };
}

/* Adds `by` screenings to both counters. Best effort: a KV hiccup must never
 * stop an order being handled. */
export async function recordUsage(env, shop, by = 1) {
  try {
    const month = billingMonthKey();
    const mk = monthlyCountKey(shop, month), lk = await lifetimeCountKey(shop);
    const m = (await readCount(env, mk)) + by, l = (await readCount(env, lk)) + by;
    await env.RS_KV.put(mk, JSON.stringify({ month, count: m }), { expirationTtl: MONTHLY_COUNT_TTL_SECONDS });
    await env.RS_KV.put(lk, JSON.stringify({ count: l }));
  } catch (e) {
    console.log(`usage count failed shop=${shop}: ${e.message}`);
  }
}

/* Throws on any failure; callers decide what unknown means. */
export async function getActiveSubscription(shop, token) {
  const resp = await fetch(`${adminBase(shop)}/graphql.json`, {
    method: "POST",
    headers: { "X-Shopify-Access-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({ query: "{ currentAppInstallation { activeSubscriptions { id name status test } } }" }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || (data.errors && data.errors.length) || !data.data) {
    throw new Error(`subscription query failed: ${resp.status}`);
  }
  const subs = (data.data.currentAppInstallation && data.data.currentAppInstallation.activeSubscriptions) || [];
  /* P1 (RS-ENH-2026-11-26-V2): recognize the $49 "Prevention" plan as paid too. */
  const paid = subs.find((x) => x.status === "ACTIVE" && (x.name === PAID_PLAN_NAME || x.name === PREVENTION_PLAN_NAME));
  return paid
    ? { isPaid: true, name: paid.name, test: Boolean(paid.test), subscriptionId: paid.id }
    : { isPaid: false, name: "Free", test: false, subscriptionId: null };
}

export function getShopPlan(active, usage) {
  const isPaid = Boolean(active && active.isPaid);
  const limit = isPaid ? PAID_SCREENING_LIMIT : FREE_SCREENING_LIMIT;
  const used = isPaid ? usage.month : usage.lifetime;
  /* P1 (RS-ENH-2026-11-26-V2): tier for the Prevention gate. The plan name
   * is the live subscription name ("Paid", "Prevention", or "Free"), so the
   * dashboard shows the real plan. Both paid tiers share the 2000/month
   * screening limit; the $49 tier adds hold/Flow/rules, not screenings. */
  const tier = active && active.name === PREVENTION_PLAN_NAME ? "prevention" : isPaid ? "standard" : "free";
  return {
    plan: isPaid ? active.name : "Free",
    tier,
    isPaid,
    test: Boolean(active && active.test),
    limit,
    used,
    remaining: Math.max(0, limit - used),
    overLimit: used >= limit,
    period: isPaid ? "month" : "lifetime",
  };
}

/* The plan for display: null means "could not tell", never "free". */
export async function loadPlan(env, shop) {
  try {
    const token = await getFreshAccessToken(env, shop);
    return getShopPlan(await getActiveSubscription(shop, token), await getUsage(env, shop));
  } catch (e) {
    console.log(`plan status failed shop=${shop}: ${e.message}`);
    return null;
  }
}

/* The gate: fails open to FREE limits on a billing error. */
export async function checkScreeningAllowed(env, shop, token) {
  let active;
  try { active = await getActiveSubscription(shop, token); }
  catch (e) {
    console.log(`billing check failed, using free limits: ${e.message}`);
    active = { isPaid: false, name: "Free", test: false, subscriptionId: null };
  }
  const plan = getShopPlan(active, await getUsage(env, shop));
  return { allowed: !plan.overLimit, plan };
}

async function handleBillingStatus(request, env) {
  const auth = request.headers.get("Authorization") || "";
  const shop = await verifySessionToken(env, auth.startsWith("Bearer ") ? auth.slice(7) : "");
  if (!shop) return json({ ok: false }, 401);
  const plan = await loadPlan(env, shop);
  return json(plan ? { ok: true, ...plan } : { ok: true, billingUnknown: true });
}

/* Shopify's app_subscriptions/update payload carries no shop domain; the shop
 * is in the X-Shopify-Shop-Domain header. The plan itself is always re-read
 * from Shopify, so this only records that a subscription ended. */
async function handleAppSubscriptionsUpdate(request, env) {
  const raw = await readRawBody(request);
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("Unauthorized", { status: 401 });
  }
  let payload = {};
  try { payload = JSON.parse(raw); } catch { payload = {}; }
  const shop = request.headers.get("X-Shopify-Shop-Domain") || (payload && payload.shop_domain) || "";
  const status = payload && payload.app_subscription ? payload.app_subscription.status : "";
  if (isValidShopDomain(shop) && ["CANCELLED", "EXPIRED", "FROZEN", "DECLINED"].includes(status)) {
    const rec = await getShopRecord(env, shop);
    if (rec) await kvPut(env, shopKey(shop), { ...rec, plan: "Free", subscriptionId: null });
  }
  return new Response("ok");
}

async function handleAppUninstalled(request, env) {
  const raw = await readRawBody(request);
  const hmac = request.headers.get("X-Shopify-Hmac-Sha256") || "";
  if (!(await verifyShopifyHmac(env.SHOPIFY_API_SECRET, raw, hmac))) {
    return new Response("HMAC validation failed", { status: 401 });
  }
  const shop = request.headers.get("X-Shopify-Shop-Domain") || "";
  if (!isValidShopDomain(shop)) return new Response("Bad shop header", { status: 400 });
  // Delete everything: a reinstall must start clean, otherwise the dead token
  // and the old screening history survive and the dashboard lies about both.
  await deleteShopData(env, shop);
  return json({ ok: true });
}

async function readRawBody(request) {
  return request.text();
}

/* Screens one order and writes the tag and note to Shopify. Shared by the
 * orders/create webhook and by the order sync, so the two can never disagree.
 * Returns null when screening itself failed (fail open: nothing is recorded and
 * nothing is tagged); otherwise { record } for the caller to store. */
export async function screenAndApply(env, shop, rec, order, settingsIn, tier = TIER_FREE) {
  const signals = extractOrderSignals(order, shop);
  let verdict;
  try {
    const keyInfo = await provisionShopKey(env, shop);
    verdict = await screenOrder(signals, keyInfo);
  } catch (e) {
    console.log(`screening failed order=${order.id}: ${e.message}`);
    return null;
  }
  const level = ["high", "medium", "unknown"].includes(verdict.level) ? verdict.level : "unknown";
  const reasons = (verdict.signals || []).flatMap((s) => s.reasons || []);
  let token = rec.access_token;
  try {
    token = await getFreshAccessToken(env, shop);
  } catch (e) {
    console.log(`token refresh failed order=${order.id}: ${e.message}`);
  }

  /* P1 (RS-ENH-ORDERS-CREATE): Prevention-tier evaluation. Runs before the
   * tag/note so a flag rule can upgrade an unknown verdict to review. */
  let ruleMatch = null;
  let allowlisted = false;
  let enrichment = { reasons: [], fingerprintReuse: false };
  let holdSettings = { hold_threshold: DEFAULT_HOLD_THRESHOLD, flag_threshold: DEFAULT_FLAG_THRESHOLD, hold_enabled: true };
  if (tier === TIER_PREVENTION) {
    try {
      const rules = await getShopRules(env, shop);
      const allow = await getShopAllowlist(env, shop);
      allowlisted = await isAllowlisted(allow, order, signals);
      if (!allowlisted) ruleMatch = await matchRules(rules, order, signals);
      enrichment = await enrichSignals(env, signals);
      holdSettings = await getHoldSettings(env, shop);
    } catch (e) {
      console.log(`rules/enrichment failed order=${order.id}: ${e.message}`);
    }
  }
  const allReasons = [...reasons, ...enrichment.reasons];
  const effectiveLevel = ruleMatch && ruleMatch.action === "flag" && level === "unknown" ? "medium" : level;

  try {
    const settings = settingsIn || (await getSettings(env, shop));
    await applyVerdictToOrder(shop, token, order, effectiveLevel, verdict.score, allReasons, settings);
  } catch (e) {
    console.log(`admin action failed order=${order.id}: ${e.message}`);
    // 401 means the stored token was revoked (uninstall then reinstall, or the
    // merchant removed the app). Drop it so the next authenticated dashboard
    // load exchanges a fresh one instead of trusting a dead token forever.
    if (/-> 401:/.test(e.message)) await dropStaleToken(env, shop);
  }

  /* Hold-before-ship: fulfillment hold only, never cancel or refund.
   * Any failure here fails open to the tag + note above. The hold line
   * goes into the order note (the REST Event resource is GET-only for
   * apps, so there is no POST /orders/{id}/events.json). */
  let held = null;
  const decision = decideHold({ tier, settings: holdSettings, score: verdict.score, level: effectiveLevel, ruleMatch, allowlisted, fingerprintReuse: enrichment.fingerprintReuse });
  if (decision.hold) {
    try {
      const res = await holdFulfillmentOrders(shop, token, order, verdict.score, allReasons);
      if (res.held.length) {
        held = { fulfillmentOrders: res.held.map((h) => h.fulfillmentOrderId), holdIds: res.held.map((h) => h.holdId).filter(Boolean), reason: decision.reason };
        await noteFingerprintHold(env, signals, order.name);
        try {
          const current = ((await adminApi(shop, token, `/orders/${order.id}.json`)) || {}).order || {};
          const existingNote = String(current.note || "");
          const holdNote = `RelayShield held this order for review before shipping (${decision.reason}). Release the hold from the order page or the RelayShield dashboard; nothing was cancelled or refunded.`;
          if (!existingNote.includes(holdNote)) {
            await adminApi(shop, token, `/orders/${order.id}.json`, "PUT", { order: { id: order.id, note: existingNote ? `${existingNote}\n${holdNote}` : holdNote } });
          }
        } catch (e) {
          console.log(`hold note failed order=${order.id}: ${e.message}`);
        }
      } else if (res.errors.length) {
        console.log(`hold failed order=${order.id}: ${res.errors.join("; ")}`);
      }
    } catch (e) {
      console.log(`hold failed order=${order.id}: ${e.message}`);
    }
  }

  /* Flow trigger: fire-and-forget, only where a merchant has an enabled
   * workflow using the trigger. Never fails the webhook. */
  if (tier === TIER_PREVENTION && (effectiveLevel === "high" || held)) {
    try {
      await sendFlowTrigger(env, shop, token, order, effectiveLevel, verdict.score, allReasons);
    } catch (e) {
      console.log(`flow trigger failed order=${order.id}: ${e.message}`);
    }
  }

  return {
    record: {
      order_id: order.id,
      order_name: order.name,
      email_hash: await hashBuyerEmail(signals.email.from_address),
      level: effectiveLevel,
      score: verdict.score,
      top_reason: allReasons[0] || null,
      held: Boolean(held),
      hold_reason: held ? held.reason : null,
      hold_ids: held ? held.holdIds : [],
      fulfillment_order_ids: held ? held.fulfillmentOrders : [],
      rule_id: ruleMatch ? ruleMatch.id : null,
      released_at: null,
      screened_at: new Date().toISOString(),
    },
  };
}

/* ------------------------------------------------------------------ */
/* order sync: screen orders that already exist in the shop            */
/* ------------------------------------------------------------------ */

/* The orders/create webhook only fires for NEW orders. A shop that installs,
 * or reinstalls after the uninstall wipe, with orders already in Shopify would
 * otherwise show an empty dashboard forever. This reads recent orders and
 * screens the ones not yet recorded, a small batch per call (Workers cap the
 * outbound requests one invocation may make); the page calls it until
 * `remaining` is 0. Shopify returns the last 60 days without read_all_orders. */
const SYNC_BATCH = 8;
const SYNC_CONCURRENCY = 4;
const SYNC_LOOKBACK = 50;

export async function fetchRecentOrders(shop, token) {
  const resp = await fetch(`${adminBase(shop)}/graphql.json`, {
    method: "POST",
    headers: { "X-Shopify-Access-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({
      query: "query($first:Int!){ orders(first:$first, sortKey:CREATED_AT, reverse:true){ nodes { legacyResourceId name email } } }",
      variables: { first: SYNC_LOOKBACK },
    }),
  });
  if (!resp.ok) throw new Error(`orders query -> ${resp.status}`);
  const data = await resp.json();
  if (data.errors || !data.data || !data.data.orders) {
    throw new Error(`orders query refused: ${JSON.stringify(data.errors || "no data").slice(0, 200)}`);
  }
  return data.data.orders.nodes.map((n) => ({
    id: Number(n.legacyResourceId),
    name: n.name,
    email: n.email || "",
  }));
}

export async function syncOrders(env, shop) {
  const rec = await getShopRecord(env, shop);
  if (!rec || !rec.access_token) throw new Error("Shop not installed");
  const token = await getFreshAccessToken(env, shop);
  const orders = await fetchRecentOrders(shop, token);
  const list = (await kvGet(env, screeningsKey(shop))) || [];
  const seen = new Set(list.map((s) => s.order_id));
  const todo = orders.filter((o) => o.id && !seen.has(o.id));
  // The same allowance as the webhook: never screen past the plan's limit.
  const gate = todo.length ? await checkScreeningAllowed(env, shop, token) : null;
  if (gate && !gate.allowed) {
    return { synced: 0, failed: 0, remaining: todo.length, total_seen: orders.length, overLimit: true, plan: gate.plan.plan };
  }
  const batch = todo.slice(0, gate ? Math.min(SYNC_BATCH, gate.plan.remaining) : SYNC_BATCH);
  const settings = await getSettings(env, shop);
  const records = [];
  let failed = 0;
  for (let i = 0; i < batch.length; i += SYNC_CONCURRENCY) {
    const outcomes = await Promise.all(batch.slice(i, i + SYNC_CONCURRENCY).map(async (o) => {
      try { return await screenAndApply(env, shop, rec, o, settings, tierOfPlan(gate && gate.plan)); } catch { return null; }
    }));
    for (const out of outcomes) { if (out) records.push(out.record); else failed++; }
  }
  // One write for the whole batch: recordScreening is read-modify-write, so
  // calling it from concurrent tasks would drop records.
  if (records.length) {
    await kvPut(env, screeningsKey(shop), [...records.reverse(), ...list].slice(0, SCREENINGS_CAP), SCREENINGS_TTL_SECONDS);
  }
  if (records.length) await recordUsage(env, shop, records.length);
  const remaining = todo.length - batch.length;
  const cappedByPlan = remaining > 0 && gate && batch.length === gate.plan.remaining && gate.plan.remaining < SYNC_BATCH;
  if (remaining === 0 && failed === 0) {
    const fresh = (await getShopRecord(env, shop)) || rec;
    await kvPut(env, shopKey(shop), { ...fresh, orders_synced_at: new Date().toISOString() });
  }
  return { synced: records.length, failed, remaining, total_seen: orders.length, overLimit: Boolean(cappedByPlan) };
}

async function handleSync(request, env, url) {
  const auth = request.headers.get("Authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const shop = await verifySessionToken(env, bearer);
  if (!shop) return json({ ok: false }, 401);
  const inst = await ensureInstalled(env, shop, bearer, url.origin);
  if (!inst.installed) return json({ ok: false, error: "not_installed" }, 503);
  try {
    return json({ ok: true, ...(await syncOrders(env, shop)) });
  } catch (e) {
    console.log(`order sync failed shop=${shop}: ${e.message}`);
    return json({ ok: false, error: "orders_unavailable" }, 502);
  }
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

  // Billing gate BEFORE screening: over the plan's allowance, nothing is screened,
  // tagged or recorded, and the dashboard says why.
  let gateToken = rec.access_token;
  try { gateToken = await getFreshAccessToken(env, shop); } catch (e) {
    console.log(`billing token refresh failed order=${order.id}: ${e.message}`);
  }
  const gate = await checkScreeningAllowed(env, shop, gateToken);
  if (!gate.allowed) return json({ ok: true, screened: false, overLimit: true, plan: gate.plan.plan });
  await recordUsage(env, shop, 1);

  const outcome = await screenAndApply(env, shop, rec, order, undefined, tierOfPlan(gate.plan));
  if (!outcome) return json({ ok: true, screened: false, error: "screening unavailable" });
  await recordScreening(env, shop, outcome.record);
  return json({ ok: true, screened: true, level: outcome.record.level, score: outcome.record.score, held: Boolean(outcome.record.held) });
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
    await deleteShopData(env, shop);
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

export function renderDashboard(shop, screenings, apiKey, host, extras = {}) {
  const settings = normalizeSettings(extras.settings);
  const plan = extras.plan === undefined ? null : extras.plan;
  const plansUrl = pricingPlansUrl(shop, extras.appHandle);
  /* P1 (RS-ENH-2026-11-26-V2): hold thresholds, rules, allowlist, held count.
   * plan is the plan object from getShopPlan (with a tier field); the hold
   * settings come from extras.holdSettings, loaded by handleDashboard. */
  const holdSettings = extras.holdSettings || { hold_threshold: DEFAULT_HOLD_THRESHOLD, flag_threshold: DEFAULT_FLAG_THRESHOLD, hold_enabled: true };
  const rules = extras.rules || [];
  const allowlist = extras.allowlist || [];
  const heldCount = screenings.filter((s) => s.held && !s.released_at).length;
  const storeHandle = String(shop || "").replace(/\.myshopify\.com$/i, "");
  const counts = { high: 0, medium: 0, unknown: 0 };
  for (const s of screenings) if (counts[s.level] !== undefined) counts[s.level]++;
  const usageText = (p) => p.isPaid
    ? `${esc(p.used)} of ${esc(p.limit)} screenings used this month.`
    : `${esc(p.used)} of ${esc(p.limit)} free checks used.`;
  const planText = !shop ? "Sign in through Shopify Admin to see your plan."
    : plan === null ? "We could not confirm your plan just now. Use the button below to choose or review it."
    : `Current plan: <strong>${esc(plan.plan)}</strong>${plan.test ? " (test charge)" : ""}. ${usageText(plan)}` +
      (plan.overLimit ? (plan.isPaid
        ? " You have reached this month's limit; new orders are not screened until next month."
        : " You have used all your free checks; new orders are not screened until you choose the Paid plan.") : "");
  const orderCell = (s) => storeHandle && s.order_id
    ? `<a href="https://admin.shopify.com/store/${esc(storeHandle)}/orders/${esc(s.order_id)}" target="_top">${esc(s.order_name)}</a>`
    : esc(s.order_name);
  const rows = screenings.map((s) => `
      <tr data-level="${esc(s.level)}">
        <td>${orderCell(s)}</td>
        <td>${esc(s.screened_at)}</td>
        <td><span class="badge badge-${esc(s.level)}">${esc(s.level)}</span></td>
        <td>${esc(s.score)}/100</td>
        <td>${esc(s.top_reason || "no flags found")}</td>
        <td>${s.held ? `HELD${s.released_at ? " (released)" : ""} <button data-release="${esc(s.order_id)}" ${s.released_at ? "disabled" : ""}>Release</button>` : "—"}</td>
      </tr>`).join("");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield Order Screening</title>
<meta name="shopify-api-key" content="${esc(apiKey)}" />
<script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
<script>
  (function() {
    var attempts = 0;
    function tryInit() {
      attempts++;
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
              // The first load has no token, so the server rendered an empty
              // dashboard. Reload once with the token; never loop.
              var authed = document.body && document.body.getAttribute("data-shop");
              if (r.status === 200 && !authed && !/[?&]id_token=/.test(location.search)) {
                var u = new URL(location.href);
                u.searchParams.set("id_token", token);
                location.replace(u.toString());
              }
            }).catch(function(e) {
              console.log("[RelayShield] session auth call failed:", e && e.message);
            });
          }).catch(function(e) {
            console.log("[RelayShield] session token unavailable:", e && e.message);
          });
        } else if (attempts < 20) {
          // Script may not have loaded yet; retry
          setTimeout(tryInit, 500);
        } else {
          console.log("[RelayShield] App Bridge not ready after retries");
        }
      } catch (e) {
        console.log("[RelayShield] App Bridge init skipped:", e && e.message);
      }
    }
    // Start after DOM is ready to give the CDN script time to load
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", tryInit);
    } else {
      tryInit();
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
  .panel { background: #fff; border-radius: 8px; padding: 16px 20px; margin: 16px 0; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
  .panel h2 { margin: 0 0 8px; font-size: 16px; }
  .check { display: block; margin: 8px 0; font-size: 14px; }
  .hint { color: #5c5f62; font-size: 13px; }
  .toolbar { display: flex; gap: 8px; align-items: center; margin: 16px 0 8px; font-size: 14px; }
  .btn { display: inline-block; padding: 7px 14px; border: 1px solid #8a8a8a; border-radius: 8px; background: #fff; color: #303030; font-size: 14px; font-weight: 600; text-decoration: none; cursor: pointer; }
  .btn-primary { background: #303030; border-color: #303030; color: #fff; }
  .btn[disabled] { opacity: .6; cursor: default; }
</style>
</head>
<body data-shop="${esc(shop)}" data-needs-sync="${extras.needsSync ? "1" : "0"}">
<div class="wrap">
  <h1>RelayShield Order Screening</h1>
  <p>Screening orders for <strong>${esc(shop)}</strong> against the RelayShield threat-intelligence corpus.</p>
  <div class="cards">
    <div class="card"><div class="n">${counts.high}</div><div>High risk (tagged relayshield-high-risk)</div></div>
    <div class="card"><div class="n">${counts.medium}</div><div>Needs review (tagged relayshield-review)</div></div>
    <div class="card"><div class="n">${counts.unknown}</div><div>No flags found (no tag)</div></div>
    <div class="card"><div class="n">${heldCount}</div><div>Held for review (fulfillment hold)</div></div>
  </div>
  <div class="panel">
    <h2>Your plan</h2>
    <p id="plan-text">${planText}</p>
    <p><a class="btn btn-primary" id="manage-plan" href="${esc(plansUrl)}" target="_top">View or change plan</a></p>
  </div>
  <form class="panel" id="settings-form" onsubmit="return false">
    <h2>Screening settings</h2>
    <label class="check"><input type="checkbox" id="set-tag-medium"${settings.tag_medium ? " checked" : ""}> Tag medium-risk orders <code>relayshield-review</code></label>
    <label class="check"><input type="checkbox" id="set-add-note"${settings.add_note ? " checked" : ""}> Add a RelayShield line to the order note</label>
    <p class="hint">High-risk orders are always tagged. RelayShield never cancels, refunds, or holds an order.</p>
    <p><button type="submit" class="btn btn-primary" id="save-settings">Save settings</button> <span id="settings-status" role="status" aria-live="polite"></span></p>
  </form>
  <div class="toolbar">
    <label for="verdict-filter">Show</label>
    <select id="verdict-filter">
      <option value="all">All screened orders</option>
      <option value="high">High risk</option>
      <option value="medium">Needs review</option>
      <option value="unknown">No flags found</option>
    </select>
    <button type="button" class="btn" id="sync-btn">Sync orders</button>
    <button type="button" class="btn" id="refresh-btn">Refresh</button>
    <span id="sync-status" role="status" aria-live="polite"></span>
  </div>
  <table>
    <thead><tr><th>Order</th><th>Screened</th><th>Verdict</th><th>Score</th><th>Top signal</th><th>Held</th></tr></thead>
    <tbody id="rows">${rows || '<tr><td colspan="6">No orders screened yet.</td></tr>'}</tbody>
  </table>
  <p class="hint" id="filter-empty" hidden>No orders match this filter.</p>
  <p class="note"><a href="${SUPPORT_URL}" target="_blank" rel="noopener">Support</a> &middot; <a href="${PRIVACY_URL}" target="_blank" rel="noopener">Privacy policy</a></p>
  <p class="note">A result of "no flags found" means nothing is known against the order right now, not proof of safety. On the $49 Prevention tier, high-risk orders are held for your review before shipping; a hold is a fulfillment hold, never a cancel or refund. On the $29 tier, high-risk orders are tagged for your review and nothing is held.</p>
    <h2>Plan and thresholds</h2>
    <p>Current plan: <strong>${plan ? `${esc(plan.plan)} (${esc(plan.tier)})` : "could not tell"}</strong> &mdash; <a href="${esc(plansUrl)}" target="_blank" rel="noopener">View or change plan</a></p>
    ${plan && plan.tier === "prevention" ? "<p>Prevention tier is active: hold-before-ship, Shopify Flow, custom rules and device fingerprinting are on.</p>" : "<p>Hold-before-ship, Shopify Flow, custom rules and device fingerprinting are on the $49/mo Prevention tier. Pick it in the plan picker above; the $29/mo Standard tier keeps screen-and-tag.</p>"}
    <form id="rs-hold-settings">
      <label>Hold threshold (0-100): <input type="number" name="hold_threshold" min="0" max="100" value="${esc(holdSettings.hold_threshold)}"></label>
      <label>Flag threshold (0-100): <input type="number" name="flag_threshold" min="0" max="100" value="${esc(holdSettings.flag_threshold)}"></label>
      <label><input type="checkbox" name="hold_enabled" ${holdSettings.hold_enabled ? "checked" : ""}> Hold-before-ship enabled</label>
      <button type="submit">Save thresholds</button>
    </form>
    <h2>Custom rules and allowlist</h2>
    <p>Rules only apply on the Prevention tier. A rule matches an order by email domain, phone, country, or risk score; an "allowlist" entry always screens normally. Values are stored as SHA-256 hashes, never as raw buyer data.</p>
    <form id="rs-rules">
      <input type="text" name="field" placeholder="email_domain" required>
      <input type="text" name="value" placeholder="example.com" required>
      <select name="action"><option value="flag">Flag</option><option value="allow">Allow</option></select>
      <button type="submit">Add rule</button>
    </form>
    <ul>
      ${rules.map((r) => `<li>${esc(r.field)}: ${esc(r.value_hash)} (${esc(r.action)}) <button data-rule="${esc(r.id)}">Delete</button></li>`).join("") || "<li>No rules yet.</li>"}
    </ul>
    <form id="rs-allowlist">
      <input type="text" name="field" placeholder="email" required>
      <input type="text" name="value" placeholder="customer@example.com" required>
      <button type="submit">Allowlist</button>
    </form>
    <ul>
      ${allowlist.map((r) => `<li>${esc(r.field)}: ${esc(r.value_hash)} <button data-allow="${esc(r.id)}">Delete</button></li>`).join("") || "<li>No allowlist entries yet.</li>"}
    </ul>
    <script>
      document.getElementById("rs-hold-settings").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        await api("/api/hold-settings", "POST", { hold_threshold: Number(f.get("hold_threshold")), flag_threshold: Number(f.get("flag_threshold")), hold_enabled: f.get("hold_enabled") === "on" });
      });
      document.getElementById("rs-rules").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        await api("/api/rules", "POST", { field: f.get("field"), value: f.get("value"), action: f.get("action") });
      });
      document.getElementById("rs-allowlist").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        await api("/api/allowlist", "POST", { field: f.get("field"), value: f.get("value") });
      });
      document.querySelectorAll("[data-rule]").forEach((b) => b.addEventListener("click", async () => { await api("/api/rules/" + b.dataset.rule, "DELETE"); }));
      document.querySelectorAll("[data-allow]").forEach((b) => b.addEventListener("click", async () => { await api("/api/allowlist/" + b.dataset.allow, "DELETE"); }));
      document.querySelectorAll("[data-release]").forEach((b) => b.addEventListener("click", async () => { await api("/api/release/" + b.dataset.release, "POST"); }));
    </script>
</div>
<script>
(function() {
  var filter = document.getElementById("verdict-filter");
  filter.addEventListener("change", function() {
    var want = filter.value, shown = 0;
    document.querySelectorAll("#rows tr[data-level]").forEach(function(tr) {
      var show = want === "all" || tr.getAttribute("data-level") === want;
      tr.hidden = !show;
      if (show) shown++;
    });
    document.getElementById("filter-empty").hidden = shown !== 0 || !document.querySelector("#rows tr[data-level]");
  });
  document.getElementById("refresh-btn").addEventListener("click", function() {
    // The id_token in the URL is short-lived; drop it so the page fetches a fresh one and reloads once.
    var u = new URL(location.href);
    u.searchParams.delete("id_token");
    location.replace(u.toString());
  });
  function getToken() {
    if (!(window.shopify && typeof window.shopify.idToken === "function")) return Promise.reject(new Error("no app bridge"));
    return window.shopify.idToken();
  }
  var syncing = false;
  function runSync() {
    if (syncing) return;
    syncing = true;
    var btn = document.getElementById("sync-btn"), status = document.getElementById("sync-status");
    var total = 0, rounds = 0, overLimit = false;
    btn.disabled = true;
    status.textContent = "Syncing orders...";
    function step() {
      return getToken().then(function(token) {
        return fetch("/api/sync", { method: "POST", headers: { "Authorization": "Bearer " + token } });
      }).then(function(r) {
        if (!r.ok) throw new Error("status " + r.status);
        return r.json();
      }).then(function(j) {
        total += j.synced; rounds++;
        if (j.overLimit) overLimit = true;
        status.textContent = "Screened " + total + " existing order" + (total === 1 ? "" : "s") + (j.remaining > 0 && !j.overLimit ? ", more to go..." : ".");
        if (j.remaining > 0 && j.synced > 0 && rounds < 8) return step();
      });
    }
    step().then(function() {
      if (total > 0) {
        var u = new URL(location.href);
        u.searchParams.delete("id_token");
        location.replace(u.toString());
      } else {
        status.textContent = overLimit ? "Your plan's screening limit is reached. Choose the Paid plan to screen more orders." : "Your recent orders are all screened.";
      }
    }).catch(function() {
      status.textContent = "Could not read your orders from Shopify. Try again, or contact support.";
    }).then(function() { syncing = false; btn.disabled = false; });
  }
  document.getElementById("sync-btn").addEventListener("click", runSync);
  if (document.body.getAttribute("data-needs-sync") === "1" && document.body.getAttribute("data-shop")) {
    // Orders that already exist are not delivered by webhook. Sync them once on the first signed-in load.
    setTimeout(runSync, 300);
  }
  document.getElementById("save-settings").addEventListener("click", function() {
    var btn = this, status = document.getElementById("settings-status");
    if (!(window.shopify && typeof window.shopify.idToken === "function")) {
      status.textContent = "Open this app from Shopify Admin to change settings.";
      return;
    }
    btn.disabled = true;
    status.textContent = "Saving...";
    window.shopify.idToken().then(function(token) {
      return fetch("/api/settings", {
        method: "POST",
        headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
        body: JSON.stringify({
          tag_medium: document.getElementById("set-tag-medium").checked,
          add_note: document.getElementById("set-add-note").checked
        })
      });
    }).then(function(r) {
      status.textContent = r.ok ? "Saved." : "Could not save (" + r.status + "). Reload and try again.";
      if (r.ok && window.shopify.toast) window.shopify.toast.show("Settings saved");
    }).catch(function() {
      status.textContent = "Could not save. Reload and try again.";
    }).then(function() { btn.disabled = false; });
  });
})();
</script>
</body>
</html>`;
}

async function handleSettingsSave(request, env) {
  const auth = request.headers.get("Authorization") || "";
  const shop = await verifySessionToken(env, auth.startsWith("Bearer ") ? auth.slice(7) : "");
  if (!shop) return json({ ok: false }, 401);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "bad json" }, 400); }
  if (!body || typeof body.tag_medium !== "boolean" || typeof body.add_note !== "boolean") {
    return json({ ok: false, error: "tag_medium and add_note must be booleans" }, 400);
  }
  const settings = normalizeSettings(body);
  await kvPut(env, settingsKey(shop), settings);
  return json({ ok: true, settings });
}

async function handleDashboard(request, env) {
  const url = new URL(request.url);
  const auth = request.headers.get("Authorization") || "";
  const bearer = auth.startsWith("Bearer ")
    ? auth.slice(7)
    : url.searchParams.get("id_token") || "";
  const shop = await verifySessionToken(env, bearer);
  // Serve the dashboard HTML even without a valid session token: the page
  // acquires one client-side via window.shopify.idToken() and reloads itself
  // with it. (Shopify's embedded-app checks are telemetry from real Admin
  // sessions, not a crawler that loads this URL.)
  if (shop) await ensureInstalled(env, shop, bearer, url.origin);
  const screenings = shop ? ((await kvGet(env, screeningsKey(shop))) || []) : [];
  const settings = shop ? await getSettings(env, shop) : DEFAULT_SETTINGS;
  const plan = shop ? await loadPlan(env, shop) : null;
  const shopRec = shop ? await getShopRecord(env, shop) : null;
  const needsSync = Boolean(shop && shopRec && shopRec.access_token && !shopRec.orders_synced_at);
  /* P1 (RS-ENH-2026-11-26-V2): hold thresholds, rules, allowlist for the
   * dashboard. Defaults when there is no shop (unauthenticated load). */
  const holdSettings = shop ? await getHoldSettings(env, shop) : { hold_threshold: DEFAULT_HOLD_THRESHOLD, flag_threshold: DEFAULT_FLAG_THRESHOLD, hold_enabled: true };
  const rules = shop ? await getShopRules(env, shop) : [];
  const allowlist = shop ? await getShopAllowlist(env, shop) : [];
  const host = url.searchParams.get("host") || "";
  return new Response(renderDashboard(shop || "", screenings, env.SHOPIFY_API_KEY, host, {
    settings, plan, needsSync, appHandle: env.SHOPIFY_APP_HANDLE, holdSettings, rules, allowlist,
  }), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "frame-ancestors https://*.myshopify.com https://admin.shopify.com;",
    },
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
      if (url.pathname === "/webhooks/app-uninstalled" && request.method === "POST") {
        return handleAppUninstalled(request, env);
      }
      if (url.pathname === "/billing/status" && request.method === "GET") {
        return handleBillingStatus(request, env);
      }
      if (url.pathname === "/webhooks/app-subscriptions-update" && request.method === "POST") {
        return handleAppSubscriptionsUpdate(request, env);
      }
      if (url.pathname === "/api/sync" && request.method === "POST") {
        return handleSync(request, env, url);
      }
      if (url.pathname === "/api/settings" && request.method === "POST") {
        return handleSettingsSave(request, env);
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
        const inst = await ensureInstalled(env, shop, bearer, url.origin);
        // Visible in `wrangler tail`: proves a session token arrived in an Authorization header.
        console.log(`api/session ok shop=${shop} installed=${inst.installed} fresh=${inst.fresh}`);
        return new Response(JSON.stringify({ ok: true, shop, installed: inst.installed }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/flow/hold-order" && request.method === "POST") {
        return handleFlowAction(request, env);
      }
      if (url.pathname === "/flow/lifecycle" && request.method === "POST") {
        return handleFlowLifecycle(request, env);
      }
      if (url.pathname === "/api/hold-settings") {
        const shop = await requireSessionShop(request, env, url);
        if (!shop) return new Response(JSON.stringify({ ok: false }), { status: 401, headers: { "Content-Type": "application/json" } });
        return handleApiHoldSettings(request, env, shop);
      }
      if (url.pathname === "/api/rules") {
        const shop = await requireSessionShop(request, env, url);
        if (!shop) return new Response(JSON.stringify({ ok: false }), { status: 401, headers: { "Content-Type": "application/json" } });
        return handleApiRules(request, env, shop);
      }
      if (url.pathname === "/api/allowlist") {
        const shop = await requireSessionShop(request, env, url);
        if (!shop) return new Response(JSON.stringify({ ok: false }), { status: 401, headers: { "Content-Type": "application/json" } });
        return handleApiAllowlist(request, env, shop);
      }
      if (url.pathname === "/api/release" && request.method === "POST") {
        const shop = await requireSessionShop(request, env, url);
        if (!shop) return new Response(JSON.stringify({ ok: false }), { status: 401, headers: { "Content-Type": "application/json" } });
        return handleApiRelease(request, env, shop);
      }
      if (url.pathname === "/healthz") return new Response("ok");
      return new Response("Not found", { status: 404 });
    } catch (e) {
      console.log(`unhandled: ${e.message}`);
      return new Response("Internal error", { status: 500 });
    }
  },
};
