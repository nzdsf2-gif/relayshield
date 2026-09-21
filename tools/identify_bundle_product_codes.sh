#!/bin/sh
# Which product code belongs to which bundle? READ ONLY. Writes nothing.
#
#   AWS_PROFILE=relayshield sh tools/identify_bundle_product_codes.sh
#   AWS_PROFILE=relayshield sh tools/identify_bundle_product_codes.sh <customer-id>
#
# WHY THIS EXISTS
# ---------------
# BUNDLE_A_PRODUCT_CODE and BUNDLE_D_PRODUCT_CODE were deleted from the
# fulfillment Lambda on 2026-09-18 by an `update-function-configuration
# --environment` that replaces rather than merges. Restoring them needs the
# values, and the repository held two product-code-shaped strings in contexts
# that did not say WHICH product either belonged to. Guessing is the failure
# this programme has already paid for: a wrong code in that field raises
# nothing, matches no key row, and silently stops a cancelled customer's key
# from ever being deactivated.
#
# THERE ARE TWO AUTHORITATIVE SOURCES AND THIS READS BOTH.
#
# 1. THE KEY TABLE PAIRS THEM. Every row the fulfillment handler writes carries
#    aws_product_code AND aws_bundle side by side, so the table itself records
#    which code produced which bundle. That is a fact written by our own code at
#    the moment AWS told it, not a value anybody typed.
#
# 2. GetEntitlements IS SCOPED TO ONE PRODUCT. Ask it for a code and it answers
#    with that product's entitlement Dimension, which maps straight through
#    BUNDLE_CONFIGS. A code that is not this customer's product returns nothing.
#    That is the discriminator when two candidate codes appear for one bundle.
#
# It prints a table and nothing else. Use it, then set the env vars with
# tools/lambda_env_merge.py or the Lambda console.

set -u
export AWS_PAGER=""

REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_api_keys
CUSTOMER="${1:-}"

aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== 0. Which account are we talking to?"
if [ -z "${AWS_PROFILE:-}" ]; then
  echo "STOP: AWS_PROFILE is not set. Re-run with AWS_PROFILE=relayshield." >&2
  exit 1
fi
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: credentials resolve to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 1. Every (product code, bundle) pair our own handler has written"
echo "   Source: $TABLE. Only these three attributes are projected; the table"
echo "   also holds live API keys and a full dump would put them in this"
echo "   terminal and its scrollback."
aws_ dynamodb scan --table-name "$TABLE" \
  --filter-expression "attribute_exists(aws_product_code) AND attribute_exists(aws_bundle)" \
  --projection-expression "aws_product_code, aws_bundle, created_at" \
  --query 'Items' --output json 2>&1 | python3 -c '
import json, sys, collections
raw = sys.stdin.read()
try:
    items = json.loads(raw)
except Exception:
    print("   could not scan, verbatim:"); print("   " + raw.strip()); raise SystemExit(0)
pairs = collections.defaultdict(lambda: {"n": 0, "first": "", "last": ""})
for it in items or []:
    code = (it.get("aws_product_code") or {}).get("S", "")
    bundle = (it.get("aws_bundle") or {}).get("S", "")
    when = (it.get("created_at") or {}).get("S", "")
    if not code or not bundle:
        continue
    p = pairs[(code, bundle)]
    p["n"] += 1
    p["first"] = min(p["first"] or when, when)
    p["last"] = max(p["last"], when)
if not pairs:
    print("   no rows carry both attributes. Section 2 is the remaining route.")
    raise SystemExit(0)
print("   %-26s %-26s %5s  %s" % ("PRODUCT CODE", "BUNDLE", "ROWS", "FIRST SEEN"))
for (code, bundle), p in sorted(pairs.items(), key=lambda kv: kv[1]["first"]):
    print("   %-26s %-26s %5d  %s" % (code, bundle, p["n"], p["first"][:10]))
