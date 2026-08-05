# You Asked, We Shipped: 5 New Agent Security Tools, Structured Results, and Two Bugs We Found Along the Way

When we [published the first four `smolagents.Tool` classes](https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools) for the RelayShield Agentic Attack Surface, we closed with a question: *if there's a fifth tool that would actually get used in your agent pipelines, we'd like to hear which one.*

Two developers answered in detail. This post is what we built in response.

## What we heard

**Mason Reed** commented that self-checking agents are only going to matter more as MCP and external tools spread, and specifically flagged supply-chain risk, exposed secrets/tokens, and dependency vulnerabilities as the next things worth wrapping — with a strong note that results need to stay *explainable*: why something is risky, and what to do about it.

A second, more detailed comment made a sharper structural point. The suggestion: start with `oauth-watchlist` since it already has a public contract via our `relayshield-mcp` package; group `oauth-watchlist`, `nhi-exposure`, and `session-risk` together as one "agent authority / credential exposure" family rather than three unrelated tools, because the real question they answer together is *can someone else exercise the authority this agent currently holds?*; and — most usefully — a concrete critique that a tool an agent *may* call isn't the same control as a gate the system *must* pass, plus a proposed typed result contract so a caller can tell "nothing found" apart from "the check failed."

That comment also included something we hadn't asked for: a small integration-contract test against our public `relayshield-mcp` package, using synthetic upstream failures (401, 429, 500, malformed responses). It found that non-2xx errors were being returned as if they were successful results — a real bug, not a detection-accuracy critique.

## What shipped

**Five new tools**, taking the set from 4 to 9, live now on [the Space](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface), in `relayshield_smolagents_tool.py`, and in `relayshield-mcp` v0.2.7 (Claude Desktop / Claude Code / PyPI):

- **`oauth_watchlist`** — OAuth-connected-app breach exposure plus stolen OAuth/session tokens
- **`nhi_exposure`** — non-human-identity credentials (API keys, service tokens, PATs) found in stealer logs
- **`session_risk`** — active or reusable stolen session material that can bypass MFA entirely
- **`supply_chain`** — up to 10 vendor domains checked for breach/infostealer exposure
- **`secret_scan`** — secrets exposed in public GitHub repositories

`oauth_watchlist`, `nhi_exposure`, and `session_risk` are documented together as one family, per the framing above — the question they collectively answer is agent authority, not just login exposure.

**Every tool now returns a typed structured result** instead of a formatted string:

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

We used `no_known_finding` deliberately, not `safe` — a threat-intel lookup can report that it found nothing in the sources and scope it actually queried, which is not the same claim as "this is safe." That distinction was the point of the original feedback, so we kept the exact word.

## Also fixed while we were in there

Two bugs, both found by actually reading the code rather than assuming it worked:

- **`tech_stack_cve` was silently broken.** The shipped tool read a JSON key (`matched_cves`) that the API has never returned — the real keys are `all_matches`/`critical_cves`. It's been reporting "no CVEs found" regardless of the actual result since it shipped. Fixed.
- **`relayshield-mcp`'s error handling matched the bug report exactly.** We reproduced all of the synthetic failure cases from the comment above (401, 429, 500, a 200 with `ok: false`, a malformed body) directly against the real MCP SDK, confirmed each one was returning `isError: false`, and fixed the handler to return an explicit `CallToolResult` with `isError: true` for every one of them. Also caught two smaller things nearby: a stale price on `oauth_watchlist` ($0.15 shown, $0.30 actual) and a dead link in the setup docs.

## What's still open

The advisory-tool-vs-mandatory-gate distinction from the second comment is a good idea we haven't built yet: a second reference pattern where a high-impact action is blocked behind a required check rather than just available for an agent to call if it chooses to. That's a different kind of integration than a `Tool` — closer to a host-side hook — and we'd rather scope it properly than bolt it on. If you'd use that pattern, tell us where.

## Try it

- Space: [relayshieldadmin/relayshield-agentic-attack-surface](https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface)
- `pip install relayshield-mcp` (v0.2.7) — [PyPI](https://pypi.org/project/relayshield-mcp/0.2.7/)
- Get a key: [api.relayshield.net/developers](https://api.relayshield.net/developers?source=hf-smolagents)

— RelayShield
