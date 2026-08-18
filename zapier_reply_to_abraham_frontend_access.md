# Reply to Abraham D. (Zapier Developer Support): front-end access

**Status:** DRAFT, pending founder review. Do not send until approved.
**Their message:** 2026-08-04 20:03. API documentation requirement is **CLEARED**.
**Their ask:** reset the password and store the credentials for the test account; confirm how users
log in; they need access to the same front end users use. Stated as the last step before publishing.

## Why this draft is structured the way it is

His phrasing gives it away: *"the next and last step of the process is to reset the password and
**store the credentials for the test account**"*. That is not a question, it is a checklist item
with a form field he has to populate before he can hit publish.

So this reply **hands him the credential first** rather than explaining a philosophy first. An
earlier draft opened with "there is no login" and buried the offer of a test account at the bottom
as a conditional. That was accurate but it would have cost a round trip, and to a reviewer working
a checklist it can read as refusing a mandatory step.

Order here: answer his literal question in one line, give him the credential, then mention
self-serve as a convenience. No conditionals, nothing for him to ask twice.

## The test account: delivered through the product itself

**No credential is handed over in this thread, and none needs to be.**

The founder signed up `integration-testing@zapier.com` on the live page, which is Zapier's own
documented convention for test accounts. RelayShield emails the key to whatever address signs up,
so the key was delivered straight into an inbox Zapier already controls. It never passes through
an email body, a support thread, or a chat transcript.

That also answers his actual question in the most direct way available: the flow he was asking to
see is the flow that produced his credential.

- Allowance raised from the standard free-tier 20 to **5,000 calls**. A support key that silently
  402s mid-review, or six months later while they are helping a customer, would be worse than no
  key at all.
- Verified live against production on all three surfaces the integration touches:
  `POST /v1/account/info`, `POST /v1/metered/breach`, `POST /v1/webhook/configure`.
- **To revoke later:** set `active=false` on that row in `relayshield_api_keys`.

**Correction worth recording:** there is no "secure credential field" in an active Zapier support
thread. That field lives in the Publish / submit-for-review form in the Platform UI and is
completed at submission time. An earlier version of this note said otherwise.

---

## The reply

Hi Abraham,

Thanks, and good to hear the documentation clears that requirement.

To answer your question directly: there is no password, because RelayShield has no web application
or user dashboard. It is an API-only product, and the API key is the only credential a user ever
holds. That is the same credential the integration authenticates with, so there is nothing separate
to reset.

**For the test account, I have created one using integration-testing@zapier.com, following your
standard convention.** The API key was issued to that address the moment the account was created,
so it should already be sitting in that inbox. That key is the credential for the test account,
and it is the only credential there is.

I have raised the call allowance on it well above our normal free tier, so it will not run out
while your team is using it for support. I have also verified it against production on all three
surfaces the integration touches: the connection test, a live data call, and webhook registration.

For the front end, here is the complete flow a user goes through:

1. They go to https://api.relayshield.net/developers
2. They enter their email address. No password, no credit card.
3. Their API key is emailed to them immediately, with 20 free calls included.
4. They paste that key into the Zapier connection.

That is the entire user-facing experience. There is no account to log into afterwards.

You are very welcome to run that signup yourself at any time if it helps to see exactly what a user
sees when reproducing a support issue. It takes about ten seconds and needs no payment method, so
your team can generate a fresh account whenever one is useful.

Two things that may save your support team time:

- The connection test calls `POST /v1/account/info`, which is free and unmetered. It returns the
  plan, the account email and whether the key is active, so a failed connection is almost always a
  mistyped or inactive key rather than anything deeper.
- Full reference for every endpoint, with parameters, response fields and error codes, is at
  https://api.relayshield.net/docs

The only other account surfaces are Stripe-hosted: the checkout page for adding a payment method
once the free calls are used, and Stripe's billing portal. Those authenticate through Stripe rather
than through us.

That should be everything for the last step. Let me know if anything else is needed to publish.

Best regards,

Andrew Gibbs
RelayShield LLC
support@relayshield.net

---

## Notes for the founder

- **Nothing to paste.** The key went to `integration-testing@zapier.com` through the normal signup
  email. Do not restate the key in the reply; it is already in their inbox and repeating it in a
  support thread that gets archived and forwarded would undo the point.
- **The earlier `partners@relayshield.net` key is now redundant.** Deactivate it unless you want a
  spare, since a live 5,000-call credential with no owner is not worth leaving outstanding.
- **What is different from the earlier draft:** the credential leads, the explanation follows, and
  the self-serve signup is offered as a convenience rather than as a task for him. Same facts, one
  fewer round trip.
- **Residual risk, unchanged by wording.** If Zapier's process has a hard requirement for a
  browser-accessible login UI, no reply clears it. I do not believe it does, since API-key-only
  products are published on Zapier routinely, but if he comes back insisting on a login screen then
  that is a product decision about building an account dashboard, not a documentation one. Do not
  build one to unblock a single review without weighing it on its own merits.
- **Revoke when the review closes** if you would rather not leave a long-lived 5,000-call key
  outstanding: set `active=false` on that row. Their support use case argues for leaving it live.
