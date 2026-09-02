// Tests for the RISK VERDICT produced by cloudflare_worker_checkemail.js.
//
// WHY THIS EXISTS
// ---------------
// On 2026-09-02 a genuine, unremarkable email from the founder's own Gmail came
// back MEDIUM RISK. The whole basis was one flag: the display name "Andrew
// Gibbs" does not appear inside the local part "nzdsf2". That is true of most
// Gmail accounts in existence, so the flag reduced to "this person has a Gmail
// address" while the risk model was `flags.length ? MEDIUM : LOW` -- any single
// observation, however ordinary, produced MEDIUM.
//
// A verdict a reader can dismiss by glancing at their own inbox is worse than
// no verdict, because it teaches them to ignore the next one. So the thing that
// needs a test is not "does it flag bad mail" but "does it stay quiet on
// ordinary mail". Both directions are below.
//
// RUN IT (no npm install, no network, no Cloudflare account):
//     node test_checkemail_verdict.mjs

import { readFileSync, writeFileSync, unlinkSync } from "node:fs";
let src = readFileSync(
  new URL("./cloudflare_worker_checkemail.js", import.meta.url), "utf8");
src = src.replace('import { EmailMessage } from "cloudflare:email";',
  'class EmailMessage { constructor(f,t,raw){ this.from=f; this.to=t; this.raw=raw; } }');
src += "\nexport { buildReply, headerSignals, detectForwardedOriginal, parseAddress };\n";
const shim = new URL("./.checkemail_verdict_shim.mjs", import.meta.url);
writeFileSync(shim, src);
const { buildReply, headerSignals, detectForwardedOriginal } = await import(shim.href);

const hdrs = (o) => ({ get: (k) => o[k.toLowerCase()] ?? null });

/** Run the real pipeline the way scanAndReply does. */
function verdict({ from, replyTo = "", headers = {}, body = "", links = [] }) {
  const email = {
    from: parseFrom(from),
    replyTo: [parseFrom(replyTo)],
    subject: headers.subject || "",
  };
  const forwarded = detectForwardedOriginal(body);
  const sig = headerSignals(email, hdrs({ ...headers, "reply-to": replyTo }), forwarded);
  const text = buildReply(sig, links, email.subject, forwarded);
  return { risk: text.split(" RISK")[0].replace("RelayShield email check: ", ""), text, sig, forwarded };
}
function parseFrom(v) {
  if (!v) return { name: "", address: "" };
  const m = v.match(/^\s*"?([^"<]*)"?\s*<([^>]+)>\s*$/);
  return m ? { name: m[1].trim(), address: m[2].trim().toLowerCase() }
           : { name: "", address: v.trim().toLowerCase() };
}

