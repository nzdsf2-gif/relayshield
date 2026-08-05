# From Advisory Tool to Mandatory Gate: A LangChain Reference Implementation

Our [last post](https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2) closed with an open question: a commenter had made the point that a `Tool` an agent *may* call isn't the same control as a gate the system *must* pass before a high-impact action, and we said we hadn't built that pattern yet. This post is what we built in response.

## The distinction, restated precisely

**John6666**, the commenter who raised this, followed up with something more complete than we expected: a full normalized policy — ten states (`finding`, `no_known_finding`, `unknown`, `partial`, `stale`, `auth_failure`, `upstream_failure`, `malformed`, `payment_required`, `missing`), each mapped to a gate action (`allow`, `review`, `deny`, `defer`) — plus a worked example of why the distinction matters:

> No matching intelligence was found in a fresh, defined search scope. The available sources covered only part of the target. The result is older than the policy permits. The request failed before a result was obtained. Only the first is a candidate for `no_known_finding`. The others are variations of insufficient knowledge or failed execution.

That's not a minor taxonomy point. Collapsing those into one "clean" bucket is exactly the failure mode that makes an advisory tool unsafe to promote into a mandatory boundary — the downstream question stops being "what should I tell the user?" and becomes "may this external action proceed?"

## What we built

We built the reference against **LangChain's `wrap_tool_call` middleware** — a real, shipped, pre-execution hook: inspect the tool call, decide, and only then invoke (or refuse to invoke) the handler.

The gate protects one concrete action: connecting to or installing an unfamiliar MCP server, checked against RelayShield's `mcp-registry-risk` endpoint.

```python
class RelayShieldMCPGateMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        if request.tool_call["name"] not in PROTECTED_TOOLS:
            return handler(request)

        state, result, err = check_mcp_registry_risk_with_retry(**target)
        decision = evaluate_gate_policy(state, result)
        record_gate_decision(target, decision)

        if decision.action == GateAction.ALLOW:
            return handler(request)
        return _deny_message(tool_call, decision)  # protected action does not occur
```

A few properties we treated as non-negotiable, all from the original proposal:

- **A hook exception defaults to `defer`, never silently to `allow`.** Failing open would defeat the point of a mandatory gate.
- **Bounded retry applies only to `upstream_failure`** (timeout/429/5xx) — auth failures, malformed responses, and payment-required states are terminal after one attempt, not retried indefinitely.
- **The audit log records decision, reason codes, check version, target, and timestamp — never keys, payment proofs, or session material.**
- **The raw connect/install tool is never bound to the model directly.** There's no "the model calls a lower-level connector to bypass the gate" scenario to defend against after the fact, because that tool doesn't exist in the model's toolset in the first place — the only exposed path already goes through the gate.

## Testing the boundary, not the label

The proposal included something we found unusually useful: a **protected-action acceptance suite** — asserting on whether the handler actually ran, not just on what label came back. We built exactly that: 12 cases (known-risk server, benign/fresh, `no_known_finding` with partial coverage, stale, 401, 429, 500, malformed response, network disconnect, 402 payment-required, an internal gate exception, and an unrelated tool passing through untouched), all passing against the real `langchain`/`langgraph` packages — only the RelayShield HTTP call is mocked per fixture, not any framework internals.

Code, tests, and a full README: [relayshield-langchain-gate](https://github.com/nzdsf2-gif/relayshield-langchain-gate).

## What's still open

`payment_required` (HTTP 402) is handled as "deferred pending negotiation," per the original proposal's framing — not denied, since payment-required isn't a completed security check either. The reference implementation currently defers and stops there; wiring an actual x402 negotiation-and-recheck loop inline is the next piece, not yet built. OAuth/vendor-grant gating with explicit identity/app/scope bindings is the next gate pattern in line, sequenced after this one.

## Try it

- Gate reference + tests: [nzdsf2-gif/relayshield-langchain-gate](https://github.com/nzdsf2-gif/relayshield-langchain-gate)
- Get a key: [api.relayshield.net/developers](https://api.relayshield.net/developers?source=hf-smolagents)

— RelayShield
