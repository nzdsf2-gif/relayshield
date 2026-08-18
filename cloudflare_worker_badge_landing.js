const VERTICALS = {
  defi: {
    navLabel: "DeFi & Prediction Markets",
    pageTitle: "Security Badge — DeFi & Prediction Markets | RelayShield",
    metaDesc: "Free embeddable security badge for DeFi protocols and prediction markets. Live credential risk score, updated hourly.",
    headlineLine1: "Show users you're watching",
    headlineLine2: "the right signals.",
    subtitle: "Free embeddable security badge for DeFi protocols and prediction markets. Live credential risk score, updated every hour.",
    exampleDomain: "yourprotocol.xyz",
    signals: [
      { icon: "🔑", title: "Employee credentials", desc: "Stealer log corpus — leaked logins tied to your domain" },
      { icon: "🔗", title: "Vendor supply chain", desc: "Chainlink, Pyth, Alchemy, and oracle provider risk" },
      { icon: "🎯", title: "Threat actor IOCs", desc: "Attribution against active threat intelligence feeds" },
      { icon: "🔐", title: "Service account exposure", desc: "API keys and oracle signing tokens in criminal markets" },
    ],
    narrativeHeading: "Built for DeFi and prediction markets",
    narrativeBody: "The attack surface in DeFi is rarely the smart contract — it's the credential layer around it. Oracle signing keys, developer credentials, vendor service tokens. These don't show up in an audit report. They show up in criminal stealer log archives. RelayShield monitors the layer auditors don't look at.",
  },
  fintech: {
    navLabel: "Fintech & Payments",
    pageTitle: "Security Badge — Fintech & Payments | RelayShield",
    metaDesc: "Free embeddable security badge for fintech and payments platforms. Live credential risk score, updated hourly.",
    headlineLine1: "Prove your infrastructure is",
    headlineLine2: "watched, not just audited.",
    subtitle: "Free embeddable security badge for fintech and payments platforms. Live credential risk score, updated every hour.",
    exampleDomain: "yourcompany.com",
    signals: [
      { icon: "🔑", title: "Employee credentials", desc: "Stealer log corpus — leaked logins tied to your domain" },
      { icon: "🏦", title: "Vendor & rail supply chain", desc: "Payment processors, banking rails, and KYC vendor risk" },
      { icon: "🎯", title: "Threat actor IOCs", desc: "Attribution against active threat intelligence feeds" },
      { icon: "💳", title: "Session & token exposure", desc: "API keys and customer session cookies in criminal markets" },
    ],
    narrativeHeading: "Built for fintech and payments",
    narrativeBody: "Compliance audits check your controls once a year. Fraud doesn't wait for the audit cycle. RelayShield continuously monitors the credential and session layer — the same layer account takeover and payment fraud actually start from — so your security posture is something customers and partners can verify in real time, not just take on faith.",
  },
  saas: {
    navLabel: "SaaS & Dev Tools",
    pageTitle: "Security Badge — SaaS & Dev Tools | RelayShield",
    metaDesc: "Free embeddable security badge for SaaS and developer-tools platforms. Live credential risk score, updated hourly.",
    headlineLine1: "Security posture your",
    headlineLine2: "customers can actually see.",
    subtitle: "Free embeddable security badge for SaaS and developer-tools platforms. Live credential risk score, updated every hour.",
    exampleDomain: "yourapp.com",
    signals: [
      { icon: "🔑", title: "Employee credentials", desc: "Stealer log corpus — leaked logins tied to your domain" },
      { icon: "🧩", title: "Vendor supply chain", desc: "Third-party integrations and SaaS vendor risk" },
      { icon: "🕵️", title: "Domain lookalikes", desc: "Typosquat and phishing domains impersonating your brand" },
      { icon: "🔐", title: "Session & API key exposure", desc: "Customer tokens and API keys in criminal markets" },
    ],
    narrativeHeading: "Built for SaaS and dev-tools companies",
    narrativeBody: "Your security page says you take this seriously. This badge proves it, continuously. Enterprise buyers increasingly ask for live evidence, not a PDF from last year's pen test. RelayShield gives prospects and customers a real-time signal instead of a static claim.",
  },
  "ai-agents": {
    navLabel: "AI-Agent-Native",
    pageTitle: "Security Badge — AI-Agent-Native Companies | RelayShield",
    metaDesc: "Free embeddable security badge for AI-agent-native and tools-platform companies. Live risk score, updated hourly.",
    headlineLine1: "Show you're watching the",
    headlineLine2: "agentic attack surface.",
    subtitle: "Free embeddable security badge for AI-agent-native and tools-platform companies. Live risk score, updated every hour.",
    exampleDomain: "youragent.dev",
    signals: [
      { icon: "🧭", title: "MCP registry risk", desc: "Typosquatted and newly-registered tool servers" },
      { icon: "💉", title: "Prompt-injection breach", desc: "Session exposure correlated to prompt-injection attacks" },
      { icon: "🛠️", title: "Agent-framework CVEs", desc: "CVE targeting scoped to LangChain, AutoGPT, CrewAI, and similar" },
      { icon: "🤖", title: "Per-agent identity risk", desc: "Bulk risk scoring across your declared agent identities" },
    ],
    narrativeHeading: "Built for AI-agent-native companies",
    narrativeBody: "Agents that call tools, hold credentials, and act autonomously are a new attack surface with no established monitoring category yet. Typosquatted MCP servers and prompt-injection-driven credential theft are already documented, active techniques — not hypotheticals. RelayShield's Agentic Attack Surface coverage is built specifically for this layer.",
  },
};

