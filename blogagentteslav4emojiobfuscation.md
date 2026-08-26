# Agent Tesla is hiding in emoji. Your hunting query is probably missing it for a much duller reason.

*Every RelayShield number below was measured in a live Microsoft Sentinel workspace on 2026-08-15.*

<!-- INTERNAL: publish everything from the rule below down to the NOT FOR PUBLICATION line.
     The italic line above is publishable; this comment and the plan at the bottom are not. -->

---

KnowBe4 published an analysis of a new Agent Tesla build this month, and one detail is getting all
the attention: the JScript dropper is padded with **Unicode emoji characters scattered through the
code body**. They do nothing. That is the point. They break string-based signature matching and
make the file visually noisy enough that a human skimming it gives up.

It is a good trick. It is also the second-most interesting thing in this story, because the same
class of failure — *matching a string you assumed was normalised* — is probably live in your SIEM
right now, and nobody put emoji in your data to cause it.

## What the campaign actually does

The chain, as reported:

| Stage | What happens |
|---|---|
| Lure | BEC email posing as forwarded internal correspondence about a pending wire transfer, aimed at finance |
| Attachment | `SWIFT Payment Maker 103 – 10.06.26.JS` — a 6.94 MB JScript file dressed as payment paperwork |
| Obfuscation | Unicode emoji embedded through the code body, defeating signature matching |
| Loader | DonutLoader shellcode |
| Injection | Reflective in-memory MSIL injection — the terminal payload never touches disk |
| Payload | ConfuserEx-obfuscated .NET infostealer |
| Theft | Credentials from 40+ applications, plus keystrokes, clipboard and host fingerprinting |
| Exfil | FTP, to a single threat-actor-controlled domain |

Anti-analysis is thorough: debugger detection, cloud-hosting IP checks, timing-based VM detection,
sandbox DLL enumeration, and WMI queries for VMware, VirtualBox and Hyper-V.

Two things are worth pulling out, because they change what detection you should be leaning on.

**The payload never touches disk.** Reflective MSIL injection means file-based detection has one
shot — the JScript dropper — and that is the artefact wearing the emoji costume. If your control
stack is weighted toward on-disk scanning, the obfuscation is aimed precisely at you.

**Exfiltration is FTP to one domain.** That is old-fashioned, and it is the campaign's weakest
link. A single hardcoded destination is a single indicator, and egress FTP from a finance
workstation is anomalous on almost any network. If you can only afford one detection here, make it
that one.

## The duller failure, and it is probably in your queries

Agent Tesla is not new. It has been circulating since 2014, it is in every threat feed, and it
shows up in ours: **304 `agenttesla`-labelled indicators** in a two-hour window when we measured
our own feed landing in a live Sentinel workspace on 2026-08-15.

Here is the part worth your afternoon. While measuring that, we found something in the label data
that has nothing to do with Agent Tesla and applies to every family you hunt.

Threat-intel labels are **not case-normalised at source**. Ours were not. Both `ClearFake` and
`clearfake` occur in the same feed, in the same table, describing the same family. Some labels also
carry several comma-joined values inside a single string.

So this query:

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(7d)
| mv-expand Label = Data.labels
| where tostring(Label) == "malware:clearfake"
```

returned **196** indicators.

And this one:

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(7d)
| summarize arg_max(TimeGenerated, *) by Id
| where IsDeleted == false
| mv-expand Label = Data.labels
| extend Family = tolower(replace_string(tostring(Label), "malware:", ""))
| mv-expand Family = split(Family, ",")
| extend Family = trim(" ", tostring(Family))
| where Family == "clearfake"
```

returned **608**.

Same corpus, same window, same family. The exact-match version silently dropped **roughly two
thirds of the matches**, and reported success while doing it.

That is the emoji trick again, wearing a suit. The dropper defeats matching by putting characters
where you did not expect them. An exact-match label filter defeats itself by assuming characters
are where you *did* expect them. Neither raises an error. Both return a confident number.

**If you hunt Agent Tesla with `== "malware:AgentTesla"`, you are running the 196 query.**

## What to actually do

**In your hunting queries**, fold case on both sides and split multi-value labels, always:

```kusto
| extend Family = tolower(replace_string(tostring(Label), "malware:", ""))
| mv-expand Family = split(Family, ",")
| extend Family = trim(" ", tostring(Family))
| where Family == "agenttesla"
```

Also deduplicate. Feeds that republish unexpired indicators on a cycle — ours runs every 7 to 10
days — will otherwise have you counting the same indicator repeatedly:

```kusto
| summarize arg_max(TimeGenerated, *) by Id
| where IsDeleted == false
```

