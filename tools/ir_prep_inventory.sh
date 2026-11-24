#!/bin/sh
# Read-only inventory that answers the factual questions in docs/security/tabletop_exercise_1.md BEFORE the exercise.
#
#   sh tools/ir_prep_inventory.sh
#
# It changes nothing. It prints IAM users with their keys (last four characters only) and what each can do,
# who has admin, the CloudTrail trail and where it stores logs, DynamoDB recovery state, log retention and the
# secret names. READ THE OUTPUT YOURSELF; do not commit it and do not paste it into a public place: it describes
# the account's real configuration. Gaps it shows are for you to fix, not to write into the repository.
#
# UNVERIFIED: not run against AWS from the container that wrote it. `sh -n` clean only. Every line uses a plain
# `aws ... --query` that other tools in this repo already use; a line that errors is printed, and the script goes on.

set -u

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }
try() { "$@" 2>&1 || echo "   (that call failed: $*)"; }

GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing read." >&2
  exit 1
fi
echo "account $GOT -- correct"
echo "who am I: $(aws sts get-caller-identity --query Arn --output text)"

echo
echo "== 1. IAM users: groups, policies, and keys (tabletop inject 2: which user, what can it do)"
for U in $(aws iam list-users --query 'Users[].UserName' --output text); do
  echo "user: $U"
  echo "   groups:            $(aws iam list-groups-for-user --user-name "$U" --query 'Groups[].GroupName' --output text)"
  echo "   attached policies: $(aws iam list-attached-user-policies --user-name "$U" --query 'AttachedPolicies[].PolicyName' --output text)"
  echo "   inline policies:   $(aws iam list-user-policies --user-name "$U" --query 'PolicyNames' --output text)"
  for K in $(aws iam list-access-keys --user-name "$U" --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
    INFO=$(aws iam list-access-keys --user-name "$U" --query "AccessKeyMetadata[?AccessKeyId=='$K'].[Status,CreateDate]" --output text)
    LAST=$(aws iam get-access-key-last-used --access-key-id "$K" --query 'AccessKeyLastUsed.[LastUsedDate,ServiceName]' --output text)
    echo "   key ending $(printf %s "$K" | tail -c 4):  $INFO   last used: $LAST"
  done
done

echo
echo "== 2. Groups and their policies (who has administrator access)"
for G in $(aws iam list-groups --query 'Groups[].GroupName' --output text); do
  echo "group: $G   policies: $(aws iam list-attached-group-policies --group-name "$G" --query 'AttachedPolicies[].PolicyName' --output text)"
done

echo
echo "== 3. CloudTrail (inject 3: where is the evidence, for how long)"
try aws cloudtrail describe-trails --query 'trailList[].[Name,S3BucketName,IsMultiRegionTrail,LogFileValidationEnabled]' --output text
for B in $(aws cloudtrail describe-trails --query 'trailList[].S3BucketName' --output text); do
  echo "-- lifecycle rules on $B (id, status, expires after days)"
  try aws s3api get-bucket-lifecycle-configuration --bucket "$B" --query 'Rules[].[ID,Status,Expiration.Days]' --output text
done

echo
echo "== 4. DynamoDB recovery state: tables, and how many have point-in-time recovery on"
N=0; ON=0
for T in $(aws dynamodb list-tables --query 'TableNames[]' --output text); do
  N=$((N + 1))
  S=$(aws dynamodb describe-continuous-backups --table-name "$T" --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus' --output text 2>/dev/null)
  [ "$S" = "ENABLED" ] && ON=$((ON + 1))
done
echo "   $N tables, $ON with point-in-time recovery enabled"

echo
echo "== 5. Log retention (inject 3 and 4: how far back can you look)"
try aws logs describe-log-groups --query '[length(logGroups),length(logGroups[?retentionInDays==null])]' --output text
echo "   (first number: log groups; second: groups with NO retention set, i.e. kept forever)"

echo
echo "== 6. Secret names (inject 3 and PB-1 step 6: what would you rotate)"
try aws secretsmanager list-secrets --query 'SecretList[].Name' --output text

echo
echo "== 7. Lambda functions and the ones the rollback workflow covers (inject 4)"
echo "   functions: $(aws lambda list-functions --query 'length(Functions)' --output text)"
echo "   rollback workflow covers: relayshield-api relayshield-bundle-fulfillment relayshield-stripe-webhook relayshield-mcp-http"

echo
echo "Done. Read it, then work through docs/security/tabletop_prep.md."
