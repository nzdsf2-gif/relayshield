---
title: "Your AI Coding Credentials Are Now Infostealer Targets"
slug: your-ai-coding-credentials-are-now-infostealer-targets
date: 2026-10-20
---

# Your AI Coding Credentials Are Now Infostealer Targets

There's a new item on the infostealer shopping list. It's not your bank password. It's your Claude API key.

Symantec's Threat Hunter team found that the newest Aoki infostealer samples specifically target AI coding assistant credentials. The malware reaches for `.claude.json`, Claude desktop cookies, and the Codex `config.toml` and `.env` files. If you use Claude Code, Claude Desktop, or Codex, your credentials are in the crosshairs.

## Why AI credentials are worth stealing

Stolen API keys can be cashed in three ways. The attacker can use them directly, resell them on underground marketplaces, or simply burn through your API quota to run up your bill. All three are profitable.

But AI credentials are worse than stolen card data in one important way. A credit card gives the attacker money. An AI coding assistant credential gives them your identity as a developer, plus a route into your connected repositories, cloud services, and CI/CD pipelines. One stolen `.claude.json` can become access to your entire development infrastructure.

## The market already exists

Infostealer logs are bought and sold every day on Telegram marketplaces. A log containing valid AI assistant credentials commands a premium because the buyer gets both compute and access. The credentials move fast: from infection to listing to resale in hours.

This is the part most developers miss. You're thinking about whether your machine is infected. You should also be thinking about whether your credentials are already being traded.

## What you can do

**Rotate your keys.** If you suspect any compromise, regenerate your API keys immediately. Don't wait for confirmation.

**Check if you're exposed.** Our threat intelligence corpus monitors 125 Telegram marketplaces for stealer logs and compromised credentials. If your credentials are being traded, we can tell you.

**Separate your environments.** Don't use the same API key for personal projects and production systems. A compromise in one shouldn't cascade to the other.

**Watch your usage.** Unexpected spikes in API consumption are often the first sign that a key has been stolen. Set up billing alerts.

## The bottom line

AI coding assistants went from novelty to critical infrastructure in under two years. Attackers noticed. Your `.claude.json` is now as valuable as your SSH keys, and it's sitting in a predictable location on every developer machine running these tools.

Check whether your credentials are already out there. It's free.

---

*RelayShield monitors 125 Telegram marketplaces for stealer logs, compromised credentials, and threat indicators. Check your exposure with our free Telegram or WhatsApp bot.*