**Treat the label namespace as a hint, not a taxonomy.** Ours mixes families with behaviours
(`phishing`, `coinminer`), platforms (`windows`), vendor names, and the occasional malformed
identifier. Anything built on it needs to tolerate that. We are normalising ours at source; until
every provider does, fold case yourself.

**For this campaign specifically**, in rough order of value for effort:

1. Alert on outbound FTP from finance endpoints. One hardcoded exfil domain is the softest target
   in the chain.
2. Treat `.JS` attachments as executable content in mail policy. A 6.94 MB JScript file attached to
   a wire-transfer thread has no legitimate reading.
3. Do not rely on file size or entropy heuristics tuned pre-emoji. The padding is designed to move
   both.
4. Because the payload runs in memory, weight in-memory and behavioural detection over on-disk
   scanning for this family.

## The honest caveat about our number

We are not claiming the 304 Agent Tesla indicators are ours exclusively. Agent Tesla is published
by abuse.ch and every major feed, and a large share of any corpus's Agent Tesla coverage — ours
included — is ingested rather than collected. Anyone telling you their Agent Tesla feed is
proprietary is selling you URLhaus with a markup.

What is defensible is the measurement above: the case-folding gap is real, we found it in our own
data, and it will be in yours.

---

## NOT FOR PUBLICATION — plan, checks and open items

### Pre-publication checklist

- [ ] **Re-run the two `clearfake` queries before publishing.** The 196/608 figures were measured
      2026-08-15. The ratio is the claim; if it has moved, publish the new pair, not the old one.
- [ ] **Re-run the `agenttesla` count.** 304 was a two-hour window on 2026-08-15. Either re-measure
      or change the sentence to "when we measured on 2026-08-15", which is already how it reads.
- [ ] **Confirm the KnowBe4 details against their own post**, not the trade coverage. Filename,
      file size, 40+ apps, FTP exfil and the DonutLoader stage all come from secondary reporting.
- [ ] **Do not name the exfil domain or post IOCs** unless we independently observed them. We did
      not analyse this sample; citing someone else's IOCs as if we had is the exact overreach this
      post criticises.
- [ ] Confirm `agenttesla` is genuinely in our label set at publish time, not just on 2026-08-15.

### Why this post exists

It is a **news-reaction post with an original measurement inside it**. The reaction half is
perishable — every vendor will cover the emoji trick within a week and the coverage is already
crowded. The measurement half is ours and does not decay.

The structure is deliberate: use the news for reach, spend that attention on a finding nobody else
has. If we publish only the news half we are the fifteenth blog about emoji obfuscation.

**This is why it goes first.** See the ordering note in the secret-scanning follow-up.

### What we are deliberately NOT claiming

- Not claiming exclusivity on Agent Tesla indicators. Stated in the post, on purpose.
- Not claiming we analysed the sample. We did not.
- Not quoting the 511K corpus figure anywhere. The measured, checkable numbers carry this post.

### Channels

Canonical `blog.relayshield.net` → Medium (**import, do not paste**) → LinkedIn → Telegram →
Farcaster (`/security`) → Mastodon. **Not X** (suspended). **Not Hashnode** (abandoned).

Move fast on this one — a news-reaction post published a week late is worth a fraction of one
published in two days.

**LinkedIn angle:** lead with the query gap, not the emoji. "Your Agent Tesla hunt is returning a
third of the matches" outperforms "new malware variant" with that audience, and it is the half only
we can say.

**Length limits:** Mastodon 500 chars · Farcaster ~1024 bytes · LinkedIn 3000 · Telegram 4096.
Write each short version to its own limit. Apply the no-dash rule to every short version.

**LinkedIn hashtags** (3–5): `#ThreatIntelligence #DetectionEngineering #InfoSec #SIEM #BEC`
**Mastodon** (3–4): `#infosec #threatintel #detection #malware`

### Sources

- [New Agent Tesla Malware Variant Boosts Evasion Capabilities — Infosecurity Magazine](https://www.infosecurity-magazine.com/news/agent-tesla-malware-evasion/)
- [Anatomy of an Agent Tesla BEC Attack — KnowBe4](https://blog.knowbe4.com/anatomy-agent-tesla-bec-attack-in-memory-infostealer)
- [New Agent Tesla malware version uses emoji obfuscation — SC Media](https://www.scworld.com/brief/new-agent-tesla-malware-version-uses-emoji-obfuscation-to-evade-detection)
- [Hackers Hide Agent Tesla JScript Behind Unicode Emojis — Cybersecurity News](https://cybersecuritynews.com/hackers-hide-agent-tesla/)
- RelayShield internal: `elastic_security_integration_guide.md` / the Sentinel guide's measured
  2026-08-15 workspace figures.
