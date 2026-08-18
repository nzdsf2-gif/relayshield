// pricing.relayshield.net — Crypto Shield Mobile pricing page
// Stripe Payment Links — replace with real plink_ URLs from Stripe Dashboard
const STRIPE_MONTHLY = "https://buy.stripe.com/4gMdRa7Yq7OZf9aesn0Ny0g";
const STRIPE_ANNUAL  = "https://buy.stripe.com/6oUdRabaC4CN4uwbgb0Ny0h";

addEventListener("fetch", event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);

  // Redirect /monthly and /annual directly to Stripe
  if (url.pathname === "/monthly") return Response.redirect(STRIPE_MONTHLY, 302);
  if (url.pathname === "/annual")  return Response.redirect(STRIPE_ANNUAL,  302);

  return new Response(html(), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function html() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Shield Pricing — RelayShield</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0a1628;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px 60px;
  }
  .logo { font-size: 48px; margin-bottom: 12px; }
  h1 { font-size: 32px; font-weight: 800; color: #f1f5f9; text-align: center; }
  .sub { color: #64748b; margin-top: 8px; font-size: 15px; text-align: center; max-width: 480px; line-height: 1.6; }

  .plans {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 20px;
    width: 100%;
    max-width: 700px;
    margin: 40px 0;
  }
  .plan {
    background: #0F1F3D;
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 28px 24px;
    display: flex;
    flex-direction: column;
  }
  .plan.featured {
    border-color: #00B5A5;
    border-width: 2px;
  }
  .badge {
    display: inline-block;
    background: #00B5A5;
    color: #0a1628;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.5px;
    padding: 3px 8px;
    border-radius: 6px;
    margin-bottom: 16px;
    text-transform: uppercase;
  }
  .plan-name { font-size: 14px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
  .price { font-size: 36px; font-weight: 800; color: #f1f5f9; }
  .price span { font-size: 16px; font-weight: 500; color: #64748b; }
  .per { font-size: 12px; color: #475569; margin-top: 4px; margin-bottom: 20px; }
  .features { list-style: none; margin-bottom: 24px; flex: 1; }
  .features li { font-size: 13px; color: #94a3b8; padding: 5px 0; display: flex; gap: 8px; align-items: flex-start; }
  .features li::before { content: "✓"; color: #00B5A5; font-weight: 700; flex-shrink: 0; }
  .features li.dim::before { color: #334155; }
  .features li.dim { color: #334155; }
  .btn {
    display: block;
    text-align: center;
    padding: 14px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 15px;
    text-decoration: none;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.85; }
  .btn-primary { background: #00B5A5; color: #0a1628; }
  .btn-outline { border: 1px solid #00B5A5; color: #00B5A5; background: transparent; }

  .comparison { width: 100%; max-width: 700px; background: #0F1F3D; border-radius: 16px; border: 1px solid #1e3a5f; padding: 28px 24px; margin-bottom: 40px; }
  .comparison h2 { font-size: 16px; font-weight: 700; color: #94a3b8; margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; }
  th { font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px; text-align: left; border-bottom: 1px solid #1e3a5f; }
  td { font-size: 13px; color: #94a3b8; padding: 10px 12px; border-bottom: 1px solid #0a1628; vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  .check { color: #00B5A5; font-weight: 700; }
  .cross { color: #334155; }
  td:first-child { color: #cbd5e1; font-weight: 500; }

  footer { color: #334155; font-size: 12px; text-align: center; }
  footer a { color: #4a7fa5; text-decoration: none; }
  footer a:hover { text-decoration: underline; }
  .savings-tag { font-size: 12px; color: #00B5A5; font-weight: 700; margin-left: 8px; }
</style>
</head>
<body>

<div class="logo">🛡</div>
<h1>Crypto Shield Pro</h1>
<p class="sub">Real-time Web3 wallet security for individuals and crypto-native teams.</p>

<div class="plans">

  <div class="plan">
    <div class="plan-name">Free</div>
    <div class="price">$0 <span>/ month</span></div>
    <div class="per">No credit card needed</div>
    <ul class="features">
      <li>1 monitored wallet</li>
      <li>Manual risk scans</li>
      <li>Basic threat intel</li>
      <li>EVM + Solana support</li>
      <li class="dim">Push alerts</li>
      <li class="dim">Address poisoning detection</li>
      <li class="dim">Portfolio valuation</li>
      <li class="dim">Security sweep</li>
    </ul>
    <a href="https://solanamobile.com/de" class="btn btn-outline">Download Free</a>
  </div>

  <div class="plan featured">
    <div class="badge">Most Popular</div>
    <div class="plan-name">Pro Annual <span class="savings-tag">Save 20%</span></div>
    <div class="price">$105.99 <span>/ year</span></div>
    <div class="per">That's $8.83 / month — save 20%</div>
    <ul class="features">
      <li>5 monitored wallets</li>
      <li>Real-time push alerts</li>
      <li>Address poisoning detection</li>
      <li>SOL + SPL portfolio valuation</li>
      <li>EVM · Solana · TON · Bitcoin</li>
      <li>NFT &amp; airdrop scam detection</li>
      <li>SIM-swap &amp; breach alerts</li>
      <li>Security sweep (email + OAuth)</li>
    </ul>
    <a href="${STRIPE_ANNUAL}" class="btn btn-primary">Get Pro Annual →</a>
  </div>

  <div class="plan">
    <div class="plan-name">Pro Monthly</div>
    <div class="price">$10.99 <span>/ month</span></div>
    <div class="per">Cancel any time</div>
    <ul class="features">
      <li>5 monitored wallets</li>
      <li>Real-time push alerts</li>
      <li>Address poisoning detection</li>
      <li>SOL + SPL portfolio valuation</li>
      <li>EVM · Solana · TON · Bitcoin</li>
      <li>NFT &amp; airdrop scam detection</li>
      <li>SIM-swap &amp; breach alerts</li>
      <li>Security sweep (email + OAuth)</li>
    </ul>
    <a href="${STRIPE_MONTHLY}" class="btn btn-outline">Get Pro Monthly →</a>
  </div>

</div>

<div class="comparison">
  <h2>Feature Comparison</h2>
  <table>
    <tr><th>Feature</th><th>Free</th><th>Pro</th></tr>
    <tr><td>Wallets monitored</td><td>1</td><td>5</td></tr>
    <tr><td>Chains supported</td><td>EVM, Solana</td><td>EVM, Solana, TON, Bitcoin</td></tr>
    <tr><td>Manual risk scans</td><td class="check">✓</td><td class="check">✓</td></tr>
    <tr><td>Real-time push alerts</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>Address poisoning detection</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>SOL + SPL portfolio valuation</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>SIM-swap monitoring</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>Email breach &amp; infostealer alerts</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>Security sweep</td><td class="cross">—</td><td class="check">✓</td></tr>
    <tr><td>NFT &amp; airdrop scam detection</td><td class="cross">—</td><td class="check">✓</td></tr>
  </table>
</div>

<footer>
  <p>Questions? <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
  <p style="margin-top:8px;">
    <a href="https://terms.relayshield.net">Terms</a> &nbsp;·&nbsp;
    <a href="https://privacy.relayshield.net">Privacy</a> &nbsp;·&nbsp;
    <a href="https://api.relayshield.net/developers">Developer API</a>
  </p>
  <p style="margin-top:12px; color:#1e3a5f;">© 2026 RelayShield</p>
</footer>

</body>
</html>`;
}
