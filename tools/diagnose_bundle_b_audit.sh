#!/bin/sh
# Why does AWS's audit see no GetEntitlements calls and no metering records for
# Bundle B? READ ONLY. It writes nothing to AWS.
#
#   AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_audit.sh
#
# THE AUDIT SAYS TWO THINGS AND THERE ARE THREE CAUSES.
#
#   AUDIT_ERROR 1  no successful calls to the Entitlements Service
#   AUDIT_ERROR 2  no successful metering records
#
# Both are downstream of ONE event that has not happened: the fulfillment
# redirect. Accepting a private offer creates an AGREEMENT. It does not POST a
# registration token to our handler, and the token is what starts everything:
#
#   redirect  -> ResolveCustomer -> GetEntitlements   <- fixes audit error 1
#             -> writes pending_<customer>            -> redirect to /developers
#   SNS       -> subscribe-success -> GetEntitlements -> provisions the API key
#   one call  -> BatchMeterUsage with the LicenseArn  <- fixes audit error 2
#
# Three things can break that chain and each has a different fix. This script
# separates them, because "resubmit and see" costs an audit cycle.
#
# CAUSE A. BUNDLE_B_PRODUCT_CODE HOLDS A WRONG VALUE, WHICH IS WORSE THAN NONE.
#   _resolve_bundle() compares BUNDLE_CONFIGS["attack_surface_bundle_access"]
#   ["product_code"] against the code ResolveCustomer returned, and on a
#   mismatch it logs "Bundle mismatch" and returns None -- deliberately, because
#   provisioning the wrong bundle is worse than provisioning none. So a wrong
#   value BLOCKS fulfillment, while an EMPTY value skips the check entirely and
#   lets it through. The git SHA written on 2026-09-18 is a wrong value.
#
# CAUSE B. NOTHING IS SUBSCRIBED TO BUNDLE B'S SNS TOPICS.
#   Each SaaS product gets its own pair of topics in AWS's account, named after
#   the PRODUCT CODE. The key is provisioned on subscribe-success, so with no
#   subscription the buyer never gets a key and audit error 2 can never clear.
#   NOTHING IN THIS REPOSITORY HAS EVER CREATED ONE: grep for
#   aws-mp-subscription-notification and the only hits are a comment and a
#   docstring. Bundle D's and Bundle A's were made by hand and nobody wrote it
#   down, which is the drift rule applied to a resource rather than to code.
#
# CAUSE C. THE REDIRECT SIMPLY HAS NOT BEEN FOLLOWED.
#   Cheapest of the three and the most likely. Section 4 says whether a
#   pending_ row exists, which is the fingerprint of a redirect that ran.

set -u

PROFILE="${AWS_PROFILE:-}"
REGION=us-east-1
ACCOUNT=239677749008
FUNC=relayshield-bundle-fulfillment
# AWS Marketplace publishes these topics from its own account in us-east-1.
MP_ACCOUNT=287250355862

export AWS_PAGER=""
aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== 0. Which account are we talking to?"
if [ -z "$PROFILE" ]; then
  echo "STOP: AWS_PROFILE is not set. Re-run with AWS_PROFILE=relayshield, or" >&2
  echo "      this reads 620534471984, the pre-audit account, and reports" >&2
  echo "      missing resources that are not missing." >&2
  exit 1
fi
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: credentials resolve to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 1. CAUSE A. What product codes does the fulfillment Lambda hold?"
echo "   Only these three keys are printed. The block also holds live secrets"
echo "   and a full dump would put them in this terminal and its scrollback."
for KEY in BUNDLE_D_PRODUCT_CODE BUNDLE_A_PRODUCT_CODE BUNDLE_B_PRODUCT_CODE; do
  V=$(aws_ lambda get-function-configuration --function-name "$FUNC" \
        --query "Environment.Variables.$KEY" --output text 2>&1) || true
  case "$V" in
    ""|None) V="(not set)" ;;
    *Error*|*error*) V="(could not read: $V)" ;;
  esac
  printf '   %-24s %s\n' "$KEY" "$V"
done
cat <<'EOT'
   READING IT:
     a 40-character hex string  -> a git commit SHA. This is CAUSE A and it
                                   BLOCKS fulfillment. Worse than empty.
     prod-...                   -> a Catalog API entity id, not a product code.
                                   Also a mismatch, also blocks.
     25 lowercase alphanumerics -> the right shape. Compare it against the
                                   Product code field on the product's page in
                                   the Marketplace Management Portal.
     (not set)                  -> fulfillment WORKS (the mismatch check is
                                   skipped on an empty config value), but a
                                   cancelled customer's key is never
                                   deactivated. Fix it after the audit clears.
EOT
echo

echo "== 2. CAUSE B. Is anything subscribed to Bundle B's SNS topics?"
CODE=$(aws_ lambda get-function-configuration --function-name "$FUNC" \
         --query "Environment.Variables.BUNDLE_B_PRODUCT_CODE" --output text 2>/dev/null) || CODE=""
case "$CODE" in None) CODE="" ;; esac
if ! printf '%s' "$CODE" | grep -Eq '^[a-z0-9]{20,30}$'; then
  echo "   SKIPPED: BUNDLE_B_PRODUCT_CODE is not a product code, and the topic"
  echo "   names are built FROM the product code, so there is nothing to look"
  echo "   up. Fix cause A first, then re-run. This is a limit of the input,"
  echo "   not a finding about the topics."
