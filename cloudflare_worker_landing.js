/**
 * relayshield.net -- RelayShield main site (revamp).
 *
 * Served by the "relayshield-landing" worker (wrangler.landing.toml),
 * route relayshield.net/*. Professional revamp of the Carrd landing page:
 * "Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era".
 * Staged for review. Not yet deployed.
 */

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield: Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era</title>
<meta name="description" content="Identity security, threat monitoring and intelligence for the agentic AI era. TAP verifier for agentic commerce, MCP Proxy Firewall for AI agents, and threat intelligence APIs backed by 700K+ indicators across 125 monitored marketplaces.">
<meta property="og:title" content="RelayShield: Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era">
<meta property="og:description" content="TAP verifier, MCP Proxy Firewall, and threat intelligence APIs for the agentic AI era.">
<meta property="og:type" content="website">
<style>
  :root {
    --bg: #0a0f1c;
    --bg2: #0e1526;
    --card: #131c31;
    --border: #23304d;
    --blue: #2f81f7;
    --blue-d: #1f6feb;
    --text: #eef2f9;
    --muted: #9aa7c2;
    --green: #3fb950;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }
  a { color: var(--blue); }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 0 24px; }

  /* nav */
  nav { position: sticky; top: 0; z-index: 50; background: rgba(10,15,28,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
  .nav-inner { display: flex; align-items: center; justify-content: space-between; height: 64px; }
  .brand { font-weight: 800; font-size: 1.15rem; color: var(--text); text-decoration: none; display: flex; align-items: center; gap: 8px; }
  .brand .shield { font-size: 1.4rem; }
  .nav-links { display: flex; gap: 22px; align-items: center; }
  .nav-links a { color: var(--muted); text-decoration: none; font-size: .95rem; }
  .nav-links a:hover { color: var(--text); }
  .btn { display: inline-block; padding: 12px 26px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 1rem; }
  .btn-primary { background: var(--blue-d); color: #fff; }
  .btn-primary:hover { background: var(--blue); }
  .btn-ghost { border: 1px solid var(--border); color: var(--text); }
  .btn-ghost:hover { border-color: var(--blue); }
  .btn-sm { padding: 9px 18px; font-size: .9rem; }

  /* hero */
  .hero { padding: 96px 0 72px; text-align: center; background: radial-gradient(ellipse 80% 60% at 50% -10%, #16294d 0%, var(--bg) 70%); }
  .hero .kicker { display: inline-block; font-size: .8rem; letter-spacing: 2px; text-transform: uppercase; color: var(--blue); border: 1px solid var(--border); padding: 6px 16px; border-radius: 999px; margin-bottom: 24px; background: rgba(47,129,247,.08); }
  .hero h1 { font-size: 3rem; line-height: 1.15; font-weight: 800; max-width: 860px; margin: 0 auto 20px; }
  .hero p.sub { font-size: 1.2rem; color: var(--muted); max-width: 720px; margin: 0 auto 32px; }
  .hero-ctas { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }

  /* metrics */
  .metrics { border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: var(--bg2); }
  .metrics-inner { display: flex; justify-content: center; gap: 64px; padding: 36px 0; flex-wrap: wrap; }
  .metric { text-align: center; }
  .metric .num { font-size: 2rem; font-weight: 800; color: var(--blue); }
  .metric .lbl { font-size: .85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }

  /* sections */
  section.block { padding: 80px 0; }
  .sec-head { text-align: center; margin-bottom: 48px; }
  .sec-head h2 { font-size: 2rem; font-weight: 800; margin-bottom: 12px; }
  .sec-head p { color: var(--muted); max-width: 680px; margin: 0 auto; font-size: 1.05rem; }

  /* product cards */
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; }
  .card .icon { font-size: 2rem; margin-bottom: 16px; }
  .card h3 { font-size: 1.3rem; margin-bottom: 10px; }
  .card p { color: var(--muted); font-size: .98rem; margin-bottom: 16px; flex: 1; }
  .card .tag { display: inline-block; font-size: .75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--green); border: 1px solid var(--border); padding: 4px 10px; border-radius: 999px; margin-bottom: 14px; align-self: flex-start; }
  .card .links { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .card .links a.more { font-size: .92rem; }

  /* pricing */
  .pricing { background: var(--bg2); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .price-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; }
  .price-card.featured { border-color: var(--blue); box-shadow: 0 0 40px rgba(47,129,247,.15); }
  .price-card h3 { font-size: 1.25rem; margin-bottom: 6px; }
  .price-card .for { color: var(--muted); font-size: .9rem; margin-bottom: 16px; }
  .price-card .amount { font-size: 2.2rem; font-weight: 800; margin-bottom: 4px; }
  .price-card .per { color: var(--muted); font-size: .9rem; margin-bottom: 20px; }
  .price-card ul { list-style: none; margin-bottom: 24px; }
  .price-card li { padding: 6px 0; color: var(--muted); font-size: .95rem; }
  .price-card li::before { content: "\\2713  "; color: var(--green); font-weight: 700; }

  /* dev cta */
  .dev-cta { text-align: center; background: radial-gradient(ellipse 70% 80% at 50% 110%, #16294d 0%, var(--bg) 70%); }
  .dev-cta code { display: inline-block; background: #000; border: 1px solid var(--border); border-radius: 8px; padding: 12px 20px; font-size: .95rem; margin: 20px 0; color: var(--green); }

  /* contact */
  .contact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }
  .contact-item { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
  .contact-item h4 { margin-bottom: 8px; }
  .contact-item p, .contact-item a { color: var(--muted); font-size: .95rem; }

  footer { border-top: 1px solid var(--border); padding: 40px 0; color: var(--muted); font-size: .9rem; }
  .foot-inner { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; }
  .foot-links { display: flex; gap: 20px; flex-wrap: wrap; }
  .foot-links a { color: var(--muted); text-decoration: none; }
  .foot-links a:hover { color: var(--text); }

  @media (max-width: 640px) {
    .hero h1 { font-size: 2rem; }
    .hero { padding: 64px 0 48px; }
    .nav-links a:not(.btn) { display: none; }
    section.block { padding: 56px 0; }
    .metrics-inner { gap: 32px; }
  }
</style>
</head>
<body>

<nav>
  <div class="wrap nav-inner">
    <a class="brand" href="/"><span class="shield">&#x1F6E1;&#xFE0F;</span> RelayShield</a>
    <div class="nav-links">
      <a href="#products">Products</a>
      <a href="#pricing">Pricing</a>
      <a href="#developers">Developers</a>
      <a href="#contact">Contact</a>
      <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Get API access</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="wrap">
    <span class="kicker">Identity Security for the Agentic AI Era</span>
    <h1>Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era</h1>
    <p class="sub">AI agents transact, browse, and call tools on your behalf. RelayShield verifies who is acting, screens what they touch, and watches the threat landscape behind them. Built on a live corpus of 700K+ threat indicators across 125 monitored marketplaces.</p>
    <div class="hero-ctas">
      <a class="btn btn-primary" href="https://api.relayshield.net/developers">Get API access</a>
      <a class="btn btn-ghost" href="#products">Explore products</a>
    </div>
  </div>
</header>

<div class="metrics">
  <div class="wrap metrics-inner">
    <div class="metric"><div class="num">125</div><div class="lbl">Monitored marketplaces</div></div>
    <div class="metric"><div class="num">700K+</div><div class="lbl">Threat indicators</div></div>
    <div class="metric"><div class="num">8.7M</div><div class="lbl">Corpus citations</div></div>
  </div>
</div>

<section class="block" id="products">
  <div class="wrap">
    <div class="sec-head">
      <h2>Products</h2>
      <p>Security layers for agents, merchants, developers, and the people behind them.</p>
    </div>
    <div class="grid">
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F4E6;</div>
        <h3>TAP Verifier</h3>
        <p>Visa Trusted Agent Protocol verification for agentic commerce. One API call checks the agent RFC 9421 message signature, validates the signing key against Visa JWKS, and screens the agent identity against the RelayShield threat corpus, including intent mismatch detection.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://buy.stripe.com/bJe28semO0mxf9adoj0Ny0l">$49/mo flat</a>
          <a class="more" href="https://api.relayshield.net/developers">Pricing and API keys</a>
        </div>
      </div>
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6E1;&#xFE0F;</div>
        <h3>MCP Proxy Firewall</h3>
        <p>Runtime security between AI agents and MCP servers. Screens every tool call and response, quarantines suspicious servers, and scores each verdict with confidence and cause codes. Includes a free pre-deployment scanner that audits tool definitions before you connect.</p>
        <div class="links">
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">Enterprise: custom from $3,000/mo</a>
        </div>
      </div>
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F50D;</div>
        <h3>Threat Intelligence APIs</h3>
        <p>REST, MCP, and x402 pay-per-call access to the RelayShield corpus: breach exposure, infostealer logs, SIM swap signals, wallet and domain reputation, and MCP registry risk. Free checks available with no signup.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Browse the API</a>
          <a class="more" href="https://blog.relayshield.net">Blog</a>
        </div>
      </div>
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F4F1;</div>
        <h3>Personal Shield</h3>
        <p>Breach, SIM swap, and infostealer monitoring for individuals and families, delivered over WhatsApp and Telegram with step-by-step remediation guidance. Includes the free Telegram checker and WhatsApp scam-check bot.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a">$14.99/mo</a>
          <a class="more" href="https://t.me/relayshield_bot">Try free on Telegram</a>
        </div>
      </div>
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6D2;</div>
        <h3>Order Screening for Shopify</h3>
        <p>Threat-intel layer for Shopify merchants: screens buyer identity against the RelayShield corpus to flag high-risk orders. A complement to built-in fraud analysis, which scores the transaction while RelayShield scores the buyer.</p>
        <div class="links">
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">$29/mo on the App Store</a>
        </div>
      </div>
      <div class="card">
        <span class="tag">Live</span>
        <div class="icon">&#x1F310;</div>
        <h3>Browser and Mobile</h3>
        <p>RelayShield scam checks in the Chrome extension, and Crypto Shield for mobile wallet screening. The same intelligence, wherever you browse and transact.</p>
        <div class="links">
          <a class="more" href="https://cryptoshieldmobile.relayshield.net">Crypto Shield mobile</a>
          <a class="more" href="https://api.relayshield.net/developers">Chrome extension</a>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="block pricing" id="pricing">
  <div class="wrap">
    <div class="sec-head">
      <h2>Pricing</h2>
      <p>Flat monthly pricing. No minimums, no surprises. API keys and full plans at the developers page.</p>
    </div>
    <div class="grid">
      <div class="price-card featured">
        <h3>TAP Verifier</h3>
        <div class="for">Merchants accepting agentic payments</div>
        <div class="amount">$49</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Visa TAP signature verification</li>
          <li>Intent mismatch detection</li>
          <li>Threat corpus screening</li>
          <li>Pay-as-you-go at $0.10 per verification</li>
        </ul>
        <a class="btn btn-primary" href="https://buy.stripe.com/bJe28semO0mxf9adoj0Ny0l">Subscribe</a>
      </div>
      <div class="price-card">
        <h3>MCP Proxy Firewall</h3>
        <div class="for">Teams running agents on MCP</div>
        <div class="amount">Custom</div>
        <div class="per">from $3,000/mo, onsite available</div>
        <ul>
          <li>Runtime tool-call screening</li>
          <li>Confidence scores with cause codes</li>
          <li>Policy engine and audit trail</li>
          <li>Free pre-deployment scanner</li>
        </ul>
        <a class="btn btn-ghost" href="https://api.relayshield.net/developers">Contact us</a>
      </div>
      <div class="price-card">
        <h3>Personal Shield</h3>
        <div class="for">Individuals and families</div>
        <div class="amount">$14.99</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Breach and dark web monitoring</li>
          <li>SIM swap monitoring</li>
          <li>Infostealer log alerts</li>
          <li>WhatsApp and Telegram delivery</li>
        </ul>
        <a class="btn btn-primary" href="https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a">Subscribe</a>
      </div>
    </div>
  </div>
</section>

<section class="block dev-cta" id="developers">
  <div class="wrap">
    <div class="sec-head">
      <h2>Developers</h2>
      <p>REST, MCP, and x402. Free checks with no signup, pay-per-call when you scale. Get your API key in minutes.</p>
    </div>
    <code>curl https://api.relayshield.net/v1/check/url -d '{"url":"..."}'</code>
    <br>
    <a class="btn btn-primary" href="https://api.relayshield.net/developers">api.relayshield.net/developers</a>
  </div>
</section>

<section class="block" id="contact">
  <div class="wrap">
    <div class="sec-head">
      <h2>Contact</h2>
      <p>Partnerships, enterprise, press, or just questions.</p>
    </div>
    <div class="contact-grid">
      <div class="contact-item">
        <h4>Telegram channel</h4>
        <p><a href="https://t.me/RelayShield">@RelayShield</a> for announcements and threat posts.</p>
      </div>
      <div class="contact-item">
        <h4>WhatsApp checker</h4>
        <p><a href="https://wa.me/17407373961?text=SRC_wa-landing">Message +1 740 737 3961</a> to check a link or wallet free.</p>
      </div>
      <div class="contact-item">
        <h4>Contact form</h4>
        <p><a href="https://docs.google.com/forms/d/e/1FAIpQLScEirvBRF-sYtGw7QZF7vY0YkaOD12DZznv4OwIdNyNxOeMfw/viewform?usp=publish-editor">Send us a message</a> and we will reply.</p>
      </div>
      <div class="contact-item">
        <h4>Business plans</h4>
        <p>Team protection for 1 to 10 seats, with domain monitoring. <a href="https://buy.stripe.com/28EdRa2E61qB2mo3NJ0Ny0c">Business Starter</a> and <a href="https://buy.stripe.com/14A8wQa6y1qB8KM2JF0Ny00">team gifting</a> available.</p>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot-inner">
    <div>RelayShield LLC</div>
    <div class="foot-links">
      <a href="https://blog.relayshield.net">Blog</a>
      <a href="https://relayshield.hashnode.dev/archive">Archive</a>
      <a href="https://www.linkedin.com/company/112663616/admin/dashboard/">LinkedIn</a>
      <a href="https://www.facebook.com/profile.php?id=61590625257695">Facebook</a>
      <a href="https://www.promptfrenzy.com/directory">Directory</a>
      <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a>
      <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>
    </div>
  </div>
</footer>

</body>
</html>`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }
    return new Response(HTML, {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  },
};
