# HackerNoon submission: "Sender Recognition Is Not Authentication"

**Status:** ready to paste. Not yet submitted.
**Canonical source:** https://blog.relayshield.net/sender-recognition-is-not-authentication

---

## How to submit, and the one risk to watch

HackerNoon has **no URL importer**. Medium has one, HackerNoon does not. You paste the body into
their editor and set the canonical by hand.

1. Paste everything below the `=== PASTE BELOW ===` line into a new HackerNoon draft.
2. Open **story settings** and find the field called **"First seen at"**. Put the canonical URL
   above into it. That field is HackerNoon's canonical link.
3. Submit. Editorial review runs about **3 days**.

**The risk, stated plainly.** HackerNoon's own guideline says editors "have the rights to override
canonical links when they see fit," and there is a documented case of them stripping canonicals from
syndicated posts, publishing anyway, refusing to restore them, and the HackerNoon copy then
outranking the author's original in Google search. That is the same class of problem that retired
the last rented platform.

Two hedges are built into the copy below, so the attribution survives even if the canonical field
does not:

- The **first line of the body** states where it was originally published, with a link.
- The **closing line** repeats it. An editor removing a canonical field will usually not also strip
  body text, because that is a visible edit to the author's prose.

**After it publishes, check the canonical yourself.** View source on the HackerNoon page and read
`link[rel="canonical"]`. If it points anywhere other than blog.relayshield.net, the ask is removal,
not negotiation.

## What changed from the published post, and why

The blog version carries a section called "What we can and cannot see" that is entirely about
RelayShield's corpus, what it now contains, and what its endpoints return. That section is the
reason an editor would flag this as promotional, and it is the only part of the post that is about
us rather than about the campaign.

**It is cut in full here.** Not softened, cut. The footer boilerplate with the indicator and channel
counts is cut too. What is left is the analysis, which is the part worth reading anyway and the part
that earns the link back.

One consequence worth knowing: because the coverage claim is gone, there is no capability claim left
to disclaim, so this version cannot be read as "RelayShield detects BlueNoroff" by anyone. The
honesty problem solves itself by subtraction.

The JUMPSEC indicator publication is still mentioned once, as a fact about the research, phrased so
it says nothing about who ingested it.

## Suggested tags

`cybersecurity`, `social-engineering`, `north-korea`, `threat-intelligence`, `clickfix`,
`cryptocurrency-security`

## Suggested subtitle

A campaign that turns every victim's messaging session into the delivery channel for the next one.

---

=== PASTE BELOW ===

