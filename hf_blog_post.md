# Giving agent frameworks a threat-intel safety check: RelayShield's smolagents tools

If you're building autonomous agents with `smolagents`, two of the riskiest surfaces are usually invisible until something goes wrong: the MCP servers your agent connects to, and the prompts it gets fed by tools/data sources it doesn't fully trust. We built four `smolagents.Tool` classes that let an agent check both before it acts.

## What's in the Space

[`relayshieldadmin/relayshield-agentic-attack-surface`](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface) is a live MCP server (also usable as a Gradio Space) exposing four tools:

- **`mcp-registry-risk`** — checks an MCP server against known-malicious/impersonation registry entries before your agent connects to it
- **`prompt-injection-breach`** — flags whether content an agent is about to ingest matches known prompt-injection patterns
- **`tech-stack-cve`** — cross-references a declared tech stack (including agent frameworks themselves — LangChain, CrewAI, AutoGPT, Nacos, etc.) against CISA KEV + high-EPSS CVEs
- **`bulk-identity-risk`** — scores up to 10 domains x 5 associated emails each for breach/infostealer/session/CVE exposure in one call

`relayshield_smolagents_tool.py` wraps all four as drop-in `smolagents.Tool` subclasses — pull it from the Space repo and hand it to your `CodeAgent`/`ToolCallingAgent` alongside your other tools.

## Why this matters for agent builders specifically

The Sysdig/JadePuffer report on the first fully-autonomous-LLM-agent ransomware operation showed initial access through an unauthenticated RCE in an agent framework (Langflow, CVE-2025-3248, CISA KEV-tagged) — exactly the class of thing `tech-stack-cve` is built to catch generically, including on your own agent's dependencies, not just customer-facing infrastructure.

## Pricing

Each call is billed pay-as-you-go via Stripe — self-serve signup at [api.relayshield.net/developers](https://api.relayshield.net/developers?source=hf-smolagents), no subscription and no monthly minimum, billed monthly for what you actually use (most teams spend $0 in their first week while integrating). Set your key as `RELAYSHIELD_API_KEY` and you're calling all four tools; the key is what gates usage, not a Space-level secret, so you're never paying for someone else's calls.

For fully autonomous agent-to-agent payments — no human provisioning a key up front — these same four checks are also available pay-per-call in USDC via [x402](https://www.x402.org/) on the underlying API's `/v1/payg/*` routes.

## Feedback welcome

These four tools draw from a continuously growing pipeline behind them: 3M+ IOCs, 4,500+ tracked malware families, 40+ monitored criminal marketplaces, 20+ authoritative feeds, MITRE ATT&CK threat actor profiles (see our companion [MITRE ATT&CK group-technique dataset](https://huggingface.co/datasets/relayshieldadmin/mitre-attack-groups)), and CISA KEV-backed early warnings — we picked these four as the most agent-relevant checks to start with, out of a broader 22-endpoint API. If there's a fifth tool that would actually get used in your agent pipelines, we'd like to hear which one.

— RelayShield
