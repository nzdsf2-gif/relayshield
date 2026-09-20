# Bundle B: Architecture details, and the pricing to check against

Paste-ready copy for the AWS Marketplace Management Portal, product
**RelayShield - Attack Surface & Supply Chain API**, entity `prod-szi2wdww3obry`.

## 0. THE FORM IS ONE RADIO BUTTON. THE ANSWER IS "None of the above."

Read from the form itself on 2026-09-20. It asks only for an **AWS hosting pattern**, four
options, no description box and no upload.

**Pick "None of the above."** Its own text says: *"Although it's not considered deployed on AWS,
you can continue publishing in AWS Marketplace."* That satisfies the required field, clears the red
badge, and unblocks Update visibility.

### Why not "The product runs entirely on AWS"

Because that option requires *"the application plane, control plane and any 3rd party dependencies
(including LLMs) run on AWS"*, and two of Bundle B's five endpoints depend on services that are not
in our AWS account or the buyer's. Read out of `relayshield_api.py` rather than recalled:

| Endpoint | Outbound dependency | Where |
|---|---|---|
| `/v1/metered/supply-chain` | `_check_vendor_domain` | **haveibeenpwned.com**, a paid commercial API |
| `/v1/metered/secret-scan` | `_github_secret_scan` and five artifact scanners | github.com, registry.npmjs.org, pypi.org, hub.docker.com, huggingface.co, www.postman.com |
| `/v1/metered/asset-intel` | none | |
| `/v1/metered/threat-actor` | none | |
| `/v1/metered/session-risk` | none | |

Have I Been Pwned is the one that settles it. A public package index can be argued as reading the
open internet rather than depending on a component; **a paid commercial API our endpoint cannot
answer without is a third-party dependency by any reading.** Option 1 would be a claim a reviewer
can check, on a public listing, and it would be false.

### Why not "Only the application plane runs on AWS"

That option describes a product whose **control plane runs OUTSIDE AWS**. Ours does not: key
issuance, entitlement, metering and configuration are all Lambda, DynamoDB and the Marketplace
APIs. Picking it would misdescribe us in the opposite direction.

### What this costs, and why it is reversible

It forgoes the "Deployed on AWS" designation, which is a search-result badge, not an eligibility
requirement. The form says an unapproved submission can be sent again, and architecture details can
be updated later, **so this is a decision you can revisit once somebody has actually read the
Architecture guidelines page** (it is egress-blocked from this container, so I have not). Today the
asymmetry is the whole argument: "None of the above" satisfies the gate in one click, and a
rejected assessment on the last gate before go-public is another round.

**The diagram and description below are NOT needed for this form.** Keep them: AWS's 2025 SaaS
policy requires an architecture diagram in the portal as part of product validation, and the
description is the text to hand a reviewer who asks. They cost nothing sitting here.

---

**UNVERIFIED: I have not seen the Architecture details form.** `aws.amazon.com` and
`docs.aws.amazon.com` both return HTTP 000 from this container, and no session has recorded
that form's fields. So this gives you a description AND a diagram, because the form asks for
one or both and guessing which would cost a round. Use what fits; the rest costs nothing.

**This is the first architecture-details submission this repo has a record of.** Bundle A and
Bundle D are both live and public, so either they carry one that no session wrote down, or the
field is not a hard gate for visibility. Worth one glance at Bundle D's own Architecture details
tab while you are in the portal: if it is filled, copy its shape rather than mine.

---

## 1. The diagram

    assets/marketplace/bundle_b_architecture.png     1600 x 900, PNG, ~170 KB

**It reaches your Mac through the merge, not through this chat.** An image sent in chat arrives
re-encoded as `.webp`, which an upload dialog filters out of the file picker so it cannot even be
selected. That cost three rounds on the miniTelegram icon. The merge block is at the end of this
file; after it, `open assets/marketplace`.

It is generated from `assets/marketplace/bundle_b_architecture.html` by headless Chromium, so a
correction is an edit to the HTML and a re-render, never an image editor.

**The AWS account number is deliberately not in it.** An account id is not a secret and it is also
not something to print on a public product page.

---

## 2. Architecture description

Paste this into the description field. It is written to be readable as one block if the form has a
single box, and it splits cleanly at the headings if it has several.

