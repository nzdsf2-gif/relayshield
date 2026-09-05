# AgentBaiting: what Island found, what we already answer, and the one thing worth building

*2026-09-03, prompted by Island's webinar on AgentBaiting. Their numbers, quoted as theirs: 30,000
MCP servers and 450,000 AI tools scanned, 7,600 malicious GitHub repositories, and roughly half the
MCP servers carrying at least one security finding.*

---

## The attack, stated precisely, because the precision is the product

A repository is prepared to be found by an agent rather than by a person. Its code is clean. Every
scanner passes it. What is hostile is the **English**: install instructions, a README, an
`AGENTS.md`, a tool description in an MCP manifest, written so that an agent reading them does
something the user never asked for. Fetch this script and run it. Read this file and post it here.
Ignore what you were told before.

**Nothing about that is a code vulnerability, so nothing that looks for code vulnerabilities sees
it.** That is the whole finding, and it is why "we scanned it and it was clean" is a true statement
about a malicious repository.

## What we already answer, and what we do not

| | Today | Covers AgentBaiting? |
|---|---|---|
| `/v1/metered/mcp-registry-risk` | typosquat and near-miss detection on MCP server names and URLs, our IOC corpus, domain registration age | **Partly.** Catches the impersonation half. Blind to a repo with an honest name and hostile instructions |
| `/v1/metered/prompt-injection-breach` | exposure whose source dump suggests an agent was involved in obtaining it | **No.** That is the aftermath, not the bait |
| `rsscan` | secrets in your own diff and in published artifacts | **No.** Different question entirely |

So we cover the name and the domain. **Nobody in our stack reads the instructions.**

## The thing worth building: `agent-bait-scan`

One endpoint. Give it a GitHub repository, an MCP server package name, or a manifest URL, and it
fetches the surfaces an agent actually reads and scores what it finds:

