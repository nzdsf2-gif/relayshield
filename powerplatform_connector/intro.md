# RelayShield

RelayShield screens the identity layer. It checks emails, domains and IP addresses against breach
records, infostealer logs and aggregated threat feeds, so a flow can decide before it grants access,
resets a credential or trusts a message.

The intelligence comes from commercial and public threat feeds combined with continuous monitoring of
95 criminal channels, and is served through one API key that also works over REST, MCP and
STIX/TAXII.

## Prerequisites

- A RelayShield API key on a metered subscription. Every action in this connector is billed per call.
- No other Microsoft licence or Azure resource is required.

## How to get credentials

1. Go to <https://api.relayshield.net/developers> and sign up with an email address.
2. Add a payment method to enable metered calls.
3. Copy the API key shown after signup.
4. In Power Automate, create a RelayShield connection and paste the key into **RelayShield API key**.
   It is stored as a secure string and is sent as the `X-RS-API-KEY` header.

Keep the key in a Power Platform environment variable or Azure Key Vault rather than pasting it into
each flow.

## Actions

| Action | What it does |
|---|---|
| `CheckEmailBreach` | Check email for breach exposure |
| `CheckInfostealer` | Check email in infostealer logs |
| `CheckDomainLookalikes` | Find phishing lookalike domains |
| `GetIpIntel` | Get reputation for a domain or IP |
| `CheckSupplyChain` | Assess vendor breach risk |
| `CheckRansomwareRisk` | Check domain on ransomware leak sites |
| `GetIdentityRiskScore` | Score a domain for identity risk |
| `ScanTextForSecrets` | Scan text or a diff for secrets |
| `CheckSessionRisk` | Check for stolen session cookies |
| `CheckMachineCredentials` | Find exposed machine credentials |
| `CheckOauthTokens` | Find exposed OAuth and SaaS tokens |

## Known issues and limitations

- **Every action is billed per call.** There is no free tier inside this connector. A loop over a
  large collection bills once per item, so gate loops carefully.
- **This connector is Premium tier, and that cannot be changed later.** Users need a plan that
  includes premium connectors. Microsoft's own documentation states the Premium tier cannot be
  removed or changed once published.
- **Pay-as-you-go endpoints are deliberately not exposed here.** They settle in USDC over x402, which
  has no meaning inside a Power Automate flow. Only API-key metered endpoints are included.
- **SIM swap checking is not included in this release.** The underlying carrier data is pending
  network registration, and an action that cannot return a verdict is worse than no action. It will
  be added in a connector update once carrier coverage is live.
- **Actions return a verdict, not a decision.** A clean result means nothing matched the corpus at
  the time of the call. It is evidence for a flow's branch condition, not proof of safety.
- **Rate limits apply per key.** A burst from a high-volume flow may receive HTTP 429; handle it with
  the standard Power Automate retry policy.

## Support

`support@relayshield.net`

## Documentation

- API reference: <https://api.relayshield.net/docs>
- Developer guide: <https://api.relayshield.net/developers>
