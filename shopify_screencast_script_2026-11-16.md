# Shopify item 4.5.3 screencast: dry run and talking points (2026-11-16)

Reviewer's words: "Please provide a comprehensive screencast showing that it passes and the fail message."
This is one video, about three minutes, narrated (the earlier clips were silent). It answers 4.5.3 only. The four items from 11-15 are separate.

## Correction to what I told you earlier

A clean order does NOT show 0/100. The live check returns a baseline of **15/100, level "unknown"**, because the shop's own URL is part of the check. Tested against the live endpoint on 2026-11-16 with three ordinary addresses: all returned `unknown`, `15`, reasons "no flags found by link check" and "no email risk flags". The two fixture addresses return 55 and 85. The app has no badge that says "pass": the badge reads `unknown`, and the filter calls that level "No flags found". Say that out loud in the video (talking points below).

## What each of the three orders must produce

| | PASS | FAIL medium | FAIL high |
|---|---|---|---|
| Customer email | `jane.smith.test@gmail.com` | `fixture-medium-test@relayshield.net` | `fixture-high-test@relayshield.net` |
| App table badge | `unknown` | `medium` | `high` |
| Score | 15/100 | 55/100 | 85/100 |
| Reason column | no flags found by link check | Fixture: synthetic medium-risk address for App Store screenshots | Fixture: synthetic high-risk address for App Store screenshots |
| Tag in Admin | none | `relayshield-review` | `relayshield-high-risk` |
| Order note | yes, 15/100 (unknown) | yes, 55/100 (medium) | yes, 85/100 (high) |

The note on each order reads: `RelayShield screened order #N: composite risk S/100 (level). Signals: <reasons>. This is a risk signal, not proof of safety; review before fulfilling. Nothing was changed automatically.`

Values for the two fixture rows come from running `fixtureVerdict`, `verdictActions` and `buildOrderNoteLine` from `shopify/worker.js` on these addresses. Values for the PASS row come from the live `composite-check` endpoint. The Shopify side (does the webhook fire, does the tag appear) has NOT been seen by me: that is what the dry run proves.

**Use the same three addresses in the dry run and in the recording** (changed 2026-11-17; the first version of this file said to use `-dryrun` names). The table already held 21 rows before the dry run, so separate names buy nothing, and the rehearsal should be identical to the take. Nothing in the Worker stops the same address being screened twice: each order is screened on its own.

**Create all three orders live, while recording, and rehearse the same way.** Pre-made orders only show the reviewer a finished table. Live creation shows cause and effect: the order is paid, then the verdict appears. While the 15-second wait runs, talk (for example: "RelayShield screens the order as soon as Shopify tells it a new order exists").

**Same customer twice:** from memory, Shopify may refuse **Create a new customer** with an email that already exists. On the second pass (the recording) search the email in **Add customer** and select the existing customer instead. If it errors, send me a screenshot.

Older rows stay in the table. In the recording the newest order is at the top; use the **Show** filter when you want one level only.

## Before either run

1. Open the app. Plan panel must say "N of 100 free checks used" with N well under 100. At 100 the app stops screening and nothing below will work.
2. Settings: **Tag medium-risk orders** ticked, **Add a RelayShield line to the order note** ticked. Click **Save settings**, wait for "Saved.". Clip A unticked the note box on Saturday and the setting may have survived.

## Order steps (same for all three, from memory of Shopify's screens)

Admin, **Orders**, **Create order**. Add any product. **Add customer**, **Create a new customer**, enter the email from the table, save. **Collect payment**, **Mark as paid**. Wait 15 seconds. In the app click **Refresh**.

If the order has no email on it, nothing below works: the screening reads the order's email.

## Talking points

**Opening (10 seconds).** "This is RelayShield Order Screening on a Shopify development store. It screens each new order's customer email and store URL, then shows the result in the app and writes it back to the order. It never cancels, holds or refunds an order. That stays the merchant's decision."

**Order 1, PASS: `jane.smith.test@gmail.com`.**
- "This is an ordinary order. RelayShield found nothing against it."
- "In the app it shows level 'unknown', score 15 out of 100, reason 'no flags found'. 'Unknown' is how we say nothing is known against this order. The filter calls the same thing 'No flags found'."
- "In the Shopify order list there is no RelayShield tag, so the merchant is not interrupted."
- "The order note still records the check, and it says plainly this is not proof of safety."

**Order 2, FAIL medium: `fixture-medium-test@relayshield.net`.**
- "This order is flagged medium risk, 55 out of 100."
- "The merchant sees a `relayshield-review` tag in the Orders list, and the same result in the app table."
- "Open the order: the note says composite risk 55 out of 100, medium, and 'Nothing was changed automatically'. The merchant decides whether to look closer."
- "Medium tagging is a setting. The merchant can switch it off here." (point at **Tag medium-risk orders**, do not click it)

**Order 3, FAIL high: `fixture-high-test@relayshield.net`.**
- "This order is flagged high risk, 85 out of 100."
- "It gets the `relayshield-high-risk` tag. In the Orders list this is the one a merchant will see before fulfilling."
- "Open the order and scroll to the note: composite risk 85 out of 100, high, with the reason, and the line 'review before fulfilling'."
- In the app, choose **Show**, **High risk**: only this order remains. Choose **All screened orders** to go back.

**Closing (10 seconds).** "To summarise: normal orders pass untouched, medium and high orders are tagged and noted, and every decision stays with the merchant."

## One honesty line, say it once

"The two flagged orders use synthetic test addresses built into this development store so the flagged result can be shown on demand. They run the same tagging and note code as a real flagged order."

Do not say these two orders were detected as real fraud. They were not: the fixture returns a canned verdict.

## After the dry run

If all three match the table: record the real take with the `-test` addresses. If any row differs, send me a screenshot of the app table and the order page before recording.
