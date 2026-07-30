# Your AI agents have credentials. Someone is already looking for them.

RelayShield's **Agentic Attack Surface** bundle is now live on AWS Marketplace. Five endpoints, one
contract, billed through AWS with no separate account or payment method. If your organisation buys
software through AWS, you can now buy agent security the same way.

But the listing is not the interesting part. The interesting part is why we built it.

## The economics changed

For most of security's history, a stolen credential was a means to an end. The attacker wanted your
data, your customers, your network. The credential was the door.

LLM API keys broke that model. An LLM key is not a door. **It is the thing being stolen**, because it
converts directly into compute that somebody else pays for. There is no lateral movement, no
exfiltration, no ransom note. Just a bill.

The industry has a name for it now: **LLMjacking**. The numbers are not hypothetical.

- **$46,000 per day**, from Sysdig's research on compromised AWS Bedrock credentials.
- **$82,000 in 48 hours**, from a single leaked Google Gemini key in March 2026.
- **35,000+ attack sessions in 40 days**, running **$100,000+ per day** against flagship models, in
  the campaign tracked as Operation Bizarre Bazaar.
- **376% increase** in credential theft targeting AI services between Q4 2025 and Q1 2026, per Sysdig.

Stolen LLM credentials sell for around **$30** on criminal marketplaces. That is the arbitrage: a $30
key against a $46,000 a day burn rate. Those numbers work for an attacker of almost any skill level.
All it takes is one leaked `.env` file.

## Why your existing tooling misses it

Ask yourself what would actually fire if an agent's Anthropic key leaked tomorrow.

Your EDR sees nothing, because no endpoint is compromised. Your SIEM sees nothing, because there is no
anomalous login, no impossible travel, no privilege escalation. Your cloud posture tool sees nothing,
because nothing is misconfigured. Your DLP sees nothing, because no data left the building.

The first signal is your bill, and by then you have been paying for somebody else's inference for
days or weeks. Sysdig's $46,000 per day figure is not the cost of the breach. It is the cost of the
part of the breach that nobody noticed.

This is a detection gap, not a tooling failure. The controls are all working correctly. They are
watching for the wrong thing, because the thing being stolen is not data.

## What we built

RelayShield already ran the pipeline that catches this. We monitor **83 criminal Telegram channels**
and **20 threat intelligence feeds**, and the corpus currently holds **4.6 million indicators**. What
was missing was pattern matching for AI provider key formats specifically.

So we added them. Today we match **19 distinct LLM credential formats across 14 named providers**:
OpenAI, Anthropic, Google, AWS Bedrock, Groq, xAI, Replicate, DeepSeek, Moonshot, Qwen, Alibaba,
NVIDIA, Hugging Face and LangSmith, plus a generic matcher for the long tail of OpenAI compatible
endpoints.

## The bundle

**Agentic Attack Surface** is five endpoints at $299 per month, plus per call usage.

| Endpoint | What it answers | Per call |
|---|---|---|
| `llm-credential-exposure` | Are our LLM provider keys circulating in stealer logs and criminal markets? | $0.40 |
| `mcp-registry-risk` | Is this MCP server a typosquat, newly registered, or known malicious, before an agent connects? | $0.35 |
| `prompt-injection-breach` | Have credentials or sessions been exposed through agentic breaches? | $0.35 |
| `tech-stack-cve` | Which CVEs target the agent frameworks we actually run? | $0.20 |
| `bulk-identity-risk` | What is the identity risk across our whole org, scored per agent email? | $2.00 |

The common thread: these are all questions about the **identity and supply chain layer of an agent deployment**.
That layer exists because you deployed agents, and nothing in a traditional security stack was built
to watch it.

## Try it without buying anything

The `llm-credential-exposure` check runs on a shared free tier through our MCP server, with no API
key required.

```python
from gradio_client import Client

client = Client("relayshieldadmin/relayshield-agentic-attack-surface")
print(client.predict("yourcompany.com", "", api_name="/check_llm_credential_exposure"))
```

Point it at your own domain. If it comes back clean, you have lost thirty seconds. If it does not,
you will want to know today rather than at the end of the billing cycle.

The REST endpoint runs the same check.

```bash
curl -X POST https://api.relayshield.net/v1/metered/llm-credential-exposure \
  -H "X-RS-API-KEY: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain": "yourcompany.com"}'
```

## One honest caveat

A clean result from RelayShield means **nothing was found in the sources we actually queried**. It is
not a certificate that your keys are safe. We never map a clean result to "good" in any integration
we ship. In our Cortex XSOAR pack, a clean check returns DBotScore *Unknown* rather than *Good*,
precisely so it cannot silently contribute a "safe" vote to an auto close rule.

Criminal marketplaces are not a complete index of the world. Anyone who tells you their threat feed
proves absence is selling you certainty that does not exist.

## Get it

- **AWS Marketplace.**
  [Agentic Attack Surface on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq).
  Billing runs through your existing AWS account, with no separate payment method.
- **Direct.** [api.relayshield.net/developers](https://api.relayshield.net/developers?src=blog), pay
  as you go, no monthly minimum.
- **Agents.** The API is x402 enabled, so an agent can pay per call in USDC without a human ever
  creating an account.

Questions, or a provider key format we should be matching and are not:
[support@relayshield.net](mailto:support@relayshield.net).
