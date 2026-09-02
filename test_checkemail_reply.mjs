// Tests for the reply MIME message built by cloudflare_worker_checkemail.js.
//
// WHY THIS EXISTS
// ---------------
// On 2026-09-02 the Worker deployed cleanly, answered /health, accepted mail,
// and sent no reply -- 6 errors across 8 requests, with nothing on the
// dashboard saying why. The cause was that makeReply() built a message that is
// not a valid RFC 5322 message, and Cloudflare validates the raw bytes before
// it will send them. It had no Message-ID, no Date, an empty In-Reply-To when
// the original had none, and a body joined with bare LF inside a CRLF message.
//
// None of that is visible by reading the function. All of it is caught by
// building one message and looking at the bytes, which is what this does.
//
// RUN IT (no npm install, no network, no Cloudflare account):
//     node test_checkemail_reply.mjs
//
// It shims "cloudflare:email" so the real source file can be imported outside
// the Workers runtime. The source is read, not copied, so this cannot drift
// from the thing it tests.

import { readFileSync, writeFileSync, unlinkSync } from "node:fs";
let src = readFileSync(
  new URL("./cloudflare_worker_checkemail.js", import.meta.url), "utf8");
src = src.replace('import { EmailMessage } from "cloudflare:email";',
  'class EmailMessage { constructor(f,t,raw){ this.from=f; this.to=t; this.raw=raw; } }');
src += "\nexport { makeReply, buildReply, headerSignals, detectForwardedOriginal, parseAddress };\n";
const shim = new URL("./.checkemail_shim.mjs", import.meta.url);
writeFileSync(shim, src);
const { makeReply } = await import(shim.href);

const mk = (hdrs, from) => ({
  from,
  headers: { get: (k) => hdrs[k.toLowerCase()] ?? null },
});

function check(name, msg, text) {
  const em = makeReply(msg, text);
  const raw = em.raw;
  const [head, ...rest] = raw.split("\r\n\r\n");
  const body = rest.join("\r\n\r\n");
  const problems = [];
  if (/\n/.test(head.replace(/\r\n/g, ""))) problems.push("bare LF in headers");
  if (/(^|[^\r])\n/.test(body)) problems.push("bare LF in body");
  for (const h of ["From:", "To:", "Message-ID:", "Date:", "Subject:", "MIME-Version:", "Content-Type:"]) {
    if (!head.includes(h)) problems.push("missing " + h);
  }
  for (const line of head.split("\r\n")) {
    if (/:\s*$/.test(line)) problems.push("empty header value: " + line.trim());
  }
  if ([...raw].some((c) => c.charCodeAt(0) > 126)) problems.push("non-ASCII in 7bit message");
  console.log((problems.length ? "FAIL " : "ok   ") + name + (problems.length ? "  " + problems.join("; ") : ""));
  return problems.length === 0;
}

let ok = true;
ok &= check("normal gmail message",
  mk({ "message-id": "<abc@mail.gmail.com>", subject: "Fwd: your account" }, "nzdsf2@gmail.com"),
  "RelayShield email check: HIGH RISK\n\nDMARC FAILED.\n");
ok &= check("no Message-ID on original",
  mk({ subject: "hello" }, "nzdsf2@gmail.com"),
  "RelayShield email check: LOW RISK\n");
ok &= check("no Subject on original",
  mk({ "message-id": "<x@y>" }, "nzdsf2@gmail.com"),
  "line one\nline two\n");
ok &= check("unicode subject (attacker-controlled)",
  mk({ "message-id": "<x@y>", subject: "Ваш аккаунт заблокирован — действуй" }, "a@b.com"),
  "body\n");
ok &= check("header-injection attempt in subject",
  mk({ "message-id": "<x@y>", subject: "hi\r\nBcc: victim@example.com" }, "a@b.com"),
  "body\n");
ok &= check("em-dash inside reply body",
  mk({ "message-id": "<x@y>", subject: "s" }, "a@b.com"),
  "RelayShield — verdict\n");

// THREADING. These are the cases that took down the first real forward.
//
// Cloudflare validates References against the thread and rejects the reply if
// it disagrees. The value it wants is the INCOMING message's References chain
// with the incoming Message-ID appended -- not the Message-ID alone, which is
// what an earlier version of makeReply sent:
//
//   Error: provided References header is invalid; expected
//   <51977-nzdsf2@sH994It.abn> <CAA5...@mail.gmail.com> <CAA5...@mail.gmail.com>
//
// It never showed on a freshly composed test message, because one has no chain.
// It showed on the first forward, because every forward has one.
function refsOf(raw) {
  const line = raw.split("\r\n\r\n")[0].split("\r\n")
    .find((l) => l.toLowerCase().startsWith("references:"));
  return line ? line.slice("References:".length).trim() : null;
}

const chain = "<51977-nzdsf2@sH994It.abn> <CAA5aaa@mail.gmail.com>";
const own = "<CAA5bbb@mail.gmail.com>";
const threaded = makeReply(
  mk({ "message-id": own, references: chain, subject: "Fwd: spam" }, "nzdsf2@gmail.com"), "b\n").raw;
const gotRefs = refsOf(threaded);
const wantRefs = `${chain} ${own}`;
console.log((gotRefs === wantRefs ? "ok   " : "FAIL ") +
  "References = incoming chain + incoming Message-ID" +
  (gotRefs === wantRefs ? "" : `\n       got:  ${gotRefs}\n       want: ${wantRefs}`));
ok &= gotRefs === wantRefs;

const noChain = refsOf(makeReply(mk({ "message-id": own }, "a@b.com"), "b\n").raw);
console.log((noChain === own ? "ok   " : "FAIL ") +
  "no incoming chain: References is just the Message-ID");
ok &= noChain === own;

const noId = refsOf(makeReply(mk({ subject: "x" }, "a@b.com"), "b\n").raw);
console.log((noId === null ? "ok   " : "FAIL ") +
  "no Message-ID at all: References is omitted, never sent empty");
ok &= noId === null;

// Explicit: the injected Bcc must not have become a header.
const inj = makeReply(mk({ "message-id": "<x@y>", subject: "hi\r\nBcc: victim@example.com" }, "a@b.com"), "b\n");
const headBlock = inj.raw.split("\r\n\r\n")[0];
// It is fine for "Bcc:" to appear as TEXT inside the Subject value. What must
// never happen is it appearing at the START of a line, which is a real header.
const smuggled = headBlock.split("\r\n").some((l, i) => i > 0 && /^bcc:/i.test(l));
console.log((smuggled ? "FAIL " : "ok   ") + "no Bcc smuggled as its own header line");
ok &= !smuggled;
const crlfInFrom = makeReply(mk({ "message-id": "<x@y>" }, "a@b.com\r\nBcc: v@e.com"), "b\n").raw;
const injFrom = crlfInFrom.split("\r\n\r\n")[0].split("\r\n").some((l) => /^bcc:/i.test(l));
console.log((injFrom ? "FAIL " : "ok   ") + "CRLF in envelope sender cannot inject a header");
ok &= !injFrom;

console.log("\n--- sample reply ---");
console.log(JSON.stringify(makeReply(mk({ "message-id": "<abc@mail.gmail.com>", subject: "Fwd: your account" }, "nzdsf2@gmail.com"), "RelayShield email check: HIGH RISK\n\nDMARC FAILED.\n").raw));
console.log(ok ? "\nALL REPLY CASES PASS" : "\nFAILURES ABOVE");
unlinkSync(shim);
process.exit(ok ? 0 : 1);
