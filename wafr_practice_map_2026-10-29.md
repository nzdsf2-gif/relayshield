# WAFR High-risk practice map, 2026-10-29

Every unmet High-risk practice Andrew read from the console (OPS 11, REL 37; SEC 36 are in `LOG_CURRENT.md`), with what now
backs it. **Nothing here is ticked and nothing has been applied to AWS.** A practice may be ticked only when its status reads
EVIDENCE EXISTS and the evidence is cited in the Note. The Well-Architected Tool decides which practices clear a question; this
file cannot predict that, and ticking a practice that is not true is what fails an FTR review.

Status key: **UNRUN** built and tested, not run against AWS. **DRAFT** document written, not adopted or tested.
**ANDREW** needs a purchase, a click, or a fact only he holds. **NOT BUILT**. **N/A?** probably does not apply, owner decides
and states why in the Note.

## Operational Excellence (11 practices)

| Practice | Backing | Status |
|---|---|---|
| Implement distributed tracing | `tools/wafr_observability.py --step tracing` (X-Ray on 4 Lambdas and the API stage) | UNRUN |
| Create support plans for production workloads | a paid AWS Support plan; search summary says Business Support+ from $29 per month (UNVERIFIED) | ANDREW |
| Mechanisms exist to manage responsibilities and ownership | `docs/ops/operating_model.md` section 1 | DRAFT |
| Mechanisms exist to request additions, changes, and exceptions | operating model section 2 | DRAFT |
| Responsibilities between teams are predefined or negotiated | operating model section 1; one-person company | DRAFT, N/A? |
| Escalation is encouraged | operating model section 3 (CONFIRM items) | DRAFT, ANDREW |
| Communications are timely, clear, and actionable | operating model section 4 plus alarms (UNRUN) | DRAFT |
| Team members are encouraged to maintain and grow their skill sets | operating model section 5 (CONFIRM what is actually done) | ANDREW |
| Resource teams appropriately | operating model section 5 | DRAFT, ANDREW |
| Ensure personnel capability | operating model section 5 | DRAFT, ANDREW |
| Evaluate internal customer needs | operating model section 6 (CONFIRM cadence) | ANDREW |

## Reliability (37 practices)

| Practice | Backing | Status |
|---|---|---|
| Manage service quotas across accounts and Regions | single account, single Region | N/A? |
| Accommodate fixed service quotas and constraints through architecture | serverless design; API Gateway 29 s limit already noted in LOG | review Note |
| Monitor and manage quotas | `tools/wafr_observability.py --step quota` (account concurrency alarm from the real quota); quota already raised to 1,000 on 2026-10-12 | UNRUN |
| Automate quota management | Service Quotas automatic management not investigated | NOT BUILT |
| Sufficient gap between quotas and maximum usage for failover | no failover site | N/A? |
| Redundant private connectivity to on-premises | no VPC | N/A? (the question, not four practices: mark it not applicable in the Tool; it is already High with the Note written, so check how it was answered) |
| IP subnet allocation for expansion | no VPC | N/A? |
| Prefer hub-and-spoke over mesh | no VPC | N/A? |
| Non-overlapping private IP ranges | no VPC | N/A? |
| Implement loosely coupled dependencies | scheduled EventBridge jobs are decoupled; the request path is synchronous | NOT BUILT |
| Do constant work | scheduled polling is constant by design; not assessed | review Note |
| Control and limit retry calls | async retry limits (`MaximumRetryAttempts`, `MaximumEventAge`) not set | NOT BUILT |
| Fail fast and limit queues | DLQs, timeouts not configured | NOT BUILT |
| Define and calculate metrics (aggregation) | dashboard `relayshield-service-health`, error-rate metric math (`--step dashboard`) | UNRUN |
| Send notifications (real-time processing and alarming) | `tools/wafr_hardening.py --step alarm` plus quota alarm; path test in game day 4 | UNRUN |
| Automate responses (real-time processing and alarming) | nothing automated responds to an alarm | NOT BUILT |
| Analyze logs | five saved Logs Insights queries (`--step dashboard`) | UNRUN |
| Monitor end-to-end tracing of requests | `--step tracing` | UNRUN |
| Integrate functional testing as part of your deployment | `deploy_lambdas.yml` now needs `tests.yml`; first green run on GitHub still to be seen | UNRUN (merge first) |
| Integrate resiliency testing as part of your deployment | game day scenario 3 exercises the rollback; nothing automated in CI | DRAFT |
| Deploy using immutable infrastructure | versions published per deploy plus `rollback_lambda.yml`; API still invokes the unqualified function, so versions are not yet what serves traffic | UNRUN, PARTIAL |
| Use bulkhead architectures | `tools/wafr_hardening.py --step concurrency`; proof is game day scenario 2 | UNRUN |
| Automate recovery for components constrained to a single location | rollback workflow only; no automated recovery | NOT BUILT |
| Monitor all components of the workload | API and key functions covered; DynamoDB, EventBridge and the other 57 functions are not | PARTIAL |
| Fail over to healthy resources | single Region, accepted risk written in the DR plan | N/A? |
| Rely on the data plane, not the control plane, during recovery | PITR restore and redeploy are control-plane operations | NOT BUILT, say so in the Note |
| Use static stability to prevent bimodal behavior | serverless, multi-AZ managed services; not assessed | review Note |
| Send notifications when events impact availability | same alarms as above; needs game day 4 | UNRUN |
| Architect your product to meet availability targets and SLAs | `docs/reliability/availability_target_and_load_test_plan.md` section 1 | DRAFT |
| Test scalability and performance requirements | load test plan, section 2 | DRAFT, not run |
| Test resiliency using chaos engineering | game day scenario 2 | DRAFT, not held |
| Conduct game days regularly | `docs/reliability/game_day_plan.md` | DRAFT, none held |
| Define recovery objectives for downtime and data loss | `docs/reliability/recovery_objectives_and_dr_plan.md` section 2 | DRAFT |
| Use defined recovery strategies to meet the recovery objectives | DR plan section 1, needs PITR applied and one restore | DRAFT, ANDREW |
| Test disaster recovery implementation | game day scenario 1 (PITR restore) | DRAFT, not run |
| Manage configuration drift at the DR site or Region | Lambda drift check exists; Workers, API Gateway, IAM not covered | PARTIAL |
| Automate recovery (DR) | restore is manual | NOT BUILT |

## What would move the most, in order

1. Merge this branch, push `main`, see `tests.yml` and the deploy gate go green. Costs nothing.
2. Run, in order, with a dry run first each time: `tools/wafr_hardening.py` (three steps), then `tools/wafr_observability.py` (four
   steps), then `tools/apply_deploy_versions_policy.sh`. Then `tools/protect_dynamodb_tables.sh --apply`.
3. Hold game day 1 (PITR restore and bulkhead test): it turns four DRAFT rows into evidence.
4. Adopt or edit the four documents and answer their CONFIRM items.
5. Build what is left: async retry and DLQ settings, an AWS Backup plan, DynamoDB alarms, API integration through the alias.
6. Only then re-tick, citing each piece of evidence in the Note.
