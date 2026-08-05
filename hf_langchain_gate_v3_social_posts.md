Canonical post: HF blog (`huggingface.co/blog/relayshieldadmin/langchain-mcp-security-gate`), same as v1/v2 —
publish there first, then Hashnode/Medium cross-post back to it. See `hf_blog_post_v3_hashnode_crosspost.md`
for the full publish order and settings. (HF Discuss only has the separate, currently-frozen reply to
John6666 — not a distribution channel for the full post.)

Content below is simplified from the full post for readers who don't have the smolagents/HF-thread
backstory — drops the ten-state policy table and the John6666-attribution narrative, keeps the concrete
technical claim (mandatory gate vs. optional tool) and the proof points (public repo, 12 passing tests,
a real upstream gap found and filed).

---

## LinkedIn

Most "AI agent security" tools today are optional — the agent *can* call a safety check, but nothing
stops it from skipping that call and taking the risky action anyway.

We built the other kind: a gate the agent's framework enforces *before* a risky action can happen at
all, not a tool it's free to ignore.

Reference implementation, built on LangChain's `wrap_tool_call` middleware:
→ Every attempt to connect to or install an unfamiliar MCP server gets checked first
→ If the check fails, times out, or errors — the connection is blocked or deferred, never silently allowed
→ 12 test cases (known-risk, clean, stale data, auth failures, timeouts, malformed responses, and more) verified against the real LangChain/LangGraph packages, not mocks of our own code

Along the way we also found a real gap in a different agent framework (smolagents) — no equivalent hook exists there yet — and filed it upstream rather than working around it silently.

Code + tests: https://github.com/nzdsf2-gif/relayshield-langchain-gate
Get a key: https://api.relayshield.net/developers

#AIagents #AgentSecurity #MCP #LangChain #CyberSecurity

---

## Telegram

🛡️ New: a mandatory security gate for AI agents, not just an optional check.

Built on LangChain's `wrap_tool_call` middleware — blocks an agent from connecting to an unfamiliar MCP server unless a security check clears first. Fails closed (never silently allows on error), 12 passing tests against the real framework.

Also found and reported a real gap in another agent framework (smolagents) that doesn't support this kind of check yet.

Repo: https://github.com/nzdsf2-gif/relayshield-langchain-gate

---

## Farcaster (post to /security, /ai, /relayshield)

Shipped: a LangChain reference implementation that makes an MCP-server security check *mandatory* before an agent can connect — not a tool the agent can just skip.

Fails closed on error, 12 tests passing against the real framework, plus a real gap found + filed in smolagents (no equivalent hook there yet).

https://github.com/nzdsf2-gif/relayshield-langchain-gate

---

## Mastodon (infosec.exchange)

Reference implementation: a #LangChain middleware that gates AI agents from connecting to unfamiliar MCP servers behind a *mandatory* security check — not an optional tool call the agent is free to skip.

Fails closed by design (a hook error defers, never silently allows), bounded retry only on genuine upstream failures, 12-case acceptance suite passing against the real `langchain`/`langgraph` packages (not mocks of our own logic).

Also found a real gap while building this: @huggingface's smolagents has no pre-execution hook today — filed as a feature request rather than a workaround.

https://github.com/nzdsf2-gif/relayshield-langchain-gate

#InfoSec #MCP #AgentSecurity #AIsecurity

---

## Medium (full cross-post, not a teaser)

Use **"Import a story"** with the **HF blog URL** as the source — do not paste. Medium has zero
Markdown-paste support (worse than Hashnode's), and Import auto-sets the canonical link back to
the source in the same step (per `feedback_medium_import_not_paste.md`).

- **Canonical URL**: auto-set by Import to the HF blog URL — verify it landed correctly in Story
  settings → Advanced settings, don't need to set it by hand
- **Tags** (Medium caps at 5): `AI`, `Cybersecurity`, `MCP`, `LangChain`, `AI Agents`
- **Subtitle**: `A LangChain reference implementation that makes MCP-server security checks mandatory, not optional — with tests against the real framework and a real gap found and filed upstream.`

---

## Not included

X/Twitter — deliberately excluded, standing call per suspension history.
