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

// Every link shares one wall-clock budget for the VirusTotal poll. A reply that
// arrives is worth more than a verdict that is twenty seconds more complete,
// and an email handler that runs long is an email handler that gets killed.
const LINK_SCAN_BUDGET_MS = 12000;
const LINK_POLL_INTERVAL_MS = 2500;

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

// ---------------------------------------------------------------------------
// Brand impersonation: the display-name check that is actually a signal
// ---------------------------------------------------------------------------
//
// REWRITTEN 2026-09-02, after a genuine message from the founder's own Gmail
// came back MEDIUM RISK on a single flag: the display name "Andrew Gibbs" did
// not appear in the local part "nzdsf2".
//
// That rule fires on almost every real Gmail user. The good addresses went
// years ago, so most people's address has nothing to do with their name, and
// the flag reduced to "this person has a Gmail account" -- dressed up as a
// finding. A verdict a user can dismiss with one glance at their own inbox is
// worse than no verdict, because it teaches them to ignore the next one.
//
// The distinction that IS worth making is not name-versus-address. It is
// whether the display name claims to be an INSTITUTION while the address is
// free webmail. "Andrew Gibbs" from gmail.com is a person. "PayPal Support"
// from gmail.com is an attack, because PayPal does not send from gmail.com and
// never will. That asymmetry is the whole value of the check.
const IMPERSONATED_BRANDS = [
  // Payments and banking
  "paypal", "stripe", "venmo", "cash app", "zelle", "wise", "revolut", "monzo",
  "chase", "wells fargo", "bank of america", "citibank", "citi", "capital one",
  "hsbc", "barclays", "lloyds", "natwest", "santander", "halifax", "amex",
  "american express", "visa", "mastercard",
  // Crypto, where the loss is irreversible
  "coinbase", "binance", "kraken", "gemini", "metamask", "ledger", "trezor",
  "phantom", "uniswap", "opensea", "blockchain.com",
  // Big tech account takeover
  "microsoft", "office 365", "outlook", "apple", "icloud", "google", "gmail",
  "amazon", "aws", "meta", "facebook", "instagram", "whatsapp", "linkedin",
  "netflix", "spotify", "dropbox", "docusign", "adobe", "ebay", "paypal inc",
  // Government and tax, the classic urgency lever
  "irs", "hmrc", "social security", "medicare", "dvla", "gov.uk",
  // Couriers, the classic pretext
  "dhl", "fedex", "ups", "usps", "royal mail", "evri", "hermes", "dpd",
  // Security brands, used to sell fake remediation
  "norton", "mcafee", "geek squad", "best buy",
];

// A display name claiming a ROLE rather than a person. "Security Team" from a
// free webmail address is the same trick with the brand left implicit.
const AUTHORITY_WORDS = [
  "support", "security", "helpdesk", "help desk", "billing", "accounts",
  "account services", "service desk", "customer service", "customer care",
  "fraud", "verification", "no-reply", "noreply", "administrator", "admin team",
  "it department", "payroll", "hr department",
];

const WEBMAIL = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
  "hotmail.com", "hotmail.co.uk", "icloud.com", "me.com", "aol.com",
  "live.com", "live.co.uk", "protonmail.com", "proton.me", "mail.com",
  "gmx.com", "yandex.com", "zoho.com", "msn.com",
]);

/**
 * Signals computed from headers alone.
 *
 * Returns { flags, notes, score, ... }. The split matters:
 *
 *   flags  raise the risk score. Each one is something that should not be true
 *          of a legitimate message.
 *   notes  are stated in the reply but score ZERO. They are observations a
 *          reader benefits from, that are also true of masses of ordinary mail.
 *
 * Before this split every observation was a flag, and any single one of them
 * produced MEDIUM RISK. Weighting them means the word MEDIUM keeps meaning
 * something.
 */
