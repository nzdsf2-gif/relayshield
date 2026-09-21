# Bundle B: the eight steps to published. Nothing is unresolved.

**Everything that was open is now measured.** The only reads left are verifications.

| Fact | Value | How it was settled |
|---|---|---|
| Bundle B product code | **`cmh79gzztkdtp0dlzbdepa643`** | Carries `attack_surface_bundle_access`, expiring `2026-10-19T16:40:10`, which matches the agreement's `endTime` to the millisecond |
| Bundle B entity | `prod-szi2wdww3obry` | The agreement's own `resource`, ACTIVE, acceptor `442429445748` |
| Bundle B customer id | **`hEXRdWpDgwB`** | The `CustomerIdentifier` on that entitlement |
| Bundle A product code | `cvfvhwhmichl13kcuuutkbwmp` | Paired with `core_identity_exposure` in our own key table |
| Bundle D product code | `46y72j0d99w7lyqkiqrakpc5k` | Paired with `agentic_attack_surface` in our own key table |
| `7ws2zmbdyk70tq34pr0pea0s2` | **NOT Bundle B.** Has no entitlements at all, for any customer | Unfiltered `GetEntitlements` |

**THE ONE THING THAT IS STILL ODD, AND IT DECIDES STEP 4.** The entitlement sits under
`hEXRdWpDgwB`, and both fulfillment attempts logged `customer=fHL5zV6grGn` while correctly
resolving product `cmh79gzztkdtp0dlzbdepa643`. `fHL5zV6grGn` is the identifier on an August
Bundle A purchase. **An AWS CustomerIdentifier is issued per customer per product**, so two
identifiers on one product means the registration token came from a different signed-in
identity than the one holding the agreement.

**So step 4 is done signed into `442429445748` specifically, and step 5 checks which identifier
came back.** That is the difference between a key that can meter and a key that cannot.

---

## STEP 1 -- ANDREW CLICKS THIS. Set three environment variables.

1. Open
   <https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/relayshield-bundle-fulfillment>
2. **Check the top right reads `239677749008`.** If it reads `620534471984` you are in the
   pre-audit account; switch first.
3. Tab **Configuration** -> **Environment variables** (left list) -> button **Edit**.
4. Row `BUNDLE_B_PRODUCT_CODE` currently holds `622fa036203fb4ea59ea180be6d4570757ec755e`.
   Change its **value** to:

       cmh79gzztkdtp0dlzbdepa643

5. **Add environment variable** -> key `BUNDLE_A_PRODUCT_CODE`, value:

       cvfvhwhmichl13kcuuutkbwmp

6. **Add environment variable** -> key `BUNDLE_D_PRODUCT_CODE`, value:

       46y72j0d99w7lyqkiqrakpc5k

7. **Change nothing else.** The block holds live secrets. -> button **Save**.

EXPECT: the list redisplays with all three present.
STOP IF: `ResourceConflictException` -- a deploy is in flight. Wait a minute, press Save again.

**Steps 5 and 6 are a live defect, not Bundle B housekeeping.** With those unset,
`_deactivate_api_key` matches no key row, so a cancelled Bundle A or Bundle D customer keeps a
working key on two listings that are already public.

## STEP 2 -- ANDREW RUNS THIS. Confirm the edit landed.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh

EXPECT: section 1 shows three 25-character codes, and section 2 is **no longer SKIPPED** --
it prints the two topic ARNs and almost certainly `NO SUBSCRIPTIONS`, which is step 3's job.
STOP IF: section 1 still shows the 40-hex string. Save did not take; repeat step 1.

## STEP 3 -- ANDREW RUNS THIS. Subscribe to Bundle B's SNS topics.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/subscribe_bundle_sns.sh cmh79gzztkdtp0dlzbdepa643

EXPECT: `added` then `subscribed:` for BOTH the subscription and entitlement topics.
**Run it a second time. Every line must then read `already present` / `already subscribed`.**
That re-run is the verification; there is no other.
STOP IF: `AuthorizationError` on subscribe -- the topic policy refuses this account, which for
a marketplace topic means the product is not ours. Send me the output.

**This is the step that provisions the key.** `relayshield_bundle_fulfillment.py` issues the API
key on `subscribe-success`, and with no subscription that event never arrives. Nothing in this
repository has ever created one of these; Bundle D's and Bundle A's were made by hand years of
sessions ago and nobody recorded it.

## STEP 4 -- ANDREW CLICKS THIS. Re-follow the fulfillment redirect, from the RIGHT account.

1. **Sign out of AWS entirely**, then sign in as **`442429445748` (TestUser)**. This is the
   account named as `acceptor` on the agreement, and it is the one whose identifier holds the
   entitlement.
2. AWS Marketplace -> **Manage subscriptions** -> the **Attack Surface & Supply Chain**
   subscription -> **Set up your account**.
3. It lands on `api.relayshield.net/developers`. Enter an email when asked.

