#!/bin/sh
# Pre-provision the incident responder role, so access exists BEFORE an incident (SEC 10 "Pre-provision access").
#
#   sh tools/apply_ir_responder_role.sh
#
# Creates ONE role, relayshield-ir-responder, READ-ONLY: the AWS-managed SecurityAudit and ViewOnlyAccess
# policies plus CloudWatch Logs read. It can look at everything and change nothing. It is assumable only by a
# principal in this account that signed in with MFA within the last hour (iam_ir_responder_trust.json).
# Containment itself (deny policies, concurrency 0, key disable) uses your normal admin access, by design.
#
# The role does not exist until this runs, and nothing else depends on it. If it already exists the script
# stops and says so, rather than rewriting a trust policy.
#
# UNVERIFIED: not run against AWS from the container that wrote it. `sh -n` clean only.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
ROLE=relayshield-ir-responder
TRUST=iam_ir_responder_trust.json

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

[ -f "$TRUST" ] || { echo "STOP: $TRUST not found. Run from the repo root." >&2; exit 1; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing changed." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 2. Does the role already exist?"
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  echo "STOP: $ROLE already exists. Nothing changed. Inspect it before editing:" >&2
  echo "      aws iam get-role --role-name $ROLE" >&2
  exit 1
fi
echo "   not found -- creating."
echo

echo "== 3. Create $ROLE with the MFA-only trust policy"
aws iam create-role --role-name "$ROLE" --assume-role-policy-document "file://$TRUST" \
  --max-session-duration 3600 --description "Read-only incident responder. MFA required. See docs/security/forensics_plan.md" \
  --query 'Role.Arn' --output text
for P in arn:aws:iam::aws:policy/SecurityAudit arn:aws:iam::aws:policy/job-function/ViewOnlyAccess \
         arn:aws:iam::aws:policy/CloudWatchLogsReadOnlyAccess; do
  aws iam attach-role-policy --role-name "$ROLE" --policy-arn "$P"
  echo "   attached $P"
done
echo

echo "== 4. Prove it: the role may read CloudTrail and may NOT change IAM"
FAILED=0
for ACTION in cloudtrail:LookupEvents iam:ListAccessKeys lambda:GetFunction logs:FilterLogEvents; do
  D=$(aws iam simulate-principal-policy --policy-source-arn "arn:aws:iam::$ACCOUNT:role/$ROLE" --action-names "$ACTION" \
        --query 'EvaluationResults[0].EvalDecision' --output text)
  if [ "$D" = "allowed" ]; then echo "   allowed   $ACTION"; else echo "   $D  $ACTION  (expected allowed)"; FAILED=1; fi
done
for ACTION in iam:CreateAccessKey iam:PutRolePolicy lambda:UpdateFunctionCode dynamodb:DeleteTable; do
  D=$(aws iam simulate-principal-policy --policy-source-arn "arn:aws:iam::$ACCOUNT:role/$ROLE" --action-names "$ACTION" \
        --query 'EvaluationResults[0].EvalDecision' --output text)
  if [ "$D" = "allowed" ]; then echo "   allowed   $ACTION  (expected DENIED)"; FAILED=1; else echo "   denied    $ACTION"; fi
done
echo
if [ "$FAILED" -ne 0 ]; then echo "STOP: the role does not behave as a read-only responder." >&2; exit 1; fi
echo "relayshield-ir-responder exists, can read, and cannot change anything."
