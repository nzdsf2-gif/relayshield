#!/bin/sh
# Create relayshield_bot_tokens and confirm relayshield-intel-monitor can
# write to it. Read-mostly and idempotent -- safe to re-run.
#
#   sh tools/setup_bot_tokens_table.sh
#
# WHY THIS TABLE EXISTS
# ---------------------
# BOT-TOKEN-1 phase 1 (leaked_bot_token_finding_scope.md section 6). A
# Telegram bot token found in the corpus gets ONE getMe call to establish
# liveness and the owner's username, and only sha256(token) plus that
# username plus the liveness verdict are stored -- never the token itself.
# The key is the hash, deliberately: it is both the idempotency check and
# the only thing that could identify the credential, mirroring
# relayshield_stolen_cards, which is keyed on pan_hash for the same reason.
#
# THE CODE SHIPS INERT WITHOUT THIS TABLE, ON PURPOSE. _store_bot_token_finding
# catches every DynamoDB error and logs a warning; nothing raises and nothing
# blocks archive ingestion. The corpus simply does not accumulate bot-token
# findings until this runs, with no deploy needed once it does.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_bot_tokens
FUNC=relayshield-intel-monitor

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
  # Hash key only, on sha256(token). The token itself is never a field on
  # this table or anywhere else -- see _store_bot_token_finding's docstring.
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=token_hash,AttributeType=S \
    --key-schema AttributeName=token_hash,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. TTL -- and this is the step that is easy to skip and silently wrong"
# DynamoDB IGNORES a 'ttl' attribute unless TTL is ENABLED on the table.
# Without this step, a finding never expires: harmless for a REVOKED token,
# but a LIVE one that gets revoked later stays flagged CRITICAL forever with
# nothing here to say the danger has passed.
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
# THE CHEAP QUESTION FIRST, per this repo's own rule: the shared role may
# already carry a relayshield_* wildcard, in which case there is nothing to
# grant -- which matters more than usual, because that role's inline budget
# is full and its managed slots are at 11 of 10.
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
echo "  allowed         -- done. Nothing else to do; the corpus starts"
echo "                     accumulating bot-token findings on the next scan."
echo "  implicitDeny    -- a grant is needed. The shared role's inline budget"
echo "                     is FULL, so it must be a CUSTOMER-MANAGED policy,"
echo "                     and that role is already at 11 attached of 10"
echo "                     allowed. Do NOT force it: read iam_role_split.md"
echo "                     first."
echo "  simulate-failed -- says nothing about the grant, only that this"
echo "                     identity cannot run simulate-principal-policy."
echo "                     Not a finding."
echo
echo "Nothing breaks while this is outstanding: _store_bot_token_finding logs"
echo "a warning and returns. It is just not yet collecting."
