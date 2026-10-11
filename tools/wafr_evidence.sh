#!/bin/sh
# READ-ONLY. Gathers the facts the remaining Well-Architected questions
# (Reliability, Performance Efficiency, Cost Optimization, Sustainability) ask for,
# so each answer is ticked from evidence and never from memory.
#
#   AWS_PROFILE=relayshield sh tools/wafr_evidence.sh 2>&1 | tee /tmp/wafr_evidence.txt
#
# Nothing here writes, creates or changes anything. It never prints Lambda
# environment variables (they carry secrets) or secret values: it selects named
# fields only. A section that cannot be read prints "(not readable: ...)" and the
# script carries on, because "this identity cannot see it" is itself a finding and
# must not be mistaken for "it is not there".
#
# EVERY NUMBER BELOW IS AN ANSWER-INPUT. Paste the whole output back; do not
# summarise it, and do not edit it.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }
try() { "$@" 2>&1 || echo "   (not readable: the call above failed or was denied)"; }
hdr() { printf '\n== %s\n' "$1"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
echo "account $GOT (correct), region $REGION"

NOW=$(python3 -c 'import datetime as d;print(d.datetime.now(d.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')
W7=$(python3 -c 'import datetime as d;print((d.datetime.now(d.timezone.utc)-d.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
W30=$(python3 -c 'import datetime as d;print((d.datetime.now(d.timezone.utc)-d.timedelta(days=30)).strftime("%Y-%m-%d"))')
TODAY=$(python3 -c 'import datetime as d;print(d.datetime.now(d.timezone.utc).strftime("%Y-%m-%d"))')

hdr "REL 1 / PERF: Lambda account limits and fleet shape"
try aws lambda get-account-settings --query '{ConcurrentExecutionsLimit:AccountLimit.ConcurrentExecutions,UnreservedConcurrency:AccountLimit.UnreservedConcurrentExecutions,FunctionCount:AccountUsage.FunctionCount}' --output table
echo "-- functions by runtime / architecture"
try aws lambda list-functions --query 'Functions[].[Runtime,Architectures[0]]' --output text | sort | uniq -c
echo "-- memory and timeout (distinct combinations)"
try aws lambda list-functions --query 'Functions[].[MemorySize,Timeout]' --output text | sort -n | uniq -c
echo "-- functions with tracing ACTIVE / dead-letter config set (counts)"
try aws lambda list-functions --query 'length(Functions[?TracingConfig.Mode==`Active`])'
try aws lambda list-functions --query 'length(Functions[?DeadLetterConfig!=null])'

hdr "REL 7 / PERF: last 7 days account-wide Lambda demand"
for M in Invocations Errors Throttles; do
  printf '%-12s sum=' "$M"
  try aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name "$M" --start-time "$W7" --end-time "$NOW" --period 604800 --statistics Sum --query 'Datapoints[0].Sum' --output text
done
printf 'ConcurrentExecutions max='
try aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name ConcurrentExecutions --start-time "$W7" --end-time "$NOW" --period 604800 --statistics Maximum --query 'Datapoints[0].Maximum' --output text

hdr "REL 8: change management. Versions and aliases on relayshield-api"
printf 'published versions: '
try aws lambda list-versions-by-function --function-name relayshield-api --query 'length(Versions)'
printf 'aliases: '
try aws lambda list-aliases --function-name relayshield-api --query 'length(Aliases)'

hdr "REL 1 / REL 5: API Gateway"
try aws apigateway get-rest-apis --query 'items[].[id,name]' --output text
API_ID=$(aws apigateway get-rest-apis --query 'items[?contains(name,`elay`)].id | [0]' --output text 2>/dev/null)
echo "using API id: ${API_ID:-none found}"
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
  echo "-- stages: name, tracing, cache cluster, access logging configured?"
  try aws apigateway get-stages --rest-api-id "$API_ID" --query 'item[].[stageName,tracingEnabled,cacheClusterEnabled,accessLogSettings.destinationArn!=null]' --output text
  echo "-- stage method settings (throttling / logging / metrics)"
  try aws apigateway get-stages --rest-api-id "$API_ID" --query 'item[].methodSettings' --output json
fi
echo "-- usage plans (throttle and quota)"
try aws apigateway get-usage-plans --query 'items[].[name,throttle.rateLimit,throttle.burstLimit,quota.limit,quota.period]' --output text
echo "-- account-level API Gateway throttle and CloudWatch role"
try aws apigateway get-account --query '{rate:throttleSettings.rateLimit,burst:throttleSettings.burstLimit,cwRole:cloudwatchRoleArn!=null}' --output table

hdr "REL 9 / REL 13: DynamoDB backups (tables with a problem only)"
TABLES=$(aws dynamodb list-tables --query 'TableNames[]' --output text 2>/dev/null)
echo "table count: $(echo $TABLES | wc -w | tr -d ' ')"
NOPITR=0; NODEL=0; PROV=0
for T in $TABLES; do
  P=$(aws dynamodb describe-continuous-backups --table-name "$T" --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus' --output text 2>/dev/null)
  D=$(aws dynamodb describe-table --table-name "$T" --query '[Table.DeletionProtectionEnabled,Table.BillingModeSummary.BillingMode]' --output text 2>/dev/null)
  [ "$P" = "ENABLED" ] || { NOPITR=$((NOPITR+1)); echo "   PITR not enabled: $T ($P)"; }
  case "$D" in *True*) : ;; *) NODEL=$((NODEL+1));; esac
  case "$D" in *PAY_PER_REQUEST*) : ;; *) PROV=$((PROV+1)); echo "   not on-demand: $T ($D)";; esac
