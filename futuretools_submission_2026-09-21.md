# FutureTools.io: the WhatsApp bot. Paste-ready.

**One thing decides whether this works and it is the Tool URL.**

---

## THE TOOL URL MUST BE A PAGE. `wa.me` IS NOT ONE.

A directory reviewer opens the URL to see what the tool is, and to take the screenshot the
listing card uses. **`wa.me/<number>` gives them nothing to look at**: on a phone it opens
WhatsApp, and on the desktop they are almost certainly reviewing from it shows a "continue
to chat" interstitial. There is no product to see, so there is nothing to approve.

**Use `https://relayshield.net`.** It is the consumer page, it is WhatsApp-native
throughout, and it matches what the listing says the tool is. `api.relayshield.net/developers`
is a real page and carries attribution, but a listing called a WhatsApp scam checker that
lands on an API reference is a mismatch a reviewer notices.

**THE COST OF THAT CHOICE, STATED RATHER THAN HIDDEN: relayshield.net is a Carrd site and
reads no `?source=` parameter**, so the page view itself is unattributable. Only
`api.relayshield.net/developers` reads those, and that is the wrong page here.

**The fix is free and it is one line of Carrd.** Put the attributed WhatsApp link on the
page, so a FutureTools visitor who taps through to the bot IS counted even though their page
view is not:

```text
https://wa.me/17407373961?text=SRC_wa-futuretools
```

**`wa-futuretools` needs no registration anywhere.** `parse_wa_source` has no allowlist, and
the funnel's WHATSAPP stage filters `wa-[a-z0-9-]*`, so this key is counted the moment it is
used. **The only unrecoverable mistake on this surface is omitting the `?text=SRC_` suffix**:
a bare `wa.me` link logs nothing, leaves no `unmatched:` row to find later, and is
indistinguishable from organic traffic forever.

---

## The fields

**Tool Name**

```text
RelayShield
```

Not "RelayShield WhatsApp Bot". A directory card is scanned, and a name carrying its own
delivery channel reads as a limitation rather than a feature. The description says WhatsApp
in its first line.

**Tool URL**

```text
https://relayshield.net
```

**Short Description**

```text
Forward a suspicious link, message or wallet address to RelayShield on WhatsApp and get a risk verdict back in seconds. Free, no account. It also monitors your email, phone number and wallets for data breaches, infostealer malware and SIM-swap attempts, then walks you through the fix step by step in the same chat.
```

Three things that are deliberate in that paragraph:

- **It leads with what a reader can do in the next ten seconds**, not with what the company
  is. A directory visitor is deciding whether to click, not whether to buy.
- **"Free, no account" is the strongest phrase available to us** and it is true: the link and
  address checks are keyless, capped per source IP rather than billed.
- **It does not say "AI".** Every listing on that site says AI. The specific thing we do is
  more persuasive than the category we are in, and a reviewer reading forty submissions a
  week has seen the word.

**Category**

**Pick the first of these that the dropdown offers**, and I am not guessing further because
`futuretools.io` is egress-blocked from the container and choosing from a list I cannot see
is the mistake this programme has paid for:

1. Security
2. Productivity
3. Chat (the field's current default, and defensible for a messaging bot)

**Pricing: Freemium.**

Checkable and correct. The link and wallet checks are free with no account; the monitored
plans are paid. **Not "Free"**, which would be a claim a reviewer disproves by opening the
pricing section, and not "Paid", which understates the thing most likely to make somebody
try it.

**Your Email:** `relayshieldadmin@gmail.com`, already filled.

**Newsletter checkbox:** leave it unticked. It has no bearing on the submission.

---

## What to expect, and the one thing worth checking afterwards

FutureTools is curated: a human reviews submissions and not everything is listed. There is no
published turnaround that I can see from here.

**If it is listed, check the card.** Directories routinely rewrite the description and pull
their own screenshot, and a listing that describes us as something else is worth one email to
correct. The name and the first sentence are the two fields that matter.

**UNVERIFIED:** `futuretools.io` is egress-blocked from this container, so the category list,
any character limits and the review process are all things your browser can see and I cannot.
If a field truncates, the first sentence of the short description stands alone.
