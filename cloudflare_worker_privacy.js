export default {
  async fetch(request) {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Privacy Policy — RelayShield</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 760px; margin: 0 auto; padding: 40px 24px; color: #1e293b; line-height: 1.7; }
    h1 { font-size: 28px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
    h2 { font-size: 18px; font-weight: 600; color: #0f172a; margin-top: 32px; }
    .meta { color: #64748b; font-size: 14px; margin-bottom: 40px; }
    a { color: #00B5A5; }
    .back { display: inline-block; margin-bottom: 32px; font-size: 14px; color: #00B5A5; text-decoration: none; }
    hr { border: none; border-top: 1px solid #e2e8f0; margin: 40px 0; }
  </style>
</head>
<body>
  <a href="https://relayshield.net" class="back">← RelayShield</a>
  <h1>Privacy Policy</h1>
  <p class="meta">Last updated: June 2026</p>

  <p>RelayShield ("we", "us", or "our") operates relayshield.net and the CryptoShield mobile application. RelayShield is based in Massachusetts, United States. This policy explains how we collect, use, and protect your information.</p>

  <h2>1. Information We Collect</h2>
  <p><strong>Account &amp; API:</strong> When you sign up, we collect the email address and phone number you provide for monitoring, plus usage data (API call counts, timestamps, endpoint usage). We do not collect payment card data, billing address, or any other checkout details directly — these are collected and processed entirely by Stripe, our payment processor, and are never transmitted to or stored in RelayShield's systems.</p>
  <p><strong>Wallet addresses:</strong> Wallet addresses you add to CryptoShield are stored locally on your device using encrypted storage. We transmit them to our API solely to perform breach and risk checks on your behalf.</p>
  <p><strong>Usage data:</strong> We log API requests (endpoint, timestamp, response code) for security monitoring and rate limiting. We do not log request payloads beyond what is necessary to fulfill the request.</p>

  <h2>2. How We Use Your Information</h2>
  <ul>
    <li>To provide and improve the RelayShield service</li>
    <li>To send security alerts and digest notifications you have opted into</li>
    <li>To enforce rate limits and prevent abuse</li>
    <li>To comply with legal obligations</li>
  </ul>

  <h2>3. Data Sharing</h2>
  <p>We do not sell your personal information. We share data only with:</p>
  <ul>
    <li><strong>Stripe</strong> — payment processing</li>
    <li><strong>AWS</strong> — infrastructure (data stored in us-east-1)</li>
    <li><strong>Twilio</strong> — WhatsApp alert delivery</li>
    <li>Law enforcement when required by valid legal process</li>
  </ul>

  <h2>4. Data Retention</h2>
  <p>API logs are retained for 1 year. Account data is retained until you request deletion. Wallet addresses stored on-device are under your control and can be deleted at any time from the app.</p>

  <h2>5. Your Rights</h2>
  <p>You may request access to, correction of, or deletion of your personal data at any time by contacting <a href="mailto:support@relayshield.net">support@relayshield.net</a>.</p>

  <h2>6. Security</h2>
  <p>We use TLS in transit and AES-256 at rest. API keys are hashed before storage. We do not store wallet private keys.</p>

  <h2>7. Contact</h2>
  <p><a href="mailto:support@relayshield.net">support@relayshield.net</a></p>

  <hr>
  <p style="font-size:13px;color:#94a3b8;">© 2026 RelayShield. All rights reserved.</p>
</body>
</html>`;

    return new Response(html, {
      headers: {
        "Content-Type": "text/html;charset=UTF-8",
        "Cache-Control": "public, max-age=86400",
      },
    });
  },
};
