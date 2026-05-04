# RelayShield — Reddit Marketing Drafts

Account: u/BothFan5617
Tone: value-first, problem/solution, native to each subreddit — no spam, no hard sell.
Andrew posts manually and engages in comments.

---

## r/netsec — PyPI Supply Chain (post Wednesday May 6 2026)

**Title:** TeamPCP compromised LiteLLM, Telnyx, and PyTorch Lightning via a single misconfigured GitHub Actions workflow — here's the full chain

**Body:**
Been tracking the TeamPCP supply chain campaign that ran through March and April. The attack chain is worth understanding because it started in a place most teams aren't watching.

**How it started:**
TeamPCP identified a misconfigured `pull_request_target` workflow in Trivy — a widely-used open source security scanner. That trigger runs with elevated repository permissions and, when misconfigured, exposes secrets to pull requests from forks. They used it to exfiltrate a personal access token.

**What they did with it:**
- Pushed malicious commits to 76 of 77 Trivy GitHub Action version tags
- Used the compromised Trivy action as a foothold to steal maintainer credentials downstream
- Published malicious versions of LiteLLM (1.82.7, 1.82.8 — March 24), Telnyx (4.87.1, 4.87.2 — March 27), and PyTorch Lightning (2.6.2, 2.6.3 — April 30)

**What the malicious versions harvested:**
Environment variables, SSH keys, AWS/GCP/Azure credentials, Kubernetes configs, Docker configs, shell history, database credentials, CI/CD pipeline secrets, and wallet files — all exfiltrated on install.

LiteLLM alone runs at ~3.4 million downloads per day. The blast radius during even a 24-hour window is significant.

**The AI stack targeting is deliberate:**
LiteLLM routes calls to Anthropic, OpenAI, Google, etc. Developers running it typically have high-value API keys in their environment. Targeting AI infrastructure packages maximises credential value per compromised machine.

**Three mitigations worth prioritising:**

1. Audit any workflow using `pull_request_target` — it should not have access to secrets unless you explicitly need it and have scoped it carefully
2. Pin dependencies in CI — `pip install litellm==1.82.6` instead of latest. Review upgrades before applying
3. PyPI Trusted Publishing — eliminates stored API tokens by using short-lived OIDC tokens tied to your GitHub repo. No token to steal

If you ran LiteLLM, Telnyx, or Lightning in the affected version windows and haven't rotated credentials yet, assume exfiltration occurred.

Happy to go deeper on the GitHub Actions misconfiguration vector — it's underappreciated as an initial access technique.

---

*[Comment, not in post body]* For teams wanting programmatic breach and supply chain monitoring, I built a B2A API and MCP server for this — relayshield-mcp on PyPI, API on RapidAPI. Not the point of this post but happy to share if useful.

---

## r/Python — PyPI Supply Chain (post Wednesday May 6 2026)

**Title:** If you ran LiteLLM, Telnyx, or PyTorch Lightning between March 24 and May 1 — rotate your credentials

**Body:**
Not trying to be alarmist but this one is worth knowing about if you haven't seen it.

Between March and April 2026, attackers compromised multiple popular Python packages and used them to harvest developer credentials on install. The affected packages and windows:

- **LiteLLM 1.82.7 and 1.82.8** — March 24–25
- **Telnyx 4.87.1 and 4.87.2** — March 27–28
- **PyTorch Lightning 2.6.2 and 2.6.3** — April 30–May 1

The malicious code ran silently on `pip install` and exfiltrated environment variables, SSH keys, cloud credentials, and CI/CD pipeline secrets to attacker-controlled infrastructure.

The attack started with a misconfigured `pull_request_target` GitHub Actions workflow in Trivy that leaked a maintainer token — which was then used to push directly to PyPI without going through normal code review.

**If you installed any of these in the affected windows:**
- Rotate your AWS/GCP/Azure credentials
- Rotate any API keys in your environment (OpenAI, Anthropic, etc.)
- Rotate SSH keys
- Check for any new CI/CD pipeline secrets that were active during that period

