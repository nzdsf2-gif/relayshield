# LLMjacking is draining AI budgets faster than most teams notice — here's how to catch it before the bill does

A leaked AWS key used to mean someone might spin up crypto-mining instances on your account. In 2026, it increasingly means someone routes inference traffic through your Claude, GPT, or Gemini access instead — and the bill looks nothing like mining.

Real incidents this year: **$46,000/day** from a single exposed AWS Bedrock credential (Sysdig's research). **$82,000 in 48 hours** from one leaked Google Gemini key. One company ran up a **$500,000 single-month Claude bill** simply from unthrottled employee API licenses with no usage cap. Sysdig also reports a **376% rise in credential theft targeting AI services specifically** between Q4 2025 and Q1 2026 — this isn't generic credential theft with an AI-shaped side effect, it's now its own targeted category, with its own underground market: stolen LLM API keys reportedly sell for as little as **$30**.

The industry has a name for it now: **LLMjacking**.

## Why this is a different kind of exposure

A leaked database credential is bad because of what someone can *read*. A leaked LLM API key is bad because of what someone can *spend* — and unlike most cloud resources, LLM inference has no natural ceiling. There's no disk that fills up, no instance limit that caps the damage. A key with no usage cap attached to a company card is, functionally, a blank check with your name on it, sitting in a criminal's stealer-log archive until someone gets around to using it.

The asymmetry is what makes this category so attractive to attackers: a stolen key costs $30 and can be resold or used directly to route tens of thousands of dollars a day in inference costs onto the victim's account. Attackers don't need to breach your infrastructure to hurt you here — they just need one developer's laptop to get hit by an infostealer, and the key sitting in a `.env` file or shell history does the rest.

## The detection gap

Most security tooling watches for the wrong signal. Generic secret scanners flag "an API key was found" without distinguishing a Stripe key (bounded financial risk, easily capped) from an LLM provider key (unbounded spend risk, often provisioned with no cap at all). By the time a company notices — usually via the invoice — the damage is already done. That's reactive detection: it tells you what happened, after it happened.

We built RelayShield around a different premise: catch the signal *while the attack is still forming*, not after. Our infostealer-log monitoring pipeline already watches criminal marketplaces for exposed credentials in near real time — we just extended it to specifically recognize LLM/AI provider key formats (OpenAI, Anthropic, Google, Groq, xAI, Replicate) and treat them as the CRITICAL-severity finding the real dollar-impact data says they are, not lumped in with lower-stakes SaaS key leaks.

## What we shipped

**A dedicated detection endpoint** — `check_llm_credential_exposure` — that scans our stealer-log corpus for exposed LLM provider keys tied to a domain, and returns which provider, how severe, and what to do about it (rotate immediately, check the usage dashboard *now*, don't wait for the invoice).

**Free to try, no signup required.** This is available as one of 13 tools on our MCP server (Model Context Protocol) — [RelayShield Agentic Attack Surface](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface) — and it's the one tool on that server you can call with zero API key. We think LLMjacking detection is valuable enough that the barrier to trying it should be zero.

**A composite risk tool**, `check_agent_risk_summary`, that combines LLM credential exposure with breach and tech-stack CVE checks into a single call — useful for agent pipelines that want one fused verdict instead of orchestrating multiple tool calls themselves.

**Available everywhere we already operate**: the same detection is live via our REST API (`/v1/metered/llm-credential-exposure`), on the MCP server for agentic workflows, and as a `/checkllm` command in our Telegram bot for business-tier subscribers who've set a monitored company domain.

## Why an MCP server, specifically

If you're building with autonomous agents, this threat has a second angle worth naming directly: an agent with its own LLM API key is itself a target. An exposed agent credential doesn't just cost money — depending on what that agent is authorized to do, a stolen key can let an attacker impersonate the agent's own actions. Wiring an LLMjacking check into your agent's own security tooling isn't just about your organization's exposure, it's about the agent's.

## Try it

- MCP server (13 tools, LLM credential check works with no key): [huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface)
- Full API + self-serve key signup: [api.relayshield.net/developers](https://api.relayshield.net/developers)

If you've been burned by this — or you check and find nothing, which is also useful information — we'd like to hear about it.

— RelayShield
