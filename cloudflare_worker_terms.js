export default {
  async fetch(request) {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Terms of Service | RelayShield</title>
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
  <h1>Terms of Service</h1>
  <p class="meta">Last updated: August 2026</p>

  <p>By accessing or using RelayShield ("Service"), you agree to these Terms. If you do not agree, do not use the Service. RelayShield is based in Massachusetts, United States.</p>

  <h2>1. Service Description</h2>
  <p>RelayShield provides threat intelligence APIs, breach and credential exposure monitoring, SIM swap risk monitoring, and security alerting services. The Service is provided for informational purposes only and does not constitute financial, legal, or security advice.</p>

  <h2>1a. SIM Swap Monitoring</h2>
  <p>SIM swap monitoring is an optional feature. If you enroll a mobile number, you confirm that you own or control that number and that you consent to us periodically checking it with our telecommunications data provider for SIM and carrier change activity. You may not enroll a number belonging to anyone else, and you may not use the Service to look up, track, or investigate a number that is not your own. Results are provided to you alone, and you may withdraw consent and remove the number at any time. SIM swap detection depends on carrier-supplied data, is not guaranteed to be complete or timely, and must not be relied on as your only defense against account takeover.</p>

  <p><strong>Wireless carrier authorization.</strong> You authorize your wireless carrier to use or disclose information about your account and your wireless device, if available, to RelayShield LLC or its service provider for the duration of your business relationship, solely to help them identify you or your wireless device and to prevent fraud. See our <a href="https://privacy.relayshield.net">Privacy Policy</a> for how we treat your data.</p>

  <h2>2. Accounts &amp; API Keys</h2>
  <p>You are responsible for maintaining the confidentiality of your API key and for all activity under your account. You must notify us immediately at <a href="mailto:support@relayshield.net">support@relayshield.net</a> if you suspect unauthorized use.</p>

  <h2>3. Acceptable Use</h2>
  <p>You may not use the Service to:</p>
  <ul>
    <li>Violate any applicable law or regulation</li>
    <li>Reverse-engineer, scrape, or resell the Service without written permission</li>
    <li>Exceed rate limits or attempt to circumvent usage restrictions</li>
    <li>Use the Service to target, harass, or surveil individuals</li>
    <li>Transmit malware or engage in any activity that disrupts the Service</li>
  </ul>

  <h2>4. Subscription &amp; Billing</h2>
  <p>Paid plans are billed monthly via Stripe. You may cancel at any time; cancellation takes effect at the end of the current billing period. We do not offer refunds for partial periods except where required by law.</p>

  <h2>5. Disclaimer of Warranties</h2>
  <p>THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND. WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR THAT THREAT INTELLIGENCE DATA WILL BE COMPLETE OR ACCURATE. SECURITY DECISIONS SHOULD NOT BE MADE SOLELY ON THE BASIS OF OUR OUTPUT.</p>

  <h2>6. Limitation of Liability</h2>
  <p>TO THE MAXIMUM EXTENT PERMITTED BY LAW, RELAYSHIELD SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES ARISING FROM YOUR USE OF THE SERVICE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES. OUR TOTAL LIABILITY SHALL NOT EXCEED THE AMOUNTS YOU PAID IN THE TWELVE MONTHS PRECEDING THE CLAIM.</p>

  <h2>7. Termination</h2>
  <p>We may suspend or terminate your access immediately for violation of these Terms. You may terminate your account at any time by contacting support.</p>

  <h2>8. Changes to Terms</h2>
  <p>We may update these Terms at any time. Continued use of the Service after changes constitutes acceptance. Material changes will be communicated via email.</p>

  <h2>9. Governing Law</h2>
  <p>These Terms are governed by the laws of the Commonwealth of Massachusetts, USA, without regard to conflict of law principles.</p>

  <h2>10. Contact</h2>
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
