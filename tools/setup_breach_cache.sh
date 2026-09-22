#!/bin/sh
# Create relayshield_breach_cache and confirm relayshield-api can use it.
# Read-mostly and idempotent -- safe to re-run.
#
#   sh tools/setup_breach_cache.sh
#
# WHY THIS TABLE EXISTS
# ---------------------
# handle_breach called HIBP live on every request and cached nothing. HIBP is a
# SUBSCRIPTION WITH A RATE LIMIT, not a per-call bill, so the scarce thing is
# requests per minute against ONE key -- shared by the Telegram bot, the
# WhatsApp bot, the OAuth watchlist and every paying API customer. A 429 earned
# by one caller is served to all of them.
#
# THE CODE SHIPS INERT WITHOUT THIS TABLE, ON PURPOSE. _breach_cache_get fails
# soft and returns None, so every call falls through to a live HIBP request --
# exactly today's behaviour. Nothing breaks before this runs and the cache
# starts working the moment it does, with no deploy.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_breach_cache
FUNC=relayshield-api

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT." >&2
  echo "Nothing has been created." >&2
  exit 1
fi
echo "   $GOT  (correct)"

echo
echo "== 2. Table $TABLE"
if aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "   already exists -- leaving it alone"
else
  echo "   not present -- creating"
  # Hash key only, on the SHA-256 of the address. The email itself is never
  # stored: a dump of this table must not be a list of who asked about whom.
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=email_hash,AttributeType=S \
    --key-schema AttributeName=email_hash,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. TTL -- and this is the step that is easy to skip and silently wrong"
# _breach_cache_put writes a `ttl` attribute. DynamoDB IGNORES that attribute
# unless TTL is ENABLED on the table, so without this step rows never expire:
# the cache would serve a breach verdict from months ago, forever, and look
# perfectly healthy while doing it. A stale "no breaches" is the worst thing
# this table can produce.
TTL_STATUS=$(aws dynamodb describe-time-to-live --table-name "$TABLE" \
  --query 'TimeToLiveDescription.TimeToLiveStatus' --output text 2>/dev/null || echo UNKNOWN)
echo "   current: $TTL_STATUS"
case "$TTL_STATUS" in
  ENABLED|ENABLING)
    echo "   already on -- nothing to do" ;;
  *)
    echo "   enabling on attribute 'ttl'"
    aws dynamodb update-time-to-live --table-name "$TABLE" \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text ;;
esac

echo
echo "== 4. Can $FUNC already write to it?"
# THE CHEAP QUESTION FIRST. The shared role carries a policy per table by
# convention, but if any of them grants a relayshield_* wildcard the permission
# already exists and there is nothing to add -- which matters more than usual
# here, because that role's inline budget is FULL (26 policies, 10127/10240
# bytes) and its managed slots are at 11 of 10. A grant that is not needed is a
# grant that cannot be made.
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" \
  --query Role --output text)
ROLE=${ROLE_ARN##*/}
echo "   role: $ROLE"
TABLE_ARN="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}"

for ACTION in dynamodb:GetItem dynamodb:PutItem; do
  DECISION=$(aws iam simulate-principal-policy \
    --policy-source-arn "$ROLE_ARN" \
    --action-names "$ACTION" \
    --resource-arns "$TABLE_ARN" \
    --query 'EvaluationResults[0].EvalDecision' --output text 2>/dev/null || echo "simulate-failed")
  printf '   %-22s %s\n' "$ACTION" "$DECISION"
done

echo
echo "READ THE TWO DECISIONS ABOVE:"
echo "  allowed         -- done. Nothing else to do; the cache is live."
echo "  implicitDeny    -- a grant is needed. The shared role's inline budget is"
echo "                     FULL, so it must be a CUSTOMER-MANAGED policy, and"
echo "                     that role is already at 11 attached of 10 allowed."
echo "                     Do NOT force it: read iam_role_split.md first."
echo "  simulate-failed -- says nothing about the grant, only that this identity"
echo "                     cannot run simulate-principal-policy. Not a finding."
echo
echo "The cache degrades to a live HIBP call in every one of those cases, so"
echo "nothing is broken while this is outstanding. It is just not yet helping."
