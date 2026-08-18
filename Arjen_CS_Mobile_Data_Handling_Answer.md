# Crypto Shield Mobile: what we collect, where it goes, and who can reach it

Written 2026-08-09 in answer to Arjen's question: monitoring needs an email, a phone number and
wallet addresses, so does that widen the user's doxing surface, and how do we guarantee no external
party gets at it.

Everything below was verified against the deployed code and live AWS configuration, not against
documentation. Where the answer was uncomfortable it is written down anyway, along with what changed
today because of it.

---

## The short answer

Three of the four things you would worry about were already right, and one was not.

| | Status |
|---|---|
| Does a database hold your email, phone or wallet after a scan? | **No.** The screening endpoints persist nothing |
| Is the data encrypted in transit and at rest where it is stored? | **Yes**, and phone numbers in the older Telegram product are KMS-encrypted plus separately hashed |
| Can a third party query us for a user's history? | **No.** There is no endpoint that returns "what has this person been screened for" |
| Was there a durable, plaintext record of every person screened? | **Yes, in the logs. Fixed today.** |

---

## 1. What the app asks for, and why each one

- **Wallet addresses.** Needed to watch the chain for activity on them. Public data by
  construction: an address is already visible to anyone with a block explorer.
- **Email.** Needed to query breach and infostealer corpora. This is the same input HIBP takes.
- **Phone number.** Needed for SIM swap detection, which is a carrier lookup keyed on the number.

None of the three is optional for the feature it drives, and none is used for anything else. The app
does not ask for a name, a date of birth, an address or a government identifier.

## 2. Where each one is stored

**On the device.** Wallets, monitored emails, the phone number and the API key live in
`expo-secure-store`, which is the iOS Keychain and the Android Keystore. They are written under
`cs_wallets`, `cs_monitored_emails`, `cs_phone_number` and `cs_api_key`. Deleting the app wipes them.

**On our servers, the honest inventory:**

- `handle_breach`, `handle_sim_swap`, `handle_infostealer` and `handle_wallet_risk` **write nothing
  at all.** They are pass-through queries: the value arrives in the request, is used to query the
  upstream corpus, and is discarded when the Lambda returns. I verified this by walking each function
  body for any `put_item`, `update_item` or `delete_item` call. There are none.
- The **only** server-side write in the Crypto Shield Mobile path is `register-push`, which stores
  the Expo push token, the wallet addresses being watched, and NFT collections. That is unavoidable:
  the server cannot push you an alert about an address it does not know. It stores **no email and no
  phone number**.

So the answer to "does monitoring build a profile of me" is that for email and phone, we hold
nothing between one scan and the next. For wallets, we hold the addresses and nothing else.

## 3. Which external parties see what

This is the part worth being precise about, because "no external party gains access" is not a
promise we can honestly make in absolute terms. Screening inherently means asking someone else.

| Data | Goes to | Why | What they get |
|---|---|---|---|
| Email | Have I Been Pwned | Breach corpus lookup | The email |
| Email | Hudson Rock (Cavalier) | Infostealer log lookup | The email |
| Phone | Twilio Lookup | Carrier and SIM swap signal | The number |
| Wallet address | GoPlus, Blockstream, TONAPI | Chain risk signals | The address, which is already public |
| Email | Stripe | Billing only, for paying users | The email |

Each of those is a contracted processor with its own published privacy terms, and each receives
only the single field it needs. None receives a bundle. Twilio never learns the user's email, HIBP
never learns their phone number, and GoPlus never learns either. **The correlation between a user's
email, phone and wallets does not exist outside their own device.**

That is the strongest privacy property in the design and it happened on purpose. It is worth saying
plainly to a customer: we cannot dox you by joining your identifiers together, because we never hold
them joined.

## 4. What was wrong, and what changed today

**The finding.** Every screening handler logged its subject in plaintext. Lines like
`breach check email=<the actual address>` and `sim-swap check phone=<the actual number>` went to
CloudWatch on every single call. And **all 54 relayshield log groups had retention set to `None`,
meaning never expires.**

So while no table held this data, the logs did, permanently. A durable record of which humans were
screened and when existed, and nobody had designed it. That is exactly the surface the question was
asking about, and answering the question is what surfaced it.

**Fixed and deployed today.** All 18 log statements that emitted an email or a phone number now pass
the value through a salted, truncated SHA-256 first, so a line reads `em#70f6574938cc` instead of the
address. The salt is generated fresh at container start by default, which makes the hashes
deliberately **unlinkable across time**: you cannot assemble a history of one person out of the logs
even with full access to them. Operational debugging still works, because within a single execution
context the same subject still hashes the same way.

**Still open, and it is a decision rather than a fix.** Log retention is still unlimited on all 54
groups, and the historical logs written before today still contain plaintext. Setting a retention
window would age those out, but it also permanently deletes operational and billing history, so it
should be a deliberate choice rather than something done quietly.

## 5. Who can reach the data we do hold

- Every API call requires a key, and keys are scoped: a Crypto Shield Mobile key reaches only the
  small set of endpoints the app uses, not the wider catalogue.
- The API Lambda's IAM role grants per-table access by explicit ARN, with no wildcard. A component
  cannot read a table it was not specifically granted.
- Data is encrypted in transit by TLS and at rest by DynamoDB's default encryption. In the older
  Telegram product, phone numbers additionally get KMS envelope encryption plus a separate SHA-256
  hash used for lookups, so the lookup index never contains the number itself.
- There is no endpoint, for any customer or partner, that answers "show me this person's screening
  history". The data to answer it is not retained.

## 6. What I would tell a customer who asks this

The three inputs are the queries, not a profile. We keep the wallet addresses because pushing you an
alert requires knowing what to watch. We do not keep your email or your phone number after the
answer comes back. The only parties who see any of it are the corpora we have to ask, and each one
sees a single field, never the set. The one place a durable record had accumulated by accident was
our own logs, and that was closed on 2026-08-09.

---
NOT FOR SENDING AS-IS

- Founder decision needed on log retention before this goes to Arjen, because section 4 commits to
  the state of it. Recommended: 90 days on the 54 groups. The command is in the session notes.
- Section 4 discloses a defect we found and fixed. That is the right call for a business partner who
  asked a direct security question, and it is the reason the rest of the document is credible. Do
  not strip it.
- Numbers deliberately omitted: IOC corpus size and channel count drift between surfaces, and this
  document does not need them.
