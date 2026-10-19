# AWS FTR: finish list, 2026-10-18

Solution `soln-aicwx4eiyofnm` ("RS Agentic Attack Surface API"), linked to product `prod-kkvurtspreofy`.
Workload "RelayShield API", Production, us-east-1, account 239677749008, Framework lens, 57 questions.

**What this file is.** The saved answer sheets (`wafr_answers_reliability_2026-10-11.md`,
`wafr_answers_perf_cost_sus_2026-10-12.md`) were written before several facts changed. This lists
only what has to change in the console, in order, and what Andrew has to read back. Nothing here was
checked against AWS from the container, which has no credentials; every AWS fact below comes from
Andrew's own output recorded in `docs/claude_memory/LOG_CURRENT.md` and its archive.

---

## 1. Read four things first, so the Notes below are true when pasted

The block is in the chat reply. A Note that states a fact the reviewer can check and that is not true
is what fails an FTR, so these come before any edit.

| Read | Must be | If it is not |
|---|---|---|
| Lambda account concurrent executions | `1000` | Do not paste the REL 1, REL 7, REL 10, PERF 2, PERF 5 or COST 9 updates below. Keep the old Notes and tell me what it printed. |
| Budget `relayshield-monthly-cost` limit | any amount | If missing, the COST 1 sentence about a budget must stay out. |
| EventBridge rule `relayshield-sim-swap-monitor-schedule` | `rate(12 hours)` | If not, the SUS 3 and COST 1 "twelve-hourly" sentences stay out. |
| SNS subscriptions whose endpoint contains `bundle-fulfillment` | a topic ARN and `lambda`, or nothing | Nothing is a valid answer and means the diagram correctly omits SNS. A row means add the box (section 6). |

(The SIM swap schedule is recorded as applied on 2026-10-12 and Andrew confirmed the twelve-hour
cadence is what resolved the Twilio spend. The read is to make the Note's source a fresh output rather
than a memory.)

## 2. Find the one unanswered question

Well-Architected Tool, workload "RelayShield API", **Overview**. Each pillar row shows answered
over total. The totals are OPS 11, SEC 11, REL 13, PERF 5, COST 11, SUS 6 = 57. **The pillar whose
answered count is one short holds it**; open that pillar and the unanswered question has no
selection. The container cannot see the console, so this one is Andrew's read.

* If it is in **REL, PERF, COST or SUS**, its answer is already written in the two sheets above.
* If it is in **OPS or SEC**, those answers were given in chat and were not saved. Send me the
  question's number and its text, and I will draft it from the repository and the evidence reads.

## 3. Notes that changed

Paste each over the existing Notes for that question. Each is under the console's 2,084-character
limit. Only after the first read prints `1000`.

**REL 1, Notes**

> The account's Lambda concurrent-execution limit was 10, and observed peak concurrency in a 7-day
> window reached 10, with 427 throttled invocations. AWS approved an increase to 1,000 on
> 2026-10-12. Reserved concurrency per function and a CloudWatch alarm on throttles and on
> concurrency as a share of the limit are the next steps and are not yet in place. Other quotas are
> not yet monitored.

**REL 7, Notes**

> Scaling is automatic. The Lambda concurrency limit that previously capped it (10) was raised to
> 1,000 on 2026-10-12. No load test has been performed; a baseline load test is planned.

*Tick change, mine to be overruled:* tick "Obtain resources upon detection that more resources are
needed" only if the first read printed `1000`. The reviewer will ask for evidence, and the evidence is the
Lambda throttles metric for the days since 2026-10-12 showing none.

**REL 8, Notes**

> Deployments are automated through GitHub Actions with change detection and OIDC credentials, and a
> post-deploy import probe that fails the run on any Lambda runtime initialisation error. In October
> the public API function had two initialisation outages caused by bad deployment packages: a syntax
> error on 5 October that the probe did not then recognise (the probe has since been corrected and a
> compile test for every source file added), and a package missing a module on 11 October, believed
> to be a manual deployment outside the pipeline. Manual deployments still bypass the pipeline and
> no alarm covered the API function. The test suite is not yet run in CI and there are no versions
> or aliases to roll back to. Alarming the API function, running the suite in CI and publishing
> versions behind an alias are planned.

**REL 10, Notes**

> Single Region, multi-AZ through managed services. No function has reserved concurrency, so a
> background job can still consume the shared pool that serves the public API. The account limit was
> raised to 1,000 on 2026-10-12, so reserved concurrency can now be set; setting it for the public API
> function is the next step. Leave the bulkhead practice unticked until it is done.

**PERF 2, Notes**

> 61 Lambda functions at 128 MB to 1,024 MB with timeouts from 3 to 900 seconds; all x86_64. Memory
> and timeouts were set when each function was created and have not been right-sized against
> measured duration. Graviton (arm64) has not been evaluated. The account concurrency quota, which
> was the binding constraint at 10, was raised to 1,000 on 2026-10-12. A right-sizing pass and an
> arm64 trial on the highest-volume functions are planned.

