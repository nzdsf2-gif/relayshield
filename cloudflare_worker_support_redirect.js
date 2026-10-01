/**
 * support.relayshield.net — RelayShield support page.
 *
 * Served by the "relayshield-support-redirect" worker (wrangler.support.toml),
 * route support.relayshield.net/*. Replaces the original mailto-redirect stub
 * with a full support page: product overview, the four free tools, contact
 * channels, and FAQ. Contact email is relayshieldadmin@gmail.com directly —
 * support@relayshield.net risks the silent inbound-mail-drop issue confirmed
 * for andrew@relayshield.net on Cloudflare Email Routing.
 */

const SUPPORT_EMAIL = "relayshieldadmin@gmail.com";

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Support — RelayShield Free Scam Checks</title>
  <meta name="description" content="Get help with RelayShield Free Scam Checks: free threat-intelligence screening for links, crypto wallets, suspicious emails, and data breaches.">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 760px; margin: 0 auto; padding: 40px 24px;
           background: #0a1628; color: #e2e8f0; line-height: 1.7; }
    h1 { font-size: 30px; font-weight: 700; color: #ffffff; margin-bottom: 4px; }
    h2 { font-size: 19px; font-weight: 600; color: #ffffff; margin-top: 40px;
         border-bottom: 1px solid #1e3a5f; padding-bottom: 8px; }
    h3 { font-size: 16px; font-weight: 600; color: #7dd3fc; margin-top: 24px; margin-bottom: 6px; }
    .tagline { color: #94a3b8; font-size: 16px; margin-bottom: 32px; }
    a { color: #00B5A5; }
    .card { background: #0f2240; border: 1px solid #1e3a5f; border-radius: 10px;
            padding: 20px 22px; margin: 16px 0; }
    .card p { margin: 8px 0; }
    .tool { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #7dd3fc; font-weight: 600; }
    .faq-q { font-weight: 600; color: #ffffff; margin-top: 20px; }
    .faq-a { color: #cbd5e1; }
    .btn { display: inline-block; background: #00B5A5; color: #06281f !important;
           font-weight: 600; padding: 10px 22px; border-radius: 8px;
           text-decoration: none; margin-top: 8px; }
    .btn:hover { background: #00d3bf; }
    ul { padding-left: 22px; }
    li { margin: 6px 0; color: #cbd5e1; }
    .footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid #1e3a5f;
              color: #64748b; font-size: 13px; }
    .footer a { color: #64748b; }
  </style>
</head>
<body>
  <h1>&#x1F6E1;&#xFE0E; RelayShield Support</h1>
  <p class="tagline">Help with <strong>RelayShield Free Scam Checks</strong> — free threat-intelligence
  screening for phishing links, crypto wallets, suspicious emails, and data breaches.</p>

  <h2>What is RelayShield Free Scam Checks?</h2>
  <p>A free set of four read-only tools that screen what you're about to click, pay, or reply to
  against RelayShield's threat-intelligence corpus: <strong>115 monitored Telegram marketplaces</strong>,
  <strong>494K+ indicators</strong>, and <strong>7.8M+ citations</strong>. No signup, no API key, no cost.</p>

  <div class="card">
    <h3>The four tools</h3>
    <p><span class="tool">check_link</span> — Screen 1&ndash;25 URLs for phishing and malware.</p>
    <p><span class="tool">check_wallet</span> — Risk assessment of a crypto wallet address
    (EVM, Solana, TON, and Bitcoin auto-detected).</p>
    <p><span class="tool">check_email</span> — Score a suspicious email for phishing signals
    from its parsed fields.</p>
    <p><span class="tool">check_breach</span> — Check whether an email address appears in
    known data breaches.</p>
  </div>

  <h2>Get help</h2>
  <div class="card">
    <p><strong>Telegram channel:</strong> <a href="https://t.me/relayshield">t.me/relayshield</a>
    &mdash; announcements and community discussion.</p>
    <p><strong>Telegram miniApp:</strong> <a href="https://t.me/relayshield_bot">t.me/relayshield_bot</a>
    &mdash; run the free checks yourself, no signup.</p>
    <p><strong>Email:</strong> <a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a></p>
    <p><a class="btn" href="mailto:${SUPPORT_EMAIL}">Email support</a></p>
  </div>

  <h2>Frequently asked questions</h2>

  <p class="faq-q">Is it really free?</p>
  <p class="faq-a">Yes. All four tools are free to use &mdash; no signup, no API key, no payment.
  If a tool ever asks you for money or credentials, it isn't us: contact support immediately.</p>

  <p class="faq-q">What do the results mean?</p>
  <p class="faq-a">A <strong>FLAGGED</strong> result means our corpus holds threat intelligence on that
  link, wallet, or address &mdash; treat it as hostile until proven otherwise. <strong>&ldquo;No flags
  found&rdquo;</strong> means nothing in our corpus matched. That is <em>not</em> a clean bill of health:
  absence of evidence is not evidence of absence. Our tools never report anything as &ldquo;safe&rdquo;.</p>

  <p class="faq-q">Do I need an API key for the breach check?</p>
  <p class="faq-a">No. The breach lookup runs against our partner key, which is configured on our
  servers &mdash; you just use the tool.</p>

  <p class="faq-q">How fast are the checks?</p>
  <p class="faq-a">Most checks complete in a few seconds. If a check seems stuck, our upstream services
  may be cold-starting &mdash; wait a minute and try again. For support inquiries, we typically reply
  within two business days.</p>

  <p class="faq-q">How do I report a false positive or something you missed?</p>
  <p class="faq-a">Email <a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a> with the link, wallet,
  or email in question and what you expected. Reports from the field directly improve the corpus.</p>

  <p class="faq-q">Do you store what I check?</p>
  <p class="faq-a">Checks are read-only. We keep aggregate usage counts for abuse prevention and service
  health, and nothing more. See our <a href="https://privacy.relayshield.net/">privacy policy</a>
  for details.</p>

  <div class="footer">
    <p>&copy; 2026 RelayShield &middot;
    <a href="https://relayshield.net/">relayshield.net</a> &middot;
    <a href="https://privacy.relayshield.net/">Privacy</a> &middot;
    <a href="https://terms.relayshield.net/">Terms</a></p>
  </div>
</body>
</html>`;

export default {
  async fetch() {
    return new Response(HTML, {
      status: 200,
      headers: { "Content-Type": "text/html;charset=UTF-8", "Cache-Control": "no-store" },
    });
  },
};