const BASE_STYLE = `
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0a1628; color: #e2e8f0; line-height: 1.6; }

    .hero { max-width: 760px; margin: 0 auto; padding: 48px 24px 48px; text-align: center; }
    .logo { color: #00B5A5; font-size: 14px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 24px; }
    .logo a { color: #00B5A5; text-decoration: none; }
    h1 { font-size: 42px; font-weight: 800; color: #f1f5f9; line-height: 1.15; margin-bottom: 16px; }
    h1 span { color: #00B5A5; }
    .subtitle { font-size: 18px; color: #94a3b8; max-width: 560px; margin: 0 auto 40px; }

    .vertical-nav { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; max-width: 760px; margin: 24px auto 0; padding: 0 24px; }
    .vertical-pill { font-size: 12px; color: #64748b; border: 1px solid #1e3a5f; border-radius: 999px; padding: 6px 14px; text-decoration: none; }
    .vertical-pill.active { color: #00B5A5; border-color: #00B5A5; }
    .vertical-pill:hover { color: #e2e8f0; border-color: #64748b; }

    .badge-preview { margin: 0 auto 48px; display: inline-block; }
    .badge-preview svg { display: block; border-radius: 6px; box-shadow: 0 4px 24px rgba(0,181,165,0.15); }
    .badge-caption { font-size: 12px; color: #475569; margin-top: 8px; }

    .cta-row { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-bottom: 72px; }
    .btn-primary { background: #00B5A5; color: #0a1628; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 15px; text-decoration: none; }
    .btn-secondary { background: transparent; color: #00B5A5; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 15px; text-decoration: none; border: 1.5px solid #00B5A5; }

    .section { max-width: 760px; margin: 0 auto; padding: 0 24px 64px; }
    h2 { font-size: 24px; font-weight: 700; color: #f1f5f9; margin-bottom: 16px; }
    h3 { font-size: 16px; font-weight: 600; color: #00B5A5; margin-bottom: 8px; margin-top: 24px; }
    .narrative-body { color: #94a3b8; }

    .signals { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 48px; }
    .signal { background: #0F1F3D; border: 1px solid #1e3a5f; border-radius: 10px; padding: 20px; }
    .signal-icon { font-size: 22px; margin-bottom: 8px; }
    .signal-title { font-size: 14px; font-weight: 600; color: #e2e8f0; margin-bottom: 4px; }
    .signal-desc { font-size: 13px; color: #64748b; }

    .code-block { background: #0F1F3D; border: 1px solid #1e3a5f; border-radius: 10px; padding: 20px 24px; font-family: "SF Mono", "Fira Code", monospace; font-size: 14px; color: #00B5A5; overflow-x: auto; margin-bottom: 16px; white-space: pre; }
    .note { font-size: 13px; color: #64748b; margin-bottom: 32px; }

    .colors { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 32px; }
    .color-chip { display: flex; align-items: center; gap: 8px; background: #0F1F3D; border: 1px solid #1e3a5f; border-radius: 8px; padding: 10px 16px; font-size: 13px; }
    .dot { width: 12px; height: 12px; border-radius: 50%; }

    .divider { border: none; border-top: 1px solid #1e3a5f; margin: 48px 0; }

    .aws-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 16px; }
    .aws-card { background: #0F1F3D; border: 1px solid #1e3a5f; border-radius: 10px; padding: 24px; display: flex; flex-direction: column; }
    .aws-card-title { font-size: 16px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px; }
    .aws-card-desc { font-size: 13px; color: #94a3b8; margin-bottom: 20px; flex-grow: 1; }
    .aws-card .btn-secondary { text-align: center; }

    .picker-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; max-width: 760px; margin: 0 auto; padding: 0 24px 64px; }
    .picker-card { background: #0F1F3D; border: 1px solid #1e3a5f; border-radius: 10px; padding: 28px; text-decoration: none; display: block; transition: border-color 0.15s; }
    .picker-card:hover { border-color: #00B5A5; }
    .picker-card-title { font-size: 18px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px; }
    .picker-card-desc { font-size: 13px; color: #64748b; }

    footer { text-align: center; padding: 32px 24px; color: #475569; font-size: 13px; }
    footer a { color: #00B5A5; text-decoration: none; }
`;

