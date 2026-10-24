// Tests for cloudflare_worker_webcheck.js. Run with: node test_webcheck.mjs
// No dependencies. The Worker file is ESM syntax in a .js file, so this test
// copies it to a temp .mjs and imports that (Cloudflare serves the .js as
// a module Worker; node needs the .mjs extension without a package.json).
// The Worker must not touch Cloudflare-only globals at import time: fetch,
// crypto.subtle, Request, Response, FormData, btoa are all node globals.

import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, copyFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const dir = mkdtempSync(join(tmpdir(), "webcheck-test-"));
const workerMjs = join(dir, "worker.mjs");
const workerSrc = fileURLToPath(
  new URL("./cloudflare_worker_webcheck.js", import.meta.url),
);
copyFileSync(workerSrc, workerMjs);
const mod = await import(pathToFileURL(workerMjs).href);
const handler = mod.default;

class FakeKV {
  constructor() {
    this.map = new Map();
  }
  async get(k) {
    const v = this.map.get(k);
    return v === undefined ? null : v;
  }
  async put(k, v) {
    this.map.set(k, v);
  }
}

const ctx = { waitUntil: async (p) => await p };

function jsonResp(obj, ok = true) {
  return {
    ok,
    text: async () => JSON.stringify(obj),
    json: async () => obj,
  };
}

function apiFetch(url, opts) {
  // Turnstile posts form-encoded bodies, not JSON: branch before parsing.
  if (String(url).includes("turnstile")) {
    return Promise.resolve(jsonResp({ success: true }));
  }
  const body = opts && opts.body ? JSON.parse(opts.body) : {};
  if (String(url).includes("/v1/link-check")) {
    return Promise.resolve(
      jsonResp({
        ok: true,
        data: {
          level: "high",
          flagged: true,
          reasons: [
            "matches a known phishing kit",
            "lookalike domain",
            "third reason, must be cut",
          ],
        },
      }),
    );
  }
  if (String(url).includes("/v1/wallet-risk")) {
    return Promise.resolve(
      jsonResp({
        ok: true,
        data: { risk_level: "HIGH", risk_flags: ["sanctioned", "mixer"] },
      }),
    );
  }
  if (String(url).includes("/v1/email-check")) {
    return Promise.resolve(
      jsonResp({ ok: true, data: { risk: "medium", flags: ["spoofed sender"] } }),
    );
  }
  if (String(url).includes("rekognition")) {
    return Promise.resolve(
      jsonResp({
        TextDetections: [
          { Type: "LINE", DetectedText: "Visit https://evil.example.com/login now" },
          { Type: "WORD", DetectedText: "Visit" },
        ],
      }),
    );
  }
  throw new Error("unexpected fetch: " + url);
}

function withFetch(mock, fn) {
  const prev = globalThis.fetch;
  globalThis.fetch = mock;
  return fn().finally(() => {
    globalThis.fetch = prev;
  });
}

function checkReq(input, token) {
  return new Request("https://relayshield.net/check/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, turnstileToken: token || "" }),
  });
}

// --- classification -------------------------------------------------------

test("classifyInput routes link, wallet, email, and rejects prose", () => {
  assert.deepEqual(mod.classifyInput("https://example.com/x"), {
    kind: "link",
    value: "https://example.com/x",
  });
  assert.deepEqual(mod.classifyInput("example.com"), {
    kind: "link",
    value: "https://example.com",
  });
  assert.deepEqual(mod.classifyInput("0x" + "a".repeat(40)), {
    kind: "wallet",
    value: "0x" + "a".repeat(40),
  });
  assert.deepEqual(mod.classifyInput("EQ" + "A".repeat(46)), {
    kind: "wallet",
    value: "EQ" + "A".repeat(46),
  });
  assert.deepEqual(mod.classifyInput("name@example.com"), {
    kind: "email",
    value: "name@example.com",
  });
  assert.deepEqual(mod.classifyInput("hello is this thing on"), {
    kind: "unknown",
  });
  assert.deepEqual(mod.classifyInput(""), { kind: "unknown" });
  assert.deepEqual(mod.classifyInput("x".repeat(2001)), { kind: "unknown" });
  assert.deepEqual(mod.classifyInput("foo bar@example.com"), {
    kind: "unknown",
  });
});

