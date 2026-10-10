/**
 * relayshield.net -- RelayShield main site (revamp).
 *
 * Served by the "relayshield-landing" worker (wrangler.landing.toml),
 * route relayshield.net/*. Matrix-themed revamp of the Carrd landing page:
 * "Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era".
 * Interactive: tab navigation, product drill-down modals, Matrix code rain.
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
    --bg: #141414;
    --bg2: #1b1b1b;
    --card: #1f1f1f;
    --purple: #a855f7;
    --purple-d: #7c3aed;
    --purple-glow: rgba(168, 85, 247, 0.22);
    --green: #00ff41;
    --green-dim: #00c832;
    --text: #eaeaea;
    --muted: #a6a6a6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
  }
  #matrix {
    position: fixed; inset: 0; width: 100%; height: 100%;
    z-index: 0; opacity: 0.13; pointer-events: none;
  }
  .scanlines {
    position: fixed; inset: 0; z-index: 60; pointer-events: none; opacity: 0.35;
    background: repeating-linear-gradient(0deg, rgba(0,0,0,0.28) 0 1px, transparent 1px 3px);
  }
  .content { position: relative; z-index: 1; }
  a { color: var(--green); }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 0 24px; }

  /* nav */
  nav { position: sticky; top: 0; z-index: 50; background: rgba(20,20,20,0.94); backdrop-filter: blur(8px); border-bottom: 2px solid var(--purple-d); }
  .nav-inner { display: flex; align-items: center; justify-content: space-between; height: 64px; }
  .brand { font-weight: 800; font-size: 1.15rem; color: var(--text); text-decoration: none; display: flex; align-items: center; gap: 8px; }
  .brand .shield { font-size: 1.4rem; color: var(--green); text-shadow: 0 0 12px var(--green); }
  .nav-links { display: flex; gap: 22px; align-items: center; }
  .nav-links a { color: var(--muted); text-decoration: none; font-size: .95rem; }
  .nav-links a:hover { color: var(--green); }
  .btn { display: inline-block; padding: 12px 26px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 1rem; cursor: pointer; border: none; }
  .btn-primary { background: linear-gradient(135deg, var(--purple-d), var(--purple)); color: #fff; box-shadow: 0 0 18px var(--purple-glow); }
  .btn-primary:hover { box-shadow: 0 0 28px rgba(168,85,247,0.45); }
  .btn-ghost { border: 1px solid var(--purple-d); color: var(--text); background: transparent; }
  .btn-ghost:hover { border-color: var(--purple); box-shadow: 0 0 14px var(--purple-glow); }
  .btn-sm { padding: 9px 18px; font-size: .9rem; }

  /* hero */
  .hero { padding: 96px 0 72px; text-align: center; }
  .hero .kicker { display: inline-block; font-size: .8rem; letter-spacing: 2px; text-transform: uppercase; color: var(--green); border: 1px solid var(--green-dim); padding: 6px 16px; border-radius: 999px; margin-bottom: 24px; background: rgba(0,255,65,0.06); text-shadow: 0 0 10px rgba(0,255,65,0.6); }
  .hero h1 { font-size: 3rem; line-height: 1.15; font-weight: 800; max-width: 880px; margin: 0 auto 20px; }
  .hero h1 .accent { color: var(--purple); text-shadow: 0 0 24px var(--purple-glow); }
  .hero p.sub { font-size: 1.2rem; color: var(--muted); max-width: 740px; margin: 0 auto 32px; }
  .hero-ctas { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }

  /* metrics */
  .metrics { border-top: 1px solid var(--purple-d); border-bottom: 1px solid var(--purple-d); background: rgba(27,27,27,0.85); }
  .metrics-inner { display: flex; justify-content: center; gap: 64px; padding: 36px 0; flex-wrap: wrap; }
  .metric { text-align: center; }
  .metric .num { font-size: 2rem; font-weight: 800; color: var(--green); text-shadow: 0 0 14px rgba(0,255,65,0.5); }
  .metric .lbl { font-size: .85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }

  /* tab bar */
  .tabbar { position: sticky; top: 66px; z-index: 40; background: rgba(20,20,20,0.96); border-bottom: 1px solid #333; }
  .tabbar-inner { display: flex; gap: 8px; overflow-x: auto; padding: 12px 0; }
  .tab { background: transparent; border: 1px solid transparent; color: var(--muted); font-size: 1rem; font-weight: 700; padding: 10px 22px; border-radius: 8px; cursor: pointer; white-space: nowrap; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--purple); border-color: var(--purple-d); box-shadow: 0 0 14px var(--purple-glow); background: rgba(124,58,237,0.08); }

  /* sections */
  section.block { padding: 72px 0; }
  .sec-head { text-align: center; margin-bottom: 44px; }
  .sec-head h2 { font-size: 2rem; font-weight: 800; margin-bottom: 12px; }
  .sec-head h2 .accent { color: var(--purple); }
  .sec-head p { color: var(--muted); max-width: 680px; margin: 0 auto; font-size: 1.05rem; }
  .panel { display: none; }
  .panel.active { display: block; }

  /* product cards */
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
  .card { background: var(--card); border: 1px solid var(--purple-d); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; cursor: pointer; transition: transform .15s ease, box-shadow .15s ease; box-shadow: 0 0 16px rgba(124,58,237,0.12); }
  .card:hover { transform: translateY(-3px); box-shadow: 0 0 30px rgba(168,85,247,0.35); }
  .card .icon { font-size: 2rem; margin-bottom: 16px; }
  .card h3 { font-size: 1.3rem; margin-bottom: 10px; }
  .card p { color: var(--muted); font-size: .98rem; margin-bottom: 16px; flex: 1; }
  .card .tag { display: inline-block; font-size: .75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--green); border: 1px solid var(--green-dim); padding: 4px 10px; border-radius: 999px; margin-bottom: 14px; align-self: flex-start; }
  .card .links { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .card .links a.more { font-size: .92rem; }
  .card .drill-hint { margin-top: 14px; font-size: .8rem; color: var(--purple); }

  /* pricing */
  .price-card { background: var(--card); border: 1px solid var(--purple-d); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; box-shadow: 0 0 16px rgba(124,58,237,0.12); }
  .price-card.featured { border: 2px solid var(--purple); box-shadow: 0 0 34px rgba(168,85,247,0.3); }
  .price-card h3 { font-size: 1.25rem; margin-bottom: 6px; }
  .price-card .for { color: var(--muted); font-size: .9rem; margin-bottom: 16px; }
  .price-card .amount { font-size: 2.2rem; font-weight: 800; margin-bottom: 4px; color: var(--green); text-shadow: 0 0 14px rgba(0,255,65,0.4); }
  .price-card .per { color: var(--muted); font-size: .9rem; margin-bottom: 20px; }
  .price-card ul { list-style: none; margin-bottom: 20px; }
  .price-card li { padding: 6px 0; color: var(--muted); font-size: .95rem; }
  .price-card li::before { content: "\\2713  "; color: var(--green); font-weight: 700; }
  .price-card .tos { font-size: .8rem; color: var(--muted); margin-bottom: 12px; }

  /* dev cta */
  .dev-cta { text-align: center; }
  .dev-cta code { display: inline-block; background: #000; border: 1px solid var(--purple-d); border-radius: 8px; padding: 12px 20px; font-size: .95rem; margin: 20px 0; color: var(--green); box-shadow: 0 0 16px var(--purple-glow); }

  /* contact */
  .contact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }
  .contact-item { background: var(--card); border: 1px solid var(--purple-d); border-radius: 12px; padding: 24px; box-shadow: 0 0 14px rgba(124,58,237,0.1); }
  .contact-item h4 { margin-bottom: 8px; color: var(--purple); }
  .contact-item p, .contact-item a { color: var(--muted); font-size: .95rem; }

  footer { border-top: 2px solid var(--purple-d); padding: 40px 0; color: var(--muted); font-size: .9rem; }
  .foot-inner { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; }
  .foot-links { display: flex; gap: 20px; flex-wrap: wrap; }
  .foot-links a { color: var(--muted); text-decoration: none; }
  .foot-links a:hover { color: var(--green); }

  /* modal */
  .modal-overlay { position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.78); display: none; align-items: center; justify-content: center; padding: 20px; }
  .modal-overlay.open { display: flex; }
  .modal { background: #1a1a1a; border: 2px solid var(--purple); border-radius: 16px; max-width: 640px; width: 100%; max-height: 86vh; overflow-y: auto; padding: 36px; box-shadow: 0 0 60px rgba(168,85,247,0.4); position: relative; }
  .modal .m-tag { display: inline-block; font-size: .75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--green); border: 1px solid var(--green-dim); padding: 4px 10px; border-radius: 999px; margin-bottom: 14px; }
  .modal h2 { font-size: 1.6rem; margin-bottom: 12px; }
  .modal .m-sub { color: var(--purple); font-weight: 700; margin-bottom: 14px; }
  .modal p.body { color: var(--muted); margin-bottom: 18px; }
  .modal ul { list-style: none; margin-bottom: 22px; }
  .modal li { padding: 7px 0; color: var(--text); font-size: .97rem; border-bottom: 1px solid #2c2c2c; }
  .modal li::before { content: "\\25B8  "; color: var(--green); }
  .modal .m-links { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .modal-close { position: absolute; top: 14px; right: 18px; background: transparent; border: none; color: var(--muted); font-size: 1.6rem; cursor: pointer; }
  .modal-close:hover { color: var(--green); }

  @media (max-width: 640px) {
    .hero h1 { font-size: 2rem; }
    .hero { padding: 64px 0 48px; }
    .nav-links a:not(.btn) { display: none; }
    section.block { padding: 52px 0; }
    .metrics-inner { gap: 32px; }
    .modal { padding: 26px; }
  }
</style>
</head>
<body>
<canvas id="matrix"></canvas>
<div class="scanlines"></div>
<div class="content">

<nav>
  <div class="wrap nav-inner">
    <a class="brand" href="/"><span class="shield">&#x1F6E1;&#xFE0F;</span> RelayShield</a>
    <div class="nav-links">
      <a href="#products" data-goto-tab="products">Products</a>
      <a href="#pricing" data-goto-tab="pricing">Pricing</a>
      <a href="#developers" data-goto-tab="developers">Developers</a>
      <a href="#contact" data-goto-tab="contact">Contact</a>
      <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Get API access</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="wrap">
    <span class="kicker">Identity Security for the Agentic AI Era</span>
    <h1>Identity Security, Threat Monitoring and <span class="accent">Intelligence</span> for the Agentic AI Era</h1>
    <p class="sub">AI agents transact, browse, and call tools on your behalf. RelayShield verifies who is acting, screens what they touch, and watches the threat landscape behind them. Built on a live corpus of 700K+ threat indicators across 125 monitored marketplaces.</p>
    <div class="hero-ctas">
      <a class="btn btn-primary" href="https://api.relayshield.net/developers">Get API access</a>
      <a class="btn btn-ghost" href="#products" data-goto-tab="products">Explore products</a>
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

<div class="tabbar">
  <div class="wrap tabbar-inner">
    <button class="tab active" data-tab="products">Products</button>
    <button class="tab" data-tab="pricing">Pricing</button>
    <button class="tab" data-tab="developers">Developers</button>
    <button class="tab" data-tab="contact">Contact</button>
  </div>
</div>

<main>
<section class="block panel active" id="products" data-panel="products">
  <div class="wrap">
    <div class="sec-head">
      <h2>Pro<span class="accent">ducts</span></h2>
      <p>Security layers for agents, merchants, developers, and the people behind them. Click any product for details.</p>
    </div>
    <div class="grid">
      <div class="card" data-drill="tap">
        <span class="tag">Live</span>
        <div class="icon">&#x1F4E6;</div>
        <h3>TAP Verifier</h3>
        <p>Visa Trusted Agent Protocol verification for agentic commerce. One API call checks the agent signature, validates the signing key, and screens agent identity against the threat corpus.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://buy.stripe.com/bJe28semO0mxf9adoj0Ny0l">$49/mo flat</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="mcp">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6E1;&#xFE0F;</div>
        <h3>MCP Proxy Firewall</h3>
        <p>Runtime security between AI agents and MCP servers. Screens every tool call and response, quarantines suspicious servers, and scores each verdict with confidence and cause codes.</p>
        <div class="links">
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">Enterprise: custom from $3,000/mo</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="ti">
        <span class="tag">Live</span>
        <div class="icon">&#x1F50D;</div>
        <h3>Threat Intelligence APIs</h3>
        <p>REST, MCP, and x402 pay-per-call access to the RelayShield corpus. Now with live licenses on AWS Marketplace.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Browse the API</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="msg">
        <span class="tag">Free</span>
        <div class="icon">&#x1F4AC;</div>
        <h3>Telegram and WhatsApp Monitoring</h3>
        <p>Free threat-intel monitoring bots for Telegram and WhatsApp. The free discovery surface for RelayShield intelligence. No signup, no API key.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://t.me/relayshield_bot">Try free on Telegram</a>
          <a class="more" href="https://wa.me/17407373961?text=SRC_wa-landing">WhatsApp bot</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="solana">
        <span class="tag">Live</span>
        <div class="icon">&#x1F4F1;</div>
        <h3>Solana Crypto Shield Mobile</h3>
        <p>Wallet screening in your pocket. Crypto Shield Mobile checks Solana wallet addresses, links, and tokens before you sign, backed by the full RelayShield corpus.</p>
        <div class="links">
          <a class="more" href="https://cryptoshieldmobile.relayshield.net">Crypto Shield mobile</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="shield">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6E1;</div>
        <h3>Personal Shield</h3>
        <p>Breach, SIM swap, and infostealer monitoring for individuals and families, delivered over WhatsApp and Telegram with step-by-step remediation guidance.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a">$14.99/mo</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="shopify">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6D2;</div>
        <h3>Order Screening for Shopify</h3>
        <p>Threat-intel layer for Shopify merchants: screens buyer identity against the RelayShield corpus to flag high-risk orders.</p>
        <div class="links">
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">$29/mo on the App Store</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="chrome">
        <span class="tag">Live</span>
        <div class="icon">&#x1F310;</div>
        <h3>Chrome Extension</h3>
        <p>RelayShield scam checks in your browser. Screens links and pages as you browse, with tri-state verdicts: BLOCKED, FLAGGED, ALLOWED.</p>
        <div class="links">
          <a class="more" href="https://api.relayshield.net/developers">Get the extension</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
    </div>
  </div>
</section>

<section class="block panel" id="pricing" data-panel="pricing">
  <div class="wrap">
    <div class="sec-head">
      <h2>Pri<span class="accent">cing</span></h2>
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
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
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
        <p class="tos">By engaging you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
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
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a">Subscribe</a>
      </div>
      <div class="price-card">
        <h3>Business Plans</h3>
        <div class="for">Teams of 1 to 10 seats</div>
        <div class="amount">Custom</div>
        <div class="per">domain monitoring included</div>
        <ul>
          <li>Everything in Personal Shield</li>
          <li>Telegram and WhatsApp monitoring for teams</li>
          <li>Domain and brand monitoring</li>
          <li>Contractor and employee seats</li>
        </ul>
        <p class="tos">By engaging you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-ghost" href="https://api.relayshield.net/developers">Talk to us</a>
      </div>
    </div>
  </div>
</section>

<section class="block panel dev-cta" id="developers" data-panel="developers">
  <div class="wrap">
    <div class="sec-head">
      <h2>Develo<span class="accent">pers</span></h2>
      <p>REST, MCP, and x402. Free checks with no signup, pay-per-call when you scale. Get your API key in minutes.</p>
    </div>
    <code>curl https://api.relayshield.net/v1/check/url -d '{"url":"..."}'</code>
    <br>
    <a class="btn btn-primary" href="https://api.relayshield.net/developers">api.relayshield.net/developers</a>
  </div>
</section>

<section class="block panel" id="contact" data-panel="contact">
  <div class="wrap">
    <div class="sec-head">
      <h2>Con<span class="accent">tact</span></h2>
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
</main>

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

</div>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal" role="dialog" aria-modal="true">
    <button class="modal-close" id="modalClose" aria-label="Close">&times;</button>
    <span class="m-tag" id="mTag"></span>
    <h2 id="mTitle"></h2>
    <div class="m-sub" id="mSub"></div>
    <p class="body" id="mBody"></p>
    <ul id="mList"></ul>
    <div class="m-links" id="mLinks"></div>
  </div>
</div>

<script>
/* Matrix code rain */
(function () {
  var canvas = document.getElementById('matrix');
  var ctx = canvas.getContext('2d');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var chars = 'アイウエオカキクケコサシスセソタチツテト0123456789ABCDEF$#@%&';
  var fontSize = 18, columns = 0, drops = [];
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    columns = Math.floor(canvas.width / fontSize);
    drops = [];
    for (var i = 0; i < columns; i++) { drops[i] = Math.random() * -100; }
  }
  function draw() {
    ctx.fillStyle = 'rgba(20,20,20,0.08)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#00ff41';
    ctx.font = fontSize + 'px monospace';
    for (var i = 0; i < columns; i++) {
      var ch = chars.charAt(Math.floor(Math.random() * chars.length));
      ctx.fillText(ch, i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) { drops[i] = 0; }
      drops[i]++;
    }
  }
  window.addEventListener('resize', resize);
  resize();
  if (!reduce) { setInterval(draw, 66); }
})();

/* Tabs */
(function () {
  var tabs = document.querySelectorAll('.tab');
  var panels = document.querySelectorAll('.panel');
  function activate(name) {
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === name);
    }
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.toggle('active', panels[j].getAttribute('data-panel') === name);
    }
  }
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener('click', function () { activate(this.getAttribute('data-tab')); });
  }
  var gotoLinks = document.querySelectorAll('[data-goto-tab]');
  for (var k = 0; k < gotoLinks.length; k++) {
    gotoLinks[k].addEventListener('click', function (e) {
      e.preventDefault();
      activate(this.getAttribute('data-goto-tab'));
      var bar = document.querySelector('.tabbar');
      if (bar) { bar.scrollIntoView({ behavior: 'smooth' }); }
    });
  }
  window.__activateTab = activate;
})();

