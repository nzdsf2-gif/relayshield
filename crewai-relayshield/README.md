# crewai-relayshield

A pre-execution gate for [CrewAI](https://github.com/crewAIInc/crewAI). Before an
agent connects to an MCP server or installs a tool it found on its own,
RelayShield is asked about the target, and the call is refused if the answer is
bad.

```bash
pip install crewai-relayshield
```

```python
from crewai_relayshield import install

install()   # registers a before_tool_call hook with CrewAI
```

That is the whole integration. The hook fires only for tools that connect or
install something (`DEFAULT_PROTECTED_TOOLS`); pass `tools=[...]` to name your
own.

## What it does

`install()` registers a `before_tool_call` hook. When a protected tool is about
to run, the gate pulls the target out of the tool's arguments, calls
RelayShield's `mcp-registry-risk` check, and maps the answer to one of four
actions:

| Check said | Action | Tool call |
|---|---|---|
| a finding | `DENY` | blocked |
| nothing known against it | `ALLOW` | proceeds |
| unknown, or only partly checkable | `REVIEW` | blocked |
| the check itself failed | `DEFER` | blocked (see below) |

Returning `False` from a CrewAI before-hook aborts the call, which is what
blocking means here.

## Fail-closed by default, and why

Only `ALLOW` proceeds. A gate that lets the call through when the check fails is
not a gate: anyone who can cause a timeout or a 429 has removed it, and those
are cheap to cause.

That does couple your agent's availability to ours, which is a real cost and
your decision rather than ours:

```python
install(fail_open=True)
```

`fail_open` releases `DEFER` only, meaning a check that could not be
**completed**. A completed check that said `REVIEW` still blocks, and a
`FINDING` always blocks. There is no setting that lets a known-bad target
through.

## Without CrewAI

The decision path has no framework import, so you can use it behind any
pre-execution chokepoint, or test it on its own:

```python
from crewai_relayshield import decide

allowed, decision = decide({"server_url": "https://example.invalid/mcp"})
print(allowed, decision.action, decision.reason_codes)
```

## What it never claims

The check reports what is **known against** a target. "No known finding" is an
absence of evidence, not proof that something is safe, and this package does not
upgrade one into the other anywhere in its output.

## Configuration

| Env var | Meaning |
|---|---|
| `RELAYSHIELD_API_KEY` | subscription key; without it the API answers 402 and the gate defers |
| `RELAYSHIELD_API_URL` | override the API base (defaults to `https://api.relayshield.net`) |

Get a key, including a free tier:
<https://api.relayshield.net/developers?source=pypi>

## Licence

MIT.
