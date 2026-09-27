// Shared by background.js (importScripts) and popup.html (<script> tag).
// One copy of the request shape and the address-chain detection, because two
// copies of one model that can silently disagree is this repo's most-repeated
// defect -- see CLAUDE.md on the pattern tables and the email-check scoring
// model for why this file exists instead of being inlined twice.

const RS_API_BASE = "https://api.relayshield.net";
const RS_SOURCE = "chrome-extension";

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

// One entry point for "the user gave me a string, figure out what to check."
// Never guesses past what the two detectors above already decide, and never
// silently treats "unknown" as "safe" -- the level a clean answer renders is
// "unknown", not "safe", matching the API's own never-says-safe rule.
async function rsCheckAny(raw) {
  const s = raw.trim();
  if (!s) throw new Error("Paste a link or a wallet address first.");
  if (rsLooksLikeUrl(s)) {
    const data = await rsCheckLink(s);
    return { kind: "link", target: s, level: data.level, reasons: data.reasons || [] };
  }
  const chain = rsDetectChain(s);
  if (chain === "unknown") {
    throw new Error("That doesn't look like a link (http/https) or a supported wallet address (EVM, Solana, TON, Bitcoin).");
  }
  const data = await rsCheckWallet(s);
  return { kind: "wallet", target: s, level: (data.risk_level || "unknown").toLowerCase(), reasons: data.risk_flags || [] };
}
