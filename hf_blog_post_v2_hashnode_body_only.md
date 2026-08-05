# You Asked, We Shipped: 5 New Agent Security Tools, Structured Results, and Two Bugs We Found Along the Way

When we [published the first four `smolagents.Tool` classes](https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools) for the RelayShield Agentic Attack Surface, we closed with a question: *if there's a fifth tool that would actually get used in your agent pipelines, we'd like to hear which one.*

A couple of developers answered in detail. This post is what we built in response.

## What we heard

One commenter mentioned that self-checking agents are only going to matter more as MCP and external tools spread, and specifically flagged supply-chain risk, exposed secrets/tokens, and dependency vulnerabilities as the next things worth wrapping — with a strong suggestion that results need to stay *explainable*. Why is something risky, and what should be done about it.

A second, more detailed comment made a sharper structural point: start with `oauth-watchlist` since it already has a public contract via our `relayshield-mcp` package. Then group `oauth-watchlist`, `nhi-exposure`, and `session-risk` together as one "agent authority / credential exposure" family rather than three unrelated tools, because the real question they answer together is *can someone else exercise the authority this agent currently holds?* Additionally, a tool an agent *may* call isn't the same control as a gate the system *must* pass, plus a proposed typed result contract so a caller can tell "nothing found" apart from "the check failed."

That comment also included something we hadn't tried yet: a small integration-contract test against our public `relayshield-mcp` package, using synthetic upstream failures (401, 429, 500, malformed responses). It found that non-2xx errors were being returned as if they were successful results — a real bug, not a detection-accuracy critique.

## What shipped

**Five new tools:** extends our set from 4 to 9, live now on [the Space](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface), in `relayshield_smolagents_tool.py`, and in `relayshield-mcp` v0.2.7 (Claude Desktop / Claude Code / PyPI):

- **`oauth_watchlist`**: OAuth-connected-app breach exposure plus stolen OAuth/session tokens
- **`nhi_exposure`**: Non-human-identity credentials (API keys, service tokens, PATs) found in stealer logs
- **`session_risk`**: Active or reusable stolen session material that can bypass MFA entirely
- **`supply_chain`**: Up to 10 vendor domains checked for breach/infostealer exposure
- **`secret_scan`**: Secrets exposed in public GitHub repositories

`oauth_watchlist`, `nhi_exposure`, and `session_risk` are documented together as one family, and per the above framing, the question they collectively answer is agent authority, not just login exposure.

Every tool now returns a typed structured result instead of a formatted string:

```json
{
  "outcome": "finding | no_known_finding | error",
  "recommended_action": "allow | review | deny | defer",
  "reason_codes": ["..."],
  "evidence": ["..."],
  "coverage": {"complete": true, "scope": "what was actually checked"},
  "freshness": {"observed_at": "...", "expires_at": null},
  "error": {"kind": "...", "message": "...", "retryable": false} | null
}
```

We used `no_known_finding` deliberately, not `safe`, since a threat-intel lookup can report that it found nothing in the sources and scope it actually queried, which is not the same claim as "this is safe." That distinction was the point of the original feedback, so we kept the exact wording.

## Also fixed while we were in there

`relayshield-mcp`'s error handling matched the bug report exactly. We reproduced all of the synthetic failure cases from the comment above (401, 429, 500, a 200 with `ok: false`, a malformed body) directly against the real MCP SDK, confirmed each one was returning `isError: false`, and fixed the handler to return an explicit `CallToolResult` with `isError: true` for every one of them.

## What's still open

The advisory-tool-vs-mandatory-gate distinction from the second comment is a good idea we haven't built yet. It consists of a second reference pattern where a high-impact action is blocked behind a required check rather than just available for an agent to call if it chooses to. That's a different kind of integration than a `Tool`. It's closer to a host-side hook, and as such we intend to separately scope it. If you would like to see that pattern, we welcome your feedback on your intended use cases.

## Try it

- Space: [relayshieldadmin/relayshield-agentic-attack-surface](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface)
- `pip install relayshield-mcp` (v0.2.7) — [PyPI](https://pypi.org/project/relayshield-mcp/0.2.7/)
- Get a key: [api.relayshield.net/developers](https://api.relayshield.net/developers)

— RelayShield
