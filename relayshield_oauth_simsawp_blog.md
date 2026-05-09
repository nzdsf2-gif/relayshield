# The Attack That Survives Your Password Reset

*How attackers chain OAuth breaches with SIM swaps to defeat every layer of your security — and why no consumer tool detects it*

*By Andrew Gibbs, RelayShield | May 2026*

---

> **Platform notes**
> - **LinkedIn:** Use as written. Add 3-line hook before title for preview. Hashtags at end: #cybersecurity #identitysecurity #SIMswap #OAuth #infosec #identityprotection
> - **Medium:** Use as written. Subtitle: "The two-signal attack chain that defeats every layer of traditional identity protection." Consider adding attack chain diagram.
> - **Reddit (r/cybersecurity, r/netsec, r/privacy):** Remove the closing CTA section. Lead with: *"I've been building a multi-vector attack correlation engine and wanted to write up the OAuth + SIM swap chain because it's the most underappreciated attack pattern I've seen. Not a sales pitch — just want to discuss the detection architecture."* Post the technical detection section prominently. Engage comments seriously.

---

When a company you use gets breached, you know what to do: change your password, enable 2FA, move on.

That playbook used to work. It doesn't anymore.

There's a class of attack growing in sophistication and frequency — one where the victim's password was never exposed, their 2FA was never bypassed, and no breach notification service ever fired an alert. By the time the victim realises something is wrong, the attacker has been inside their accounts for days.

It starts with an OAuth token. It ends with your SIM.

---

## What Is an OAuth Token — and Why Should You Care?

When you click "Sign in with Google" on a third-party app — Slack, GitHub, Notion, Zapier, Vercel — you are issuing that app a long-lived credential called an OAuth token. This token allows the app to act on your behalf within Google (or Microsoft, or GitHub) without ever knowing your password.

OAuth tokens are the lifeblood of the modern productivity stack. The average knowledge worker has granted OAuth access to 40–60 applications. They are also one of the most significant and undermonitored attack surfaces in identity security.

Here's the critical detail most people don't know: **OAuth tokens don't expire when you change your password.** They can persist for months or years. They're stored in the third-party app's database, not yours — and if that app is breached, the attacker gets your token without ever touching your account or triggering a single credential alert.

---

## The Attack Chain in Full

**Step 1: A SaaS app you use gets breached.**

Maybe it's a developer tool. Maybe it's a project management platform. The breach may not make front page news — dozens of smaller SaaS companies suffer credential exposure each month. The attacker's target isn't the SaaS app's own data. It's the OAuth tokens it holds on behalf of its users.

In April 2026, the Vercel/Context.ai incident demonstrated exactly this: attackers breached a third-party AI tool, extracted stored OAuth tokens, and used them to pivot into a Vercel employee's Google Workspace. The employee's credentials were never exposed. HIBP never fired. No existing identity protection service detected it.

**Step 2: The attacker extracts your OAuth token from the breached database.**

With a valid OAuth token, they can authenticate to your Google or GitHub account as if they were you. No password required. No 2FA prompt triggered in most configurations. The token *is* the credential — and it arrived in the attacker's hands through a breach you had no control over.

**Step 3: The attacker hits a problem — and solves it.**

Some high-value actions still trigger a 2FA challenge. To eliminate this last obstacle, the attacker initiates a SIM swap: a social engineering attack on your mobile carrier that transfers your phone number to a SIM card they control. This is where 25 years of telecom security experience tells me this attack is far more achievable than most people realise — carrier verification processes have known weaknesses, and SIM swap fraud is a documented, scaled criminal industry.

**Step 4: Your phone goes dark.**

No calls. No texts. No 2FA codes. Every security notification your carrier, bank, or Google would send you is now going to the attacker's device.

**Step 5: With your OAuth token plus phone control, they own everything connected to your account.**

Vercel deployments. GitHub repositories. Any downstream service that trusts your Google or GitHub identity. They change recovery emails, revoke your own access, and move quietly through your infrastructure.

**Total attack window from first exploitation to full compromise: often under 72 hours.**

---

## Why Your Current Tools Don't See This

| Tool | What it monitors | Why it misses this attack |
|---|---|---|
| HIBP / breach monitors | Credential databases — emails and passwords | If your password wasn't in the breach, it doesn't fire |
| Bank fraud detection | Unusual transactions | Fires after the account is already compromised |
| Carrier SIM swap notification | Sends SMS to confirm SIM change | Sent to the number the attacker now controls |
| LifeLock / identity protection services | Credit file, SSN, dark web | OAuth tokens are not in your credit file |
| Antivirus / EDR | Device-level threats | OAuth attacks happen server-side, no malware involved |

