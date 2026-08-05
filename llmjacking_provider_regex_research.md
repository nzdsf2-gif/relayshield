# LLMjacking detection — provider regex research

Research only. Nothing has been changed in `relayshield_api.py`. Compiled 2026-07-28 against
TODO item 77 (Chinese/closed-source LLM key research, carried over from 2026-07-26).

Method: primary vendor docs where they publish a format, the maintained
[gitleaks](https://github.com/gitleaks/gitleaks) ruleset where they do not, and independent
verification of base64 anchors computed locally. This follows the standard already set in
`NHI_PATTERNS`: do not ship a guessed regex that would silently fail to catch real keys.

---

## 1. Headline finding — an existing CRITICAL detection is failing today

**`openai_key` misses every modern OpenAI key.**

Current pattern:

```
sk-[a-zA-Z0-9]{48}
```

OpenAI migrated to prefixed keys (`sk-proj-`, `sk-svcacct-`, `sk-admin-`) which contain
hyphens and underscores and are far longer than 48 chars. Tested:

| Key shape | Current regex matches? |
|---|---|
| legacy `sk-` + 48 | yes |
| modern `sk-proj-` + ~74 | **no** |
| `sk-svcacct-` / `sk-admin-` | **no** |

This is a live false negative in the flagship LLMjacking product, on the single most common
LLM provider. It is almost certainly worth more than any new provider added below.

Gitleaks' pattern anchors on `T3BlbkFJ`, which is `base64("OpenAI")` embedded mid-key
(verified locally). That makes it essentially false-positive-free:

```
\b(sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})T3BlbkFJ(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})\b|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20})
```

Related: `anthropic_key` is currently `sk-ant-[a-zA-Z0-9\-]{90,}`. Gitleaks uses the tighter
`sk-ant-api03-[a-zA-Z0-9_\-]{93}AA`. The current one is looser, so it should still match —
but it does not cover `_` in the body, which the gitleaks pattern does. Worth a look.

---

## 2. Verifiable and ready to ship

### Amazon Bedrock — long-lived API key

```
\b(ABSK[A-Za-z0-9+/]{109,269}={0,2})
```

Source: gitleaks `aws-amazon-bedrock-api-key-long-lived`. **Independently verified**: every
long-term key is `ABSK` + base64 of a payload beginning `BedrockAPIKey-`, and
`base64("BedrockAPIKey-") = QmVkcm9ja0FQSUtleS0=`, so real keys start `ABSKQmVkcm9ja0FQSUtleS`.
That 22-char anchor is effectively false-positive-free if a tighter pattern is preferred.

### Amazon Bedrock — short-lived API key

```
bedrock-api-key-YmVkcm9jay5hbWF6b25hd3MuY29t
```

**Independently verified**: `base64("bedrock.amazonaws.com") = YmVkcm9jay5hbWF6b25hd3MuY29t`.
A literal string match, zero false positives.

> **This corrects an out-of-date comment in `NHI_PATTERNS`**, which currently states that
> "AWS Bedrock access uses standard AWS IAM credentials, not a separate 'Bedrock key' format."
> That was true when written; AWS has since shipped dedicated Bedrock API keys used as bearer
> tokens via `AWS_BEARER_TOKEN_BEDROCK`. These are *distinct* from IAM keys, are Bedrock-scoped,
> and can therefore be tagged `llm_provider="bedrock"` **without** the noise problem that
> correctly stopped us tagging generic `AKIA` keys.

### Hugging Face — user access token

```
\b(hf_[a-zA-Z]{34})\b
```

Source: gitleaks `huggingface-access-token`. Note the body is **letters only**, not alphanumeric.

### Hugging Face — organization token

```
\b(api_org_[a-zA-Z]{34})\b
```

### Alibaba Cloud AccessKey ID (the Qwen/DashScope cloud credential)

```
\b(LTAI[a-zA-Z0-9]{20})\b
```

Source: gitleaks `alibaba-access-key-id`. This is the Alibaba Cloud credential, not the
DashScope `sk-` key — but it grants access to Model Studio/Qwen, so it is a legitimate
Qwen exposure vector and it *is* reliably patterned.

### Perplexity (bonus, not requested)

```
\b(pplx-[a-zA-Z0-9]{48})\b
```

---

## 3. Strategic point — Hugging Face is the highest-leverage single addition

The founder's own observation is the important one: Kimi, DeepSeek, Qwen and NVIDIA models are
all reachable through Hugging Face Inference Providers. A leaked `hf_` token can therefore bill
against those models **without the attacker ever holding a Moonshot/DeepSeek/Qwen key**.

So `hf_` is not just "one more provider" — it is the single pattern that covers the whole
Chinese-open-model surface at once, and unlike the `sk-` providers it has a reliable,
externally-validated regex. If only one thing ships, ship this.

---

## 4. Not verifiable — recommend NOT shipping a regex

No vendor publishes a key format spec for these, and gitleaks (the most comprehensive public
ruleset) has **zero** rules for any of them — confirmed by direct search of the full ruleset:

| Provider | Prefix | Status |
|---|---|---|
| DeepSeek | `sk-` | Length disputed across sources (32 vs 48). No official spec. |
| Moonshot / Kimi | `sk-` | "sk- followed by a long string." No official spec. |
| Alibaba Qwen (DashScope) | `sk-` | Referenced only as `sk-xxx` in examples. No official spec. |
| Meta Muse Spark (Meta Model API) | undisclosed | Docs show only `Authorization: Bearer $MODEL_API_KEY`. Base URL `https://api.meta.ai/v1`, model `muse-spark-1.1`, public preview/waitlist. |
| NVIDIA NIM | `nvapi-` | Prefix well-attested across multiple sources; **length never documented**. |

**NVIDIA is the closest to shippable.** The `nvapi-` prefix is distinctive and consistently
attested, and unlike the `sk-` family it cannot collide with another provider. A deliberately
loose `nvapi-[A-Za-z0-9_-]{60,}` would very likely be safe on false positives given the unique
prefix — but the length is unverified, so it should be labelled best-effort in the same way
`mcp_token_generic` already is.

### The `sk-` collision problem — this is the real blocker

OpenAI, DeepSeek, Moonshot and Qwen **all** use `sk-`. Consequences:

1. **There is no way to attribute a bare `sk-` key to a provider by pattern alone.** Any regex
   claiming to identify "a DeepSeek key" by shape is guessing, and would mislabel provider
   attribution in customer-facing output.
2. **Current misattribution risk**: today's `sk-[a-zA-Z0-9]{48}` would tag a 48-char DeepSeek or
   Moonshot key as `llm_provider="openai"`. If any of them issue 48-char keys, we are already
   reporting the wrong provider to customers.

Options if we want this surface covered anyway:
- **(a) Generic bucket.** Add `llm_key_generic_sk` = `sk-[a-zA-Z0-9]{32,64}` at a lower severity,
  tagged `llm_provider="unknown_openai_compatible"`. Honest about the ambiguity, catches the keys,
  makes no false attribution claim. This is my recommendation.
- **(b) Contextual detection.** Match `sk-` keys only when a provider name appears nearby
  (`DEEPSEEK_API_KEY=`, `MOONSHOT_API_KEY=`, `DASHSCOPE_API_KEY=`). This is exactly how gitleaks
  handles Cohere and Alibaba secret keys, and stealer-log dumps usually do include the env var
  name. Higher precision, more implementation work.
- **(c) Live validation.** Test the key against each provider's endpoint to determine ownership.
  Highest accuracy, but means transmitting harvested credentials to third parties — **not
  recommended** on legal/ethical grounds.

---

## 5. Also worth revisiting

`NHI_PATTERNS` says Cohere has "no verifiable standardized prefix." Gitleaks does ship a Cohere
rule — but it is a *contextual* one (requires the literal `cohere` or `CO_API_KEY` near a
40-char token), not a prefix rule. So the existing comment is correct in substance; option (b)
above would be the way to cover it.

---

## Suggested order

1. **Fix `openai_key`** — live false negative on the biggest provider. Highest value, lowest risk.
2. **Add Hugging Face** (`hf_`, `api_org_`) — reliable regex, covers the Chinese open models via Inference Providers.
3. **Add Bedrock** (both forms) — verified anchors, and corrects a stale code comment.
4. **Add Alibaba `LTAI`** — reliable, real Qwen vector.
5. **Decide on the `sk-` bucket** — needs a product call on (a) vs (b) before any code.
6. **NVIDIA `nvapi-`** — ship only if we accept a best-effort length, labelled as such.
7. **Meta Muse Spark** — blocked; no published format. Revisit when out of public preview.

## Sources

- [gitleaks ruleset (config/gitleaks.toml)](https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml)
- [Use an Amazon Bedrock API key — AWS docs](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html)
- [Securing Amazon Bedrock API keys — AWS Security Blog](https://aws.amazon.com/blogs/security/securing-amazon-bedrock-api-keys-best-practices-for-implementation-and-management/)
- [Hugging Face user access tokens](https://huggingface.co/docs/hub/en/security-tokens)
- [Meta Model API — getting started](https://dev.meta.ai/docs/getting-started/overview/)
- [Introducing Muse Spark 1.1 — Meta AI blog](https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/)
- [DeepSeek API docs](https://api-docs.deepseek.com/)
- [NVIDIA NeMo Retriever — authentication and API keys](https://docs.nvidia.com/nemo/retriever/latest/extraction/api-keys/)
- [Alibaba Cloud Model Studio — first API call to Qwen](https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen)
