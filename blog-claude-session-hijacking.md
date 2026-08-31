# This Is Not LLMjacking, and Rotating Your Key Will Not Fix It

**DRAFTED 2026-08-30. NOT YET PUBLISHED.**
**Rendered copy:** `blog_markdown/this-is-not-llmjacking-and-rotating-your-key-will-not-fix-it.md`
(that file is what `build_blog.py` reads; this file is the channel plan and the checklist).

**Source:** Anthropic's email to affected users, reported by BleepingComputer, 2026-08-30, by Mayank
Parmar. Original email shared by the affected user on r/ClaudeAI.

**No numbers in this post, deliberately.** The measurement doctrine applies with force here: this is
a category anyone can check, and the post's argument does not need a corpus figure. Nothing about
stolen-session volume, nothing about corpus size, no category counts. If a number is ever added, it
comes from `exclusive_share_by_category.py` and only once that category clears 100.

**Em-dashes: 0.** Verified before commit.

---

## Why this post, and why now

The story is being filed under LLMjacking everywhere, and it is not LLMjacking. That mistake is not
pedantry, it changes the remediation: LLMjacking is API key theft and rotating the key fixes it,
while this is session cookie theft and rotating anything fixes nothing. Being the post that draws
that line correctly is the entire opportunity.

Three things carry it:

1. **The 2FA point.** Anthropic says in its own email that an already authenticated session means
   the attacker "may not need to go through the normal password and 2FA login process again". A
   major vendor saying that plainly is rare and quotable.
2. **The ordering.** Anthropic also warns that signing out does not remove the malware. The correct
   sequence is clean the machine, then revoke sessions, then rotate credentials. The instinctive
   sequence, change the password first, hands the attacker a fresh cookie from the same infected
   machine. We have argued session-revocation-before-password-reset before; this is third-party
   confirmation of it.
3. **Why Claude noticed and nothing else did.** This is the original argument in the post and the
   one to lead with in syndication. Claude has a consumable resource with a visible meter, so theft
   produced a signal. A replayed webmail session moves no counter anybody watches. The applications
   that will tell you a session was stolen are the ones that meter something, and that is a very
   short list.

## Product link, kept honest

The post does not claim we detected this campaign. It says what is true: RelayShield checks whether
credentials and sessions tied to an identity are surfacing in criminal channels and stealer dumps.
That is the `session-risk` and stolen-session work, live since before this story broke, and the
honest framing is "this is the gap we built for", not "we called it".

Prior art to link from syndication where it fits: `blog-medusahvnc-dolphinx-session-hijacking.md`
(2026-08-04), which made the same argument about credential theft becoming the setup rather than the
goal.

---

## Channel plan

Order, per house rules: `blog.relayshield.net` canonical, then Medium, LinkedIn, Telegram,
Farcaster, Mastodon. **Not X** (`@RelayShieldHQ` suspended). **Not Hashnode** (abandoned
2026-07-29). Medium is an import with the canonical URL, never a paste.

Canonical URL once deployed:
`https://blog.relayshield.net/this-is-not-llmjacking-and-rotating-your-key-will-not-fix-it`

### LinkedIn (limit 3000)

Anthropic has started emailing Claude users to tell them infostealer malware stole their active
login sessions, and that somebody has been signing in as them and burning their usage.

Almost every writeup is calling this LLMjacking. It is not, and the difference decides the fix.

LLMjacking is API key theft. Rotate the key and the stolen copy is worthless.

This is session theft. The malware copied an authenticated browser session. In Anthropic's own
words, that means the attacker "may not need to go through the normal password and 2FA login process
again". Nothing is phished. No second factor is defeated. The authentication already happened on the
victim's machine, and the cookie is the proof of it.

So there is no key to rotate, and changing the password does not help unless the platform revokes
existing sessions when you do. Many do not.

Anthropic also names the trap, and it is the one most people walk into:

"Signing you out of Claude stops the stolen sessions, but it doesn't remove the malware. If it's
still on your computer, your next login session could be stolen the same way."

Change the password on an infected machine and you have created a fresh session, on the same
machine, with the same stealer running. The order that works is the reverse of the instinct: remove
the malware, then revoke every session everywhere, then rotate credentials, then audit what the
session could reach.

The part that should worry you more than the Claude part: the same stealer log held every other
authenticated session that browser had. Email. Cloud console. Source control. The attacker picked
Claude out of the pile. The pile was never Claude specific.

