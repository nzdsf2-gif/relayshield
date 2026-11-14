// Runs the Worker with an in-memory KV and a stubbed fetch. No network.
//   node shopify/test_worker_session.mjs
import { createHmac } from "node:crypto";
import { copyFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const here = dirname(fileURLToPath(import.meta.url));
const tmp = mkdtempSync(join(tmpdir(), "rs-shopify-"));
copyFileSync(join(here, "worker.js"), join(tmp, "worker.mjs"));
const worker = await import(pathToFileURL(join(tmp, "worker.mjs")).href);

const SECRET = "test-secret", KEY = "client-id-123", SHOP = "relayshield-test.myshopify.com";
const b64u = (o) => Buffer.from(typeof o === "string" ? o : JSON.stringify(o)).toString("base64url");
function idToken(over = {}) {
  const h = b64u({ alg: "HS256", typ: "JWT" });
  const p = b64u({ dest: `https://${SHOP}`, aud: KEY, exp: Math.floor(Date.now() / 1000) + 60, ...over });
  return `${h}.${p}.${createHmac("sha256", SECRET).update(`${h}.${p}`).digest("base64url")}`;
}
function mkEnv(initial = {}) {
  const m = new Map(Object.entries(initial).map(([k, v]) => [k, JSON.stringify(v)]));
  return { SHOPIFY_API_KEY: KEY, SHOPIFY_API_SECRET: SECRET, _m: m,
    RS_KV: { get: async (k) => m.get(k) ?? null, put: async (k, v) => void m.set(k, v), delete: async (k) => void m.delete(k) } };
}
let calls;
function stubFetch(exchangeStatus = 200) {
  calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith("/admin/oauth/access_token"))
      return new Response(JSON.stringify(exchangeStatus === 200
        ? { access_token: "shpat_new", refresh_token: "shprt_new", expires_in: 3600 } : { error: "no" }), { status: exchangeStatus });
    return new Response("{}", { status: 201 });
  };
}
const get = (env, path, headers = {}) => worker.default.fetch(new Request(`https://app.example${path}`, { headers }), env);
let n = 0; const ok = (name) => console.log(`ok ${++n} ${name}`);

