# Discord outreach — smolagents v2 feedback release

Both messages assume a Discord DM or reply in whatever channel the original comment/interaction happened in (HF Discord, or wherever these two are reachable — usernames below are placeholders where identity is uncertain). Blog post is live: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2

---

## To Mason Reed (masonreed11)

Hey Mason — thanks for the comment on the smolagents post. Took your suggestion seriously: just shipped `supply_chain` and `secret_scan` as new tools (dependency vulns were already covered by `tech_stack_cve` — turned out that one had a real bug where it was silently reporting "no CVEs found" regardless of actual results, fixed that too while I was in there).

Also rebuilt every tool's output around your "explainable" point specifically — instead of a formatted string, each one now returns outcome/recommended_action plus the actual evidence and reason codes behind it, so it's not just a verdict, it's why.

Wrote up the full release here if you want the details: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2. Would genuinely like to know if this is closer to what you had in mind.

---

## To the second commenter (identity unconfirmed — fill in handle/DM target before sending)

Hey — that was one of the more useful pieces of feedback we've gotten on this. Specifically acted on:

- Shipped `oauth_watchlist`, `nhi_exposure`, and `session_risk` grouped exactly as you framed it — one "agent authority" family, not three unrelated checks. `supply_chain` too.
- Used your structured result contract almost verbatim: outcome/recommended_action/reason_codes/evidence/coverage/freshness/error, all 9 tools now. Kept `no_known_finding` instead of `safe`, for the reason you gave.
- Your synthetic-failure test on `relayshield-mcp` was right — reproduced all 5 of your cases (401/429/500/200-with-ok:false/malformed) against the real SDK, confirmed `isError` was wrong on all of them, fixed it end to end. That's shipped in v0.2.7 on PyPI now.

Haven't built the advisory-vs-mandatory-gate distinction yet — that's a real architectural piece, not something to bolt on quickly, so it's next rather than in this release. Full writeup: https://huggingface.co/blog/relayshieldadmin/smolagents-agent-security-tools-v2. If you'd actually use a host-side gate pattern like you described, that's useful to know before we scope it.

---

**Before sending**: I don't have a name or handle for the second commenter beyond the quoted text you pasted — you'll need to fill in who/where this goes. If you have their HF username or a Discord handle, I can tailor the message further once I know it.
