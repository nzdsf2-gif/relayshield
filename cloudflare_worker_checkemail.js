/**
 * checkemail@relayshield.net — forward-an-email scanning (FD-8).
 *
 * A Cloudflare Email Worker. A user forwards a suspicious email; this parses it,
 * scores it, and replies in plain text with a verdict.
 *
 * WHY THIS IS A WORKER AND NOT A LAMBDA
 * ------------------------------------
 * Cloudflare Email Routing already terminates mail for relayshield.net and is
 * audited working (TODO item 23: 45/45 delivered over 30 days). Routing the
 * address to a Worker is a rule plus this file. Doing it in Lambda would mean
 * SES inbound, an S3 bucket, a rule set, an IAM policy and a deploy-map entry --
 * five new pieces of production surface for the same result.
 *
 * WHAT IT DOES THAT THE BOTS CANNOT
 * ---------------------------------
 * The bots see a message body. A forwarded email carries the envelope, the
 * Received: chain, and Authentication-Results -- an SPF/DKIM/DMARC verdict
 * already computed by the user's own provider. A DMARC fail on mail claiming to
 * be from a bank is the strongest single signal available anywhere in this
 * product, and it is stronger than Telegram's forward_origin, which is the best
 * the bots have. WhatsApp carries no sender at all.
 *
 * So the header analysis here is NOT a port of the bot analyser. It is the part
 * only email can do. Links still go to /v1/scan-url, which is the same corpus +
 * Google Safe Browsing + VirusTotal path every other surface uses -- one source
 * of truth for link verdicts.
 *
 * PRIVACY, DECIDED BEFORE THE FIRST COMMIT
 * ----------------------------------------
 * Forwarded mail is somebody else's correspondence. **The body is never stored.**
 * What leaves this Worker is the verdict and the extracted indicators. There is
 * no code path here that persists a body, and there must never be one -- adding
 * it later is the kind of change that is easy to make and impossible to undo for
 * mail already received.
 *
 * ZERO NPM DEPENDENCIES, DELIBERATELY
 * -----------------------------------
 * The first version imported postal-mime and would not build: Wrangler could not
 * resolve it, because this repo has no package.json and no node_modules, and
 * adding both to a repo of Python Lambdas and standalone Workers to obtain one
 * MIME parser is a poor trade. Cloudflare already parses the headers for us and
 * hands them over as message.headers, which is where every signal that matters
 * lives -- Authentication-Results, Reply-To, Return-Path, From. The only thing
 * the library was buying was body extraction, which is ~60 lines below.
 *
 * So this Worker imports exactly one thing, from the Cloudflare runtime itself.
 * It deploys with a single command and nothing to install.
 *
 * DEPLOY
 *   npx wrangler deploy --config wrangler.checkemail.toml
 *   Then: Cloudflare dashboard -> Email -> Email Routing -> Routing rules ->
 *   checkemail@relayshield.net -> Send to a Worker -> relayshield-checkemail
 *
 * Requires the RS_API_KEY secret and the CHECKEMAIL_RL KV namespace; see
 * wrangler.checkemail.toml.
 */

import { EmailMessage } from "cloudflare:email";

const API_BASE = "https://api.relayshield.net";

// Free tier. Deliberately generous per day and tight per hour: a worried person
// checks two or three things in a burst, an abuser sends hundreds.
const RATE_LIMIT_PER_HOUR = 5;
const RATE_LIMIT_PER_DAY = 20;

const MAX_LINKS_CHECKED = 5;      // an email can carry hundreds; check the first few
const MAX_BODY_CHARS = 20000;     // parse ceiling, never a storage ceiling

// ---------------------------------------------------------------------------
// Header analysis — the part only email can do
// ---------------------------------------------------------------------------

/**
 * Read the provider's own SPF/DKIM/DMARC verdict.
 *
 * Authentication-Results is written by the RECEIVING provider (Gmail,
 * Microsoft), not by the sender, so it cannot be forged by whoever sent the
 * mail. When a user forwards, their provider's header comes along with it.
 * That makes it the highest-confidence signal in the whole message.
 */
