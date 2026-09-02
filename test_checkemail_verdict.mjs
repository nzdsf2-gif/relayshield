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
src += "\nexport { buildReply, headerSignals, detectForwardedOriginal, parseAddress, extractAttachmentNames, attachmentSignals, pressureSignals, stripHtml, decodeEncodedWords, unwrap, publicHostSignal };\n";
const shim = new URL("./.checkemail_verdict_shim.mjs", import.meta.url);
writeFileSync(shim, src);
const { buildReply, headerSignals, detectForwardedOriginal, extractAttachmentNames, attachmentSignals, parseAddress: parseAddr, stripHtml, decodeEncodedWords, unwrap, publicHostSignal } = await import(shim.href);

const hdrs = (o) => ({ get: (k) => o[k.toLowerCase()] ?? null });

/** Run the real pipeline the way scanAndReply does. */
// A small stand-in for the real IANA list. The Worker fetches ~1,450 entries
// and caches them in KV; the check only needs a Set, so the tests supply one.
const TLDS = new Set(["com", "net", "org", "co", "uk", "io", "gmail", "aol",
                      "info", "biz", "de", "fr", "tld", "ru", "xyz", "top"]);

function verdict({ from, to = "", replyTo = "", headers = {}, body = "",
                   links = [], raw = "", tlds = TLDS }) {
  const email = {
    from: parseFrom(from),
    replyTo: [parseFrom(replyTo)],
    subject: headers.subject || "",
  };
  const forwarded = detectForwardedOriginal(body, (from.match(/<([^>]+)>/) || [])[1] || from);
  const sig = headerSignals(email, hdrs({ ...headers, "reply-to": replyTo }), forwarded, {
    bodyText: body,
    links,
    tlds,
    attachments: attachmentSignals(extractAttachmentNames(raw)),
    recipientLocal: (to || "").split("@")[0],
  });
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

console.log("\n-- a TLD that does not exist (the 2026-09-02 false negative) --");

// The real message, from the founder's spam folder, forwarded inline. Before
// this suite it scored 0 and came back LOW RISK.
const realPhish = verdict({
  from: '"Andrew Gibbs" <nzdsf2@gmail.com>',
  to: "nzdsf2@gmail.com",
  headers: { subject: "Fwd: Action Required: Storage 100% Full",
             "authentication-results": "spf=pass; dkim=pass; dmarc=pass" },
  body: "---------- Forwarded message ---------\n" +
        "From: nzdsf2 <alert-9626@ydxla.abn>\n" +
        "Date: Mon, Aug 31, 2026 at 12:11AM\n" +
        "Subject: Action Required: Storage 100% Full\nTo: <me@aol.com>\n\n" +
        "Payment failed for your Cloud storage renewal. We couldn't renew your\n" +
        "Cloud storage subscription. Update your payment details within 24 hours\n" +
        "or your files will be permanently deleted.\n" +
        "https://cloud-billing-update.ydxla.abn/renew\n",
  links: [{ url: "https://cloud-billing-update.ydxla.abn/renew", status: "unknown",
            detail: "no security vendor has published a verdict on this link yet" }],
});
expect("the real spam message is now HIGH", realPhish.risk, "HIGH");
expect("  ...it names the nonexistent TLD",
  realPhish.text.includes('There is no ".abn" on the internet'), true);
expect("  ...it names the ask-plus-pressure pattern",
  realPhish.text.includes("two halves of almost every"), true);
expect("  ...it spots the display name copying the recipient's own account name",
  realPhish.text.includes("which is your own account"), true);

expect("a real TLD is never called nonexistent",
  verdict({ from: '"Acme" <billing@acme.co.uk>', to: "andrew@x.com",
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "LOW");

expect("with no TLD list the check fails OPEN, not closed",
  verdict({ from: '"X" <a@thing.abn>', to: "andrew@x.com", tlds: null,
            headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" } }).risk, "LOW");

console.log("\n-- ask plus pressure, but never either alone --");

expect("an ask with no deadline or threat stays LOW",
  verdict({ from: '"Shop" <a@shop.com>', to: "andrew@x.com", headers: {},
            body: "Please click here to view your receipt." }).risk, "LOW");

expect("a deadline with no ask stays LOW",
  verdict({ from: '"Shop" <a@shop.com>', to: "andrew@x.com", headers: {},
            body: "Your invoice is due within 48 hours. Thanks for your business." }).risk, "LOW");

expect("ask plus threat is MEDIUM",
  verdict({ from: '"Shop" <a@shop.com>', to: "andrew@x.com", headers: {},
            body: "Verify your account or your account will be suspended." }).risk, "MEDIUM");

console.log("\n-- attachments, by name and type only --");

const att = (name) => "Content-Disposition: attachment; filename=\"" + name + "\"\r\n";

expect("a plain PDF is not flagged",
  verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
            raw: att("invoice.pdf") }).risk, "LOW");

expect("an .exe is HIGH",
  verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
            raw: att("setup.exe") }).risk, "HIGH");

const dbl = verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
                      raw: att("Invoice_2026.pdf.scr") });