print()
print("   READING IT: aws_bundle is BUNDLE_CONFIGS[...][\"label\"], written by")
print("   the handler at fulfillment from the dimension AWS returned. So a row")
print("   here is our own code recording what AWS said, which is stronger than")
print("   any value in a comment or a doc.")
print("     agentic_attack_surface      -> BUNDLE_D_PRODUCT_CODE")
print("     core_identity_exposure      -> BUNDLE_A_PRODUCT_CODE")
print("     attack_surface_supply_chain -> BUNDLE_B_PRODUCT_CODE")
'
echo

echo "== 2. Codes seen by ResolveCustomer that have NO row yet"
echo "   These are fulfillment attempts that were REFUSED before a row could be"
echo "   written, so section 1 cannot pair them. The log names the code; only"
echo "   GetEntitlements can say which bundle it is."
SINCE=$(( ( $(date +%s) - 14*24*3600 ) * 1000 ))
UNPAIRED=$(aws_ logs filter-log-events \
  --log-group-name "/aws/lambda/relayshield-bundle-fulfillment" \
  --start-time "$SINCE" --filter-pattern '"Product code not recognised"' \
  --query 'events[].message' --output text 2>/dev/null \
  | tr '\t' '\n' \
  | sed -n 's/.*got \([a-z0-9]\{20,30\}\).*/\1/p' | sort -u) || UNPAIRED=""
if [ -z "$UNPAIRED" ]; then
  echo "   none in the last 14 days."
else
  echo "$UNPAIRED" | sed 's/^/   /'
fi
echo

echo "== 3. GetEntitlements per candidate code. THIS IS THE DISCRIMINATOR."
if [ -z "$CUSTOMER" ]; then
  CUSTOMER=$(aws_ logs filter-log-events \
    --log-group-name "/aws/lambda/relayshield-bundle-fulfillment" \
    --start-time "$SINCE" --filter-pattern '"Bundle unresolved at fulfillment"' \
    --query 'events[-1].message' --output text 2>/dev/null \
    | tr '\t' '\n' \
    | sed -n 's/.*customer=\([A-Za-z0-9_-]*\).*/\1/p' | head -1) || CUSTOMER=""
fi
if [ -z "$CUSTOMER" ]; then
  echo "   SKIPPED: no customer identifier. Pass one as the first argument."
  echo "   It is the customer= value in a 'Bundle unresolved' log line."
else
  echo "   customer: $CUSTOMER"
  for CODE in $UNPAIRED; do
    printf '   %-26s ' "$CODE"
    OUT=$(aws_ marketplace-entitlement get-entitlements --product-code "$CODE" \
            --filter "CUSTOMER_IDENTIFIER=$CUSTOMER" \
            --query 'Entitlements[].[Dimension,ExpirationDate]' --output text 2>&1) || true
    if printf '%s' "$OUT" | grep -qi "error"; then
      echo "ERROR: $OUT"
    elif [ -z "$OUT" ] || [ "$OUT" = "None" ]; then
      echo "no entitlement for this customer"
    else
      echo "$OUT" | tr '\n' ' '; echo
    fi
  done
  cat <<'EOT'
   READING IT:
     a Dimension comes back        -> THIS is the product code for the bundle
                                      that dimension belongs to. Authoritative:
                                      AWS answered it for this customer.
     "no entitlement"              -> either the wrong code for this customer,
                                      or the agreement has not propagated yet.
                                      NOT proof the code is wrong on its own.
     AccessDeniedException         -> the role lacks
                                      aws-marketplace:GetEntitlements. A fact
                                      about the identity, not about the code.
     attack_surface_bundle_access  -> BUNDLE_B_PRODUCT_CODE
     agentic_bundle_access         -> BUNDLE_D_PRODUCT_CODE
     core_identity_bundle_access   -> BUNDLE_A_PRODUCT_CODE
EOT
fi
echo
echo "== DONE. Nothing above wrote to AWS."