// Static illustrative example — the real per-domain badge (api.relayshield.net/v1/badge)
// returns UNKNOWN for any unregistered domain, which looks bad as a marketing preview.
// This mirrors that SVG's exact layout/style but hardcodes a flattering LOW-risk example.
function exampleBadgeSvg() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="250" height="28">
    <rect rx="4" width="250" height="28" fill="#0a1628"/>
    <rect rx="4" x="150" width="100" height="28" fill="#22c55e"/>
    <rect rx="4" width="250" height="28" fill="url(#a)"/>
    <linearGradient id="a" x2="0" y2="100%"><stop offset="0" stop-color="#fff" stop-opacity=".15"/><stop offset="1" stop-opacity=".15"/></linearGradient>
    <g fill="#fff" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
      <text x="8" y="19" fill="#00B5A5" font-weight="bold">🛡 RelayShield</text>
      <text x="158" y="19" fill="#0a1628" font-weight="bold">LOW 8/100</text>
    </g>
  </svg>`;
}

function verticalNav(activeKey) {
  const links = Object.entries(VERTICALS)
    .map(([key, v]) => {
      const cls = key === activeKey ? "vertical-pill active" : "vertical-pill";
      return `<a href="/${key}" class="${cls}">${v.navLabel}</a>`;
    })
    .join("\n    ");
  return `<div class="vertical-nav">\n    ${links}\n  </div>`;
}

function renderVerticalPage(key) {
  const v = VERTICALS[key];
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${v.pageTitle}</title>
  <meta name="description" content="${v.metaDesc}">
  <meta property="og:title" content="${v.pageTitle}">
  <meta property="og:description" content="${v.metaDesc}">
  <style>${BASE_STYLE}</style>
</head>
<body>

<div class="hero">
  <div class="logo"><a href="https://relayshield.net">🛡 RelayShield</a></div>
  <h1>${v.headlineLine1}<br><span>${v.headlineLine2}</span></h1>
  <p class="subtitle">${v.subtitle}</p>

  <div class="badge-preview">
    ${exampleBadgeSvg()}
    <div class="badge-caption">Illustrative example — your live score replaces this once your domain is registered</div>
  </div>

  <div class="cta-row">
    <a href="https://api.relayshield.net/developers" class="btn-primary">Get API Key — Free</a>
    <a href="#embed" class="btn-secondary">See Embed Code</a>
  </div>
</div>

${verticalNav(key)}

<div class="section">
  <h2>What the badge monitors</h2>
  <div class="signals">
    ${v.signals
      .map(
        (s) => `<div class="signal">
      <div class="signal-icon">${s.icon}</div>
      <div class="signal-title">${s.title}</div>
      <div class="signal-desc">${s.desc}</div>
    </div>`
      )
      .join("\n    ")}
  </div>

  <h2>Risk levels</h2>
  <div class="colors">
    <div class="color-chip"><div class="dot" style="background:#22c55e"></div> GREEN — Monitored, no active threats</div>
    <div class="color-chip"><div class="dot" style="background:#eab308"></div> YELLOW — Low signals detected</div>
    <div class="color-chip"><div class="dot" style="background:#f97316"></div> ORANGE — Elevated risk</div>
    <div class="color-chip"><div class="dot" style="background:#ef4444"></div> RED — Active signals detected</div>
    <div class="color-chip"><div class="dot" style="background:#64748b"></div> GREY — Domain not yet monitored</div>
  </div>

  <hr class="divider">
  <h2>${v.narrativeHeading}</h2>
  <p class="narrative-body">${v.narrativeBody}</p>
</div>

<div class="section" id="embed">
  <hr class="divider">
  <h2>Embed in 60 seconds</h2>

  <h3>SVG badge (img tag)</h3>
  <div class="code-block">&lt;img src="https://api.relayshield.net/v1/badge?domain=${v.exampleDomain}"
     alt="Security Status" width="250" height="28"&gt;</div>

  <h3>Markdown (README / docs)</h3>
  <div class="code-block">[![Security Status](https://api.relayshield.net/v1/badge?domain=${v.exampleDomain})](https://badge.relayshield.net/${key})</div>

  <p class="note">Replace <code style="color:#00B5A5">${v.exampleDomain}</code> with your domain. Badge updates hourly. No API key required for the public badge endpoint.</p>

  <h3>Full monitoring + webhooks</h3>
  <p style="color:#94a3b8; margin-bottom:16px">Get real-time alerts when signals are detected — Telegram, WhatsApp, or webhook.</p>
  <a href="https://api.relayshield.net/developers" class="btn-primary">View API Docs</a>
</div>

<div class="section" id="aws-marketplace">
  <hr class="divider">
  <h2>Also on AWS Marketplace</h2>
  <p style="color:#94a3b8; margin-bottom:24px">Buy through your existing AWS bill — no separate vendor invoice.</p>
  <div class="aws-cards">
    <div class="aws-card">
      <div class="aws-card-title">Threat Intelligence &amp; Identity Security API</div>
      <div class="aws-card-desc">Flat-rate subscription. 23 metered endpoints included — breach detection, SIM swap monitoring, infostealer exposure, domain lookalikes, and more. $499/mo Starter (10,000 calls) or $999/mo Unlimited.</div>
      <a href="https://aws.amazon.com/marketplace/pp/prodview-z3izf6val3jb2" class="btn-secondary">View on AWS Marketplace</a>
    </div>
    <div class="aws-card">
      <div class="aws-card-title">Core Identity Exposure API Bundle</div>
      <div class="aws-card-desc">Six identity-exposure checks billed per call through AWS Marketplace: breach exposure, SIM swap detection, infostealer log checks, domain lookalikes, OAuth app watchlist, and crypto address intel. $150/mo minimum commitment plus usage from $0.10 per call.</div>
      <a href="https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog" class="btn-secondary">View on AWS Marketplace</a>
    </div>
    <div class="aws-card">
      <div class="aws-card-title">Consumption Security API Bundles</div>
      <div class="aws-card-desc">Metered access to focused capability sets, billed per-call through AWS Marketplace. Bundle D, Agentic Attack Surface, covers MCP registry risk, prompt-injection breach correlation, agent-framework CVE targeting, bulk per-agent identity risk scoring, and LLM credential exposure detection. $299/mo minimum commitment.</div>
      <a href="https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq" class="btn-secondary">View on AWS Marketplace</a>
    </div>
  </div>
</div>

<footer>
  © 2026 RelayShield &nbsp;·&nbsp;
  <a href="https://relayshield.net">Home</a> &nbsp;·&nbsp;
  <a href="https://api.relayshield.net/developers">API Docs</a> &nbsp;·&nbsp;
  <a href="https://privacy.relayshield.net">Privacy</a> &nbsp;·&nbsp;
  <a href="https://terms.relayshield.net">Terms</a>
</footer>

</body>
</html>`;
}