let pass = 0, fail = 0;
function expect(name, got, want) {
  const ok = got === want;
  ok ? pass++ : fail++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${name}${ok ? "" : `   got ${got}, want ${want}`}`);
}

console.log("-- must stay QUIET on ordinary mail (the 2026-09-02 regression) --");

// The exact message that produced the undefendable MEDIUM.
const andrew = verdict({
  from: '"Andrew Gibbs" <nzdsf2@gmail.com>',
  headers: {
    subject: "Test Message",
    "authentication-results": "mx.cloudflare.net; spf=pass; dkim=pass; dmarc=pass",
  },
  body: "https://www.evil.com\n",
  links: [{ url: "https://www.evil.com", status: "unknown",
            detail: "no security vendor has published a verdict on this link yet" }],
});
expect("real person, own Gmail, all auth passing, one unknown link", andrew.risk, "LOW");
expect("  ...and produced no flags at all", andrew.sig.flags.length, 0);

expect("plain webmail user, name unrelated to address",
  verdict({ from: '"Bob Kramich" <bk8842@yahoo.com>',
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "LOW");

expect("newsletter with a Return-Path on a different domain",
  verdict({ from: '"Acme News" <news@acme.com>',
            headers: { "return-path": "<bounce@sendgrid.net>",
                       "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "LOW");

expect("  ...and says so as a note, not a flag",
  verdict({ from: '"Acme News" <news@acme.com>',
            headers: { "return-path": "<bounce@sendgrid.net>",
                       "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).sig.notes.length, 1);

expect("forwarded mail with SPF softfail only",
  verdict({ from: '"Someone" <s@example.com>',
            headers: { "authentication-results": "spf=softfail; dkim=pass; dmarc=pass" } }).risk, "LOW");

console.log("\n-- must SPEAK UP on the real thing --");

expect("DMARC fail",
  verdict({ from: '"PayPal" <service@paypal.com>',
            headers: { "authentication-results": "spf=fail; dkim=fail; dmarc=fail" } }).risk, "HIGH");

expect("brand display name on free webmail",
  verdict({ from: '"PayPal Support" <paypal.secure.9931@gmail.com>',
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "HIGH");

expect("courier brand on free webmail",
  verdict({ from: '"DHL Delivery" <dhl.parcel.uk@outlook.com>', headers: {} }).risk, "HIGH");

expect("authority role name on free webmail",
  verdict({ from: '"IT Security Team" <itsec99@gmail.com>',
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "MEDIUM");

expect("Reply-To on a different domain",
  verdict({ from: '"Finance" <ap@supplier.com>', replyTo: "ap.supplier@mail.ru",
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "MEDIUM");

expect("one malicious link alone",
  verdict({ from: '"A" <a@b.com>', headers: {},
            links: [{ url: "http://x.tld", status: "malicious", detail: "8 of 94 vendors" }] }).risk, "HIGH");

expect("one suspicious link alone",
  verdict({ from: '"A" <a@b.com>', headers: {},
            links: [{ url: "http://x.tld", status: "suspicious", detail: "registered 2 days ago" }] }).risk, "MEDIUM");

expect("suspicious link plus Reply-To mismatch compounds to HIGH",
  verdict({ from: '"A" <a@b.com>', replyTo: "z@evil.tld", headers: {},
            links: [{ url: "http://x.tld", status: "suspicious", detail: "new domain" }] }).risk, "HIGH");

console.log("\n-- inline forwards: never claim we checked the original --");

const gmailFwd = verdict({
  from: '"Andrew Gibbs" <nzdsf2@gmail.com>',
  headers: { subject: "Fwd: Your account is locked",
             "authentication-results": "spf=pass; dkim=pass; dmarc=pass" },
  body: "FYI\n\n---------- Forwarded message ---------\n" +
        "From: PayPal Service <paypal.alerts.44@gmail.com>\n" +
        "Date: Mon, 1 Sep 2026\nSubject: Your account is locked\nTo: <nzdsf2@gmail.com>\n\n" +
        "Click here https://paypa1-secure.tld\n",
});
expect("Gmail forward is detected", Boolean(gmailFwd.forwarded), true);
expect("  ...original sender is recovered from the quoted block",
  gmailFwd.forwarded.address, "paypal.alerts.44@gmail.com");
expect("  ...impersonation is judged on the ORIGINAL, not the forwarder",
  gmailFwd.risk, "HIGH");
expect("  ...and the forwarder's passing DMARC is NOT reported as a pass",
  gmailFwd.text.includes("SENDER CHECKS PASSED"), false);
expect("  ...the reply says the original's authentication was stripped",
  gmailFwd.text.includes("strips the original SPF, DKIM and DMARC"), true);
expect("  ...and tells the user how to get a real answer",
  gmailFwd.text.includes("Forward as attachment"), true);

const appleFwd = verdict({
  from: '"A" <a@b.com>',
  headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" },
  body: "Begin forwarded message:\n\nFrom: Chase Alerts <chase.verify@gmail.com>\nSubject: x\n",
});
expect("Apple Mail forward is detected", appleFwd.forwarded.address, "chase.verify@gmail.com");

const outlookFwd = verdict({
  from: '"A" <a@b.com>', headers: {},
  body: "-----Original Message-----\nFrom: HMRC Refunds <hmrc.refund@outlook.com>\nSent: x\n",
});
expect("Outlook forward is detected", outlookFwd.forwarded.address, "hmrc.refund@outlook.com");

expect("a normal message is NOT mistaken for a forward",
  detectForwardedOriginal("Hi, here is the link you asked for: https://x.tld\nThanks\n"), null);

console.log("\n-- unknown links must never move the rating --");
const withUnknown = verdict({
  from: '"A" <a@b.com>', headers: { "authentication-results": "spf=pass; dmarc=pass" },
  links: [
    { url: "http://a.tld", status: "unknown", detail: "no security vendor has published a verdict on this link yet" },
    { url: "http://b.tld", status: "unknown", detail: "no security vendor has published a verdict on this link yet" },
    { url: "http://c.tld", status: "unknown", detail: "no security vendor has published a verdict on this link yet" },
  ],
});
expect("three unknown links still LOW", withUnknown.risk, "LOW");
expect("  ...and the reply says UNKNOWN is not a finding",
  withUnknown.text.includes("UNKNOWN is not a finding"), true);

console.log("\n--- the reply Andrew would now receive for his test message ---\n");
console.log(andrew.text);

unlinkSync(shim);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
