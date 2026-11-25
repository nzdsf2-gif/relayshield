# Your Gemini CLI agent can now sit behind the RelayShield Firewall

Date: 2026-11-25 (draft for Andrew's review, prepared 2026-11-24)
Status: Draft. Do not publish until Andrew approves. Based on the Gemini Firewall guide of 2026-11-21 and the live test of 2026-11-22.

## Draft

Agent payments stopped being a demo last week. On November 17, Google made Gemini Tasks free for hundreds of millions of people, and Gemini now pays through AP2 on Visa and Mastercard network tokens. The same week, ChatGPT Wallet launched with Proof x401. Agents are now spending real money at real checkouts, and the question is no longer whether an agent can pay. It is whether anything checks the payment before it goes through.

That check has two halves. AP2 proves the agent is authorized to spend. RelayShield proves the counterparty is legitimate. A signed AP2 mandate for a spoofed storefront is still a signed mandate, so the mandate alone does not make the payee safe. The Firewall is the enforcement for the second half: it screens every tool call at the gate, and the agent cannot skip it.

This post is a guide for connecting Gemini CLI to the RelayShield MCP Proxy Firewall, and it is honest about what was proved and what was not. The connection config is verified against the official Gemini CLI MCP docs. The Firewall path was proved live on November 22 against a real tenant: a direct check_link call through the tenant URL returned the verdict, and the Audit Trail shows the entry. The steps below are the ones to run, and the live test is the one already done.

One scope note first. Gemini Tasks users in the Gemini app cannot add an MCP server, so this guide is not for them. The audience is developers using Gemini CLI, and by the same config, ADK and Gemini Enterprise agents that accept a remote MCP server. That is a smaller audience than the hundreds of millions of Tasks consumers, and it is the audience that can actually connect today.

## The idea

Your Gemini CLI agent talks to MCP servers. The Firewall sits in front of them and screens every tool call. Connect Gemini CLI to the Firewall URL as its MCP server, and you get both at once: the free scam checks, because the Firewall fronts the free RelayShield scam-checks server, and the enforcement, because the Firewall screens every tool call before it reaches the server. One URL, the checks plus the enforcement. It is the same pattern as the Lindy guide, which is verified live.

If you do not have a Firewall tenant yet, start with the free route. The free scam-checks server is available as a Gemini CLI extension with no signup and no token. Start here when you want enforcement on top of the checks.

## Connect it

You need a provisioned RelayShield Firewall tenant. Your Firewall MCP URL is https://\<tenant-id\>.proxy.relayshield.net/mcp, and your proxy token is in Secrets Manager at relayshield/hosted/\<tenant-id\> (JSON, proxy_token key) and in the welcome email. The console does not show the token.

Gemini CLI connects to a remote MCP server over Streamable HTTP with the httpUrl key, and it accepts custom headers. Put the token in a .env file, not in settings.json, so it never lands in a shared config or a screenshot.

Step 1, save the token where Gemini CLI reads it:

```text
# ~/.gemini/.env
RS_PROXY_TOKEN=<your proxy token from Secrets Manager>
```

Step 2, add the Firewall as an MCP server:

```json
// ~/.gemini/settings.json
{
  "mcpServers": {
    "relayshield-firewall": {
      "httpUrl": "https://<tenant-id>.proxy.relayshield.net/mcp",
      "headers": {
        "Authorization": "Bearer ${RS_PROXY_TOKEN}"
      },
      "timeout": 30000
    }
  }
}
```

Replace \<tenant-id\> with your tenant id, and keep the /mcp path: it is the MCP endpoint. Restart Gemini CLI after changing settings.

There is a command-line alternative with the same result, `gemini mcp add --transport http`, but it puts the token in shell history, so the settings.json plus .env form is the better one.

Why settings.json and not a gallery extension: a Gemini CLI extension manifest is a static public file, and the Firewall URL and token are per tenant. There is no single public extension that can carry every tenant's token. The free scam-checks server, which needs no token, is the one that fits the extension route.

## Test it

Start Gemini CLI and list MCP servers with `/mcp list`. You should see relayshield-firewall as Ready, with the upstream tools listed (check_link, check_wallet, check_email, and any other tools your Firewall fronts).

Ask Gemini CLI to check a link, for example: "Check https://google.com with RelayShield." It should call check_link through the Firewall and return the verdict (unknown for google.com: not in the threat-intelligence corpus, no threat feeds flagged it).

Verify the screened call in the Audit Trail, which now pulls live proxy entries. Look for your check_link entry with the verdict attached. Then ask the agent to check a known-bad link. The Firewall should flag or block it according to your Policy 1 mode.

If the tools do not arrive, check the proxy token first: a wrong or expired token is the most likely cause. If a call is blocked and you did not expect it, check Policy 1 mode in the console. If Gemini CLI reports the server as not ready, confirm the URL ends in /mcp and the token expanded from the .env file.

## What it costs

The signature solution is the MCP Proxy Firewall plus Agent Verifiers license at $109 a month. It is the surface the AP2 verifier was developed for: the Firewall screens every tool call at the gate, and the verifiers prove the spend is authorized and the counterparty is legitimate. The extra $60 a month over the Firewall alone buys the TAP Verifier, PAP, Passport identity, intent binding, the settle check, and 100 free verifications a month, plus Threat corpus screening, on top of the Firewall's 20,000 screened calls included, $0.002 per call over that. Bought separately the Firewall is $49 a month and the Agent Verifiers Bundle is $79 a month, $128 together, so the $109 bundle saves $19. The $49 Firewall alone is the entry point: self-serve through Stripe, provisioning creates your tenant URL and token, and the free scam checks come along as the upstream, so you are not paying extra for them.

## The spend-authorization half

Screening the payee is one half. Proving the agent is authorized to spend is the other, and that half is now verified too. The RelayShield AP2 mandate verifier was verified live on November 23 against a real, independently minted v0.2 mandate from the official AP2 SDK: signature, checkout hash binding, scope, validity window, receipt matching, and replay protection all passed. The verifier is bundled into the Agent Verifiers bundle, so the Firewall screen and the mandate check are available together for a seller agent that buys supplies: the mandate proves the spend is authorized, the counterparty screen proves the payee is legitimate, and intent binding proves the call matches what the owner approved.

## What this does not do

It does not patch vulnerable MCP servers. The Firewall catches the attempt at the gate; upgrading the server is still the fix. It does not reach Gemini Tasks consumers in the Gemini app, who cannot add an MCP server. And it does not claim a Gemini CLI session has already run this end to end in front of a user: the path is proved through the live tenant test, and the in-session run is the next proof to add.

## Where to start

If you run a Gemini CLI agent that touches money, links, or wallets, put it behind the Firewall and see what it flags. The free extension gives you the checks with no signup. The Firewall adds the enforcement, the audit trail, and the policies that decide what gets through.

---

## Review notes (not for publication)

- Framing: developer-first, per Andrew's 2026-11-21 approval. Tasks consumers excluded, stated plainly.
- Honest claim: Firewall path proved 2026-11-22 via direct curl check_link through a live tenant plus the Audit Trail entry. Do NOT claim Gemini CLI invoked the tool in session; that run is still owed.
- AP2 verifier: verified live 2026-11-23 against a real, independently minted v0.2 mandate from the official AP2 SDK. Never call it Gemini-issued; a live Gemini-issued mandate is not capturable.
- Updated from the Nov 21 guide: the guide said the AP2 verifier needed a go and the console Audit Trail showed demo data. Both are now out of date: AP2 is verified live, and the Audit Trail pulls live proxy entries.
- Not claimed: fleet-wide GET /mcp fix. The fix is proved on the test tenant; the fleet deploy has not run. No fleet claim appears in this draft.
- Prices: $49 direct, 20,000 screened calls included, $0.002 per call over. Firewall figures only. The What it Costs section now leads with the $109/mo Firewall plus Agent Verifiers bundle (Andrew, 2026-11-24), which saves $19 against the $128 separate total.
- Zero em dashes in the draft body. Sources: ~/workspace/your_files/relayshield-gemini-firewall-guide-2026-11-21.md; Gemini CLI MCP docs https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html; Google Tasks announcement Nov 17, 2026 https://blog.google/innovation-and-ai/products/gemini-app/tasks-in-gemini-free-new-features/
- Publish path, same as the Lindy and CB posts: blog.relayshield.net, then Threads, Hugging Face, and Dev.to (Google SSO as relayshieldadmin@gmail.com). Andrew posts Mastodon and Farcaster himself.
