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
