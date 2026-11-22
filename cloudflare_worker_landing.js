/**
 * relayshield.net -- RelayShield main site (revamp).
 *
 * Served by the "relayshield-landing" worker (wrangler.landing.toml),
 * route relayshield.net/*. Matrix-themed revamp of the Carrd landing page:
 * "Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era".
 * Interactive: tab navigation, product drill-down modals, Matrix code rain.
 * Staged for review. Not yet deployed.
 */

// ETSY-OAUTH-WIRING-2026-11-22: Etsy OAuth connect flow. The module is
// bundled by wrangler from ./etsy_oauth.js in the same directory. The
// handlers need env for the Etsy client ID/secret and AWS credentials.
import { handleEtsyStart, handleEtsyCallback } from "./etsy_oauth.js";

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield: Identity Security, Threat Monitoring and Intelligence for the Agentic AI Era</title>
<meta name="description" content="Identity security, threat monitoring and intelligence for the agentic AI era. TAP verifier for agentic commerce, MCP Proxy Firewall for AI agents, and threat intelligence APIs backed by 850K+ indicators across 144 monitored Telegram marketplaces.">
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
  .panel { display: none !important; }
  .panel.active { display: block !important; }

  /* product cards */
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
  .card { background: var(--card); border: 1px solid var(--purple-d); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; cursor: pointer; transition: transform .15s ease, box-shadow .15s ease; box-shadow: 0 0 16px rgba(124,58,237,0.12); }
  .card:hover { transform: translateY(-3px); box-shadow: 0 0 30px rgba(168,85,247,0.35); }
  .card .icon { font-size: 2rem; margin-bottom: 16px; filter: drop-shadow(0 0 8px rgba(168, 85, 247, 0.6)); }
  .card h3 { font-size: 1.3rem; margin-bottom: 10px; }
  .card p { color: var(--muted); font-size: .98rem; margin-bottom: 16px; flex: 1; }
  .card .tag { display: inline-block; font-size: .75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--green); border: 1px solid var(--green-dim); padding: 4px 10px; border-radius: 999px; margin-bottom: 14px; align-self: flex-start; }
  .card .links { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .card .links a.more { font-size: .92rem; }
  .card .aws-links { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  .card .aws-links a.more { font-size: .85rem; }
  .card .drill-hint { margin-top: 14px; font-size: .8rem; color: var(--purple); }
  /* comparison table (monitoring drilldown) */
  .compare { width: 100%; border-collapse: collapse; margin: 18px 0; font-size: .82rem; }
  .compare th, .compare td { padding: 7px 5px; border-bottom: 1px solid #2c2c2c; text-align: center; vertical-align: top; }
  .compare th:first-child, .compare td:first-child { text-align: left; }
  .compare th { color: var(--purple); font-size: .78rem; line-height: 1.3; }
  .compare th span, .compare td span { display: block; font-size: .7rem; color: var(--muted); font-weight: 400; }
  .compare tr.sec td { color: var(--green); text-transform: uppercase; letter-spacing: 1px; font-size: .72rem; font-weight: 700; padding-top: 14px; text-align: left; }

  /* pricing */
  .price-card { background: var(--card); border: 1px solid var(--purple-d); border-radius: 14px; padding: 32px; display: flex; flex-direction: column; box-shadow: 0 0 16px rgba(124,58,237,0.12); }
  .price-card.featured { border: 2px solid var(--purple); box-shadow: 0 0 34px rgba(168,85,247,0.3); }
  .price-card { cursor: pointer; transition: transform .15s ease, box-shadow .15s ease; }
  .price-card:hover { transform: translateY(-3px); }
  .price-card.selected { border-color: var(--purple); box-shadow: 0 0 30px rgba(168,85,247,0.35); }
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
  .modal ol { list-style: decimal; padding-left: 24px; margin-bottom: 18px; }
  .modal ol li::before { content: none; }
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
    <p class="sub">AI agents transact, browse, and call tools on your behalf. RelayShield verifies who is acting, screens what they touch, and watches the threat landscape behind them. Built on a live corpus of 850K+ threat indicators across 144 monitored Telegram marketplaces.</p>
    <div class="hero-ctas">
      <a class="btn btn-primary" href="https://api.relayshield.net/developers">Get API access</a>
      <a class="btn btn-ghost" href="#products" data-goto-tab="products">Explore products</a>
    </div>
  </div>
</header>

<div class="metrics">
  <div class="wrap metrics-inner">
    <div class="metric"><div class="num">144</div><div class="lbl">Monitored Telegram marketplaces</div></div>
    <div class="metric"><div class="num">850K+</div><div class="lbl">Threat indicators</div></div>
    <div class="metric"><div class="num">11M+</div><div class="lbl">Corpus citations</div></div>
  </div>
</div>

<div class="tabbar">
  <div class="wrap tabbar-inner">
    <button class="tab active" data-tab="products" onclick="switchTab('products')">Products</button>
    <button class="tab" data-tab="pricing" onclick="switchTab('pricing')">Pricing</button>
    <button class="tab" data-tab="developers" onclick="switchTab('developers')">Developers</button>
    <button class="tab" data-tab="contact" onclick="switchTab('contact')">Contact</button>
  </div>
</div>

<main>
<section class="block panel active" id="products" data-panel="products">
  <div class="wrap">
    <div class="sec-head">
      <h2>Products</h2>
      <p>Security layers for agents, merchants, developers, and the people behind them. Click any product for details.</p>
    </div>
        <div class="subsec">
      <h3><span class="accent">Agentic Commerce</span></h3>
      <p class="tagline">Verify every agent. Trust every transaction.</p>
      <p style="color: var(--muted); max-width: 680px; margin: 12px auto 0; font-size: 0.95rem;">Powered by x402 agent-to-agent payments. Listed on <a href="https://www.coinbase.com/x402">Coinbase Bazaar</a> for agent discovery.</p>
    </div>
    <div class="grid">
      <div class="card" data-drill="tap">
        <span class="tag">Live</span>
        <div class="icon">&#x1F4E6;</div>
        <h3>Agent Verifiers Bundle</h3>
        <p class="tagline">RelayShield Passport, intent binding, and TAP and PAP verification, checked together.</p>
        <p>Verify the agent, bind its intent, then check the action before settlement. The RelayShield Passport gives an agent a signed identity that can be checked and revoked. Intent binding records a signed binding for payer, counterparty, amount, currency, and artifact set, and a settle check allows or blocks that exact payment, once only. TAP verification covers card network transactions, and PAP verification covers merchant checkout. All checks screen against the RelayShield threat intelligence corpus.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="#pricing" data-goto-tab="pricing">$79/mo flat</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="mcp">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6E1;&#xFE0F;</div>
        <h3>MCP Proxy Firewall</h3>
        <p>Runtime security between AI agents and MCP servers. Screens every tool call and response, quarantines suspicious servers, and scores each verdict with confidence and cause codes.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://buy.stripe.com/28E6oI0vY4CN5yAac70Ny0n">$49/mo flat</a>
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">Enterprise: white-glove from $3K - Contact us</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
    </div>

    <p style="color: var(--muted); max-width: 680px; margin: 12px auto 0; font-size: 0.95rem;">RelayShield covers the four tiers of the <a href="https://api.relayshield.net/developers#agent-identity-tad">Trusted Agent Delegation framework</a> with primitives that are live today: proxy screening with no identity required, intent binding tied to a session, Passport identity across sessions, and step-up human approval for high-risk actions. <a href="https://api.relayshield.net/developers#agent-identity-tad">Read the full mapping</a>.</p>

    <div class="subsec">
      <h3><span class="accent">Threat Intelligence APIs</span></h3>
      <p class="tagline">OSINT-driven proactive defense. We monitor threat actor channels directly and acquire fresh intelligence, detecting attacks as they form, before the damage is done: account drain, data exfiltration, ransomware, LLMjacking. A proactive response layer for enterprises and MSPs.</p>
    </div>
    <div class="grid">
      <div class="card" data-drill="ti">
        <span class="tag">Live</span>
        <div class="icon">&#x1F50D;</div>
        <h3>Threat Intelligence APIs</h3>
        <p>REST, MCP, and x402 pay-per-call access to the RelayShield corpus. Now with live licenses on AWS Marketplace.</p>
        <div class="links">
          <a class="btn btn-primary btn-sm" href="https://api.relayshield.net/developers">Browse the API</a>
        </div>
        <div class="aws-links">
          <a class="more" href="https://aws.amazon.com/marketplace/pp/prodview-z3izf6val3jb2">AWS: Threat Intelligence and Identity Security API</a>
          <a class="more" href="https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq">AWS: Consumption Security API Bundles</a>
          <a class="more" href="https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog">AWS: Attack Surface and Supply Chain API</a>
          <a class="more" href="https://aws.amazon.com/marketplace/pp/prodview-bn2q7auacucho">AWS: Core Identity Exposure API Bundle</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
      <div class="card" data-drill="shopify">
        <span class="tag">Live</span>
        <div class="icon">&#x1F6D2;</div>
        <h3>Order Screening for Shopify</h3>
        <p>Reduce seller chargebacks by identifying buyer fraud. Threat-intel layer for Shopify merchants: screens buyer identity against the RelayShield corpus to flag high-risk orders before fulfillment.</p>
        <div class="links">
          <a class="btn btn-ghost btn-sm" href="https://api.relayshield.net/developers">$29/mo on the App Store</a>
        </div>
        <div class="drill-hint">Click for details &#x25B8;</div>
      </div>
    </div>
  </div>
</section>

    <div class="subsec">
      <h3><span class="accent">Threat Monitoring</span></h3>
      <p class="tagline">24x7 identity threat monitoring, detection, and proactive response for individuals and SMBs.</p>
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
          <a class="more" href="https://relayshield.net/check">Free scam check, no signup</a>
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



<section class="block panel" id="pricing" data-panel="pricing">
  <div class="wrap">
    <div class="sec-head">
      <h2>Pricing</h2>
      <p>Flat monthly pricing. No minimums, no surprises. API keys and full plans at the developers page.</p>
    </div>
    <div class="grid">
      <div class="price-card featured">
        <h3>TAP Verifier</h3>
        <div class="for">Standalone TAP only, for merchants accepting agentic payments</div>
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
        <h3>Agent Verifiers Bundle</h3>
        <div class="for">Merchants and businesses accepting agent payments</div>
        <div class="amount">$79</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in TAP Verifier</li>
          <li>Everything in PAP Verifier</li>
          <li>RelayShield Passport identity verification</li>
          <li>Intent binding and settle check</li>
          <li>100 free verifications per month</li>
          <li>Threat corpus screening</li>
        </ul>
        <a class="btn btn-primary" href="https://api.relayshield.net/developers">Get the bundle</a>
      </div>
      <div class="price-card">
        <h3>Hosted MCP Proxy Firewall</h3>
        <div class="for">Teams running agents on MCP</div>
        <div class="amount">$49</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Dedicated hosted proxy instance, single tenant by construction</li>
          <li>Your own URL and per-tenant token</li>
          <li>20,000 screened calls included, $0.002 per call above that</li>
          <li>Works with Coinbase Wallet MCP and MetaMask</li>
          <li>PII redaction built in: sensitive values are redacted from tool calls and tool results in both directions, opt-in per tenant</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://mcpfw.relayshield.net">Subscribe via the console</a>
      </div>
      <div class="price-card">
        <h3>Firewall + Verifiers Bundle</h3>
        <div class="for">A single developer or small team, one price</div>
        <div class="amount">$109</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in Hosted MCP Proxy Firewall</li>
          <li>Everything in Agent Verifiers Bundle</li>
          <li>20,000 screened calls included, $0.002 per call above that</li>
          <li>100 free verifications per month</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://mcpfw.relayshield.net">Subscribe via the console</a>
      </div>
      <div class="price-card">
        <h3>MCP Proxy Firewall On-Premise</h3>
        <div class="for">Enterprise teams with custom needs</div>
        <div class="amount">Custom</div>
        <div class="per">from $3,000/mo, onsite available</div>
        <ul>
          <li>Everything in Hosted</li>
          <li>White glove customization including dedicated support and policy configuration</li>
          <li>Dedicated support</li>
          <li>Custom policy configuration</li>
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
      <div class="price-card" id="business-starter-card">
        <h3>Business Starter</h3>
        <div class="for">Sole proprietors and freelancers</div>
        <div class="amount">$19.99</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in Personal Shield</li>
          <li>Quarterly sweep reminder</li>
          <li>Monthly security digest</li>
          <li>1 contractor/employee seat</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://buy.stripe.com/28EdRa2E61qB2mo3NJ0Ny0c">Subscribe</a>
      </div>
      <div class="price-card">
        <h3>Business Starter + Domain</h3>
        <div class="for">Sole proprietors with a business website</div>
        <div class="amount">$24.99</div>
        <div class="per">flat monthly pricing</div>
        <ul>
          <li>Everything in Business Starter</li>
          <li>Domain monitoring (1 domain)</li>
          <li>Brand impersonation alerts</li>
        </ul>
        <p class="tos">By subscribing you agree to our <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a> and <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>.</p>
        <a class="btn btn-primary" href="https://buy.stripe.com/eVqbJ26Um1qBbWY3NJ0Ny06">Subscribe</a>
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
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/aFa8wQ3Iab1b8KM9830Ny03">Business Basic $89.99/mo</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/8x24gA6Um2uF2mo9830Ny04">Business Shield $139.99/mo</a>
        <a class="btn btn-ghost btn-sm plan-btn" href="https://buy.stripe.com/4gMdRa7Yq7OZf9aesn0Ny0g">Business Shield Pro $299.99/mo</a>
        <p style="font-size: 0.85rem; color: var(--muted); margin-top: 12px;">Annual plans available on Stripe at checkout.</p>
      </div>
    </div>
  </div>
</section>

<section class="block panel dev-cta" id="developers" data-panel="developers">
  <div class="wrap">
    <div class="sec-head">
      <h2>Developers</h2>
      <p>REST, MCP, and x402. Free checks with no signup, pay-per-call when you scale. Get your API key in minutes.</p>
    </div>
    <code>curl https://api.relayshield.net/v1/check/url -d '{"url":"..."}'</code>
    <br>
    <a class="btn btn-primary" href="https://api.relayshield.net/developers">api.relayshield.net/developers</a>
    <div class="contact-grid" style="margin-top: 32px; text-align: left;">
      <div class="contact-item">
        <h4>Zapier Integration</h4>
        <p>Automate threat checks in your Zapier workflows. 7 ready-made templates for breach monitoring, link screening, and alerts.</p>
      </div>
      <div class="contact-item">
        <h4>N8n Integration</h4>
        <p>Self-hosted workflow automation with RelayShield nodes. Screen URLs, wallets, and emails in your n8n pipelines.</p>
      </div>
      <div class="contact-item">
        <h4>xSOAR Marketplace</h4>
        <p>Live in the Palo Alto Cortex XSOAR marketplace. Threat intelligence enrichment for your SOC playbooks.</p>
      </div>
    </div>
  </div>
</section>

<section class="block panel" id="contact" data-panel="contact">
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
        <h4>Email checker</h4>
        <p>Check any email address for breach exposure via the <a href="https://api.relayshield.net/developers">check_email API</a> or paste suspicious content into our WhatsApp bot.</p>
      </div>
      <div class="contact-item">
        <h4>Telegram miniApp</h4>
        <p>Run RelayShield checks inside Telegram with our miniApp. <a href="https://t.me/relayshield_bot">Open @relayshield_bot</a> and launch the miniApp.</p>
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
      <a href="https://relayshield.net/check">Free scam check</a>
      <a href="https://infosec.exchange/@relayshieldadmin">Mastodon</a>
      <a href="https://www.linkedin.com/company/112663616/admin/dashboard/">LinkedIn</a>
      <a href="https://www.facebook.com/profile.php?id=61590625257695">Facebook</a>
      <a href="https://www.promptfrenzy.com/directory" rel="noopener" target="_blank" title="Featured on PromptFrenzy AI Directory"><img src="https://www.promptfrenzy.com/badges/directory-mono-light.svg" alt="Featured on PromptFrenzy AI Directory" width="120" height="24" loading="lazy" /></a>
      <a href="https://docs.google.com/document/d/e/2PACX-1vTuxkRdCZNeRghwIqhY8XH9-OzYCMNokKiqmQwQODuHGFYfc3htt_-2_se5YkWtEXLwwLclxCq_8KWz/pub">Terms of Service</a>
      <a href="https://docs.google.com/document/d/e/2PACX-1vTu1KknanQip9yqLMXBzEPTU1uggFn2FVNFIcQzTT3D49rJMi0SzsKbFIlvVYfpJBbNOsxr7MIGx3m5/pub">Privacy Policy</a>
      <a href="mailto:support@relayshield.net">support@relayshield.net</a>
      <!-- FOOTER-CHANGELOG-LINK-2026-11-18 -->
      <a href="/changelog">Changelog</a>
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
    <div id="mTable" style="display:none; overflow-x:auto;"></div>
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
    (function(tab) {
      tab.addEventListener('click', function () {
        var name = tab.getAttribute('data-tab');
        // Update tabs
        for (var a = 0; a < tabs.length; a++) {
          tabs[a].classList.toggle('active', tabs[a] === tab);
        }
        // Update panels - hide all, show matching
        var allPanels = document.querySelectorAll('[data-panel]');
        for (var b = 0; b < allPanels.length; b++) {
          var p = allPanels[b];
          if (p.getAttribute('data-panel') === name) {
            p.classList.add('active');
            p.style.display = 'block';
          } else {
            p.classList.remove('active');
            p.style.display = 'none';
          }
        }
        // Scroll to top of content
        window.scrollTo({top: 0, behavior: 'smooth'});
      });
    })(tabs[i]);
  }
  var gotoLinks = document.querySelectorAll('[data-goto-tab]');
  for (var k = 0; k < gotoLinks.length; k++) {
    gotoLinks[k].addEventListener('click', function (e) {
      e.preventDefault();
      if (typeof window.closeModal === 'function') window.closeModal();
      activate(this.getAttribute('data-goto-tab'));
      setTimeout(function() {
        var el = document.getElementById('business-starter-card');
        if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        else { var bar = document.querySelector('.tabbar'); if (bar) { bar.scrollIntoView({ behavior: 'smooth' }); } }
      }, 150);
    });
  }
  window.__activateTab = activate;
})();