expect("a double extension is HIGH", dbl.risk, "HIGH");
expect("  ...and is explained as a disguise",
  dbl.text.includes("wearing"), true);

expect("a macro-enabled Office file is MEDIUM",
  verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
            raw: att("Statement.xlsm") }).risk, "MEDIUM");

expect("an .iso is MEDIUM",
  verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
            raw: att("delivery.iso") }).risk, "MEDIUM");

const zip = verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
                      raw: att("photos.zip") });
expect("a plain archive is a note, not a flag", zip.risk, "LOW");
expect("  ...and says we cannot see inside it",
  zip.text.includes("cannot tell you what is inside"), true);

expect("a folded, unquoted filename is still read",
  extractAttachmentNames(
    "Content-Disposition: attachment;\r\n\tfilename=aRsVr-Carrier Requested Details.pdf\r\n")[0],
  "aRsVr-Carrier Requested Details.pdf");

expect("an RFC 2231 encoded filename is decoded",
  extractAttachmentNames(
    "Content-Disposition: attachment; filename*=UTF-8''fact%C3%BAra.pdf\r\n")[0],
  "fact\u00fara.pdf");

const noAtt = verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {} });
expect("the reply always states the attachment position",
  noAtt.text.includes("ATTACHMENTS: none."), true);

console.log("\n-- an HTML forward must still yield a sender (the score=0 bug) --");

// The live run on 2026-09-02 logged: forwarded=true score=0 flags=0, on the
// SAME .abn message that the plain-text test above rates HIGH. The forward was
// detected and then analysed against nothing, because Gmail quotes the original
// header block as HTML and stripHtml decoded only &nbsp; and &amp;. So the line
//     From: nzdsf2 &lt;alert-9626@ydxla.abn&gt;
// reached parseAddress with its angle brackets still entity-encoded, matched
// nothing, and every sender-based check silently had no sender to check.
const htmlFwdBody = stripHtml(
  '<div>FYI</div><div class="gmail_quote">' +
  '<div dir="ltr" class="gmail_attr">---------- Forwarded message ---------<br>' +
  'From: <b>nzdsf2</b> &lt;<a href="mailto:alert-9626@ydxla.abn">alert-9626@ydxla.abn</a>&gt;<br>' +
  'Date: Mon, Aug 31, 2026 at 12:11&nbsp;AM<br>' +
  'Subject: Action Required: Storage 100% Full<br>' +
  'To: &lt;me@aol.com&gt;<br></div><br>' +
  '<div>Update your payment details within 24 hours or your files will be ' +
  'permanently deleted.</div></div>');

expect("entities are decoded, so the angle brackets survive as characters",
  htmlFwdBody.includes("&lt;"), false);
expect("  ...and the address itself is in the extracted text",
  htmlFwdBody.includes("alert-9626@ydxla.abn"), true);

const htmlFwd = verdict({
  from: '"Andrew Gibbs" <nzdsf2@gmail.com>',
  to: "nzdsf2@gmail.com",
  headers: { subject: "Fwd: Action Required: Storage 100% Full",
             "authentication-results": "spf=pass; dkim=pass; dmarc=pass" },
  body: htmlFwdBody,
  links: [{ url: "https://cloud-billing-update.ydxla.abn/renew", status: "unknown",
            detail: "no security vendor has published a verdict on this link yet" }],
});
expect("the HTML forward recovers the original sender",
  htmlFwd.forwarded.address, "alert-9626@ydxla.abn");
expect("  ...and rates HIGH, not zero", htmlFwd.risk, "HIGH");

