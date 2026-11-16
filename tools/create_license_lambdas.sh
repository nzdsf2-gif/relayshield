#!/bin/sh
# Create the two Step 4 licensing Lambdas: the license service and
# the Stripe issuance flow. Each gets its own role and policy.
#
#   sh tools/create_license_lambdas.sh
#
# Run from the repo root, on the Mac, AFTER Phase 1 (tables, KMS
# key, SES) and Phase 2 (the two .py files at the repo root).
# Idempotent: every step checks first, so a re-run after a partial
# failure is safe.
#
# CREATE FIRST, MAP SECOND. The functions must exist before they
# are mapped in deploy_lambdas.yml, because the deployer calls
# update-function-code on whatever LAMBDA_MAP names. Mapping a
# function that does not exist turns the first push red with a
# ResourceNotFoundException that reads exactly like a broken
# deploy. This script creates them; Phase 3 maps them, in that
# order and no other. (Phase 3 is done before this phase in the
# document so the mapping edits are reviewed together with the
# code; the functions are created here, before the commit in
# Phase 8, so the first dispatch in Phase 9 has a target.)
#
# The Stripe function import probe returns 500 "webhook secret
# unavailable" until Phase 7 stores relayshield/stripe_webhook_secret.
# That is expected and is not a failure: the probe only asserts the
# module imported, and a real JSON error body proves it did.

set -eu
export AWS_PAGER=""

ACCOUNT="239677749008"
REGION="us-east-1"
PROFILE="relayshield"

echo "== identity =="
ACTUAL=$(AWS_PROFILE=$PROFILE aws sts get-caller-identity --query Account --output text --no-cli-pager)
echo "account: $ACTUAL"
if [ "$ACTUAL" = "$ACCOUNT" ]; then
  echo "correct account"
else
  echo "REFUSING: expected $ACCOUNT, got $ACTUAL. 620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2
  exit 1
fi

echo
echo "== tables must already exist =="
AWS_PROFILE=$PROFILE aws dynamodb describe-table --table-name relayshield_license_revocations --region $REGION --no-cli-pager >/dev/null || { echo "STOP: relayshield_license_revocations does not exist. Run Phase 1 first." >&2; exit 1; }
AWS_PROFILE=$PROFILE aws dynamodb describe-table --table-name relayshield_licenses --region $REGION --no-cli-pager >/dev/null || { echo "STOP: relayshield_licenses does not exist. Run Phase 1 first." >&2; exit 1; }
echo "both tables exist"

echo
echo "== KMS key ARN =="
KMS_ARN=$(AWS_PROFILE=$PROFILE aws kms describe-key --key-id alias/relayshield/license-kms --query KeyMetadata.Arn --output text --region $REGION --no-cli-pager)
echo "kms key: $KMS_ARN"

create_role() {
  ROLE="$1"
  if AWS_PROFILE=$PROFILE aws iam get-role --role-name "$ROLE" --no-cli-pager >/dev/null 2>&1; then
    echo "$ROLE exists"
  else
    AWS_PROFILE=$PROFILE aws iam create-role --role-name "$ROLE" \
      --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
      --no-cli-pager >/dev/null
    AWS_PROFILE=$PROFILE aws iam attach-role-policy --role-name "$ROLE" \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --no-cli-pager
    echo "$ROLE created"
  fi
}

