# Well-Architected review, RELIABILITY pillar: answers for REL 1 to REL 13

Workload: RelayShield API, Production, us-east-1, account 239677749008, Framework lens.
Written 2026-10-11 from `tools/wafr_evidence.sh` output (read from the account, not recalled).

**How to use this.** For each question: tick the practices under TICK, leave the ones under
LEAVE UNTICKED, and paste the Notes text. Practice names are from the Framework lens as I know
it; match by meaning if the console wording differs. **Do not tick anything under LEAVE UNTICKED
to make a risk go away.** The FTR reviewer asks for evidence behind each tick and an overclaim
is what fails it. A flagged risk with a credible plan is acceptable; a ticked practice with no
evidence is not.

## The numbers every answer rests on

| Fact | Value | Source |
|---|---|---|
| Lambda functions | 61 (24 py3.12, 1 py3.13, 36 py3.14), all x86_64 | evidence script |
| **Account concurrent-execution limit** | **10** (unreserved 10); observed maximum **10** | evidence script |
| Throttles, 7 days | **427** | evidence script |
| Invocations / errors, 7 days | 70,202 / **11,227 (16%)**, NOT yet split by function | evidence script |
| Tracing / dead-letter queues on Lambdas | none / none | evidence script |
| Published versions / aliases on relayshield-api | 1 / 0 | evidence script |
| API Gateway | one REST API, stage `prod`; no tracing, no cache, no access logging, no stage method throttling; no CloudWatch role | evidence script |
| Usage plan `relayshield-growth` | 50 rps, burst 100, 50,000 requests per month | evidence script |
| DynamoDB | 57 tables, all on-demand; **PITR off on 19**; deletion protection off on 50 | evidence script |
| AWS Backup plans / on-demand backups | 0 / 0 | evidence script |
| CloudWatch alarms | 5, all Lambda error alarms; none in ALARM | evidence script |
| Log groups | 62; 54 at 90 days; **8 with no retention** | evidence script |
| EventBridge | 35 rules, mostly `rate()` schedules | evidence script |
| S3 | 5 buckets, all encrypted; versioning on 1; lifecycle on 1 | evidence script |
| Budgets / anomaly monitors | none / 1 | evidence script |
| GuardDuty / WAF | none / none; one AWS Config recorder | evidence script |

**The two findings an FTR reviewer will see first are the account concurrency limit of 10 and the
16% error rate.** Neither is hidden below. Both have a fix path in the improvement plan at the end,
and the first should be requested before validation is submitted.

---

## REL 1. How do you manage Service Quotas and constraints?

**TICK**
- Aware of service quotas and constraints. *We have read the Lambda account settings and know the
  limit.*

**LEAVE UNTICKED**
- Manage service quotas across accounts and Regions (single account, single Region)
- Accommodate fixed service quotas and constraints through architecture
- Monitor and manage quotas
- Automate quota management
- Ensure a sufficient gap exists between current quotas and maximum usage to accommodate failover

**Notes**
> The account's Lambda concurrent-execution limit is 10, and observed peak concurrency in the last
> 7 days reached 10, with 427 throttled invocations. This is a high risk. A quota increase request
> is being submitted, after which reserved concurrency will be set per function and a CloudWatch alarm
> added on throttles and on concurrency as a share of the limit. Other quotas are not yet monitored.

## REL 2. How do you plan your network topology?

**TICK**
- Use highly available network connectivity for your workload public endpoints. *The public API is
  an API Gateway regional endpoint, which is managed and multi-AZ.*

**LEAVE UNTICKED**
- Provision redundant connectivity between private networks in the cloud and on-premises environments
- Ensure IP subnet allocation accounts for expansion and availability
- Prefer hub-and-spoke topologies over many-to-many mesh
- Enforce non-overlapping private IP address ranges in multiple private address spaces

**Notes**
> Serverless architecture with no VPC: no Lambda function is VPC-attached, so private network
> topology practices do not apply. The public API is an API Gateway regional endpoint.

## REL 3. How do you design your workload service architecture?

**TICK**
- Choose how to segment your workload. *61 single-purpose Lambda functions.*
- Build services focused on specific business domains and functionality
- Provide service contracts per API. *OpenAPI document, x402 discovery manifest and MCP tool
  manifests are published and tested against the handlers.*

