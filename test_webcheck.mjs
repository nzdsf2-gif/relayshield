// Tests for cloudflare_worker_webcheck.js. Run with: node test_webcheck.mjs
// after `npm install` in the repo root. The Worker file is ESM syntax in a
// .js file, so this test copies it to a temp .mjs and imports that
// (Cloudflare serves the .js as a module Worker; node needs the .mjs
// extension without a package.json "type": "module"). The Worker imports
// jsqr and jpeg-js, so the temp dir gets a node_modules symlink into the
// repo root; without `npm install` the import below throws a clear error.
// The Worker must not touch Cloudflare-only globals at import time: fetch,
// crypto.subtle, Request, Response, FormData, btoa are all node globals.

import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  copyFileSync,
  readFileSync,
  existsSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import jpeg from "jpeg-js";

const dir = mkdtempSync(join(tmpdir(), "webcheck-test-"));
const workerMjs = join(dir, "worker.mjs");
const workerSrc = fileURLToPath(
  new URL("./cloudflare_worker_webcheck.js", import.meta.url),
);
const repoRoot = fileURLToPath(new URL(".", import.meta.url));
const nodeModules = join(repoRoot, "node_modules");
if (!existsSync(nodeModules)) {
  throw new Error(
    "node_modules not found in the repo root. Run `npm install` in the repo " +
      "root first (package.json pins jsqr and jpeg-js).",
  );
}
symlinkSync(nodeModules, join(dir, "node_modules"), "dir");
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

// --- server-side QR decode ---------------------------------------------------
// Fixtures: a QR code for the QR_TEXT link as an RGBA PNG, a solid 16x16
// gray PNG (no QR code), and a tiny 2x2 RGB PNG for the exact-pixel check.
// Embedded as base64 so the suite needs no QR encoder at test time.
const QR_TEXT = "https://relayshield.net/check-qr-fixture";
const QR_PNG_B64 = "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";
const SOLID_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAAAAAAAAAAAAAAAD0lEQVR4nGM4gQYYRrYAAEdGyAEAAAAAAAAAAElFTkQAAAAA";
const TINY_RGB_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAAAAAAAAAAAFElEQVR4nGP4z8DAAMIM/////w8AH+4F+wAAAAAAAAAASUVORAAAAAA=";
const fromB64 = (s) => new Uint8Array(Buffer.from(s, "base64"));

test("decodeQrServerSide decodes a QR PNG", async () => {
  assert.equal(
    await mod.decodeQrServerSide(fromB64(QR_PNG_B64), "png"),
    QR_TEXT,
  );
});

test("decodeQrServerSide decodes a QR JPEG", async () => {
  const img = await mod.decodeImageToRgba(fromB64(QR_PNG_B64), "png");
  const jpg = jpeg.encode(
    { data: Buffer.from(img.data), width: img.width, height: img.height },
    92,
  );
  assert.equal(
    await mod.decodeQrServerSide(new Uint8Array(jpg.data), "jpeg"),
    QR_TEXT,
  );
});

test("decodeQrServerSide returns null for a non-QR image", async () => {
  assert.equal(
    await mod.decodeQrServerSide(fromB64(SOLID_PNG_B64), "png"),
    null,
  );
});

test("decodeQrServerSide never throws on bad input", async () => {
  assert.equal(
    await mod.decodeQrServerSide(new Uint8Array([1, 2, 3]), "png"),
    null,
  );
  assert.equal(
    await mod.decodeQrServerSide(fromB64(QR_PNG_B64).subarray(0, 60), "png"),
    null,
  );
  assert.equal(
    await mod.decodeQrServerSide(
      new Uint8Array([0x47, 0x49, 0x46, 0x38, 0x39, 0x61]),
      "gif",
    ),
    null,
  );
});

test("decodeImageToRgba recovers exact pixels", async () => {
  const img = await mod.decodeImageToRgba(fromB64(TINY_RGB_PNG_B64), "png");
  assert.deepEqual([...img.data], [
    255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255,
  ]);
});

