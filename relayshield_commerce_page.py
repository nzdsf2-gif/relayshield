def lambda_handler(event, context):
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield Commerce Protection</title>
<style>
  :root { --bg: #0f172a; --panel: #1e293b; --text: #f1f5f9; --muted: #94a3b8; --accent: #3b82f6; --green: #22c55e; --amber: #f59e0b; --red: #ef4444; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, "Segoe UI", Roboto, sans-serif; line-height: 1.6; }
  .wrap { max-width: 800px; margin: 0 auto; padding: 48px 24px; }
  h1 { font-size: 32px; margin: 0 0 12px; }
  .lead { font-size: 18px; color: var(--muted); margin: 0 0 32px; }
  h2 { font-size: 22px; margin: 40px 0 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin: 24px 0; }
  .card { background: var(--panel); border-radius: 12px; padding: 24px; }
  .card h3 { margin: 0 0 8px; font-size: 18px; }
  .card p { margin: 0; font-size: 14px; color: var(--muted); }
  .verdicts { display: flex; gap: 12px; margin: 24px 0; flex-wrap: wrap; }
  .verdict { padding: 8px 16px; border-radius: 8px; font-weight: 600; font-size: 14px; }
  .blocked { background: rgba(239,68,68,.15); color: var(--red); border: 1px solid var(--red); }
  .flagged { background: rgba(245,158,11,.15); color: var(--amber); border: 1px solid var(--amber); }
  .allowed { background: rgba(34,197,94,.15); color: var(--green); border: 1px solid var(--green); }
  .cta { display: inline-block; background: var(--accent); color: #fff; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 24px; }
  .stats { display: flex; gap: 32px; margin: 32px 0; flex-wrap: wrap; }
  .stat { text-align: center; }
  .stat .num { font-size: 28px; font-weight: 700; }
  .stat .label { font-size: 13px; color: var(--muted); }
  footer { margin-top: 48px; padding-top: 24px; border-top: 1px solid #1e293b; font-size: 13px; color: var(--muted); }
  footer a { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <h1>RelayShield Commerce Protection</h1>
  <p class="lead">Buyer fraud screening for marketplace sellers. Know who's buying before you ship.</p>
  <div class="stats">
    <div class="stat"><div class="num">661K+</div><div class="label">Threat indicators</div></div>
    <div class="stat"><div class="num">124</div><div class="label">Monitored marketplaces</div></div>
    <div class="stat"><div class="num">8.6M+</div><div class="label">Corpus citations</div></div>
  </div>
  <h2>How it works</h2>
  <p>When a new order arrives, RelayShield scores the buyer against our threat-intelligence corpus: stolen payment methods, chargeback history, reshipping mule addresses, and compromised identities. You get a verdict before fulfillment.</p>
  <div class="verdicts">
    <span class="verdict blocked">BLOCKED &mdash; high risk, do not ship</span>
    <span class="verdict flagged">FLAGGED &mdash; review before shipping</span>
    <span class="verdict allowed">ALLOWED &mdash; no known risk</span>
  </div>
  <h2>Where it works</h2>
  <div class="grid">
    <div class="card">
      <h3>Shopify</h3>
      <p>Live on the Shopify App Store as RelayShield Order Screening. Installs in minutes, screens every order automatically.</p>
    </div>
    <div class="card">
      <h3>Walmart Marketplace</h3>
      <p>Solution Provider application in progress. OAuth 2.0 integration with the Orders API for buyer screening at scale.</p>
    </div>
    <div class="card">
      <h3>Agent Commerce</h3>
      <p>TAP signature verification plus counterparty screening for Visa Intelligent Commerce and x402 agent transactions.</p>
    </div>
    <div class="card">
      <h3>ChatGPT</h3>
      <p>Free scam checks inside ChatGPT via the RelayShield Scam Checks plugin. No signup, no API key.</p>
    </div>
  </div>
  <h2>Pricing</h2>
  <p>Flat monthly pricing. Free tier for low-volume sellers. No per-order fees, no revenue share.</p>
  <a class="cta" href="https://api.relayshield.net/developers">Get API access</a>
  <footer>
    <p>RelayShield &mdash; threat intelligence for commerce.<br>
    <a href="https://relayshield.net">relayshield.net</a> &middot;
    <a href="https://privacy.relayshield.net">Privacy</a> &middot;
    <a href="https://api.relayshield.net/developers">Developers</a></p>
  </footer>
</div>
</body>
</html>"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html
    }