**Three things worth doing going forward:**

1. **Pin your dependencies** — `pip freeze > requirements.txt` and review upgrades before applying them in production
2. **Use project-scoped PyPI tokens** if you publish packages — account-wide tokens are too broad
3. **Enable PyPI Trusted Publishing** — it removes stored API tokens from the equation entirely by using OIDC. Setup takes about 20 minutes and is worth it

The supply chain attack surface for Python packages is real and the AI ecosystem is being targeted specifically because of the high-value credentials developers in that space carry.

Happy to answer questions about the attack chain or the mitigations.

---

## r/smallbusiness

**Title:** After my vendor got breached, I realized changing my password wasn't enough — here's what actually protects you

**Body:**
A supplier we use got hit in a breach earlier this year. I changed my password with them immediately, felt good about it, moved on.

Three weeks later I found out attackers had used that breach to get into a connected email account — because I never revoked the OAuth access the supplier's app had. The password reset didn't touch it.

That's what nobody explains: modern attacks don't need your new password. They use the backdoors you leave open when you reset. Gmail forwarding rules, OAuth grants to third-party apps, recovery email addresses — these all survive a password reset and give attackers persistent access.

What actually helps after a breach:

1. **Revoke active sessions first, before you change the password** — otherwise whoever's in stays in
2. **Audit OAuth grants** — myaccount.google.com/permissions — remove anything you don't recognise
3. **Check your email for forwarding rules you didn't set** — attackers love these because they're invisible
4. **Enable SIM lock with your carrier** — port-out fraud is real and most people have zero protection

Most small business owners I talk to have never heard of any of this. The services that are supposed to protect you (Aura, LifeLock) just send you an alert and leave you to figure it out.

Happy to answer any questions about what to actually do after a breach if anyone's been through it.

---

## r/Entrepreneur

**Title:** I built something I wish had existed when my business identity got hit — asking for honest feedback

**Body:**
Two years ago someone fraudulently transferred my phone number (SIM swap). In the 90 minutes before I got it back they had accessed two business accounts. Nobody at my carrier warned me this was possible. No security service I was paying for noticed. I got an alert the next day.

The experience sent me down a rabbit hole. I spent the last 6 months building a different kind of protection — not another monitoring dashboard, but something that actually walks you through the response.

The insight that drove it: detection is commoditised. Google, Apple, and Firefox all notify you about breaches for free. The gap nobody's filled is response. When you get the alert at 10pm, panicked, what do you actually do? In what order? Most people change their password and stop there — which leaves every backdoor open.

What I built (RelayShield) sends you a WhatsApp message with the breach details and then walks you through the actual remediation — in the right order (sessions before password, OAuth audit, email backdoors, carrier hardening) — as a back-and-forth conversation. No dashboard to log into, no PDF to figure out. Just your WhatsApp.

For business owners I added SIM swap detection, domain lookalike monitoring (someone registers acme0.com to phish your customers), and employee breach alerts so you know when your team's credentials are exposed.

I'm not here to pitch — I'd genuinely appreciate feedback from other founders. Is this a problem you'd pay to solve? What's missing?

---

## r/freelance

**Title:** Freelancers are high-value targets for account takeover and most don't know it

**Body:**
I work in telecom security. The threat model for a freelancer is different from an employee — and worse.

You're a single point of failure. No IT department. No security team. One compromised account (email, banking, payment processor) and your entire operation stops. And you're using the same email for client communication, invoicing, and account recovery — which means one breach cascades everywhere.

The attacks targeting freelancers right now:

**SIM swap** — attacker calls your carrier, pretends to be you, moves your number to their SIM. Now they own your 2FA for everything. Takes about 15 minutes. Most carriers have opt-in protections that almost nobody turns on.

**Email forwarding rules** — after a breach or phishing hit, attackers add a Gmail forwarding rule to a mailbox they control. You never see it. They silently receive copies of your invoices, client emails, contract negotiations — indefinitely. Survives a password reset.

