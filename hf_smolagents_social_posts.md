HF blog post (published): https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools

---

## LinkedIn

We built four security tools for AI agents built with smolagents — and published them as an MCP server on Hugging Face.

Most agent frameworks trust two things blindly: the MCP servers they connect to, and the content they ingest. Both are real attack surfaces now — the Sysdig/JadePuffer report on the first fully-autonomous-LLM-agent ransomware operation showed initial access through an unauthenticated RCE in an agent framework itself.

Our four tools check exactly that, before your agent acts on it:
→ Is this MCP server known-malicious?
→ Does this content match known prompt-injection patterns?
→ Does my own tech stack (agent framework included) carry a known CVE?
→ Bulk identity-risk scoring across domains and emails

Pay-as-you-go, self-serve signup, no subscription. Built on a corpus of 3M+ IOCs, 4,500+ tracked malware families, and 40+ monitored criminal marketplaces.

Read the writeup: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools

#AIagents #AgentSecurity #MCP #smolagents #CyberSecurity

---

## Telegram

🛡️ New: RelayShield security tools for smolagents agents, published on Hugging Face.

Four checks your agent can run before it trusts an MCP server or ingests content: mcp-registry-risk, prompt-injection-breach, tech-stack-cve, bulk-identity-risk. Pay-per-call, no subscription needed.

Full writeup: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools

---

## Farcaster (post to /security, /ai, /relayshield)

Agents trust their MCP servers and their inputs blindly by default. We built 4 tools that check both before your agent acts — published as an MCP server + smolagents integration on HF.

Pay-per-call, x402 USDC available too (no key needed for that path).

https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools

---

## Mastodon (infosec.exchange)

New from RelayShield: four #AIsecurity checks for agents built with smolagents, published as an MCP server on @huggingface.

- MCP server reputation check before your agent connects
- Prompt-injection pattern detection on ingested content
- Tech-stack CVE monitoring (covers agent frameworks themselves — Langflow's CVE-2025-3248 was the initial-access vector in the first documented autonomous-agent ransomware op)
- Bulk identity-risk scoring

Self-serve, pay-per-call, no subscription.

https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools

#InfoSec #MCP #AgentSecurity #ThreatIntel

---

## Hashnode cross-post

Don't retype the content — copy the full post from `hf_blog_post.md` (same repo) into Hashnode's editor. **Paste with Cmd+Shift+V (plain text), not a normal paste** — a normal paste leaves the Markdown syntax (`#`, `**`, backticks) unrendered as literal characters (confirmed 2026-07-17, see `feedback_hashnode_paste_markdown.md` in memory).

**Post settings / Discovery page:**

- **Article slug**: `smolagents-agent-security-tools` (same as the HF post's slug — consistency between the canonical and the cross-post)
- **Canonical URL**: `https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools` (mark this as a cross-post pointing back to HF — avoids duplicate-content SEO issues, matches the pattern already used for the AgentCore/x402 announcement)
- **Tags** (cap ~5): `ai`, `cybersecurity`, `mcp`, `agents`, `opensource` — Hashnode may only accept tags that already exist on the platform; if `mcp` doesn't autosuggest, substitute the closest existing tag (e.g. `llm` or `ai-agents`)
- **SEO title** (~60 char budget, separate from the display title): `smolagents Agent Security Tools (MCP + Prompt-Injection)`
- **SEO description** (~150-160 char budget): `Four smolagents.Tool classes that check MCP servers and agent inputs for threats before your AI agent acts — with a companion MITRE ATT&CK dataset.`
- **Cover image**: none required to publish — can add later, same as the prior launch's approach

This will be Hashnode post #10 — crosses the threshold noted in `TODO.md`'s `BLOG-CF-PAGES` item for the planned Cloudflare Pages migration.
