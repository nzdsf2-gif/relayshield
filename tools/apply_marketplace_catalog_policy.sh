#!/bin/sh
# Grant relayshield-github-deploy the Marketplace Catalog and log-read permissions
# that tools/marketplace_add_dimension.py and tools/agent_bait_fp_rate.py need.
#
#   sh tools/apply_marketplace_catalog_policy.sh
#
# Run it from the repo root, on the Mac. It creates or updates ONE
# customer-managed policy and attaches it. Everything else is a read.
#
# WHY A CUSTOMER-MANAGED POLICY AND NOT AN INLINE ONE
# ---------------------------------------------------
# CLAUDE.md's IAM section: the shared role's inline budget is spent at
# 10,127/10,240 bytes, and a role may attach only 10 managed policies. An inline
# policy is not available; a managed one is, and it is also versioned and
# detachable, which an inline policy is not.
#
# WHY THIS RUNS AS THE OPERATOR AND NOT IN ACTIONS
# ------------------------------------------------
# A role cannot widen its own permissions. relayshield-github-deploy has no
# iam:CreatePolicy or iam:AttachRolePolicy, so a workflow running AS that role
# cannot perform this grant -- that is IAM working correctly, not a gap. So the
# FIRST grant is operator-side, once. After it, marketplace_dimension.yml runs
# under the role and needs nothing further from a human except the workflow
# dispatch.
#
# Everything downstream of this is automated. This one command is the bootstrap.

set -eu
export AWS_PAGER=""

ROLE="relayshield-github-deploy"
NAME="relayshield-marketplace-catalog"
FILE="iam/relayshield-marketplace-catalog.json"
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
  # IAM allows 5 versions per policy. Prune the oldest non-default first so a
  # re-run never fails with LimitExceeded after four edits.
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
AWS_PROFILE=relayshield aws iam list-attached-role-policies --role-name "$ROLE" \
  --query "AttachedPolicies[?PolicyName=='${NAME}']" --output table --no-cli-pager

echo
echo "== PROVE IT, against the ROLE =="
# Simulate against the role, never from the operator's own shell: the operator
# can do things the role cannot, so testing here would answer the wrong question.
AWS_PROFILE=relayshield aws iam simulate-principal-policy \
  --policy-source-arn "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
  --action-names aws-marketplace:DescribeEntity aws-marketplace:StartChangeSet logs:FilterLogEvents \
  --query 'EvaluationResults[].{action:EvalActionName,decision:EvalDecision}' \
  --output table --no-cli-pager

echo
echo "Every decision above must read allowed."
echo "Then, in the Actions UI, run 'Marketplace Dimension' with mode=describe."