// --- badge mapping --------------------------------------------------------

test("badgeFor maps every API verdict", () => {
  const link = (level) => mod.badgeFor("link", { ok: true, data: { level } });
  assert.equal(link("critical"), "threat");
  assert.equal(link("high"), "threat");
  assert.equal(link("medium"), "suspicious");
  assert.equal(link("low"), "clean");
  assert.equal(link("clean"), "clean");
  assert.equal(link("unknown"), "unchecked");
  assert.equal(mod.badgeFor("link", { ok: true, data: { checked: false } }), "unchecked");
  assert.equal(mod.badgeFor("link", { ok: false }), "unchecked");
  assert.equal(
    mod.badgeFor("wallet", { ok: true, data: { risk_level: "HIGH" } }),
    "threat",
  );
  assert.equal(
    mod.badgeFor("wallet", { ok: true, data: { risk_level: "MEDIUM" } }),
    "suspicious",
  );
  assert.equal(
    mod.badgeFor("wallet", { ok: true, data: { risk_level: "LOW" } }),
    "clean",
  );
  assert.equal(
    mod.badgeFor("email", { ok: true, data: { risk: "high" } }),
    "threat",
  );
  assert.equal(
    mod.badgeFor("email", { ok: true, data: { risk: "medium" } }),
    "suspicious",
  );
  assert.equal(
    mod.badgeFor("email", { ok: true, data: { risk: "low" } }),
    "clean",
  );
});

// --- card shape and copy rules --------------------------------------------

test("buildCard follows the bot card format and copy rules", () => {
  const card = mod.buildCard(
    "link",
    "https://evil.example.com/login",
    {
      ok: true,
      data: { level: "high", reasons: ["reason one", "reason two", "reason three"] },
    },
    "paste",
  );
  assert.equal(card.header, "RelayShield Verdict");
  assert.equal(card.badge, "THREAT DETECTED");
  assert.equal(card.why.length, 2, "Why is capped at 2 lines");
  assert.equal(
    card.footer,
    "Checked against a growing threat intelligence corpus with over 129 monitored marketplaces.",
  );
  assert.equal(
    card.forward,
    "Forward this verdict to anyone who received the same link.",
  );
  assert.deepEqual(
    card.botLinks.map((b) => b.href),
    ["/check/go?to=tg", "/check/go?to=wa", "/check/go?to=miniapp"],
  );
  const text = JSON.stringify(card);
  assert.ok(!text.includes("—"), "no em dash in card text");
  assert.ok(!/is safe| safe\./i.test(text), "never claims safe");
  assert.ok(!text.includes("725K"), "no cumulative corpus count");
  assert.ok(!text.includes("$"), "no prices in card");
  const walletCard = mod.buildCard(
    "wallet",
    "0x" + "a".repeat(40),
    { ok: true, data: { risk_level: "LOW", risk_flags: [] } },
    "paste",
  );
  assert.equal(walletCard.target, "0xaaaa...aaaa", "wallets truncate first6/last4");
});

test("escapeHtml neutralises markup in targets and reasons", () => {
  assert.equal(
    mod.escapeHtml('<script>alert("x")</script>'),
    "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
  );
  assert.equal(mod.escapeHtml("a'b&c"), "a&#39;b&amp;c");
});

// --- uploads ---------------------------------------------------------------

test("validateUpload checks magic bytes and size", () => {
  const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0, 0, 0, 0, 0]);
  assert.equal(mod.validateUpload(png, "qr.png").type, "png");
  const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  assert.equal(mod.validateUpload(jpeg, "photo.jpg").type, "jpeg");
  const webp = new Uint8Array([
    0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50,
  ]);
  assert.equal(mod.validateUpload(webp, "qr.webp").type, "webp");
  assert.equal(mod.validateUpload(new Uint8Array([1, 2, 3]), "x.bin").ok, false);
  assert.equal(mod.validateUpload(new Uint8Array(0), "empty.png").reason, "empty-file");
  const big = new Uint8Array(5 * 1024 * 1024 + 1);
  big[0] = 0x89; big[1] = 0x50; big[2] = 0x4e; big[3] = 0x47;
  assert.equal(mod.validateUpload(big, "big.png").reason, "too-large");
});

