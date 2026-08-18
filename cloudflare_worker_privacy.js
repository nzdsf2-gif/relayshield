export default {
  async fetch(request) {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Privacy Policy | RelayShield</title>
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
  <p class="meta">Last updated: August 2026</p>

  <p>RelayShield ("we", "us", or "our") operates relayshield.net, the RelayShield API, the CryptoShield mobile application, and our Discord and Telegram bots. RelayShield is based in Massachusetts, United States. This policy explains how we collect, use, and protect your information.</p>

  <h2>1. Information We Collect</h2>
  <p><strong>Account &amp; API:</strong> When you sign up, we collect the email address you provide, plus usage data (API call counts, timestamps, endpoint usage). We do not collect payment card data, billing address, or any other checkout details directly. Those are collected and processed entirely by Stripe, our payment processor, and are never transmitted to or stored in RelayShield's systems.</p>
  <p><strong>Mobile number:</strong> You may optionally provide a mobile number to enroll it in SIM swap monitoring. Providing a number is not required to use RelayShield. You may only enroll a number that you own or control, and we never accept a number submitted by one person about another. See section 4 for exactly what we do with it.</p>
  <p><strong>Wallet addresses:</strong> Wallet addresses you add to CryptoShield are stored locally on your device using encrypted storage. We transmit them to our API solely to perform breach and risk checks on your behalf.</p>
  <p><strong>Usage data:</strong> We log API requests (endpoint, timestamp, response code) for security monitoring and rate limiting. We do not log request payloads beyond what is necessary to fulfill the request.</p>
  <p><strong>What we do not do:</strong> We do not purchase, rent, scrape, or otherwise acquire phone numbers from public databases, data brokers, marketing partners, or affiliate programs. Every number we hold was given to us by the person it belongs to, for the purpose stated at the time they gave it.</p>

  <h2>2. How We Use Your Information</h2>
  <ul>
    <li>To provide and improve the RelayShield service</li>
    <li>To send security alerts and digest notifications you have opted into</li>
    <li>To enforce rate limits and prevent abuse</li>
    <li>To comply with legal obligations</li>
  </ul>

  <h2>3. Data Sharing</h2>
  <p>We do not sell your personal information, and we do not share it for targeted advertising, marketing, profiling, credit scoring, or any form of eligibility decision. We share data only with:</p>
  <ul>
    <li><strong>Stripe</strong>: payment processing</li>
    <li><strong>AWS</strong>: infrastructure (data stored in us-east-1, United States)</li>
    <li><strong>Twilio</strong>, our communications and telecommunications data provider: WhatsApp alert delivery, and SIM swap and carrier status lookups on numbers you have enrolled (see section 4)</li>
    <li>Law enforcement when required by valid legal process</li>
  </ul>

  <h2>4. SIM Swap Monitoring</h2>
  <p>SIM swap monitoring is optional and applies only to a mobile number you have explicitly enrolled.</p>
  <p><strong>What we send, and to whom.</strong> If you enroll a mobile number, we periodically send that number to Twilio, our telecommunications data provider, to determine whether the SIM or carrier associated with it has recently changed. We send the number itself and nothing else. We do not send your name, email address, wallet addresses, or any other information about you.</p>
  <p><strong>Why.</strong> A SIM swap is a common precursor to account takeover, because it lets an attacker receive your SMS one-time passcodes. We compare each result against the previously recorded state for your own number, and if the SIM or carrier has changed we alert you so you can contact your carrier and stop relying on SMS for two-factor authentication.</p>
  <p><strong>Limits on use.</strong> The result is used only to alert you, the owner of the number. It is never sold, never shared with advertisers or marketing partners, never used for scoring or profiling, and never disclosed to any third party asking about you.</p>
  <p><strong>Consent and withdrawal.</strong> You consent to this monitoring when you enroll the number, on a screen that states this purpose before any lookup takes place. You may withdraw consent at any time by removing the number in the app or by emailing <a href="mailto:support@relayshield.net">support@relayshield.net</a>. Lookups stop immediately and the stored number and its carrier history are deleted.</p>

  <h2>5. Chat Bots (Discord and Telegram)</h2>
  <p>We operate bots on Discord and Telegram. They respond only to commands you explicitly send them.</p>
  <p><strong>What the bot can see.</strong> On Discord, our app does not request the Message Content Intent. It is structurally unable to read the messages in a server, including messages sent while it is present. The only thing it ever receives is the text you deliberately type into a slash command, plus the Discord-supplied username of the person who ran it.</p>
  <p><strong>What we do with what you send.</strong> A link or wallet address you submit is screened against our threat intelligence corpus and, where relevant, third-party reputation providers. An email address you submit to the exposure command is checked against breach and infostealer sources. The result is returned to you and used for nothing else.</p>
  <p><strong>What we store.</strong> Nothing. Bot commands create no account, no profile and no history. We do not build a record of what you have checked, and we do not associate your checks with your Discord or Telegram identity.</p>
  <p><strong>What we log.</strong> The bot does not write the content of your commands to its logs. Links, wallet addresses, email addresses and usernames submitted to the bot are not recorded in a readable form. Operational logs contain errors and timing only, and are retained for 90 days as described in the Data Retention section.</p>
  <p><strong>Replies are private by default.</strong> On Discord, every reply is ephemeral: only the person who ran the command sees it. A flagged link or address result offers a button to repost the result to the channel, and it is posted only if you press it. Exposure results are never shareable and have no such button, because a breach result is about a person.</p>
  <p><strong>Third parties.</strong> Screening a link or address may involve the third-party providers listed in the Data Sharing section. We send the item being screened and nothing else. We do not send your Discord or Telegram identity, your server, or any other information about you.</p>

  <h2>6. Data Retention</h2>
  <p>API logs are retained for 90 days and then automatically deleted. The identifiers you submit for screening, such as an email address or phone number, are not written to those logs in a readable form: they are replaced with a one-way hash before anything is recorded. Account data is retained until you request deletion. An enrolled mobile number and its carrier history are retained only while the number stays enrolled, and are deleted when you remove it. Wallet addresses stored on-device are under your control and can be deleted at any time from the app.</p>

  <h2>7. Your Rights</h2>
  <p>You may request access to, correction of, or deletion of your personal data at any time by contacting <a href="mailto:support@relayshield.net">support@relayshield.net</a>. You may withdraw consent to SIM swap monitoring at any time, as described in section 4.</p>

  <h2>8. Data Location</h2>
  <p>All personal data is processed and stored in the United States, in AWS region us-east-1 (Northern Virginia). Results returned to us by our telecommunications data provider are not transferred to, accessed from, or stored in any location outside the United States.</p>

  <h2>9. Security</h2>
  <p>We use TLS in transit and AES-256 at rest. API keys are hashed before storage. We do not store wallet private keys.</p>

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
