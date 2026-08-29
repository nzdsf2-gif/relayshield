#!/bin/sh
# A6 first-seen: create the table in the RIGHT account and grant the intel
# monitor permission to write to it. Idempotent -- safe to re-run.
#
#   sh tools/setup_first_seen.sh
#
# WHY THIS IS A SCRIPT AND NOT A PASTED BLOCK
# -------------------------------------------
# On 2026-08-29 `aws dynamodb create-table --table-name relayshield_intel_first_seen`
# was run without AWS_PROFILE=relayshield. It PRINTED A SUCCESS BLOCK and created
# the table in 620534471984, the pre-audit account, where relayshield-intel-monitor
# does not exist. A read against the wrong account is a confusing error; a WRITE
# against the wrong account is a resource that exists, looks right in the output,
# and is invisible to everything that needs it.
#
# So this asserts the account before it does anything, and every command inside
# carries the profile explicitly rather than relying on one being exported.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_intel_first_seen
FUNC=relayshield-intel-monitor
POLICY=relayshield-first-seen-write

# AWS CLI v2 pipes output through a pager when stdout is a terminal, exactly
# like git. In a multi-step script that means execution stops at the first
# command with more than a screenful of output and the rest never runs. Empty
# AWS_PAGER turns it off.
export AWS_PAGER=""

aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT." >&2
  echo "Nothing has been created. Fix the profile in ~/.aws/config first." >&2
  exit 1
fi
echo "   $GOT  (correct)"

echo
echo "== 2. Table $TABLE"
if aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "   already exists in $ACCOUNT -- leaving it alone"
else
  echo "   not present in $ACCOUNT -- creating"
  # Hash key only. _record_first_seen() writes one row per distinct indicator
  # with ConditionExpression="attribute_not_exists(ioc_value)", so the first
  # write wins and every later sighting is a no-op. No range key: a second key
  # would let the same indicator be recorded "first seen" more than once, which
  # is the one thing this table exists to prevent.
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=ioc_value,AttributeType=S \
    --key-schema AttributeName=ioc_value,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  echo "   waiting for it to become ACTIVE"
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. Which role does $FUNC run as?"
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" --query Role --output text)
ROLE=${ROLE_ARN##*/}
echo "   $ROLE"

echo
echo "== 4. Grant PutItem on $TABLE to $ROLE"
DOC="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"}]}"

# This role already carries 20-odd inline policies. IAM caps the AGGREGATE size
# of a role's inline policies at 10,240 characters, and that cap is the reason
# an ordinary put-role-policy fails here with LimitExceeded. Adding a 20-somethingth
# inline policy is the wrong shape anyway.
#
# A customer-managed policy does not count against that budget at all: a role
# may attach 10 of them, each up to 6,144 characters, tracked separately. So try
# inline first, because it keeps the grant visible right on the role, and fall
# back to managed when the budget is spent -- which is the expected path here.
INLINE_COUNT=$(aws iam list-role-policies --role-name "$ROLE" --query 'length(PolicyNames)' --output text)
echo "   role currently has $INLINE_COUNT inline policies (IAM caps their total size at 10,240 chars)"

if aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY" --policy-document "$DOC" 2>/tmp/rs_iam_err; then
  GRANT="inline policy $POLICY"
  echo "   attached as an inline policy"
else
  echo "   inline failed:"
  sed 's/^/     /' /tmp/rs_iam_err
  echo "   falling back to a customer-managed policy, which has its own budget"

  ARN="arn:aws:iam::${ACCOUNT}:policy/${POLICY}"
  if aws iam get-policy --policy-arn "$ARN" >/dev/null 2>&1; then
    echo "   managed policy already exists -- adding a new default version"
    # Five versions is the hard limit, so drop the oldest non-default before
    # adding one. Re-running this script must not eventually start failing.
    OLD=$(aws iam list-policy-versions --policy-arn "$ARN" \
            --query 'sort_by(Versions[?IsDefaultVersion==`false`], &CreateDate)[0].VersionId' \
            --output text)
    if [ -n "$OLD" ] && [ "$OLD" != "None" ]; then
      COUNT=$(aws iam list-policy-versions --policy-arn "$ARN" --query 'length(Versions)' --output text)
      [ "$COUNT" -ge 5 ] && aws iam delete-policy-version --policy-arn "$ARN" --version-id "$OLD" && echo "   pruned version $OLD"
    fi
    aws iam create-policy-version --policy-arn "$ARN" --policy-document "$DOC" --set-as-default \
      --query 'PolicyVersion.VersionId' --output text
  else
    aws iam create-policy --policy-name "$POLICY" --policy-document "$DOC" \
      --query 'Policy.Arn' --output text
  fi

  aws iam attach-role-policy --role-name "$ROLE" --policy-arn "$ARN"
  GRANT="managed policy $ARN"
  echo "   attached $ARN to $ROLE"
fi
rm -f /tmp/rs_iam_err

echo
echo "== 5. Verify"
echo -n "   table status : "
aws dynamodb describe-table --table-name "$TABLE" --query 'Table.TableStatus' --output text
echo -n "   item count   : "
aws dynamodb describe-table --table-name "$TABLE" --query 'Table.ItemCount' --output text
echo "   grant        : $GRANT"
echo -n "   resource     : "
case "$GRANT" in
  inline*)  aws iam get-role-policy --role-name "$ROLE" --policy-name "$POLICY" \
              --query 'PolicyDocument.Statement[0].Resource' --output text ;;
  *)        aws iam get-policy-version \
              --policy-arn "arn:aws:iam::${ACCOUNT}:policy/${POLICY}" \
              --version-id "$(aws iam get-policy --policy-arn "arn:aws:iam::${ACCOUNT}:policy/${POLICY}" --query 'Policy.DefaultVersionId' --output text)" \
              --query 'PolicyVersion.Document.Statement[0].Resource' --output text ;;
esac

echo
echo "Done. Next, backfill from the existing corpus -- dry run first:"
echo "  AWS_PROFILE=$PROFILE ~/.rsvenv/bin/python tools/backfill_first_seen.py"
echo "  AWS_PROFILE=$PROFILE ~/.rsvenv/bin/python tools/backfill_first_seen.py --apply"
echo
echo "There is an empty $TABLE in 620534471984 from the 2026-08-29 mistake."
echo "It costs nothing on PAY_PER_REQUEST with no items. Deleting it is your"
echo "call -- this script will not aim a delete-table at that account."
