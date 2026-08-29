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

aws() { command aws --profile "$PROFILE" --region "$REGION" "$@"; }

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
aws iam put-role-policy \
  --role-name "$ROLE" \
  --policy-name "$POLICY" \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"}]}"
echo "   inline policy $POLICY attached"

echo
echo "== 5. Verify"
echo -n "   table status : "
aws dynamodb describe-table --table-name "$TABLE" --query 'Table.TableStatus' --output text
echo -n "   item count   : "
aws dynamodb describe-table --table-name "$TABLE" --query 'Table.ItemCount' --output text
echo -n "   policy       : "
aws iam get-role-policy --role-name "$ROLE" --policy-name "$POLICY" \
  --query 'PolicyDocument.Statement[0].Resource' --output text

echo
echo "Done. Next, backfill from the existing corpus -- dry run first:"
echo "  AWS_PROFILE=$PROFILE ~/.rsvenv/bin/python tools/backfill_first_seen.py"
echo "  AWS_PROFILE=$PROFILE ~/.rsvenv/bin/python tools/backfill_first_seen.py --apply"
echo
echo "There is an empty $TABLE in 620534471984 from the 2026-08-29 mistake."
echo "It costs nothing on PAY_PER_REQUEST with no items. Deleting it is your"
echo "call -- this script will not aim a delete-table at that account."
