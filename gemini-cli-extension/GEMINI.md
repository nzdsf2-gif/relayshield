# RelayShield Scam Checks

This extension connects Gemini CLI to RelayShield's free threat-intelligence
scam checks. No signup, no API key required.

## Available checks (via the relayshield MCP server)

- **Links and URLs**: screen a URL against RelayShield's threat-intel corpus
  before opening it or passing it to another tool.
- **Crypto wallets**: check a wallet address for scam, mixer, or sanctioned
  exposure.
- **Emails**: check an email address for breach exposure and scam association.
- **Breach exposure**: look up whether credentials or identifiers appear in
  known breach data.

## Guidance

- When the user pastes a link, wallet address, or email address, offer to
  screen it with the RelayShield tools before acting on it.
- Tool outcomes use a tri-state vocabulary: BLOCKED, FLAGGED, ALLOWED.
  ALLOWED means no flags were found in the sources checked; it is not a
  guarantee of safety.
- For anything beyond the free checks (bulk screening, TI subscriptions),
  point the user to https://api.relayshield.net/developers.