/* Product drill-down modal */
var PRODUCT_DETAILS = {
  tap: {
    tag: 'Live', title: 'Agent Verifiers Bundle',
    sub: 'RelayShield Passport, intent binding, and TAP and PAP verification, checked together',
    body: 'Three checks, in order, at the point where the action happens. 1. RelayShield Passport as identity: an agent presents a signed passport that can be issued, checked, and revoked. A revoked passport is blocked at the per-call check. 2. Intent Binding: before settlement, a signed binding records payer, counterparty, amount, currency, and artifact set, and a settle check allows only a match, once only. A repeat settle is blocked because the binding is consumed exactly once. Amount drift, recipient drift, scope expansion, a missing binding, and a revoked passport are blocked in Enforce and recorded for audit. 3. TAP and PAP transaction verifiers: TAP covers Visa Trusted Agent Protocol transactions, with RFC 9421 message signature verification, signing key validation against the Visa JWKS, intent mismatch detection, and threat corpus screening. PAP covers merchant checkout, with session token, DPoP proof, identity validation, and the same corpus screening.',
    body_html: 'Three ordered checks at the point where the action happens.<ol><li>RelayShield Passport as identity: an agent presents a signed passport that can be issued, checked, and revoked. A revoked passport is blocked at the per-call check.</li><li>Intent Binding: before settlement, a signed binding records payer, counterparty, amount, currency, and artifact set, and a settle check allows only a match, once only. A repeat settle is blocked because the binding is consumed exactly once. Amount drift, recipient drift, scope expansion, a missing binding, and a revoked passport are blocked in Enforce and recorded for audit.</li><li>TAP and PAP transaction verifiers: TAP covers Visa Trusted Agent Protocol transactions, with RFC 9421 message signature verification, signing key validation against the Visa JWKS, intent mismatch detection, and threat corpus screening. PAP covers merchant checkout, with session token, DPoP proof, identity validation, and the same corpus screening.</li></ol>',
    list: ['RFC 9421 message signature verification', 'Signing key validation against Visa JWKS', 'Intent mismatch detection on payment details', 'Agent identity screening against the 850K+ indicator corpus', 'RelayShield Passport identity, issued, checked, and revoked', 'Intent binding and settle check, exactly once', 'Signed verification receipts'],
    links: [
      { text: '$79/mo flat', href: 'https://api.relayshield.net/developers', cls: 'btn btn-primary btn-sm' },
      { text: 'API docs', href: 'https://api.relayshield.net/developers', cls: 'btn btn-ghost btn-sm' }
    ]
  },
  mcp: {
    tag: 'Live', title: 'MCP Proxy Firewall',
    sub: 'Runtime security for AI agents on MCP',
    body: 'A reverse proxy that sits between the AI agent and its MCP servers. Every tool call and every tool response passes through the proxy, where it is screened before reaching the agent. Suspicious calls are blocked or quarantined. Clean calls pass with negligible latency. Available as a $49/mo cloud service or a $3,000/mo on-premise deployment with white glove customization including dedicated support and policy configuration.',
    list: ['Free pre-deployment scanner: audits tool definitions before you connect, CI ready', 'Runtime screening of every tool call and tool response', 'Confidence scores with machine-readable cause codes on every verdict', 'Declarative allow and deny policy engine per agent, tool, and server', 'Server reputation graph that tracks repeat offenders over time', 'Complete audit trail for compliance and incident review', 'Behavioral baselining that flags novel attack patterns'],
    links: [
      { text: '$49/mo flat', href: 'https://buy.stripe.com/28E6oI0vY4CN5yAac70Ny0n', cls: 'btn btn-primary btn-sm' },
      { text: 'On-premise: white-glove from $3K - Contact us', href: 'https://api.relayshield.net/developers', cls: 'btn btn-ghost btn-sm' }
    ]
  },
  ti: {
    tag: 'Live', title: 'Threat Intelligence APIs',
    sub: 'The corpus behind everything we build',
    body: 'REST, MCP, and x402 pay-per-call access to the RelayShield corpus: 850K+ indicators and 11M+ citations across 144 monitored Telegram marketplaces and 20 authoritative feeds. Breach exposure, infostealer logs, SIM swap signals, wallet and domain reputation, and MCP registry risk. Now with live licenses on AWS Marketplace.',
    list: ['Live licenses on AWS Marketplace', 'REST, MCP, STIX/TAXII, and x402 rails', 'Breach, infostealer, SIM swap, wallet, domain, and MCP registry coverage', 'Free checks with no signup', 'Pay per call when you scale'],
    links: [
      { text: 'Browse the API', href: 'https://api.relayshield.net/developers', cls: 'btn btn-primary btn-sm' },
      { text: 'AWS: Threat Intelligence and Identity Security API (30 endpoints)', href: 'https://aws.amazon.com/marketplace/pp/prodview-z3izf6val3jb2', cls: '' },
      { text: 'AWS: Consumption Security API Bundles', href: 'https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq', cls: '' },
      { text: 'AWS: Attack Surface and Supply Chain API', href: 'https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog', cls: '' },
      { text: 'AWS: Core Identity Exposure API Bundle', href: 'https://aws.amazon.com/marketplace/pp/prodview-bn2q7auacucho', cls: '' }
    ]
  },
  msg: {
    tag: 'Free', title: 'Telegram and WhatsApp Monitoring',
    sub: 'Free discovery surfaces',
    body: 'Our free bots are the front door to RelayShield intelligence. Paste a link, wallet address, or email and get a verdict in seconds. No signup, no API key. The same checks developers call over the API, delivered where people already chat. Paid plans add continuous monitoring, AI remediation guidance, and team features. Compare below.',
    list: ['Free scam checks on Telegram: @relayshield_bot', 'Free scam checks on WhatsApp: message +1 740 737 3961', 'Screenshot to verdict on photo messages', 'Breach exposure lookups by email', 'No signup, no API key'],
    table: '<table class="compare"><thead><tr><th></th><th>Personal Shield<br><span>Individuals and families</span></th><th>Business Starter<br><span>Sole proprietors and freelancers</span></th><th>Starter + Domain<br><span>Sole proprietors with a business website</span></th><th>Business Basic<br><span>Teams up to 5</span></th><th>Business Shield<br><span>Teams up to 10</span></th></tr></thead><tbody><tr class="sec"><td colspan="6">Core protection</td></tr><tr><td>Breach monitoring</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>WhatsApp alerts</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>AI remediation guidance</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>SIM swap monitoring</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Session hijacking alerts</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Infostealer malware monitoring</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Vishing preparedness</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Instant file and link scanning</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Connected app audit (OAuth)</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;<span>+ team admin</span></td><td>&#x2713;<span>+ team admin</span></td></tr><tr class="sec"><td colspan="6">Business features</td></tr><tr><td>Quarterly sweep reminder</td><td>&#x2014;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Monthly security digest</td><td>&#x2014;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Contractor / employee seats</td><td>&#x2014;</td><td>1 seat</td><td>1 seat<span>solo only</span></td><td>5 seats</td><td>10 seats</td></tr><tr><td>Team seat management</td><td>&#x2014;</td><td>&#x2014;</td><td>&#x2014;</td><td>&#x2713;</td><td>&#x2713;</td></tr><tr><td>Domain monitoring</td><td>&#x2014;</td><td>&#x2014;</td><td>&#x2713;<span>1 domain</span></td><td>&#x2713;<span>2 domains</span></td><td>&#x2713;<span>2 domains</span></td></tr></tbody></table>',
    links: [
      { text: 'Try free on Telegram', href: 'https://t.me/relayshield_bot', cls: 'btn btn-primary btn-sm' },
      { text: 'WhatsApp bot', href: 'https://wa.me/17407373961?text=SRC_wa-landing', cls: '' }
    ]
  },
  solana: {
    tag: 'Live', title: 'Solana Crypto Shield Mobile',
    sub: 'Wallet screening in your pocket',
    body: 'Crypto Shield Mobile brings RelayShield scam checks to your phone, with Solana wallet screening built in. Check wallet addresses, links, and tokens before you sign a transaction. The same 850K+ indicator corpus, in your pocket.',
    list: ['Solana wallet address screening', 'Link and token checks before you sign', 'Phishing and drainer detection', 'Same 850K+ indicator corpus as the API', 'Phone friendly: works where mobile browsers do not support extensions'],
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
    list: ['Tri-state verdicts: BLOCKED, FLAGGED, ALLOWED', 'Screenshot to verdict', 'Same 850K+ indicator corpus', 'Privacy respecting: checks run against the API, browsing stays local'],
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
  var mTable = document.getElementById('mTable');
  var mLinks = document.getElementById('mLinks');
  function openModal(key) {
    var d = PRODUCT_DETAILS[key];
    if (!d) { return; }
    mTag.textContent = d.tag;
    mTitle.textContent = d.title;
    mSub.textContent = d.sub;
    if (d.body_html) { mBody.innerHTML = d.body_html; } else { mBody.textContent = d.body; }
    mList.innerHTML = '';
    for (var i = 0; i < d.list.length; i++) {
      var li = document.createElement('li');
      li.textContent = d.list[i];
      mList.appendChild(li);
    }
    if (d.table) { mTable.innerHTML = d.table; mTable.style.display = 'block'; }
    else { mTable.innerHTML = ''; mTable.style.display = 'none'; }
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
  window.closeModal = function closeModal() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
  document.getElementById('modalClose').addEventListener('click', closeModal);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) { closeModal(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeModal(); } });
  var priceCards = document.querySelectorAll('.price-card');
  for (var m = 0; m < priceCards.length; m++) {
    priceCards[m].addEventListener('click', function (e) {
      if (e.target.closest('a')) { return; }
      for (var n = 0; n < priceCards.length; n++) { priceCards[n].classList.remove('selected'); }
      this.classList.add('selected');
    });
  }

  var cards = document.querySelectorAll('.card[data-drill]');
  for (var k = 0; k < cards.length; k++) {
    cards[k].addEventListener('click', function (e) {
      if (e.target.closest('a')) { return; }
      openModal(this.getAttribute('data-drill'));
    });
  }
})();

