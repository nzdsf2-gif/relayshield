#!/bin/sh
# Subscribe relayshield-bundle-fulfillment to a SaaS product's AWS Marketplace
# SNS topics. IDEMPOTENT: safe to re-run, and it re-runs read-only when the
# subscription already exists.
#
#   AWS_PROFILE=relayshield sh tools/subscribe_bundle_sns.sh <product-code>
#
# WHY THIS EXISTS, AND IT IS THE DRIFT RULE APPLIED TO A RESOURCE
# ---------------------------------------------------------------
# Every SaaS product gets its own pair of SNS topics, in AWS's own account,
# named after the PRODUCT CODE:
#
#   aws-mp-subscription-notification-<product-code>   subscribe/unsubscribe
#   aws-mp-entitlement-notification-<product-code>    contract changes
#
# relayshield_bundle_fulfillment.py provisions the customer's API key on
# subscribe-success. With no subscription that event never arrives, no key is
# ever issued, no metered call is ever made, and AWS's audit reports "no
# successful metering records" -- which reads as a code problem and is a
# missing resource.
#
# NOTHING IN THIS REPOSITORY HAS EVER CREATED ONE. Bundle D's and Bundle A's
# were made by hand and no session recorded it, so the step was invisible to
# every later reader, including the one writing Bundle B's runbook. That is the
# drift rule in its usual shape with the direction reversed: not code living
# only in AWS, but a REQUIRED AWS RESOURCE living only in somebody's memory.
#
# TWO CALLS PER TOPIC AND BOTH ARE NEEDED
# ---------------------------------------
#   lambda add-permission  lets SNS invoke the function. Without it the
#                          subscription is created and every delivery fails.
#   sns subscribe          creates the delivery.
# The permission is added FIRST, deliberately: a subscription that exists
# before the permission drops the events that arrive in between, and a
# subscribe-success is not re-sent.

set -u
export AWS_PAGER=""

REGION=us-east-1
ACCOUNT=239677749008
MP_ACCOUNT=287250355862
FUNC=relayshield-bundle-fulfillment
FUNC_ARN="arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FUNC}"

CODE="${1:-}"
if [ -z "$CODE" ]; then
  echo "usage: AWS_PROFILE=relayshield sh $0 <product-code>" >&2
  echo "" >&2
  echo "The PRODUCT CODE, 25 lowercase alphanumerics. NOT the prod-... entity" >&2
  echo "id, which is the Catalog API identifier and names no topic." >&2
  exit 2
fi
if ! printf '%s' "$CODE" | grep -Eq '^[a-z0-9]{20,30}$'; then
  echo "REFUSING: '$CODE' is not a product code." >&2
  case "$CODE" in
    prod-*) echo "That is a Catalog API ENTITY ID. The product code is a" >&2
            echo "separate value, returned by ResolveCustomer and shown as" >&2
            echo "'Product code' on the product's page in the Marketplace" >&2
            echo "Management Portal." >&2 ;;
    *) if printf '%s' "$CODE" | grep -Eq '^[0-9a-f]{40}$'; then
         echo "That is a git commit SHA, which is the most copyable 40-hex" >&2
         echo "string on an Actions run page and is never a product code." >&2
       fi ;;
  esac
  exit 2
fi

aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== identity =="
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
echo "account: $GOT"
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "REFUSING: expected $ACCOUNT, got $GOT." >&2
  echo "620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2
  exit 1
fi

for KIND in subscription entitlement; do
  TOPIC="arn:aws:sns:${REGION}:${MP_ACCOUNT}:aws-mp-${KIND}-notification-${CODE}"
  # A statement id may only contain alphanumerics and a few punctuation marks,
  # and must be unique per function: one per topic, derived so a re-run
  # produces the same id and AWS reports it as already existing rather than
  # creating a duplicate.
  SID="mp-${KIND}-${CODE}"
  echo
  echo "== ${KIND} topic =="
  echo "$TOPIC"

  echo "-- lambda permission --"
  OUT=$(aws_ lambda add-permission --function-name "$FUNC" \
          --statement-id "$SID" --action lambda:InvokeFunction \
          --principal sns.amazonaws.com --source-arn "$TOPIC" 2>&1) || true
  case "$OUT" in
    *ResourceConflictException*) echo "   already present, left alone" ;;
    *error*|*Error*) echo "   FAILED, verbatim:"; echo "$OUT" | sed 's/^/   /' ;;
    *) echo "   added" ;;
  esac

  echo "-- subscription --"
  # Listing first so a re-run does not create a second delivery to the same
  # endpoint. SNS does dedupe identical lambda subscriptions, but the listing
  # is also the only way to REPORT the state, and a script that cannot say
  # what it found is a script somebody runs twice.
  HAVE=$(aws_ sns list-subscriptions-by-topic --topic-arn "$TOPIC" \
           --query "Subscriptions[?Endpoint=='${FUNC_ARN}'].SubscriptionArn" \
           --output text 2>&1) || true
  if printf '%s' "$HAVE" | grep -qi "error"; then
    echo "   could not list (expected before the first subscription: the topic"
    echo "   is in AWS's account). Subscribing anyway."
    HAVE=""
  fi
  if [ -n "$HAVE" ] && [ "$HAVE" != "None" ]; then
    echo "   already subscribed: $HAVE"
  else
    OUT=$(aws_ sns subscribe --topic-arn "$TOPIC" --protocol lambda \
            --notification-endpoint "$FUNC_ARN" \
            --query SubscriptionArn --output text 2>&1) || true
    case "$OUT" in
      *error*|*Error*) echo "   FAILED, verbatim:"; echo "$OUT" | sed 's/^/   /'
                       echo "   AuthorizationError here means the topic policy does not allow"
                       echo "   this account to subscribe, which for a marketplace topic means"
                       echo "   the product code is wrong or the product is not yours." ;;
      *) echo "   subscribed: $OUT" ;;
    esac
  fi
done

echo
echo "== VERIFY =="
echo "Re-run this script. Every line should read 'already present' or"
echo "'already subscribed'. Anything else means a call did not take."
echo
echo "A subscription does NOT replay events that were missed. If the"
echo "subscribe-success for an existing agreement has already been sent, the"
echo "key is provisioned by following the fulfillment redirect again from the"
echo "BUYER account rather than by waiting for another notification."