/* Product drill-down modal */
var PRODUCT_DETAILS = {
  tap: {
    tag: 'Live', title: 'TAP Verifier',
    sub: 'Cryptographic proof for agentic payments',
    body: 'RelayShield verifies Visa Trusted Agent Protocol messages so merchants know the agent at checkout is who it claims to be. Each verification checks the RFC 9421 message signature, validates the signing key against the Visa JWKS, and screens the agent identity against the RelayShield threat corpus.',
    list: ['RFC 9421 message signature verification', 'Signing key validation against Visa JWKS', 'Intent mismatch detection on payment details', 'Agent identity screening against the 700K+ indicator corpus', 'Signed verification receipts'],
    links: [
      { text: '$49/mo flat', href: 'https://buy.stripe.com/bJe28semO0mxf9adoj0Ny0l', cls: 'btn btn-primary btn-sm' },
      { text: 'API docs', href: 'https://api.relayshield.net/developers', cls: 'btn btn-ghost btn-sm' }
    ]
  },
  mcp: {
    tag: 'Live', title: 'MCP Proxy Firewall',
    sub: 'Runtime security for AI agents on MCP',
    body: 'A reverse proxy that sits between the AI agent and its MCP servers. Every tool call and every tool response passes through the proxy, where it is screened before reaching the agent. Suspicious calls are blocked or quarantined. Clean calls pass with negligible latency.',
    list: ['Free pre-deployment scanner: audits tool definitions before you connect, CI ready', 'Runtime screening of every tool call and tool response', 'Confidence scores with machine-readable cause codes on every verdict', 'Declarative allow and deny policy engine per agent, tool, and server', 'Server reputation graph that tracks repeat offenders over time', 'Complete audit trail for compliance and incident review', 'Behavioral baselining that flags novel attack patterns'],
    links: [
      { text: 'Enterprise: custom from $3,000/mo', href: 'https://api.relayshield.net/developers', cls: 'btn btn-ghost btn-sm' }
    ]
  },
  ti: {
    tag: 'Live', title: 'Threat Intelligence APIs',
    sub: 'The corpus behind everything we build',
    body: 'REST, MCP, and x402 pay-per-call access to the RelayShield corpus: 700K+ indicators and 8.7M citations across 125 monitored Telegram marketplaces and 20 authoritative feeds. Breach exposure, infostealer logs, SIM swap signals, wallet and domain reputation, and MCP registry risk. Now with live licenses on AWS Marketplace.',
    list: ['Live licenses on AWS Marketplace', 'REST, MCP, STIX/TAXII, and x402 rails', 'Breach, infostealer, SIM swap, wallet, domain, and MCP registry coverage', 'Free checks with no signup', 'Pay per call when you scale'],
    links: [
      { text: 'Browse the API', href: 'https://api.relayshield.net/developers', cls: 'btn btn-primary btn-sm' },
      { text: 'Blog', href: 'https://blog.relayshield.net', cls: '' }
    ]
  },
  msg: {
    tag: 'Free', title: 'Telegram and WhatsApp Monitoring',
    sub: 'Free discovery surfaces',
    body: 'Our free bots are the front door to RelayShield intelligence. Paste a link, wallet address, or email and get a verdict in seconds. No signup, no API key. The same checks developers call over the API, delivered where people already chat.',
    list: ['Free scam checks on Telegram: @relayshield_bot', 'Free scam checks on WhatsApp: message +1 740 737 3961', 'Screenshot to verdict on photo messages', 'Breach exposure lookups by email', 'No signup, no API key'],
    links: [
      { text: 'Try free on Telegram', href: 'https://t.me/relayshield_bot', cls: 'btn btn-primary btn-sm' },
      { text: 'WhatsApp bot', href: 'https://wa.me/17407373961?text=SRC_wa-landing', cls: '' }
    ]
  },
  solana: {
    tag: 'Live', title: 'Solana Crypto Shield Mobile',
    sub: 'Wallet screening in your pocket',
    body: 'Crypto Shield Mobile brings RelayShield scam checks to your phone, with Solana wallet screening built in. Check wallet addresses, links, and tokens before you sign a transaction. The same 700K+ indicator corpus, in your pocket.',
    list: ['Solana wallet address screening', 'Link and token checks before you sign', 'Phishing and drainer detection', 'Same 700K+ indicator corpus as the API', 'Phone friendly: works where mobile browsers do not support extensions'],
    links: [
      { text: 'Crypto Shield mobile', href: 'https://cryptoshieldmobile.relayshield.net', cls: 'btn btn-primary btn-sm' }
    ]
  },
  shield: {
    tag: 'Live', title: 'Personal Shield',
    sub: 'Continuous protection for you and your family',
    body: 'Breach, SIM swap, and infostealer monitoring for individuals and families, delivered over WhatsApp and Telegram with step-by-step remediation guidance when something is found.',
    list: ['Breach and dark web monitoring', 'SIM swap monitoring', 'Infostealer log alerts', 'AI remediation guidance', 'WhatsApp and Telegram delivery'],
    links: [
      { text: '$14.99/mo flat', href: 'https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a', cls: 'btn btn-primary btn-sm' }
    ]
  },
  shopify: {
    tag: 'Live', title: 'Order Screening for Shopify',
    sub: 'Threat intel for your checkout',
    body: 'A threat-intel layer for Shopify merchants: screens buyer identity against the RelayShield corpus to flag high-risk orders. Built-in fraud analysis scores the transaction. RelayShield scores the buyer.',
    list: ['Per-order buyer identity screening', 'High-risk order tagging for review before fulfillment', 'Timeline notes on screened orders', 'Free tier: 100 screenings per month'],
    links: [
      { text: '$29/mo on the App Store', href: 'https://api.relayshield.net/developers', cls: 'btn btn-ghost btn-sm' }
    ]
  },
  chrome: {
    tag: 'Live', title: 'Chrome Extension',
    sub: 'Scam checks in your browser',
    body: 'The RelayShield Chrome extension screens links and pages as you browse, with tri-state verdicts: BLOCKED, FLAGGED, ALLOWED. An ALLOWED verdict means no flags were found, with caveats shown.',
    list: ['Tri-state verdicts: BLOCKED, FLAGGED, ALLOWED', 'Screenshot to verdict', 'Same 700K+ indicator corpus', 'Privacy respecting: checks run against the API, browsing stays local'],
    links: [
      { text: 'Get the extension', href: 'https://api.relayshield.net/developers', cls: 'btn btn-primary btn-sm' }
    ]
  }
};