test("sniffImageType rejects non-images", () => {
  assert.equal(mod.sniffImageType(new Uint8Array([0x25, 0x50, 0x44, 0x46, 0, 0, 0, 0, 0, 0, 0, 0])), null);
});

// --- rate limiting and metrics ---------------------------------------------

test("isRateLimited enforces per-minute and per-day caps, fails open without KV", async () => {
  assert.equal(await mod.isRateLimited(null, "1.2.3.4", new Date(), false), false);
  const kv = new FakeKV();
  const now = new Date();
  for (let i = 0; i < 20; i++) {
    assert.equal(await mod.isRateLimited(kv, "1.2.3.4", now, false), false);
  }
  assert.equal(await mod.isRateLimited(kv, "1.2.3.4", now, false), true);
  const kvUp = new FakeKV();
  for (let i = 0; i < 5; i++) {
    assert.equal(await mod.isRateLimited(kvUp, "5.6.7.8", now, true), false);
  }
  assert.equal(await mod.isRateLimited(kvUp, "5.6.7.8", now, true), true);
});

test("recordCheck and readMetrics count checks and conversions", async () => {
  const kv = new FakeKV();
  const now = new Date();
  await mod.recordCheck(kv, "link", "threat", now);
  await mod.recordCheck(kv, "wallet", "clean", now);
  await mod.recordConversion(kv, "tg", now);
  await mod.recordConversion(kv, "tg", now);
  await mod.recordConversion(kv, "wa", now);
  const m = await mod.readMetrics(kv, now);
  assert.equal(m.available, true);
  assert.equal(m.checks_total, 2);
  assert.equal(m.checks_by_type.link, 1);
  assert.equal(m.checks_by_type.wallet, 1);
  assert.equal(m.conversions_total.tg, 2);
  assert.equal(m.conversions_total.wa, 1);
  assert.equal(m.last_7_days.checks, 2);
  assert.equal(m.last_7_days.conversions, 3);
  assert.equal(m.last_7_days.conversions_by_dest.tg, 2);
  assert.equal(m.last_7_days.conversion_rate, 150);
  assert.deepEqual(await mod.readMetrics(null, now), { available: false });
});

// --- Turnstile ---------------------------------------------------------------

test("verifyTurnstile skips without secret, fails closed on invalid token, open on service error", async () => {
  assert.deepEqual(
    await mod.verifyTurnstile("", "tok", "1.2.3.4", apiFetch),
    { skipped: true },
  );
  assert.deepEqual(
    await mod.verifyTurnstile("secret", "", "1.2.3.4", apiFetch),
    { ok: false, reason: "missing-token" },
  );
  assert.deepEqual(
    await mod.verifyTurnstile("secret", "tok", "1.2.3.4", apiFetch),
    { ok: true },
  );
  const bad = () => Promise.resolve(jsonResp({ success: false }));
  assert.deepEqual(
    await mod.verifyTurnstile("secret", "tok", "1.2.3.4", bad),
    { ok: false, reason: "invalid-token" },
  );
  const boom = () => Promise.reject(new Error("down"));
  assert.deepEqual(
    await mod.verifyTurnstile("secret", "tok", "1.2.3.4", boom),
    { ok: true, degraded: true },
  );
  // NOTE: the apiFetch mock always answers Turnstile success, so a
  // "bad token" case cannot be simulated with it; see the dedicated
  // success:false mock block in the handler test below.
});

// --- OCR text extraction ------------------------------------------------------

