---
title: "Your API Key Is Someone Else's Credit Card: Inside the LLMjacking Economy"
slug: llmjacking-api-key-credit-card
date: 2026-11-08
tags: [llmjacking, api-keys, threat-intel, llm-mixers]
canonical: https://blog.relayshield.net/
---

# Your API Key Is Someone Else's Credit Card: Inside the LLMjacking Economy


**Updated Nov 8, 2026:** this post refreshes our Sept 28 piece with the Nov 2, 2026 Google Threat Intelligence Group and Mandiant report on LLM Mixers.

On Nov 2, Google's Threat Intelligence Group (GTIG) and Mandiant reported that criminals are breaking into companies' cloud accounts, switching on AI model services, and reselling that access to paying customers. Single incidents generated more than $100,000 in fraudulent charges in a day, and some organizations were billed up to $1 million before access was cut. One actor made more than 500,000 requests through a victim's account in under eight hours.

The resale channel has a name: LLM Mixers. These are underground services that pool many stolen accounts and sell cheap subscriptions to frontier AI models. One service, Jet Night, sold access for about $60 a month, against the $100 to $250 that consumer plans typically cost. GTIG says Jet Night passed nearly one million dollars in token costs to one victim organization.

This is the same economy we described in September, grown up. In September the hook was GTIG chief analyst John Hultquist telling the Financial Times that LLM-jacking was rising sharply, with dark web marketplaces selling unauthorized access to models from OpenAI, Anthropic, and Google at discounts of up to 97%, and premium subscriptions running up to $200 per user per month. The November report adds the division of labor: initial-access actors on one side, Mixer resellers on the other, with open-source key-pooling tools as the plumbing.

GTIG's contrast with cryptojacking is the line that matters. Cryptojacking burned CPU slowly. LLMjacking can generate large spikes in fraudulent cloud charges in a matter of hours. GTIG expects threat actors will increasingly prioritize LLMjacking over traditional resource theft like cryptojacking. The victim pays, the buyer gets frontier access at a steep discount, and the bill arrives before anyone notices.

The supply chain starts where our last post ended: infostealer malware siphoning API keys and session tokens off developer laptops, plus cloud credentials found in public code repositories, session tokens tricked out of users, and unauthenticated model servers left open to the internet. One compromised corporate account was pushed to nearly 200,000 API requests in two minutes. The keys do not get burned by the thief directly. They get fenced. And the fence is a marketplace.

## We watch the fence

This is the part most coverage misses. The theft is the supply; the market is the business. RelayShield monitors 136 Telegram marketplaces, and our corpus (785K indicators, 10M+ citations) tracks tokens and keys across 14 open-source and closed-source model families: Claude, OpenAI, xAI, DeepSeek, Kimi, Alibaba Qwen, and the open models behind Hugging Face, as they surface for trade.

A stolen model key works exactly like a stolen credit card: whoever holds it spends someone else's inference budget and compute capacity. The victim gets the bill; the buyer gets frontier capability at a steep discount. The Mixer model makes the arbitrage industrial: one stolen account feeds dozens of paying subscribers, and the victim only notices when the statement arrives.

And the blast radius keeps widening. A single Hugging Face token can reach thousands of open models. Steal one key and the thief inherits an entire model zoo. Aggregators like OpenRouter work the same way: one key, dozens of providers behind it. Every consolidation point for developers is a consolidation point for thieves. And you do not need to be an AI shop to receive an AI bill: in several incidents GTIG describes, the AI services were not enabled before the compromise. The attackers enabled them.

## The playbook

Four things, in order:

1. **Stop the leak before it ships.** Keys land in repos, gists, and chat logs because nobody scans before commit. Scan early, scan always.
2. **Check whether your key is already out there.** If your Anthropic or OpenAI key is sitting in a marketplace listing, you want to know before the invoice tells you. Run it against a corpus that watches the bazaars.
3. **Watch the marketplaces, not just your logs.** By the time anomalous usage shows up in your dashboard, the key has already been fenced and burned. Marketplace monitoring catches the listing; log monitoring catches the aftermath.
4. **Cap the spend and scope the key.** GTIG's practical fix is spending caps on AI services, tighter key scopes, and alerts when an AI service is suddenly enabled or its logging switched off. A key for a small internal tool should not be able to call the most expensive models, and an unexpected enablement should be treated as a critical security event.

One honest limit: no screening service stops a platform from leaking environment variables in the first place. Once a bearer key is stolen it looks legitimate, which is why binding, scoping, and usage monitoring matter. The key you issue is a credit card you handed out. Treat it like one.

## Sources

- Google Threat Intelligence Group and Mandiant, "LLMJacking: How Threat Actors Monetize Compromised Cloud and Model Resources," Nov 2, 2026 (via AI Cyber Brief, Nov 6, 2026: https://aicyberbrief.com/article/google-and-mandiant-stolen-cloud-ai-access-is-being-resold-with-victims-billed-up-to-1-million)
- Dataconomy, Sept 28, 2026; PYMNTS, Sept 2026 (Sept GTIG coverage, via the original Sept 28 post)

---

*Free, no-signup key check: https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-muse*
