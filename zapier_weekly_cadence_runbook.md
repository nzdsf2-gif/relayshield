# Zapier: move the 12 test Zaps from daily to weekly

*Written 2026-08-20. Purpose: get 133 held tasks off hold and stop the cap being re-blown.*

## Read this first — there are no CLI commands for this

**Zapier has no public API for editing a Zap's trigger schedule.** The Platform CLI (`zapier`)
manages *integrations* you publish — versions, deploys, validation — not the Zaps in an account.
There is no `zapier zap update` and no REST endpoint for it.

So the steps below are a **UI click-path**, not shell commands. Anyone who tells you to script this
is describing something that does not exist. This needs the founder in a browser; roughly five
minutes.

## The arithmetic, so the target is clear

| | Tasks/month |
|---|---|
| 12 Zaps × daily (~30 fires) | ~360 |
| Plan cap | 100 |
| 12 Zaps × weekly (~4.3 fires) | ~52 |

Weekly leaves ~48 tasks of headroom, which is what the real embed signup needs in order to fire the
beta early-exit trigger.

## Click-path

1. Go to **zapier.com/app/zaps**.
2. Filter to the 12 test Zaps — they are named `Daily … — RelayShield`. Search `— RelayShield` to
   pull the set together, and **count them: you should see 12.** If the count is different, stop and
   reconcile before changing anything; the 360 figure depends on it.
3. For **each** Zap:
   a. Click the Zap to open the editor.
   b. Click the **trigger** step (the first card — Schedule by Zapier).
   c. Open the **Configure** tab (older UIs call it "Set up trigger").
   d. Change the trigger event from **Every Day** to **Every Week**.
      * If Zapier makes you re-pick the event rather than edit it, choose **Every Week** and
        re-select the app *Schedule by Zapier* — the action steps below are preserved.
   e. Set **Day of the week**. **Spread these across the week** rather than putting all 12 on
      Monday: a single day means 12 tasks land at once and a burst is what trips a cap.
   f. Set **Time of day**. Keep it off the hour if the option exists.
   g. **Test the trigger**, confirm it still passes, then **Publish**.
4. After all 12: go to **zapier.com/app/history** and confirm no new held tasks are accumulating.

## Guardrails, carried forward and still binding

* **Do not delete any Zap or template.** They are the live-usage evidence for the partner listing.
* **Do not enable pay-per-task.**
* **Do not replay the held tasks.** They are not auto-replayed, and replaying them would immediately
  re-blow the cap — which is the exact hole this exercise is climbing out of. Let them expire.

## Then: request the Partner Sandbox

Zapier Partners Support confirmed on 2026-08-19 that **now the integration is public, the Partner
Sandbox is available** — premium Zapier features free, intended for ongoing integration
development.

Path: **Zapier developer platform → your integration → Manage → Manage team → "Zapier Partner
Sandbox" panel → Request access.**

**This is the real fix, and it should be done regardless of the weekly change.** The cap problem
exists because integration testing is being paid for out of a consumer task allowance. The Sandbox
is designed to carry exactly that load — which means the weekly cadence is the tourniquet and the
Sandbox is the treatment. Do both, in this order, because the request may take days to be granted.

## New ToDo: template → flywheel

**Add a new template to the Zapier dev sandbox to pave the path to a flywheel.**

The mechanism worth building toward: published templates are Zapier's own discovery surface. A user
who installs a template becomes a live integration user without ever visiting relayshield.net, which
is the acquisition loop the embed was meant to start and the held tasks have been blocking.

Sequence:

1. Get Sandbox access (above) so template development stops consuming the 100-task cap.
2. Build and test the new template **in the Sandbox**, not the production account.
3. Publish, then measure installs — not task count.

Five template ideas were drafted previously in `zapier_integration_description.md` and the
2026-08-1x session notes; pick from those rather than starting cold.

**Sequencing note:** do not build the template before Sandbox access lands. Building it in the
production account is what would re-blow the cap a second time, for the same reason as the first.
