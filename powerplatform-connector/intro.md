# RelayShield

RelayShield is identity threat intelligence for security and IT operations. It answers one question
in a form a flow can act on: has this person, phone number, domain, vendor or address already been
exposed?

Every operation takes a single identifier and returns a severity-ranked verdict with the evidence
behind it, so a flow can branch on the result instead of routing a human to another console.

## What you can build

- **Joiner, mover, leaver.** On a new hire, check the corporate address for prior breach and
  infostealer exposure before the account is handed over. On an exit, check whether the departing
  user's credentials or session cookies are already circulating.
- **Vendor and third-party risk.** Score a vendor domain when a supplier record is created, and
  re-score on a schedule. Send anything above your threshold to an approval before contracts move.
- **Helpdesk triage.** Turn an exposure finding into a ticket in your service desk, with the
  affected service named, rather than a generic "possible compromise" alert.
- **Brand and domain watch.** Detect lookalike domains registered against your own, and alert the
  channel your team already reads.
- **Pre-commit and pre-deploy checks.** Scan text or a diff for leaked API keys before it is
  published to a wiki, a ticket or a repository.

## Operations

| Operation | Takes | Answers |
|---|---|---|
| Check an email for data breach exposure | Email | Which breaches, when, and what was exposed |
| Check a phone number for a recent SIM swap | Phone (E.164) | Whether the SIM changed recently, and when |
| Find lookalike domains impersonating a domain | Domain | Registered lookalikes, with risk scoring |
| Check an email for risky OAuth app grants and stolen tokens | Email | Risky third-party grants, plus stolen tokens seen in stealer logs |
| Check an email for infostealer malware exposure | Email | Whether the address appears in infostealer logs |
| Score vendor domains for third-party breach risk | Domain list | Per-vendor risk rating and the factors behind it |
| Scan text for leaked API keys and credentials | Text | Credential type, location, and a non-reversible fingerprint |
| Check an email for stolen active session cookies | Email | Which services have live hijackable sessions |
| Get a combined identity risk score for an email | Domain | A single score combining the signals above |
| Check TLS certificate expiry for a domain | Domain | Days remaining and the issuing authority |
| Check a BIN or card range for carding-market exposure | BIN | Whether the range appears in carding markets |
| Check an IP address for malicious reputation | IP | Reputation, categories, and observed activity |

## Prerequisites

You need a RelayShield API key. Create an account at
[api.relayshield.net/developers](https://api.relayshield.net/developers) and copy the key from the
dashboard.

## Getting credentials

1. Go to [api.relayshield.net/developers](https://api.relayshield.net/developers).
2. Create an account, or sign in to an existing one.
3. Copy the API key from the dashboard.
4. When you add the RelayShield connection in Power Automate or Power Apps, paste the key into the
   **RelayShield API key** field.

The key is sent as the `x-api-key` request header and is stored by Power Platform as a secure
string. There is no OAuth flow and no redirect URI to configure.

## Known limitations

- Operations are billed per call against your RelayShield plan. A flow that runs an operation inside
  a loop over a large collection will consume calls quickly. Use the vendor risk operation's domain
  array rather than looping where you can.
- SIM swap coverage depends on the carrier. Some carriers and some regions do not expose a
  last-changed date, in which case the operation returns an explicit "unknown" rather than a
  negative result. Treat unknown as unknown, not as safe.
- Breach and infostealer results describe exposure that is already known. A clean result is not a
  guarantee that credentials are safe, only that nothing has been observed.
- Requests are rate limited per plan. The connector surfaces HTTP 429 so a flow can retry.

## Support

[support@relayshield.net](mailto:support@relayshield.net)
