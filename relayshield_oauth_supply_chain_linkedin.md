# LinkedIn Article — OAuth Supply Chain Attack
*Ready to post: April 26, 2026 — replaces IoT blog in content calendar*

---

## TITLE
The Vercel Hack Wasn't About a Stolen Password. It Was About a Trusted App With the Keys to the Kingdom.

---

## ARTICLE BODY

The employee's credentials were never compromised.

No phishing email worked. No password was leaked. Multi-factor authentication was never bypassed. If you ran their email through any breach monitoring service the day before the attack, it would have come back clean.

And yet attackers made it into Vercel's production infrastructure.

Here's how.

---

**The Attack Chain**

Vercel's breach started not with Vercel — but with Context.ai, a third-party AI tool that employees had connected to their corporate Google accounts.

AI productivity tools like Context.ai need broad access to do their job. They read your emails, your files, your calendar — all to provide relevant "context" to AI assistants. To do that, they ask you to grant OAuth access to your Google or Microsoft account. You click Allow. The tool stores that access token in its database. You forget about it.

Context.ai was breached. Attackers took control of its OAuth application and accessed the stored tokens.

One of those tokens belonged to a Vercel employee's corporate Google Workspace account.

From there:

1. Attackers used the stolen OAuth token to authenticate as the Vercel employee — no password required
2. Inside Google Workspace, they found pathways into Vercel's internal production systems
3. They read environment variables marked as "non-sensitive" and therefore stored unencrypted at rest

The attack took place entirely behind the authentication layer. It never triggered a login alert. It never showed up in breach data. There was no unusual sign-in to detect because the OAuth token was legitimate — it had been issued with the employee's full consent, weeks or months earlier.

---

**Why This Is Structurally Different From Every Breach You've Heard About**

The entire identity protection industry is built on one assumption: breaches start with credential compromise.

Your email appears in a breach database → a service alerts you → you change your password → you're protected.

OAuth supply chain attacks break this model completely.

```
Traditional breach:      Your credentials leaked
                         → attacker logs in as you

OAuth supply chain:      App you trusted is breached
                         → attacker uses their stored token
                         → your credentials were never touched
                         → HIBP never fires
                         → no password to change
                         → attacker has full authenticated access
```

The OAuth token is a long-lived credential that lives in someone else's database. When you grant an app access to your Google or Microsoft account, you're issuing a key — and that key lives on their servers, subject to their security posture, not yours.

If their database is compromised, the attacker has your key. And you have no indication that anything has happened until they use it.

---

**The Scope Problem**

OAuth tokens are not created equal. The permissions attached to them — called scopes — determine what an attacker can do once they have the token.

Productivity and AI tools often request the broadest scopes available, because that's what they need to function:

→ Read all mail
→ Read all Drive files
→ Read calendar and contacts
→ In some cases, send mail and manage files

For an individual user, that's significant. For a corporate employee at a technology company, a Google Workspace identity is often the SSO credential for every internal tool they use — code repositories, deployment pipelines, cloud infrastructure consoles, internal databases.

A single OAuth token from a single AI assistant can be the first step into production infrastructure. That is what happened at Vercel.

---

**The Gap No Monitoring Service Is Watching**

The question worth asking about any identity protection service you use — whether it's a consumer tool or an enterprise product — is this: does it monitor the OAuth layer?

Not just your credentials. The apps you've trusted with access to your credentials.

Most services do not. They monitor breach databases for your email address. They watch for your information on dark web marketplaces. They alert you when your password is leaked.

None of them tell you when an app you granted access to has itself been compromised. None of them correlate a SaaS breach with your existing OAuth grants and say: "This app was just breached — revoke its access to your Google account immediately."

That is the monitoring gap the Vercel attack exposes.

---

**What You Should Do Right Now**

This is not a theoretical risk. AI tools, productivity integrations, and developer tools routinely request broad OAuth access. Most people have granted this access to applications they no longer actively use, whose security posture they cannot assess, and whose breach they would never hear about.

**Step 1 — Audit your Google OAuth grants**
Go to myaccount.google.com/permissions
Review every application listed. Remove anything you don't recognise, no longer use, or that has broader access than it needs.

**Step 2 — Audit your Microsoft OAuth grants**
Go to myapps.microsoft.com
Same process — remove unrecognised or unnecessary applications.

**Step 3 — Apply this to your team**
If you manage employees, they have each individually granted OAuth access to the tools your company uses. Each of those grants is a potential entry point. An OAuth audit is not a one-time IT exercise — it should be part of your regular security hygiene, the same way password rotation used to be.

**Step 4 — Treat scope as a security decision**
When any app — especially an AI tool — requests access to your email and files, check what it's actually asking for. Read-only access to specific folders is meaningfully different from read/write access to all mail. Least privilege applies to OAuth scopes.

---

**The Broader Lesson**

The security industry has spent a decade focused on credential security — passwords, MFA, phishing resistance. That work is not wasted. Credential attacks remain the most common entry point.

But the attack surface has expanded. OAuth supply chain is a category of identity attack that bypasses every credential security control you have — not by defeating them, but by going around them entirely. The attack happens at the layer below your credentials: the apps you trusted to act on your behalf.

The response layer for this attack is OAuth hygiene: regular audits, least-privilege scope selection, and — critically — immediate revocation when a connected app is reported compromised. No current consumer or SMB identity protection service delivers this automatically.

That is the gap worth watching.

---

If this is useful, follow RelayShield for more plain-language analysis of the identity attack vectors your current tools aren't monitoring.

*Built by a 25-year telecom security professional. relayshield.net*

---

## HASHTAGS
#CyberSecurity #IdentityProtection #OAuth #DataBreach #InfoSec #SmallBusiness #CloudSecurity #GoogleWorkspace #Microsoft365 #CyberAwareness

---

## TEASER POST (paste into "Tell your network" box)

Vercel's production environment was breached. The employee's password was never leaked.

The attack came through a trusted AI tool that had OAuth access to their Google account. No credential compromise. No MFA bypass. No HIBP alert.

This is the identity attack vector no monitoring service is watching.