expect("an address with no angle brackets is still recovered",
  parseAddr("From: alert-9626@ydxla.abn").address, "alert-9626@ydxla.abn");
expect("a line with no address at all yields no address",
  parseAddr("Sender unknown").address, "");

console.log("\n-- the API envelope: link checking had never returned a verdict --");

// relayshield_api.py's _ok() returns { ok: true, data: { ... } }. scanLink read
// analysis_id and immediate_signal off the TOP level, where neither exists, so
// every link came back "no analysis was started" and the RelayShield IOC
// corpus, Google Safe Browsing and domain-age checks were never consulted.
expect("the envelope is unwrapped",
  unwrap({ ok: true, data: { analysis_id: "abc", immediate_signal: "flagged" } }).analysis_id, "abc");
expect("a bare payload passes through untouched",
  unwrap({ analysis_id: "xyz" }).analysis_id, "xyz");
expect("a null body does not throw", typeof unwrap(null), "object");

console.log("\n-- a legitimate host carrying somebody else's page --");

// The real forward's only links were storage.googleapis.com/midfielders/*.
// Domain reputation is useless: the domain is Google's and always will be.
const gcs = publicHostSignal([
  { url: "https://storage.googleapis.com/midfielders/midfielders.html?act=cl&pid=12406_md" },
]);
expect("storage.googleapis.com is recognised", gcs.length, 1);
expect("  ...and named by service", gcs[0].service, "storage.googleapis.com");
expect("a company's own domain is not flagged",
  publicHostSignal([{ url: "https://www.acme.com/invoice" }]).length, 0);
expect("an unparseable URL does not throw",
  publicHostSignal([{ url: "not a url" }]).length, 0);

const hostedPhish = verdict({
  from: '"Cloud Services" <billing@notify-cloud.com>', to: "andrew@x.com",
  headers: {},
  body: "Update your payment details within 24 hours or your files will be permanently deleted.",
  links: [{ url: "https://storage.googleapis.com/midfielders/midfielders.html?act=cl",
            status: "unknown", detail: "no verdict yet" }],
});
expect("public host + an ask under pressure reaches HIGH", hostedPhish.risk, "HIGH");
expect("  ...and explains why reputation cannot see it",
  hostedPhish.text.includes("borrows the host's good reputation"), true);
expect("the public host alone, with no ask, is only MEDIUM",
  verdict({ from: '"A" <a@b.com>', to: "andrew@x.com", headers: {},
            body: "Here are the slides from today.",
            links: [{ url: "https://storage.googleapis.com/x/y.html", status: "unknown", detail: "" }]
          }).risk, "MEDIUM");

console.log("\n-- never report the reader their own address as the sender --");

const selfFwd = verdict({
  from: '"Andrew Gibbs" <nzdsf2@gmail.com>', to: "nzdsf2@gmail.com",
  headers: { "authentication-results": "spf=pass; dkim=pass; dmarc=pass" },
  body: "---------- Forwarded message ---------\nFrom: Andrew Gibbs <nzdsf2@gmail.com>\nDate: x\n",
});
expect("a quoted From: matching the forwarder is treated as a parse failure",
  selfFwd.forwarded.parseFailed, true);
expect("  ...and is flagged as a self-match, not reported as a sender",
  selfFwd.forwarded.selfMatch, true);
expect("  ...so the reply never prints their own address as the original",
  selfFwd.text.includes("original sender shows in the quoted"), false);

console.log("\n-- RFC 2047 subjects must not reach the reader encoded --");

expect("a Q-encoded subject with an emoji is decoded",
  decodeEncodedWords("=?UTF-8?Q?Fwd=3A_=F0=9F=9A=A8_Action_Required?="),
  "Fwd: \u{1F6A8} Action Required");
expect("a B-encoded subject is decoded",
  decodeEncodedWords("=?UTF-8?B?SGVsbG8gd29ybGQ=?="), "Hello world");
expect("plain ASCII passes through untouched",
  decodeEncodedWords("Your invoice"), "Your invoice");
expect("a malformed encoded word is left alone rather than lost",
  decodeEncodedWords("=?UTF-8?X?whatever?="), "=?UTF-8?X?whatever?=");

console.log("\n--- the reply Andrew would now receive for his spam forward ---\n");
console.log(realPhish.text);

console.log("\n--- the reply Andrew would now receive for his test message ---\n");
console.log(andrew.text);

unlinkSync(shim);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