function headerSignals(email, headers, forwarded) {
  const flags = [];      // { text, weight }
  const notes = [];      // strings, weight zero by construction
  const auth = parseAuthResults(headers);

  // WHOSE authentication is this? On an inline forward, Authentication-Results
  // describes the FORWARDER, not the original sender -- see detectForwardedOriginal.
  const authIsAboutOriginal = !forwarded;

  if (auth.present && authIsAboutOriginal) {
    if (auth.dmarc === "fail") {
      flags.push({ weight: 3, text:
        "DMARC FAILED. Your own email provider checked whether this message was " +
        "really authorised by the domain it claims to come from, and the answer " +
        "was no. That is the strongest single signal available here." });
    }
    if (auth.spf === "fail") {
      flags.push({ weight: 2, text:
        "SPF FAILED. The server that sent this is not one the claimed domain " +
        "lists as its own." });
    } else if (auth.spf === "softfail") {
      flags.push({ weight: 1, text:
        "SPF SOFTFAIL. The claimed domain does not list this sending server, but " +
        "stops short of saying the mail is forged. Common on forwarded mail." });
    }
    if (auth.dkim === "fail") {
      flags.push({ weight: 2, text:
        "DKIM FAILED. The message signature does not verify, so the content may " +
        "have been altered after it was sent." });
    }
  }

  // On a forward, analyse the address the forward claims the mail came FROM,
  // not the friend who forwarded it to us.
  const fromAddr = forwarded ? forwarded.address
                             : ((email.from && email.from.address) || "");
  const fromName = forwarded ? forwarded.name
                             : ((email.from && email.from.name) || "");
  const fromDomain = domainOf(fromAddr);

  // Reply-To pointing somewhere else is the classic BEC setup: the display and
  // the From look right, and the reply quietly goes to the attacker. Only
  // meaningful on a direct message; a forward's Reply-To is the forwarder's.
  const replyTo = (email.replyTo && email.replyTo[0] && email.replyTo[0].address) || "";
  if (!forwarded && replyTo && domainOf(replyTo) && domainOf(replyTo) !== fromDomain) {
    flags.push({ weight: 2, text:
      `Reply-To mismatch. It appears to come from ${fromAddr}, but a reply would ` +
      `go to ${replyTo} instead, on a different domain. That is how business ` +
      "email compromise usually works." });
  }

  // Return-Path is the envelope sender. A mismatch is completely normal for
  // mailing lists, newsletters and every legitimate forwarder, so it is a NOTE.
  // Scoring it was part of what made the first verdict undefendable.
  const returnPath = headers.get("return-path") || "";
  const rpDomain = domainOf(returnPath);
  const headerFromDomain = domainOf((email.from && email.from.address) || "");
  if (rpDomain && headerFromDomain && rpDomain !== headerFromDomain) {
    notes.push(
      `The envelope sender is ${rpDomain} while the message header says ` +
      `${headerFromDomain}. That is normal for newsletters, mailing lists and ` +
      "forwarded mail, so on its own it means nothing.");
  }

  // The narrowed impersonation check.
  if (fromName && WEBMAIL.has(fromDomain)) {
    const nameLower = fromName.toLowerCase();
    const brand = IMPERSONATED_BRANDS.find((b) => nameLower.includes(b));
    const authority = AUTHORITY_WORDS.find((w) => nameLower.includes(w));
    if (brand) {
      flags.push({ weight: 3, text:
        `The sender's display name claims to be "${fromName}", but the address is ` +
        `a free ${fromDomain} account. ${brand.replace(/\b\w/g, (c) => c.toUpperCase())} ` +
        "does not send mail from free webmail, and neither does any bank, tax " +
        "office or courier. This is the single most common shape of a phishing " +
        "message." });
    } else if (authority) {
      flags.push({ weight: 2, text:
        `The display name "${fromName}" presents as a department or a support ` +
        `desk, but the address is a free ${fromDomain} account. A real ` +
        "organisation writes from its own domain." });
    }
  }

  const score = flags.reduce((n, f) => n + f.weight, 0);
  return { flags, notes, score, auth, authIsAboutOriginal, fromAddr, fromName, fromDomain };
}