function renderPicker() {
  const cards = Object.entries(VERTICALS)
    .map(
      ([key, v]) => `<a href="/${key}" class="picker-card">
    <div class="picker-card-title">${v.navLabel}</div>
    <div class="picker-card-desc">${v.subtitle}</div>
  </a>`
    )
    .join("\n  ");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Security Badge — RelayShield</title>
  <meta name="description" content="Free embeddable security badge. Live credential risk score, updated hourly. Pick your industry.">
  <meta property="og:title" content="RelayShield Security Badge">
  <meta property="og:description" content="Show your users you're watching the right signals. One line of code, live risk score.">
  <style>${BASE_STYLE}</style>
</head>
<body>

<div class="hero">
  <div class="logo"><a href="https://relayshield.net">🛡 RelayShield</a></div>
  <h1>Show users you're watching<br><span>the right signals.</span></h1>
  <p class="subtitle">Free embeddable security badge. Live credential risk score, updated every hour. Pick the page that matches your industry.</p>

  <div class="badge-preview">
    ${exampleBadgeSvg()}
    <div class="badge-caption">Illustrative example — your live score replaces this once your domain is registered</div>
  </div>
</div>

<div class="picker-cards">
  ${cards}
</div>

<footer>
  © 2026 RelayShield &nbsp;·&nbsp;
  <a href="https://relayshield.net">Home</a> &nbsp;·&nbsp;
  <a href="https://api.relayshield.net/developers">API Docs</a> &nbsp;·&nbsp;
  <a href="https://privacy.relayshield.net">Privacy</a> &nbsp;·&nbsp;
  <a href="https://terms.relayshield.net">Terms</a>
</footer>

</body>
</html>`;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const key = path.slice(1);

    const html = VERTICALS[key] ? renderVerticalPage(key) : renderPicker();

    return new Response(html, {
      headers: {
        "Content-Type": "text/html;charset=UTF-8",
        "Cache-Control": "public, max-age=3600",
      },
    });
  },
};
