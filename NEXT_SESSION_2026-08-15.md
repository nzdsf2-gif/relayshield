# Next session, 2026-08-15

## 1. Virtuals ACP registration. Founder's pick for tomorrow.

**Honest effort estimate: an evening, not minimal, and there is one unknown.**

Registration itself is small: `acp agent create` to mint an agent identity (a wallet, **not** building
an autonomous agent and **not** a token launch), then `acp offering create` to define services with
pricing, and expose the endpoints as **Resources** (name, description, URL, params JSON schema).
Discovery is via `acp browse`. Compute accounts need a USDC top-up, $1 minimum.

**The unknown:** two sources disagree on whether an agent identity is mandatory for API-only
providers. The `acp-cli` README says it is; a secondary summary says it is not. **Resolve by running
the command, not by more searching.** Tokenisation carries a launch fee and appears optional:
confirm that before doing anything that costs money.

**Trap:** two servers resolve as "Virtuals Protocol" (12,661 and 9.2% online, and 5,677 at 4.5%).
One of them is not theirs. **Confirm the official invite from virtuals.io before joining either.**

Full design and the honest counterweight: `x402_agent_economy_angle_2026-08-14.md`.

## 2. Stripe MPP. PARKED, do not build.

Crypto is **Ineligible** on the account and it is a rollout gate, not a form. Contact-sales submitted
2026-08-14. **Do not convert the Stripe account from individual to company as a fix** for this.

**The founder's reasoning was right**, and this is worth restating so it is not re-argued: dual fiat
plus crypto rails would reach a buyer population x402 does not. Only the access is missing. **If
Stripe opens the crypto rail, MPP returns to first priority** ahead of ACP, and there is an official
Python SDK so no rewrite is needed.

## 3. Five outreach threads live, all awaiting reply. Do not chase yet.

| Thread | Contact | Sent |
|---|---|---|
| Corix / Hiscox | Lori Bailey | 2026-08-14 |
| Vouch | Clark Kays | 2026-08-14 |
| Cowbell | Rajeev Gupta | 2026-08-14 |
| Famous Fox Federation | Draxxts, DM | 2026-08-14 |
| Twilio #28883049 | Avinash Sawant | 2026-08-14 |

**Give them a week.** Corix fallback is James Baker, VP Underwriting, if Lori has not replied by
2026-08-28.

## 4. Discord: DeFi Kingdoms is the next target

**Founder is a former player and it has a partner channel**, which is real standing and the thing
member counts only estimate. Official invite `discord.com/invite/kARBQuMAhS`, 55,661 members, 5.4%
online. Band deliberately overridden.

Then Wildcard, Honeyland, Genopets, Pirate Nation, all ~1,100 members at 13-15% online.

**Gods Unchained is lost.** "Unable to accept invite" is Discord's wording for a ban. Optional single
polite appeal via Immutable support; otherwise let it go. **Rule change: company-run servers with
staff moderators are now "do not approach".** That covers MapleStory Universe, Avalanche's own
server, and Open Loot.

## 5. SIM swap: what is left

The rebuild is done and deployed. Remaining:

- **Crypto Shield Mobile v1.6.0** must call `/v1/sim-swap/enroll`. Until it ships, a CS Mobile user
  who enters a number gets no monitoring. That gap is now **visible** rather than silent, and it does
  not block the Twilio audit.
- **Consolidate the founder's duplicate user records.** His number is on two rows, which caused two
  separate bugs in one evening. Worth doing before it causes a third.
- Telegram `/simswap` and `STOPSIM` are implemented and deployed but **have not been exercised
  live**. Worth one pass.

## 6. Unchanged and still open

- **XSOAR demo, promised Fri 21 Aug.** Moshe is investigating. Nothing to do until he replies.
- Blue Team Village rsscan post, drafted in `btv_rsscan_post.md`, channel `#tools`, not sent.
- Bundle D Stripe Door 2, ClickFix false positives, CPPO + MSP target list.
- **The Stripe account is `business_type: individual` while RelayShield LLC is the entity named in
  the Terms, the carrier consent clause, and the Vouch and Corix policies.** Worth correcting on its
  own merits, on its own timeline, not as an MPP fix.
