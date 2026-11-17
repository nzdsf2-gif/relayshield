# A Stolen API Key, Unredacted Traces, and a Trojanized Extension

**Draft for Wednesday, November 18, 2026. For Andrew's review.**
**Status: draft only, not published. Do not publish without Andrew's go.**

---

A single stolen API key set off a chain that ended with a trojanized
extension on Cursor's marketplace. The key itself was not the end of
the story. The damage came from what the key exposed: unredacted
credentials sitting in coding-agent traces, waiting to be harvested.

Cursor traced the trojanized Claude Code extension to a stolen
Fireworks AI access key. That key exposed unredacted credentials in
coding-agent traces. Attackers used one of those credentials on
October 29 to plant backdoored builds of the extension, versions
2.1.312 and 2.1.313, on Cursor's extension marketplace. Up to 5,000
users may have received the trojanized builds. They were available
for about 11 hours before removal.

Read that sequence again, because it is the shape of a whole class
of agent-security failures.

1. A key is stolen.
2. The key gives access to agent traces.
3. The traces contain other credentials, in plain text.
4. An attacker harvests one of those credentials.
5. The harvested credential is used to plant malware where users
   will install it.

The initial theft is hard to prevent entirely. The second step is
where the damage multiplies, and it is preventable. The credentials
in the traces did not have to be there in plain text.

## Your agent's traces are a credential leak

Coding agents generate traces. Every tool call, every tool result,
every intermediate step is recorded so the developer can debug what
the agent did. Those traces are useful. They are also a record of
everything the agent touched, including secrets.

When an agent calls a tool with an API key as a parameter, that key
lands in the trace. When a tool returns a result containing a
credential, that credential lands in the trace. When an agent reads
a config file, a log file, or an environment dump, the secrets in
those files land in the trace. The trace becomes a credential
store, and it is stored with far less protection than a vault.

This is not a hypothetical risk. The Fireworks incident is a
concrete example. A stolen key exposed credentials in traces, and
one of those credentials was used to compromise a software supply
chain. The blast radius of a single stolen key grew because the
traces were unredacted.

The lesson is not to stop logging. The lesson is to redact secrets
before they reach the log.

## Redact at the proxy, before the trace

RelayShield's MCP Proxy Firewall now redacts PII and secrets from
AI agent traffic in both directions. Every tool call going out and
every tool result coming back is screened. When a tool call or a
tool result contains an API key, a secret, an email address, a phone
number, a Social Security number, a credit card number, or a crypto
wallet address, the proxy replaces the sensitive value with a
redaction token and lets the call continue. The raw value never
reaches the agent, and it never reaches the audit log.

The Fireworks key is an API key. API key and secret is one of the
types the redaction covers. If the coding agent was routing its MCP
tool calls through the RelayShield proxy, and the Fireworks key
appeared in a tool call or a tool result, the proxy would have
replaced it with a redaction token before it reached the trace.
The credential would not have been sitting in plain text for an
attacker to harvest.

This is not a claim that redaction would have prevented the initial
theft of the Fireworks key. It would not have. What redaction
prevents is the second step: the exposure of credentials in traces
that turns one stolen key into a supply-chain compromise.

Redaction is opt-in per tenant, off by default, and included in
existing licenses at no extra charge. Enable it per PII type in the
console Policies tab, or contact support to enable it for your
tenant.

## What to check now

The Fireworks incident is a reason to audit what your agents are
logging.

- Check what credentials have been pasted into agent sessions.
  Rotate any key that appeared in a trace, a log, or a shared
  session.
- Check which keys are still live. Revoke keys that are no longer
  needed, and rotate keys that may have been exposed.
- Check whether your agent traces redact secrets. If they do not,
  assume any secret the agent touched is in a log somewhere.

The trojanized extension was live for about 11 hours. The
credentials in the traces were there longer. The time to redact
is before the leak, not after.

---

**Sources:** Cursor's tracing of the trojanized Claude Code extension,
as reported by The Hacker News, November 15, 2026. Trojanized
versions 2.1.312 and 2.1.313. Up to 5,000 users may have received
the builds. Available about 11 hours before removal.

**About RelayShield:** RelayShield screens AI agents at the tool
call against a live threat-intelligence corpus of 144 monitored
Telegram marketplaces, 800K+ indicators, and 10.9M citations.
The Hosted MCP Proxy Firewall is a dedicated proxy per client org.
Learn more at https://relayshield.net and
https://api.relayshield.net/developers.
