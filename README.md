# RelayShield

Threat intelligence for commerce. Buyer fraud screening, agent verification, and scam detection powered by a live corpus of 661K+ indicators across 124 monitored marketplaces.

## Products

- **Order Screening** (Shopify) — Buyer fraud screening for marketplace sellers. `$29/mo flat`.
- **TAP Verifier** — Merchant-side Visa Trusted Agent Protocol verification with TI corpus screening. `$49/mo flat`. API: `POST https://api.relayshield.net/v1/tap/verify`
- **Commerce Protection** — Unified buyer screening across Shopify, Walmart, and agent commerce. https://commerce.relayshield.net
- **ChatGPT Plugin** — Free scam checks inside ChatGPT. No signup required.
- **Chrome Extension** — Tri-state verdicts (BLOCKED/FLAGGED/ALLOWED) for links, wallets, and emails.
- **Telegram & WhatsApp Bots** — Personal Shield threat monitoring. `$14.99/mo`.

## API

Base URL: `https://api.relayshield.net`

Key endpoints:
- `POST /v1/link-check` — Screen URLs against the TI corpus
- `POST /v1/tap/verify` — Verify TAP agent signatures with counterparty screening
- `POST /v1/breach` — Check email for data breaches
- `GET /commerce` — Commerce protection landing page

Full spec: `relayshield_api_openapi.yaml`

Developers: https://api.relayshield.net/developers

## Threat Intelligence

- 661K+ indicators
- 124 monitored marketplaces
- 8.6M+ corpus citations

## Contact

- Email: relayshieldadmin@gmail.com
- Site: https://relayshield.net
- Blog: https://blog.relayshield.net
- Privacy: https://privacy.relayshield.net

## License

MIT
