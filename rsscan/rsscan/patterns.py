"""Credential patterns — a byte-faithful mirror of the server's NHI_PATTERNS.

rsscan matches entirely on the developer's machine. No source code, no diff and
no matched value ever leaves the host, which is what makes the free tier free
(zero API cost) and removes the "why does this hook POST our source to a third
party" objection outright.

DO NOT hand-edit. Regenerate with:

    python3 tools/sync_patterns.py

Sync digest: 79b77d3c5a303232
`tools/sync_patterns.py --check` fails if this drifts from relayshield_api.py,
so a pattern fixed server-side cannot silently go stale in the client.
"""

from __future__ import annotations

import hashlib
import re as _re


def _ctx_key(vendors: str, key_re: str) -> str:
    """Build a context-anchored credential regex (gitleaks style).

    Several LLM vendors (DeepSeek, Moonshot/Kimi, Alibaba DashScope/Qwen) issue
    OpenAI-compatible keys with a bare ``sk-`` prefix and publish no format spec,
    so the key alone is not attributable to a provider by shape. Requiring the
    vendor name or its env-var nearby is the only way to attribute one without
    guessing -- stealer-log dumps generally capture the surrounding ``.env`` line.
    The secret itself must be the single capturing group; _detect_nhi_in_text
    reports group(1) so the vendor context never leaks into the preview.
    """
    return (
        rf"(?i)(?:{vendors})[\w.\-]{{0,20}}[\s'\"]{{0,3}}"
        rf"(?:=|:|=>|:=|\|\|)[\s'\"`]{{0,5}}({key_re})"
    )