create_function() {
  FN="$1"
  HANDLER="$2"
  FILE="$3"
  ROLE="$4"
  TIMEOUT="$5"
  ENV_VARS="$6"
  TMP=$(mktemp -d)
  cp "$FILE" "$TMP/"
  (cd "$TMP" && zip -q function.zip "$FILE")
  if AWS_PROFILE=$PROFILE aws lambda get-function --function-name "$FN" --region $REGION --no-cli-pager >/dev/null 2>&1; then
    AWS_PROFILE=$PROFILE aws lambda update-function-code --function-name "$FN" \
      --zip-file "fileb://$TMP/function.zip" --region $REGION --no-cli-pager >/dev/null
    AWS_PROFILE=$PROFILE aws lambda wait function-updated --function-name "$FN" --region $REGION
    echo "$FN code updated"
  else
    CREATED=0
    i=1
    while [ "$i" -le 10 ]; do
      if AWS_PROFILE=$PROFILE aws lambda create-function --function-name "$FN" \
          --runtime python3.12 --handler "$HANDLER" \
          --role "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
          --timeout "$TIMEOUT" --memory-size 256 \
          --environment "Variables={${ENV_VARS}}" \
          --zip-file "fileb://$TMP/function.zip" --region $REGION --no-cli-pager >/dev/null 2>"$TMP/err"; then
        CREATED=1
        break
      fi
      if grep -q "cannot be assumed by Lambda" "$TMP/err"; then
        echo "  role not propagated yet, attempt $i of 10, waiting 6s"
        sleep 6
        i=$((i + 1))
        continue
      fi
      echo "create-function failed for a reason that is not propagation:" >&2
      cat "$TMP/err" >&2
      exit 1
    done
    if [ "$CREATED" = "1" ]; then
      echo "$FN created"
    else
      echo "role still not assumable after 60s. Re-run this script." >&2
      exit 1
    fi
  fi
  AWS_PROFILE=$PROFILE aws lambda update-function-configuration --function-name "$FN" \
    --environment "Variables={${ENV_VARS}}" --region $REGION --no-cli-pager >/dev/null
  AWS_PROFILE=$PROFILE aws lambda wait function-updated --function-name "$FN" --region $REGION
  rm -rf "$TMP"
  AWS_PROFILE=$PROFILE aws lambda wait function-active-v2 --function-name "$FN" --region $REGION
  echo "$FN Active"
  AWS_PROFILE=$PROFILE aws lambda invoke --function-name "$FN" --region $REGION \
    --payload '{"source":"ci.import-probe"}' --cli-binary-format raw-in-base64-out \
    /tmp/rs-license-probe.json --no-cli-pager >/dev/null
  cat /tmp/rs-license-probe.json
  echo
  if [ -s /tmp/rs-license-probe.json ]; then
    if grep -q "ImportModuleError" /tmp/rs-license-probe.json; then
      echo "STOP: $FN failed to import. Read the body above." >&2
      exit 1
    fi
    echo "$FN imports cleanly (probe response above)"
  else
    echo "STOP: $FN probe returned nothing." >&2
    exit 1
  fi
}

echo
echo "== license service function =="
create_role "relayshield-license-service-role"
AWS_PROFILE=$PROFILE aws iam put-role-policy --role-name "relayshield-license-service-role" \
  --policy-name relayshield-license-service-access \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\"],
       \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/relayshield_license_revocations\"}
    ]}" --no-cli-pager
echo "license service policy applied"
create_function "relayshield-license-service" "relayshield_license_service.lambda_handler" "relayshield_license_service.py" "relayshield-license-service-role" "30" "LICENSE_REVOCATIONS_TABLE=relayshield_license_revocations"

echo
echo "== Stripe issuance function =="
create_role "relayshield-stripe-license-role"
AWS_PROFILE=$PROFILE aws iam put-role-policy --role-name "relayshield-stripe-license-role" \
  --policy-name relayshield-stripe-license-access \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\",\"dynamodb:UpdateItem\",\"dynamodb:GetItem\",\"dynamodb:Query\"],
       \"Resource\":[\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/relayshield_licenses\",\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/relayshield_license_revocations\"]},
      {\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",
       \"Resource\":[\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:relayshield/stripe_webhook_secret-*\",\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:relayshield/license_signing_key-*\"]},
      {\"Effect\":\"Allow\",\"Action\":\"kms:Encrypt\",
       \"Resource\":\"${KMS_ARN}\"},
      {\"Effect\":\"Allow\",\"Action\":\"ses:SendEmail\",
       \"Resource\":\"*\",
       \"Condition\":{\"StringEquals\":{\"ses:FromAddress\":\"licenses@relayshield.net\"}}}
    ]}" --no-cli-pager
echo "Stripe license policy applied"
create_function "relayshield-stripe-license" "relayshield_stripe_license.lambda_handler" "relayshield_stripe_license.py" "relayshield-stripe-license-role" "60" "STRIPE_WEBHOOK_SECRET_NAME=relayshield/stripe_webhook_secret,LICENSE_SIGNING_KEY_NAME=relayshield/license_signing_key,LICENSES_TABLE=relayshield_licenses,LICENSE_REVOCATIONS_TABLE=relayshield_license_revocations,LICENSE_KMS_KEY_ID=${KMS_ARN},LICENSE_SENDER_EMAIL=licenses@relayshield.net,LICENSE_SERVICE_URL=https://api.relayshield.net"

echo
echo "== DONE =="
echo "Both functions exist and import cleanly."
echo "Next: Phase 5 (relayshield-api role policy), then Phase 6 (API Gateway routes)."
