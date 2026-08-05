# n8n Offboarding Template — Announcement Copy

## n8n Community Forum post

```
Just shipped a new n8n template: automated credential-risk checks on employee offboarding.

Most offboarding checklists stop at "disable the account." This template catches something checklists usually miss: whether the departing employee's credentials were *already* compromised before they left — a breach, a stealer-log hit, or an exposed OAuth token that could keep working after their account is disabled.

How it works:
1. Your HR system POSTs to a webhook when someone's offboarded
2. Three parallel RelayShield checks run: breach exposure, infostealer log detection, and OAuth/API token exposure
3. If anything's found, it posts to Slack, emails the departing employee's manager with a summary, and logs the finding to Notion for audit
4. Clean results get logged too, so every offboarding is auditable either way

Live template: https://n8n.io/workflows/16694

Built this after realizing most offboarding automations only handle access revocation, not the credential-integrity question underneath it. Happy to answer questions on the RelayShield side if anyone's adapting it.
```

## LinkedIn post

```
Shipped something useful for security/IT teams: an n8n template that catches a gap in most offboarding checklists.

Standard offboarding: disable accounts, revoke access, done. What it usually misses — were this person's credentials already compromised before they left? A breach, a stealer-log hit, an exposed OAuth token — any of these can keep working even after the account itself is disabled.

This template runs three checks automatically the moment HR marks someone offboarded: breach exposure, infostealer log detection, and OAuth/API token exposure. Anything found gets routed to Slack, emailed to the manager, and logged for audit. Clean results get logged too — every offboarding becomes auditable, not just access-revoked.

Now live in n8n's official template library: https://n8n.io/workflows/16694

If you're running employee offboarding through n8n already, this drops in alongside whatever access-revocation automation you have.

#SecurityAutomation #n8n #ITSecurity #Offboarding
```

## MSP brief update — proof point to add

Add to `RelayShield_MSP_Solution_Brief.md` (and regenerate the .pdf):

> **Live automation, not just an API**: RelayShield's employee-offboarding credential check is a published, officially-approved template in n8n's workflow library (n8n.io/workflows/16694) — HR webhook triggers three parallel identity-risk checks (breach, infostealer, OAuth token exposure), routing findings to Slack/Notion/manager email automatically. This isn't a hypothetical integration — it's live, installable today, built on the same API MSPs get access to directly.