// ---------------------------------------------------------------------------
// Inline forwards: whose message are we actually looking at?
// ---------------------------------------------------------------------------
//
// ADDED 2026-09-02, and it is the most important honesty fix in this file.
//
// When someone hits Forward in Gmail, Gmail composes a NEW message from them,
// quoting the original as text. Cloudflare therefore hands us headers belonging
// to the forwarder. Authentication-Results says Gmail authenticated the
// forwarder, which it did -- and the first version of this Worker reported that
// as "SENDER CHECKS PASSED", which reads as a verdict on the suspicious message.
// It is not. It is a verdict on the person asking us about it.
//
// That is the same failure the WhatsApp adapter is written to avoid: never
// imply we identified a sender we did not. So on an inline forward we say
// plainly that the authentication results are not the original's, and we tell
// the user how to get an answer that is (forward as an attachment).
//
// The original sender's ADDRESS is still recoverable, because every mail client
// quotes it in the body. That address cannot be authenticated -- anyone can type
// any address into a forwarded block -- but it is what the impersonation check
// needs, and it is far better than analysing the forwarder.
function detectForwardedOriginal(bodyText) {
  if (!bodyText) return null;
  const markers = [
    /-{2,}\s*Forwarded message\s*-{2,}/i,     // Gmail
    /Begin forwarded message:/i,               // Apple Mail
    /-{2,}\s*Original Message\s*-{2,}/i,       // Outlook, older
    /^\s*_{10,}\s*$/m,                         // Outlook, newer
  ];
  const hit = markers.find((re) => re.test(bodyText));
  if (!hit) return null;

  const after = bodyText.slice(bodyText.search(hit));
  // "From: Display Name <addr@example.com>" inside the quoted block.
  const m = after.match(/^\s*(?:>\s*)?From:\s*(.+)$/im);
  if (!m) return { address: "", name: "", parseFailed: true };
  const parsed = parseAddress(m[1].trim());
  return { address: parsed.address || "", name: parsed.name || "", parseFailed: false };
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

/**
 * Check one link through the same pipeline every other RelayShield surface uses.
 *
 * REWRITTEN 2026-09-02. The first version read `data.status` from
 * POST /v1/scan-url and treated anything that was not "malicious"/"suspicious"/
 * "clean" as unknown. That endpoint ALWAYS returns status "pending": it submits
 * to VirusTotal and hands back an analysis_id to poll. So the field was never
 * a verdict, every link came back "no reputation data", and the link half of
 * the product had never worked at all. It looked like a link nobody had heard
 * of; it was a field that does not carry what was being read out of it.
 *
 * The response does carry an immediate answer, in `immediate_signal` --
 * RelayShield's own criminal IOC corpus, Google Safe Browsing, and RDAP
 * registration age, all computed before the call returns. That is the part
 * VirusTotal cannot tell you, so it is used first and always.
 *
 * The VirusTotal verdict then needs a poll, which is what /v1/result is for.
 * All links share one wall-clock budget, because a reply that arrives is worth
 * more than a verdict that is 20 seconds more complete.
 */
async function scanLink(url, apiKey, deadline) {
  let submitted;
  try {
    const resp = await fetch(`${API_BASE}/v1/scan-url`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": apiKey },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) {
      return { url, status: "unknown", detail: `check unavailable (HTTP ${resp.status})` };
    }
    submitted = await resp.json();
  } catch (err) {
    // A link check that failed must never render as a link that passed.
    return { url, status: "unknown", detail: "check unavailable" };
  }

  // Signal one, available immediately, and the one nobody else has.
  const reasons = Array.isArray(submitted.immediate_reasons) ? submitted.immediate_reasons : [];
  if (submitted.immediate_signal === "flagged" && reasons.length) {
    const corroborated = reasons.some(
      (r) => /IOC corpus|Safe Browsing/i.test(r));
    return {
      url,
      status: corroborated ? "malicious" : "suspicious",
      detail: reasons.join("; "),
    };
  }

  // Signal two: VirusTotal, which needs the poll the first version never did.
  const analysisId = submitted.analysis_id;
  if (!analysisId) {
    return { url, status: "unknown", detail: "no analysis was started for this link" };
  }
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, LINK_POLL_INTERVAL_MS));
    try {
      const resp = await fetch(
        `${API_BASE}/v1/result/${encodeURIComponent(analysisId)}`,
        { headers: { "x-api-key": apiKey } });
      if (!resp.ok) break;
      const data = await resp.json();
      if (data.status === "pending") continue;
      if (data.verdict === "malicious" || data.verdict === "suspicious") {
        const n = data.malicious || data.suspicious || 0;
        const total = data.total_engines || 0;
        return {
          url,
          status: data.verdict,
          detail: total ? `${n} of ${total} security vendors flag this` : data.verdict,
        };
      }
      if (data.verdict === "clean") {
        return {
          url,
          status: "clean",
          detail: data.total_engines
            ? `no detections from ${data.total_engines} security vendors`
            : "no detections",
        };
      }
      break;   // "timeout" or anything unrecognised
    } catch (err) {
      break;
    }
  }

  // Honest, and deliberately not dressed up as a result. "No reputation data"
  // is the truthful answer for most links, and it must not read as either a
  // pass or a fail.
  return {
    url,
    status: "unknown",
    detail: "no security vendor has published a verdict on this link yet",
  };
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