**PERF 5, Notes**

> Runtimes and dependencies are kept current. Performance KPIs, tracing, load testing and a
> performance-improvement process do not exist yet. The first findings from measurement were a high
> error rate on the public API, which proved to be two function-initialisation outages caused by bad
> deployment packages (see REL 8), and 427 throttles in seven days under the previous concurrency
> limit of 10, since raised to 1,000. A baseline load test is planned.

**COST 9, Notes**

> Demand is throttled in layers: API Gateway usage plan, per-key hourly and per-source daily caps,
> and a daily budget on the shared upstream key. Supply is dynamic and was capped by an account
> concurrency quota of 10, raised to 1,000 on 2026-10-12.

**SUS 3, Notes** (only if the third read printed `rate(12 hours)`)

> Background work is scheduled rather than polled, and caches avoid repeating expensive upstream calls.
> A review of scheduled-job frequency found one running twelve times more often than needed (hourly,
> against a twelve-hour cadence that sees the same events), now corrected. Low-use components have not
> been systematically reviewed and code has not been profiled.

**COST 1:** no text change. The budget sentence in the saved sheet is now true if the second read printed a
limit. Andrew's target was USD 10 and the last recorded limit was USD 50, so re-running
`create_cost_budget.sh` with its default lowers it; do that if the print shows 50.

## 4. The remaining High risks

Do not chase the count to zero. Unticked practices become flagged risks by design, and the saved
answers keep every unticked practice unticked on purpose, because an overclaim is what an FTR
reviewer catches. The test for each remaining High risk is that its Notes names a concrete plan, as
the sheets do. **UNVERIFIED:** whether unresolved High risks block approval. The FTR Guide in
Partner Central is the authority; I could not read it from the container. If it names a checklist
item you cannot answer, send me the item.

## 5. Save the report, then request validation

1. **Save milestone**, then **Generate report**. The PDF must be under 3 MB.
2. **Partner Central, solution `soln-aicwx4eiyofnm`, Validation tab, Request validation.** Reported
   prerequisites, from secondary sources and not yet confirmed against AWS's page: the solution links
   exactly one software product (it does), and a WAFR report as the evidence upload.
3. **Do not click "Update visibility" on the older four-product solution.**

## 6. The architecture diagram for this product

`assets/marketplace/consumption_security_architecture.png` (1600 x 900), generated from the
`.html` beside it, so a correction is an edit and a re-render. It reaches the Mac through the merge,
not through chat, which re-encodes images to `.webp` and an upload dialog then cannot select them.

It includes Amazon SNS: Andrew's read on 2026-10-18 showed this product's subscription and entitlement topics both invoke the fulfillment function. It names the product by its listing name, shows the Hugging Face MCP endpoint and Cloudflare as
**outside AWS** rather than hiding them, and **deliberately omits** two things:
* **Any claim about per-function IAM roles, key types or log redaction.** Dozens of Lambdas still
  share one role, and some handlers log values readably.
* **Vendor names, the account number and corpus counts.**

**The earlier Bundle B description and diagram footer made those claims and have been corrected.**
Nothing had been submitted with them: the Bundle B form was a single radio button.

**Still unread and it matters:** this product's own *Architecture details* tab in the Marketplace
Management Portal. For Bundle B the honest answer was "None of the above", which the form says is
"not considered deployed on AWS", because endpoints depend on third-party data providers. If this
product's tab says the same and the FTR needs an "AWS-hosted" product, that is the one thing that
could stop validation, and it is better found now than after the request. Read it and tell me what
it says; **do not change it in the same sitting.**

## 7. The question to AWS goes through support, not through Dave. SEND THIS NOW.

**Andrew's rule, 2026-10-19: Dave Shapiro is not the right person for this (not his business line), and he is
messaged only when there is a result to share.** The question goes to AWS's own support route. Two routes,
in this order:

1. **The "Contact us for details" link beside "No, this product is not fully deployed on AWS"** on the
   product's Architecture details tab. It is attached to exactly the assessment that fails, so it reaches the
   team that owns it. UNVERIFIED where it leads (the page is not reachable from the container).
2. **A Partner Central support case**, if the link only offers a form without a free-text box or if nobody
   answers in a few business days. Look for the FTR or AWS Marketplace category; the Validation tab may
   also carry its own link.

Paste this as the case text (no names, so it can be routed to whoever owns it):

