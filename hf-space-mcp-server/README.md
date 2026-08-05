---
title: RelayShield Agentic Attack Surface
emoji: 🛡️
colorFrom: blue
colorTo: red
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
pinned: false
tags:
  - mcp-server
  - security
  - agent
---

# RelayShield Agentic Attack Surface

13 AI-agent-specific security checks from [RelayShield](https://api.relayshield.net/developers), exposed as MCP tools:

- **MCP Server Risk** — typosquat/reputation/registration-age risk check for MCP server URLs. Use this before connecting an agent to an unfamiliar MCP server or tool registry.
- **Prompt-Injection Breach Check** — checks whether an email's credentials were exposed via a breach sourced specifically from a prompt-injection attack against an AI agent, distinct from ordinary phishing/malware-sourced breaches.
- **Tech Stack CVE Check** — CISA KEV / high-EPSS CVEs targeting a declared AI agent framework or tech stack.
- **Bulk Identity Risk** — hierarchical org + AI-agent-identity risk scoring for a domain and its agent/service-account identities.
- **OAuth Watchlist** — OAuth-connected-app breach exposure plus stolen OAuth/session tokens.
- **Supply Chain Risk** — breach and infostealer exposure check for up to 10 vendor domains.
- **Session Risk** — active or reusable stolen session (cookie/token) exposure that can bypass MFA.
- **NHI Exposure** — API keys, service-account tokens, and other machine credentials found in criminal stealer logs.
- **Secret Scan** — secrets exposed in public GitHub repositories.
- **LLM Credential Exposure (LLMjacking)** — exposed OpenAI/Anthropic/Google/Groq/xAI/Replicate API keys. **Free to try, no key required.**
- **Agent Risk Summary** — composite check combining breach, LLM credential exposure, and tech-stack CVE into one call.
- **STIX Indicators** — RelayShield's IOC corpus as STIX 2.1 objects via TAXII (requires a TI subscription key).
- **Server Status** — lists available tools and confirms upstream connectivity. No key required.

## API key required per call

Each tool call takes your own RelayShield API key as an argument — this Space is a single shared server handling many remote MCP callers at once, so there's no per-caller "environment" to read a key from. Get one at [api.relayshield.net/developers](https://api.relayshield.net/developers) — self-serve, pay-as-you-go, no monthly minimum. `check_llm_credential_exposure` and `check_server_status` work with no key at all (shared demo quota on the former).

## Using this as an MCP tool

This Space is MCP-compatible — add it to your MCP client from [huggingface.co/settings/mcp](https://huggingface.co/settings/mcp), or connect directly to its MCP endpoint (`/gradio_api/mcp/sse`).

## Learn more

Full API docs and self-serve signup: [api.relayshield.net/developers](https://api.relayshield.net/developers)
