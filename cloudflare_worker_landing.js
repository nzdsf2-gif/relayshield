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
<link rel="icon" href="data:image/png;base64,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">
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
  .brand .logo { height: 34px; width: 34px; border-radius: 8px; filter: drop-shadow(0 0 10px rgba(0,255,65,0.75)) drop-shadow(0 0 26px rgba(168,85,247,0.45)); }
  .subsec { margin: 46px 0 24px; text-align: left; }
  .subsec:first-of-type { margin-top: 8px; }
  .subsec h3 { font-size: 1.55rem; font-weight: 800; }
  .subsec .tagline { color: var(--green); font-size: 1.05rem; margin-top: 6px; }
  .aws-links { display: flex; flex-direction: column; gap: 6px; margin: 14px 0; }
  .aws-links a { font-size: .92rem; }
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
  .plan-btn { display: block; text-align: center; margin-bottom: 8px; }

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
    <a class="brand" href="/"><img class="logo" src="data:image/png;base64,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" alt="RelayShield"> RelayShield</a>
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
        <div class="subsec">
      <h3><span class="accent">Agentic Commerce</span></h3>
      <p class="tagline">Verify every agent. Trust every transaction.</p>
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
    </div>

    <div class="subsec">
      <h3><span class="accent">Threat Monitoring</span></h3>
      <p class="tagline">Know when you are exposed. Act before it is too late.</p>
    </div>
    <div class="grid">
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
      <div class="card" data-drill="bizmon">
        <span class="tag">Live</span>
        <div class="icon">&#x1F3E2;</div>
        <h3>Business Monitoring</h3>
        <p>Team threat monitoring for sole proprietors, freelancers, and teams up to 10. Domain and brand monitoring, contractor and employee seats, delivered over Telegram and WhatsApp.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="#pricing" data-goto-tab="pricing">See one-click plans</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
    </div>

    <div class="subsec">
      <h3><span class="accent">Threat Intelligence APIs</span></h3>
      <p class="tagline">The corpus behind the verdicts. 700K+ indicators, 8.7M citations.</p>
    </div>
    <div class="grid">
      <div class="card" data-drill="ti">
        <span class="tag">Live</span>
        <div class="icon">&#x1F50D;</div>
        <h3>Threat Intelligence APIs</h3>
        <p>REST, MCP, and x402 pay-per-call access to the RelayShield corpus. Now with live licenses on AWS Marketplace.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Browse the API</a>
          <a class="more" href="https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq">AWS Marketplace</a>
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
        <h3>Business Starter</h3>
        <div class="for">Sole proprietors and freelancers</div>
        <div class="amount">One-click</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in Personal Shield</li>
          <li>Business monitoring coverage</li>
          <li>Telegram and WhatsApp delivery</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://buy.stripe.com/28EdRa2E61qB2mo3NJ0Ny0c">Subscribe</a>
      </div>
      <div class="price-card">
        <h3>More business plans</h3>
        <div class="for">Teams and additional tiers</div>
        <div class="amount">One-click</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in Personal Shield</li>
          <li>Domain and brand monitoring</li>
          <li>Contractor and employee seats</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/eVqbJ26Um1qBbWY3NJ0Ny06">Business plan</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/aFa8wQ3Iab1b8KM9830Ny03">Business plan</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/8x24gA6Um2uF2mo9830Ny04">Business plan</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/4gMdRa7Yq7OZf9aesn0Ny0g">Business plan</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/5kQfZi7Yq4CNe56esn0Ny0k">Business plan</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/aFa00k1A26KV7GIdoj0Ny0m">Business plan</a>
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
      { text: 'AWS: Consumption Security API Bundles', href: 'https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq', cls: '' },
      { text: 'AWS: Threat Intelligence and Identity Security API', href: 'https://aws.amazon.com/marketplace/pp/prodview-z3izf6val3jb2', cls: '' },
      { text: 'AWS: Attack Surface and Supply Chain API', href: 'https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog', cls: '' },
      { text: 'AWS: Core Identity Exposure API Bundle', href: 'https://aws.amazon.com/marketplace/pp/prodview-bn2q7auacucho', cls: '' }
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
  bizmon: {
    tag: 'Live', title: 'Business Monitoring',
    sub: 'Threat monitoring for teams',
    body: 'RelayShield business monitoring extends Personal Shield protection to sole proprietors, freelancers, and teams up to 10. Domain and brand monitoring, contractor and employee seats, delivered over Telegram and WhatsApp with step-by-step remediation guidance.',
    list: ['Everything in Personal Shield', 'Domain and brand monitoring', 'Contractor and employee seats', 'Team delivery over Telegram and WhatsApp', 'One-click Stripe purchase, no sales call'],
    links: [
      { text: 'See one-click plans', href: '#pricing', cls: 'btn btn-primary btn-sm' }
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
