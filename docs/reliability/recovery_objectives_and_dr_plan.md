# Recovery objectives and disaster recovery plan

**STATUS: DRAFT, written 2026-10-29 by Claude from the repo. NOT ADOPTED.** The objectives below are proposals. They become the
standing objectives when Andrew Gibbs (owner) reads them, edits what he disagrees with, and replaces this line with
"ADOPTED <date> by Andrew Gibbs". Until then they must not be ticked as defined in the Well-Architected Tool.

Covers WAFR Reliability: *Define recovery objectives for downtime and data loss*, *Use defined recovery strategies to meet the
recovery objectives*, *Test disaster recovery implementation*, *Manage configuration drift at the DR site*, *Automate recovery*.

## 1. Strategy: backup and restore, single Region (us-east-1), repository as the source for code

RelayShield is serverless: Lambda, API Gateway (REST, stage `prod`), DynamoDB on-demand, EventBridge schedules, S3, Secrets
Manager, KMS, with Cloudflare Workers for the public sites. There is no server to rebuild and no second Region. Recovery means
re-creating resources from the repository and restoring data from point-in-time recovery (PITR).

**Accepted risk, stated plainly:** loss of the whole us-east-1 Region is NOT covered by this plan. Recovery from that would be a
rebuild in another Region from the repository and from whatever backups exist, taking days. A second Region is not justified at
current revenue; revisit when it is. This is a decision for the owner, not a gap to hide.

## 2. Proposed objectives (PROPOSAL: edit freely)

| Component | What is lost if it fails | Proposed RTO | Proposed RPO | Recovery method |
|---|---|---|---|---|
| Lambda code (61 functions) | the service stops or misbehaves | 1 hour | 0 (code is in git) | `rollback_lambda.yml` for the four versioned functions; otherwise `deploy_lambdas.yml` run manually (deploys every mapped function from `main`) |
| API Gateway routes and stage | public API down | 4 hours | 0 if scripted | re-create from `tools/create_*.sh`. UNVERIFIED that every route is scripted; checking this is the first game-day task |
| DynamoDB customer-state tables (watchlist, verdict_watches, discord_installs) | customers lose paid state | 4 hours | 5 minutes (PITR) | restore to a new table from PITR, then repoint or copy back (section 4) |
| DynamoDB evidence tables (intel_first_seen, operator_identities, kit_fingerprints, marketplace_listings) | the lead-time evidence is lost | 24 hours | 5 minutes (PITR) | as above |
| DynamoDB caches and re-ingestable collections | slower service until refilled | best effort | not applicable | re-ingest; deliberately not backed up |
| Secrets (Secrets Manager) | integrations fail | 4 hours | not applicable | re-enter from the owner's password manager. UNVERIFIED: where the master copies live; owner to confirm |
| Cloudflare Workers (blog, Mini App, partners, privacy) | public sites down | 4 hours | 0 (code in git) | redeploy from `wrangler.*.toml` via the deploy workflows |
| DNS | everything unreachable | 4 hours | not applicable | Cloudflare zone; registrar access held by the owner |

PITR restores to any second in the last 35 days, with the latest restorable time usually about 5 minutes behind, which is where
the 5-minute RPO comes from. It only covers tables on which PITR is enabled: see section 3.

## 3. Preconditions, none of which is proven today

1. PITR and deletion protection enabled on the protected tables: `tools/protect_dynamodb_tables.sh --apply`. Run status UNKNOWN.
2. At least one restore performed and checked (game day, scenario 1). Until then the RPO above is a claim about AWS, not about us.
3. Lambda versions published, so rollback has something to restore (deploy role grant: `tools/apply_deploy_versions_policy.sh`).
4. A recurring AWS Backup plan is NOT in place. PITR covers 35 days only; anything needed longer needs a backup plan. Not built.

## 4. Runbook: restore a DynamoDB table (the one that has never been tried)

A restore always creates a NEW table; it never overwrites. The application reads tables by fixed name, so the choices are to
copy the needed items back into the original table, or to repoint the Lambda environment variable that names the table.
The first is safer for partial loss; the second for total loss. Decide per incident. The restore itself:

ANDREW RUNS THIS (during the game day, then during a real incident, with the real table name):

```zsh
AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text --no-cli-pager
AWS_PROFILE=relayshield aws dynamodb restore-table-to-point-in-time --no-cli-pager --source-table-name relayshield_verdict_watches --target-table-name relayshield_verdict_watches_restoretest --use-latest-restore-time
```
EXPECT: the first line prints 239677749008; the second prints a table description with `"TableStatus": "CREATING"`.
STOP IF: the account is not 239677749008 (nothing was changed), or `PointInTimeRecovery is not enabled` (section 3, item 1).
UNVERIFIED: not run from the container that wrote this.

## 5. Configuration drift

There is no DR site, so drift here means live differing from the repository. `lambda_drift_check.yml` compares deployed Lambda
code with `main` daily and opens a `lambda-drift` issue on a difference. It does not cover Cloudflare Workers, API Gateway
configuration, IAM or table settings. Those are the known gaps.

## 6. Review

After any declared incident and at least once a year. Last test: NONE. First test: game day 1, see `game_day_plan.md`.