> RelayShield's Attack Surface & Supply Chain API is delivered as a multi-tenant SaaS HTTPS API.
> It is entirely serverless, runs in a single AWS Region (us-east-1) inside one AWS account, and
> uses no EC2 instances, containers or persistent compute.
>
> **Fulfillment.** A buyer who subscribes in AWS Marketplace is redirected to our registration
> URL carrying the AWS Marketplace registration token. Amazon API Gateway passes the request to
> an AWS Lambda function, which calls the AWS Marketplace Metering Service ResolveCustomer
> operation to identify the buyer and the AWS Marketplace Entitlement Service GetEntitlements
> operation to confirm the subscription. The function then issues an API key, stores it in Amazon
> DynamoDB against the customer identifier and product code, and delivers it to the buyer by
> email through Amazon SES.
>
> **Serving a call.** The customer's application calls one of five endpoints over HTTPS with that
> API key. Amazon API Gateway terminates TLS and invokes the API Lambda function, which
> authenticates the key against DynamoDB, confirms the entitlement is current, and runs the
> requested check against our indicator corpus in DynamoDB. Credentials for upstream data sources
> are read at runtime from AWS Secrets Manager; none is stored in code or in function
> configuration.
>
> **Metering.** Each successful call is reported to the AWS Marketplace Metering Service with
> BatchMeterUsage against its usage dimension. Only a successful response is metered, so a failed
> or refused call is never billed. The monthly commitment dimension is entitled rather than
> metered.
>
> **Entitlement lifecycle.** Amazon SNS delivers AWS Marketplace subscription notifications for
> entitlement changes, suspension and unsubscription. The same fulfillment Lambda function
> consumes them and deactivates the customer's key when an entitlement lapses.
>
> **Security and operations.** Every AWS Lambda function runs under its own least-privilege IAM
> role. All data in transit uses TLS 1.2 or later. All data at rest in DynamoDB and Secrets
> Manager is encrypted with AWS-managed keys. Customer request bodies are not retained; operational
> logs go to Amazon CloudWatch Logs with identifiers hashed before they are written. Availability
> and scaling come from the managed services themselves, with no instances to patch or scale.

**Services named, if the form asks for a list rather than prose:** Amazon API Gateway, AWS Lambda,
Amazon DynamoDB, AWS Secrets Manager, Amazon SNS, Amazon SES, Amazon CloudWatch Logs, AWS Identity
and Access Management, AWS Marketplace Metering Service, AWS Marketplace Entitlement Service.

**Every one of those is in the code rather than aspirational.** If the form asks you to attest to
the deployment, this is an accurate description of what runs today.

---

## 3. The pricing, which is already submitted

You asked for the pricing to fill in. **It is already on the product**, submitted in the same
change set that created it, which is why the Pricing configuration tab carries no warning badge
while Architecture details carries a red 1. This table is here so you can CHECK the tab against
it rather than retype it.

Read out of `aws_marketplace/bundle_b_create_entity.json`, which is what AWS accepted.

| Dimension key | Shown as | Type | Price |
|---|---|---|---|
| `attack_surface_bundle_access` | Attack Surface & Supply Chain - Monthly | Entitled, 1 month | **$100.00 / month** |
| `supply_chain_calls` | Supply Chain Exposure Check | Externally metered | $0.10 / call |
| `asset_intel_calls` | Asset Intelligence Sweep | Externally metered | $0.15 / call |
| `secret_scan_calls` | Public Artifact Secret Scan | Externally metered | $0.35 / call |
| `threat_actor_calls` | Threat Actor and Campaign Lookup | Externally metered | $0.30 / call |
| `session_risk_calls` | Session Hijack Risk | Externally metered | $0.30 / call |

Pricing model is Contract: a configurable upfront monthly term on the entitled dimension, plus a
usage-based rate card on the five metered ones.

**Those five prices are not typed into the listing by hand.** They are derived from
`BUNDLE_B_DIMENSION_NAMES` and `METERED_CREDIT_COSTS` in `relayshield_api.py`, and
`test_bundle_b_changeset.py` fails if the listing and the billing tables ever disagree. A listing
price above what we meter is a price we do not honour; one below it bills AWS buyers less than
everyone else, with nothing raising.

**STOP IF the Pricing configuration tab disagrees with this table in any row.** Send me the row.
Do not correct it in the portal: pricing lives on the entity and a portal edit and a change set
are two sources of truth for the same field.

---

## 4. Going public

Once Architecture details is filled, **Update visibility in the portal does the same thing as the
STEP 9 change set** (`aws_marketplace/bundle_b_go_public.json`, `UpdateVisibility` on
`prod-szi2wdww3obry`). Use whichever is in front of you; do not run both.

**Public visibility is the thing that is hard to reverse.** Everything up to here can be replaced
by another change set.

---

## 5. Getting the diagram onto your Mac

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/tender-planck-cb2qrx
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD
    file assets/marketplace/bundle_b_architecture.png
    open assets/marketplace

EXPECT: `PNG image data, 1600 x 900`, and Finder opens on the folder.
STOP IF: conflict markers. A conflict in CLAUDE.md alone is expected and the resolution is KEEP
BOTH SIDES: `git checkout --merge CLAUDE.md`, then delete the three marker lines by hand. A
conflict in a `.py`, a `.json` or a workflow is two sessions on the same code; send it.
STOP IF: `No such file or directory` on the `file` line. The merge did not complete, and
everything above it in the block will say why.
