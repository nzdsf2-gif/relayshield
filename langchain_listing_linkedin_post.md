# LinkedIn post — LangChain integration listing

Paste the block below the line. LinkedIn strips Markdown, so this is written as plain text with
line breaks doing the formatting work.

---

A while back someone left a comment on one of our posts that changed what we built.

The point was simple: a tool an agent *may* call is not the same thing as a gate the system *must* pass. If your security check is just another entry in the tools array, the model decides whether to run it. That is not a control. That is a suggestion.

So we rebuilt it as a gate.

RelayShield's LangChain integration is now middleware, not a tool. It runs before execution and blocks connect_mcp_server and install_mcp_package calls outright when we report risk on the target. The agent does not get a vote.

As of today it is listed in LangChain's official integration docs.

Why this matters beyond us: agents are getting write access to real systems, and the security model most teams have is "we gave it a tool that can check things." The moment the model is the one deciding whether to invoke the check, you have advisory security on an autonomous system.

The pattern generalises. Lifecycle actions like onboarding and offboarding can fire in parallel and log after the fact. Approval decisions — installing an MCP server, granting a scope, executing a payment — have to block on the check. Those are different problems and they need different plumbing.

pip install langchain-relayshield

Docs: https://api.relayshield.net/developers

What is the highest-impact agent action in your stack that currently runs without a mandatory pre-execution check?

#AIAgents #LangChain #MCP #AgentSecurity #CyberSecurity

---

## Notes (not part of the post)

- The hook is the commenter's objection, not the listing. The listing is credibility that arrives
  in one line halfway down; leading with "we got listed" is a press release and will underperform.
- The closing question is doing the real work. Per prior RelayShield posts, engagement and actual
  product direction came from comments, not the body — reply to every one within the first hour.
- The gate-vs-parallel paragraph is deliberate: it is the distinction that makes this a design
  argument rather than a product announcement, and it is the part practitioners will push back on.
- 5 hashtags is the practical ceiling. #LangChain and #MCP are the targeting ones; #CyberSecurity
  is reach.
- Post as a POST, not an article.
- Do NOT claim RelayShield detects specific malware families in comments — see the MedusaHVNC
  channel-strategy notes.