else
  for KIND in subscription entitlement; do
    TOPIC="arn:aws:sns:${REGION}:${MP_ACCOUNT}:aws-mp-${KIND}-notification-${CODE}"
    echo "   -- ${KIND} topic"
    echo "      $TOPIC"
    OUT=$(aws_ sns list-subscriptions-by-topic --topic-arn "$TOPIC" \
            --query 'Subscriptions[].[Protocol,Endpoint]' --output text 2>&1) || true
    if printf '%s' "$OUT" | grep -qi "error"; then
      echo "      could not list, verbatim:"
      echo "      $OUT"
      echo "      AuthorizationError or NotFound here is EXPECTED when nothing"
      echo "      has ever subscribed: the topic lives in AWS's account and a"
      echo "      seller can list it only once it holds a subscription of"
      echo "      theirs. Treat it as 'no subscription', not as a broken topic."
    elif [ -z "$OUT" ]; then
      echo "      NO SUBSCRIPTIONS. This is CAUSE B: subscribe-success will"
      echo "      never reach us, so no key is ever provisioned."
    else
      echo "$OUT" | sed 's/^/      /'
    fi
  done
fi
echo

echo "== 3. Has GetEntitlements ever run for Bundle B? (last 14 days)"
SINCE=$(( ( $(date +%s) - 14*24*3600 ) * 1000 ))
for PAT in "fulfillment entitlement check" "get_entitlements failed" "Bundle mismatch" "Product code not recognised" "Bundle unresolved"; do
  echo "   -- $PAT"
  OUT=$(aws_ logs filter-log-events \
          --log-group-name "/aws/lambda/${FUNC}" \
          --start-time "$SINCE" --filter-pattern "\"$PAT\"" \
          --max-items 10 --query 'events[].message' --output text 2>&1) || true
  if printf '%s' "$OUT" | grep -qi "error"; then
    echo "      could not read, verbatim: $OUT"
  elif [ -z "$OUT" ] || [ "$OUT" = "None" ]; then
    echo "      none"
  else
    echo "$OUT" | sed 's/^/      /'
  fi
done
cat <<'EOT'
   READING IT:
     "Product code not recognised: got <CODE>" names the code ResolveCustomer
     ACTUALLY returned. That is the authoritative value for cause A, better
     than any value typed from memory, because it came from AWS.
     "Bundle mismatch" is cause A firing: the redirect ran and was refused.
     Nothing at all means the redirect has not been followed -- cause C.
EOT
echo

echo "== 4. CAUSE C. Did the fulfillment redirect ever run?"
echo "   A redirect writes pending_<customer-id> before it renders. Scanning"
echo "   for pending rows; only the key name and product code are printed."
OUT=$(aws_ dynamodb scan --table-name relayshield_api_keys \
        --filter-expression "begins_with(api_key, :p)" \
        --expression-attribute-values '{":p":{"S":"pending_"}}' \
        --projection-expression "api_key, aws_product_code, aws_bundle, created_at" \
        --query 'Items' --output json 2>&1) || true
if printf '%s' "$OUT" | grep -qi "error"; then
  echo "   could not scan, verbatim: $OUT"
elif [ "$OUT" = "[]" ] || [ -z "$OUT" ]; then
  echo "   NO PENDING ROWS. The redirect has not run. That is cause C and it"
  echo "   is the cheapest of the three to fix: open the subscription from the"
  echo "   BUYER account and follow its set-up link."
else
  echo "$OUT" | sed 's/^/   /'
fi
echo

echo "== 5. Has BatchMeterUsage ever succeeded? (last 14 days)"
# ALL SIX STRINGS THE FUNCTION WRITES. The first three were the whole list
# until 2026-09-22, and the three that were missing are exactly the ones the
# metering-response fix ADDED -- so a REJECTED record printed "none" here,
# which reads identically to "nothing was ever metered" and is a different
# finding with a different fix. For the product-code JOIN, use
# tools/verify_bundle_b_metering.py: these lines log account= and dimension=
# and never the product, so this section cannot say WHICH product landed.
for PAT in "Marketplace usage reported" "Marketplace usage NOT metered" \
           "Marketplace usage UNPROCESSED" "Marketplace usage reporting returned no Results" \
           "Marketplace usage reporting failed" "Skipping bundle usage report"; do
  echo "   -- $PAT"
  OUT=$(aws_ logs filter-log-events \
          --log-group-name "/aws/lambda/relayshield-api" \
          --start-time "$SINCE" --filter-pattern "\"$PAT\"" \
          --max-items 10 --query 'events[].message' --output text 2>&1) || true
  if printf '%s' "$OUT" | grep -qi "error"; then
    echo "      could not read, verbatim: $OUT"
  elif [ -z "$OUT" ] || [ "$OUT" = "None" ]; then
    echo "      none"
  else
    echo "$OUT" | sed 's/^/      /'
  fi
done
cat <<'EOT'
   READING IT:
     "Skipping bundle usage report: missing account/license_arn/dimension"
     means a call was served and NOT metered, because the key row carries no
     LicenseArn. That happens when the key was made outside the SNS
     subscribe-success path, and AWS's audit counts it as zero either way.
     A key that cannot meter is a key that cannot clear audit error 2.
EOT
echo
echo "== DONE. Nothing above wrote to AWS."