Not one of these tools monitors the OAuth layer. Not one correlates a SaaS breach signal with a SIM swap signal on the same user. The attack runs completely beneath every existing detection surface.

---

## The 72-Hour Window

The reason temporal correlation matters: sophisticated attackers don't execute all steps simultaneously. The SaaS breach happens first — it may be days before the OAuth token database is extracted, indexed, and sold. The targeted SIM swap follows, once a specific high-value target has been identified from the token database.

This creates a detection window. If you know a SaaS app was breached and you know a SIM swap occurred on the same user's number within the following 72 hours, the co-occurrence is not coincidence — it's a coordinated campaign in progress.

No consumer or SMB product was monitoring this window. Until we built it.

---

## How RelayShield Detects This Chain

RelayShield runs a 72-hour rolling signal window on every subscriber account. Every alert-generating event — SaaS breach detection, SIM swap, suspicious link reported, unexpected OTP — is recorded as a timestamped signal.

When a SaaS app on our watchlist is breached (we monitor 40+ apps: Slack, GitHub, Notion, Zapier, Linear, Vercel, HubSpot, and others), we fire an `oauth_app_breach` signal for active subscribers. At that moment, we also send a predictive warning — before the second attack vector arrives:

> *"A SaaS app you've granted OAuth access to was breached. Consider locking your SIM now — attackers combine OAuth breaches with SIM swaps to bypass all remaining 2FA. Steps: [SIM lock instructions]"*

If a SIM swap is detected on that subscriber's number within the 72-hour window, the correlation engine fires a CRITICAL composite alert:

> *"🚨 CRITICAL — Coordinated attack detected. A SaaS app you've granted OAuth access to was breached AND your SIM was swapped within 72 hours. The attacker may hold your OAuth tokens AND control your phone number. Revoke all OAuth grants immediately: myaccount.google.com/permissions"*

The alert includes exact revocation steps for Google, Microsoft, and GitHub — prioritised by the specific app that was breached.

**This is the only consumer or SMB product monitoring the OAuth supply chain layer and correlating it with carrier-level SIM swap telemetry in real time.**

---

## What You Can Do Right Now

Whether you use RelayShield or not, three steps materially reduce your exposure to this attack:

**1. Audit your OAuth grants today.**
Go to [myaccount.google.com/permissions](https://myaccount.google.com/permissions). Revoke every app you no longer use actively. For Microsoft: [myaccount.microsoft.com/permissions](https://myaccount.microsoft.com/permissions). For GitHub: Settings → Applications → Authorized OAuth Apps.

**2. Add a SIM PIN to your carrier account.**
Call your carrier and add a PIN required for any SIM changes. AT&T: "Extra Security." Verizon: "Number Lock." T-Mobile: "SIM Protection" in the app. This is the single highest-leverage action you can take against SIM swap attacks — it costs nothing and takes five minutes.

**3. Treat OAuth grants like admin access.**
Every time you click "Sign in with Google," you're extending your attack surface to include that app's security posture. Grant minimally. Audit quarterly. Revoke immediately whenever a connected service reports a breach.

---

## The Larger Pattern

The identity attack surface has expanded dramatically beyond passwords. The perimeter is now every app you've ever authorised, every SIM card you've ever trusted, every service that knows your phone number.

Attackers have figured this out. The security industry largely hasn't caught up — most consumer identity protection was designed for a world where credential theft meant a username and password in a breach database. That world is gone.

The next generation of identity attacks are coordinated, multi-vector, and timed across days — not seconds. Detecting them requires correlating signals across independent channels: breach data, carrier telemetry, user-reported anomalies, and OAuth supply chain events simultaneously.

That's what we built at RelayShield. And it's why we believe the signal correlation layer is where the durable moat in identity protection lies — not breach monitoring alone, but the synthesis of signals no single tool was ever designed to see together.

---

*RelayShield is an AI-native identity protection service delivering real-time breach alerts, SIM swap detection, OAuth supply chain monitoring, and multi-vector attack correlation via WhatsApp and Telegram. Personal Shield starts at $9.99/month.*

*→ [relayshield.net](https://relayshield.net)*
*→ Telegram: [@RelayShield\_bot](https://t.me/RelayShield_bot)*

---

*#cybersecurity #identitysecurity #SIMswap #OAuth #infosec #identityprotection #cyberthreats #datasecurity*
