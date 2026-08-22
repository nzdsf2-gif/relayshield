DRAFT — NOT POSTED. For founder review before opening on
https://github.com/huggingface/smolagents/issues

Proposed title:
Feature request: a supported pre-execution tool-call hook (no equivalent to
CrewAI's before_tool_call / LangChain's wrap_tool_call today)

---

**Summary**

`smolagents` has `step_callbacks`, but they fire on `ActionStep` *after* the
tool has already executed (`agents.py`, `_setup_step_callbacks` /
`self.step_callbacks.callback(memory_step, agent=self)` called post-hoc).
`execute_tool_call()` invokes the tool directly with no interception point
before execution.

This means there is currently no supported way to build a mandatory,
pre-execution policy gate in front of a specific tool call (e.g. "block this
connection/install until a security check completes") — only post-hoc
observation of what already happened.

**Why this matters**

Other agent frameworks expose exactly this as a first-class extension point:

- CrewAI: `before_tool_call` hook (`crewai.hooks.register_before_tool_call_hook`),
  receives tool/input/agent/task/crew context, returns `False` to abort
  execution before it runs.
- LangChain: `wrap_tool_call` middleware (`AgentMiddleware.wrap_tool_call`),
  receives a `ToolCallRequest` and a `handler` callable — the middleware
  decides whether to invoke the handler at all.

Both let a host application enforce a policy boundary — not just observe,
but block — before a tool with real-world side effects (installing a
package, connecting to an external server, sending credentials) runs.

Today, the only way to approximate this in smolagents is to subclass
`MultiStepAgent` and override `execute_tool_call()` directly. That works,
but it's an override of an internal method, not a documented extension
point — it's fragile across smolagents versions and isn't something a
security-sensitive host application should have to rely on.

**Proposed shape** (not prescriptive — happy to discuss the right form for
this codebase)

A callback registry analogous to `step_callbacks`, but invoked *before*
`execute_tool_call` actually calls the tool, with the ability to short-circuit:

```python
def my_gate(tool_name: str, arguments: dict, agent) -> bool:
    # return False to block execution
    ...

agent = CodeAgent(..., before_tool_call_hooks=[my_gate])
```

**Context**

This came up concretely while working through a mandatory-gate design with
a commenter (John6666) on RelayShield's smolagents-agent-security-tools-v2
release — the intended reference implementation was "block connecting to an
unfamiliar MCP server until a registry-risk check completes," and smolagents
was the natural first place to demonstrate it, since that's the library the
whole conversation is about. We ended up building the reference against
CrewAI/LangChain instead, since both already support this pattern natively.
Happy to help scope or contribute an implementation if there's interest.


---
---

# Reply to kantorcodes (#2557), 2026-08-22 — RECOMMENDED ACTION

## Decision: reply now, build only on a maintainer signal

**Do not open a PR yet. Do reply today.**

### Why not build it yet

The issue already says "if maintainers are open to this direction, we're happy to contribute", and
**no maintainer has answered.** Writing an interception point into `execute_tool_call()` before that
signal is speculative work on someone else's core loop — a much riskier bet than the Rapid7 plugin,
which went into a repo with an explicit open-contribution model and a documented plugin toolkit.
smolagents has neither for core agent internals.

### Why replying now matters more than the code would

**A second, independent consumer is the single most valuable thing that can happen to a feature
request, and it just happened.** HOL Guard has the same pre-execution requirement, arrived at
independently, and describes a contract that is **identical to ours**: resolved tool name plus
validated arguments, delivered immediately before `execute_tool_call()`, with a deny short-circuiting
to zero downstream execution.

That turns this from "one vendor wants a hook for their product" into "this is a category
requirement with two implementations waiting." Confirming the contract match publicly is what
converts it. Silence wastes the strongest moment the thread will have.

### Why we want this specifically

`relayshield_langchain_gate.py` is built on LangChain's `wrap_tool_call`. The smolagents equivalent
**cannot be built properly without this hook** — the only alternative is overriding an internal
method, which is exactly what a security gate must not depend on. So this is not a nice-to-have: it
gates a product that already exists on another framework and already has published launch material.

### Endorse their test explicitly — it is better than ours

Their proposed assertion is *"a denied hook leaves the target tool invocation count at zero while
allow executes exactly once, including MCP-imported tools."*

**The MCP clause is the important half and we should say so.** MCP-imported tools are the most likely
path for a gate to be silently bypassed, because they are registered through a different code path
from natively-defined ones. A gate that holds for native tools and leaks on MCP tools is worse than
no gate — it produces confident false assurance. That is the same failure class as a secret scanner
returning a false all-clear.

---

## Draft reply — post as-is

> Author of the issue here. Confirming the contract you describe is the same one we need, arrived at
> independently — resolved tool name plus validated arguments, delivered immediately before
> `execute_tool_call()`, with a deny short-circuiting to zero downstream execution. Provider-neutral
> is right, and we'd also keep our gate separately maintained rather than adding a framework
> dependency in either direction.
>
> Two things worth adding from our side.
>
> **The MCP clause in your test is the one that matters most.** MCP-imported tools register through a
> different path from natively-defined ones, so a hook that holds for native tools and leaks on MCP
> tools is worse than no hook — it gives confident false assurance to exactly the person who checked.
> Asserting both in the same test is the right call.
>
> **We have a concrete use waiting.** We maintain a policy gate on LangChain built on
> `wrap_tool_call`; the smolagents equivalent isn't buildable today without this, because subclassing
> and overriding `execute_tool_call()` is an internal-method override and a security boundary can't
> rest on one.
>
> @maintainers — with two independent consumers and both of us offering to do the work, is this a
> direction you'd accept a PR for? Happy to split it: hook contract and tests, or a docs example,
> whichever placement suits smolagents. If the shape is the concern rather than the feature, we'd
> rather agree the signature in this thread first than send a PR you have to redesign.

## If a maintainer says yes

Scope it small and take the half nobody wants: **the tests, including the MCP case.** A feature
request with a passing test suite attached is far more likely to land than one with an
implementation, and it is the piece most likely to be skipped. HOL Guard has offered the hook
contract; the two halves fit together without either party depending on the other.

## If the thread goes quiet for two weeks

Do not chase it. The override path works today and is what our own gate would ship on in the
meantime — documented as an override with the risk stated, not presented as a supported extension
point.