/**
 * Turn the signals into a reply a worried non-specialist can act on.
 *
 * RISK IS SCORED, NOT COUNTED. Rewritten 2026-09-02: the first version was
 * `bad.length || dmarcFailed ? HIGH : sig.flags.length ? MEDIUM : LOW`, so any
 * single observation -- including ones true of most ordinary mail -- produced
 * MEDIUM RISK. A genuine message from the founder's own Gmail came back MEDIUM
 * on the strength of his display name not appearing in his email address.
 *
 * A verdict the reader can dismiss by glancing at their own inbox is worse than
 * no verdict, because it trains them to ignore the next one. So:
 *
 *   HIGH    score 3+   something is wrong that should not be true of real mail
 *   MEDIUM  score 2     one solid anomaly, worth checking before acting
 *   LOW     score 0-1   nothing found, stated as nothing found
 *
 * and observations that are ALSO true of newsletters and forwards are printed
 * under WORTH KNOWING, where they inform without inflating the verdict.
 */
function buildReply(sig, linkResults, subject, forwarded) {
  const bad = linkResults.filter((l) => l.status === "malicious");
  const sus = linkResults.filter((l) => l.status === "suspicious");
  const unknown = linkResults.filter((l) => l.status === "unknown");
  const clean = linkResults.filter((l) => l.status === "clean");

  const score = sig.score + bad.length * 3 + sus.length * 2;
  const risk = score >= 3 ? "HIGH" : score === 2 ? "MEDIUM" : "LOW";

  const out = [];
  out.push(`RelayShield email check: ${risk} RISK`);
  out.push("");
  if (subject) out.push(`Subject checked: ${subject}`);
  out.push(`Claimed sender: ${sig.fromAddr || "not stated"}`);
  out.push("");

  // WHOSE MESSAGE IS THIS. Said before any verdict, because on an inline
  // forward every authentication result below belongs to the reader's own
  // forward and not to the message they are worried about.
  if (forwarded) {
    out.push("ABOUT THIS FORWARD:");
    if (forwarded.address) {
      out.push(`  You forwarded this inline, so the original sender shows in the quoted`);
      out.push(`  text as ${forwarded.address}. We analysed that address, not yours.`);
    } else {
      out.push("  You forwarded this inline, and we could not read the original sender");
      out.push("  out of the quoted text.");
    }
    out.push("  BUT: forwarding inline strips the original SPF, DKIM and DMARC results.");
    out.push("  Your provider re-signed the forward as coming from you, which it does");
    out.push("  honestly, so we CANNOT tell you whether the original was really sent by");
    out.push("  the domain it claims. An address typed into a quoted block proves nothing.");
    out.push("  To get that answer, forward it AS AN ATTACHMENT instead:");
    out.push("    Gmail: open the message, three-dot menu, Forward as attachment.");
    out.push("    Outlook: More, Forward as attachment.");
    out.push("    Apple Mail: hold Shift and choose Forward as Attachment.");
    out.push("");
  }

  if (sig.flags.length) {
    out.push(`WHAT IS WRONG (${sig.flags.length}):`);
    sig.flags.forEach((f) => out.push(`  - ${f.text}`));
  } else if (sig.auth.present && sig.authIsAboutOriginal) {
    out.push(
      "SENDER CHECKS PASSED. SPF, DKIM and DMARC as recorded by your own email " +
      "provider show nothing wrong. That means the message really was sent by " +
      "the domain it claims. It does NOT mean the domain is trustworthy: a " +
      "scammer who registers their own domain passes all three.");
  } else if (!sig.authIsAboutOriginal) {
    out.push(
      "NOTHING WRONG FOUND IN WHAT WE CAN SEE. On an inline forward that is a " +
      "weak statement, for the reason above.");
  } else {
    out.push(
      "NO AUTHENTICATION HEADERS. This message did not carry your provider's " +
      "SPF/DKIM/DMARC results, so the sender could not be verified either way.");
  }
  out.push("");

  if (linkResults.length) {
    out.push("LINKS:");
    bad.forEach((l) => out.push(`  DANGEROUS  ${l.url}${l.detail ? " -- " + l.detail : ""}`));
    sus.forEach((l) => out.push(`  SUSPICIOUS ${l.url}${l.detail ? " -- " + l.detail : ""}`));
    clean.forEach((l) => out.push(`  no match   ${l.url}${l.detail ? " -- " + l.detail : ""}`));
    unknown.forEach((l) => out.push(`  UNKNOWN    ${l.url} -- ${l.detail}`));
    if (unknown.length) {
      out.push("");
      out.push(
        "  UNKNOWN is not a finding. Most links are unknown, including almost");
      out.push(
        "  every legitimate one, and it did not count towards the rating above.");
    }
    if (clean.length && !bad.length && !sus.length) {
      out.push("");
      out.push(
        "  A clean result is not a guarantee. A brand new phishing domain can");
      out.push("  take hours to appear in any threat database.");
    }
  } else {
    out.push("LINKS: none found in the text.");
  }
  out.push("");

  if (sig.notes.length) {
    out.push("WORTH KNOWING (this did not affect the rating):");
    sig.notes.forEach((n) => out.push(`  - ${n}`));
    out.push("");
  }

  out.push("WHAT TO DO:");
  if (risk === "HIGH") {
    out.push("  - Do not click anything in that email and do not reply to it.");
    out.push("  - If it claims to be a company you use, go to their site yourself and log in there.");
    out.push("  - If it names a person you know, contact them another way before acting.");
  } else if (risk === "MEDIUM") {
    out.push("  - Treat it as unverified. Do not enter a password or payment detail from a link in it.");
    out.push("  - Confirm through a channel you already trust before acting.");
  } else {
    out.push("  - We found nothing wrong. That is not the same as proving it is safe,");
    out.push("    and no scan anywhere can prove that.");
    out.push("  - An unexpected request for money, credentials or urgency is a warning");
    out.push("    sign regardless of what any checker says.");
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

  // Whose message is this? Must be decided BEFORE the signals, because on an
  // inline forward the authentication headers describe the person asking us
  // rather than the message they are asking about.
  const forwarded = detectForwardedOriginal(body);
  const sig = headerSignals(email, message.headers, forwarded);

  const links = extractLinks(body).slice(0, MAX_LINKS_CHECKED);
  const deadline = Date.now() + LINK_SCAN_BUDGET_MS;
  const linkResults = env.RS_API_KEY
    ? await Promise.all(links.map((u) => scanLink(u, env.RS_API_KEY, deadline)))
    : links.map((u) => ({
        url: u, status: "unknown",
        detail: "link checking is not configured on this deployment",
      }));

  console.log(
    "checkemail: scanned", message.from,
    "forwarded=", Boolean(forwarded),
    "score=", sig.score,
    "flags=", sig.flags.length,
    "links=", linkResults.map((l) => l.status).join(",") || "none");

  const reply = buildReply(sig, linkResults, (email.subject || "").slice(0, 120), forwarded);
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
