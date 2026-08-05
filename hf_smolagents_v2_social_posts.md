HF blog post (published): https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

---

## LinkedIn

We asked what tool to build next for AI agents. Two developers answered in detail — here's what we shipped in response.

Our original 4 smolagents.Tool security checks for AI agents (published as an MCP server on Hugging Face) got real, specific community feedback: group OAuth/credential-exposure checks as one "agent authority" family, add supply-chain and secret-scanning coverage, and — most usefully — a bug report showing our public MCP package was returning failed checks as if they'd succeeded.

We shipped all of it:
→ 5 new tools (oauth_watchlist, nhi_exposure, session_risk, supply_chain, secret_scan) — 9 total now
→ Every tool now returns a typed result (outcome/recommended_action/evidence/reason_codes), not a formatted string
→ Fixed the isError bug in relayshield-mcp (v0.2.7, live on PyPI) so a failed check can no longer be mistaken for a clean one

Pay-as-you-go, self-serve signup, no subscription required.

Read the writeup: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

#AIagents #AgentSecurity #MCP #smolagents #CyberSecurity

---

## Telegram

🛡️ Update: RelayShield's agent security tools just went from 4 to 9 — direct response to community feedback on the original release.

New: oauth_watchlist, nhi_exposure, session_risk (grouped as one "agent authority" check), plus supply_chain and secret_scan. Every tool now returns a typed, explainable result instead of a plain string.

Full writeup: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

---

## Farcaster (post to /security, /ai, /relayshield)

We asked which tool to build next. Two devs answered in detail — shipped 5 new agent security checks + a typed result schema in response, and fixed a real bug in our public MCP package along the way.

4 tools → 9. Pay-per-call, x402 USDC available (no key needed for that path).

https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

---

## Mastodon (infosec.exchange)

RelayShield's agent security tools, v2: 4 → 9, direct response to #AIsecurity feedback from the community on the original release.

New: oauth_watchlist, nhi_exposure, session_risk — grouped as one "agent authority" family (can someone else exercise this agent's current authority?) — plus supply_chain and secret_scan.

Every tool now returns a typed outcome/recommended_action result instead of a formatted string. Also fixed a real bug in our public @huggingface MCP package: failed upstream checks were being reported as successful — confirmed and fixed end to end.

Self-serve, pay-per-call, no subscription.

https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

#InfoSec #MCP #AgentSecurity #ThreatIntel

---

## Medium (full cross-post, not a teaser)

Medium gets the full article, same treatment as Hashnode — copy the complete post body from `hf_blog_post_v2_hashnode_body_only.md` (same repo), not a short blurb.

- **Canonical URL**: set to `https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2` in Medium's story settings (Story settings → Advanced settings → "Change canonical URL") — avoids duplicate-content SEO issues, same reasoning as the Hashnode cross-post.
- **Tags** (Medium caps at 5): `AI`, `Cybersecurity`, `MCP`, `AI Agents`, `Open Source`
- **Subtitle** (Medium's version of a dek, shows under the title): `Five new smolagents.Tool checks, a typed result schema, and two real bugs fixed — shipped in direct response to community feedback.`
- Medium doesn't have Hashnode's markdown-paste-mangling issue in the same way (its editor is closer to a standard rich-text paste target), but if formatting breaks on paste, use the same `pbcopy`-from-raw-file approach that fixed it for Hashnode rather than copying from this chat.

---

## Hashnode cross-post

Already done — see `hf_blog_post_v2_hashnode_crosspost.md` and `hf_blog_post_v2_hashnode_body_only.md` (same repo).
