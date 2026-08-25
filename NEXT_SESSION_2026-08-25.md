NEXT_SESSION_2026-08-25.md

Full context for everything below is in CLAUDE.md's "SESSION STATE — 2026-08-24" section --
read that first. This file is just the prioritized punch list.

## Top 10

1. **Regenerate the Telethon session** the moment an OTP actually arrives. Run
   `"$HOME/Side SaaS Hustle/.telethon_venv/bin/python3" "$HOME/Side SaaS Hustle/regenerate_telethon_session.py"`
   -- do NOT re-run it repeatedly while still troubleshooting delivery, that risks its own
   flood-wait on top of whatever's blocking delivery now. If still nothing by tomorrow, escalate
   (see #7).

2. **Merge PR #12** (`claude/redeploy-relayshield-api-5e5v2h` -> `main`, github.com/nzdsf2-gif/relayshield)
   once reviewed. Open and mergeable as of 2026-08-24. Carries the TI demo recovery/fixes, the
   INTEL-2/5 lock fix, the CI guardrail, and the relayshield-mcp submodule bump.

3. **Cut a GitHub Release for relayshield-mcp (0.2.11)** so the LLMjacking tool, the `mcp<2.0.0`
   cap, and the Dockerfile/`__main__.py` fixes actually reach PyPI -- this repo only publishes on
   `release: published` (`.github/workflows/publish.yml`), not on push to main. `main` has been at
   0.2.11 since 2026-08-24; PyPI is still on 0.2.9. Anyone `pip install`-ing this today gets broken
   code (the `mcp` 2.0 crash) until this is cut.

4. **Publish the Apify Actor** once business verification clears (Apify's own 1-2 day lead time,
   submitted 2026-08-24). Set the Monetization pricing model first -- remember Apify's own
   platform pricing stacks on top of RelayShield's x402 pricing, it does not replace it.

5. **Fix the ransomware-victim false-positive class** that's still open after today's regex fix:
   ransom-note boilerplate ("Recover Your Files") gets captured as if it were an organisation
   name. Today's fix (`_RE_RANSOM_VICTIM` in `relayshield_intel_monitor.py`) killed the
   mid-word-fragment garbage ("rs Remote Control."); this is a separate, still-open class of noise
   in the same table, visible on the live TI demo tab.

6. **Decide on a dedicated (non-personal) number/account for the Telethon session.** This is the
   second `AuthKeyDuplicatedError` incident riding on a family member's personal Telegram account
   (2026-07-23, 2026-08-24) -- today's lock fix stops the specific concurrency bug that caused
   both, but the underlying fragility (any future flag/ban risk lands on a real person's account)
   isn't solved by that fix. sms-activate.org (the service the original setup instructions
   pointed at) is discontinued -- a real prepaid SIM in a spare device, dedicated to nothing else,
   was the alternative discussed.

7. **If Telegram OTP delivery is still failing**, this now looks Telegram-side, not anything
   fixable from a terminal -- two different numbers, two different carriers, WiFi off, tried via
   SMS/in-app/official-app-login, nothing after hours. Check Telegram's own status
   (downdetector.com/status/telegram or their status channel) for reports of SMS delivery issues,
   and consider contacting Telegram support directly if nothing shows up there either.

8. **Pick a GitHub identity for the Apify creator profile** -- `nzdsf2-gif` (the monorepo) or
   `relayshield` (the org that owns `relayshield-mcp`, the actual published product). Left open,
   your call.

9. **Set the actual Apify Monetization pricing** once billing verification clears -- blocked on
   #4's verification, but decide the number now so it's not a fire drill when it clears.

10. **Revisit Apify partnership options 1 and 3** from the original three-option ask (dedicated
    Apify Actors in their marketplace; a broader formal partnership) -- only option 2 (MCP/tool
    layer integration) has been built and pursued so far.

## Also worth a look, not top-10

- v-shukore's Azure Sentinel PR commits (data connector UI cleanup) looked like normal reviewer
  iteration, not something needing action -- but nobody's actually diffed what "remove duplicate
  data connector text blocks" removed.
