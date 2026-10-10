/**
 * tap.relayshield.net -- TAP Verifier demo page.
 *
 * Served by the "relayshield-tap-demo" worker (wrangler.tap-demo.toml),
 * route tap.relayshield.net/*. Merchant-facing demo for the TAP verifier:
 * live endpoint, unsigned-request behavior, intent-mismatch detection, and
 * links to the developers page for pricing and API keys.
 * Staged for review. Not yet deployed.
 */

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TAP Verifier Demo - RelayShield</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
h1 { font-size: 1.8rem; }
.code { background: #f4f4f4; padding: 1rem; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: .85rem; }
.cta { display: inline-block; margin-top: 1rem; padding: .75rem 1.5rem; background: #0066cc; color: #fff; text-decoration: none; border-radius: 6px; }
.note { color: #666; font-size: .9rem; }
</style>
</head>
<body>
<h1>TAP Verifier: Know Your Agent Before It Transacts</h1>
<p>Visa's Trusted Agent Protocol lets AI agents act on a buyer's behalf. The merchant is left holding the question: is this agent who it claims to be?</p>
<p>RelayShield's TAP verifier answers that question with one API call. It checks the agent's RFC 9421 message signature, validates the signing key against Visa's JWKS, screens the agent identity against RelayShield's threat-intelligence corpus, and flags intent mismatch when an agent's actions do not match its stated purpose.</p>
<h2>Live Endpoint</h2>
<div class="code">POST https://api.relayshield.net/v1/tap/verify</div>
<h2>What It Returns</h2>
<p>Send a properly signed request and you get a decision: <strong>accept</strong> or <strong>reject</strong>, with reasons. Send an unsigned request and the verifier tells you exactly what is missing:</p>
<div class="code">{"decision": "reject", "reasons": ["missing_signature_headers"], "details": {}}</div>
<p class="note">The verifier never calls a result safe. Best case is no flags found, with the caveats that apply to any screening system.</p>
<h2>Intent Mismatch Detection</h2>
<p>TAP credentials are minted against a declared purchasing intent. A token scoped to read-only browsing that attempts a payment action is an intent mismatch, and the verifier rejects it. This catches the most common agent-fraud pattern: a legitimate credential used outside its scope.</p>
<h2>Pricing</h2>
<p>$49/month flat for regular volume, or $0.10 per verification pay as you go.</p>
<a class="cta" href="https://api.relayshield.net/developers">Get API Keys and Pricing</a>
<p class="note">Background reading: <a href="https://blog.relayshield.net/tap-verifier-ai-agents-transact">Verifying AI Agents Before They Transact</a></p>
</body>
</html>
`;

export default {
  async fetch() {
    return new Response(HTML, {
      status: 200,
      headers: { "Content-Type": "text/html;charset=UTF-8", "Cache-Control": "no-store" },
    });
  },
};