NHI_PATTERNS = [
    # (name, regex, severity, description, llm_provider)
    # llm_provider is None for non-LLM credentials, or a short provider slug
    # for LLM/AI API keys — used to power the dedicated LLMjacking check
    # (handle_llm_credential_exposure) without a second detection pass.
    ("aws_access_key",   r"AKIA[A-Z0-9]{16}",                         "CRITICAL", "AWS IAM Access Key", None),
    ("github_pat",       r"gh[pousr]_[a-zA-Z0-9]{36,}",              "CRITICAL", "GitHub Personal Access Token", None),
    ("github_pat_fine",  r"github_pat_[a-zA-Z0-9_]{82}",             "CRITICAL", "GitHub Fine-Grained PAT", None),
    ("stripe_secret",    r"sk_live_[a-zA-Z0-9]{24,}",                "CRITICAL", "Stripe Secret Key", None),
    # Our own key format. Added 2026-08-18 after a live rs_live_ key reached a
    # public commit and was caught by GitGuardian, not by us. rsscan carried 33
    # patterns and none of them matched the credential this product issues,
    # which is the first thing a security audience tests.
    ("relayshield_key",  r"rs_(?:live|demo)_[a-f0-9]{32,}",           "CRITICAL", "RelayShield API Key", None),
    ("private_key",      r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "CRITICAL", "Private Cryptographic Key", None),
    ("slack_bot",        r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+",        "HIGH",     "Slack Bot Token", None),
    ("slack_user",       r"xoxp-[0-9]+-[0-9]+-[0-9]+-[a-zA-Z0-9]+","HIGH",     "Slack User Token", None),
    # A webhook URL is a credential in its own right: anyone holding it can post
    # into the channel. Distinct shape from xoxb/xoxp, so the token patterns above
    # never matched it. GitHub push protection caught one we shipped; we did not.
    ("slack_webhook",    r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9_]{16,}",
                                                                     "HIGH",     "Slack Incoming Webhook URL", None),
    # Same shape, same reasoning: a Zapier catch hook fires the Zap for anyone
    # holding the URL. Found 2026-08-18 on an internal key record while auditing
    # the rs_live_ exposure.
    ("zapier_webhook",   r"https://hooks\.zapier\.com/hooks/(?:catch|standard)/[0-9]+/[a-zA-Z0-9]{16,}",
                                                                     "HIGH",     "Zapier Webhook URL", None),
    # LLM/AI provider keys — bumped to CRITICAL 2026-07-26 (LLMjacking):
    # a leaked key here isn't just data exposure, it's a live, uncapped
    # billing liability — real incidents range from $46K/day (Sysdig, AWS
    # Bedrock) to $82K/48hr (leaked Gemini key) to a $500K single-month
    # bill from one unthrottled account. Underground price for a stolen
    # LLM key is ~$30 — the asymmetry between theft cost and victim damage
    # is exactly why this deserves CRITICAL, not the generic HIGH other
    # SaaS API keys get.
    ("google_api",       r"AIza[0-9A-Za-z\-_]{35}",                  "CRITICAL", "Google AI (Gemini) API Key", "google"),
    # OpenAI rebuilt its key format around prefixed keys (sk-proj-/sk-svcacct-/
    # sk-admin-) that contain hyphens and underscores and run far longer than the
    # 48-char legacy shape. The previous pattern (sk-[a-zA-Z0-9]{48}) matched ONLY
    # legacy keys, so every modern key was a silent false negative -- on the most
    # common LLM provider, in the LLMjacking product. Fixed 2026-07-28.
    # Both branches anchor on T3BlbkFJ, which is base64("OpenAI") embedded in the
    # key body (verified locally). That anchor is what makes attribution safe
    # despite the sk- prefix being shared with DeepSeek/Moonshot/Qwen.
    ("openai_key",       r"sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})T3BlbkFJ(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})",
                                                                     "CRITICAL", "OpenAI API Key", "openai"),
    ("openai_key_v1",    r"sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}", "CRITICAL", "OpenAI API Key (v1 format)", "openai"),
    # Legacy pre-2023 keys carry no T3BlbkFJ anchor, so a bare sk-+48 match cannot
    # be attributed to OpenAI rather than DeepSeek/Moonshot/Qwen. Context-anchored
    # instead of guessing -- see _ctx_key.
    ("openai_key_legacy", _ctx_key(r"openai|OPENAI_API_KEY", r"sk-[a-zA-Z0-9]{48}"),
                                                                     "CRITICAL", "OpenAI API Key (legacy format)", "openai"),
    # Underscore added to the body class 2026-07-28: real Anthropic keys contain
    # "_" as well as "-", and the previous class [a-zA-Z0-9\-] caused the {90,}
    # quantifier to fail on any key with an underscore in its first 90 body
    # chars -- a silent false negative of the same class as the OpenAI one above.
    # Kept looser than gitleaks' sk-ant-api03-...{93}AA so it survives a future
    # version bump past api03.
    ("anthropic_key",    r"sk-ant-[a-zA-Z0-9_\-]{90,}",              "CRITICAL", "Anthropic API Key", "anthropic"),
    ("groq_key",         r"gsk_[a-zA-Z0-9]{52}",                     "CRITICAL", "Groq API Key", "groq"),
    ("xai_key",          r"xai-[a-zA-Z0-9]{80}",                     "CRITICAL", "xAI (Grok) API Key", "xai"),
    ("replicate_key",    r"r8_[a-zA-Z0-9]{37}",                      "CRITICAL", "Replicate API Key", "replicate"),
    # --- added 2026-07-28 (TODO item 77) -------------------------------------
    # Amazon Bedrock now issues dedicated API keys used as bearer tokens via
    # AWS_BEARER_TOKEN_BEDROCK, distinct from IAM credentials. Because they are
    # Bedrock-scoped they CAN be tagged with an llm_provider, unlike generic AKIA
    # keys below. Both anchors verified locally:
    #   long-lived : ABSK + base64("BedrockAPIKey-") -> ABSKQmVkcm9ja0FQSUtleS...
    #   short-lived: literal "bedrock-api-key-" + base64("bedrock.amazonaws.com")
    ("bedrock_key_long",  r"ABSKQmVkcm9ja0FQSUtleS[A-Za-z0-9+/]{80,250}={0,2}",
                                                                     "CRITICAL", "Amazon Bedrock API Key (long-lived)", "bedrock"),
    ("bedrock_key_short", r"bedrock-api-key-YmVkcm9jay5hbWF6b25hd3MuY29t[A-Za-z0-9+/=]*",
                                                                     "CRITICAL", "Amazon Bedrock API Key (short-lived)", "bedrock"),
    # Hugging Face tokens are the highest-leverage LLM credential in this list:
    # Kimi, DeepSeek, Qwen and NVIDIA models are all reachable through HF
    # Inference Providers, so a leaked hf_ token bills against those models
    # without the attacker ever holding a vendor key. Body is letters only.
    ("huggingface_token", r"hf_[a-zA-Z]{34}",                        "CRITICAL", "Hugging Face User Access Token", "huggingface"),
    ("huggingface_org",   r"api_org_[a-zA-Z]{34}",                   "CRITICAL", "Hugging Face Organization Token", "huggingface"),
    # Alibaba Cloud AccessKey ID -- the cloud credential that grants Model Studio
    # (Qwen) access. Distinct from the DashScope sk- key, and unlike it this one
    # has a reliable, unambiguous prefix.
    ("alibaba_access_key_id", r"LTAI[a-zA-Z0-9]{20}",                "HIGH",     "Alibaba Cloud AccessKey ID (Qwen/Model Studio)", "alibaba"),
    # NVIDIA NIM (build.nvidia.com / integrate.api.nvidia.com). BEST-EFFORT
    # LENGTH: the "nvapi-" prefix is consistently attested across NVIDIA's own
    # docs and multiple independent sources, but no source documents the body
    # length or character set -- and gitleaks ships no NVIDIA rule at all, so
    # there is no external pattern to borrow. Shipped anyway on the same basis
    # as mcp_token_generic below: the prefix is distinctive enough to carry
    # attribution on its own (unlike the sk- family, which is why NVIDIA needs
    # no context anchor), so an open-ended {40,} risks a stray match rather than
    # a wrong provider label. Tighten if a real key length is ever confirmed.
    ("nvidia_nim_key",   r"nvapi-[A-Za-z0-9_\-]{40,}",               "CRITICAL", "NVIDIA NIM API Key", "nvidia"),
    # OpenAI-compatible vendors with no published key format. Context-anchored
    # rather than pattern-guessed, so provider attribution is never fabricated.
    ("deepseek_key",     _ctx_key(r"deepseek|DEEPSEEK_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "DeepSeek API Key", "deepseek"),
    ("moonshot_key",     _ctx_key(r"moonshot|kimi|MOONSHOT_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "Moonshot (Kimi) API Key", "moonshot"),
    ("qwen_key",         _ctx_key(r"dashscope|qwen|DASHSCOPE_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"),
                                                                     "CRITICAL", "Alibaba DashScope (Qwen) API Key", "qwen"),
    # Catch-all for a bare OpenAI-compatible key with no vendor context to
    # attribute it. Deliberately claims NO provider: the sk- prefix is shared by
    # OpenAI (legacy), DeepSeek, Moonshot/Kimi and DashScope/Qwen, so naming one
    # would be a fabricated attribution. HIGH rather than CRITICAL only because
    # a bare sk- string carries some residual false-positive risk from non-LLM
    # services; the billing liability if it is real is identical.
    # MUST stay last in this list -- _detect_nhi_in_text suppresses it for any
    # value an attributed pattern already claimed, so it never double-reports.
    ("llm_key_generic_sk", r"sk-[a-zA-Z0-9]{32,64}",                 "HIGH",     "OpenAI-compatible LLM API Key (provider unattributed)", "unknown_openai_compatible"),
    # Cohere and Azure OpenAI keys are opaque tokens with no verifiable
    # standardized prefix -- deliberately not pattern-matched rather than
    # shipping a guessed regex that would silently fail to catch real
    # leaked keys. (Cohere could be covered contextually via _ctx_key if it
    # ever justifies the noise; not done yet.)
    #
    # Corrected 2026-07-28: this block previously said Bedrock had no separate
    # key format and used plain IAM credentials. AWS has since shipped dedicated
    # Bedrock API keys -- see bedrock_key_long / bedrock_key_short above.
    # Generic AKIA IAM keys are still deliberately NOT tagged llm_provider
    # (most AWS key leaks have nothing to do with Bedrock; tagging every one
    # would make the dedicated LLM-exposure endpoint noisy) -- that reasoning
    # stands, it just no longer means Bedrock itself is undetectable.
    #
    # Still unshippable for lack of any published format (researched 2026-07-28,
    # see llmjacking_provider_regex_research.md): NVIDIA NIM (nvapi- prefix is
    # well attested but its length is documented nowhere) and Meta Muse Spark /
    # Meta Model API (format undisclosed, waitlisted public preview).
    ("sendgrid_key",     r"SG\.[a-zA-Z0-9\-_.]{22}\.[a-zA-Z0-9\-_.]{43}", "HIGH", "SendGrid API Key", None),
    ("twilio_sid",       r"AC[a-f0-9]{32}",                           "MEDIUM",   "Twilio Account SID", None),
    ("stripe_pub",       r"pk_live_[a-zA-Z0-9]{24,}",                "MEDIUM",   "Stripe Publishable Key", None),
    ("jwt_token",        r"eyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}", "MEDIUM", "JWT Token", None),
    # Agent-framework credentials (added 2026-07-07, AGENTIC-1) — AI agent
    # orchestration platforms are now a confirmed autonomous-attack target
    # (JadePuffer/Sysdig, July 2026).
    ("langsmith_key",    r"lsv2_(?:pt|sk)_[a-f0-9]{32,}",             "HIGH",     "LangSmith API Key", "langsmith"),
    # MCP has no standardized token format as of 2026-07 — this is a
    # best-effort pattern based on an emerging informal prefix convention
    # in some MCP server implementations, not a guaranteed catch-all.
    ("mcp_token_generic", r"mcp_(?:live|sk|pat)_[a-zA-Z0-9]{20,}",    "MEDIUM",   "Possible MCP Server Auth Token", None),
]


_COMPILED = [
    (name, _re.compile(pat), sev, desc, provider)
    for name, pat, sev, desc, provider in NHI_PATTERNS
]

PATTERN_COUNT = len(_COMPILED)


def fingerprint(value: str) -> str:
    """Stable, non-reversible id — identical scheme to the server's.

    Must stay byte-identical or an allowlist written against a server-side scan
    would stop matching a local one.
    """
    return "sha256:" + hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]

