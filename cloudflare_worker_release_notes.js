/**
 * RelayShield Customer Release Notes Portal
 *
 * Password-gated via token query param: ?token=<TOKEN>
 * Deploy to Cloudflare Workers, bind to: relayshield.net/updates
 *
 * Setup:
 *   1. Add Cloudflare Worker secret: RELEASE_TOKEN = "rs-<random-string>"
 *   2. Send customers the URL: https://relayshield.net/updates?token=rs-<random-string>
 *   3. Rotate token quarterly — update secret, send new link via SES
 *
 * To add a new release: update the RELEASE_NOTES constant below and redeploy.
 */

const RELEASE_NOTES = `
<article>
  <div class="release-header">
    <span class="badge">July 2026</span>
    <h2>Product Updates &mdash; What&rsquo;s New at RelayShield</h2>
  </div>

  <div class="product-block">
    <div class="product-label api">🔬 Threat Intelligence API &mdash; For Security Teams &amp; Developers</div>

    <section>
      <h3>🆕 STIX/TAXII 2.1 and MISP Feed Export</h3>
      <p>Two new ways to pull the full IOC corpus directly into your existing security tooling &mdash; no custom integration work required.</p>
      <p><code>GET /v1/intel/taxii/*</code> &mdash; A standards-compliant TAXII 2.1 server. Point Splunk, Sentinel, Elastic, or QRadar's built-in TAXII client at this endpoint and IOCs arrive as STIX 2.1 Indicator objects.</p>
      <p><code>GET /v1/intel/misp/event</code> &mdash; The same IOC corpus as a native MISP Event, for teams running MISP rather than a TAXII-based pipeline.</p>
      <p class="tag">TI Subscription required</p>
    </section>

    <section>
      <h3>🆕 SIEM/SOAR Push Delivery &mdash; Splunk, QRadar &amp; Cortex XSOAR</h3>
      <p>A companion to STIX/TAXII and MISP above, for teams that want findings pushed to them rather than polling for them. Configure a destination once via <code>POST /v1/siem/configure</code> and real-time findings from breach, domain, infostealer, SIM swap, OAuth, and dark-web-channel monitoring dispatch automatically &mdash; no polling required.</p>
      <p>Supports Splunk HTTP Event Collector, CEF (QRadar and other CEF-compatible SIEMs), and Cortex XSOAR's Generic Webhook incident-creation shape.</p>
    </section>

    <section>
      <h3>🆕 Shareable Risk Report Links</h3>
      <p><code>POST /v1/report/share</code> &mdash; Turn any wallet scan, domain check, or vendor sweep result into a persistent URL. Generating a link requires a subscription; viewing a shared link is public, no login required &mdash; paste it into a client ticket or incident report the same way you'd link to a VirusTotal or Shodan result page.</p>
    </section>

    <section>
      <h3>🆕 Agentic Attack Surface &mdash; New Endpoints</h3>
      <p>Three new endpoints targeting the emerging attack surface of AI agent credentials, hijacked agent sessions, and poisoned MCP/tool ecosystems &mdash; timed to the first documented fully-autonomous-AI-agent ransomware operation (JadePuffer, reported July 2026).</p>
      <p><code>POST /v1/metered/tech-stack-cve</code> &mdash; Agent framework exploit monitoring. Cross-references your declared tech stack against CISA KEV and high-EPSS CVEs &mdash; now covering AI agent orchestration frameworks (Langflow, LangChain, AutoGPT, CrewAI, Flowise, n8n self-hosted) and companion infrastructure (Nacos, MinIO), the exact vector JadePuffer used for initial access and lateral movement.</p>
      <p><code>POST /v1/metered/mcp-registry-risk</code> &mdash; MCP server &amp; agent-tool registry reputation. Checks an MCP server URL or package name against RelayShield's criminal IOC corpus, typosquat detection against known MCP domains, and domain registration age &mdash; early coverage for an ecosystem with minimal dedicated security tooling today.</p>
      <p><code>POST /v1/metered/prompt-injection-breach</code> &mdash; Flags stolen session/credential exposure whose source dump text suggests an AI agent, rather than a traditional phishing or malware campaign, was involved in obtaining it.</p>
      <p>Also enhanced: <code>nhi-exposure</code> and <code>session-risk</code> now classify agent-framework API keys (OpenAI, Anthropic, LangSmith) and hijacked AI agent platform sessions (ChatGPT, Claude, Zapier, Make, n8n) &mdash; no action needed, existing subscribers get this automatically.</p>
    </section>

    <section>
      <h3>🆕 Native SDK Packages for LangChain and the OpenAI Agents SDK</h3>
      <p>The MCP registry-risk and prompt-injection-breach checks above are now available as installable packages for the two most widely used agent frameworks &mdash; no raw HTTP calls required.</p>
      <p><code>pip install langchain-relayshield</code> &mdash; <a href="https://github.com/nzdsf2-gif/langchain-relayshield">source</a>. Ships both tools plus an optional mandatory pre-execution gate that blocks a risky MCP connect/install action outright, rather than relying on the model to choose to check first.</p>
      <p><code>pip install openai-agents-relayshield</code> &mdash; <a href="https://github.com/nzdsf2-gif/openai-agents-relayshield">source</a>. Same two tools plus the equivalent mandatory gate, built on the SDK's own pre-execution guardrail hook.</p>
    </section>

    <section>
      <h3>📈 OSINT Corpus Growth</h3>
      <p>Our Telegram-native criminal-channel monitoring pipeline now covers <strong>122 active channels</strong>, up from 40&#43; &mdash; continuous, verified surveillance of infostealer markets, credential dumps, and breach announcements, not a static feed subscription. Combined with 3.2M&#43; indicators aggregated from 17 authoritative external sources, most findings surface 24&ndash;72 hours ahead of public breach databases.</p>
    </section>
  </div>

  <div class="product-block">
    <div class="product-label cryptoshield">🛡 Introducing Crypto Shield &mdash; Wallet Security for Solana, EVM, TON &amp; Bitcoin</div>

    <section>
      <h3>📱 A New RelayShield Product</h3>
      <p>Crypto Shield is a read-only wallet security app &mdash; it never asks for your seed phrase or private keys, and can't move your funds. It watches your wallets across <strong>Solana, EVM, TON, and Bitcoin</strong> and alerts you the moment something looks wrong: real-time wallet risk scanning, address poisoning detection, NFT security and floor-price tracking, criminal Telegram marketplace intelligence, SIM-swap and breach alerts, and Signature Guard (approval monitoring, transaction simulation, session hijack detection). Every alert is cryptographically verified before it reaches your phone, and RelayShield carries active Tech E&amp;O and Cyber Insurance coverage.</p>
      <p>Launching first on the <strong>Solana dApp Store</strong>, with additional platforms planned.</p>
    </section>

    <section>
      <h3>🆕 NFT Security Scanning</h3>
      <p>A new "NFT Security" scan type flags malicious or fake NFT contracts &mdash; catching the category of scam where a drainer contract is disguised as an airdropped "reward" NFT. This is separate from the existing NFT floor-price tracking, which only monitors market value, not contract safety.</p>
    </section>

    <section>
      <h3>🆕 XRP Ledger Support</h3>
      <p>Crypto Shield now scans native XRP Ledger addresses &mdash; balance lookups plus fraud-advisory flags for accounts reported for scams.</p>
    </section>

    <section>
      <h3>🆕 Lookalike-Token Fraud Detection</h3>
      <p>Token scans now cross-check the scanned token's name/symbol against CoinGecko's verified contract registry. If a token shares its name with a verified, newly-listed asset or tokenized stock but the contract address doesn't match the verified listing, the scan flags likely impersonation &mdash; a common scam pattern with newly-minted assets.</p>
    </section>
  </div>

  <div class="product-block">
    <div class="product-label consumer">📱 Personal &amp; Business Protection &mdash; WhatsApp / Telegram Alerts</div>

    <section>
      <h3>✅ Fix: WhatsApp Alert Reliability</h3>
      <p>Resolved an issue where WhatsApp's 24-hour messaging window could silently close between alert events, causing some notifications to fail without warning. All subscribers now receive a weekly check-in message. <strong>Tap &ldquo;✓ Active&rdquo; when you receive it</strong> to keep your alert channel open. If you miss it, simply message the bot to reactivate.</p>
    </section>

    <section>
      <h3>🆕 New Alert: Ransomware Victim Warning</h3>
      <p>If the domain associated with your monitored email appears on a ransomware group&rsquo;s victim list, you will now receive an immediate alert via WhatsApp and Telegram before the attack is publicly disclosed. This gives you a window to verify whether your data was affected and contact the organisation directly.</p>
    </section>

    <section>
      <h3>🆕 New Alert: Active Session Hijack Detection</h3>
      <p>RelayShield now monitors criminal channels for stolen session cookies linked to your monitored email addresses. If active credentials are found that an attacker could use right now without your password, you will receive a CRITICAL alert naming the affected services. Tapping &ldquo;Remediation Steps&rdquo; walks you through revoking sessions from a clean device.</p>
    </section>
  </div>

  <div class="product-block">
    <div class="product-label api">🔬 Threat Intelligence API &mdash; For Security Teams &amp; Developers</div>

    <section>
      <h3>📊 IOC Corpus &mdash; Now 3.2M+ Indicators</h3>
      <p>Our threat intelligence database has grown to <strong>3.2M+ indicators</strong> drawn from 17 authoritative external sources updated daily, layered with continuous, verified monitoring across 122 active criminal Telegram channels. We track <strong>4,500+ malware families</strong> including LummaC2, RedLine, Vidar, Emotet, and QakBot. Every indicator carries threat actor attribution, confidence scoring, MITRE ATT&amp;CK technique mapping, and 365-day retention.</p>
    </section>

    <section>
      <h3>🆕 Bulk IOC Enrichment</h3>
      <p><code>POST /v1/metered/bulk-ioc</code> &mdash; Submit up to 100 indicators in a single call. Built for SIEM log enrichment pipelines. Returns malware family, threat actor, confidence score, and first/last seen for each.</p>
      <p class="price">$0.50 per batch (up to 100 IOCs)</p>
    </section>

    <section>
      <h3>🆕 IOC Pivot &mdash; Lateral Infrastructure Discovery</h3>
      <p><code>POST /v1/metered/ioc-pivot</code> &mdash; Given one known-malicious indicator, discover all related infrastructure sharing the same malware family.</p>
      <p class="price">$0.20 per call</p>
    </section>

    <section>
      <h3>🆕 Brand Protection Monitoring</h3>
      <p><code>POST /v1/metered/brand-monitor</code> &mdash; Scan 3.2M+ indicators for your brand name. Returns phishing domains, malware C2 referencing your name, and dark web mentions.</p>
      <p class="price">$0.25 per call</p>
    </section>

    <section>
      <h3>🆕 Agentic AI Identity Risk</h3>
      <p><code>POST /v1/metered/bulk-identity-risk</code> &mdash; Score the identity risk of up to 10 organisational domains plus up to 5 agent or service account identities per domain in a single call. Each domain returns a 0&ndash;100 risk score across six dimensions. Each agent identity returns breach, infostealer, and stolen session signals. A critically exposed agent automatically elevates the organisational risk rating.</p>
      <p class="price">$2.00 per call</p>
    </section>

    <section>
      <h3>🆕 Threat Actor Profiles</h3>
      <p><code>GET /v1/intel/actor</code> &mdash; Full MITRE ATT&amp;CK profile for any named threat actor: tactics, techniques, target sectors, origin country, and associated indicators from our live corpus.</p>
      <p class="tag">TI Subscription required</p>
    </section>

    <section>
      <h3>🆕 Trending Threats</h3>
      <p><code>GET /v1/intel/trending</code> &mdash; The top indicators actively spreading across all feeds in the last 24 or 48 hours, grouped by type.</p>
      <p class="tag">TI Subscription required</p>
    </section>

    <section>
      <h3>⚡ Early Warning Intelligence</h3>
      <p>The threat actor endpoint now surfaces CVE proof-of-concept discussion in criminal channels <strong>24&ndash;72 hours before NVD publication</strong> &mdash; giving you a window to act before patches are available. Combined with daily CISA KEV ingestion (1,600+ actively-exploited CVEs).</p>
    </section>

    <section>
      <h3>🏢 Third-Party Risk Score</h3>
      <p><code>POST /v1/metered/supply-chain</code> &mdash; Composite vendor risk score for up to 10 domains per call: breach history, infostealer exposure, and dark web signals.</p>
      <p class="price">$0.10 per call (up to 10 domains)</p>
    </section>
  </div>

  <div class="product-block">
    <div class="product-label integrations">🔌 Integrations</div>

    <section>
      <h3>🔧 n8n Community Node &mdash; v0.1.15</h3>
      <p>The RelayShield n8n node has been updated with five new operations: Identity Graph correlation, Ransomware Risk assessment, Session Risk / AiTM detection, Supply Chain risk scoring, and an upgraded OAuth Watchlist with live stealer log corpus matching. Search <strong>&ldquo;RelayShield&rdquo;</strong> in n8n to install or update.</p>
    </section>
  </div>

</article>
`;
const HTML = (content) => `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RelayShield — Product Updates</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0F1F3D;
      color: #E8EDF5;
      min-height: 100vh;
      padding: 0 0 60px;
    }
    header {
      background: #0A1628;
      border-bottom: 2px solid #00B5A5;
      padding: 20px 40px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    header .logo {
      font-size: 22px;
      font-weight: 700;
      color: #fff;
      letter-spacing: -0.5px;
    }
    header .logo span { color: #00B5A5; }
    header .subtitle {
      font-size: 13px;
      color: #6B8CAE;
      margin-left: auto;
    }
    .container {
      max-width: 760px;
      margin: 48px auto;
      padding: 0 24px;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 8px;
    }
    .intro {
      color: #6B8CAE;
      font-size: 14px;
      margin-bottom: 40px;
      line-height: 1.6;
    }
    .release-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 32px;
    }
    .badge {
      background: #00B5A5;
      color: #0F1F3D;
      font-weight: 700;
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    article h2 {
      font-size: 20px;
      font-weight: 700;
      color: #fff;
    }
    section {
      background: #1A2E4A;
      border: 1px solid #243B5A;
      border-left: 3px solid #00B5A5;
      border-radius: 6px;
      padding: 20px 24px;
      margin-bottom: 16px;
    }
    section h3 {
      font-size: 15px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 10px;
    }
    section p {
      font-size: 14px;
      line-height: 1.65;
      color: #B0C4D8;
    }
    section p + p { margin-top: 8px; }
    code {
      background: #0F1F3D;
      color: #00B5A5;
      font-family: 'SFMono-Regular', Consolas, monospace;
      font-size: 12.5px;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid #243B5A;
    }
    .price {
      display: inline-block;
      margin-top: 10px !important;
      background: #0F1F3D;
      border: 1px solid #00B5A5;
      color: #00B5A5 !important;
      font-size: 12px !important;
      padding: 3px 10px;
      border-radius: 4px;
      font-weight: 600;
    }
    .tag {
      display: inline-block;
      margin-top: 10px !important;
      background: #1A3A5C;
      border: 1px solid #4A6A8A;
      color: #8AB4D4 !important;
      font-size: 12px !important;
      padding: 3px 10px;
      border-radius: 4px;
    }
    strong { color: #fff; font-weight: 600; }
    .product-block { margin-bottom: 36px; }
    .product-label {
      font-size: 13px; font-weight: 700; letter-spacing: 0.3px;
      padding: 8px 14px; border-radius: 5px 5px 0 0;
      margin-bottom: 0; display: inline-block;
    }
    .product-label.consumer     { background: #00B5A5; color: #0A1628; }
    .product-label.api          { background: #1A3A5C; color: #7FC8E8; border: 1px solid #2A5A8C; }
    .product-label.integrations { background: #2A2A4A; color: #A0A0D0; border: 1px solid #3A3A6A; }
    .product-label.cryptoshield { background: #9945FF; color: #fff; }
        footer {
      text-align: center;
      color: #4A6A8A;
      font-size: 12px;
      margin-top: 48px;
    }
    footer a { color: #00B5A5; text-decoration: none; }
  </style>
</head>
<body>
  <header>
    <div class="logo">Relay<span>Shield</span></div>
    <div class="subtitle">Customer Portal — Product Updates</div>
  </header>
  <div class="container">
    <h1>What's New</h1>
    <p class="intro">Release notes for RelayShield subscribers. This page is updated with each product release.<br>Questions? Contact <a href="mailto:support@relayshield.net" style="color:#00B5A5;">support@relayshield.net</a></p>
    ${content}
    <footer>
      <p>RelayShield &mdash; Identity protection built for what comes after the breach.</p>
      <p style="margin-top:8px;"><a href="https://api.relayshield.net/developers">Developer docs</a> &nbsp;&middot;&nbsp; <a href="mailto:support@relayshield.net">Support</a></p>
    </footer>
  </div>
</body>
</html>`;

const GATE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RelayShield — Access Required</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #0F1F3D; color: #E8EDF5;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .box { background: #1A2E4A; border: 1px solid #243B5A; border-top: 3px solid #00B5A5;
           border-radius: 8px; padding: 40px; max-width: 420px; text-align: center; }
    h2 { color: #fff; margin-bottom: 12px; }
    p { color: #6B8CAE; font-size: 14px; line-height: 1.6; }
    a { color: #00B5A5; }
  </style>
</head>
<body>
  <div class="box">
    <h2>🔒 Access Required</h2>
    <p>This page is for RelayShield customers. Your access link was sent by email.<br><br>
    If you need access, contact <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
  </div>
</body>
</html>`;

export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const token  = url.searchParams.get("token") || "";
    const valid  = token === "rs-relayshield2026";

    if (!valid) {
      return new Response(GATE_HTML, {
        status: 401,
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    return new Response(HTML(RELEASE_NOTES), {
      status: 200,
      headers: {
        "Content-Type": "text/html;charset=UTF-8",
        // Don't let browsers cache — token check must always run
        "Cache-Control": "no-store",
      },
    });
  },
};