(function () {
  var overlay = document.getElementById('modalOverlay');
  var mTag = document.getElementById('mTag');
  var mTitle = document.getElementById('mTitle');
  var mSub = document.getElementById('mSub');
  var mBody = document.getElementById('mBody');
  var mList = document.getElementById('mList');
  var mLinks = document.getElementById('mLinks');
  function openModal(key) {
    var d = PRODUCT_DETAILS[key];
    if (!d) { return; }
    mTag.textContent = d.tag;
    mTitle.textContent = d.title;
    mSub.textContent = d.sub;
    mBody.textContent = d.body;
    mList.innerHTML = '';
    for (var i = 0; i < d.list.length; i++) {
      var li = document.createElement('li');
      li.textContent = d.list[i];
      mList.appendChild(li);
    }
    mLinks.innerHTML = '';
    for (var j = 0; j < d.links.length; j++) {
      var a = document.createElement('a');
      a.textContent = d.links[j].text;
      a.href = d.links[j].href;
      if (d.links[j].cls) { a.className = d.links[j].cls; }
      mLinks.appendChild(a);
    }
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
  document.getElementById('modalClose').addEventListener('click', closeModal);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) { closeModal(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeModal(); } });
  var cards = document.querySelectorAll('.card[data-drill]');
  for (var k = 0; k < cards.length; k++) {
    cards[k].addEventListener('click', function (e) {
      if (e.target.closest('a')) { return; }
      openModal(this.getAttribute('data-drill'));
    });
  }
})();
</script>
</body>
</html>
`;

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