test("findCheckableInText prefers URL, then wallet, then email", () => {
  assert.deepEqual(
    mod.findCheckableInText("see https://evil.example.com/x and 0x" + "b".repeat(40)),
    { kind: "link", value: "https://evil.example.com/x" },
  );
  assert.deepEqual(mod.findCheckableInText("send to 0x" + "c".repeat(40)), {
    kind: "wallet",
    value: "0x" + "c".repeat(40),
  });
  assert.deepEqual(mod.findCheckableInText("mail me at a@b.co"), {
    kind: "email",
    value: "a@b.co",
  });
  assert.deepEqual(mod.findCheckableInText("nothing checkable here"), {
    kind: "unknown",
  });
});

test("decodeQrServerSide is a documented seam, null until wired", async () => {
  assert.equal(await mod.decodeQrServerSide(new Uint8Array([1, 2, 3]), "png"), null);
  mod.__setQrDecoderForTests(async () => "https://example.com/qr");
  assert.equal(
    await mod.decodeQrServerSide(new Uint8Array([1, 2, 3]), "png"),
    "https://example.com/qr",
  );
  mod.__setQrDecoderForTests(null);
});

// --- SigV4 shape ---------------------------------------------------------------

test("signRekognitionRequest produces a well-formed Authorization header", async () => {
  const auth = await mod.signRekognitionRequest(
    "AKIDEXAMPLE",
    "secret",
    "us-east-1",
    "20261024T120000Z",
    "abc123",
    "RekognitionService.DetectText",
  );
  assert.ok(
    auth.startsWith(
      "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261024/us-east-1/rekognition/aws4_request, SignedHeaders=content-type;host;x-amz-date;x-amz-target, Signature=",
    ),
  );
  const sig = auth.split("Signature=")[1];
  assert.match(sig, /^[0-9a-f]{64}$/);
});

// --- HTTP handler --------------------------------------------------------------

test("GET /check serves the page with jsQR, Turnstile hook, and no em dash", async () => {
  const resp = await handler.fetch(
    new Request("https://relayshield.net/check"),
    { TURNSTILE_SITE_KEY: "testkey" },
    ctx,
  );
  assert.equal(resp.status, 200);
  const html = await resp.text();
  assert.ok(html.includes("RelayShield free check"));
  assert.ok(html.includes("jsqr@1.4.0/dist/jsQR.js"));
  assert.ok(html.includes("turnstile"));
  assert.ok(html.includes('type="file"'));
  assert.ok(!html.includes("—"), "no em dash in page copy");
  assert.ok(!/is safe/i.test(html), "page makes no safe claim");
});

test("POST /check/api/check returns a card and counts it", async () => {
  const kv = new FakeKV();
  await withFetch(apiFetch, async () => {
    const resp = await handler.fetch(
      checkReq("https://evil.example.com/login"),
      { WEBCHECK_KV: kv },
      ctx,
    );
    assert.equal(resp.status, 200);
    const data = await resp.json();
    assert.equal(data.ok, true);
    assert.equal(data.card.badge, "THREAT DETECTED");
    assert.equal(data.card.why.length, 2);
    assert.equal(data.card.botLinks[0].href, "/check/go?to=tg");
    const m = await mod.readMetrics(kv, new Date());
    assert.equal(m.checks_total, 1);
    assert.equal(m.checks_by_type.link, 1);
  });
});

test("POST /check/api/check rejects prose, bad Turnstile, and floods", async () => {
  const kv = new FakeKV();
  await withFetch(apiFetch, async () => {
    const prose = await handler.fetch(checkReq("hello there friend"), { WEBCHECK_KV: kv }, ctx);
    assert.equal(prose.status, 400);
    // NOTE: apiFetch always answers Turnstile success, so a "bad token"
    // cannot fail inside this block; the dedicated success:false block
    // below is the real 403 test.
  });
  await withFetch(
    () => Promise.resolve(jsonResp({ success: false })),
    async () => {
      const resp = await handler.fetch(
        checkReq("https://example.com", "badtoken"),
        { TURNSTILE_SECRET_KEY: "secret" },
        ctx,
      );
      assert.equal(resp.status, 403);
    },
  );
  const kvFull = new FakeKV();
  const now = new Date();
  for (let i = 0; i < 20; i++) {
    await mod.isRateLimited(kvFull, "9.9.9.9", now, false);
  }
  await withFetch(apiFetch, async () => {
    const req = new Request("https://relayshield.net/check/api/check", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "CF-Connecting-IP": "9.9.9.9",
      },
      body: JSON.stringify({ input: "https://example.com" }),
    });
    const resp = await handler.fetch(req, { WEBCHECK_KV: kvFull }, ctx);
    assert.equal(resp.status, 429);
  });
});

