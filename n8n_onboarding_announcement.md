# n8n Onboarding Template — Announcement Copy

## n8n Community Forum post

```
Just shipped the bookend to an earlier template: automated identity checks on employee onboarding, not just offboarding.

Most onboarding automations handle one thing: create the account, grant access, done. This template adds the question that usually gets skipped — does this new hire's personal email already show signs of exposure (a breach, a stealer-log hit) before you hand them a corporate identity?

How it works:
1. Your HR system POSTs to a webhook when a new hire is ready to onboard
2. Two things happen in parallel, independently of each other: a RelayShield identity check on the personal email (breach + infostealer exposure), and account provisioning (Google Workspace or Microsoft Graph)
3. A risky personal email doesn't block day-one access — it's logged to Notion and flags Security in Slack as an awareness item, not a gate
4. Provisioning success/failure is tracked as its own separate outcome, so a failed account creation gets its own alert regardless of what the identity check found

Same shape as the offboarding template, opposite direction — check on the way in instead of the way out.

Live template: https://creators.n8n.io/workflows/17255

Happy to answer questions if anyone's adapting it for their own HR/IT stack.
```

## LinkedIn post

```
Shipped the other half of something I posted a while back: automated onboarding identity checks, not just offboarding.

The offboarding template checks whether a departing employee's credentials were already compromised. This one asks the same question on the way in: does a new hire's personal email already show signs of exposure — a breach, a stealer-log hit — before they get a corporate identity handed to them?

It doesn't block anything. Day-one provisioning goes ahead regardless — this is a security-awareness flag, not a hiring gate. What it does do: log the finding, alert your security team, and track account provisioning as its own independent outcome, so a failed Google Workspace/Microsoft Graph call gets flagged on its own, separate from whatever the identity check turned up.

Now live in n8n's template library: https://creators.n8n.io/workflows/17255

#SecurityAutomation #n8n #ITSecurity #Onboarding
```

## MSP brief update — proof point to add

Add to `RelayShield_MSP_Solution_Brief.md` (and regenerate the .pdf), alongside the existing offboarding proof point:

> **Onboarding, not just offboarding**: RelayShield's new-hire identity check is a published n8n template — HR webhook triggers a parallel breach + infostealer check on the incoming employee's personal email alongside Google Workspace/Microsoft Graph account provisioning, with independent audit logging for both. Bookends the existing offboarding template, covering the full employee lifecycle.

