#!/bin/sh
# Give the deploy role READ-ONLY rights for the scheduled data-at-rest check, and PROVE the grant.
#
#   sh tools/apply_data_at_rest_read_policy.sh
#
# Run it from the repo root, on the Mac. It writes ONE inline IAM policy on relayshield-github-deploy and
# otherwise only reads. Every action in it is a Get, List or Describe: the scheduled check can see, not change.
# The WRITES (tools/wafr_data_at_rest.py --apply) run on the Mac under AWS_PROFILE=relayshield, never in Actions.
#
# Without this grant .github/workflows/data_at_rest_check.yml runs red with AccessDenied, which is the correct
# outcome: a check that cannot read must not report clean.
#
# UNVERIFIED: not run against AWS from the container that wrote it. `sh -n` clean only.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
ROLE=relayshield-github-deploy
DOC=iam_github_data_at_rest_read.json
POLICY_NAME=relayshield-data-at-rest-read

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

[ -f "$DOC" ] || { echo "STOP: $DOC not found. Run from the repo root." >&2; exit 1; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing changed." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 2. Apply $DOC as inline policy $POLICY_NAME"
aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY_NAME" --policy-document "file://$DOC"
echo "   put-role-policy $POLICY_NAME -- ok"
echo

echo "== 3. Prove it, as the ROLE, rather than assuming IAM propagated"
FAILED=0
for ACTION in s3:ListAllMyBuckets s3:GetEncryptionConfiguration s3:GetBucketPolicyStatus s3:GetAccountPublicAccessBlock \
              sqs:ListQueues sqs:GetQueueAttributes dynamodb:ListTables dynamodb:DescribeContinuousBackups; do
  DECISION=$(aws iam simulate-principal-policy --policy-source-arn "arn:aws:iam::$ACCOUNT:role/$ROLE" \
               --action-names "$ACTION" --resource-arns "*" --query 'EvaluationResults[0].EvalDecision' --output text)
  if [ "$DECISION" = "allowed" ]; then echo "   allowed  $ACTION"; else echo "   $DECISION  $ACTION"; FAILED=1; fi
done
echo
if [ "$FAILED" -ne 0 ]; then
  echo "STOP: at least one action is still not allowed for $ROLE." >&2
  exit 1
fi
echo "The deploy role can read the data-at-rest settings the scheduled check needs."
