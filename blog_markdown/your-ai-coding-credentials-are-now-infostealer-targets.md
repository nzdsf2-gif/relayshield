---
title: "Your AI Coding Credentials Are Now Infostealer Targets"
slug: your-ai-coding-credentials-are-now-infostealer-targets
date: 2026-10-20
---

# Your AI Coding Credentials Are Now Infostealer Targets

There's a new item on the infostealer shopping list. It's not your bank password. It's your Claude API key.

Symantec's Threat Hunter team reported on October 15 that the newest Aoki infostealer samples specifically target AI coding assistant credentials. The malware reaches for `.claude.json`, Claude desktop cookies, ChatGPT cookies, and the Codex `config.toml` and `.env` files. It also steals tokens for GitHub Copilot, Cursor, Google Gemini, JetBrains AI Assistant, and Kiro, along with AWS credentials. If you write code with AI tools, your credentials are in the crosshairs.

Aoki (also called Aokigahara) is a relatively new stealer, first observed earlier in 2026. Earlier samples did not touch AI-related files, which tells you this capability was added recently and is still being expanded.

## Why AI credentials are worth stealing

Stolen API keys can be cashed in three ways. The attacker can use them directly, resell them on underground marketplaces, or simply burn through your API quota to run up your bill. All three are profitable.

But AI credentials are worse than stolen card data in one important way. A credit card gives the attacker money. An AI coding assistant credential gives them your identity as a developer: operating under your name, on your API quota, past whatever trust your account carries. Depending on what that account can touch, the same material can open a route into your connected repositories, cloud services, and CI/CD pipelines.

## The market already exists

Infostealer logs are bought and sold every day on Telegram marketplaces. A log containing valid AI assistant credentials carries strong resale value because the buyer gets both compute and access. The credentials move fast: from infection to listing to resale in hours.

This is the part most developers miss. You're thinking about whether your machine is infected. You should also be thinking about whether your credentials are already being traded.

## What you can do

**Rotate your keys.** If you suspect any compromise, regenerate your API keys immediately. Don't wait for confirmation.

**Check if you're exposed.** Our threat intelligence corpus monitors 125 Telegram marketplaces for stealer logs and compromised credentials. If your credentials are being traded, we can tell you.

**Separate your environments.** Don't use the same API key for personal projects and production systems. A compromise in one shouldn't cascade to the other.

**Watch your usage.** Unexpected spikes in API consumption are often the first sign that a key has been stolen. Set up billing alerts.

## The bottom line

AI coding assistants went from novelty to critical infrastructure in under two years. Attackers noticed. Your `.claude.json` is now as valuable as your SSH keys, and it's sitting in a predictable location on every developer machine running these tools.

The concrete move: rotate your API keys, set billing alerts, and check whether your credentials are already being traded in the markets where stealer logs change hands.

---

*RelayShield monitors 125 Telegram marketplaces for stealer logs, compromised credentials, and threat indicators. Check your exposure with our free Telegram or WhatsApp bot.*

**Sources:** Symantec Threat Hunter report via [Infosecurity Magazine](https://www.infosecurity-magazine.com/news/aoki-infostealer-ai-coding/) (October 15, 2026); [Cyber Insider](https://cyberinsider.co.uk/aoki-infostealer-expands-credential-theft-to-ai-coding-assistants/); [GBHackers](https://gbhackers.com/aoki-infostealer-targets-ai/).
