---
title: "When the platform holding your keys is the breach: Northflank and stolen AI keys"
slug: northflank-stolen-api-keys
date: 2026-11-09
---

On October 30, Northflank told its customers to assume that every environment variable stored on its platform had been decrypted, and to rotate every key. That is about as blunt as a breach notice gets. When the system that holds your secrets is the thing that was breached, you cannot wait for a list of affected accounts before acting.

The timeline, as published on Northflank's status page, started with a threat alert from cloud security company Wiz at 11:43 UTC on October 30. Northflank reviewed it a minute later and patched at 12:02 UTC. By 13:58 UTC, customers were told to assume decryption and to rotate all keys. By 23:38 UTC, Northflank said users had reported unauthorized use of AI API keys supplied to the platform. Northflank's November 6 update adds that the first known decryption of secrets happened between 02:39 and 03:08 UTC on October 30, eight to nine hours before the first alert, and that the exploit was patched within 60 minutes of the alert and customers were notified within two hours. As of that November 6, 10:09 UTC update, Northflank had still not published a root cause or a count of affected customers, and said it will share a root cause analysis once findings are confirmed, so rotate broadly rather than narrowly. Northflank also said the attack was contained within an hour of the first alert, that running workloads were unaffected and the attack focused on secrets in its control plane, that customers on forward-deployed or dedicated control planes were unaffected, and that CVE-2026-98432 was patched across the fleet on November 2, without saying whether that CVE was how the attacker got in.

## Why a stolen AI key is different from a stolen password

Environment variables hold database passwords, cloud credentials, and API keys. An AI API key is a particularly costly one to lose, because it is a bearer key: whoever holds it can use it, and the service has no easy way to tell a thief from the legitimate owner.

Wiz calls the resulting abuse LLMjacking: using another organization's credentials to run models on that organization's account, running up charges or reselling the access. In two cases Wiz investigated, compromised credentials were used for about 2.5 million Amazon Bedrock API calls, generating roughly $100,000 in usage. Those are Wiz investigations, not a confirmed Northflank customer total. The point stands without it: a stolen AI key converts directly into someone else's bill.

## This was not one platform in one bad week

Northflank was the last of at least nine AI developer platforms that disclosed incidents in October, in Wiz's report "Black October for AI Developer Platforms". The list runs from Fireworks AI on October 6 to Northflank on October 30, and includes Railway, OpenCode, and Warp. Wiz found no single vulnerability linking all nine, and has not attributed them all to the same attackers. What they share is the target: stored environment variables, with a focus on the ones that grant AI access.

## What RelayShield monitoring does, and does not, do here

Be clear about the limit. This post is based on Northflank's status updates and Wiz's reporting, not on a RelayShield catch. It does not claim RelayShield caught Northflank, that Northflank indicators are in the RelayShield corpus, or that RelayShield stops a platform from losing its stored secrets. No monitoring tool can un-steal a key once it has left a breached control plane.

What RelayShield monitoring is built to surface is the next step: what happens to stolen credentials and indicators after they leave. RelayShield monitors 136 Telegram marketplaces, with 785K indicators and over 10 million citations, and its bots and free checks let you screen a suspicious link, wallet, or email before trusting it.

The deeper lesson is scoping. A bearer key that works everywhere, with no spending limit and no usage alert, is a blank check once stolen. A key scoped to one service, with a spending cap and a usage alert, still hurts if stolen, but it hurts in one place, for a bounded amount, and it shows up in a billing log quickly.

## What to do today

If you run anything on Northflank, or on any platform that has told you to rotate, do not rotate only the keys that already show abuse. Revoke at the issuing provider, not just inside the platform, generate replacements, and update the workloads and secret groups that used the old ones. Then review your AI provider usage and billing logs, and report anything suspicious to the platform and the provider.

For every other key, apply the same three controls now: scope each key to one service, set a spending cap and a usage alert on metered AI keys, and keep a rotation list you can run in an afternoon. The next breach notice may not name you. A scoped key with an alert does not need the notice to limit the damage.

Sources: Northflank status timeline and Wiz "Black October", as reported by TEISS and Qovery: https://www.teiss.co.uk/news/northflank-security-incident-leads-to-unauthorized-use-of-ai-api-keys-customers-told-to-rotate-credentials-18398 and https://www.qovery.com/blog/northflank-security-incident-secrets-own-cloud