// 1. A shop with no token (managed install) is exchanged on first authenticated load.
{
  const env = mkEnv(); stubFetch();
  const r = await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.ok, true); assert.equal(j.installed, true);
  const ex = calls.find((c) => c.url.endsWith("/admin/oauth/access_token"));
  assert.ok(ex, "token exchange was called");
  const body = new URLSearchParams(ex.init.body);
  assert.equal(body.get("grant_type"), "urn:ietf:params:oauth:grant-type:token-exchange");
  assert.equal(body.get("subject_token_type"), "urn:ietf:params:oauth:token-type:id_token");
  assert.equal(body.get("requested_token_type"), "urn:shopify:params:oauth:token-type:offline-access-token");
  assert.equal(body.get("client_secret"), SECRET);
  const rec = JSON.parse(env._m.get(`shop:${SHOP}`));
  assert.equal(rec.access_token, "shpat_new"); assert.equal(rec.install_flow, "token_exchange");
  const topics = calls.filter((c) => c.url.includes("/webhooks.json")).map((c) => JSON.parse(c.init.body).webhook.topic);
  assert.deepEqual(topics.sort(), ["app/uninstalled", "orders/create"]);
  assert.equal(rec.webhooks_v2, true);
  ok("first load exchanges the session token, stores the token, registers the webhook");
}
// 2. An already-installed shop is NOT exchanged again (the dev store that exists today).
{
  const env = mkEnv({ [`shop:${SHOP}`]: { access_token: "shpat_old", refresh_token: "r", token_expires_at: Date.now() + 3600e3, webhooks_v2: true } });
  stubFetch();
  const r = await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal((await r.json()).installed, true);
  assert.equal(calls.length, 0, "no network call for an installed shop");
  assert.equal(JSON.parse(env._m.get(`shop:${SHOP}`)).access_token, "shpat_old");
  ok("an installed shop is left alone");
}
// 3. A failed exchange never breaks the dashboard or the endpoint.
{
  const env = mkEnv(); stubFetch(403);
  const r = await get(env, `/?id_token=${idToken()}&shop=${SHOP}&host=x`);
  assert.equal(r.status, 200);
  assert.ok(!env._m.has(`shop:${SHOP}`), "nothing stored on failure");
  const r2 = await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal(r2.status, 200); assert.equal((await r2.json()).installed, false);
  ok("a refused exchange leaves the dashboard and /api/session working");
}
// 4. Bad tokens are refused and trigger no exchange.
{
  const env = mkEnv(); stubFetch();
  for (const bad of ["", "a.b.c", idToken({ exp: 1 }), idToken({ dest: "https://evil.example" }), idToken().slice(0, -2) + "xx"]) {
    const r = await get(env, "/api/session", bad ? { Authorization: `Bearer ${bad}` } : {});
    assert.equal(r.status, 401, `refused: ${bad.slice(0, 20)}`);
  }
  assert.equal(calls.length, 0);
  ok("expired, forged, wrong-shop and missing tokens get 401 and no exchange");
}
// 5. The page App Bridge needs: meta key, CDN script first in head, framing allowed, authed flag.
{
  const env = mkEnv({ [`shop:${SHOP}`]: { access_token: "t" } }); stubFetch();
  const r = await get(env, `/?id_token=${idToken()}&shop=${SHOP}`);
  const html = await r.text();
  const head = html.slice(html.indexOf("<head>"), html.indexOf("</head>"));
  assert.ok(head.includes(`<meta name="shopify-api-key" content="${KEY}"`));
  const scripts = [...head.matchAll(/<script\b([^>]*)>/g)].map((m) => m[1]);
  assert.match(scripts[0], /src="https:\/\/cdn\.shopify\.com\/shopifycloud\/app-bridge\.js"/);
  assert.doesNotMatch(scripts[0], /async|defer|module/);
  assert.match(r.headers.get("content-security-policy"), /frame-ancestors https:\/\/\*\.myshopify\.com https:\/\/admin\.shopify\.com/);
  assert.ok(html.includes(`<body data-shop="${SHOP}" data-needs-sync="0">`) || html.includes(`<body data-shop="${SHOP}" data-needs-sync="1">`));
  const anon = await (await get(env, "/")).text();
  assert.ok(anon.includes('<body data-shop="" data-needs-sync="0">'));
  ok("meta key, first-script CDN App Bridge, frame-ancestors, and the authed flag are all present");
}

/* ---- helpers for the checks below ---- */
const post = (env, path, body, headers = {}) =>
  worker.default.fetch(new Request(`https://app.example${path}`, { method: "POST", body, headers }), env);
const sign = (raw) => createHmac("sha256", SECRET).update(raw).digest("base64");
const installed = (extra = {}) => ({ [`shop:${SHOP}`]: { access_token: "t", refresh_token: "r", token_expires_at: Date.now() + 3600e3, webhooks_v2: true, ...extra } });
function stubWith(handler) {
  calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const r = handler(String(url), init);
    return r || new Response("{}", { status: 201 });
  };
}