**Notes**
> Services are segmented per function (API, webhooks, monitors, billing, intelligence ingest).
> Contracts are published as an OpenAPI document and a machine-readable payment manifest.

## REL 4. How do you design interactions in a distributed system to prevent failures?

**TICK**
- Identify which kind of distributed system is required. *Soft real-time request path plus scheduled
  batch jobs.*
- Make all responses idempotent. *Payment fulfilment is idempotent on the provider's charge id,
  first-seen writes are conditional on non-existence, and backfills are conditional.* Tick this one
  only if you are comfortable that "all" is read as "the money-moving ones"; otherwise leave it and
  say so in the Notes.

**LEAVE UNTICKED**
- Implement loosely coupled dependencies (the Telegram signal path invokes another Lambda directly)
- Do constant work

**Notes**
> Webhook fulfilment and first-seen writes are idempotent. Some inter-function calls are direct
> synchronous invokes rather than queues. Decoupling those through a queue is on the improvement list.

## REL 5. How do you design interactions in a distributed system to mitigate or withstand failures?

**TICK**
- Implement graceful degradation. *Caches fail soft to the live call; screening fails open to an
  explicit unknown, never to clean.*
- Throttle requests. *Usage plan 50 rps / burst 100, per-key hourly caps on cost-bearing endpoints,
  per-IP daily quotas on keyless endpoints, a daily budget on the shared VirusTotal key.*
- Set client timeouts. *Explicit timeouts on every outbound call.*
- Make services stateless where possible. *Lambda functions hold no state; DynamoDB holds it.*
- Implement emergency levers. *Environment-based switches (for example the payment challenge flag).*

**LEAVE UNTICKED**
- Control and limit retry calls (not audited across the fleet)
- Fail fast and limit queues (no queues in use)

**Notes**
> Rate limits are layered at the gateway, per key and per source. Retry behaviour has not been
> audited across all 61 functions and is on the improvement list.

## REL 6. How do you monitor workload resources?

**TICK**
- Monitor all components for the workload (Generation). *All functions log to CloudWatch with 90-day
  retention on 54 of 62 groups.*

**LEAVE UNTICKED**
- Define and calculate metrics (Aggregation). *Only default service metrics.*
- Send notifications (Real-time processing and alarming). **Tick only if you confirm the 5 alarms
  publish to an SNS topic that reaches you.** I have not read their actions.
- Automate responses
- Analytics
- Conduct reviews regularly
- Monitor end-to-end tracing of requests through your system (tracing is off everywhere)

**Notes**
> Five CloudWatch alarms cover Lambda errors for the breach monitor, intel monitor, SIM swap monitor, Stripe webhook and WhatsApp webhook. There are no alarms
> on API 5XX, latency, throttles or DynamoDB errors, no X-Ray tracing, and API Gateway access logging
> is not configured because no CloudWatch role is set. Eight log groups have no retention period set.
> These are planned in this order: throttle and 5XX alarms, API access logging, retention on the
> remaining groups, then tracing.

## REL 7. How do you design your workload to adapt to changes in demand?

**TICK**
- Use automation when obtaining or scaling resources. *Lambda, API Gateway and on-demand DynamoDB
  scale without operator action.*
- Obtain resources upon detection of impairment to a workload. *Managed services replace
  unhealthy capacity.*

**LEAVE UNTICKED**
- Obtain resources upon detection that more resources are needed. **Scaling is capped by the
  account limit of 10 concurrent executions, so this does not hold today.**
- Load test your workload

**Notes**
> Scaling is automatic but is currently constrained by the Lambda concurrency limit (see REL 1).
> No load test has been performed. A quota increase and a baseline load test are planned together.

## REL 8. How do you implement change?

**TICK**
- Use runbooks for standard activities such as deployment. *Runbooks are committed in the repository.*
- Deploy changes with automation. *GitHub Actions deploys with change detection, OIDC credentials
  and a post-deploy import probe.*

**LEAVE UNTICKED**
- Integrate functional testing as part of your deployment. *The unit tests run locally; the deploy
  runs an import probe only.*
- Integrate resiliency testing as part of your deployment
- Deploy using immutable infrastructure. *One published version and no aliases on the main
  function, so there is no instant rollback.*

**Notes**
> Deployments are automated but the test suite is not yet run in CI and there are no versions or
> aliases to roll back to. Running the suite in the deploy workflow and publishing versions behind
> an alias are planned.

