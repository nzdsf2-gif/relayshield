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
  assert.ok(calls.some((c) => c.url.includes("/webhooks.json")), "orders/create webhook registered");
  ok("first load exchanges the session token, stores the token, registers the webhook");
}
// 2. An already-installed shop is NOT exchanged again (the dev store that exists today).
{
  const env = mkEnv({ [`shop:${SHOP}`]: { access_token: "shpat_old", refresh_token: "r", token_expires_at: Date.now() + 3600e3 } });
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
  assert.ok(html.includes(`<body data-shop="${SHOP}">`));
  const anon = await (await get(env, "/")).text();
  assert.ok(anon.includes('<body data-shop="">'));
  ok("meta key, first-script CDN App Bridge, frame-ancestors, and the authed flag are all present");
}
console.log(`\n${n} passed`);
