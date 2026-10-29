#!/bin/sh
# Give the deploy role the rights to publish versions, move the 'live' alias and roll back, and PROVE the grant.
#
#   sh tools/apply_deploy_versions_policy.sh
#
# Run it from the repo root, on the Mac. It writes ONE inline IAM policy on relayshield-github-deploy and
# otherwise only reads. It does not touch the shared Lambda execution role, whose inline budget is full.
#
# WHY: deploy_lambdas.yml now publishes a version after each deploy and rollback_lambda.yml restores one. Both
# run as relayshield-github-deploy. Without this grant the deploys still succeed and the versioning step prints
# a warning saying so, so nothing breaks while this is outstanding, but the REL 8 practice is not met until it runs.
#
# UNVERIFIED: not run against AWS from the container that wrote it. `sh -n` clean only.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
ROLE=relayshield-github-deploy
DOC=iam_github_deploy_versions.json
POLICY_NAME=relayshield-deploy-versions

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

echo "== 2. Do the repo files agree with each other?"
python3 test_deploy_versions.py
echo

echo "== 3. Apply $DOC as inline policy $POLICY_NAME"
aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY_NAME" --policy-document "file://$DOC"
echo "   put-role-policy $POLICY_NAME -- ok"
echo

echo "== 4. Prove it, as the ROLE, rather than assuming IAM propagated"
FAILED=0
for FUNC in $(python3 - <<'PY'
import json
d = json.load(open("iam_github_deploy_versions.json"))
for arn in d["Statement"][0]["Resource"]:
    if not arn.endswith(":*"):
        print(arn.rsplit(":", 1)[-1])
PY
); do
  ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"
  for ACTION in lambda:PublishVersion lambda:UpdateAlias lambda:CreateAlias; do
    DECISION=$(aws iam simulate-principal-policy --policy-source-arn "arn:aws:iam::$ACCOUNT:role/$ROLE" \
                 --action-names "$ACTION" --resource-arns "$ARN" \
                 --query 'EvaluationResults[0].EvalDecision' --output text)
    if [ "$DECISION" = "allowed" ]; then echo "   allowed  $ACTION  $FUNC"; else echo "   $DECISION  $ACTION  $FUNC"; FAILED=1; fi
  done
done
echo
if [ "$FAILED" -ne 0 ]; then
  echo "STOP: at least one action is still not allowed for $ROLE." >&2
  exit 1
fi
echo "The deploy role can publish versions and move the live alias for every versioned function."
