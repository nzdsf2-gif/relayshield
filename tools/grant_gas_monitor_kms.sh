#!/bin/sh
# Give relayshield-gas-monitor-role the KMS permissions its DynamoDB tables need.
#
#   AWS_PROFILE=relayshield sh tools/grant_gas_monitor_kms.sh            # reads, prints the policy
#   AWS_PROFILE=relayshield sh tools/grant_gas_monitor_kms.sh --apply
#
# WHY. tools/diagnose_lambda_errors.sh found relayshield-gas-monitor failing every run
# (2,021 of 2,021 in 7 days, about three times its 15-minute schedule once the two
# automatic retries are counted):
#
#   AccessDeniedException calling Scan: KMS key access denied ...
#   assumed-role/relayshield-gas-monitor-role is not authorized to perform ...
#
# The function's code is not the problem. relayshield_users is encrypted with a
# customer-managed key, and this function runs on its OWN role, which was never given
# permission to use that key. The shared role has it, which is why every other
# function reads the table. So the gas alerts have never been able to run.
#
# THE KEY IS READ FROM THE TABLE, NOT ASSUMED. The script asks DynamoDB which key
# each table uses, and asks IAM whether the role may already use it. It grants only
# what simulate-principal-policy says is missing, on exactly those key ARNs, and only
# when the call comes through DynamoDB (kms:ViaService), so the role gains no general
# ability to decrypt anything with that key.
#
# THE REAL PROOF IS THE NEXT SCHEDULED RUN, NOT THE SIMULATION. The policy is conditioned
# on kms:ViaService, which simulate-principal-policy cannot evaluate unless told the
# service, so the simulation AFTER the grant may still say implicitDeny while real
# DynamoDB calls succeed. Do not treat that line as a failure. Wait for a 15-minute
# tick and run: sh tools/diagnose_lambda_errors.sh relayshield-gas-monitor

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
ROLE=relayshield-gas-monitor-role
TABLES="relayshield_users relayshield_gas_state"
POLICY=GasMonitorKmsViaDynamoDB
ACTIONS="kms:Decrypt kms:Encrypt kms:GenerateDataKey kms:DescribeKey"
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was changed." >&2
  exit 1
fi
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text 2>&1) || { echo "STOP: $ROLE_ARN" >&2; exit 1; }
echo "role: $ROLE_ARN"

KEYS=""
for T in $TABLES; do
  K=$(aws dynamodb describe-table --table-name "$T" --query 'Table.SSEDescription.KMSMasterKeyArn' --output text 2>&1)
  echo "table $T  key: $K"
  case "$K" in
    arn:aws:kms:*) case " $KEYS " in *" $K "*) : ;; *) KEYS="$KEYS $K";; esac;;
    *) echo "   (no customer-managed key on this table, or not readable)";;
  esac
done
[ -n "$KEYS" ] || { echo "STOP: no table uses a customer-managed key, so this is not the cause. Nothing changed." >&2; exit 1; }

echo
echo "== can the role use each key today? (simulation)"
MISSING=""
for K in $KEYS; do
  for A in $ACTIONS; do
    D=$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" --action-names "$A" --resource-arns "$K" \
        --query 'EvaluationResults[0].EvalDecision' --output text 2>&1)
    printf '   %-22s %-14s %s\n' "$A" "$D" "${K##*/}"
    [ "$D" = "allowed" ] || MISSING="yes"
  done
done
if [ -z "$MISSING" ]; then
  echo "Everything is already allowed. The cause is elsewhere (the key policy, or a different key)."
  exit 0
fi

DOC=$(python3 - $KEYS <<'PY'
import json, sys
print(json.dumps({"Version": "2012-10-17", "Statement": [{
    "Sid": "UseTheTableKeysOnlyThroughDynamoDB",
    "Effect": "Allow",
    "Action": ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
    "Resource": sys.argv[1:],
    "Condition": {"StringEquals": {"kms:ViaService": "dynamodb.us-east-1.amazonaws.com"}}}]}, indent=2))
PY
)
echo
echo "== inline policy $POLICY that would be added to $ROLE"
echo "$DOC"

if [ "$1" != "--apply" ]; then
  echo
  echo "DRY RUN. Re-run with --apply to attach it."
  exit 0
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY" --policy-document "$DOC" && echo "attached."
echo
echo "== simulation after (IAM can lag a few seconds)"
for K in $KEYS; do
  for A in $ACTIONS; do
    printf '   %-22s %s\n' "$A" "$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" --action-names "$A" --resource-arns "$K" --query 'EvaluationResults[0].EvalDecision' --output text 2>&1)"
  done
done
echo
echo "Now wait for the next 15-minute run and confirm:  sh tools/diagnose_lambda_errors.sh relayshield-gas-monitor"
