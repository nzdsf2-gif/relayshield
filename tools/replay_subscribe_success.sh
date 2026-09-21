#!/bin/sh
# Provision the API key for an existing AWS Marketplace agreement whose
# subscribe-success notification we were not subscribed to receive.
#
#   AWS_PROFILE=relayshield sh tools/replay_subscribe_success.sh \
#       <customer-identifier> <product-code>
#
# WHY THIS IS NEEDED, AND WHY IT IS NOT A HACK
# --------------------------------------------
# relayshield_bundle_fulfillment.py provisions the customer's rs_live_ key in
# exactly ONE place: the SNS `subscribe-success` branch. The fulfillment
# redirect does not provision -- it writes a pending_ row, and the email page
# only DISPLAYS a key that already exists, falling back to "your key is being
# provisioned and will arrive by email" when it does not.
#
# Bundle B's agreement was accepted on 2026-09-19. Nothing was subscribed to
# that product's SNS topic at the time, and SNS does not replay what a
# subscriber missed. So for this agreement the provisioning event is simply
# gone, and subscribing now does not bring it back: it only covers the NEXT
# customer.
#
# This invokes our own function, in our own account, with the event AWS already
# sent. It is a replay, not a fabrication: every value that matters is then read
# back FROM AWS by the handler itself -- GetEntitlements supplies the dimension,
# the LicenseArn and the CustomerAWSAccountId, and a customer with no live
# entitlement gets nothing. The only thing this payload asserts is WHICH
# customer and WHICH product to look up.
#
# THE LicenseArn IS THE POINT. BatchMeterUsage under AWS's Concurrent
# Agreements model identifies the product from the LicenseArn, so a key
# provisioned outside this path carries none and every metered call is dropped
# with "Skipping bundle usage report" -- served, unbilled, and counted as zero
# by the AWS audit. That is the difference between a key that can clear the
# audit and one that cannot.

set -u
export AWS_PAGER=""

REGION=us-east-1
ACCOUNT=239677749008
FUNC=relayshield-bundle-fulfillment

CUSTOMER="${1:-}"
CODE="${2:-}"
if [ -z "$CUSTOMER" ] || [ -z "$CODE" ]; then
  echo "usage: AWS_PROFILE=relayshield sh $0 <customer-identifier> <product-code>" >&2
  echo "" >&2
  echo "  customer-identifier  the CustomerIdentifier on the entitlement, e.g." >&2
  echo "                       the one tools/diagnose_bundle_b_entitlement.sh" >&2
  echo "                       printed in section 1." >&2
  echo "  product-code         25 lowercase alphanumerics. NOT a prod-... id." >&2
  exit 2
fi
if ! printf '%s' "$CODE" | grep -Eq '^[a-z0-9]{20,30}$'; then
  echo "REFUSING: '$CODE' is not a product code." >&2
  case "$CODE" in
    prod-*) echo "That is a Catalog API entity id." >&2 ;;
    *) printf '%s' "$CODE" | grep -Eq '^[0-9a-f]{40}$' && echo "That is a git commit SHA." >&2 ;;
  esac
  exit 2
fi

aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== identity =="
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
echo "account: $GOT"
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "REFUSING: expected $ACCOUNT, got $GOT." >&2
  exit 1
fi

echo
echo "== the entitlement this will provision from =="
# Read it FIRST and refuse if it is not there. Invoking without an entitlement
# writes a key with no LicenseArn, which is the exact defect this exists to
# avoid, and it would look like a success.
ENT=$(aws_ marketplace-entitlement get-entitlements --product-code "$CODE" \
        --filter "CUSTOMER_IDENTIFIER=$CUSTOMER" \
        --query 'Entitlements[].[Dimension,ExpirationDate]' --output text 2>&1) || true
if printf '%s' "$ENT" | grep -qi "error"; then
  echo "could not read, verbatim:" >&2; echo "$ENT" >&2; exit 1
fi
if [ -z "$ENT" ] || [ "$ENT" = "None" ]; then
  echo "REFUSING: no entitlement for customer=$CUSTOMER on product=$CODE." >&2
  echo "Provisioning from here would write a key with no LicenseArn, which" >&2
  echo "serves calls and meters nothing. Check the customer identifier first:" >&2
  echo "  AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_entitlement.sh" >&2
  exit 1
fi
echo "$ENT" | sed 's/^/   /'

echo
echo "== invoking =="
# BSD mktemp (macOS) requires the XXXXXX placeholder in a -t template and
# errors with "too few X's" without it. Caught by running this rather than
# by reading it, which is the whole reason every branch here is exercised.
TMP=$(mktemp -t rsreplay.XXXXXX) || exit 1
trap 'rm -f "$TMP" "$TMP.out"' EXIT
# The envelope handle_sns() parses: Records[0].EventSource == "aws:sns", and
# Sns.Message is a JSON STRING, which is how SNS delivers it.
cat > "$TMP" <<JSON
{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\\"action\\":\\"subscribe-success\\",\\"customer-identifier\\":\\"$CUSTOMER\\",\\"product-code\\":\\"$CODE\\"}"}}]}
JSON
python3 -c 'import json,sys; json.load(open(sys.argv[1])); print("   payload is valid JSON")' "$TMP" || exit 1

aws_ lambda invoke --function-name "$FUNC" \
  --cli-binary-format raw-in-base64-out \
  --payload "file://$TMP" "$TMP.out" --output json 2>&1 | sed 's/^/   /'
echo "   response body:"
cat "$TMP.out" 2>/dev/null | sed 's/^/   /'
echo

echo "== VERIFY, and this is the step that matters =="
cat <<'EOT'
   The invoke returning 200 only means the function did not raise. Confirm the
   key exists and carries a LicenseArn:

     AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh

   Section 3 should now show a "fulfillment entitlement check ... active=True"
   line, and the welcome email carries the rs_live_ key.

   IT IS IDEMPOTENT ENOUGH TO RE-RUN: _provision_api_key writes a key row and
   deletes the pending_ row, so a second run issues a SECOND key rather than
   failing. That is not harmful -- both are valid -- but use the one from the
   most recent welcome email.
EOT