> Our Partner Central solution soln-aicwx4eiyofnm (linked to Marketplace SaaS product prod-kkvurtspreofy)
> cannot request Foundational Technical Review validation because the prerequisite "AWS Marketplace
> product is deployed on AWS" is Incomplete. Our listing's hosting pattern is "None of the above", and the
> Architecture details tab reads "not fully deployed on AWS". Our API, data and billing run on AWS in one
> account. Three of the product's five usage endpoints pass the customer's input (a domain, an email or a
> technology name) to third-party data services outside AWS; the other two make no external calls.
>
> Please tell us: (1) which of those dependencies count under the hosting-pattern rules, in particular
> lookups of public registry or public-data sources; (2) whether any hosting pattern fits a product whose
> third-party data is replicated into AWS ahead of time; (3) whether the FTR can be scoped to the
> AWS-hosted workload, with the external services declared; and (4) separately, what we need to do to clear
> the Partner Revenue Measurement prerequisite for a SaaS product.

**Dave Shapiro, later and only with a result:** when the FTR is requested or approved, a two-line note is
enough. The co-sell and PDM question can go in that note. Nothing is sent to him before then.

---

## 8. What to send back

1. The output of the four reads in section 1.
2. The pillar and number of the unanswered question (and the question text if it is OPS or SEC).
3. What this product's Architecture details tab currently says.
4. Any FTR checklist item you cannot answer.

## 9. What the Architecture details tab said (read 2026-10-18)

Hosting pattern **"None of the above"**, and AWS's assessment reads **"No, this product is not fully
deployed on AWS. Contact us for details."** The product page's own banner says a product can be
published with any architecture and that matching a hosting pattern only earns a "deployed on AWS"
designation in search results.

**What AWS's SaaS guidelines say about that designation** (read through search results quoting
https://docs.aws.amazon.com/marketplace/latest/userguide/saas-guidelines.html, which is egress-blocked
here, so secondary): the application and control planes must run entirely on AWS, and third-party services
that transmit, store or process application data must also run on AWS, with carve-outs for CDNs, DNS and
corporate identity providers. Our endpoints query third-party data providers, so "None of the above" is the
accurate answer and stays. **Do not change it to get the badge.**

**Not established: whether the FTR requires the designation.** No result stated an FTR eligibility rule.
The FTR is described as a review of the AWS-hosted workload against best practices; the WAFR and the
diagram both describe exactly that workload and show what is outside AWS. My recommendation, mine to be
overruled: proceed with the validation request, and put the eligibility question to AWS in the Dave
email (draft above) rather than guessing. A failed review is reported as resubmittable.

## 10. CORRECTION, 2026-10-19: "deployed on AWS" IS A HARD FTR PREREQUISITE. SECTION 9'S RECOMMENDATION WAS WRONG.

Partner Central's Validation tab lists five prerequisites, run in sequence. Three are Complete (exactly one
Marketplace product, no non-Marketplace products, a software product). **Two are Incomplete: "AWS
Marketplace product is deployed on AWS" and "Partner Revenue Measurement (PRM) enabled".** Section 9 said the
designation probably did not matter for the FTR and recommended proceeding. It does matter: the prerequisite
reads the Architecture details assessment. Nothing can be submitted until both pass.

**Why this product fails it, from the code (static audit, one level of calls, so a dynamically built URL
could be missed).** Of the five usage endpoints:
* No outbound calls found: `llm-credential-exposure`, `prompt-injection-breach`.
* Customer input goes to a third party: `tech-stack-cve` (GitHub search), `mcp-registry-risk` (an RDAP domain
  lookup), `bulk-identity-risk` (breach and infostealer data providers).

AWS's guidelines, as summarised by secondary sources (docs.aws.amazon.com is unreachable from here), require
third-party services that process application data to run on AWS as well, with carve-outs for CDNs, DNS and
corporate identity providers. So "None of the above" is the true answer today and must not be changed to
clear the check.

**PRM, separately.** Reported as clearing when the product appears as onboarded in the Attributed revenue
dashboard, with up to seven days of lag after enabling, and for SaaS through resource tagging or a
user-agent string rather than Marketplace Metering. Secondary again: the PRM onboarding guide is the
authority. It is independent of the hosting question, so **start it now: the lag is the longest item.**

**Options, with my lean, mine to be overruled:**
1. **Ask AWS first (cheap, today):** the email above, and the "Contact us for details" link on the Architecture
   tab. It settles which dependencies count before anything is rebuilt.
2. **Read the rubric (Andrew, 10 minutes):** the "Architecture guidelines" link on that tab, and the exact text of
   the four hosting-pattern options under Request changes, then Update architecture details (open it, do not
   submit). One option may describe replicating third-party data into AWS.
3. **Only then decide the product change:** make the three endpoints AWS-only where the data is public (a
   pre-fetched copy of registry data in DynamoDB), narrow this product to the two clean endpoints, or run the
   FTR on a new narrower product. Each is a real build or a change set against a live listing, so none starts
   before steps 1 and 2 answer.

The WAFR, the milestone and the diagram are not wasted: every route needs them.
