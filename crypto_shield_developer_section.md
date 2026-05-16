# Developer Section — crypto.relayshield.net
## Add to Carrd below the pricing section

---

### HEADLINE
Built for developers and AI agents

### SUBHEADLINE
Every Crypto Shield signal is available via REST API — no SDKs, plain JSON in, plain JSON out.
Integrate wallet monitoring, token risk, and SIM swap detection directly into your app or agent.

---

### ENDPOINT + PRICING TABLE

| Endpoint | What it does | Price |
|---|---|---|
| POST /v1/wallet-risk | Multi-chain risk score — EVM, Solana, TON | $0.15 / call |
| POST /v1/token-security | Rug pull, honeypot & tax analysis | $0.10 / call |
| POST /v1/nft-security | NFT contract risk scan | $0.10 / call |
| POST /v1/breach | Email breach — 13B+ records | $0.10 / call |
| POST /v1/sim-swap | SIM/eSIM swap — live carrier data | $0.25 / call |

Pay-as-you-go via x402 (USDC on Base) or subscribe on RapidAPI.

---

### PYTHON SNIPPET

```python
import requests

url = "https://relayshield-security-intelligence.p.rapidapi.com/v1/wallet-risk"

payload = { "address": "0xYourWalletAddress" }
headers = {
    "x-rapidapi-key": "YOUR_RAPIDAPI_KEY",
    "x-rapidapi-host": "relayshield-security-intelligence.p.rapidapi.com",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
print(response.json())
```

---

### NODE.JS SNIPPET

```javascript
const axios = require("axios");

const options = {
  method: "POST",
  url: "https://relayshield-security-intelligence.p.rapidapi.com/v1/wallet-risk",
  headers: {
    "x-rapidapi-key": "YOUR_RAPIDAPI_KEY",
    "x-rapidapi-host": "relayshield-security-intelligence.p.rapidapi.com",
    "Content-Type": "application/json"
  },
  data: { address: "0xYourWalletAddress" }
};

const response = await axios.request(options);
console.log(response.data);
```

---

### CTA BUTTON
View full API docs on RapidAPI →
URL: https://rapidapi.com/relayshield/api/relayshield-security-intelligence

---

## CARRD IMPLEMENTATION NOTES
- Add a new Section below the pricing/plans section
- Background: dark (matches rest of page)
- Add a Text element for headline + subheadline
- Add a Table or styled Text element for the endpoint list
- Add a Code element (or styled text box) for the Python snippet
- Add a Button linking to RapidAPI
- Keep it minimal — developers scan, they don't read
