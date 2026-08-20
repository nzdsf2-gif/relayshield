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

## Also: request the Partner Sandbox — but it does NOT fix the cap

**Correction to an earlier note in this file.** It previously said the weekly change was a
tourniquet and the Partner Sandbox was the treatment. **That was wrong**, and the distinction
matters enough to state plainly:

**The Zapier Partner Sandbox (ZPS) is a separate *workspace*, and it does not raise the task limit
on the workspace where the 12 Zaps live.** Per Zapier's own ZPS documentation:

* It "gives your integration team access to **a workspace** with premium Zap features at no cost."
  You keep using your existing login; it is a second workspace, not an upgrade to the current one.
* It is scoped to integration development and "demonstrations of specific illustrative workflows."
* **"You agree not to submit any production data through Zaps created within the workspace."**
* It explicitly does **not** include pay-per-task billing.

So the weekly cadence change is **the fix**, not a stopgap. It is the only thing that resolves the
existing workspace's cap. The Sandbox is where *new template development* belongs — which is exactly
what the flywheel todo below needs, and nothing more.

**Eligibility and route.** ZPS is open to partners with a **beta or public** integration, and any
Admin or Collaborator on the team can request it. RelayShield shows `Public` `Beta`, so it qualifies
— which matches what Partners Support said on 2026-08-19.

Path: **`https://developer.zapier.com/` → select the RelayShield integration → Manage → Manage team
→ the "Zapier Partner Sandbox" panel at the top → Request access.**

There is a per-integration deep link of the form `developer.zapier.com/app/<APP_ID>/...`, but the
app ID is not recorded anywhere in this repo and every `zapier.com` domain is egress-blocked from
the sandbox, so it could not be verified. **Two clicks from the root beats a guessed URL that
404s.** Program details: `docs.zapier.com/integrations/publish/zps`.

**Request it now anyway** — approval is not instant, and the template work below is blocked behind
it.

### Open question before moving anything into the Sandbox

Do **not** migrate the 12 test Zaps into the Sandbox workspace on the assumption it solves the cap.
Two reasons: the no-production-data restriction, and — more importantly — those Zaps exist to be
**live-usage validation evidence** for the partner listing. Whether usage inside a sandbox workspace
still counts toward that is unknown, and getting it wrong would destroy the exact evidence they were
created to produce. **Ask Zapier Partners Support before moving them.** Until there is an answer,
they stay where they are, on a weekly cadence.

## New ToDo: template → flywheel

**Add a new template to the Zapier dev sandbox to pave the path to a flywheel.**

The mechanism worth building toward: published templates are Zapier's own discovery surface. A user
who installs a template becomes a live integration user without ever visiting relayshield.net, which
is the acquisition loop the embed was meant to start and the held tasks have been blocking.

Sequence:

1. Get Sandbox access (above) so template development happens in the workspace built for it,
   rather than consuming the production workspace's 100-task cap.
2. Build and test the new template **in the Sandbox**, not the production account.
3. Publish, then measure installs — not task count.

Five template ideas were drafted previously in `zapier_integration_description.md` and the
2026-08-1x session notes; pick from those rather than starting cold.

**Sequencing note:** do not build the template before Sandbox access lands. Building it in the
production account is what would re-blow the cap a second time, for the same reason as the first.


---

# 2026-08-20 — you cannot publish the weekly change this cycle

**What happened:** publishing the daily→weekly edit was refused at **103 of 100 tasks**.

**Why, and why no amount of editing fixes it:** Zapier will not let you turn a Zap **on** while the
account is over quota, and publishing an edit *is* turning it on. Task counts do not go down — 103
is spent for this billing cycle. **So the weekly change cannot be published until the cycle
resets.** That is not a setting to find; it is the quota doing what it does.

## Do this instead, today

**Turn the daily Zaps OFF.** Toggling a Zap off is a switch on the Zaps list — it needs no test run
and no publish, so **it works while over quota**, which is the whole point.

1. **zapier.com/app/zaps** → search `— RelayShield`.
2. Toggle **off** the daily test Zaps.
3. Held tasks stop accruing, and the daily warning emails stop with them.

That directly answers "not sure there is a way to avoid the daily warnings about growing on-hold
Zaps." **Turning them off is the way** — the warnings are generated by Zaps that are on, held, and
still firing.

## Then, on the cycle reset date

1. Note the reset date from **zapier.com/app/settings/billing**.
2. On reset: open each Zap, change the trigger to **Every Week**, spread the days across the week,
   **publish**, and toggle back on.

Off now, weekly on reset — the cap is never re-blown, and the evidence of live usage resumes.

## Correction: the Sandbox is bigger than assumed

The approval email states the terms plainly, and one number was missing from the earlier note:
premium apps, multi-step Zaps, paths, and **2,000 tasks per month**. That is **20× the production
account's 100**.

Also now confirmed: **Integration ID `243026`**, workspace granted to `relayshieldadmin@gmail.com`.
Access path: log in → circle icon, top-right → switch workspace.

**This does not change the advice.** The Sandbox is a *separate workspace* and its terms forbid
production data, so it does not lift the production account's cap and the 12 Zaps do not move there.
What it does change is the template work: 2,000 tasks/month is ample, and there is now no reason to
build or test anything in the production account again.

## ToDo: seed the flywheel with a NEW template

**Founder direction 2026-08-20: it must not be one of the existing 12 Zaps.** Those are test Zaps
that prove the integration runs. A template is a different artefact — a published, installable
workflow that a stranger finds in Zapier's directory and installs, becoming a live integration user
without ever visiting relayshield.net. That is the flywheel; re-publishing a test Zap is not.

Build it **in the Sandbox** (Integration ID 243026).

Candidate templates, each pairing a RelayShield trigger with a popular destination so it surfaces in
*both* apps' directories — which is the actual discovery mechanism:

| Template | Shape | Why it earns installs |
|---|---|---|
| **Breach alert → Slack** | RelayShield breach → Slack channel | Slack's directory is enormous; "tell my team when someone's credentials leak" needs no explanation |
| **Breach alert → Google Sheets** | append a row | The universal "just log it somewhere I can see" workflow; zero-cost to try |
| **New employee → add to breach monitoring** | HR/Google Form → RelayShield | Onboarding, and it lands us inside a recurring business process rather than an alert feed |
| **Wallet risk flag → Discord** | wallet-risk → Discord webhook | Pairs directly with the gaming-community outreach; the same audience, a different surface |

**Pick the Slack one first.** Biggest directory, clearest one-line value, and the least setup for
someone who has never heard of us.

Measure **installs**, not task count. Task count is what got us here.