// 6. Settings change what gets written to an order.
{
  assert.deepEqual(worker.verdictActions("high", { tag_medium: false, add_note: false }), { tags: ["relayshield-high-risk"], note: false });
  assert.deepEqual(worker.verdictActions("medium", { tag_medium: false, add_note: true }), { tags: [], note: false });
  assert.deepEqual(worker.verdictActions("medium"), { tags: ["relayshield-review"], note: true });
  assert.deepEqual(worker.verdictActions("unknown", {}), { tags: [], note: false });
  assert.deepEqual(worker.normalizeSettings({ tag_medium: "no", add_note: 0 }), { tag_medium: true, add_note: true });
  ok("settings gate tags and notes, high risk is always tagged, junk values fall back to defaults");
}
// 7. POST /api/settings: session-token auth, boolean validation, persisted, shown on the page.
{
  const env = mkEnv(installed()); stubFetch();
  const H = (t) => ({ Authorization: `Bearer ${t}`, "Content-Type": "application/json" });
  assert.equal((await post(env, "/api/settings", "{}", {})).status, 401);
  assert.equal((await post(env, "/api/settings", "{}", H(idToken({ exp: 1 })))).status, 401);
  assert.equal((await post(env, "/api/settings", "not json", H(idToken()))).status, 400);
  assert.equal((await post(env, "/api/settings", JSON.stringify({ tag_medium: "yes", add_note: true }), H(idToken()))).status, 400);
  assert.equal((await post(env, "/api/settings", JSON.stringify({ tag_medium: true, add_note: "yes" }), H(idToken()))).status, 400);
  assert.equal((await post(env, "/api/settings", JSON.stringify({ tag_medium: true }), H(idToken()))).status, 400);
  assert.ok(!env._m.has(`settings:${SHOP}`), "nothing stored by refused requests");
  const r = await post(env, "/api/settings", JSON.stringify({ tag_medium: false, add_note: true }), H(idToken()));
  assert.equal(r.status, 200);
  assert.deepEqual(JSON.parse(env._m.get(`settings:${SHOP}`)), { tag_medium: false, add_note: true });
  const html = await (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text();
  assert.doesNotMatch(html, /id="set-tag-medium" checked/);
  assert.match(html, /id="set-add-note" checked/);
  ok("settings save needs a valid session token and boolean fields, persist, and render back checked or unchecked");
}
// 8. The page has controls a merchant can use, even before a session exists.
{
  const env = mkEnv(installed()); stubFetch();
  for (const path of [`/?id_token=${idToken()}&shop=${SHOP}`, "/"]) {
    const html = await (await get(env, path)).text();
    for (const id of ["manage-plan", "save-settings", "verdict-filter", "refresh-btn", "set-tag-medium", "set-add-note"])
      assert.ok(html.includes(`id="${id}"`), `${id} present at ${path.slice(0, 12)}`);
    assert.ok(html.includes("https://support.relayshield.net") && html.includes("https://privacy.relayshield.net"));
    assert.match(html, /<button type="button" class="btn" id="refresh-btn">/);
  }
  const html = worker.renderDashboard(SHOP, [{ order_id: 99, order_name: "#1001", level: "high", score: 90, screened_at: "x" }], KEY, "");
  assert.ok(html.includes(`href="https://admin.shopify.com/store/relayshield-test/orders/99" target="_top">#1001</a>`));
  assert.ok(html.includes('<tr data-level="high">'));
  ok("plan link, settings form, filter, refresh, support and privacy links render signed in or out; orders link to Admin");
}
// 9. Plan status comes from Shopify and is shown, never invented.
{
  const gql = (payload, status = 200) => (url) => url.endsWith("/graphql.json") ? new Response(JSON.stringify(payload), { status }) : null;
  const page = async (handler) => { const env = mkEnv(installed()); stubWith(handler); return (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text(); };
  let html = await page(gql({ data: { currentAppInstallation: { activeSubscriptions: [{ name: "Standard", status: "ACTIVE", test: false }] } } }));
  assert.match(html, /Current plan: <strong>Standard<\/strong>/);
  assert.match(html, /charges\/relayshield-order-screening\/pricing_plans/);
  assert.doesNotMatch(html, /test charge/);
  html = await page(gql({ data: { currentAppInstallation: { activeSubscriptions: [] } } }));
  assert.match(html, /No active plan yet/);
  html = await page(gql({ errors: [{ message: "boom" }] }));
  assert.match(html, /could not confirm your plan/);
  html = await page(gql({}, 500));
  assert.match(html, /could not confirm your plan/);
  const env = mkEnv(installed()); stubWith(gql({ data: { currentAppInstallation: { activeSubscriptions: [] } } }));
  await get(env, `/?id_token=${idToken()}&shop=${SHOP}`);
  const q = calls.find((c) => c.url.endsWith("/graphql.json"));
  assert.ok(q.url.includes(`https://${SHOP}/admin/api/`) && q.init.method === "POST");
  assert.equal(q.init.headers["X-Shopify-Access-Token"], "t");
  assert.match(JSON.parse(q.init.body).query, /activeSubscriptions/);
  assert.ok(!/appSubscriptionCreate/.test(JSON.stringify(calls)), "Managed Pricing: the app never creates a charge");
  assert.equal(worker.pricingPlansUrl(SHOP, "my-handle"), "https://admin.shopify.com/store/relayshield-test/charges/my-handle/pricing_plans");
  ok("plan status is read from Shopify, failures show as unknown, and the app never creates a charge");
}
// 10. app/uninstalled wipes the shop so a reinstall starts clean.
{
  const all = { ...installed(), [`screenings:${SHOP}`]: [{ order_id: 1 }], [`settings:${SHOP}`]: { tag_medium: false, add_note: false } };
  const env = mkEnv(all); stubFetch();
  const raw = "{}";
  assert.equal((await post(env, "/webhooks/app-uninstalled", raw, { "X-Shopify-Hmac-Sha256": "bad", "X-Shopify-Shop-Domain": SHOP })).status, 401);
  assert.ok(env._m.has(`shop:${SHOP}`), "forged request deletes nothing");
  assert.equal((await post(env, "/webhooks/app-uninstalled", raw, { "X-Shopify-Hmac-Sha256": sign(raw), "X-Shopify-Shop-Domain": "evil.example" })).status, 400);
  const r = await post(env, "/webhooks/app-uninstalled", raw, { "X-Shopify-Hmac-Sha256": sign(raw), "X-Shopify-Shop-Domain": SHOP });
  assert.equal(r.status, 200);
  for (const k of ["shop", "screenings", "settings"]) assert.ok(!env._m.has(`${k}:${SHOP}`), `${k} deleted`);
  // shop/redact deletes the same set, through the shared helper
  const env2 = mkEnv(all);
  const red = JSON.stringify({ shop_domain: SHOP });
  await post(env2, "/webhooks/gdpr", red, { "X-Shopify-Hmac-Sha256": sign(red), "X-Shopify-Topic": "shop/redact" });
  for (const k of ["shop", "screenings", "settings"]) assert.ok(!env2._m.has(`${k}:${SHOP}`), `redact: ${k} deleted`);
  ok("app/uninstalled and shop/redact delete token, history and settings; forged or malformed requests delete nothing");
}
// 11. A reinstall after uninstall exchanges a fresh token (the old one is gone).
{
  const env = mkEnv(); stubFetch();
  const r = await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal((await r.json()).installed, true);
  assert.ok(calls.some((c) => c.url.endsWith("/admin/oauth/access_token")));
  ok("after an uninstall wipe, the next authenticated load exchanges a new token");
}
// 12. Shops installed before app/uninstalled existed get it registered once.
{
  const env = mkEnv({ [`shop:${SHOP}`]: { access_token: "t", refresh_token: "r", token_expires_at: Date.now() + 3600e3 } });
  stubFetch();
  await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal(calls.filter((c) => c.url.includes("/webhooks.json")).length, 2);
  assert.equal(JSON.parse(env._m.get(`shop:${SHOP}`)).webhooks_v2, true);
  assert.equal(JSON.parse(env._m.get(`shop:${SHOP}`)).access_token, "t", "existing token kept");
  calls.length = 0;
  await get(env, "/api/session", { Authorization: `Bearer ${idToken()}` });
  assert.equal(calls.length, 0, "second load does not register again");
  ok("older installs are backfilled with the uninstall webhook exactly once");
}
// 13. A revoked token (401 from the Admin API) is dropped so the next load re-exchanges.
{
  const env = mkEnv(installed({ rs_key_mode: "keyless" })); 
  stubWith((url) => {
    if (url.includes("execute-api")) return new Response(JSON.stringify({ ok: true, data: { level: "high", score: 90, signals: [] } }));
    if (url.includes("/admin/api/")) return new Response("revoked", { status: 401 });
    return null;
  });
  const raw = JSON.stringify({ id: 5, name: "#1005", email: "a@b.example" });
  const r = await post(env, "/webhooks/orders-create", raw, { "X-Shopify-Hmac-Sha256": sign(raw), "X-Shopify-Shop-Domain": SHOP });
  assert.equal(r.status, 200);
  const rec = JSON.parse(env._m.get(`shop:${SHOP}`));
  assert.ok(!rec.access_token && !rec.refresh_token, "dead token removed");
  assert.equal(rec.webhooks_v2, true, "other fields kept");
  assert.equal(JSON.parse(env._m.get(`screenings:${SHOP}`)).length, 1, "screening still recorded");
  ok("a 401 from the Admin API drops the stored token and still records the screening");
}

// 14. Existing orders are synced in batches, once, and the shop is then marked synced.
{
  const nodes = Array.from({ length: 10 }, (_, i) => ({ legacyResourceId: String(100 + i), name: `#${1000 + i}`, email: `buyer${i}@example.com` }));
  const env = mkEnv(installed()); let composite = 0;
  stubWith((url, init) => {
    if (url.endsWith("/graphql.json") && String(init.body).includes("orders(")) return new Response(JSON.stringify({ data: { orders: { nodes } } }));
    if (url.includes("execute-api")) { composite++; return new Response(JSON.stringify({ ok: true, data: { level: "unknown", score: 10, signals: [] } })); }
    return null;
  });
  const H = { Authorization: `Bearer ${idToken()}` };
  assert.equal((await post(env, "/api/sync", "", {})).status, 401);
  assert.equal(composite, 0, "no screening without a session");
  let html = await (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text();
  assert.match(html, /data-needs-sync="1"/);
  let j = await (await post(env, "/api/sync", "", H)).json();
  assert.deepEqual([j.ok, j.synced, j.remaining, j.failed], [true, 8, 2, 0]);
  assert.ok(!JSON.parse(env._m.get(`shop:${SHOP}`)).orders_synced_at, "not marked synced while orders remain");
  j = await (await post(env, "/api/sync", "", H)).json();
  assert.deepEqual([j.synced, j.remaining], [2, 0]);
  const list = JSON.parse(env._m.get(`screenings:${SHOP}`));
  assert.equal(list.length, 10); assert.equal(new Set(list.map((x) => x.order_id)).size, 10, "no duplicates");
  assert.ok(JSON.parse(env._m.get(`shop:${SHOP}`)).orders_synced_at, "marked synced");
  assert.ok(!JSON.stringify(list).includes("buyer0@example.com"), "raw email never stored");
  j = await (await post(env, "/api/sync", "", H)).json();
  assert.equal(j.synced, 0); assert.equal(composite, 10, "second pass screens nothing again");
  html = await (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text();
  assert.match(html, /data-needs-sync="0"/); assert.match(html, /#1009/);
  ok("existing orders are screened in batches, once each, recorded without raw emails, and the shop is then marked synced");
}
// 15. The reviewer's path: orders exist, app is uninstalled then reinstalled, dashboard must not stay empty.
{
  const nodes = Array.from({ length: 6 }, (_, i) => ({ legacyResourceId: String(200 + i), name: `#${2000 + i}`, email: `b${i}@example.com` }));
  const env = mkEnv({ ...installed({ orders_synced_at: "x" }), [`screenings:${SHOP}`]: [{ order_id: 200 }] });
  stubWith((url, init) => {
    if (url.endsWith("/admin/oauth/access_token")) return new Response(JSON.stringify({ access_token: "shpat_new", refresh_token: "r", expires_in: 3600 }));
    if (url.endsWith("/graphql.json") && String(init.body).includes("orders(")) return new Response(JSON.stringify({ data: { orders: { nodes } } }));
    if (url.includes("execute-api")) return new Response(JSON.stringify({ ok: true, data: { level: "unknown", score: 0, signals: [] } }));
    return null;
  });
  const raw = "{}";
  await post(env, "/webhooks/app-uninstalled", raw, { "X-Shopify-Hmac-Sha256": sign(raw), "X-Shopify-Shop-Domain": SHOP });
  assert.ok(!env._m.has(`screenings:${SHOP}`));
  const html = await (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text();
  assert.match(html, /data-needs-sync="1"/, "reinstalled shop is flagged for sync on first signed-in load");
  const j = await (await post(env, "/api/sync", "", { Authorization: `Bearer ${idToken()}` })).json();
  assert.equal(j.synced, 6);
  const after = await (await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).text();
  assert.doesNotMatch(after, /No orders screened yet/);
  for (let i = 0; i < 6; i++) assert.ok(after.includes(`#${2000 + i}`));
  ok("uninstall, reinstall, first load: the six existing orders appear instead of 'No orders screened yet'");
}
// 16. A refused orders read is reported, never marks the shop synced, never breaks the page.
{
  const env = mkEnv(installed());
  stubWith((url, init) => url.endsWith("/graphql.json") && String(init.body).includes("orders(")
    ? new Response(JSON.stringify({ errors: [{ message: "Access denied" }] })) : null);
  const r = await post(env, "/api/sync", "", { Authorization: `Bearer ${idToken()}` });
  assert.equal(r.status, 502); assert.equal((await r.json()).error, "orders_unavailable");
  assert.ok(!JSON.parse(env._m.get(`shop:${SHOP}`)).orders_synced_at);
  assert.equal((await get(env, `/?id_token=${idToken()}&shop=${SHOP}`)).status, 200);
  ok("a refused orders query returns 502, leaves the shop unsynced, and the dashboard still renders");
}
// 17. Sync writes the same tag a webhook would, and skips orders the webhook already recorded.
{
  const nodes = [{ legacyResourceId: "300", name: "#3000", email: "x@example.com" }, { legacyResourceId: "301", name: "#3001", email: "y@example.com" }];
  const env = mkEnv({ ...installed(), [`screenings:${SHOP}`]: [{ order_id: 301, level: "unknown" }] });
  stubWith((url, init) => {
    if (url.endsWith("/graphql.json") && String(init.body).includes("orders(")) return new Response(JSON.stringify({ data: { orders: { nodes } } }));
    if (url.includes("execute-api")) return new Response(JSON.stringify({ ok: true, data: { level: "high", score: 90, signals: [] } }));
    if (url.includes("/orders/300.json") && (init.method || "GET") === "GET") return new Response(JSON.stringify({ order: { tags: "" } }));
    return null;
  });
  const j = await (await post(env, "/api/sync", "", { Authorization: `Bearer ${idToken()}` })).json();
  assert.equal(j.synced, 1, "order 301 was already recorded");
  const put = calls.find((c) => c.url.includes("/orders/300.json") && c.init.method === "PUT");
  assert.ok(put && JSON.parse(put.init.body).order.tags.includes("relayshield-high-risk"));
  assert.ok(!calls.some((c) => c.url.includes("/orders/301")), "recorded order not touched");
  const screened = calls.filter((c) => c.url.includes("execute-api")).map((c) => JSON.parse(c.init.body));
  assert.equal(screened.length, 1);
  assert.equal(screened[0].email.from_address, "x@example.com", "the buyer email reaches the screening call");
  assert.equal(screened[0].url, `https://${SHOP}`);
  ok("sync tags a high-risk existing order like the webhook does and leaves already-recorded orders alone");
}
// 18. Sync works on a shop that has no token yet (reinstall: sync can arrive before any other call).
{
  const env = mkEnv();
  stubWith((url, init) => {
    if (url.endsWith("/admin/oauth/access_token")) return new Response(JSON.stringify({ access_token: "shpat_new", refresh_token: "r", expires_in: 3600 }));
    if (url.endsWith("/graphql.json") && String(init.body).includes("orders(")) return new Response(JSON.stringify({ data: { orders: { nodes: [{ legacyResourceId: "400", name: "#4000", email: "z@example.com" }] } } }));
    if (url.includes("execute-api")) return new Response(JSON.stringify({ ok: true, data: { level: "unknown", score: 1, signals: [] } }));
    return null;
  });
  const j = await (await post(env, "/api/sync", "", { Authorization: `Bearer ${idToken()}` })).json();
  assert.equal(j.ok, true); assert.equal(j.synced, 1);
  assert.equal(JSON.parse(env._m.get(`shop:${SHOP}`)).access_token, "shpat_new");
  ok("sync exchanges a token first when the shop has none");
}
console.log(`\n${n} passed`);
