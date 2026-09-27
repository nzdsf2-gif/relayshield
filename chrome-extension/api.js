// Shared by background.js (importScripts) and popup.html (<script> tag).
// One copy of the request shape and the address-chain detection, because two
// copies of one model that can silently disagree is this repo's most-repeated
// defect -- see CLAUDE.md on the pattern tables and the email-check scoring
// model for why this file exists instead of being inlined twice.

const RS_API_BASE = "https://api.relayshield.net";
const RS_SOURCE = "chrome-extension";

// Filled in once the extension is actually live on the Chrome Web Store --
// its item id is assigned by Chrome at publish time, so there is nothing
// real to put here before then. Left empty rather than guessed, same
// pattern as WA_NUMBER in cloudflare_worker_miniapp.js: the share feature
// below falls back to a link that already works today (the Mini App) until
// this is set, rather than ever sharing a broken or placeholder URL.
const RS_STORE_URL = "";

// What a "share" actually links to: the store listing once it exists, and
// the Mini App (live today, no install needed) until then. A friend without
// the extension can still get real value from either.
function rsShareUrl() {
  return RS_STORE_URL ||
    "https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-chromeext";
}

// The message a "share" action copies. Framed around what the check just
// found, not a generic "try this extension" -- the moment right after a
// result is the one point where the value is concrete rather than abstract.
function rsShareText(summary) {
  return `I just checked ${summary} with RelayShield -- free scam/phishing ` +
    `and wallet-risk screening, no signup: ${rsShareUrl()}`;
}

// A SEPARATE share, decoupled from having just run a check -- somebody who
// likes the extension in general has no specific verdict to reference, and
// making that person wait for a flagged result before they can recommend it
// is the same gap as never offering the check-result share at all.
function rsGenericShareText() {
  return "Check any link, wallet address, or suspicious email for scams -- " +
    `free, no signup: ${rsShareUrl()}`;
}

// Mirrors relayshield_api.py's _detect_chain_api exactly. The SERVER is the
// authority -- if this guesses wrong, the API answers "unrecognised address
// format" rather than a silently wrong verdict, so drift here is a UX papercut,
// not a correctness bug. Still kept in sync deliberately.
function rsDetectChain(address) {
  if (/^0x[0-9a-fA-F]{40}$/.test(address)) return "evm";
  if (/^[EUeu][Qq][A-Za-z0-9_-]{46}$/.test(address)) return "ton";
  if (/^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$/.test(address)) return "bitcoin";
  if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address)) return "solana";
  return "unknown";
}

function rsLooksLikeUrl(s) {
  return /^https?:\/\//i.test(s.trim());
}

// Explorer/DEX/aggregator pages put the actual on-chain address IN THE URL
// (jup.ag/tokens/<mint>, solscan.io/token/<mint>, etherscan.io/token/<addr>,
// dexscreener.com/solana/<pair>, birdeye.so/token/<mint>, ...) -- checking
// only the domain (jup.ag, solscan.io, etherscan.io -- all huge, legitimate
// platforms) answers a question nobody asked and misses the one thing the
// user actually wants screened. Rather than hard-coding a pattern per site,
// this walks every path segment and query value and reuses rsDetectChain,
// the same authority the bare-address path already trusts -- one host-agnostic
// rule instead of an every-growing per-platform list.
function rsExtractEmbeddedAddress(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const candidates = [
    ...parsed.pathname.split("/").filter(Boolean),
    ...[...parsed.searchParams.values()],
  ];
  for (const segment of candidates) {
    const chain = rsDetectChain(segment);
    if (chain !== "unknown") return { address: segment, chain };
  }
  return null;
}

async function rsCheckLink(url) {
  const resp = await fetch(`${RS_API_BASE}/v1/link-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, source: RS_SOURCE }),
  });
  const json = await resp.json();
  if (!resp.ok || !json.ok) {
    throw new Error(json.error || `link-check failed (${resp.status})`);
  }
  return json.data;
}

async function rsCheckWallet(address) {
  const resp = await fetch(`${RS_API_BASE}/v1/wallet-risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, source: RS_SOURCE }),
  });
  const json = await resp.json();
  if (!resp.ok || !json.ok) {
    throw new Error(json.error || `wallet-risk failed (${resp.status})`);
  }
  return json.data;
}

// /v1/email-check is built for a caller that has ALREADY PARSED the message
// (an agent reading a mailbox), not a raw pasted blob -- it does not extract
// links itself. The extension is exactly that caller here: pull links out of
// the pasted body text client-side before sending, the same way a mailbox
// agent would have them already split out.
function rsExtractLinks(text) {
  const matches = text.match(/https?:\/\/[^\s<>"')]+/g) || [];
  return [...new Set(matches)].slice(0, 25);
}

async function rsCheckEmail({ fromAddress, subject, bodyText }) {
  if (!fromAddress && !subject && !bodyText) {
    throw new Error("Fill in at least the sender address, subject, or body.");
  }
  const resp = await fetch(`${RS_API_BASE}/v1/email-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      from_address: fromAddress || undefined,
      subject: subject || undefined,
      body_text: bodyText || undefined,
      links: bodyText ? rsExtractLinks(bodyText) : undefined,
      source: RS_SOURCE,
    }),
  });
  const json = await resp.json();
  if (!resp.ok || !json.ok) {
    throw new Error(json.error || `email-check failed (${resp.status})`);
  }
  return json.data;
}

// Worse wins: a clean domain carrying a flagged token must never render as
// the clean verdict just because the domain check happened to be listed
// first. Same ordering the API's own _link_check_level uses.
const RS_LEVEL_RANK = { high: 3, medium: 2, low: 1, unknown: 0 };

// One entry point for "the user gave me a string, figure out what to check."
// Never guesses past what the two detectors above already decide, and never
// silently treats "unknown" as "safe" -- the level a clean answer renders is
// "unknown", not "safe", matching the API's own never-says-safe rule.
async function rsCheckAny(raw) {
  const s = raw.trim();
  if (!s) throw new Error("Paste a link or a wallet address first.");

  if (rsLooksLikeUrl(s)) {
    const embedded = rsExtractEmbeddedAddress(s);
    if (!embedded) {
      const data = await rsCheckLink(s);
      return { kind: "link", target: s, level: data.level, reasons: data.reasons || [] };
    }
    // Explorer/DEX page: check the domain AND the address it's actually
    // showing, in parallel, and let the worse of the two decide the headline.
    const [linkData, walletData] = await Promise.all([
      rsCheckLink(s),
      rsCheckWallet(embedded.address),
    ]);
    const linkLevel = linkData.level;
    const walletLevel = (walletData.risk_level || "unknown").toLowerCase();
    const worse = RS_LEVEL_RANK[walletLevel] > RS_LEVEL_RANK[linkLevel] ? walletLevel : linkLevel;
    const reasons = [
      ...(linkData.reasons || []).map((r) => `Domain (${new URL(s).hostname}): ${r}`),
      ...(walletData.risk_flags || []).map((r) => `${embedded.chain.toUpperCase()} address in the URL: ${r}`),
    ];
    return {
      kind: "link", target: s, level: worse, reasons,
      embeddedAddress: embedded.address, embeddedChain: embedded.chain,
    };
  }

  const chain = rsDetectChain(s);
  if (chain === "unknown") {
    throw new Error("That doesn't look like a link (http/https) or a supported wallet address (EVM, Solana, TON, Bitcoin).");
  }
  const data = await rsCheckWallet(s);
  return { kind: "wallet", target: s, level: (data.risk_level || "unknown").toLowerCase(), reasons: data.risk_flags || [] };
}
