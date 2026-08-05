> **STATUS: Draft — hold for Monday publish**

# Remus Stealer: The New $250-a-Month Infostealer Renting Out Your Google Session

Flashpoint first spotted it for sale in criminal marketplaces in March 2026. By the time most security teams heard the name, it was already a working product with a price list.

Remus Stealer isn't a novel piece of malware engineering. It's something more troubling: a well-packaged, professionally distributed clone of an existing threat, sold as a subscription to anyone willing to pay.

---

## A Familiar Threat, Repackaged and Resold

Remus shares deep similarities with the Lumma malware family — the administration panel, the stolen-log file structure, and much of the core code are close enough that researchers describe it as derivative rather than original. That's not a reassuring detail. It means the same proven playbook that made Lumma one of the most prolific credential-theft operations of the past two years is now available under a new name, with a new storefront, to a new wave of buyers.

What Remus adds isn't cleverer malware — it's better infrastructure. A modern command-and-control layer and networking setup designed specifically to slip past the security perimeters that have caught up to older stealer families. The malware evolves less than the delivery pipeline around it.

---

## Malware-as-a-Service, Priced Like Software

Remus is sold on a three-tier subscription model, the same shape as any legitimate SaaS pricing page:

- **Basic** — $250
- **Pro** — $500
- **Enterprise** — $1,000

Buyers aren't writing exploit code. They're subscribing to a service, the same way a legitimate business subscribes to a CRM. The tiers unlock more features, more automation, more support — for stealing your data instead of managing your customers.

Two features stand out. **Google OAuth cookie restoration** lets a buyer regenerate access to a victim's Google session even after the victim has logged out or changed their password — turning a one-time credential theft into a persistent backdoor. **Telegram channel integration for logs** means stolen data doesn't sit on a private server waiting to be sold later; it streams directly into criminal Telegram channels, the same underground marketplaces where RelayShield's threat intelligence corpus already tracks infostealer activity in real time.

---

## Why This Matters Beyond One Malware Family

Remus is a symptom, not an isolated incident. The infostealer economy has matured into exactly the kind of market structure that makes any threat harder to stamp out: low barrier to entry, proven code reused under new branding, and pricing that puts industrial-scale credential theft within reach of buyers with no technical skill at all.

Every subscriber to Remus — Basic, Pro, or Enterprise — is running a tool built to do one thing: harvest session cookies, saved passwords, and OAuth tokens, then get that data out fast, before the victim notices anything is wrong. The OAuth cookie restoration feature in particular should worry anyone who assumes "I changed my password" means an incident is over. It often doesn't, if the attacker regenerated the session before you rotated your credentials.

---

## What To Do About It

**1. Treat OAuth revocation as separate from password resets.** If you suspect any account compromise, don't stop at changing your password — revoke connected sessions and app access directly at `myaccount.google.com/permissions` (and the equivalent for Microsoft, Apple, and any other OAuth provider you use). A restored cookie doesn't care that your password changed.

**2. Assume stolen credentials move fast.** Remus streams logs directly into Telegram channels — there's no lag between theft and resale. If your credentials are exposed, the exposure window is measured in hours, not weeks.

**3. Monitor for your own exposure, not just your organization's.** Infostealer logs from families like Remus and Lumma are exactly what RelayShield's threat intelligence corpus tracks — 1,000+ malware families, updated continuously from the same criminal channels these logs get sold in.

---

## The Broader Pattern

Malware-as-a-service didn't create new threats — it removed the skill requirement from old ones. Every new stealer family that reuses Lumma's playbook under a fresh name is evidence that the economics favor volume over innovation: cheap to build on proven code, easy to distribute through a subscription model, and priced low enough that the buyer pool keeps growing.

The defense has to match that shape. Detecting one malware family doesn't help if the next clone ships under a new name next quarter. What matters is watching the infrastructure these tools actually depend on — the Telegram channels where logs get sold, the C2 patterns that repeat across "new" families, and the credential exposure itself, regardless of which stealer produced it.

---

*RelayShield tracks 1,000+ malware families — including LummaC2, RedLine, Vidar, and now Remus — across 20+ authoritative feeds and criminal Telegram channels, updated continuously. Breach and infostealer exposure monitoring is available for individuals via WhatsApp/Telegram alerts, for security teams via API, and as a flat-rate TI Starter/Unlimited subscription directly on AWS Marketplace.*

*[Start monitoring → relayshield.net]*
