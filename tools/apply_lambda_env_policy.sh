#!/bin/sh
# Grant relayshield-github-deploy the permission lambda_env_set.yml needs.
#
#   sh tools/apply_lambda_env_policy.sh
#
# Run it from the repo root, on the Mac.
#
# WHY IT EXISTS
# -------------
# 2026-09-19: the lambda_env_set workflow's PLAN job succeeded and its APPLY
# job failed:
#
#     AccessDeniedException ... assumed-role/relayshield-github-deploy/...
#     is not authorized to perform: lambda:UpdateFunctionConfiguration
#     because no identity-based policy allows the action
#
# GetFunctionConfiguration is granted and UpdateFunctionConfiguration is not,
# which is exactly why plan worked and apply did not. A plan mode that passes
# on a role that cannot write is the quiet half of this: it proves the tool,
# the inputs and the merge, and says nothing about whether the write can land.
#
# WHY THIS RUNS AS THE OPERATOR AND NOT IN ACTIONS
# ------------------------------------------------
# A role cannot widen its own permissions. relayshield-github-deploy has no
# iam:CreatePolicy or iam:AttachRolePolicy, so a workflow running AS that role
# cannot perform this grant. That is IAM working correctly, not a gap. The
# first grant is operator-side, once; after it the workflow needs nothing from
# a human but the dispatch.
#
# WHY THE RESOURCE LIST IS THREE FUNCTIONS AND NOT EVERY LAMBDA
# -------------------------------------------------------------
# UpdateFunctionConfiguration does far more than environment variables: it can
# change a function's handler, timeout, memory and EXECUTION ROLE. Granting it
# account-wide to a CI role to set one string is a much larger permission than
# the job needs. The three named are the ones that carry product codes. A
# workflow run against any other function fails with an AccessDenied that NAMES
# the function, which is a clear refusal rather than a silent one.
#
# NOTE: this is a customer-managed policy and the shared runtime role is at
# 11 attached of 10 allowed -- but this attaches to relayshield-github-deploy,
# a DIFFERENT role, which is nowhere near its cap. A claim about a permission
# names the role it was read from.

set -eu
export AWS_PAGER=""

ROLE="relayshield-github-deploy"
NAME="relayshield-lambda-env"
FILE="iam/relayshield-lambda-env.json"
ACCOUNT="239677749008"
ARN="arn:aws:iam::${ACCOUNT}:policy/${NAME}"

[ -f "$FILE" ] || { echo "run this from the repo root; $FILE not found" >&2; exit 1; }

echo "== identity =="
ACTUAL=$(AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text --no-cli-pager)
echo "account: $ACTUAL"
if [ "$ACTUAL" != "$ACCOUNT" ]; then
  echo "REFUSING: expected $ACCOUNT, got $ACTUAL." >&2
  echo "620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2
  exit 1
fi

echo
echo "== policy =="
if AWS_PROFILE=relayshield aws iam get-policy --policy-arn "$ARN" --no-cli-pager >/dev/null 2>&1; then
  echo "exists; adding a new default version"
  OLD=$(AWS_PROFILE=relayshield aws iam list-policy-versions --policy-arn "$ARN" \
        --query 'Versions[?IsDefaultVersion==`false`]|[-1].VersionId' \
        --output text --no-cli-pager 2>/dev/null || echo None)
  COUNT=$(AWS_PROFILE=relayshield aws iam list-policy-versions --policy-arn "$ARN" \
          --query 'length(Versions)' --output text --no-cli-pager)
  if [ "$COUNT" -ge 5 ] && [ "$OLD" != "None" ]; then
    echo "pruning version $OLD"
    AWS_PROFILE=relayshield aws iam delete-policy-version \
      --policy-arn "$ARN" --version-id "$OLD" --no-cli-pager
  fi
  AWS_PROFILE=relayshield aws iam create-policy-version \
    --policy-arn "$ARN" --policy-document "file://$FILE" \
    --set-as-default --no-cli-pager >/dev/null
else
  echo "creating"
  AWS_PROFILE=relayshield aws iam create-policy \
    --policy-name "$NAME" --policy-document "file://$FILE" --no-cli-pager >/dev/null
fi

echo
echo "== attach =="
AWS_PROFILE=relayshield aws iam attach-role-policy --role-name "$ROLE" --policy-arn "$ARN" --no-cli-pager

echo
echo "== PROVE IT, against the ROLE and against the RESOURCE the policy names =="
# Simulate against the role, never from the operator's own shell: the operator
# can do things the role cannot, so testing here would answer the wrong
# question. And pass --resource-arns, because this statement is scoped: the
# default of "*" would return implicitDeny for a correct grant, which reads as
# a failure and is the simulation being asked the wrong question.
AWS_PROFILE=relayshield aws iam simulate-principal-policy \
  --policy-source-arn "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
  --action-names lambda:GetFunctionConfiguration lambda:UpdateFunctionConfiguration \
  --resource-arns "arn:aws:lambda:us-east-1:${ACCOUNT}:function:relayshield-bundle-fulfillment" \
  --query 'EvaluationResults[].{action:EvalActionName,decision:EvalDecision}' \
  --output table --no-cli-pager

echo
echo "BOTH decisions above must read allowed."
echo "If UpdateFunctionConfiguration still reads implicitDeny here, WITH the"
echo "resource given, the grant genuinely did not take. Send that output."
