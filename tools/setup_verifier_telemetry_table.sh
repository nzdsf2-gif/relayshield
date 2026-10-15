#!/bin/sh
# Create relayshield_verifier_telemetry. Idempotent, safe to re-run.
#
#   AWS_PROFILE=relayshield sh tools/setup_verifier_telemetry_table.sh
#
# SCHEMA (design doc section 2.3, with the deviations the code needed):
#   pk              S   TELEMETRY#<UTC date>            hash key
#   sk              S   <10-digit epoch>#<uuid hex>     range key
#   agent_id_hash   S   SHA-256 of the agent identifier. OMITTED when there is none:
#                       it is the GSI key and a DynamoDB key attribute may not be empty
#   ip_prefix       S   agent's network prefix (IPv4 /24, IPv6 /48), global addresses only
#   rejection_reason S  closed set, see REJECTION_REASONS
#   attack_pattern  S   indicator types screened on a TI match; never an indicator
#   verifier_type   S   tap | pap | x401 | tap+x401
#   issuer_hash     S   SHA-256 of the credential issuer (x401 only)
#   reporter_hash   S   16 hex of SHA-256 of the API key: deletion on request, and the
#                       count of distinct accounts. Added to the design doc's schema.
#   ttl             N   epoch seconds, 90 days
#
#   GSI AgentHashIndex   agent_id_hash (HASH), sk (RANGE), projection ALL.
#   SPARSE: rows with no agent identifier are simply not in it.
#
# WRITE VOLUME. One day's rows share one partition key. That is fine at this stage
# (a rejection is rare and an opted-in account rarer) and the day bucket is what makes
# "everything from the last 24h" a single Query. If a single day ever approaches 1,000
# rejections a second, shard the pk (TELEMETRY#<date>#<00-15>) and query all shards.
#
# THE CODE SHIPS INERT WITHOUT THIS TABLE: the writer swallows its own errors, and with
# the opt-in off (the default) it never touches the table anyway.
#
# TTL is switched on here because DynamoDB IGNORES a ttl attribute unless it is enabled
# for that name: without this step rows never expire, and the privacy policy's 90-day
# figure would be false.
#
# NOTHING HERE WRITES TO THE IOC CORPUS, and nothing may: a ti_match row is our own
# corpus's verdict coming back at us, so treating it as independent evidence would let a
# false positive look corroborated by the customers it fooled.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_verifier_telemetry
INDEX=AgentHashIndex

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
  HAS_GSI=$(aws dynamodb describe-table --table-name "$TABLE" \
    --query "Table.GlobalSecondaryIndexes[?IndexName=='$INDEX'] | length(@)" --output text 2>/dev/null || echo 0)
  if [ "$HAS_GSI" = "0" ] || [ "$HAS_GSI" = "None" ]; then
    echo "   WARNING: the table exists WITHOUT the $INDEX index. It was not created by this"
    echo "   script. Adding an index is a separate, slow operation, so nothing was changed."
  fi
else
  echo "   not present -- creating, with $INDEX"
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
        AttributeName=agent_id_hash,AttributeType=S \
    --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
    --global-secondary-indexes \
        '[{"IndexName":"AgentHashIndex","KeySchema":[{"AttributeName":"agent_id_hash","KeyType":"HASH"},{"AttributeName":"sk","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. TTL on attribute 'ttl'"
TTL_STATUS=$(aws dynamodb describe-time-to-live --table-name "$TABLE" \
  --query 'TimeToLiveDescription.TimeToLiveStatus' --output text 2>/dev/null || echo UNKNOWN)
echo "   current: $TTL_STATUS"
case "$TTL_STATUS" in
  ENABLED|ENABLING)
    echo "   already on -- nothing to do" ;;
  *)
    echo "   enabling"
    aws dynamodb update-time-to-live --table-name "$TABLE" \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text ;;
esac

echo
echo "== 4. Next: let the TAP verifier Lambda write it (dry run first)."
echo "   Find its real name first -- the repo does not record it:"
echo "   AWS_PROFILE=relayshield aws lambda list-functions --query 'Functions[?contains(FunctionName, \`tap\`)].FunctionName' --output text"
echo "   Then:"
echo "   AWS_PROFILE=relayshield python3 tools/grant_breach_cache_access.py --table $TABLE --function <that name>"