Claude is simply where it became visible, and for a reason that has nothing to do with security
engineering. Claude has a consumable resource with a meter the user can see. Usage that refills and
drains overnight is a signal. A replayed webmail session moves no counter anybody looks at.

The applications that will tell you a session was stolen are the ones that meter something. For
everything else the theft is silent, and stays silent until it is used for something you have to
explain.

Full post: [CANONICAL URL]

#infostealer #sessionhijacking #threatintelligence #identitysecurity #incidentresponse

### Telegram (limit 4096)

**This is not LLMjacking, and rotating your key will not fix it**

Anthropic is emailing Claude users: infostealer malware stole their active login sessions, and
someone has been using them to sign in and drain usage.

The tell, in Anthropic's words: "If your usage limits looked like they refilled and then drained
while you weren't using Claude, this was likely the cause."

Families named: Vidar, LummaC2, StealC, RedLine, Acreed on Windows, Atomic Stealer on Mac. Ordinary
commodity stealers. The user who published the email had installed a pirated game.

**Why the LLMjacking label is wrong.** LLMjacking is API key theft, and rotating the key fixes it.
This is session cookie theft. Anthropic: an already authenticated session means the attacker "may
not need to go through the normal password and 2FA login process again". No key to rotate, no login
to phish, no second factor to beat.

**The order almost everyone gets wrong.** Anthropic: "Signing you out of Claude stops the stolen
sessions, but it doesn't remove the malware."

Change the password first on an infected machine and you hand the attacker a fresh cookie. Correct
order:

1. Remove the malware
2. Revoke every session, everywhere
3. Then rotate credentials
4. Then audit saved payment methods, connected apps, OAuth grants, API keys

**The part nobody is saying.** The same stealer log holds every other authenticated session that
browser had. Claude is just where it became visible, because Claude has a meter the user can see.
Your webmail session being replayed moves no counter at all.

Full post: [CANONICAL URL]

### Farcaster (limit ~1024 bytes)

Anthropic is telling Claude users that infostealers took their login sessions.

Everyone is calling it LLMjacking. It isn't. LLMjacking is API key theft, and rotating the key fixes
it. This is session theft, and Anthropic says it plainly: an already authenticated session means the
attacker may not need the password or 2FA at all.

The trap is the fix. Change your password on a still-infected machine and you have just minted the
attacker a fresh cookie. Clean the machine first, then revoke sessions, then rotate.

Claude noticed because Claude has a meter. Your webmail session being replayed moves no counter
anybody watches.

[CANONICAL URL]

### Mastodon (limit 500)

Anthropic: infostealers stole Claude login sessions and drained user usage.

Not LLMjacking. That is API key theft, fixed by rotating the key. This is session cookie theft, and
per Anthropic the attacker may skip password and 2FA entirely.

Change your password on an infected machine and you just minted them a new cookie. Clean first,
revoke second, rotate third.

[CANONICAL URL]

### Medium

Import, with the canonical URL set. Never paste, Medium has no Markdown paste.

**Topics, in this order.** Medium allows five and weights the FIRST most heavily for distribution
into that topic's feed, so the order is not cosmetic.

1. Cybersecurity
2. AI
3. Malware
4. Incident Response
5. Infostealer

Two broad for reach, two mid for ranking, one narrow where we can actually be found by search.

Threat Intelligence is deliberately not on the list, despite being our category: this post is a
remediation-order argument, not a TI post, and Incident Response fits what it actually says. The
counter-argument is real, though. Using the same category tag on every post compounds into a topic
presence, so if that is being built deliberately, swap Malware out for Threat Intelligence.

Anthropic and Claude are not worth a slot. Narrow, and their attention is tied to this news cycle
rather than to a feed anyone follows.

**Remove the quote bars after import.** House style is no quote bars (see CLAUDE.md). Select each
quoted paragraph and click the quotation mark on the floating toolbar until the bar is gone. Three
of them in this post.

Tags: Cybersecurity, Infostealer, AI, Threat Intelligence, Incident Response

---

## Publish checklist

- [ ] Read the BleepingComputer piece and the Reddit thread once more before merging. Every quote in
      the post is from Anthropic's email as reported. If any wording differs, fix it: a misquoted
      vendor email is the one error this post cannot survive.
- [ ] Confirm the canonical URL resolves after deploy, then fill `[CANONICAL URL]` in all five
      channel versions above.
- [ ] Link `blog-medusahvnc-dolphinx-session-hijacking.md`'s published post from the LinkedIn version
      if it still reads naturally.
- [ ] No numbers were added during editing.
