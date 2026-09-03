#!/bin/sh
# Push iam_github_deploy_invoke.json to the deploy role, wherever that policy
# actually lives, and PROVE the grant afterwards.
#
#   sh tools/apply_deploy_invoke_policy.sh
#
# Run it from the repo root, on the Mac. It writes ONE IAM policy and otherwise
# only reads.
#
# WHY
# ---
# deploy_lambdas.yml invokes every function it deploys, to prove the handler
# imports. That probe runs as relayshield-github-deploy, whose invoke rights are
# an explicit ARN list. On 2026-09-03 relayshield-discord-bot was added to
# LAMBDA_MAP and not to the list: run 134 DEPLOYED THE CODE and then went red on
# AccessDeniedException, which looks like a failed deploy and is not one.
#
# python3 tools/check_deploy_invoke_policy.py keeps the repo half honest. This is
# the other half: the repo file means nothing until AWS has it.
#
# The policy was applied by hand on 2026-08-30 and nothing recorded WHERE, so
# this looks rather than assuming -- inline policies first, then attached
# managed policies, matching on the Sid.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
ROLE=relayshield-github-deploy
DOC=iam_github_deploy_invoke.json
SID=InvokeForImportProbe
FALLBACK_NAME=relayshield-deploy-invoke-probe

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

echo "== 2. Does the repo file agree with LAMBDA_MAP?"
python3 tools/check_deploy_invoke_policy.py
echo

echo "== 3. Where does the $SID policy live on $ROLE?"
INLINE=""
for NAME in $(aws iam list-role-policies --role-name "$ROLE" \
                --query 'PolicyNames[]' --output text | tr '\t' '\n'); do
  if aws iam get-role-policy --role-name "$ROLE" --policy-name "$NAME" \
       --query PolicyDocument --output json 2>/dev/null | grep -q "$SID"; then
    INLINE="$NAME"
    break
  fi
done

MANAGED=""
if [ -z "$INLINE" ]; then
  for ARN in $(aws iam list-attached-role-policies --role-name "$ROLE" \
                 --query 'AttachedPolicies[].PolicyArn' --output text | tr '\t' '\n'); do
    VER=$(aws iam get-policy --policy-arn "$ARN" \
            --query 'Policy.DefaultVersionId' --output text 2>/dev/null || echo "")
    [ -n "$VER" ] || continue
    if aws iam get-policy-version --policy-arn "$ARN" --version-id "$VER" \
         --query 'PolicyVersion.Document' --output json 2>/dev/null | grep -q "$SID"; then
      MANAGED="$ARN"
      break
    fi
  done
fi

if [ -n "$INLINE" ]; then
  echo "   inline policy '$INLINE'"
elif [ -n "$MANAGED" ]; then
  echo "   managed policy $MANAGED"
else
  echo "   nowhere -- no policy on this role carries $SID."
  echo "   Creating inline policy '$FALLBACK_NAME'."
fi
echo

echo "== 4. Apply $DOC"
if [ -n "$MANAGED" ]; then
  # A managed policy holds at most 5 versions. Rather than deleting one
  # unasked, fail with the list and let the operator choose.
  if ! aws iam create-policy-version --policy-arn "$MANAGED" \
         --policy-document "file://$DOC" --set-as-default \
         --query 'PolicyVersion.VersionId' --output text; then
    echo >&2
    echo "STOP: could not add a version. Existing versions:" >&2
    aws iam list-policy-versions --policy-arn "$MANAGED" \
      --query 'Versions[].[VersionId,IsDefaultVersion,CreateDate]' --output table >&2
    echo "A managed policy holds 5 versions. Delete an old non-default one with" >&2
    echo "  AWS_PROFILE=relayshield aws iam delete-policy-version --no-cli-pager \\" >&2
    echo "    --policy-arn $MANAGED --version-id vN" >&2
    echo "then re-run this script. Nothing was changed." >&2
    exit 1
  fi
else
  aws iam put-role-policy --role-name "$ROLE" \
    --policy-name "${INLINE:-$FALLBACK_NAME}" \
    --policy-document "file://$DOC"
  echo "   put-role-policy ${INLINE:-$FALLBACK_NAME} -- ok"
fi
echo

echo "== 5. Prove it, rather than assuming IAM propagated"
# simulate-principal-policy asks IAM the same question the probe asks, as the
# ROLE rather than as the operator running this script. Invoking the function
# from here would test the wrong identity entirely.
FAILED=0
for FUNC in $(python3 - <<'PY'
import json
d = json.load(open("iam_github_deploy_invoke.json"))
for s in d["Statement"]:
    if "lambda:InvokeFunction" in s["Action"]:
        for arn in s["Resource"]:
            print(arn.rsplit(":", 1)[-1])
PY
); do
  ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"
  DECISION=$(aws iam simulate-principal-policy \
               --policy-source-arn "arn:aws:iam::$ACCOUNT:role/$ROLE" \
               --action-names lambda:InvokeFunction \
               --resource-arns "$ARN" \
               --query 'EvaluationResults[0].EvalDecision' --output text)
  if [ "$DECISION" = "allowed" ]; then
    echo "   allowed  $FUNC"
  else
    echo "   $DECISION  $FUNC"
    FAILED=1
  fi
done
echo
if [ "$FAILED" -ne 0 ]; then
  echo "STOP: at least one function is still not invocable by $ROLE." >&2
  exit 1
fi
echo "Every mapped function is invocable by $ROLE. The next deploy of any of"
echo "them will get past the import probe."
