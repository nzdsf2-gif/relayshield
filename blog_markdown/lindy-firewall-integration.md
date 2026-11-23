# Your Lindy agent moves real tools. Put a Firewall in front of it.

Date: 2026-11-23

Your Lindy agent talks to MCP servers. Every tool call it makes is a real action: it checks a link, looks up a wallet, reads an email, or moves money. Until now, nothing stood between your agent and the server it called. The RelayShield MCP Proxy Firewall changes that. It sits in front of your MCP servers and screens every tool call before it reaches them.

We proved it live. A Lindy agent connected to the Firewall URL, asked it to check a link, and got the verdict back. The screened call is in the proxy audit log: tool check_link, decision allow, risk score 0.0, screened call true. The full loop works. Lindy agent to Firewall to check to verdict to agent reply. The link we checked was google.com, a known clean site, so a risk score of 0.0 and an allow decision are the expected result for that site. A clean verdict on a clean site does not mean the Firewall is permissive; it means this site carries no flags.

Connect your Lindy agent to the Firewall, and you get two things at once: the free scam checks and the enforcement. One URL, the checks plus the enforcement.

## The idea

The Firewall fronts the free RelayShield scam-checks server. Connect your Lindy agent to the Firewall URL as its MCP server, and the tools that arrive are the upstream checks: check_link, check_wallet, check_email, and any other MCP server your Firewall fronts. The difference is the gate. The free server is advice: the agent calls a check and reads a verdict. The Firewall is enforcement: the screen runs at the gate, the agent cannot skip it, and every call is logged.

For a small team whose Lindy agent touches real tools and real money, enforcement is the point.

## What you need

You need a provisioned RelayShield Firewall tenant. Your Firewall MCP URL is https://&lt;tenant-id&gt;.proxy.relayshield.net/mcp, and your proxy token is in Secrets Manager at relayshield/hosted/&lt;tenant-id&gt; (a JSON object, proxy_token key) and in the welcome email.

You also need a Lindy account. Lindy accepts any hosted MCP server, so there is no listing to find and no approval queue.

## Connect it

1. In Lindy, go to Integrations, then + Add, then MCP.
2. Paste your Firewall MCP URL as the server URL: https://&lt;tenant-id&gt;.proxy.relayshield.net/mcp. The /mcp path is the MCP endpoint.
3. Display name: "RelayShield Firewall".
4. Auth: the Firewall checks a proxy token. If Lindy asks for auth, use your proxy token as a Bearer token. If Lindy only offers an API key field, put the token there.
5. Connect. The tools should arrive enabled.

## Test it

Ask your Lindy agent to check a link. For example: "Check this link with RelayShield: https://google.com". It should call check_link through the Firewall, and the agent should report the verdict back.

Then verify the screened call in the proxy's own audit log. SSH to the tenant instance and run: curl -s 'http://localhost:8090/_rs/audit/export?format=json&limit=10'. Look for your check_link entry with screened_call true.

In our testing, the agent checked google.com and reported back: RelayShield did not flag it, the verdict was unknown, it is not in the threat-intelligence corpus, no threat feeds flagged it, and the domain age is about 29 years. RelayShield never reports a link as safe, only flagged or unknown, and the agent reported that correctly.

If the tools do not arrive, check the proxy token first. A wrong or expired token is the most likely cause. If a call is blocked and you did not expect it, check Policy 1 mode in the console. If Lindy fails to connect at all, check GET /mcp: curl the Firewall URL with your token. It should return a discovery JSON with transport streamable-http and mcp /mcp. Lindy verifies the server with a GET before it POSTs, so a 404 there fails the connection even when POST works.

## What it costs

$49 a month, 20,000 screened calls included, $0.002 per call over that. Self-serve through Stripe. Provisioning creates your tenant URL and token. The free scam checks come along as the upstream, so you are not paying extra for them.

## Why RelayShield MCP Proxy Firewall

The free server tells your agent what it found. The Firewall makes sure the check happens, every time, and keeps a record. If your agent only reads advice, it can skip the check. If it goes through the Firewall, it cannot. That is the difference between a check your agent may run and a gate your agent must pass. For an agent that touches real tools, the gate is what matters.
