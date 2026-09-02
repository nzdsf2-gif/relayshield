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
 * Attachments are read by NAME AND TYPE ONLY. Nothing here opens, decodes,
 * downloads or stores an attachment; a filename is metadata that arrives in
 * headers we already parse, and the file itself is untouched. Attachment names
 * are not persisted either -- they are printed back to the person who forwarded
 * the mail and then discarded with the request.
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

// Free tier.
//
// RAISED 2026-09-02 from 5/hour, which was wrong in both directions. The
// premise -- "a worried person checks two or three things in a burst" -- is
// exactly backwards: someone who has just realised they are being targeted goes
// through their inbox and forwards everything suspicious in it, which is the
// single most valuable session this product will ever have, and 5 cut them off
// mid-way. It blocked the founder inside one testing session. Meanwhile it does
// not stop an abuser, who has as many free addresses as they want.
//
// The per-day cap is what limits cost. The per-hour cap only needs to stop one
// address hammering the Worker, and 15 does that while leaving room for a real
// inbox sweep.
const RATE_LIMIT_PER_HOUR = 15;
const RATE_LIMIT_PER_DAY = 40;

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
//
// WIDENED AGAIN 2026-09-02, same day, after a MetaMask phishing message scored
// ZERO. It was "ApplyAML Meta Mask Details" <system@phrase.com>. The check
// above was gated on the sending domain being FREE WEBMAIL, and phrase.com is
// not webmail -- it is a real company's domain (Phrase, the localisation
// platform) being used to send mail claiming to be MetaMask. So no check ran at
// all, and the single loudest signal in the message went unexamined.
//
// The webmail gate was never the real rule. The real rule is:
//
//   the display name claims to be a brand, and the sending domain does not
//   belong to that brand.
//
// gmail.com is one way for that to be true. A compromised SaaS account, a
// hijacked ESP, a lookalike domain and a bulk sender are all the others, and
// they are the ones a competent attacker actually uses.
//
// So each brand carries the domains that legitimately send its mail. Anything
// else claiming that brand is flagged, webmail or not.
//
// FALSE-POSITIVE GUARD, deliberate: if the brand string appears in the sending
// domain itself, no flag. "Apple Tree Nursery" <hello@appletreenursery.com>
// contains "apple" and is a garden centre, not an impersonator. A name that
// happens to contain a brand word, on a domain built from the same word, is
// what an unrelated small business looks like.
const BRAND_DOMAINS = {
  // Payments and banking
  "paypal": ["paypal.com", "paypal.co.uk", "paypal-communication.com"],
  "stripe": ["stripe.com"],
  "venmo": ["venmo.com"],
  "cash app": ["cash.app", "square.com", "block.xyz"],
  "wise": ["wise.com", "transferwise.com"],
  "revolut": ["revolut.com"],
  "monzo": ["monzo.com"],
  "chase": ["chase.com", "jpmorgan.com"],
  "wells fargo": ["wellsfargo.com"],
  "bank of america": ["bankofamerica.com", "bofa.com"],
  "citibank": ["citi.com", "citibank.com"],
  "capital one": ["capitalone.com"],
  "hsbc": ["hsbc.com", "hsbc.co.uk"],
  "barclays": ["barclays.co.uk", "barclays.com"],
  "lloyds": ["lloydsbank.com", "lloydsbank.co.uk"],
  "natwest": ["natwest.com"],
  "santander": ["santander.co.uk", "santander.com"],
  "american express": ["americanexpress.com", "aexp.com"],
  "amex": ["americanexpress.com", "aexp.com"],
  // Crypto, where the loss is irreversible and there is no chargeback
  "coinbase": ["coinbase.com"],
  "binance": ["binance.com"],
  "kraken": ["kraken.com"],
  "gemini": ["gemini.com"],
  "metamask": ["metamask.io", "consensys.net", "consensys.io"],
  "ledger": ["ledger.com"],
  "trezor": ["trezor.io"],
  "phantom": ["phantom.app"],
  "uniswap": ["uniswap.org"],
  "opensea": ["opensea.io"],
  // Big tech account takeover
  "microsoft": ["microsoft.com", "office.com", "office365.com", "live.com", "outlook.com"],
  "office 365": ["microsoft.com", "office.com", "office365.com"],
  "apple": ["apple.com", "icloud.com"],
  "icloud": ["apple.com", "icloud.com"],
  "google": ["google.com", "gmail.com", "youtube.com"],
  "gmail": ["google.com", "gmail.com"],
  "amazon": ["amazon.com", "amazon.co.uk", "aws.amazon.com"],
  "meta": ["meta.com", "facebook.com", "facebookmail.com"],
  "facebook": ["facebook.com", "facebookmail.com", "meta.com"],
  "instagram": ["instagram.com", "mail.instagram.com", "meta.com"],
  "whatsapp": ["whatsapp.com", "meta.com"],
  "linkedin": ["linkedin.com"],
  "netflix": ["netflix.com"],
  "spotify": ["spotify.com"],
  "dropbox": ["dropbox.com", "dropboxmail.com"],
  "docusign": ["docusign.com", "docusign.net"],
  "adobe": ["adobe.com"],
  "ebay": ["ebay.com", "ebay.co.uk"],
  // Government and tax, the classic urgency lever
  "irs": ["irs.gov"],
  "hmrc": ["hmrc.gov.uk", "gov.uk"],
  "social security": ["ssa.gov"],
  "medicare": ["medicare.gov", "cms.gov"],
  "dvla": ["dvla.gov.uk", "gov.uk"],
  // Couriers, the classic pretext
  "dhl": ["dhl.com", "dhl.co.uk"],
  "fedex": ["fedex.com"],
  "ups": ["ups.com"],
  "usps": ["usps.com", "usps.gov"],
  "royal mail": ["royalmail.com", "royalmail.co.uk"],
  "evri": ["evri.com"],
  "dpd": ["dpd.co.uk", "dpd.com"],
  // Security brands, used to sell fake remediation
  "norton": ["norton.com", "nortonlifelock.com", "gendigital.com"],
  "mcafee": ["mcafee.com"],
  "geek squad": ["bestbuy.com", "geeksquad.com"],
};