## REL 9. How do you back up data?

**TICK after running `tools/protect_dynamodb_tables.sh --apply` and re-reading it**
- Identify and back up all data that needs to be backed up, or reproduce the data from sources.
  *Customer state and irreplaceable evidence tables get PITR; caches and re-ingestable collections
  are deliberately excluded.*
- Secure and encrypt backups. *DynamoDB encrypts at rest, including backups.*
- Perform data backup automatically. *PITR is continuous.*

**LEAVE UNTICKED**
- Perform periodic recovery of the data to verify backup integrity and processes. *Not done. A single
  restore of one PITR-enabled table to a scratch table would let you tick this.*

**Notes**
> Before this review, 19 of 57 tables had no point-in-time recovery and there was no AWS Backup plan.
> Customer-state and evidence tables have been enabled; the remaining tables are caches or
> re-ingestable data. A restore test is planned. Deletion protection is being enabled on the same
> tables. Only one of five S3 buckets has versioning.

## REL 10. How do you use fault isolation to protect your workload?

**TICK**
- Deploy the workload to multiple locations. *All managed services span multiple Availability Zones
  in us-east-1.*

**LEAVE UNTICKED**
- Select the appropriate locations for your multi-location deployment (single Region)
- Automate recovery for components constrained to a single location
- Use bulkhead architectures to limit scope of impact. **There is no bulkhead: no function has
  reserved concurrency and the account limit is 10, so one noisy scheduled function can starve the
  public API.**

**Notes**
> Single Region, multi-AZ through managed services. Functions share one 10-execution pool, so there
> is no isolation between background jobs and the public API. Reserved concurrency cannot be set until
> the account limit is raised (AWS requires a minimum unreserved pool).

## REL 11. How do you design your workload to withstand component failures?

**TICK**
- Automate healing on all layers. *Managed services recover without intervention.*

**LEAVE UNTICKED**
- Monitor all components of the workload to detect failures (see REL 6)
- Fail over to healthy resources (no second Region)
- Send notifications when events impact availability. **Tick only if the alarms notify.**
- Architect your product to meet availability targets and SLAs. *No target is defined.*

**Notes**
> No availability target or SLA has been defined yet; defining one is planned before the AWS
> Marketplace listing is promoted.

## REL 12. How do you test reliability?

**TICK**
- Use playbooks to investigate failures. *Read-only diagnostic scripts are committed per failure
  class (drift, routes, spend, watchlist, Stars).*
- Perform post-incident analysis. *Each incident is written up with its cause and the guard added.*
- Test functional requirements. *Unit and contract tests exist and are run before changes; they are
  not yet in CI.*

**LEAVE UNTICKED**
- Test scaling and performance requirements
- Test resiliency using chaos engineering
- Conduct game days regularly

## REL 13. How do you plan for disaster recovery (DR)?

**LEAVE UNTICKED**
- Define recovery objectives for downtime and data loss
- Use defined recovery strategies to meet the recovery objectives. *Only backup and restore, and
  only after REL 9 is done.*
- Test disaster recovery implementation to validate the implementation
- Manage configuration drift at the DR site or Region. *There is no DR site. A daily drift check
  compares deployed Lambda code with the repository.*
- Automate recovery

**Notes**
> No recovery time or recovery point objective is defined and no DR test has been performed. The
> intended strategy is backup and restore from PITR in a single Region, with the repository as the
> source for all code. Recovery objectives and one restore test are planned.

---

## Improvement plan, in the order that raises the most

1. **Raise the Lambda concurrency quota, today.** Read the quota, then request it. Everything else
   in REL 1, 7 and 10 is blocked on it.
2. **Split the 16% error rate by function** (`tools/lambda_errors_by_function.sh`). If the public API
   is a large share, it is the first fix; if it is a dead scheduled job, it is quick.
3. **Turn on PITR and deletion protection** for the state tables (`tools/protect_dynamodb_tables.sh`).
4. **Alarms** on API 5XX, latency and Lambda throttles; confirm the five existing alarms notify.
5. **API Gateway access logging and a CloudWatch role.**
6. **Publish versions behind an alias** for the main function.
7. **Run the test suite in the deploy workflow.**
8. **A monthly budget and one restore test.**

Do the first three before requesting validation. The rest can be stated as planned.