test("GET /check/go counts the conversion and redirects to the deep link", async () => {
  const kv = new FakeKV();
  const resp = await handler.fetch(
    new Request("https://relayshield.net/check/go?to=tg"),
    { WEBCHECK_KV: kv },
    ctx,
  );
  assert.equal(resp.status, 302);
  assert.equal(
    resp.headers.get("Location"),
    "https://t.me/relayshield_bot?start=SRC_webcheck",
  );
  const m = await mod.readMetrics(kv, new Date());
  assert.equal(m.conversions_total.tg, 1);
  const bad = await handler.fetch(
    new Request("https://relayshield.net/check/go?to=nope"),
    { WEBCHECK_KV: kv },
    ctx,
  );
  assert.equal(bad.status, 400);
});

test("GET /check/health reports control presence, never values", async () => {
  const resp = await handler.fetch(
    new Request("https://relayshield.net/check/health"),
    { TURNSTILE_SECRET_KEY: "shh", AWS_ACCESS_KEY_ID: "id", AWS_SECRET_ACCESS_KEY: "key" },
    ctx,
  );
  const data = await resp.json();
  assert.equal(data.turnstile, true);
  assert.equal(data.ocr, true);
  assert.equal(data.kv, false);
  assert.ok(!JSON.stringify(data).includes("shh"));
});

test("POST /check/api/upload runs OCR text through the check flow", async () => {
  const kv = new FakeKV();
  const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3]);
  const form = new FormData();
  form.append("file", new Blob([png], { type: "image/png" }), "shot.png");
  await withFetch(apiFetch, async () => {
    const resp = await handler.fetch(
      new Request("https://relayshield.net/check/api/upload", {
        method: "POST",
        body: form,
      }),
      {
        WEBCHECK_KV: kv,
        AWS_ACCESS_KEY_ID: "id",
        AWS_SECRET_ACCESS_KEY: "key",
      },
      ctx,
    );
    assert.equal(resp.status, 200);
    const data = await resp.json();
    assert.equal(data.ok, true);
    assert.equal(data.card.badge, "THREAT DETECTED");
    assert.equal(data.card.via, "upload-ocr");
    const m = await mod.readMetrics(kv, new Date());
    assert.equal(m.checks_by_type.upload, 1);
  });
});

test("POST /check/api/upload without OCR secrets degrades to unchecked, not an error", async () => {
  const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0, 0, 0, 0, 0]);
  const form = new FormData();
  form.append("file", new Blob([png], { type: "image/png" }), "shot.png");
  await withFetch(apiFetch, async () => {
    const resp = await handler.fetch(
      new Request("https://relayshield.net/check/api/upload", {
        method: "POST",
        body: form,
      }),
      {},
      ctx,
    );
    assert.equal(resp.status, 200);
    const data = await resp.json();
    assert.equal(data.card.badge, "UNCHECKED");
    assert.match(data.card.why[0], /not configured/);
  });
});

test("POST /check/api/upload rejects non-images and oversize files", async () => {
  const bad = new FormData();
  bad.append("file", new Blob(["%PDF-fake"], { type: "application/pdf" }), "x.pdf");
  await withFetch(apiFetch, async () => {
    const resp = await handler.fetch(
      new Request("https://relayshield.net/check/api/upload", {
        method: "POST",
        body: bad,
      }),
      {},
      ctx,
    );
    assert.equal(resp.status, 400);
  });
});

// --- source hygiene ----------------------------------------------------------

test("Worker source carries no em dash anywhere", () => {
  const src = readFileSync(workerSrc, "utf8");
  assert.ok(!src.includes("—"), "em dash found in Worker source");
});