/** Normalise a display name for brand matching: "Meta Mask" -> "metamask". */
function normaliseBrandText(text) {
  return (text || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * Does this display name claim a brand the sending domain does not belong to?
 * Returns the brand name, or "" if there is nothing to say.
 */
function impersonatedBrand(displayName, fromDomain) {
  const name = normaliseBrandText(displayName);
  const domain = (fromDomain || "").toLowerCase();
  if (!name || !domain) return "";
  for (const [brand, domains] of Object.entries(BRAND_DOMAINS)) {
    const key = normaliseBrandText(brand);
    if (!name.includes(key)) continue;
    // The brand's own domains, and any subdomain of them.
    if (domains.some((d) => domain === d || domain.endsWith("." + d))) return "";
    // The unrelated-small-business guard described above.
    if (normaliseBrandText(domain).includes(key)) return "";
    return brand;
  }
  return "";
}

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

// ---------------------------------------------------------------------------
// Attachments, by name and type only
// ---------------------------------------------------------------------------
//
// ADDED 2026-09-02. This was scoped for v1 and then not built, and the reply
// said nothing about attachments at all -- which reads as "we checked them and
// they were fine". It was not checking them.
//
// Name and type ONLY, deliberately. Nothing here opens, decodes or executes an
// attachment, and nothing stores one. A filename is metadata that arrives in
// the headers we already parse; the file itself is somebody else's document and
// stays untouched. That boundary is the same one the privacy note at the top of
// this file draws around the body.
//
// What a filename alone genuinely tells you is more than it sounds:
//   - an extension that is executable code, whatever it claims to be
//   - a DOUBLE extension, which exists for exactly one reason: to look like a
//     document in a file manager that hides known extensions
//   - a macro-enabled Office format, which is a document that can run code
//   - a disk image or a shortcut, the standard ways to smuggle the above past
//     a mail gateway that only inspects archives

// Extensions that are executable code or that run code on open. An attachment
// with one of these is not a document, whatever its icon suggests.
const EXECUTABLE_EXT = new Set([
  "exe", "scr", "com", "pif", "bat", "cmd", "msi", "msp", "cpl", "dll",
  "js", "jse", "vbs", "vbe", "wsf", "wsh", "hta", "ps1", "psm1", "reg",
  "jar", "apk", "app", "dmg", "pkg", "sh", "py", "scpt",
]);
// Containers whose whole purpose in phishing is to carry one of the above past
// a gateway, or to mount as a drive when double-clicked.
const CONTAINER_EXT = new Set(["iso", "img", "vhd", "vhdx", "lnk", "url"]);
// Office formats that can carry macros.
const MACRO_EXT = new Set(["docm", "xlsm", "xlsb", "pptm", "dotm", "xltm", "potm"]);
// Ordinary archives. Common in legitimate mail, so a NOTE, never a flag.
const ARCHIVE_EXT = new Set(["zip", "rar", "7z", "gz", "tar", "cab", "ace"]);
// What a double extension pretends to be.
const DOCUMENT_EXT = new Set([
  "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "csv",
  "jpg", "jpeg", "png", "gif", "htm", "html",
]);

/**
 * Pull attachment filenames out of a raw MIME message.
 *
 * Reads only the header lines -- Content-Disposition and Content-Type -- and
 * never the encoded content that follows them. Handles quoted and unquoted
 * filenames and RFC 2231 continuations, and unfolds first, because a long
 * filename is routinely folded across lines with a CRLF and a tab. (That
 * folding is what produced the 554 bounce on 2026-09-02: an unquoted filename
 * containing spaces, which Cloudflare's own inbound parser rejected outright.)
 */
function extractAttachmentNames(raw) {
  if (!raw) return [];
  const unfolded = raw.replace(/\r?\n[ \t]+/g, " ");
  const names = [];
  const re = /(?:file)?name\*?\s*=\s*(?:"([^"]*)"|([^;\r\n]+))/gi;
  let m;
  while ((m = re.exec(unfolded)) !== null && names.length < 25) {
    let v = (m[1] || m[2] || "").trim();
    if (!v) continue;
    // RFC 2231: charset'lang'percent-encoded-value
    if (/^[\w-]*'[\w-]*'/.test(v)) {
      v = v.replace(/^[\w-]*'[\w-]*'/, "");
      try { v = decodeURIComponent(v); } catch (err) { /* leave as-is */ }
    }
    v = v.replace(/[\r\n]/g, "").trim();
    if (v && !names.includes(v)) names.push(v);
  }
  return names;
}

/** Judge attachments on name and type alone. Returns { flags, notes, names }. */
function attachmentSignals(names) {
  const flags = [];
  const notes = [];
  for (const name of names) {
    const parts = name.toLowerCase().split(".");
    const ext = parts.length > 1 ? parts[parts.length - 1] : "";
    const prev = parts.length > 2 ? parts[parts.length - 2] : "";

    if (prev && DOCUMENT_EXT.has(prev) && (EXECUTABLE_EXT.has(ext) || CONTAINER_EXT.has(ext))) {
      flags.push({ weight: 3, text:
        `The attachment "${name}" has two extensions. It is a .${ext} file wearing ` +
        `a .${prev} name, and the only reason to do that is to look like a ` +
        "document in a file manager that hides known extensions." });
      continue;
    }
    if (EXECUTABLE_EXT.has(ext)) {
      flags.push({ weight: 3, text:
        `The attachment "${name}" is a .${ext} file, which is a program, not a ` +
        "document. Opening it runs code on your computer." });
      continue;
    }
    if (CONTAINER_EXT.has(ext)) {
      flags.push({ weight: 2, text:
        `The attachment "${name}" is a .${ext}, which mounts as a drive or opens a ` +
        "target when double-clicked. It is a common way to carry a program past a " +
        "mail filter." });
      continue;
    }
    if (MACRO_EXT.has(ext)) {
      flags.push({ weight: 2, text:
        `The attachment "${name}" is a macro-enabled Office file (.${ext}). It is a ` +
        "document that can run code. Do not enable content if it asks you to." });
      continue;
    }
    if (ARCHIVE_EXT.has(ext)) {
      notes.push(
        `"${name}" is an archive. We check attachments by name and type only and ` +
        "do not open them, so we cannot tell you what is inside this one.");
    }
  }
  return { flags, notes, names };
}

// ---------------------------------------------------------------------------
// A legitimate host carrying somebody else's page
// ---------------------------------------------------------------------------
//
// ADDED 2026-09-02, from a real forward whose only links were:
//   https://storage.googleapis.com/midfielders/midfielders.html?act=cl&pid=...
//
// Domain reputation is useless here and always will be. The domain is Google's.
// It has perfect DNS history, a valid certificate, no threat-feed presence, and
// it never will have any, because blocking storage.googleapis.com would break a
// large part of the internet. Every reputation system in the product returns
// "clean" or "unknown" for it, correctly, and the page is still a phishing page.
//
// What is anomalous is not the host but the COMBINATION: a bare .html file
// served out of a public object store or a free site host, arriving in mail that
// asks you to act on an account. Real companies send you to their own domain.
// They have one. That is what a company is.
//
// Deliberately weight 2 (MEDIUM on its own) and not 3. Plenty of legitimate
// things live on these hosts -- a status page, a shared document, an install
// script. It is the pairing with an ask that makes it a finding, and the ask
// already carries its own weight, so together they reach HIGH without either
// having to overclaim alone.
const PUBLIC_PAGE_HOSTS = [
  // Object stores: anyone with an account can serve any HTML from these.
  "storage.googleapis.com", "s3.amazonaws.com", "amazonaws.com",
  "blob.core.windows.net", "web.core.windows.net", "digitaloceanspaces.com",
  "r2.dev", "backblazeb2.com", "wasabisys.com",
  // Free hosting and site builders, the other half of the same pattern.
  "firebaseapp.com", "web.app", "pages.dev", "workers.dev", "netlify.app",
  "vercel.app", "github.io", "gitlab.io", "glitch.me", "repl.co",
  "weeblysite.com", "wixsite.com", "square.site", "godaddysites.com",
  "000webhostapp.com", "herokuapp.com", "onrender.com", "surge.sh",
  // Document and form services used to host a fake login step.
  "forms.gle", "docs.google.com/forms",
];

function publicHostSignal(links) {
  const hits = [];
  for (const l of links) {
    let host = "";
    try {
      host = new URL(l.url).hostname.toLowerCase();
    } catch (err) {
      continue;
    }
    const match = PUBLIC_PAGE_HOSTS.find(
      (h) => host === h || host.endsWith("." + h));
    if (match && !hits.some((x) => x.host === host)) {
      hits.push({ host, url: l.url, service: match });
    }
  }
  return hits;
}

// ---------------------------------------------------------------------------
// Does the sender's TLD exist at all?
// ---------------------------------------------------------------------------
//
// ADDED 2026-09-02, after a real phishing message forwarded from the founder's
// spam folder came back LOW RISK. It was from alert-9626@ydxla.abn. There is no
// .abn in the IANA root zone: that address cannot receive mail, cannot be
// registered, and cannot belong to any real organisation.
//
// This is the rarest kind of signal -- one with no legitimate explanation. A
// display name can be anything, a domain can be newly registered for good
// reasons, SPF can fail on honest forwarded mail. A TLD that does not exist is
// simply not a real address.
//
// The list is fetched from IANA and cached in KV for a day, rather than pinned
// in this file. A hardcoded list rots silently: new TLDs get delegated, and the
// failure mode of a stale list is calling a real company's mail forged, which
// is the worst error this Worker can make. Everything here FAILS OPEN -- no KV,
// no network, a bad response, and the check simply does not fire.
const IANA_TLD_URL = "https://data.iana.org/TLD/tlds-alpha-by-domain.txt";
const TLD_CACHE_KEY = "iana:tlds";
const TLD_CACHE_TTL = 86400;

async function knownTlds(kv) {
  if (!kv) return null;                      // fail open
  try {
    const cached = await kv.get(TLD_CACHE_KEY);
    if (cached) return new Set(JSON.parse(cached));
  } catch (err) {
    // fall through to a fetch
  }
  try {
    const resp = await fetch(IANA_TLD_URL, { cf: { cacheTtl: TLD_CACHE_TTL } });
    if (!resp.ok) return null;
    const list = (await resp.text())
      .split("\n")
      .map((l) => l.trim().toLowerCase())
      .filter((l) => l && !l.startsWith("#"));
    // A truncated or error response must never become "every TLD is invalid".
    if (list.length < 1000) return null;
    try {
      await kv.put(TLD_CACHE_KEY, JSON.stringify(list), { expirationTtl: TLD_CACHE_TTL });
    } catch (err) { /* caching is best effort */ }
    return new Set(list);
  } catch (err) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// What the message is actually asking for
// ---------------------------------------------------------------------------
//
// Also added 2026-09-02 from the same message. Its body read: "Payment failed
// for your Cloud storage renewal ... Update your payment details within 24
// hours or your files will be permanently deleted."
//
// That is the entire mechanism of phishing in one sentence: an ASK, a DEADLINE
// and a THREAT. Any one alone is ordinary -- real companies do say "action
// required", real invoices do have due dates. The combination is not. So the
// flag needs an ask AND pressure, never either on its own, which is what keeps
// it off legitimate billing mail.
const ASK_PHRASES = [
  "update your payment", "update your billing", "update your card",
  "verify your account", "verify your identity", "confirm your identity",
  "confirm your account", "validate your account", "reactivate your account",
  "update your details", "update your information", "confirm your password",
  "sign in to continue", "log in to continue", "click here to", "click below to",
  "re-enter your", "reconfirm your", "restore your account",
  // ADDED 2026-09-02 from a live MetaMask-impersonating message. Its ask was
  // "please add your email now", with no deadline and no threat -- a softer
  // shape than the classic "verify or lose access", and increasingly the common
  // one, because it reads as helpful housekeeping rather than an emergency.
  "add your email", "add your email address", "confirm your email",
  "verify your email", "update your email", "email-based sign-in",
  "email based sign in", "link your email", "we need your email",
  "just click the button", "click the button below",
];
const DEADLINE_PHRASES = [
  "within 24 hours", "within 48 hours", "within 72 hours", "in the next 24",
  "expires today", "expires tomorrow", "final notice", "last warning",
  "final reminder", "immediately to avoid", "act now", "urgent action",
];
const THREAT_PHRASES = [
  "permanently deleted", "will be deleted", "will be suspended",
  "will be closed", "will be terminated", "will be locked", "lose access",
  "loss of access", "legal action", "account has been suspended",
  "unauthorized access", "unauthorised access", "unusual activity",
];

function pressureSignals(bodyText) {
  const t = (bodyText || "").toLowerCase();
  const ask = ASK_PHRASES.find((p) => t.includes(p));
  const deadline = DEADLINE_PHRASES.find((p) => t.includes(p));
  const threat = THREAT_PHRASES.find((p) => t.includes(p));
  return { ask, deadline, threat };
}

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
function headerSignals(email, headers, forwarded, ctx2) {
  const { bodyText = "", tlds = null, attachments = null, links = [] } = ctx2 || {};
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

  // Brand impersonation, on ANY domain. This no longer requires free webmail:
  // see the note on BRAND_DOMAINS for why that gate was the wrong rule.
  const brand = impersonatedBrand(fromName, fromDomain);
  if (brand) {
    const Brand = brand.replace(/\b\w/g, (c) => c.toUpperCase());
    flags.push({ weight: 3, text:
      `The display name says "${fromName}", but the message was sent from ` +
      `${fromDomain}. That domain does not belong to ${Brand}. A display name is ` +
      "typed by whoever sent the message and is not checked by anything, so it " +
      "is the cheapest thing in an email to fake. If you have an account with " +
      `${Brand}, go to their site or app yourself and look there. Nothing in ` +
      "this message should be clicked to get to it." });
  } else if (fromName && WEBMAIL.has(fromDomain)) {
    // The role-name case only makes sense on webmail: a department name on a
    // company's own domain is just a department.
    const nameLower = fromName.toLowerCase();
    const authority = AUTHORITY_WORDS.find((w) => nameLower.includes(w));
    if (authority) {
      flags.push({ weight: 2, text:
        `The display name "${fromName}" presents as a department or a support ` +
        `desk, but the address is a free ${fromDomain} account. A real ` +
        "organisation writes from its own domain." });
    }
  }

  // A TLD that does not exist. No legitimate explanation, so this outranks
  // every other header signal here.
  const tld = fromDomain.includes(".") ? fromDomain.split(".").pop() : "";
  if (tlds && tld && !tlds.has(tld)) {
    flags.push({ weight: 3, text:
      `There is no ".${tld}" on the internet. ${fromAddr} cannot be a real ` +
      "address: that suffix is not in the global list of domain endings, so no " +
      "one can register it and no mail can be delivered to it. A real company " +
      "cannot have this address by mistake." });
  }

  // The display name is the RECIPIENT's own account name, on somebody else's
  // domain. That is impersonating you to you, and it is what the 2026-09-02
  // sample did: "nzdsf2 <alert-9626@ydxla.abn>" landing in nzdsf2's mailbox.
  const recipientLocal = (ctx2 && ctx2.recipientLocal ? ctx2.recipientLocal : "").toLowerCase();
  if (recipientLocal.length >= 4 && fromName &&
      fromName.toLowerCase().trim() === recipientLocal &&
      !fromAddr.toLowerCase().startsWith(recipientLocal + "@")) {
    flags.push({ weight: 2, text:
      `The sender's display name is "${fromName}", which is your own account ` +
      `name, but the address behind it is ${fromAddr}. Showing you your own ` +
      "name is meant to make the message feel like it belongs in your mailbox." });
  }

  // Ask plus pressure. Either alone is ordinary; together they are the
  // mechanism of phishing stated outright.
  const pressure = pressureSignals(bodyText);
  if (pressure.ask && (pressure.deadline || pressure.threat)) {
    const lever = pressure.threat
      ? `and pressures you with the phrase "${pressure.threat}"`
      : `and puts a deadline on it: "${pressure.deadline}"`;
    flags.push({ weight: 2, text:
      `The message asks you to "${pressure.ask}" ${lever}. Being asked to act on ` +
      "your account AND being hurried are the two halves of almost every " +
      "phishing message. A real company that needs something from you can wait " +
      "for you to go to their site yourself." });
  }

  for (const hit of publicHostSignal(links)) {
    flags.push({ weight: 2, text:
      `The link goes to ${hit.host}, which is a public file-hosting service, not ` +
      "a company's own website. Anyone can upload a page there, and the page " +
      "borrows the host's good reputation: no threat database will ever flag " +
      `${hit.service}, because blocking it would break a large part of the ` +
      "internet. A real company sends you to its own domain, because it has one." });
  }

  if (attachments) {
    attachments.flags.forEach((f) => flags.push(f));
    attachments.notes.forEach((n) => notes.push(n));
  }

  const score = flags.reduce((n, f) => n + f.weight, 0);
  return { flags, notes, score, auth, authIsAboutOriginal, fromAddr, fromName,
           fromDomain, attachmentNames: attachments ? attachments.names : [] };
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
function detectForwardedOriginal(bodyText, forwarderAddress) {
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
  //
  // Line-anchored FIRST, because that is what a well-formed quoted block looks
  // like and it bounds the match tightly. Then unanchored, because a quoted
  // block is drawn by the forwarding client rather than being a real header:
  // it can arrive wrapped, entity-encoded, or (before the stripHtml fix above)
  // flattened onto a single line. The unanchored form stops at the next header
  // keyword so it cannot swallow the rest of the message.
  const m = after.match(/^\s*(?:>\s*)?From:\s*(.+)$/im)
         || after.match(/From:\s*(.+?)(?:\s+(?:Date|Sent|Subject|To|Cc|Reply-To):|$)/is);
  if (!m) return { address: "", name: "", parseFailed: true };
  const parsed = parseAddress(m[1].trim());

  // The forwarder's own address is NEVER the original sender.
  //
  // ADDED 2026-09-02, after a reply told the reader "the original sender shows
  // in the quoted text as nzdsf2@gmail.com" -- which is the address of the
  // person who forwarded it to us. Whatever went wrong upstream, reporting
  // someone their own address as the suspicious sender is worse than reporting
  // nothing: it is confidently wrong, and it silently points every
  // sender-based check at an innocent account, which is how a message with a
  // nonexistent TLD came back scoring zero.
  //
  // "We could not read the original sender" is an honest answer the reply copy
  // already handles. This is the cheap, certain rule that keeps us in it.
  const forwarder = (forwarderAddress || "").toLowerCase();
  if (parsed.address && forwarder && parsed.address === forwarder) {
    return { address: "", name: "", parseFailed: true, selfMatch: true };
  }

  return {
    address: parsed.address || "",
    name: parsed.name || "",
    // parseFailed means "we could not read a sender", which is what the reply
    // copy keys on. A From: line we found but could not turn into an address
    // is the same outcome for the reader as no From: line at all.
    parseFailed: !parsed.address,
  };
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
    // BLOCK STRUCTURE, FIXED 2026-09-02. Every tag used to become a space, so
    // an HTML message collapsed into ONE line -- and a quoted forward header
    // block ("From: ... Date: ... Subject: ...") stopped being lines at all.
    // detectForwardedOriginal anchors on a line starting with From:, so on any
    // HTML forward it found the marker, failed to find a sender, and reported a
    // forward with nobody in it. Turning block boundaries into newlines is what
    // keeps a quoted header block readable as a header block.
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(div|p|tr|li|h[1-6]|blockquote|table)\s*>/gi, "\n")
    .replace(/<(div|p|tr|li|h[1-6]|blockquote|table)\b[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    // ENTITIES, FIXED 2026-09-02. Only &nbsp; and &amp; were decoded, so &lt;
    // and &gt; survived into the extracted text. A Gmail forward of an HTML
    // message quotes the original header block as markup, so the line
    //     From: nzdsf2 &lt;alert-9626@ydxla.abn&gt;
    // reached parseAddress with entities still in it, matched no angle
    // brackets, and yielded no address at all. detectForwardedOriginal
    // therefore reported "this is a forward" with an empty sender, every
    // sender-based check silently had nothing to work on, and a message with a
    // nonexistent TLD scored zero. Decoding is not cosmetic here; it is the
    // difference between analysing the sender and analysing nothing.
    .replace(/&nbsp;/gi, " ")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#0?39;|&apos;/gi, "'")
    .replace(/&#(\d{1,7});/g, (_, d) => {
      const n = parseInt(d, 10);
      return n > 0 && n < 0x110000 ? String.fromCodePoint(n) : " ";
    })
    .replace(/&#x([0-9a-f]{1,6});/gi, (_, h) => {
      const n = parseInt(h, 16);
      return n > 0 && n < 0x110000 ? String.fromCodePoint(n) : " ";
    })
    // &amp; LAST, so "&amp;lt;" does not become "<" in two passes.
    .replace(/&amp;/gi, "&")
    // Collapse horizontal runs only. A blanket /\s+/ would undo the newlines
    // that were just so carefully introduced.
    .replace(/[ \t\f\v\u00a0]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Decode an RFC 2047 encoded-word header ("=?UTF-8?Q?...?=" / "=?UTF-8?B?...?=").
 *
 * ADDED 2026-09-02. The reply printed a subject back to the reader as
 *
 *   Subject checked: =?UTF-8?Q?Fwd=3A_=F0=9F=9A=A8_Action_Required=3A_Storage_100=25_Full?=
 *
 * Any subject with a non-ASCII character -- an emoji, an accent, a currency
 * symbol -- arrives encoded like that, and phishing subjects are full of emoji,
 * so this hits precisely the messages the product exists for. It is not a small
 * cosmetic problem: it is the first line the reader sees, and it says we did not
 * understand their email.
 */
function decodeEncodedWords(value) {
  if (!value || !value.includes("=?")) return value || "";
  return value
    // Adjacent encoded words join with the whitespace between them dropped,
    // per RFC 2047. Done first so the decode below sees one continuous run.
    .replace(/\?=\s+=\?/g, "?==?")
    .replace(/=\?([^?]+)\?([BbQq])\?([^?]*)\?=/g, (whole, charset, enc, text) => {
      try {
        let bytes;
        if (enc.toUpperCase() === "B") {
          const bin = atob(text.replace(/\s+/g, ""));
          bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
        } else {
          // Q encoding: "_" is a space, "=XX" is a hex byte.
          const q = text.replace(/_/g, " ");
          const out = [];
          for (let i = 0; i < q.length; i++) {
            if (q[i] === "=" && /^[0-9A-Fa-f]{2}$/.test(q.slice(i + 1, i + 3))) {
              out.push(parseInt(q.slice(i + 1, i + 3), 16));
              i += 2;
            } else {
              out.push(q.charCodeAt(i) & 0xff);
            }
          }
          bytes = Uint8Array.from(out);
        }
        // An unknown charset falls back to UTF-8 rather than failing the
        // decode: a slightly wrong character beats raw encoding at the reader.
        return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
      } catch (err) {
        return whole;   // undecodable: keep the text rather than lose it
      }
    });
}

/**
 * From: / Reply-To: style value -> { address, name }.
 *
 * HARDENED 2026-09-02. This used to take whatever sat between the first pair of
 * angle brackets and call it an address. That is fine for a real header, which
 * Cloudflare hands us already parsed -- and wrong for the other caller, which is
 * detectForwardedOriginal reading a quoted forward block out of a message BODY.
 *
 * A quoted block is not a header. It is whatever the forwarding client drew,
 * and after stripHtml a Gmail forward of an HTML message yields:
 *
 *   From: nzdsf2 < mailto:alert-9626@ydxla.abn alert-9626@ydxla.abn >
 *
 * because the <a href="mailto:..."> is unwrapped to its href plus its text. The
 * old regex returned that entire run as the address, which matches no domain
 * and quietly disables every sender-based check.
 *
 * So: locate the angle brackets if present, then find the thing that is
 * actually shaped like an address INSIDE them, and fall back to scanning the
 * whole value. Returning no address is a valid answer and is better than
 * returning a wrong one -- a wrong one is what produces a confident verdict
 * about a sender that does not exist.
 */
function parseAddress(value) {
  if (!value) return { address: "", name: "" };
  const EMAIL = /[^\s<>@,;:"']+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

  const angled = value.match(/^\s*(.*?)\s*<([^>]*)>/);
  if (angled) {
    const inner = angled[2].replace(/^mailto:/i, "");
    const hit = inner.match(EMAIL);
    if (hit) {
      return {
        address: hit[0].replace(/^mailto:/i, "").toLowerCase(),
        name: angled[1].replace(/^["']|["']$/g, "").trim(),
      };
    }
  }

  const bare = value.match(EMAIL);
  if (bare) {
    return {
      address: bare[0].replace(/^mailto:/i, "").toLowerCase(),
      // Everything before the address, with the punctuation a quoted block
      // leaves lying around removed.
      name: value.slice(0, value.indexOf(bare[0]))
                 .replace(/["'<>]/g, "").replace(/mailto:/gi, "").trim(),
    };
  }
  return { address: "", name: value.trim() };
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
 * Every RelayShield API endpoint answers through _ok() in relayshield_api.py,
 * which returns { ok: true, data: { ... } }. The payload is one level down.
 *
 * FIXED 2026-09-02. scanLink read `data.analysis_id` and `data.immediate_signal`
 * off the TOP level, where neither exists -- the top level holds only `ok` and
 * `data`. So analysis_id was always undefined and every link came back
 * "no analysis was started for this link", while immediate_signal was always
 * undefined too, meaning the RelayShield IOC corpus, Google Safe Browsing and
 * domain-age checks were never consulted at all.
 *
 * This is the SECOND bug in this function with the same shape. The first read a
 * field that exists but never carries a verdict; this one read fields that were
 * never at that level. Both produced a confident-looking "UNKNOWN" that was
 * really "we did not look". A checker that cannot check must say so, and this
 * one was saying nothing.
 *
 * Tolerant on purpose: a bare payload passes through untouched, so this keeps
 * working if an endpoint is ever served without the envelope.
 */
function unwrap(body) {
  if (body && typeof body === "object" && body.data && typeof body.data === "object") {
    return body.data;
  }
  return body || {};
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
    submitted = unwrap(await resp.json());
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
      const data = unwrap(await resp.json());
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
    out.push("  To get that answer, forward it AS AN ATTACHMENT instead. Do this from");
    out.push("  the message LIST, not from the opened message, because the option is");
    out.push("  missing from the menu inside an open message:");
    out.push("    Gmail: go back to the list, tick the checkbox beside the message,");
    out.push("      then the three-dot More button in the toolbar ABOVE the list,");
    out.push("      then Forward as attachment.");
    out.push("    Outlook on the web: tick the message in the list, then the three-dot");
    out.push("      menu in the toolbar, then Forward as attachment.");
    out.push("    Apple Mail: click the message in the list once, then the Message menu");
    out.push("      at the top of the screen, then Forward as Attachment.");
    out.push("  If you cannot find it, forward it inline as you did. We still read the");
    out.push("  sender, the links and the attachment names. We just cannot verify the");
    out.push("  original's authentication.");
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

  // Always stated, including when there are none. Saying nothing about
  // attachments reads as "we checked them and they were fine", and until
  // 2026-09-02 that is exactly what the silence meant while nothing was
  // being checked at all.
  const names = sig.attachmentNames || [];
  if (names.length) {
    out.push(`ATTACHMENTS (${names.length}), checked by name and type only:`);
    names.forEach((n) => out.push(`  ${n}`));
    out.push("");
    out.push("  We do not open attachments. We look at what the file claims to be,");
    out.push("  which catches a program dressed as a document but cannot tell you");
    out.push("  what is inside a file that is what it says it is.");
  } else {
    out.push("ATTACHMENTS: none.");
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
    // Cloudflare allows exactly ONE reply per message, and it counts an
    // ATTEMPT, not a success. On 2026-09-02 the real reply threw on a bad
    // References header and the fallback below then failed with "mail has
    // already been replied to", turning one clear error into two confusing
    // ones. This flag makes the fallback fire only when no reply was ever
    // attempted -- which is the only case where it can actually work.
    const replyState = { attempted: false };
    try {
      await scanAndReply(message, env, ctx, replyState);
    } catch (err) {
      console.error(
        "checkemail: FAILED for", message.from, "--",
        err && err.stack ? err.stack : String(err)
      );
      // ADDED 2026-09-02, after a forwarded spam message produced no reply at
      // all. The comment above this handler already said silence is the worst
      // of the three outcomes; it was not actually preventing one. A person who
      // forwarded something frightening and hears nothing back does not know
      // whether we are still looking, whether it was safe, or whether the
      // address works.
      //
      // Best effort, and deliberately last: if the reply itself is what failed,
      // this fails too, and then the rethrow below gives the sender a bounce --
      // which is at least a signal.
      if (replyState.attempted) {
        console.error(
          "checkemail: no fallback sent -- a reply was already attempted for",
          message.from, "and Cloudflare permits only one. The sender gets a",
          "bounce from the rethrow below.");
        throw err;
      }
      try {
        await message.reply(makeReply(message,
          "RelayShield could not finish checking that message.\n\n" +
          "This is a fault at our end, not a verdict on the email. Treat it as " +
          "UNCHECKED: do not click links in it and do not enter a password or " +
          "payment detail from it until you have confirmed it another way.\n\n" +
          "It often helps to forward it again as an attachment. From the message " +
          "LIST (not the opened message): tick the checkbox, then the three-dot " +
          "More button in the toolbar above the list, then Forward as " +
          "attachment.\n\n" +
          "RelayShield: https://relayshield.net?source=email-scan"));
      } catch (replyErr) {
        console.error("checkemail: fallback reply also failed --",
                      replyErr && replyErr.stack ? replyErr.stack : String(replyErr));
      }
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
  const rawSubject = decodeEncodedWords(message.headers.get("subject") || "")
                     || "your email check";
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

  // References is NOT just the message we are replying to.
  //
  // FIXED 2026-09-02, and this crash was self-inflicted: References was added
  // earlier the same day as part of "make the reply a valid RFC 5322 message",
  // set to the original Message-ID alone. Cloudflare validates it against the
  // thread and rejected the reply outright:
  //
  //   Error: provided References header is invalid; expected
  //   <51977-nzdsf2@sH994It.abn> <CAA5...@mail.gmail.com> <CAA5...@mail.gmail.com>
  //
  // The correct value is the INCOMING message's own References chain with the
  // incoming Message-ID appended -- that is what continues a thread rather than
  // starting a new one. A forwarded message almost always carries a chain
  // already (the original's id, plus the forward), which is exactly why this
  // never showed up on a freshly composed test message and did show up on the
  // first real forward.
  const priorRefs = (message.headers.get("references") || "")
    .replace(/\s+/g, " ").trim();
  const references = [priorRefs, originalId].filter(Boolean).join(" ").slice(0, 900);
  const ourId = `<${Date.now()}.${Math.random().toString(36).slice(2, 12)}@relayshield.net>`;

  const headers = [
    `From: RelayShield <checkemail@relayshield.net>`,
    `To: ${to}`,
    `Message-ID: ${ourId}`,
    `Date: ${new Date().toUTCString()}`,
    // Only when the original actually had one. An empty value is malformed.
    ...(originalId ? [`In-Reply-To: ${originalId}`] : []),
    ...(references ? [`References: ${references}`] : []),
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
async function scanAndReply(message, env, ctx, replyState) {
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
    // LOGGED as of 2026-09-02. Dropping was always deliberate; being unable to
    // tell a drop from a crash was not. A forwarded spam message can easily
    // carry Precedence: bulk or an Auto-Submitted header from the original,
    // and when that happened the sender got silence and the log said nothing.
    console.log(
      "checkemail: DROPPED by loop guard --",
      "from=", sender || "(empty)",
      "auto-submitted=", autoSubmitted || "(none)",
      "precedence=", precedence || "(none)");
    return;
  }

  // An allowlist for testing and for anyone we have a reason to exempt. Set with
  //   npx wrangler secret put CHECKEMAIL_UNLIMITED --config wrangler.checkemail.toml
  // as a comma-separated list of addresses. Absent means nobody is exempt.
  const exempt = (env.CHECKEMAIL_UNLIMITED || "")
    .toLowerCase().split(",").map((a) => a.trim()).filter(Boolean)
    .includes(sender);

  if (!exempt && await rateLimited(env.CHECKEMAIL_RL, sender)) {
    if (replyState) replyState.attempted = true;
    // Says WHEN, not "shortly". A person told to wait an unspecified time by an
    // automated system assumes it is broken, and the one thing this reply must
    // not do is look like a failure -- they forwarded something because they
    // were worried about it.
    const mins = 60 - new Date().getMinutes();
    await message.reply(
      makeReply(message,
        "RelayShield: rate limit reached\n\n" +
        `The free email check allows ${RATE_LIMIT_PER_HOUR} messages an hour and ` +
        `${RATE_LIMIT_PER_DAY} a day. Your hourly allowance resets in about ` +
        `${mins} minute${mins === 1 ? "" : "s"}.\n\n` +
        "Nothing was checked, so treat that message as unchecked: do not click " +
        "links in it and do not enter a password or payment detail from it until " +
        "you have confirmed it another way.\n\n" +
        "For continuous monitoring rather than one-off checks, see " +
        "https://relayshield.net?source=email-scan")
    );
    return;
  }

  // Headers come from Cloudflare already parsed. Only the body needs reading,
  // and a body we cannot read still yields a header-only verdict -- which is
  // the strongest half anyway -- so this never aborts the scan.
  let bodyText = "";
  let attachmentNames = [];
  try {
    const raw = await new Response(message.raw).text();
    bodyText = extractText(raw).slice(0, MAX_BODY_CHARS);
    // Names and types only. The raw text is read once here and never stored.
    attachmentNames = extractAttachmentNames(raw);
  } catch (err) {
    bodyText = "";
  }

  const email = {
    from: parseAddress(message.headers.get("from")),
    replyTo: [parseAddress(message.headers.get("reply-to"))],
    subject: decodeEncodedWords(message.headers.get("subject") || ""),
  };
  const body = bodyText;

  // Whose message is this? Must be decided BEFORE the signals, because on an
  // inline forward the authentication headers describe the person asking us
  // rather than the message they are asking about.
  const forwarded = detectForwardedOriginal(body, sender);

  // The IANA list is cached in KV and fails open: without the binding, or if
  // the fetch fails, tlds is null and the check simply does not fire. It must
  // never be possible for a network problem to call a real domain forged.
  const tlds = await knownTlds(env.CHECKEMAIL_RL);

  // Links are scanned BEFORE the signals, because one of the signals is about
  // where the links point -- a page served from a public object store cannot be
  // judged from the headers alone.
  const links = extractLinks(body).slice(0, MAX_LINKS_CHECKED);
  const deadline = Date.now() + LINK_SCAN_BUDGET_MS;
  const linkResults = env.RS_API_KEY
    ? await Promise.all(links.map((u) => scanLink(u, env.RS_API_KEY, deadline)))
    : links.map((u) => ({
        url: u, status: "unknown",
        detail: "link checking is not configured on this deployment",
      }));

  const sig = headerSignals(email, message.headers, forwarded, {
    bodyText: body,
    links: linkResults,
    tlds,
    attachments: attachmentSignals(attachmentNames),
    // Who is asking us. Used to spot a display name that copies their own
    // account name onto somebody else's address.
    recipientLocal: (sender.split("@")[0] || ""),
  });

  // The forward parse is logged in full because it is where every wrong verdict
  // so far has originated, and each time it was diagnosed by guessing rather
  // than by reading. A one-line record of what was actually extracted turns the
  // next wrong answer into a five-second read.
  console.log(
    "checkemail: scanned", message.from,
    "forwarded=", forwarded
      ? `yes(sender=${forwarded.address || "UNPARSED"}${forwarded.selfMatch ? ",selfMatch" : ""})`
      : "no",
    "score=", sig.score,
    "flags=", sig.flags.length,
    "attachments=", attachmentNames.length,
    "tldlist=", tlds ? tlds.size : "unavailable",
    "links=", linkResults.map((l) => `${l.status}:${l.detail}`).join(" | ") || "none",
    "bodyhead=", JSON.stringify(body.slice(0, 300)));

  const reply = buildReply(sig, linkResults, (email.subject || "").slice(0, 120), forwarded);
  if (replyState) replyState.attempted = true;
  await message.reply(makeReply(message, reply));
  console.log("checkemail: REPLIED to", message.from, "risk=",
              reply.split(" RISK")[0].replace("RelayShield email check: ", ""));

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
