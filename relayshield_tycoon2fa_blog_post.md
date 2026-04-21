# MFA Was Supposed to Stop Them. Tycoon 2FA Just Bypassed It.

*Published April 2026 | RelayShield Blog*

---

You enabled multi-factor authentication. You did everything right.

You turned on the setting every security expert and IT team told you would protect your accounts. Every login now requires a one-time code from your phone. You felt protected.

Tycoon 2FA is a commercially sold tool that defeats MFA in real time — and it does not require any technical skill to use.

It has been deployed against Microsoft 365 and Google accounts at scale since at least 2023. In 2024, researchers at Sekoia tracked over 1,800 unique domains running Tycoon 2FA campaigns. It is a subscription service. Criminal operators pay a monthly fee, receive a ready-made phishing kit, and run automated MFA bypass attacks against your accounts. The barrier to entry is a credit card.

---

## What Tycoon 2FA Actually Does

Traditional phishing is about stealing your password. Tycoon 2FA is not interested in your password.

It steals your session.

Here is how it works in practice:

1. You receive a convincing phishing email — a fake Microsoft login page, a DocuSign notification, a SharePoint link from what appears to be a colleague
2. You click through and see a login page that looks identical to the real thing
3. You enter your username and password
4. The page prompts for your MFA code — the one-time code from your authenticator app or SMS
5. You enter it

At this point, most people believe MFA stopped the attack. It did not.

What happened instead: Tycoon 2FA is running as a **reverse proxy** — a live man-in-the-middle sitting between you and the real Microsoft or Google login server. It passed your credentials to the real server, received the MFA prompt, forwarded it to you, received your code, and forwarded that too. The authentication succeeded. A legitimate session was created.

And Tycoon 2FA stole the session cookie.

Your password is not what keeps you logged in after authentication. A session cookie is — a token that tells the server "this browser has already authenticated." Tycoon 2FA intercepts and captures that token before it reaches your browser. You are logged in normally. The attacker is also logged in, on their device, using the stolen cookie. Your MFA code authenticated both of you.

---

## Why This Changes Everything

The security industry has spent a decade telling people to enable MFA. That advice is not wrong. MFA still blocks the vast majority of credential stuffing attacks and password spraying. It remains worth having.

But Tycoon 2FA has moved the attack surface past the authentication layer entirely. The breach no longer happens at login. It happens after login, at the session layer — a place most identity protection services are not watching and most users do not know to check.

This matters because **session-layer compromise has different persistence characteristics than credential compromise.**

When an attacker steals your password, you can lock them out by changing it.

When an attacker steals your session cookie, changing your password does nothing. The session was created with valid authentication. It remains valid until it expires naturally or is explicitly revoked. A Microsoft 365 session token can persist for days or weeks depending on organisational policy. A Google session can persist indefinitely unless the account holder manually terminates it.

The attacker is inside your account. Your password change happened at the front door. They are already in the back room.

---

## The Attack Sequence Nobody Explains

What happens after session hijacking follows the same backdoor playbook as credential-based compromise — but faster, because the attacker has a fully authenticated session with no flags raised.

Within minutes of session capture:

- **Silent email forwarding rule created** — all incoming mail copied to attacker's address. Survives password resets, survives MFA re-enrollment, survives most account recovery flows.
- **Recovery options modified** — attacker's phone number or email added as a secondary recovery method. Enables account takeover even after the victim changes their password.
- **Inbox filters installed** — rules that delete password reset emails, security alerts, and bank notifications before they reach the inbox.
- **OAuth application granted persistent access** — a malicious or attacker-controlled application given read/write permission to mail, calendar, contacts, or files. OAuth tokens are not tied to session cookies or passwords. They persist independently.
- **Active session on attacker's device maintained** — the hijacked session itself, still valid, still watching.

This happens silently. No alert fires. No authentication fails. The account appears normal. The attacker reads every email you receive while appearing nowhere on your account's login history — because the session was legitimately created with your credentials and your MFA code.

---

## The Gap No Security Service Is Closing

Here is where the current identity protection market fails.

HIBP monitors for your credentials appearing in data breaches. Excellent tool. Does not detect session hijacking — session cookies are not the kind of data that appears in breach dumps.

Aura monitors for your personal information appearing on the dark web. Valuable. Does not detect active unauthorised sessions in your live accounts — that requires access to account activity data, not dark web scanning.

Your bank's fraud detection catches unusual transaction patterns. Effective for financial accounts. Does not monitor your email account's session list, forwarding rules, or OAuth grants.

Google and Apple send login notifications. Useful, but they only fire on new authentication events, not on existing sessions. And Tycoon 2FA produced a legitimate authentication event — the notification, if it fired, looked correct.

