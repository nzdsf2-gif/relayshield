# Rapid7 PR #4024 — nudge comment

**Status:** DRAFT, pending founder review. Do not post until approved.
**PR:** https://github.com/rapid7/insightconnect-plugins/pull/4024
**Verified live 2026-08-04:** `OPEN`, all checks `SUCCESS`, **0 reviews**, 1 comment,
last activity `2026-07-26T21:41:09Z` — **9 days idle**.

**Tone note:** this is a first-time external contribution to a vendor's plugin repo. The PR is
green and nobody has looked at it, so the job is to be easy to review, not to complain about the
wait. Lead with what changed since they last saw it, keep it short, and give them a reason to
pick it up now.

---

Hi — checking in on this one.

Since it was opened, everything on the RelayShield side has moved forward and the plugin is
current with it:

- All four checks are green and Snyk is clean.
- The API surface the plugin calls now has a full published reference at
  https://api.relayshield.net/docs, with an OpenAPI 3.1 spec at
  https://api.relayshield.net/openapi.json — useful if it helps review the actions against the
  documented request and response shapes.

Happy to rebase, split it into smaller commits, or make any changes that would make this easier to
review. If there is a queue or a preferred process for new plugin submissions, just point me at it
and I will follow that instead.

Thanks for taking a look.
