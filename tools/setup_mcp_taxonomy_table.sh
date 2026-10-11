#!/bin/sh
# Create relayshield_mcp_taxonomy. Idempotent, safe to re-run.
#
#   AWS_PROFILE=relayshield sh tools/setup_mcp_taxonomy_table.sh
#
# A SEPARATE TABLE, NOT relayshield_mitre_atlas. That table is rewritten weekly
# by relayshield_intel_atlas.py from MITRE's published YAML and carries a 30-day
# TTL. RelayShield-authored entries do not belong in a table a scheduled ingest
# owns, and a TTL would silently delete them.
#
# NO TTL ON PURPOSE. These are approved, hand-reviewed taxonomy entries.
#
# NOTHING READS THIS TABLE YET. Loading it grants no Lambda access and changes no
# verdict. The loader runs as the operator (relayshield-deployer), the way
# tools/backfill_first_seen.py does, so no IAM change is needed to load it.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_mcp_taxonomy

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
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=entry_id,AttributeType=S \
    --key-schema AttributeName=entry_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. Done. Next: load the entries (dry run first)."
echo "   AWS_PROFILE=relayshield python3 tools/load_mcp_taxonomy.py"
