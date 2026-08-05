# Hashnode cross-post — LangChain mandatory gate (v3)

**Correction:** an earlier pass at this doc set Hashnode as canonical and skipped the HF blog entirely.
That was wrong — HF's own blog (huggingface.co/blog) is a resource RelayShield already publishes to and
pays for, and both prior posts (original + v2) went there first. Founder caught this 2026-07-22. Restored
the proven pattern: **publish full post to HF blog first, Hashnode cross-posts back to it**, same as v1/v2.

**Publish order:**
1. Publish [hf_blog_post_v3_langchain_gate.md](hf_blog_post_v3_langchain_gate.md) to
   `huggingface.co/blog/relayshieldadmin/langchain-mcp-security-gate` (confirm exact slug availability at
   publish time)
2. Then cross-post to Hashnode using the settings below, canonical pointing back to the HF URL

Paste the full post body into Hashnode's editor with **Cmd+Shift+V (plain text)**, not a normal paste —
normal paste leaves the Markdown syntax unrendered as literal characters.

**Post settings / Discovery page:**
- **Article slug**: `langchain-mcp-security-gate`
- **Canonical URL**: `https://huggingface.co/blog/relayshieldadmin/langchain-mcp-security-gate` (cross-post pointing back to HF, same pattern as v1/v2)
- **Tags** (cap ~5): `ai`, `cybersecurity`, `mcp`, `langchain`, `agents`
- **SEO title** (~60 char budget): `Mandatory AI Agent Security Gate — LangChain Reference`
- **SEO description** (~150-160 char budget): `An open-source LangChain wrap_tool_call middleware that blocks unfamiliar MCP server connections behind a required security check, not an optional tool call.`
- **Cover image**: none required to publish

---

Content: use the full body of [hf_blog_post_v3_langchain_gate.md](hf_blog_post_v3_langchain_gate.md) as-is —
it was already written ready-to-publish, no separate "body only" file needed this round.
