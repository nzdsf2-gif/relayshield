# maigret: yes, narrowly, as internal enrichment. Not a product endpoint, and never on a victim.

Asked 2026-09-19: *"OSINT: Is this site worth using: https://github.com/soxoj/maigret"*

**Short answer: yes for one job we actually have, no for the two it looks like it fits.**
The recommendation is at the bottom, with what it costs and what it is gated on.

## What it is, read rather than recalled

`raw.githubusercontent.com` is reachable from the container, so this is from the project's own
README and PyPI metadata rather than from a search summary.

| | |
|---|---|
| What it does | Collects a dossier on a person **by username only**, checking for accounts across sites and scraping what the profile pages expose |
| Coverage | 3,000+ sites. A default run checks the **500 highest-ranked by traffic**; `-a` scans everything, `--tags` narrows by category or country |
| Licence | **MIT.** The README's Commercial Use section: *"free for commercial use without restriction"* |
| Maintained | **`maigret` 0.6.6 on PyPI, uploaded 2026-09-18** -- the day before this was written |
| Embeddable | Yes. `import maigret` and run searches programmatically; there is documented library usage |
| Keys | None required |
| Also sells | A private 5,000-site database updated daily, and a username-check API, via `maigret@soxoj.com` |

**Same author as `soxoj/telegram-bot-dumper`**, which this repo recorded reading properly after
dismissing it from its name. That went the same way here: the name says nothing and the README
settles it in two minutes.

**The honest caveat the README itself states: site checks break over time and need active
maintenance.** That is the argument for their paid daily-updated database if this ever becomes
load-bearing, and it is also the reason not to build anything whose accuracy claim depends on it.

## Where it does NOT fit, and both are the tempting ones

**1. Not a customer-facing endpoint.** Enumerating every account belonging to a named handle, on
request of somebody who may not be that person, is a different product from ours with a different
posture. RelayShield checks **your own** exposure, or a **counterparty** you are about to transact
with. "Tell me everywhere this person exists" is people-search, and it is one design decision away
from being a stalking tool. The consumer product should not grow that surface.

**2. Not the fix for the `tg_handle` noise, and this is the interesting one.**
`relayshield_operator_identities` holds 7 rows, every one at `sightings=1`, several of them
ordinary English words -- `catching`, `normanonrock` -- caught because `_RE_TG_CHANNEL` matches any
`@mention`. It is tempting to say maigret separates a real operator from a false positive.

**It does the opposite.** Common English words are registered usernames on hundreds of sites, so
maigret would return *more* hits for `catching` than for a real operator's handle. The filter this
repo already named is the right one and needs no new dependency: **require a SECOND sighting before
writing the row at all.** Repetition is the discriminator, not breadth.

## Where it DOES fit: enrichment of a handle we already trust

The exclusive asset is a handle seen in **two or more channels**. For those -- and only those --
"where else does this operator exist" is attribution work, which is what a TI buyer actually pays
for, and it is the half of the corpus that is not ingested public feeds.

Three things make it a good fit specifically there rather than generally:

- **It runs on a handle we already believe in**, so breadth is signal instead of noise.
- **It is a batch job, not a request path.** A default run is 500 outbound HTTP requests. In a
  Lambda that is slow, and every request leaves from one NAT address, which is the same
  self-throttling trap that stopped `relayshield_watchlist_monitor.py` calling our own public
  endpoint over HTTP. It belongs in a scheduled job or on the Mac.
- **`socid_extractor`, which it uses, pulls IDs and cross-links off profile pages.** A linked
  account on another platform is exactly the kind of pivot that turns a handle into an identity.

## Recommendation

**Adopt it, internally, gated on the second-sighting filter that does not exist yet.**

- **Cost:** about half a day once there is anything to run it against. MIT, no key, `pip install`.
- **Gate:** `tools/check_operator_identities.py`'s cross-channel count. While that is 0, there is
  no handle worth enriching, and running it on the seven current rows measures our extraction bug
  rather than the criminal market.
- **Do not quote any number it produces externally.** MEASUREMENT DOCTRINE applies: a count of
  "sites where this operator appears" rests on a third party's site list that the third party says
  decays, which is exactly the shape of number that gets checked and found wrong.
- **Never run it on a customer's or a victim's handle**, and do not expose it through any endpoint.
  If that ever changes it is a product decision with a legal read attached, not an integration.

**UNVERIFIED from the container:** `maigret.readthedocs.io` and the site list were not opened here.
The README, the licence and the PyPI release date were.