</script>

<script>
function switchTab(name) {
  var tabs = document.querySelectorAll('[data-tab]');
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === name);
  }
  var panels = document.querySelectorAll('[data-panel]');
  for (var j = 0; j < panels.length; j++) {
    var p = panels[j];
    var isActive = p.getAttribute('data-panel') === name;
    p.classList.toggle('active', isActive);
    p.style.display = isActive ? 'block' : 'none';
  }
  window.scrollTo(0, 0);
}
</script>
</body>
</html>
`;

const POPPY_JSON = `{
  "protocol_version": "1.0",
  "organization": {
    "name": "RelayShield",
    "domain": "relayshield.net"
  },
  "apis": [
    {
      "type": "openapi",
      "url": "https://api.relayshield.net/openapi.json",
      "description": "Threat intelligence APIs: wallet screening, counterparty screening, breach lookup, scam-kit fingerprinting, identity risk, and more. 39 pay-as-you-go endpoints, priced per call in USDC via x402, or by API key. See https://api.relayshield.net/developers for the full endpoint list and pricing."
    },
    {
      "type": "mcp",
      "url": "https://relayshieldadmin-relayshield-free-mcp.hf.space/mcp",
      "description": "RelayShield Scam Checks: free MCP server for threat intelligence screening. Check MCP servers, wallets, domains, URLs, and phone numbers against the RelayShield corpus (144 monitored Telegram marketplaces, 850K+ indicators, 11M+ citations). No API key required for the free tier."
    }
  ]
}`;

// LOGO-ROUTE-2026-11-18: RelayShield logo served at /relayshield-logo.png
// (256x256 PNG; the homepage embeds the same logo as a data URI in the
// nav, but a real file URL is needed for the ChatGPT product feed
// image_url.)
const LOGO_PNG_BASE64 = 
  "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" +
  "PWefvb/97e8L+4TAxOLdqwWUSNAqz82v5AWCnO4LQIRW7KyRtrEV8d6BuXQvX7LbDKvmiVOzTzxFz03MsOadK2GonOYKO8rcn0h6" +
  "JwHlEmh2HzPsuLEH6vbHL9/AmKz0PX+QCA3N0pNj/MFjGA16p8E7FUNAgyiZWiH1G5C7udFCt2KoO0ocZaHW1Y6OZcueiehXuxnt" +
  "vjG47XVxG7v9DeAz6lBiUyKTUo4ApIlOSCnUWFbMOtIzaCbyyEm641Bb9zpeEjGopWYJ5orduOsbmJAviNMQsIg/3B2MnlTyQmFq" +
  "LaznDPkE2YZEh30QUrmkQHESchwU6XBxLTqOOa7qa2aUE6TZFrGWqGlJSAZE+2pz6a7BtXvM4VUZ2+aeF5pPH5GH19gas1ynqB8Z" +
  "1XlXVfcfu5Oy+ZFvA1M13phLQSG2wXuuW7t2mTaaPq9vT3IcDIbDD34ND67R0iKyXWy8iEppwiCPAOxGgtDRCttGDrKYwCC64U4E" +
  "M9p7U/CO7X7JmCfYBeIzCVgA5nRSkc9rO2pAqOp6iTFu1kkoFqlChIGhZzYMbHvruXYyp/vIRBPbHloaHVihTz3LxujjJzNhDcwZ" +
  "TnZgkaUaN40VQGk4Ok4yZyrwHagyrkIlXBGqYHcvflGK0koKC5MBAx4xdho+Z2gOLvHBEa/Wst7MHj3d3HdCHl/nTeFRTUNDHUPV" +
  "3rpCQLxwjSDmYlTmRgQwc7s24R+8bP2N57Zr07mrvxXsHC1//Dn+8JPcZ/Stt2jI2Vtd7zGiznsoqGQuUXXhBpgrMoBSi4DMaM+N" +
  "PivKZgilr8DdIiNiQl+2j5JU58m6CF334h1y6Mpl7DQXnnhU04Mnqit2TV+06r13/N7Tn2Zk3Nirdg1nkC8cw1LtjkJOVwp0K6jz" +
  "gVp94okjVRDEkyA1oqrqOmT8n8wLGFGsFGluJiv/vdKyOwulIgwqGjCGjBpEJGPbnNhsjmy2T2/QsQm3MIMaw8qH/O1xtTqElFRu" +
  "IVPEEyXwEAeXwAb2zMS8+tD4xy6ZbI7RJ9/tb3VkVp+a8K8+AMv90JMU+iL5NGP4xJBEA/LN9WRpYVpRPiAz2nMDomQNsarE0VGg" +
  "3kZTDAh1JM2ZtYP20SCVLwiBY+Fb7FmfoohloGX+2gm86tBsBLK22NQxd2pnU3vTvvpvNuihU1iqSI0HgJQqgcbpSTQmonoxsVnu" +
  "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";
const LOGO_PNG_BYTES = Uint8Array.from(atob(LOGO_PNG_BASE64), (c) => c.charCodeAt(0));

// PRODUCT-FEED-2026-11-18: OpenAI Business Hub product feed (CSV).
// PRODUCT-FEED-V2-2026-11-18: v2 feed, 9 required fields only.
// PRODUCT-FEED-V3-2026-11-19: v3 feed, target_countries=US on all rows.
// PRODUCT-FEED-V4-2026-11-19: v4 feed, store_country=US on all rows.
const PRODUCT_FEED_CSV = `item_id,title,description,url,brand,seller_name,image_url,availability,price,target_countries,store_country
rs-order-screening,RelayShield Order Screening,"Screen Shopify orders against live threat intel. Each order is checked against 850K+ indicators across 144 monitored Telegram marketplaces, with 11M+ citations. High-risk orders are tagged relayshield-high-risk, medium-risk flagged for review with a timeline note. RelayShield never blocks, cancels, or refunds an order, and never calls an order safe. Privacy-first: emails SHA-256 hashed, never stored raw, 90-day retention. Includes 100 free screenings.",https://apps.shopify.com/relayshield-order-screening,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,29.00 USD,US,US
rs-mcp-proxy-firewall-direct,RelayShield MCP Proxy Firewall (Direct),"Hosted MCP Proxy Firewall for a single developer or SMB. Screens every MCP tool call and tool result against live threat intel from 144 monitored Telegram marketplaces, 850K+ indicators, 11M+ citations. Intent binding (Policy 1 bound actions only, Policy 2 step-up for high-risk actions), opt-in PII redaction, and audit trail. Includes 20,000 screened calls per month, 0.002 USD per call overage. Dedicated hosted instance, no self-hosting.",https://relayshield.net,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,49.00 USD,US,US
rs-mcp-proxy-firewall-msp,"RelayShield MCP Proxy Firewall (MSP, per client org)","Hosted MCP Proxy Firewall for MSPs and distributors, priced per client org. Screens every MCP tool call and tool result against live threat intel from 144 monitored Telegram marketplaces, 850K+ indicators, 11M+ citations. Intent binding, opt-in PII redaction, per-tenant audit trail, and tenant-scoped console login. Includes 20,000 screened calls per client org per month, 0.002 USD per call overage. Dedicated hosted instance per client org.",https://relayshield.net,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,69.00 USD,US,US
rs-agent-verifiers-bundle,RelayShield Agent Verifiers Bundle,"Verification bundle for agentic commerce: TAP Verifier, PAP, Passport identity, Intent binding and settle check, plus threat corpus screening. Includes 100 free verifications per month. Verifier calls count toward the 20,000 screened-call pool. Built for agents that transact: verify the counterparty before the call, not after.",https://relayshield.net,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,79.00 USD,US,US
rs-tap-verifier,RelayShield TAP Verifier,"Standalone TAP (Trusted Agent Protocol) verifier. Verify TAP agent credentials before transacting, with threat corpus screening on the counterparty. For agents and businesses that need credential verification without the full verifiers bundle.",https://relayshield.net,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,49.00 USD,US,US
rs-personal-shield,RelayShield Personal Shield,"Threat intel monitoring for Telegram and WhatsApp. RelayShield watches 144 monitored Telegram marketplaces and flags stolen credentials, stealer logs, and scam-kit activity tied to you. Alerts via the Telegram and WhatsApp bots.",https://relayshield.net,RelayShield,RelayShield LLC,https://relayshield.net/relayshield-logo.png,in_stock,14.99 USD,US,US
`;

// CHANGELOG-ROUTE-2026-11-18
// CHANGELOG-V2-2026-11-18
const CHANGELOG_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Changelog - RelayShield</title>
<style>
  :root {
    --bg: #141414;
    --bg2: #1b1b1b;
    --card: #1f1f1f;
    --purple: #a855f7;
    --purple-d: #7c3aed;
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
  a { color: var(--green); }
  .wrap { max-width: 860px; margin: 0 auto; padding: 0 24px; }
  nav { position: sticky; top: 0; z-index: 50; background: rgba(20,20,20,0.94); border-bottom: 2px solid var(--purple-d); }
  nav .wrap { display: flex; align-items: center; justify-content: space-between; padding-top: 14px; padding-bottom: 14px; }
  .brand { font-weight: 800; font-size: 1.15rem; color: var(--text); text-decoration: none; }
  .nav-links a { color: var(--muted); text-decoration: none; font-size: .95rem; margin-left: 20px; }
  .nav-links a:hover { color: var(--green); }
  main { padding: 48px 0 80px; }
  h1 { font-size: 2.2rem; margin-bottom: 8px; }
  .intro { color: var(--muted); margin-bottom: 32px; max-width: 680px; }
  .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 28px; }
  .tab-btn { background: var(--card); color: var(--muted); border: 1px solid var(--purple-d); border-radius: 999px; padding: 8px 18px; font-size: .95rem; cursor: pointer; }
  .tab-btn.active { background: var(--purple-d); color: var(--text); border-color: var(--purple-d); }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .version { background: var(--card); border: 1px solid var(--purple-d); border-radius: 14px; padding: 28px 32px; margin-bottom: 24px; }
  .version h2 { font-size: 1.4rem; margin-bottom: 4px; }
  .version h2 .date { color: var(--muted); font-weight: 400; font-size: 1rem; margin-left: 8px; }
  .version h3 { font-size: 1rem; color: var(--green); margin: 18px 0 8px; text-transform: uppercase; letter-spacing: 1px; }
  .version ul { padding-left: 20px; }
  .version li { margin-bottom: 6px; color: var(--text); }
  .version li code { background: var(--bg2); padding: 1px 6px; border-radius: 4px; font-size: .9em; }
  .version p { color: var(--muted); margin-bottom: 8px; }
  .version p code { background: var(--bg2); padding: 1px 6px; border-radius: 4px; font-size: .9em; color: var(--text); }
  .tag { display: inline-block; font-size: .75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--green); border: 1px solid var(--green-dim); padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; }
  .tag.unreleased { color: var(--purple); border-color: var(--purple-d); }
  footer { border-top: 1px solid #333; padding: 24px 0; color: var(--muted); font-size: .9rem; }
</style>
</head>
<body>
<nav><div class="wrap">
<a class="brand" href="/">RelayShield</a>
<div class="nav-links"><a href="/">Home</a><a href="https://blog.relayshield.net">Blog</a><a href="https://api.relayshield.net/developers">Developers</a></div>
</div></nav>
<main><div class="wrap">
<h1>Changelog</h1>
<p class="intro">All notable changes to RelayShield products. The format is based on Keep a Changelog, and this project adheres to Semantic Versioning. Every shipped change is added here automatically. Pick a product tab to see only its entries.</p>

<div class="tabs">
<button class="tab-btn active" data-tab="mcp">MCP Proxy Firewall</button>
<button class="tab-btn" data-tab="shopify">Shopify Apps</button>
<button class="tab-btn" data-tab="shared">Shared / Infrastructure</button>
</div>

<div class="tab-panel active" id="panel-mcp">

<section class="version">
<span class="tag unreleased">Unreleased</span>
<h2>[Unreleased]</h2>
<h3>Added</h3>
<ul>
<li>Intent binding proxy enforcement (Policy 1 Bound actions only, Policy 2 step-up for high-risk actions). Patch v2 applied 2026-11-17; gate verified on all 3 fleet instances 2026-11-17; console Policies tab now shows the Intent Binding panel.</li>
</ul>
<h3>Changed</h3>
<ul><li>None yet.</li></ul>
</section>

<section class="version">
<h2>[0.3.0] <span class="date">2026-11-13</span></h2>
<h3>Added</h3>
<ul>
<li>Hosted MCP Proxy Firewall: dedicated EC2 (t3.micro) per paying tenant, provisioned by Stripe webhook, with per-tenant DNS (<code>&lt;tenant-id&gt;.proxy.relayshield.net</code>), Caddy TLS, and SES welcome email.</li>
<li>Tenant-scoped console login: one-time setup link in the welcome email, Stripe customer email as username, billing read-only, tenant proxy-token rotation.</li>
<li>PII redaction (opt-in per tenant, off by default): redacts email, phone, SSN, credit card, API key or secret, and crypto wallet from tool calls and tool results, in both directions, before they reach the agent or the audit log. Included in existing licenses at no extra charge.</li>
</ul>
<h3>Fixed</h3>
<ul><li>None in this release; first public release of the hosted proxy.</li></ul>
</section>

<section class="version">
<h2>[0.2.0] <span class="date">2026-10-25</span></h2>
<h3>Added</h3>
<ul>
<li>Intent binding service: x402 and TAP proven end to end. Table <code>relayshield_intent_bindings</code> (ACTIVE, TTL on <code>expires_at</code>).</li>
<li>Proxy-side intent enforcement scoped, not yet deployed to the fleet.</li>
</ul>
</section>

<section class="version">
<h2>[0.1.0] <span class="date">2026-09-29</span></h2>
<h3>Added</h3>
<ul>
<li>RelayShield Scam Checks free MCP server published to the Official MCP Registry (<code>io.github.nzdsf2-gif/relayshield-free-mcp</code> v1.30.0).</li>
<li>Bidirectional screening of MCP tool lists, tool calls, and tool results against the RelayShield threat-intelligence corpus.</li>
<li>Flag, quarantine, and block at the tool call as policy dictates.</li>
<li>Discovery responses are flag-only; no bidirectional blocking for discovery.</li>
</ul>
</section>

<section class="version">
<h2>Release notes</h2>
<h3>2026-11-13: Hosted MCP Proxy Firewall launches</h3>
<p>The hosted Firewall is live. $49/mo direct, $69/mo per client org for MSP, $109/mo combined Firewall plus Agent Verifiers Bundle. 20,000 screened calls per client org per month, $0.002 per call overage. Blog post: <a href="https://blog.relayshield.net/2026-11-13-hosted-mcp-proxy-firewall">blog.relayshield.net/2026-11-13-hosted-mcp-proxy-firewall</a></p>
<h3>2026-11-15: PII redaction ships</h3>
<p>Redaction is implemented and committed (commit ab98547a, all 28 tests pass), deployed to all 3 fleet instances 2026-11-16. Opt-in per tenant, off by default, included at no extra charge.</p>
<h3>2026-11-16: Fleet redaction deploy incident</h3>
<p>See the status log for the full incident record. Root cause: the fleet AMI predated the <code>kill_chain_store</code> module, so a single-file proxy.py copy caused a ModuleNotFoundError restart loop. Fix: copy the whole <code>mcp_proxy</code> directory. All 3 instances verified active with health OK after the fix. A second incident the same evening (services stopped at midnight UTC by the <code>relayshield-license-check.timer</code>) is also logged in the status log.</p>
</section>

</div>

<div class="tab-panel" id="panel-shopify">

<section class="version">
<span class="tag unreleased">Unreleased</span>
<h2>[Unreleased]</h2>
<h3>Added</h3>
<ul>
<li>Buyer screening API: <code>POST /v1/buyer-screen</code> (keyless) for the Shopify Buyer Fraud app. Screens buyer email, IP, addresses, and account signals against the TI corpus; flag-only verdict (high/medium/unknown) with a score and per-signal evidence. No paid upstream calls in v1. Endpoint live and verified 2026-11-17.</li>
<li>Shopify Buyer Fraud app: buyer screening at checkout and account creation, $29/month with 100 free screenings. Build complete 2026-11-17; app awaits Partner Dashboard setup and install on the dev store.</li>
</ul>
<h3>Changed</h3>
<ul><li>None yet.</li></ul>
</section>

<section class="version">
<h2>[1.0.0] <span class="date">2026-11-17</span></h2>
<h3>Added</h3>
<ul>
<li>RelayShield Order Screening approved and published on the Shopify App Store (<a href="https://apps.shopify.com/relayshield-order-screening">apps.shopify.com/relayshield-order-screening</a>). $29/month, 100 free screenings to try.</li>
<li>Every order is checked against live threat intel (850K+ indicators across 144 monitored Telegram marketplaces, 11M+ citations). High-risk orders are tagged <code>relayshield-high-risk</code>, medium-risk flagged for review with a timeline note. The app never blocks, cancels, or refunds an order, and never calls an order safe.</li>
<li>Privacy-first: emails SHA-256 hashed, never stored raw, 90-day retention.</li>
</ul>
</section>

</div>

<div class="tab-panel" id="panel-shared">

<section class="version">
<h2>Shared / Infrastructure</h2>
<p>Changes that span products: the threat-intelligence corpus, the x402 pay-as-you-go APIs, and the shared screening services both products run on.</p>
<h3>Added</h3>
<ul>
<li>Threat-intelligence corpus: 144 monitored Telegram marketplaces, 850K+ indicators, 11M+ citations (live figures, updated 2026-11-17). Both the MCP Proxy Firewall and the Shopify apps screen against this corpus.</li>
<li>x402 pay-as-you-go screening APIs at <code>api.relayshield.net</code>: 39 paid routes, settled through Coinbase CDP and PayAI (counterparty-screen $0.10, pin-check $0.02, and 37 more). Listed on x402List with Payment-ready status.</li>
<li>Poppy discovery file published at <code>relayshield.net/.well-known/poppy.json</code> (2026-11-17): protocol_version 1.0, OpenAPI and MCP endpoints, discovery-only (no auth block yet).</li>
</ul>
<h3>Changed</h3>
<ul><li>None yet.</li></ul>
</section>

</div>

</div></main>
<footer><div class="wrap">RelayShield LLC &middot; <a href="/">relayshield.net</a> &middot; <a href="mailto:support@relayshield.net">support@relayshield.net</a></div></footer>
<script>
(function () {
  var btns = document.querySelectorAll('.tab-btn');
  function show(tab) {
    var i;
    for (i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].getAttribute('data-tab') === tab);
    }
    var panels = document.querySelectorAll('.tab-panel');
    for (i = 0; i < panels.length; i++) {
      panels[i].classList.toggle('active', panels[i].id === 'panel-' + tab);
    }
  }
  for (var j = 0; j < btns.length; j++) {
    btns[j].addEventListener('click', function () { show(this.getAttribute('data-tab')); });
  }
})();
</script>
</body>
</html>
`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
        if (url.pathname === "/.well-known/poppy.json") {
      // Poppy (Personal Agent Protocol 1.0) discovery file, v1.
      // Discovery-only: OpenAPI + MCP endpoints, no auth block (API-key
      // auth, not OAuth). Must return JSON, not the HTML landing page.
      return new Response(POPPY_JSON, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
if (url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }
    if (url.pathname === "/forward") {
      // Redirect to a mailto: draft with the same subject and body.
      // The query string passes through RAW: decoding and re-encoding
      // it (for example via URLSearchParams) would rewrite spaces as +
      // and alter the percent-encoding, corrupting the mail body.
      // Telegram's forward link points here because a mailto: text_link
      // is not tappable on iOS Telegram (confirmed 2026-10-27).
      return new Response(null, {
        status: 302,
        headers: { Location: "mailto:?" + url.search.slice(1) },
      });
    }
    // MYSLOP-TXT-2026-11-19: MySlop ownership verification file.
    if (url.pathname === "/myslop.txt") {
      return new Response("myslop-verify-6cdd6668f8641f731e258f21f26201a3\n", {
        headers: { "Content-Type": "text/plain" },
      });
    }
    if (url.pathname === "/relayshield-logo.png") {
      // LOGO-ROUTE-2026-11-18
      return new Response(LOGO_PNG_BYTES, {
        status: 200,
        headers: {
          "Content-Type": "image/png",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }
    if (url.pathname === "/product-feed.csv") {
      // PRODUCT-FEED-2026-11-18: serve the OpenAI Business Hub product feed.
      return new Response(PRODUCT_FEED_CSV, {
        status: 200,
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          "Cache-Control": "public, max-age=3600",
        },
      });
    }
    // CHANGELOG-ROUTE-2026-11-18
    if (url.pathname === "/changelog") {
      return new Response(CHANGELOG_HTML, {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
      });
    }
    // ETSY-OAUTH-WIRING-2026-11-22: Etsy OAuth connect flow. The callback
    // URL registered in the Etsy app must be exactly
    // https://relayshield.net/etsy/oauth/callback. The handlers read the
    // Etsy client ID/secret and AWS credentials from env; they throw a
    // clear error naming any missing variable. The DynamoDB table
    // relayshield_etsy_tokens must be provisioned before this works end
    // to end.
    if (url.pathname === "/etsy/oauth/start") {
      return handleEtsyStart(request, env);
    }
    if (url.pathname === "/etsy/oauth/callback") {
      return handleEtsyCallback(request, env);
    }
    return new Response(HTML, {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  },
};

// VERIFIERS-CONSOLIDATION-2026-11-18
