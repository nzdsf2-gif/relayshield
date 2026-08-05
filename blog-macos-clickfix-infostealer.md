# Your Mac Told You to Run a Command. You Did. Now Your Passwords Are Gone.

*The macOS ClickFix attack nobody warned you about — and what to do if you've been hit.*

---

A new attack targeting Mac users is spreading fast, and it works by doing something almost no one expects: it asks you to help install the malware yourself.

Security researchers have identified a technique called **ClickFix** that's now being used against macOS. The attack silently mounts disk images (DMGs) — the same installer format used by legitimate Mac apps like Zoom and Slack — and uses them to install infostealer malware. Once installed, the malware quietly harvests every saved password, browser session cookie, and stored credential on your device and sends them to attackers.

The worst part: you probably won't notice until it's too late.

---

## How It Works (In Plain English)

You're browsing the web. You hit a page that looks broken — maybe a video won't load, or a CAPTCHA seems stuck. A message appears asking you to "fix" the issue by following a few steps. It looks legitimate. Maybe it has a logo you recognise.

The steps ask you to open Terminal or run a command — something that sounds technical but is presented as routine. You follow the instructions. Nothing obviously happens.

What actually happened: you just ran a script that mounted a hidden DMG file and silently installed an infostealer. In the background, it's now:

- Exporting every saved password from Chrome, Safari, and Firefox
- Stealing active session cookies — the tokens that keep you logged into Gmail, your bank, your work tools
- Copying crypto wallet files if you have any
- Sending everything to a remote server

The session cookies are the most dangerous part. With those, an attacker doesn't need your password. They don't need to bypass your two-factor authentication. They just replay the cookie from their device and they're in — as you.

---

## Why Macs Are Being Targeted Now

For years, Mac users operated with a false sense of security. Malware was a Windows problem. That's no longer true.

Mac market share has grown significantly, particularly among business professionals, creative agencies, and high-value individuals — exactly the targets that make credential theft profitable. Attackers have followed the money.

ClickFix attacks have been devastating on Windows for over a year. Adapting them to macOS was the obvious next step, and it's happening now.

---

## How to Know If You've Been Hit

You won't get a warning. No antivirus alert. No slowdown you'd notice. Infostealers are designed to be invisible.

Signs to watch for:
- You receive a login alert from an account you didn't access
- You're suddenly logged out of services for no reason (the attacker revoked your session after taking it over)
- You notice unfamiliar activity in your email sent folder
- A friend tells you they received a strange message from you

By the time you notice any of these, the credentials are already gone.

The more reliable approach: **check before it becomes obvious.**

---

## What To Do Right Now

**If you think you ran a suspicious command recently:**

1. **Do not change your passwords yet** — if the malware is still active on your device, it will capture your new passwords the moment you type them
2. Run a malware scan first: [Malwarebytes for Mac](https://www.malwarebytes.com) has a free version
3. Once you're confident the device is clean, **revoke all active sessions** before changing passwords:
   - Google: myaccount.google.com → Security → Your devices → Sign out all
   - Microsoft: account.microsoft.com → Security → Sign-in activity
   - Apple: Settings → your name → scroll down → sign out all devices
4. Then change passwords, starting with email (email access = access to everything else)
5. Check whether your email appeared in any credential breaches: [haveibeenpwned.com](https://haveibeenpwned.com)

**If you're not sure whether you've been targeted:**

Check your email for infostealer exposure. RelayShield's infostealer monitor checks your email address against Hudson Rock's criminal credential database — one of the most comprehensive sources of real infostealer log data available. If your credentials appeared in a stealer log, you'll know within minutes.

→ **Check your email at relayshield.net** (free for personal use)

---

## For Business Owners and IT Teams

If your employees use Macs — especially if they work from home on personal devices — this attack is a direct threat to your business systems.

A single compromised employee session can give an attacker access to your Slack workspace, your Google Drive, your GitHub repositories, or your CRM. They don't need to break through your firewall. They just need one set of stolen cookies.

**Practical steps for teams:**

- Brief employees on ClickFix — show them this article
- Enforce short session timeouts on critical business tools
- Require hardware security keys (YubiKey) for admin accounts
- Run periodic infostealer checks on employee email addresses — RelayShield's API supports bulk employee monitoring

---

## The Bigger Picture

ClickFix is part of a broader shift in how attackers operate. Breaking into systems is hard. Tricking users into handing over access is easy.

Password managers help. Two-factor authentication helps. But neither protects you once your session cookie is stolen from a compromised device. The only defence at that point is detecting the theft early — before the attacker has time to act on it.

That's exactly what credential and infostealer monitoring is for.

---

*RelayShield monitors your email addresses for infostealer exposure, credential breaches, and active session theft — and alerts you via WhatsApp or Telegram the moment something is found. Check your exposure at relayshield.net.*
