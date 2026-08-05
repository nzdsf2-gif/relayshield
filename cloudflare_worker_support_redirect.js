/**
 * support.relayshield.net — thin redirect to the actual support inbox.
 *
 * Keeps the visible link as "support.relayshield.net" (not a raw mailto:
 * address) while routing mail to relayshieldadmin@gmail.com directly,
 * bypassing support@relayshield.net — that address risks the same silent
 * inbound-mail-drop issue confirmed this session for andrew@relayshield.net
 * on Cloudflare Email Routing.
 */

const SUPPORT_EMAIL = "relayshieldadmin@gmail.com";

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RelayShield Support</title>
  <meta http-equiv="refresh" content="0;url=mailto:${SUPPORT_EMAIL}">
  <style>
    body { background: #0a1628; color: #e2e8f0; font-family: -apple-system, sans-serif;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; text-align: center; }
    a { color: #00B5A5; }
  </style>
</head>
<body>
  <div>
    <p>Opening your email client…</p>
    <p style="margin-top:12px;color:#64748b;font-size:13px;">If nothing happens, <a href="mailto:${SUPPORT_EMAIL}">click here to email support</a>.</p>
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
