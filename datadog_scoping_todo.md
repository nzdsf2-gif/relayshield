# Datadog: scoping item, GATED on the XSOAR demo shipping

**Added 2026-08-11 at the founder's direction.** Not to be started before the XSOAR demo is
delivered (promised Friday 21 August).

## The single question to answer

**Is listing RelayShield as an action in Datadog's Bits Agent Builder a directory submission or a
maintained integration?**

- **Directory submission**, the LangChain shape: worth an hour. Installs drive placement, the
  listing is the product, and there is no ongoing surface to keep alive. Do it.
- **Maintained integration**, the Splunk/XSOAR shape: a quarter's commitment including review
  cycles, version compatibility and support. Answer is no, and record why so it is not re-raised.

Nothing else about Datadog needs deciding until that is known.

## What is actually there

- **Bits AI Agents** ships an Agent Builder with 2,000+ prebuilt actions across cloud, security,
  CI/CD and collaboration tools. Third-party data sources are explicitly in scope.
- There is an **AI Agent Directory** as a discovery surface.
- Datadog's MCP Apps integration surfaces Datadog telemetry inside Claude, Cursor and Codex. That
  is the reverse direction from us and is **not** the opportunity.
- Their Agent Observability SDK integrates OpenAI, LangChain, Bedrock and Anthropic. Also not the
  opportunity: that is for people instrumenting agents, not for tool providers.

The one to scope is the Bits Agent Builder action catalog. It is the same shape as
`project_langchain_integration_listing`.

## The case against, recorded so the scoping starts honest

1. **Order.** The recorded platform integration order is Sentinel, OpenCTI, Splunk, XSOAR,
   Databricks. Datadog is not on it, and XSOAR is a live commitment with an unresolved blocker.
2. **Buyer mismatch.** Datadog's user is an SRE or platform team. Our buyer is a security lead with
   threat-intel budget. An integration that reaches the wrong seat generates installs without
   pipeline, which is the exact failure mode of the listings we already have.
3. **The constraint is channel sales**, founder-stated. A tenth integration does not touch it.

None of that is a reason to skip the hour if it turns out to be an hour. It is a reason not to
spend a quarter.

## Sources

- https://www.datadoghq.com/product/ai/bits-ai-agents/
- https://www.datadoghq.com/product/ai/agent-directory/