function parseAuthResults(headers) {
  const raw = (headers.get("authentication-results") || "").toLowerCase();
  if (!raw) return { present: false };
  const grab = (mech) => {
    const m = raw.match(new RegExp(`\\b${mech}=(\\w+)`));
    return m ? m[1] : null;
  };
  return {
    present: true,
    spf: grab("spf"),
    dkim: grab("dkim"),
    dmarc: grab("dmarc"),
  };
}

function domainOf(addr) {
  const m = (addr || "").match(/@([^\s>@]+)/);
  return m ? m[1].toLowerCase().replace(/\.$/, "") : "";
}

/**
 * Signals computed from headers alone. Each returns a flag string or null, and
 * every one of them says WHY rather than just naming a rule -- the reply is read
 * by someone deciding whether to click, not by an analyst.
 */
function headerSignals(email, headers) {
  const flags = [];
  const auth = parseAuthResults(headers);

  if (auth.present) {
    if (auth.dmarc === "fail") {
      flags.push(
        "DMARC FAILED. Your own email provider checked whether this message was " +
        "really authorised by the domain it claims to come from, and the answer " +
        "was no. That is the strongest single signal here."
      );
    }
    if (auth.spf === "fail" || auth.spf === "softfail") {
      flags.push(
        "SPF " + auth.spf.toUpperCase() + ". The server that sent this is not one " +
        "the claimed domain lists as its own."
      );
    }
    if (auth.dkim === "fail") {
      flags.push("DKIM FAILED. The message signature does not verify, so the content may have been altered in transit.");
    }
  }

  const fromAddr = (email.from && email.from.address) || "";
  const fromName = (email.from && email.from.name) || "";
  const fromDomain = domainOf(fromAddr);

  // Reply-To pointing somewhere else is the classic BEC setup: the display and
  // the From look right, and the reply quietly goes to the attacker.
  const replyTo = (email.replyTo && email.replyTo[0] && email.replyTo[0].address) || "";
  if (replyTo && domainOf(replyTo) && domainOf(replyTo) !== fromDomain) {
    flags.push(
      `Reply-To mismatch. It appears to come from ${fromAddr}, but a reply would go ` +
      `to ${replyTo} instead. That is a different domain, and it is how business ` +
      "email compromise usually works."
    );
  }

  // Return-Path is the envelope sender. A mismatch is normal for mailing lists
  // and legitimate forwarders, so this is worded as a question, not a verdict.
  const returnPath = headers.get("return-path") || "";
  const rpDomain = domainOf(returnPath);
  if (rpDomain && fromDomain && rpDomain !== fromDomain) {
    flags.push(
      `Envelope sender is ${rpDomain} but the message claims to be from ${fromDomain}. ` +
      "That can be legitimate for newsletters and forwarders, but on a message asking " +
      "you to act it is worth checking."
    );
  }

  // A display name that names a person or brand, on a webmail address, with no
  // relationship between the two.
  const WEBMAIL = new Set([
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "live.com", "protonmail.com", "proton.me", "mail.com",
  ]);
  if (fromName && WEBMAIL.has(fromDomain)) {
    const tokens = fromName.toLowerCase().match(/[a-z]{3,}/g) || [];
    const local = (fromAddr.split("@")[0] || "").toLowerCase();
    if (tokens.length && !tokens.some((t) => local.includes(t))) {
      flags.push(
        `The sender calls themselves "${fromName}" but writes from a free ${fromDomain} ` +
        "address unrelated to that name. Anyone can set a display name; it is not identity."
      );
    }
  }

  return { flags, auth, fromAddr, fromName, fromDomain };
}

// ---------------------------------------------------------------------------
// Minimal MIME reading — replaces the postal-mime dependency
// ---------------------------------------------------------------------------
//
// Cloudflare hands the parsed headers over as message.headers, so everything the
// analysis actually keys on (Authentication-Results, Reply-To, Return-Path,
// From) needs no parsing at all. What is left is pulling the readable text out
// of the body, which is what these three functions do.
//
// Scope is deliberate: text/plain when present, text/html stripped as a
// fallback, quoted-printable and base64 decoded, one level of multipart walked.
// That covers what a forwarded email actually looks like. It is NOT a general
// MIME implementation and does not pretend to be -- a nested multipart with an
// unusual encoding degrades to "less text extracted", never to a wrong verdict,
// because the header signals are computed independently of the body.