**Nobody is auditing active sessions, forwarding rules, OAuth app permissions, and recovery options as a unified response to a detected threat.** That is the gap.

---

## The Right Response to Session-Layer Attacks

The correct response to a suspected session hijacking — whether triggered by a phishing alert, a breach notification, or just a suspicious email — is a structured sweep in the right order.

**Step 1 — Terminate all active sessions immediately.**
Do not change your password first. Terminate sessions first. Every platform with an authenticated session layer has a "sign out of all devices" function. Use it before anything else. This kills the hijacked session before the attacker can establish more persistent access.

- **Google:** myaccount.google.com → Security → Your devices → Manage all devices → Sign out of all
- **Microsoft 365:** mysignins.microsoft.com → Active sign-ins → Sign out everywhere
- **Apple ID:** appleid.apple.com → Devices → Remove all unrecognised devices

**Step 2 — Audit and remove OAuth app permissions.**
Active sessions expire. OAuth grants do not. Check every application that has been granted access to your account and revoke anything you do not recognise or no longer actively use.

- **Google:** myaccount.google.com → Security → Third-party apps with account access
- **Microsoft:** myapps.microsoft.com → Review all connected applications

**Step 3 — Check forwarding rules and inbox filters.**
These persist independently of sessions, passwords, and OAuth tokens. A forwarding rule set during a 10-minute session hijacking window will still be active months later.

**Step 4 — Audit recovery options.**
Remove any recovery phone number or email address you did not add yourself.

**Step 5 — Change your password.**
Now. After the backdoors are swept. Not before.

**Step 6 — Re-enroll MFA using an authenticator app.**
If SMS MFA was in use, migrate to an authenticator app. SMS is vulnerable to SIM swap attacks independently of Tycoon 2FA. The combination of session hijacking and SIM swap represents the current ceiling of accessible credential attack capability.

This is the sequence. Most users who receive a phishing warning or breach alert skip straight to step 5 and consider the problem solved. Steps 1 through 4 go unchecked. The attacker remains.

---

## What RelayShield Does About This

RelayShield was built to guide users through this exact sequence — in the right order, at the right time, on WhatsApp, without requiring the user to know any of this in advance.

When a breach is detected on a monitored account, RelayShield scores its severity and immediately opens a remediation conversation:

> *"xyz@yahoo.com was found in a credential breach. Before resetting your password, reply SWEEP for a 5-minute Email Security Sweep — closes inbox backdoors that survive password resets."*

The Email Security Sweep covers all five layers: active sessions, OAuth app permissions, forwarding rules, inbox filters, and recovery options. In that order. With platform-specific instructions delivered conversationally.

Three days later, if the sweep is not confirmed complete, RelayShield follows up. Seven days after that if it is still open.

Session auditing and revocation is the first step in every remediation flow — because a password change that leaves an active session untouched has accomplished nothing.

**For businesses:** when employee credentials are detected in a breach, the business sweep includes guidance on auditing OAuth app grants at the organisational level (Microsoft Entra connected apps, Google Workspace third-party API access) — the surface area that most SMBs have no visibility into and that attackers increasingly target.

---

## The Honest Assessment

Tycoon 2FA does not make MFA useless. Enable it anyway — it still blocks most attacks that target your password directly.

What it reveals is that MFA was never designed to protect against session-layer attacks. It was designed to protect against password theft. Those are different problems. The security industry conflated them for years because session hijacking at this scale and accessibility is relatively new.

The response layer — sweeping for backdoors, auditing sessions and OAuth grants, following up until remediation is confirmed — is what closes this gap. No credential monitoring service, dark web scanner, or credit bureau is doing this work for you.

That is the gap RelayShield fills.

---

## Get the Response Layer

RelayShield is available now with a founding member offer for Personal Shield subscribers.

**Personal Shield — $12/month for your first 3 months** (then $14.99/month)
Real-time breach monitoring, WhatsApp alerts with AI severity scoring, Email Security Sweep including active session audit and OAuth revocation guidance, and remediation tracking for individuals.

**Business Basic — [Sign up at relayshield.net](https://relayshield.net/)**
Everything in Personal Shield, plus team monitoring for up to 5 employees, domain-level breach scanning, organisational OAuth audit guidance, and admin visibility across your workforce.

Founding member spots are limited. When they fill, standard pricing applies to all new subscribers.

→ **[Secure My Account](https://relayshield.net)**

---

*RelayShield is built by a 25-year telecom security professional. We do not store passwords, do not sell your data, and do not use a CRM with PII access. AI remediation is powered by Claude.*