EXPECT: a RelayShield page showing a key beginning `rs_live_`.
STOP IF: "your subscription is being set up and needs a quick manual check". That is
`_resolve_bundle` returning None again; go straight to step 5, which names which of the two
reasons fired.

**Signing in as the right account is the whole point of this step.** The previous two attempts
resolved the correct product and a customer identifier that holds no entitlement, which is what
a token issued to a different identity looks like.

## STEP 4b -- THE REDIRECT DOES NOT ISSUE THE KEY. ADDED 2026-09-21.

**The email you type is only where the key is SENT and what gets stored on the key row. Nothing
validates it against AWS**, so use an inbox you can actually open. `nzdsf4@gmail.com` is fine;
so is any other.

**But the page will very likely say "your key is being provisioned and will arrive by email",
and no email will come.** Read from the code rather than assumed:

- `_handle_email_confirmation` **only DISPLAYS** a key that already exists. It stores the email
  and renders the fallback text when the key is not there.
- `_provision_api_key` is called in **exactly one place**: the SNS `subscribe-success` branch.
- **Bundle B's `subscribe-success` fired on 2026-09-19**, when nothing was subscribed to that
  product's topic. **SNS does not replay what a subscriber missed**, so subscribing in step 3
  covers the NEXT customer and cannot bring this one back.

So for this agreement the provisioning event is gone, and the fix is to replay it:

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/replay_subscribe_success.sh hEXRdWpDgwB cmh79gzztkdtp0dlzbdepa643

EXPECT: the entitlement printed, `payload is valid JSON`, then `"StatusCode": 200`.
STOP IF: `REFUSING: no entitlement for customer=...` -- it reads the entitlement BEFORE invoking
and refuses rather than writing a key with no `LicenseArn`, which would serve calls and meter
nothing while looking like success.

**This is a replay, not a fabrication.** It invokes our own function, in our own account, with
the event AWS already sent. Every value that matters is then read back FROM AWS by the handler:
`GetEntitlements` supplies the dimension, the `LicenseArn` and the `CustomerAWSAccountId`. The
payload asserts only WHICH customer and WHICH product to look up.

**The `LicenseArn` is the whole point.** `BatchMeterUsage` identifies the product from it under
Concurrent Agreements, so a key provisioned outside this path carries none and every metered
call is dropped with `Skipping bundle usage report` -- served, unbilled, and counted as zero by
the audit. Your offer page already shows the license exists:
`l-1285003a7867450784813d7fda977cb7`.

**The key arrives by welcome email**, at whatever address you typed.

## STEP 5 -- ANDREW RUNS THIS. Which customer identifier came back?

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh

EXPECT: section 3 shows `... fulfillment entitlement check customer=hEXRdWpDgwB active=True`,
and section 4 shows a `pending_hEXRdWpDgwB` row.
STOP IF: section 3 shows `Bundle unresolved ... customer=fHL5zV6grGn` again. The browser was
still signed into the other account. Repeat step 4 after signing out properly.
STOP IF: section 3 shows `Bundle mismatch`. The env var did not save; repeat step 1.

**`active=True` is the line that matters.** It is the first successful `GetEntitlements` for
this product, which is AWS audit issue 1.

## STEP 6 -- ANDREW RUNS THIS. One metered call.

    read -rs "RS_KEY?Paste the rs_live_ key from step 4, then press Enter: "
    curl -sS -i -X POST https://api.relayshield.net/v1/metered/threat-actor \
      -H "X-RS-API-KEY: $RS_KEY" -H "Content-Type: application/json" \
      -d '{"actor":"lazarus"}'

EXPECT: `HTTP/2 200` and a JSON body.
STOP IF: 402 or 403 -- the key carries no Bundle B entitlement, so step 4 did not complete.
STOP IF: 401 -- the key was mistyped. It is read with `-rs` so it never echoes; re-run the two
lines together.

`threat-actor` is chosen deliberately: it is the one of the five endpoints that makes **no
outbound third-party call**, so no vendor outage can turn a metering test into a false failure.

## STEP 7 -- ANDREW RUNS THIS. Confirm the meter actually fired.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh

EXPECT: section 5 shows `Marketplace usage reported account=... dimension=threat_actor_calls`.
STOP IF: `Skipping bundle usage report: missing account/license_arn/dimension`. The call was
served and NOT metered, because the key row carries no `LicenseArn` -- which happens when the
key was created outside the `subscribe-success` path, so step 3 did not take. AWS counts that
as zero either way.

**A served call and a metered call are different events, and only the second clears audit issue
2.** This is the step that has no substitute.

## STEP 8 -- ANDREW CLICKS THIS. Resubmit the visibility request.

AWS Marketplace Management Portal -> SaaS products ->
**RelayShield - Attack Surface & Supply Chain API** -> **Update visibility** -> Public.

**Only after steps 5 and 7 have both shown their EXPECT line.** Both audit issues must be true
at once and each is a different event; resubmitting on one of them costs another audit cycle.

---

## If anything stops, send me the output of

    AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh

and nothing else. Its five sections separate every failure these eight steps can produce.