function splitHeadersAndBody(raw) {
  const i = raw.search(/\r?\n\r?\n/);
  if (i === -1) return { head: raw, body: "" };
  const sep = raw.slice(i).startsWith("\r\n") ? 4 : 2;
  return { head: raw.slice(0, i), body: raw.slice(i + sep) };
}

function decodePart(body, encoding) {
  const enc = (encoding || "").toLowerCase().trim();
  if (enc === "base64") {
    try {
      return atob(body.replace(/\s+/g, ""));
    } catch {
      return body;   // malformed base64 is not worth failing the whole scan over
    }
  }
  if (enc === "quoted-printable") {
    return body
      .replace(/=\r?\n/g, "")                                  // soft line breaks
      .replace(/=([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
  }
  return body;
}

/**
 * Best-effort readable text from a raw RFC 822 message.
 * Returns "" rather than throwing: a body we cannot read must still produce a
 * header-only verdict, not an error reply.
 */
function extractText(raw) {
  const { head, body } = splitHeadersAndBody(raw);
  const unfolded = head.replace(/\r?\n[ \t]+/g, " ");
  const ctype = (unfolded.match(/^content-type:\s*(.+)$/im) || [])[1] || "";
  const cte = (unfolded.match(/^content-transfer-encoding:\s*(.+)$/im) || [])[1] || "";

  const boundaryMatch = ctype.match(/boundary="?([^";\s]+)"?/i);
  if (!boundaryMatch) {
    const text = decodePart(body, cte);
    return /text\/html/i.test(ctype) ? stripHtml(text) : text;
  }

  // Walk one level of multipart. Prefer text/plain; keep html only as fallback,
  // because a forwarded message's plain part is what the human actually read.
  const parts = body.split("--" + boundaryMatch[1]);
  let plain = "", html = "";
  for (const part of parts) {
    const { head: ph, body: pb } = splitHeadersAndBody(part.replace(/^\r?\n/, ""));
    const pUnfolded = ph.replace(/\r?\n[ \t]+/g, " ");
    const pType = (pUnfolded.match(/^content-type:\s*(.+)$/im) || [])[1] || "";
    const pEnc = (pUnfolded.match(/^content-transfer-encoding:\s*(.+)$/im) || [])[1] || "";
    if (/text\/plain/i.test(pType) && !plain) plain = decodePart(pb, pEnc);
    else if (/text\/html/i.test(pType) && !html) html = stripHtml(decodePart(pb, pEnc));
    else if (/multipart\//i.test(pType) && !plain) {
      const inner = extractText(part.replace(/^\r?\n/, ""));
      if (inner) plain = inner;
    }
  }
  return plain || html || "";
}

function stripHtml(html) {
  return html
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, " ")
    // href values are kept: a link is the thing being checked, and dropping the
    // markup must not drop the URL inside it.
    .replace(/<a\s[^>]*href=["']?([^"'\s>]+)/gi, " $1 ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ");
}

/** From: / Reply-To: style header -> { address, name }. */
function parseAddress(value) {
  if (!value) return { address: "", name: "" };
  const angled = value.match(/^\s*(.*?)\s*<([^>]+)>/);
  if (angled) {
    return {
      address: angled[2].trim().toLowerCase(),
      name: angled[1].replace(/^["']|["']$/g, "").trim(),
    };
  }
  return { address: value.trim().toLowerCase(), name: "" };
}

// ---------------------------------------------------------------------------
// Link checking — one source of truth, the existing API
// ---------------------------------------------------------------------------

function extractLinks(text) {
  const found = new Set();
  const re = /https?:\/\/[^\s<>"')\]]+/gi;
  let m;
  while ((m = re.exec(text)) !== null) {
    found.add(m[0].replace(/[.,;:!?)]+$/, ""));
    if (found.size >= 50) break;
  }
  return [...found];
}

async function scanLink(url, apiKey) {
  try {
    const resp = await fetch(`${API_BASE}/v1/scan-url`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": apiKey },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) return { url, status: "unknown", detail: `check unavailable (${resp.status})` };
    const data = await resp.json();
    return { url, status: data.status || "unknown", detail: data.detail || "" };
  } catch (err) {
    // A link check that failed must never render as a link that passed.
    return { url, status: "unknown", detail: "check unavailable" };
  }
}

// ---------------------------------------------------------------------------
// Rate limiting
// ---------------------------------------------------------------------------

async function rateLimited(kv, sender) {
  if (!kv) return false;                 // fail open: a broken KV must not break scanning
  const now = Date.now();
  const hourKey = `h:${sender}:${Math.floor(now / 3600000)}`;
  const dayKey = `d:${sender}:${Math.floor(now / 86400000)}`;
  const [h, d] = await Promise.all([kv.get(hourKey), kv.get(dayKey)]);
  const hourCount = parseInt(h || "0", 10);
  const dayCount = parseInt(d || "0", 10);
  if (hourCount >= RATE_LIMIT_PER_HOUR || dayCount >= RATE_LIMIT_PER_DAY) return true;
  await Promise.all([
    kv.put(hourKey, String(hourCount + 1), { expirationTtl: 3700 }),
    kv.put(dayKey, String(dayCount + 1), { expirationTtl: 86500 }),
  ]);
  return false;
}

// ---------------------------------------------------------------------------
// Reply
// ---------------------------------------------------------------------------

function buildReply(sig, linkResults, subject) {
  const bad = linkResults.filter((l) => l.status === "malicious" || l.status === "suspicious");
  const unknown = linkResults.filter((l) => l.status === "unknown");
  const clean = linkResults.filter((l) => l.status === "clean");

  const dmarcFailed = sig.auth.present && sig.auth.dmarc === "fail";
  const risk = (bad.length || dmarcFailed) ? "HIGH"
             : sig.flags.length ? "MEDIUM"
             : "LOW";

  const out = [];
  out.push(`RelayShield email check: ${risk} RISK`);
  out.push("");
  if (subject) out.push(`Subject checked: ${subject}`);
  out.push(`Claimed sender: ${sig.fromAddr || "not stated"}`);
  out.push("");

  if (sig.flags.length) {
    out.push(`WHAT IS WRONG WITH THE SENDER (${sig.flags.length}):`);
    sig.flags.forEach((f) => out.push(`  - ${f}`));
  } else if (sig.auth.present) {
    out.push(
      "SENDER CHECKS PASSED. SPF, DKIM and DMARC as recorded by your own email " +
      "provider show nothing wrong. That means the message really was sent by the " +
      "domain it claims -- it does NOT mean the domain is trustworthy. A scammer " +
      "who registers their own domain passes all three."
    );
  } else {
    out.push(
      "NO AUTHENTICATION HEADERS. This forward did not carry your provider's " +
      "SPF/DKIM/DMARC results, so the sender could not be verified either way. " +
      "Forwarding as an attachment usually preserves them."
    );
  }
  out.push("");

  if (linkResults.length) {
    out.push("LINKS:");
    bad.forEach((l) => out.push(`  FLAGGED  ${l.url}${l.detail ? ": " + l.detail : ""}`));
    unknown.forEach((l) => out.push(`  UNKNOWN  ${l.url}: ${l.detail || "no reputation data"}`));
    clean.forEach((l) => out.push(`  no match ${l.url}`));
    if (clean.length && !bad.length) {
      out.push("");
      out.push(
        "  A clean result is not a guarantee. New phishing domains can take hours " +
        "to appear in any threat database."
      );
    }
  } else {
    out.push("LINKS: none found in the text.");
  }
  out.push("");

  out.push("WHAT TO DO:");
  if (risk === "HIGH") {
    out.push("  - Do not click anything in that email and do not reply to it.");
    out.push("  - If it claims to be a company you use, go to their site yourself and log in there.");
    out.push("  - If it names a person you know, contact them another way before acting.");
  } else if (risk === "MEDIUM") {
    out.push("  - Treat it as unverified. Do not enter a password or payment detail from a link in it.");
    out.push("  - Confirm through a channel you already trust before acting.");
  } else {
    out.push("  - Nothing automatic flagged, but no scan proves a message is safe.");
    out.push("  - An unexpected request for money, credentials or urgency is a warning sign regardless.");
  }
  out.push("");
  out.push("---");
  out.push("Forward anything suspicious to checkemail@relayshield.net.");
  out.push("We store the verdict and the indicators we extract. We do not store your email.");
  out.push("RelayShield: https://relayshield.net?source=email-scan");
  return out.join("\n");
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export default {
  // Thin wrapper. All the work is in scanAndReply, so that a throw anywhere in
  // it gets logged with a stack before it propagates.
  //
  // ADDED 2026-09-02. The dashboard showed 6 errors across 8 requests and there
  // was no way to see what any of them were: an email handler that throws
  // produces a number on a card and nothing else. `npx wrangler tail --config
  // wrangler.checkemail.toml` now shows the actual failure, and the sender gets
  // a bounce rather than silence, because a message that vanishes with no reply
  // and no bounce is the worst of the three outcomes.
  async email(message, env, ctx) {
    try {
      await scanAndReply(message, env, ctx);
    } catch (err) {
      console.error(
        "checkemail: FAILED for", message.from, "--",
        err && err.stack ? err.stack : String(err)
      );
      throw err;
    }
  },


  // A health endpoint, because the email path gives no way to tell a Worker
  // that is not deployed from one that is deployed and silently dropping mail.
  // The 554 on 2026-09-02 was Cloudflare's inbound parser rejecting a malformed
  // MIME header before the Worker ran at all, and there was no way to see that
  // from the outside. GET this URL and you know the deploy is live and which
  // bindings it actually has. It reveals no secret -- only whether each binding
  // is present, never its value.
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/health") {
      return new Response("checkemail worker. GET /health\n", {
        status: 404,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    return Response.json({
      ok: true,
      worker: "relayshield-checkemail",
      address: "checkemail@relayshield.net",
      bindings: {
        // Rate limiting is off until this KV namespace exists. Publishing the
        // address before then means the free tier is unrated.
        CHECKEMAIL_RL: Boolean(env.CHECKEMAIL_RL),
        // Without this, links are reported "unknown" rather than scanned.
        RS_API_KEY: Boolean(env.RS_API_KEY),
      },
      at: new Date().toISOString(),
    });
  },
};

/** Build a plain-text reply message. Plain text on purpose: it renders
 *  everywhere, cannot carry a tracking pixel, and cannot itself look like the
 *  thing we are warning people about.
 *
 *  REWRITTEN 2026-09-02, after the Worker logged 6 errors across 8 requests and
 *  no reply ever arrived. The first version built a message that is not a valid
 *  RFC 5322 message, and Cloudflare validates the raw bytes handed to
 *  EmailMessage before it will send them. Four separate defects, any one of
 *  which is fatal on its own:
 *
 *  1. NO Message-ID. Every message needs its own. Cloudflare rejects a reply
 *     without one.
 *  2. NO Date. Also mandatory in RFC 5322.
 *  3. `In-Reply-To: ` with an empty value when the original carried no
 *     Message-ID. An empty header value is malformed -- better to omit the
 *     header entirely.
 *  4. HEADERS JOINED WITH CRLF, BODY JOINED WITH BARE LF. A MIME message is
 *     CRLF throughout. buildReply() joins its lines with "\n", so the body
 *     went out with bare newlines inside a CRLF message.
 *
 *  It also now strips non-ASCII from the echoed subject rather than putting raw
 *  UTF-8 bytes in a header, which needs RFC 2047 encoding to be legal. The
 *  subject we echo is attacker-controlled text from the mail being scanned, so
 *  it is the single most likely place to receive bytes that break the header
 *  block. */
function makeReply(message, text) {
  const rawSubject = message.headers.get("subject") || "your email check";
  // Header-safe: ASCII printable only, no CR or LF (header injection), capped.
  const subject = rawSubject
    .replace(/[\r\n]+/g, " ")
    .replace(/[^\x20-\x7E]/g, "")
    .slice(0, 120)
    .trim() || "your email check";

  // message.from is the envelope sender. Cloudflare parses it before we see it,
  // but it still originates outside, and it goes straight into a header line --
  // so strip anything that could start a new one.
  const to = String(message.from || "").replace(/[\r\n]+/g, "").slice(0, 320);

  const originalId = (message.headers.get("message-id") || "")
    .replace(/[\r\n]+/g, "").trim().slice(0, 320);
  const ourId = `<${Date.now()}.${Math.random().toString(36).slice(2, 12)}@relayshield.net>`;

  const headers = [
    `From: RelayShield <checkemail@relayshield.net>`,
    `To: ${to}`,
    `Message-ID: ${ourId}`,
    `Date: ${new Date().toUTCString()}`,
    // Only when the original actually had one. An empty value is malformed.
    ...(originalId ? [`In-Reply-To: ${originalId}`, `References: ${originalId}`] : []),
    `Subject: Re: ${subject}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/plain; charset=utf-8`,
    `Content-Transfer-Encoding: 7bit`,
    `Auto-Submitted: auto-replied`,
  ].join("\r\n");

  // CRLF throughout, and 7bit means the body must be ASCII to match the
  // encoding we just declared.
  const body = text
    .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/\n/g, "\r\n");

  return new EmailMessage(
    "checkemail@relayshield.net",
    to,
    `${headers}\r\n\r\n${body}\r\n`
  );
}

/** The actual scan. Split out of the email handler so that a throw here is
 *  logged with a stack rather than surfacing only as an error count on the
 *  Cloudflare dashboard. */
async function scanAndReply(message, env, ctx) {
  const sender = (message.from || "").toLowerCase();

  // Loop guards, before anything else. Replying to an auto-responder or to a
  // forwarder that points back at us ping-pongs forever and looks like an
  // attack from our own domain.
  const autoSubmitted = message.headers.get("auto-submitted") || "";
  const precedence = (message.headers.get("precedence") || "").toLowerCase();
  if (
    !sender ||
    // NARROWED 2026-09-02. This used to drop anything from @relayshield.net,
    // which is far wider than the loop it was guarding against. Our reply is
    // From: checkemail@relayshield.net, so THAT address is the only one that
    // can loop -- and blocking the whole domain silently swallowed mail from
    // andrew@relayshield.net (the founder's own send-as alias, the first
    // account that would ever test this) and would block every colleague and
    // every customer on the domain. A guard that also drops your own users is
    // not a guard.
    sender === "checkemail@relayshield.net" ||
    sender.startsWith("no-reply@") ||
    sender.startsWith("noreply@") ||
    sender.startsWith("mailer-daemon@") ||
    (autoSubmitted && autoSubmitted.toLowerCase() !== "no") ||
    precedence === "bulk" || precedence === "list" || precedence === "junk"
  ) {
    return;   // accept and drop, silently and deliberately
  }

  if (await rateLimited(env.CHECKEMAIL_RL, sender)) {
    await message.reply(
      makeReply(message,
        "RelayShield: rate limit reached\n\n" +
        `The free email check allows ${RATE_LIMIT_PER_HOUR} messages an hour and ` +
        `${RATE_LIMIT_PER_DAY} a day. Try again shortly.\n\n` +
        "For continuous monitoring rather than one-off checks, see " +
        "https://relayshield.net?source=email-scan")
    );
    return;
  }

  // Headers come from Cloudflare already parsed. Only the body needs reading,
  // and a body we cannot read still yields a header-only verdict -- which is
  // the strongest half anyway -- so this never aborts the scan.
  let bodyText = "";
  try {
    const raw = await new Response(message.raw).text();
    bodyText = extractText(raw).slice(0, MAX_BODY_CHARS);
  } catch (err) {
    bodyText = "";
  }

  const email = {
    from: parseAddress(message.headers.get("from")),
    replyTo: [parseAddress(message.headers.get("reply-to"))],
    subject: message.headers.get("subject") || "",
  };
  const body = bodyText;
  const sig = headerSignals(email, message.headers);

  const links = extractLinks(body).slice(0, MAX_LINKS_CHECKED);
  const linkResults = env.RS_API_KEY
    ? await Promise.all(links.map((u) => scanLink(u, env.RS_API_KEY)))
    : links.map((u) => ({ url: u, status: "unknown", detail: "link checking unavailable" }));

  const reply = buildReply(sig, linkResults, (email.subject || "").slice(0, 120));
  await message.reply(makeReply(message, reply));

  // Indicators only. No body, no subject, no addresses beyond the flagged
  // domains -- see the privacy note at the top of this file.
  if (env.CHECKEMAIL_RL) {
    const iocs = linkResults.filter((l) => l.status === "malicious" || l.status === "suspicious")
                            .map((l) => l.url);
    if (iocs.length) {
      ctx.waitUntil(env.CHECKEMAIL_RL.put(
        `ioc:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        JSON.stringify({ iocs, dmarc: sig.auth.dmarc || null, at: new Date().toISOString() }),
        { expirationTtl: 7776000 }
      ));
    }
  }
}
