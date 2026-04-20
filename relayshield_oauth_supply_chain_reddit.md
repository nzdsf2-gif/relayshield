# Reddit Post — OAuth Supply Chain Attack: Vercel/Context.ai
*Target subreddits: r/netsec, r/cybersecurity, r/sysadmin, r/devops*
*Ready to post: April 26, 2026*

---

## TITLE
The Vercel hack is a clean example of why "my credentials weren't leaked" is no longer sufficient protection

---

## POST BODY

Vercel's recent breach didn't start with a phishing email or a leaked password. It started with a trusted third-party app.

Here's the chain as reported:

1. Attackers breached Context.ai — an AI tool that employees use to provide "context" to AI assistants (reads files, emails, etc.)
2. Context.ai held OAuth tokens for connected Google accounts — including a Vercel employee's corporate Google Workspace
3. Attackers used those stored tokens to access the employee's Google account directly
4. From inside Google Workspace, they escalated into Vercel's internal production infrastructure
5. They read environment variables marked as "non-sensitive" and therefore unencrypted at rest

The employee's credentials were never compromised. No password was stolen. MFA was never bypassed. HIBP never fired. The attack entered through a legitimate OAuth grant the employee had made weeks or months earlier — and that grant lived in Context.ai's database, not in any system the employee controlled.

---

**Why this attack chain is structurally different**

Traditional breach response assumes a credential compromise starting point:
- Credentials appear in breach data → HIBP / monitoring service alerts → user changes password → done

OAuth supply chain attacks break this model entirely:

```
App you trusted is breached
→ Attacker has your OAuth token (not your password)
→ No credential exposure
→ No HIBP alert
→ No password to change
→ Attacker has authenticated access to your Google/Microsoft account
→ Pivots to whatever that identity can reach
```

The OAuth token is a long-lived credential that the app stores on its servers. When you grant an app access to your Google account, you're issuing a key that lives in that app's database. If their database is compromised, the attacker has a key to your account — and you have no way of knowing until they use it.

---

**What makes this worse for enterprise environments**

OAuth tokens granted to productivity and AI tools frequently have broad scopes:
- Read all mail
- Read all Drive files
- Read calendar
- Read contacts

"Context" tools specifically often request wide read access by design — they need to see your files and email to do their job. That's the exact grant an attacker wants.

For an employee at a company like Vercel, a Google Workspace identity is a master key to substantially more than personal email. It's often the SSO identity for internal tools, CI/CD systems, cloud consoles, and deployment infrastructure. The blast radius of a Google Workspace compromise extends far beyond the inbox.

---

**The defensive steps that actually apply here**

1. **Audit your OAuth grants now.** Go to myaccount.google.com/permissions. Look at every app listed. Remove anything you don't recognise, no longer actively use, or that has broader scope than it needs.

2. **Same for Microsoft:** myapps.microsoft.com

3. **Principle of least privilege on OAuth scopes.** When an app requests access, check what it's asking for. If a "context" or AI tool is requesting write access, that's a red flag. Read-only scopes limit blast radius if the app is compromised.

4. **Treat third-party SaaS apps as an extension of your attack surface.** Their security posture directly affects yours. This is especially true for AI tools, productivity integrations, and anything that connects to your email or file system.

5. **Environment variables marked "non-sensitive."** The second stage of this attack exploited the assumption that non-sensitive env vars don't need encryption at rest. If it's in production infrastructure, it's sensitive enough to encrypt.

---

**The detection gap nobody is filling**

Current identity monitoring services (HIBP, dark web scanners, credit monitoring) all assume credential compromise as the starting point. None of them:

- Monitor whether third-party apps you've connected to have themselves been breached
- Alert you to revoke specific OAuth grants when a connected app is compromised
- Correlate a SaaS breach with your existing OAuth grants

The monitoring category is built around "your credentials leaked." The attack surface has moved. OAuth supply chain is the gap.

---

Curious whether anyone has seen tooling that actively monitors the OAuth grant layer — not just the credential layer. The HIBP Breaches API at least lets you poll for newly indexed breaches and cross-reference against a watchlist of apps your users have connected. That seems like the most tractable near-term approach.
