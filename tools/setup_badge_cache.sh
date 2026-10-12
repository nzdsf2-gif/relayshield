#!/bin/sh
# Create relayshield_badge_cache, which relayshield-api reads on every badge request.
# Idempotent. Dry run by default: it only READS unless given --apply.
#
#   AWS_PROFILE=relayshield sh tools/setup_badge_cache.sh
#   AWS_PROFILE=relayshield sh tools/setup_badge_cache.sh --apply
#
# WHY. tools/diagnose_lambda_errors.sh relayshield-api (2026-10-12) showed about 285 error
# lines a day, one every five minutes, all of them:
#   Badge score fetch failed relayshield.net: ResourceNotFoundException ... GetItem
# The badge handler reads relayshield_badge_cache, which has never existed, so the catch
# sets level UNKNOWN. THE BADGE ON A PUBLIC PAGE HAS BEEN RENDERING "UNKNOWN" EVERY TIME,
# and every error count for the API carries 285 a day of this noise.
#
# NO GRANT IS NEEDED. iam/snapshots/relayshield-breach-check-role-1sapnwdl.json already
# names this table's ARN in the shared role (line 122). Step 4 still simulates it rather
# than trusting that, because a snapshot is a lead, not a fact.
#
# THE TTL STEP IS THE ONE THAT CANNOT BE SKIPPED. The handler writes a `ttl` attribute
# (one hour), and DynamoDB ignores it unless TTL is ENABLED on the table, so without it a
# score would be served forever.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_badge_cache
FUNC=relayshield-api
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Account"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing was changed." >&2
  exit 1
fi
echo "   $GOT  (correct)"

echo
echo "== 2. Table $TABLE"
if aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "   already exists -- leaving it alone"
  EXISTS=1
else
  EXISTS=0
  if [ "$APPLY" = 1 ]; then
    echo "   not present -- creating (hash key domain, on demand)"
    aws dynamodb create-table \
      --table-name "$TABLE" \
      --attribute-definitions AttributeName=domain,AttributeType=S \
      --key-schema AttributeName=domain,KeyType=HASH \
      --billing-mode PAY_PER_REQUEST \
      --query 'TableDescription.TableName' --output text
    aws dynamodb wait table-exists --table-name "$TABLE"
    echo "   created"
    EXISTS=1
  else
    echo "   not present -- DRY RUN, would create (hash key domain, on demand)"
  fi
fi

echo
echo "== 3. TTL on attribute 'ttl'"
if [ "$EXISTS" = 1 ]; then
  TTL_STATUS=$(aws dynamodb describe-time-to-live --table-name "$TABLE" \
    --query 'TimeToLiveDescription.TimeToLiveStatus' --output text 2>/dev/null || echo UNKNOWN)
  echo "   current: $TTL_STATUS"
  case "$TTL_STATUS" in
    ENABLED|ENABLING) echo "   already on -- nothing to do" ;;
    *)
      if [ "$APPLY" = 1 ]; then
        aws dynamodb update-time-to-live --table-name "$TABLE" \
          --time-to-live-specification "Enabled=true,AttributeName=ttl" \
          --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text
      else
        echo "   DRY RUN, would enable it"
      fi ;;
  esac
else
  echo "   table not created yet (dry run)"
fi

echo
echo "== 4. Can $FUNC read and write it?"
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" --query Role --output text)
echo "   role: ${ROLE_ARN##*/}"
TABLE_ARN="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}"
for ACTION in dynamodb:GetItem dynamodb:PutItem; do
  DECISION=$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" \
    --action-names "$ACTION" --resource-arns "$TABLE_ARN" \
    --query 'EvaluationResults[0].EvalDecision' --output text 2>/dev/null || echo "simulate-failed")
  printf '   %-22s %s\n' "$ACTION" "$DECISION"
done
echo
echo "allowed on both: done, no grant. implicitDeny: a grant is needed and the shared role is"
echo "full (see iam_role_split.md), so stop and say so. simulate-failed: says nothing."
[ "$APPLY" = 1 ] || { echo; echo "DRY RUN. Re-run with --apply to create it."; }
echo "Proof: the next badge request logs no 'Badge score fetch failed' line."