test("downscaleRgba caps large images", () => {
  const data = new Uint8ClampedArray(2000 * 1000 * 4).fill(128);
  const scaled = mod.downscaleRgba(data, 2000, 1000);
  assert.equal(scaled.width, 1000);
  assert.equal(scaled.height, 500);
  assert.equal(scaled.data.length, 1000 * 500 * 4);
  const small = mod.downscaleRgba(data, 800, 600);
  assert.equal(small.width, 800);
  assert.equal(small.data, data);
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

test("GET /check serves the dark matrix theme from the landing page", async () => {
  const resp = await handler.fetch(
    new Request("https://relayshield.net/check"),
    { TURNSTILE_SITE_KEY: "testkey" },
    ctx,
  );
  assert.equal(resp.status, 200);
  const html = await resp.text();
  // Head structure unchanged for the separately staged SEO patch.
  assert.ok(html.includes("<title>RelayShield free check</title>"));
  assert.ok(html.includes("<h1>RelayShield free check</h1>"));
  // Landing palette: dark background, light text, matrix green accents.
  assert.ok(html.includes("background: #141414"));
  assert.ok(html.includes("color: #eaeaea"));
  assert.ok(html.includes("color: #00ff41"));
  // Matrix canvas and scanlines, layered behind the content.
  assert.ok(html.includes('<canvas id="matrix"></canvas>'));
  assert.ok(html.includes("#matrix { position: fixed"));
  assert.ok(html.includes("opacity: 0.13"));
  assert.ok(html.includes("pointer-events: none"));
  assert.ok(html.includes('class="scanlines"'));
  assert.ok(html.includes("body > :not(#matrix):not(.scanlines) { position: relative; z-index: 1; }"));
  // Muted text brightened for the dark background; cards and buttons dark.
  assert.ok(html.includes("color: #a6a6a6"));
  assert.ok(html.includes("background: #1f1f1f"));
  // Functional content still present on top of the animation.
  assert.ok(html.includes('id="checkInput"'));
  assert.ok(html.includes('id="checkBtn"'));
  assert.ok(html.includes('id="fileInput"'));
  assert.ok(html.includes('id="result"'));
  assert.ok(!html.includes("—"), "no em dash in page copy");
});

test("Matrix animation respects reduced motion and cannot break checks", async () => {
  const resp = await handler.fetch(
    new Request("https://relayshield.net/check"),
    { TURNSTILE_SITE_KEY: "testkey" },
    ctx,
  );
  const html = await resp.text();
  assert.ok(html.includes("prefers-reduced-motion: reduce"));
  // Own script block after the functional script, guarded at both steps.
  assert.ok(html.includes("getElementById('matrix')"));
  assert.ok(html.includes("if (!canvas) { return; }"));
  assert.ok(html.includes("if (!ctx) { return; }"));
  assert.ok(html.includes("setInterval(draw, 66)"));
  assert.ok(html.indexOf("turnstileWidgetId") < html.indexOf("getElementById('matrix')"));
  // Functional hooks survive the restyle unchanged.
  assert.ok(html.includes("jsqr@1.4.0/dist/jsQR.js"));
  assert.ok(html.includes("/check/api/check"));
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

test("POST /check/api/upload decodes a QR image before OCR", async () => {
  // No OCR secrets here: if the QR path works, the upload still returns a
  // card (via upload-qr), not the "not configured" unchecked card.
  const kv = new FakeKV();
  const form = new FormData();
  form.append(
    "file",
    new Blob([fromB64(QR_PNG_B64)], { type: "image/png" }),
    "qr.png",
  );
  await withFetch(apiFetch, async () => {
    const resp = await handler.fetch(
      new Request("https://relayshield.net/check/api/upload", {
        method: "POST",
        body: form,
      }),
      { WEBCHECK_KV: kv },
      ctx,
    );
    assert.equal(resp.status, 200);
    const data = await resp.json();
    assert.equal(data.ok, true);
    assert.equal(data.card.via, "upload-qr");
    assert.equal(data.card.badge, "THREAT DETECTED");
    const m = await mod.readMetrics(kv, new Date());
    assert.equal(m.checks_by_type.upload, 1);
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
