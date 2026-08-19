# Blue Team Village — rsscan availability ask

**Goal:** get `rsscan` in front of BTV's ~8,300 defenders as a village-endorsed free tool.
This is the flywheel tactic, not a launch post: the tool is free, local, and needs no
account, so the village is giving members something useful rather than carrying a vendor ad.
Distribution first, funnel second (`?source=rsscan` on the escalation report is the only
commercial surface, and it fires only if a developer chooses to click it).

**Do not** post a Bundle D / marketplace announcement in the Discord. Same rule as
`bundle_d_launch_distribution.md` and TODO DISTRIB-FILIGRAN-1: one first impression.

**Two separate tracks, do not merge them into one message:**
1. **This ask** — rsscan availability for members (below).
2. **Their CFP** — "LLMjacking: the credential theft your SIEM structurally cannot see."
   Independent of this, and worth submitting on its own timeline.

**Before sending:** confirm the current intake route on blueteamvillage.org (contact form vs.
Discord staff channel). Do not guess an address.

---

## The message

> Hi — I'm Andrew, I run RelayShield (small independent security shop).
>
> We publish `rsscan`, a pre-commit secret scanner, and I'd like to ask whether BTV would be
> open to making it available to members — a line in the village's tooling resources, or
> however you normally surface tools.
>
> What it is, plainly:
>
> - Scans **100% locally**. 31 credential patterns run on the developer's machine. No API key,
>   no account, no network call, no size cap. Nothing leaves the box.
> - Report output carries **fingerprints only, never secret values**, so it is safe to forward
>   to a security team or paste into a ticket.
> - Installs from PyPI, GitHub, GitHub Marketplace or Docker Hub. MIT-licensed.
> - Telemetry is **off unless you pass `--org`**, and even then it is org, an anonymous install
>   id, version, and per-severity counts. No paths, no findings, no secrets.
>
> There is no signup wall and nothing to buy — I'm not asking for a promo slot, I'm asking
> whether it is useful enough to your members to be worth listing.
>
> Where it came from: we measured how badly naive secret-scanning regexes perform on public
> GitHub. `AKIA` literal returns 4,272 results; the top five were a docs table, a placeholder,
> a README describing redaction, a link list, and an allowlist. Five of five false positives.
> That is why rsscan matches locally and reports fingerprints instead of shipping your source
> to somebody's API.
>
> Happy to answer anything, and equally happy to hear no.
>
> — Andrew, RelayShield

---

## If they say yes

- Offer a short "how we use it" walkthrough for the village, not a demo of the paid product.
- Track arrivals via `?source=rsscan` and the `--org` install telemetry; a distinct install-id
  count at one org is the qualified signal PyPI downloads can never give.
- **Do not** follow up with a Bundle B/A pitch in the same thread. The ladder runs
  free rsscan → Bundle B → Bundle A on the developer's own timeline, not ours.
