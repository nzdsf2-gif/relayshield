# RelayShield — Prediction Markets Security Brief

**Use case trigger:** Polymarket hack (June 2026) + nephew's connection at prediction markets startup
**Target buyer:** Security-conscious founder/CTO at small-to-mid prediction markets company

---

## The Threat Surface

Prediction markets have a unique attack surface combining:
1. **Financial infrastructure** — smart contracts, oracle feeds, settlement keys
2. **Identity/credential layer** — admin accounts, API keys, employee credentials
3. **Third-party dependencies** — oracle providers (Chainlink, Pyth, UMA), exchange APIs, RPC nodes

The Polymarket incident was a credential/access control failure, not a smart contract exploit — exactly the surface RelayShield monitors.

---

## How RelayShield Applies

### Immediate value (no new features required)

| Threat | RS Endpoint | What it catches |
|---|---|---|
| Admin credentials in stealer logs | `/v1/metered/infostealer` | Employee credentials in criminal markets before accounts are taken over |
| API keys/tokens exposed | `/v1/metered/nhi-exposure` | Service account tokens (oracle API keys, exchange API credentials, RPC auth) in stealer logs |
| Oracle domain targeted | `/v1/metered/identity-risk-score` | 6-dimension risk score on company domain |
| Vendor/oracle provider compromise | `/v1/metered/supply-chain` | Chainlink, Pyth, UMA, Alchemy, Infura vendor risk |
| Threat actors targeting DeFi | `/v1/intel/actor` | APT groups (Lazarus Group is the primary DeFi threat actor — $3B+ stolen) |
| Infrastructure in criminal channels | `/v1/intel/telegram` | Company domains/IPs appearing in criminal Telegram channels |
| Bulk credential check | `/v1/metered/bulk-identity-risk` | All core team + AI agent identities scored in one call |

### Key endpoint for this vertical: NHI Exposure
The `/v1/metered/nhi-exposure` endpoint is uniquely valuable for prediction markets — it detects API keys and tokens (not just passwords) appearing in criminal stealer logs. A prediction market's oracle signing key or exchange API appearing in a stealer log is the exact precursor to a Polymarket-style incident.

---

## Pitch Angle

> "You don't need a full SOC. You need 30 minutes of setup and a webhook that fires when your oracle API credentials hit criminal markets — before the attacker uses them to manipulate a market."

The comparison point: a single manipulated prediction market outcome could cost 10-100x more than a year of RelayShield TI subscription. This is pure ROI math.

---

## Does This Require New Features?

**No new features needed.** Current RelayShield endpoints cover the core threat surface:

1. NHI exposure — API key/token detection in stealer logs ✅
2. Infostealer monitoring — employee credential exposure ✅  
3. Supply chain risk — oracle provider vendor risk ✅
4. Identity risk score — org-level risk across 6 dimensions ✅
5. Threat actor profiles — Lazarus Group, APT38 DeFi-specific TTPs ✅
6. Bulk identity risk — core team + bot account scoring in one call ✅

**Possible future additions specific to DeFi:**
- Wallet address monitoring (Crypto Shield already does this)
- Smart contract address IOC checking (check if contract address appears in scam databases — GoPlus already integrated)
- On-chain transaction monitoring (out of scope for identity security)

---

## Pricing Recommendation

TI Starter ($499/mo) is the right entry point:
- Full access to NHI exposure, infostealer, supply chain, IOC corpus
- 10,000 API calls/month — sufficient for a 10-50 person team + continuous monitoring
- No sales call, instant setup

For a small startup, could offer 3-month introductory at $299/mo to get them started.

---

## Action Items

- [ ] Draft cold email for nephew to pass to his company (personalized to prediction markets)
- [ ] Identify if Lazarus Group IOCs are in our corpus (primary DeFi threat actor)
- [ ] Consider adding wallet address → stealer log correlation (extends Crypto Shield to B2A)
- [ ] Check if Polymarket's domain/infrastructure appears in our IOC corpus as a data point

---

*RelayShield — Identity protection built for what comes after the breach.*
