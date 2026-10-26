Connecting
Point your MCP client at: https://api.relayshield.net/mcp

This is a remote MCP server over HTTPS using the Streamable HTTP transport. Use an MCP client that supports that transport.

No account-level secret is required to connect. Each tool call takes your RelayShield API key as a parameter, so you are only billed for the calls you make.

Tools
check_mcp_server_risk: checks an MCP server URL for typosquat risk and for presence in RelayShield's criminal IOC corpus. Returns CRITICAL, HIGH, MEDIUM or LOW with findings. Params: server_url, api_key

check_prompt_injection_breach: checks an email for credential exposure sourced specifically from prompt-injection attacks against AI agents, distinct from ordinary phishing or malware breaches. Params: email, api_key

check_tech_stack_cve: checks a declared AI agent framework or tech stack for CISA KEV or high-EPSS CVEs currently being exploited. Params: tech_stack (comma-separated, for example "langchain, nacos, minio"), api_key

check_bulk_identity_risk: hierarchical org and AI-agent-identity risk scoring for a domain and up to 5 agent or service-account identities. A critically exposed agent elevates the org's overall rating. Params: domain, agent_emails (comma-separated, up to 5), api_key

check_llm_credential_exposure: checks a domain for exposed LLM and AI provider API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate) in criminal stealer logs, where a leaked key becomes a live, uncapped billing liability. Params: domain, api_key

check_server_status: lists the tools on this server and confirms connectivity. No API key required.

How scores are produced
Every score is computed from RelayShield's own continuously collected corpus. Queries are not forwarded to outside data providers, and each response names any signal it did not run, so a missing signal is never mistaken for a clean result.

Getting an API key
Your API key is generated automatically and emailed to you when your AWS Marketplace subscription activates. No separate signup step is required.