*Originally published at [blog.relayshield.net](https://blog.relayshield.net/sender-recognition-is-not-authentication).*

Most social engineering has a tell. A domain that is one character off. A sender you have never
heard from. A tone that does not match the person it claims to be.

The campaign that JUMPSEC pulled apart in July has none of those, because the message really does
come from someone you know, from their real account, referencing a relationship that really exists.
There is nothing to spot. The sender is genuine. Only the person typing is not.

That single property is what makes this worth writing about, and it is why the usual advice
("check the sender") is not advice at all here.

## The loop

Read the attack chain in the order it actually runs and a loop appears.

1. A compromised Telegram account belonging to a real industry contact sends a meeting invitation.
2. The target joins what looks like a Zoom or Teams call. An operator appears on video with no
   audio.
3. A staged audio fault leads to a fake SDK update prompt with troubleshooting text to copy.
4. Copying that text does not copy that text. The clipboard is replaced with an attacker command.
5. Running the command installs an implant.
6. The implant checks whether the victim has Telegram Web or Telegram Desktop, and if so, steals
   that session.
7. That stolen session sends the next round of invitations.

Step 7 feeds step 1. Every successful compromise does not just produce a victim, it produces
delivery infrastructure, and the delivery infrastructure is a real human being's trusted identity
inside a community where everyone already talks to everyone.

Note what is not in that list. There is no exploit. No blockchain vulnerability. No zero day in
Telegram. The only technically interesting component is a clipboard swap, and clipboard swapping
has been a solved trick for twenty years. What carries this campaign is that step 1 and step 7 are
the same step.

## The clipboard trick, precisely

The instruction text on screen is not the instruction text that lands in your clipboard. JUMPSEC
found that clicking Copy, or simply selecting the text and pressing Ctrl+C, replaces the clipboard
contents with an operator supplied command.

This matters more than it sounds, because the defensive habit most people have built is "read
before you run." Reading is exactly what fails here. What you read and what you would run are two
different strings, and the terminal or Run dialog is the first place the real one becomes visible,
which is after you have already pasted it.

The payloads themselves are unremarkable by design. On Windows, a short PowerShell stage pulls a
VBScript dropper, adds a Defender exclusion, and beacons recon data. On macOS, a shell script drops
a decoy installer to keep the victim busy while the real binary runs, then a stealer reaches for
Chrome's keychain entry. None of that is novel. It does not need to be. The novelty was spent
upstream, on getting a competent person to paste something willingly.

## Reconnaissance happens before malware, in the browser

The part that deserves more attention than it has received is the targeting step.

Before anything is delivered, the fake meeting page fingerprints the victim's browser wallets. It
uses EIP-6963 wallet discovery, the legacy `window.ethereum` probe, and non EVM globals for chains
like Solana. It also enumerates browser extension identifiers across roughly ten browser variants.

That is a reconnaissance sweep performed with ordinary web APIs, on a page the victim opened
voluntarily, before any code has run on their machine. The operators learn which wallets you have
and then decide whether you are worth a payload.

Two consequences follow.

**Being interesting is a state you enter before you are attacked.** By the time a payload is
selected, the decision has already been made using data you handed over by loading a page. The
window in which "nothing has happened yet" is true is earlier than most people picture it.

**Low volume is a feature.** Selective delivery means the campaign generates far fewer malware
samples than its infrastructure footprint suggests, which is exactly the shape that defeats
detection approaches built on sample volume.

## The correction worth making

The version of this story circulating on social media says that opening the meeting link drains
your wallet.

In the documented chains, it does not. Compromise requires a second act by the victim: running the
pasted command, or installing the fake update. The link alone gets you fingerprinted, not drained.

The exaggerated version is scarier, and scarier travels further, which is presumably why it
travelled. It is still worth correcting, for a practical reason. If people believe a click alone is
fatal, the advice collapses into "do not click anything," which nobody can follow and therefore
nobody does. If people understand there is a specific second step, the advice becomes "never paste
a command you did not compose," which is a rule a person can actually hold and which happens to
break the entire chain.

Attribution deserves the same care. Mandiant tracks this actor as UNC1069 and describes overlap
with BlueNoroff. The US Treasury has designated BlueNoroff, also known as APT38, as a North Korean
state entity under the Reconnaissance General Bureau. Those are three labels with different
evidentiary weight, and collapsing them into "North Korea hacked Telegram" loses the parts that are
actually operationally useful.

There is also one claim worth not repeating: that expired or recycled phone numbers are the primary
route to the initial Telegram account takeover. The compromised accounts are well documented. The
mechanism that compromised them is not consistent across the published cases.

## What actually helps

**Verify out of band, and verify the meeting, not the person.** The trusted contact is real, so
confirming "is this really you" over the same channel confirms nothing. A short call to a number
you already had, or a message on a different platform, is the whole control.

**Treat "paste this to fix it" as terminal.** Legitimate video conferencing has never required a
participant to run a shell command to fix audio. Not once. This is one of the rare cases where a
blanket rule has no false positives worth caring about.

**Separate the wallet browser from the meeting browser.** The fingerprinting step reads what the
current browser exposes. A browser profile with no wallet extensions returns nothing interesting,
and the operators triage on what they find. This costs nothing and removes you from the target list
before the target list exists.

**Assume the session, not just the password.** If an implant ran, password rotation from the
infected machine is theater. Sessions have to be revoked from a clean device, and the messaging app
sessions matter as much as the exchange ones, because the messaging session is what propagates the
attack to everyone who trusts you.

**If code already ran, leave the machine powered on and disconnect it.** The FBI's guidance here is
about forensic recoverability. Powering off destroys memory resident evidence that is often the
only record of what stage two actually did.

## The layer this really sits on

Every control that failed in this chain is a control about identity, and none of them are on chain.

A trusted contact's account. A session cookie. A keychain entry. A messaging session reused as a
delivery channel. The blockchain is where the money leaves, which makes it the place everyone
watches, but by the time anything reaches the chain the interesting part of the attack has been
over for a while.

It is also worth noticing where the operators put their own infrastructure. The macOS stealer
exfiltrates through a hardcoded Telegram bot token. The platform being abused for delivery is also
the platform being used for command and control. Attackers pick the same tools as everyone else,
for the same reason everyone else picks them.

JUMPSEC published the campaign infrastructure alongside their analysis, split into high confidence
and medium confidence rather than flattened into one list. If any of it turns up in your own DNS
logs, that split is the difference between a lead and a guess. These are look-alike domains for
Zoom and Teams, which is exactly the sort of thing that sits in logs for weeks looking
unremarkable.

The thing to take away is smaller than the headline invites, and more durable than it. Sender
recognition is not authentication. It was not this month, and it will not be next month either,
against whatever replaces this campaign.

---

## References

- JUMPSEC, "Inside a DPRK BlueNoroff ClickFix Kit," July 2026
- Google Mandiant, UNC1069 intrusion documentation, February 2026
- Security Alliance advisory on UNC1069 infrastructure
- US Treasury designation of BlueNoroff / APT38
- FBI guidance on DPRK social engineering against cryptocurrency and DeFi personnel

*This piece was originally published at
[blog.relayshield.net/sender-recognition-is-not-authentication](https://blog.relayshield.net/sender-recognition-is-not-authentication).*
