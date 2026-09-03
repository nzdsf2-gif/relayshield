/**
 * Tests for the JS widget. No network.
 *
 *   node widget/relayshield-widget.test.mjs
 *
 * Deliberately mirrors test_relayshield_widget.py case for case. The two client
 * files are ports of each other and the failure mode that matters is one of
 * them quietly diverging: same input, different verdict, in someone else's bot.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { check, classify, API_BASE, SOURCE } from "./relayshield-widget.js";

function transport(response, { throws = null } = {}) {
  const calls = [];
  const t = async (url, payload, timeoutMs, apiKey) => {
    calls.push({ url, payload, timeoutMs, apiKey });
    if (throws) throw throws;
    return response;
  };
  t.calls = calls;
  return t;
}

const link = (level, reasons = []) => ({ ok: true, data: { level, reasons } });
const wallet = (risk_level, risk_flags = []) => ({ ok: true, data: { risk_level, risk_flags } });

test("classify: urls, bare domains, addresses, prose", () => {
  for (const raw of ["https://a.example/x", "http://a.example", "a.example.com/path"]) {
    const [kind, norm] = classify(raw);
    assert.equal(kind, "url", raw);
    assert.ok(norm.startsWith("http"));
  }
  assert.equal(classify("scam-site.xyz")[1], "https://scam-site.xyz");
  for (const raw of [
    "0x" + "a".repeat(40),
    "EQ" + "A".repeat(46),
    "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
  ]) {
    assert.equal(classify(raw)[0], "address", raw);
  }
  for (const raw of ["", "   ", "hello there", "check this out for me"]) {
    assert.equal(classify(raw)[0], "unsupported", JSON.stringify(raw));
  }
});

test("classify: ronin prefix is normalised, not rejected", () => {
  const [kind, norm] = classify("ronin:0x" + "b".repeat(40));
  assert.equal(kind, "address");
  assert.equal(norm, "0x" + "b".repeat(40));
});

test("routing: url to link-check with attribution, address to wallet-risk", async () => {
  const t1 = transport(link("high", ["listed"]));
  await check("https://a.example", { transport: t1 });
  assert.ok(t1.calls[0].url.endsWith("/v1/link-check"));
  assert.equal(t1.calls[0].payload.source, SOURCE);
  assert.equal(t1.calls[0].url.startsWith(API_BASE), true);

  const t2 = transport(wallet("LOW"));
  await check("0x" + "c".repeat(40), { transport: t2 });
  assert.ok(t2.calls[0].url.endsWith("/v1/wallet-risk"));
});

test("routing: unsupported input makes no call", async () => {
  const t = transport(link("high"));
  const v = await check("just some words", { transport: t });
  assert.equal(t.calls.length, 0);
  assert.equal(v.blocked, false);
});

test("routing: api key passed through, timeout suits a handler", async () => {
  const t = transport(link("unknown"));
  await check("https://a.example", { apiKey: "rs_live_x", transport: t });
  assert.equal(t.calls[0].apiKey, "rs_live_x");
  assert.ok(t.calls[0].timeoutMs <= 5000);
});

test("never throws: transport failure is an unchecked verdict", async () => {
  for (const err of [new Error("timeout"), new TypeError("fetch failed")]) {
    const v = await check("https://a.example", { transport: transport(null, { throws: err }) });
    assert.equal(v.ok, false);
    assert.equal(v.level, "unknown");
    assert.equal(v.blocked, false);
  }
});

test("never throws: error envelope and garbage bodies", async () => {
  const capped = await check("https://a.example", {
    transport: transport({ ok: false, error: "Daily limit reached" }),
  });
  assert.equal(capped.ok, false);
  assert.equal(capped.blocked, false);

  for (const body of [null, [], "nope", { data: {} }]) {
    const v = await check("https://a.example", { transport: transport(body) });
    assert.equal(v.level, "unknown");
  }
});

test("an unrecognised level from the server is not trusted", async () => {
  const v = await check("https://a.example", { transport: transport(link("SAFE")) });
  assert.equal(v.level, "unknown");
});

test("never says safe: clean carries the caveat, failure says unchecked", async () => {
  const clean = await check("https://a.example", { transport: transport(link("unknown")) });
  assert.match(clean.text, /not proof of safety/);

  const failed = await check("https://a.example", {
    transport: transport(null, { throws: new Error("x") }),
  });
  assert.match(failed.text, /did not complete/);
  assert.match(failed.text, /not as safe/);
  assert.match(failed.html, /did not complete/);
});

test("blocked: high and critical block, medium warns", async () => {
  for (const level of ["high", "critical"]) {
    const v = await check("https://a.example", { transport: transport(link(level)) });
    assert.equal(v.blocked, true, level);
  }
  const med = await check("https://a.example", { transport: transport(link("medium")) });
  assert.equal(med.blocked, false);
});

test("wallet: CLEAN maps to low, flags are readable", async () => {
  const clean = await check("0x" + "d".repeat(40), { transport: transport(wallet("CLEAN")) });
  assert.equal(clean.level, "low");
  const hit = await check("0x" + "e".repeat(40), {
    transport: transport(wallet("HIGH", ["sanctions_hit", "high_tx_volume"])),
  });
  assert.equal(hit.blocked, true);
  assert.ok(hit.reasons.includes("sanctions hit"));
});

test("telegram markdown: underscores stay inside a code span", async () => {
  const url = "https://evil.example/reset_your_account_now";
  const v = await check(url, { transport: transport(link("high")) });
  const body = v.text.split("_Checked with")[0];
  assert.ok(body.includes("`" + url + "`"));
  assert.equal((body.match(/`/g) || []).length % 2, 0);
});

test("telegram markdown: backticks cannot close the code span", async () => {
  const v = await check("https://evil.example/`whoami`", { transport: transport(link("high")) });
  const body = v.text.split("_Checked with")[0];
  assert.equal((body.match(/`/g) || []).length % 2, 0);
});

test("html escapes angle brackets, and attribution is present", async () => {
  const v = await check("https://evil.example/<script>", { transport: transport(link("high")) });
  assert.match(v.html, /&lt;script&gt;/);
  assert.doesNotMatch(v.html, /<script>/);
  assert.match(v.text, /source=tg-widget/);
  assert.match(v.html, /source=tg-widget/);
});