done
echo "PITR not enabled on $NOPITR table(s); deletion protection off on $NODEL; not on-demand on $PROV"
echo "-- AWS Backup plans / on-demand DynamoDB backups"
try aws backup list-backup-plans --query 'length(BackupPlansList)'
try aws dynamodb list-backups --query 'length(BackupSummaries)'

hdr "REL 6: alarms and log retention"
printf 'alarms defined: '
try aws cloudwatch describe-alarms --query 'length(MetricAlarms)'
printf 'alarms in ALARM now: '
try aws cloudwatch describe-alarms --state-value ALARM --query 'length(MetricAlarms)'
echo "-- alarm names (first 40)"
try aws cloudwatch describe-alarms --query 'MetricAlarms[].AlarmName' --output text | tr '\t' '\n' | head -40
printf 'log groups total / with NO retention set: '
try aws logs describe-log-groups --query '[length(logGroups),length(logGroups[?retentionInDays==null])]' --output text
echo "-- retention values in use"
try aws logs describe-log-groups --query 'logGroups[].retentionInDays' --output text | tr '\t' '\n' | sort | uniq -c

hdr "REL 4 / COST / SUS: scheduled work (EventBridge rules)"
printf 'rules: '
try aws events list-rules --query 'length(Rules)'
try aws events list-rules --query 'Rules[?ScheduleExpression!=null].[ScheduleExpression,State]' --output text | sort | uniq -c | sort -rn | head -15

hdr "REL 9 / SEC: S3"
for B in $(aws s3api list-buckets --query 'Buckets[].Name' --output text 2>/dev/null); do
  V=$(aws s3api get-bucket-versioning --bucket "$B" --query 'Status' --output text 2>/dev/null)
  E=$(aws s3api get-bucket-encryption --bucket "$B" --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text 2>/dev/null)
  L=$(aws s3api get-bucket-lifecycle-configuration --bucket "$B" --query 'length(Rules)' --output text 2>/dev/null)
  echo "   $B  versioning=${V:-none} encryption=${E:-none} lifecycleRules=${L:-none}"
done

hdr "COST 1-: spend, budgets, anomaly detection"
echo "-- last 30 days by service, top 12 (UnblendedCost, USD)"
try aws ce get-cost-and-usage --time-period Start="$W30",End="$TODAY" --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE --query 'ResultsByTime[].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]' --output text | sort -k2 -rn | head -12
echo "-- budgets"
try aws budgets describe-budgets --account-id "$ACCOUNT" --query 'Budgets[].[BudgetName,BudgetLimit.Amount,BudgetLimit.Unit,TimeUnit]' --output text
echo "-- cost anomaly monitors"
try aws ce get-anomaly-monitors --query 'length(AnomalyMonitors)'
echo "-- cost allocation tags in use (resource tag keys)"
try aws resourcegroupstaggingapi get-tag-keys --query 'TagKeys' --output text

hdr "SEC (already answered) re-read: detection services"
printf 'GuardDuty detectors: '; try aws guardduty list-detectors --query 'length(DetectorIds)'
printf 'Config recorders: ';    try aws configservice describe-configuration-recorders --query 'length(ConfigurationRecorders)'
printf 'Regional WAF web ACLs: '; try aws wafv2 list-web-acls --scope REGIONAL --query 'length(WebACLs)'

echo
echo "== done. Paste everything above, unedited."
