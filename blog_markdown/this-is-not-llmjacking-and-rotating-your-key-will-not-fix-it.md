---
title: "This Is Not LLMjacking, and Rotating Your Key Will Not Fix It"
slug: this-is-not-llmjacking-and-rotating-your-key-will-not-fix-it
date: 2026-08-30
---

# This Is Not LLMjacking, and Rotating Your Key Will Not Fix It

Anthropic has begun emailing Claude users to tell them that infostealer malware on their machines
stole their active login sessions, and that somebody has been using those sessions to sign in and
burn through their usage.

The company is signing affected users out, removing saved payment methods, and refunding charges it
can identify as unauthorised. Its own summary of the tell is worth quoting, because it is the part
most people will recognise before they recognise anything else:

> If your usage limits looked like they refilled and then drained while you weren't using Claude,
> this was likely the cause.

The families named are the ordinary ones. Vidar, LummaC2, StealC, RedLine and Acreed on Windows,
Atomic Stealer on a smaller number of Macs. Nothing bespoke, nothing targeted at Anthropic. The
user who first published the email had installed a pirated game.

## The distinction that decides the fix

This keeps getting filed under LLMjacking, and it is not LLMjacking.

LLMjacking is API key theft. Somebody finds a provider key in a public repository, in a config file,
in a stealer log, and bills inference against it until the owner notices. The fix is to rotate the
key. The moment you do, the stolen copy is worthless.

This is session theft. The malware copied an authenticated browser session, and Anthropic is
explicit about what that means:

> Infostealers can copy an already authenticated browser session, which means the attacker may not
> need to go through the normal password and 2FA login process again.

Read that again if you have ever been told that two-factor authentication solves account takeover.
The attacker is not logging in. There is nothing to phish, nothing to intercept, no second factor to
defeat, because the authentication already happened on the victim's machine and the cookie is the
proof of it.

So rotating a key fixes nothing here, because no key was involved. Changing a password fixes nothing
either, unless the platform revokes existing sessions when you do, and many do not. The only thing
that invalidates a stolen session is revoking the session.

## The order of operations, which almost everyone gets wrong

Anthropic put the trap in one sentence:

> Signing you out of Claude stops the stolen sessions, but it doesn't remove the malware. If it's
> still on your computer, your next login session could be stolen the same way.

That is the whole problem with the instinctive response. The instinct is: change the password. On an
infected machine, changing the password creates a fresh authenticated session, on the same machine,
with the same stealer still running, and hands the attacker a new cookie.

The order that works is the reverse of the instinct:

1. **Remove the malware first.** Everything else is theatre until the machine is clean.
2. **Then revoke every session**, everywhere, not just on the app that alerted you.
3. **Then rotate credentials**, and only then. A password changed before step one is a password
   the attacker watched you type.
4. **Then audit what the session could reach.** Saved payment methods, connected apps, OAuth grants,
   API keys created while the attacker had access.

We have argued this ordering before and it is the thing we would most like security guidance to
adopt: session revocation belongs before password reset, not after.

## Why it was Claude that noticed

Here is the part that should worry you more than the Claude part.

The same stealer log contains every other authenticated session that browser held. Your email. Your
cloud console. Your source control. Your payroll provider. The attacker picked Claude sessions out
of the pile, as Anthropic says, but the pile was never Claude specific.

Claude is simply where it became visible, and it became visible for a reason that has nothing to do
with security engineering: Claude has a consumable resource with a meter the user can see. Usage
that refills and drains while you are asleep is a signal. Most stolen sessions produce no signal at
all. Nobody notices a replayed session on their webmail, because reading a mailbox does not move a
counter anybody looks at.

That asymmetry is the real finding. The applications that will tell you a session was stolen are the
ones that meter something. For everything else, the theft is silent, and it stays silent until it is
used for something you eventually have to explain.

## What to do about it

If you got the email, follow the order above, and treat the Claude session as the one you happened to
find rather than the only one taken.

If you did not get the email, the useful question is not whether your Claude session is in a stealer
log. It is whether any of your sessions are, and how you would ever find out. That is the gap we
built for: RelayShield checks whether the credentials and sessions tied to an identity are turning up
in criminal channels and stealer dumps, and tells you before the meter starts moving.

The malware is ordinary. The distribution is ordinary. What is new is that a major platform has now
said out loud that stolen sessions, not stolen passwords, are what its attackers are actually using.

The tooling most people have is still built for the password.