**OAuth persistence** — if you connected a tool that got breached, the attacker may have your OAuth token. They can authenticate as you without your password. Revoking the token requires knowing to go to myaccount.google.com/permissions — most people never do this.

Three things worth doing right now if you haven't:
1. Go to myaccount.google.com/permissions and audit every connected app. Remove anything old or unrecognised.
2. Go to your Gmail settings → Forwarding — check there are no rules you didn't set.
3. Call your carrier and ask about SIM lock / number lock protection.

Happy to answer questions — this is the area I've been working in for 25 years.

---

## r/msp

**Title:** How are you handling breach response for clients who don't have M365/Google Workspace admin access?

**Body:**
Genuine question for the MSPs in here.

When a client's personal email or personal phone gets breached — not their work account, not something you manage — what's your response? Most of the time I imagine it's "here's a link, go read it" because there's not much you can do through your tooling.

The problem is personal accounts are increasingly the attack surface for business compromise. SIM swap targeting a personal number to bypass MFA on a business account. Personal Gmail forwarding rules used to intercept business email forwarded from work to personal. OAuth tokens from a breached consumer SaaS used to pivot into Google Workspace.

I've been building in this space (identity protection for SMBs and their employees, WhatsApp-native so no app to install or dashboard to manage) and the use case I keep coming back to is the gap between what MSPs can monitor and what actually gets attacked.

Curious how you're handling it today. Is this even on your radar as a billable service, or is it firmly "out of scope, talk to your carrier"?

---

## r/digitalnomad

**Title:** The security hole most remote workers don't know about — especially dangerous when you're abroad

**Body:**
Something I see constantly working in telecom security that I don't see talked about enough in the nomad community: SIM swap fraud.

Here's the scenario: you're in Portugal, your US number gets ported to an attacker's SIM without your knowledge. They now own your 2FA for banking, Gmail, everything. You find out when you suddenly have no signal. By that point they've had 30-60 minutes with your accounts.

It's worse when you're abroad because:
- You can't just walk into a carrier store
- International calling to carrier support is a nightmare
- Time zone differences mean you lose hours before you even know something's wrong

Three things to do before your next trip:

1. **Enable SIM lock with your carrier** — AT&T has "Extra Security," T-Mobile has "SIM Protection," Verizon has "Number Lock." These make it much harder to port your number without an in-person store visit. Takes 5 minutes. Almost nobody does it.

2. **Audit what uses SMS for 2FA** — banking, email recovery, anything important. Switch the critical ones to an authenticator app (Authy, Google Authenticator). SMS 2FA is the weakest link.

3. **Set a carrier PIN** — separate from your account password. Required for any account changes. Most carriers have this, most people haven't set it.

The attacks that work rely on you not having done these basics. It's a low-effort target problem.

Happy to answer any questions — this is the space I work in.

---

## r/banking

**Title:** Your bank's fraud protection doesn't protect you from the attack that happens before you call them

**Body:**
I spent 25 years in telecom security and the thing I try to explain to people is: by the time your bank's fraud team catches it, the damage is done.

The attack sequence that's working right now:

1. Attacker does a SIM swap (your number moved to their SIM in about 15 minutes)
2. They use your number to receive the SMS 2FA code from your bank
3. They log in, initiate a transfer
4. Your bank's systems flag the transfer — eventually
5. You call your bank to dispute it. Best case, you get the money back. Worst case, it's a wire and it's gone.

The window where this is preventable is step 1. Once they have your number, everything downstream is a recovery problem.

What most people don't know: **every major US carrier has an opt-in SIM lock** that makes number transfers much harder. It requires an in-person store visit to override.

- AT&T: "Extra Security" in the myAT&T app → Account → Extra Security
- T-Mobile: "SIM Protection" at account.t-mobile.com → Profile → SIM Protection
- Verizon: "Number Lock" in the My Verizon app → Account → Account Security

Enable it, set a separate carrier PIN (different from your account password), and make sure your bank account recovery phone number is actually your current number.

That's the baseline. Happy to answer questions — this kind of attack is my professional focus.