**The surfaces.** `README`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`,
`mcp.json`, `smithery.yaml`, `package.json` scripts, and the tool `name` and `description` fields in
an MCP manifest. That last one matters more than it looks: a tool description is instructions that
an agent reads with the same weight as a user's message, and almost nobody treats it as untrusted
input.

**The signals, each independently reportable rather than summed into a single opaque score:**

1. **Execution instructions.** `curl … | bash`, `iwr … | iex`, an install step that fetches from a
   second host, a `postinstall` hook that does network work.
2. **Injection markers.** "ignore previous instructions", "you are now", a `system:` prelude, an
   instruction addressed to the assistant rather than the reader, and directives hidden where a
   human will not see them: HTML comments, zero-width characters, text the same colour as the
   background.
3. **Credential-touching directives.** Instructions that name `~/.aws/credentials`, `.env`, `id_rsa`,
   the macOS keychain, or a browser profile directory, especially alongside a URL.
4. **Provenance, which is the half nobody else has.** Every domain and package the instructions
   reference, checked against our criminal IOC corpus, against typosquat distance to well-known
   names, and for registration age. A repo whose install URL is already being traded in a criminal
   channel is a categorically different verdict from one that merely reads oddly.

**Signal 4 is the reason this is ours to build.** Static instruction analysis is a good idea that a
dozen people will implement this quarter. Static instruction analysis joined to a corpus collected
from criminal channels is a thing we can do and they cannot.

## Two rules it inherits, and one it adds

It inherits the two the widget already lives by. **It never throws**, and **it never says safe**: an
absence of hostile instructions in the files we could read is not proof of anything, least of all
about the code.

The one it adds is specific to this shape and it matters more than either: **it never calls a
repository or a person malicious.** It reports what the instructions would cause an agent to do.
"This README instructs an agent to fetch and execute a script from a second domain, and that domain
was registered eleven days ago" is checkable, defensible, and enough. "This repo is malware" is a
libel risk aimed at a named maintainer on the basis of a heuristic, and we would be wrong often
enough to deserve it.

## Where it ships, in the order that costs least

1. **The API endpoint first**, `POST /v1/metered/agent-bait-scan`, because everything else is a
   client of it and because the pattern work is the same wherever it runs.
2. **As an MCP tool on our own Apify Actor**, which closes a genuinely nice loop: an agent about to
   connect to an MCP server asks our MCP server whether that one is baited.
3. **As an `rsscan` mode** for the local case, gating CI on a dependency or a submodule that arrived
   carrying agent-facing instructions.

## The honest limits, and the number we must not quote

This is heuristic and it will produce false positives on legitimate installers, because a legitimate
installer and a hostile one differ by intent rather than by syntax. Anything reported has to be
readable by a human in ten seconds so they can dismiss it in eleven.

And **we must not repeat Island's numbers as our own**. 7,600 malicious repositories is their
finding from their scan. If we want a number in this category, it has to come from our own corpus
via `exclusive_share_by_category.py`, and the standing rule applies: nothing under 100 collected
indicators in a category gets quoted anywhere.

## Effort, honestly

| Piece | Estimate |
|---|---|
| Fetchers for the agent-facing surfaces, GitHub and package registries | 1 day |
| Signals 1 to 3, with a test corpus of real hostile and real benign examples | 1.5 days |
| Signal 4, joining to the IOC corpus and the existing typosquat code | 0.5 day |
| Endpoint, pricing, gateway route, docs | 0.5 day |
| **Total** | **3.5 days** |

The test corpus is the part that decides whether it is any good, and it is the part most likely to
be skipped. Build it from real repositories, hostile and benign, before writing a single pattern.

---

## DECIDED 2026-09-05: its own endpoint, sharing code, with one field added to the live one

Asked by the founder: should this ship as part of the existing MCP server typosquat check rather
than as a new endpoint?

**No, and yes, in that order.** Separate endpoint, shared implementation, and one cheap change to
`mcp-registry-risk` that closes the gap a second endpoint would otherwise open.

### Why not fold it into `/v1/metered/mcp-registry-risk`

That endpoint is live, in Bundle D, on AWS Marketplace, and exposed through the HF Space and the
Apify Actor. Today it answers from DynamoDB and at most one RDAP lookup. `agent-bait-scan` fetches
a README, an `AGENTS.md`, a manifest and package metadata from GitHub and a registry — several
network calls to third parties, with rate limits, timeouts and partial failures of its own.

Bolting that into the live endpoint changes its latency profile and its failure modes, on a path
that is already earning and already listed. That is the isolation mandate `relayshield_agentic_api.py`
states for itself, and the reason the MPP endpoint was a new file rather than a branch in it.

Pricing points the same way. `mcp-registry-risk` is $0.35 for a lookup. A scan doing half a dozen
remote fetches is not the same unit of work and should not be forced to share a price.

### Why it must still share the code

Signal 4 — joining referenced domains and packages to the criminal IOC corpus, the typosquat
distance check and the registration-age check — is *already implemented*, in
`handle_mcp_registry_risk`. That is why the estimate for signal 4 is half a day.

**Import it, do not copy it.** This repo already carries four copies of one pattern table that must
agree with nothing checking that they do, and `relayshield_mpp_settlement.py` set the precedent on
2026-09-04 by importing the detector rather than reimplementing it. One implementation, two callers,
dependency pointing one way only.

### The one change to the live endpoint, and it is the important part

Two endpoints means an integrator calls one and believes they are covered. That is the exact failure
this document opens with — "we scanned it and it was clean" being a true statement about a malicious
repository — recreated at our own API surface, by us.

The fix costs no latency and no network call: `mcp-registry-risk` gains a field saying what it did
**not** check.

    "instructions_checked": false,
    "see_also": "/v1/metered/agent-bait-scan"

The endpoint already refuses to say "safe", and already returns a note explaining that an absence of
findings means unknown rather than verified. Naming the specific blind spot is the same rule applied
one level down, and it is the honest way to sell a second endpoint: the first one tells you it is
not the whole answer.

### Sequencing

Compose them later, not now. An `include_instructions=true` parameter on `mcp-registry-risk` that
runs both server-side and prices accordingly is a good idea **once `agent-bait-scan` has a real test
corpus and a measured false-positive rate**, and a bad idea before that, because it would put an
unmeasured heuristic into the response of an endpoint AWS Marketplace customers are already buying.

The test corpus decides whether any of this is worth having. Build it first, as this document
already says.

## PRICING AND BUNDLE PLACEMENT — decided 2026-09-05

**Not built. This document is a scope and a decision, and no code exists yet.** Saying so plainly
because "did you build it?" had to be asked, which means the previous entry read like a build report.

### It belongs in Bundle D. That was never the question.

The founder's instinct is right and it does not conflict with the decision above. Two different
questions were being answered:

- **Same ENDPOINT as `mcp-registry-risk`?** No. Different latency profile, different failure modes,
  different unit of work, on a path that is already earning.
- **Same BUNDLE as `mcp-registry-risk`?** **Yes.** Bundle D is "Agentic Attack Surface". An endpoint
  that reads the instructions an agent is given is the most on-theme thing that could be added to
  it, and it strengthens a $299/mo minimum that currently rests on two metered dimensions.

### Price: $0.50 per call

| Endpoint | Price | Work it does |
|---|---|---|
| `wallet-risk`, `token-security` | $0.05 | one corpus lookup |
| `tech-stack-cve` | $0.20 | corpus join, no fetch |
| `mcp-registry-risk` | $0.35 | corpus lookup, one RDAP call |
| **`agent-bait-scan`** | **$0.50** | **six-ish third-party fetches, then every signal above** |
| `domain` | $0.50 | external lookups |
| `bulk-identity-risk` | $2.00 | hierarchical, many subjects |

$0.50 sits exactly where the work does: more than `mcp-registry-risk` because it makes real network
calls to GitHub and a package registry, the same as `domain` which does the same kind of work, and
far below `bulk-identity-risk` which is a different unit entirely.

**Do not go to $1.00.** The realistic caller is an agent triaging several candidate MCP servers
before connecting to one. Ten candidates at $0.50 is $5.00 and defensible; at $1.00 the buyer starts
pre-filtering, which means calling `mcp-registry-risk` alone and skipping the check that matters.
Pricing that discourages the second call recreates the coverage gap this endpoint exists to close.

### Sequencing, because one of the three doors has a gate

1. **`POST /v1/payg/agent-bait-scan` first, on x402.** No gate, no review, ships the day it is built,
   and it is the door an agent actually arrives at.
2. **`POST /v1/metered/agent-bait-scan` second**, for API-key callers, same build.
3. **The AWS Bundle D dimension LAST, and it is not free.** Bundle D today has exactly two metered
   dimensions in `AWS_DIMENSION_NAMES` — `mcp_registry_risk` and `prompt_injection_breach`. Adding a
   third to a PUBLISHED Marketplace product is a change set against the listing, with AWS's own
   review latency on their side of it. Worth doing, and worth doing after the endpoint has run
   against real traffic long enough to have a measured false-positive rate, because a change set is
   a bad place to discover the heuristic needs tuning.

Bundle D subscribers are billed the $299 monthly minimum either way, so the per-call price mainly
governs the PAYG/x402 door and the AWS metered dimension. It is still the number that decides
whether an agent calls it twice.
