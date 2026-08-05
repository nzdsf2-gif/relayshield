---
title: "We Asked OpenAI's Maintainers First — Then Shipped the Agents SDK Integration"
subtitle: "RelayShield's agentic-security tools now cover CrewAI, LangChain, and the OpenAI Agents SDK — the last one built the way the maintainers actually asked for"
tags: openai, ai-agents, security, python, opensource
canonical: (fill in after Hashnode publish)
---

## The three-framework trilogy is done

Over the past two weeks we've been getting RelayShield's two agentic-security checks — MCP server registry risk and AI-agent-sourced credential breach detection — into the hands of developers building agents, not just people running our dashboard. Today the third and final piece lands: **[`openai-agents-relayshield`](https://github.com/nzdsf2-gif/openai-agents-relayshield)**, live on PyPI right now.

That completes the set: [CrewAI](https://github.com/crewAIInc/crewAI/pull/6550), [LangChain](https://github.com/nzdsf2-gif/langchain-relayshield), and now the OpenAI Agents SDK — the three frameworks most people are actually building agents on top of today.

```bash
pip install openai-agents-relayshield
```

## What's in it

Two tools, plus something more interesting than a tool.

```python
from agents import Agent, Runner
from openai_agents_relayshield import check_mcp_server_risk, check_prompt_injection_breach

agent = Agent(
    name="Assistant",
    tools=[check_mcp_server_risk, check_prompt_injection_breach],
)
```

- **`check_mcp_server_risk`** — flags known-malicious IOC matches, typosquat domains, and newly-registered domains hosting an MCP server, before your agent connects to or installs it.
- **`check_prompt_injection_breach`** — checks whether an email shows up in our stolen-session corpus with a suspected-agentic-source marker: a credential exposure that looks like it came from a compromised or hijacked AI agent, not a conventional phishing path.

Both take `api_key` as a call argument, not an environment variable — the same multi-tenant-safe pattern across all three integrations, because a shared agent process shouldn't have one hardcoded key for every caller it serves.

## The part that's actually new: a real pre-execution gate

An advisory tool only helps if the model decides to call it. We also shipped `relayshield_mcp_gate`, built on the SDK's `@tool_input_guardrail` hook — a mechanism that runs *before* a tool executes and can block the call outright, not just advise against it:

```python
from openai_agents_relayshield.guardrail import relayshield_mcp_gate

connect_mcp_server.tool_input_guardrails = [relayshield_mcp_gate]
```

This is architecturally different from what we built for LangChain, and worth calling out because it's a genuinely different design, not a rename. LangChain's version is agent-level middleware that intercepts tool calls by matching names against a protected set. The OpenAI Agents SDK does it per-tool instead — you attach the guardrail directly to the specific tool you want gated, and the SDK handles the scoping. Neither is strictly better; they're different answers to the same problem from two different framework philosophies, and we ported the same normalized policy logic (allow / review / deny / defer, with a hook exception always defaulting to defer, never silently to allow) to fit each one natively rather than forcing one shape onto both.

## Why there's no PR into the SDK itself

Before writing a line of code, we checked whether a `libs/partners`-style contribution or an in-tree example was actually the expected path here — the way it (sometimes) is for other frameworks. It isn't. We found [a maintainer's actual answer](https://github.com/openai/openai-agents-python/issues/3457) to almost this exact question, asked by someone else a few months back: *"Please share the examples within your own repo for now."* Four minutes to respond, no ambiguity.

So that's what this is — an independently maintained, independently published package, which turns out to be exactly what the maintainers want from third parties, not a fallback we settled for after being turned away. If you're building something similar for this SDK, save yourself the PR: this is apparently the way.

## Try it

```bash
pip install openai-agents-relayshield
```

Get a RelayShield API key at [api.relayshield.net/developers](https://api.relayshield.net/developers). Source, tests, and the full gate design writeup: [github.com/nzdsf2-gif/openai-agents-relayshield](https://github.com/nzdsf2-gif/openai-agents-relayshield).
