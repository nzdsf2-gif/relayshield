#!/bin/sh
# What is in relayshield-bundle-fulfillment's environment block, and what WAS
# in it before the last update? READ ONLY. It writes nothing to AWS.
#
#   AWS_PROFILE=relayshield sh tools/diagnose_bundle_fulfillment_env.sh
#
# WHY THIS EXISTS
# ---------------
# `aws lambda update-function-configuration --environment` REPLACES the whole
# variables block. It does not merge. So a command that sets one variable
# deletes every other variable on that function, silently, and the API returns
# a success block showing the new state -- which looks exactly like a correct
# result because it IS the correct result of the command that was sent.
#
# relayshield_bundle_fulfillment.py reads THREE:
#
#     BUNDLE_D_PRODUCT_CODE   Bundle D, live and public
#     BUNDLE_A_PRODUCT_CODE   Bundle A, live
#     BUNDLE_B_PRODUCT_CODE   Bundle B, not created yet
#
# An emptied BUNDLE_D_PRODUCT_CODE does not raise. PRODUCT_CODES loses the
# entry, `_product_code_filter()` stops matching any existing key row, and
# `_get_entitlement` on the SNS path queries GetEntitlements with the wrong
# set of product codes. Revocation and suspension scans find nothing and
# report success. That is the quiet-alarm shape with a live listing on it.
#
# Lambda does not keep the previous configuration of $LATEST, so there are
# exactly two places the old block can still be read from, and this checks
# both:
#
#   1. a PUBLISHED VERSION, whose configuration is frozen at publish time;
#   2. CLOUDTRAIL, where the UpdateFunctionConfiguration and CreateFunction
#      calls carry requestParameters.environment. Management events are kept
#      for 90 days.
#
# If both come back empty the honest answer is that the old block cannot be
# recovered from AWS, and the product codes have to be read off the
# Marketplace listings instead. This script says so rather than printing
# nothing, because an empty result and a missing permission look identical.

set -u

PROFILE="${AWS_PROFILE:-}"
REGION=us-east-1
ACCOUNT=239677749008
FUNC=relayshield-bundle-fulfillment

export AWS_PAGER=""

aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== 0. Which account are we talking to?"
if [ -z "$PROFILE" ]; then
  echo "STOP: AWS_PROFILE is not set. Re-run with AWS_PROFILE=relayshield," >&2
  echo "      or this reads 620534471984, the pre-audit account, and reports" >&2
  echo "      a missing function that is not missing." >&2
  exit 1
fi
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: credentials resolve to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 1. The environment block as it stands RIGHT NOW"
aws_ lambda get-function-configuration --function-name "$FUNC" \
     --query 'Environment.Variables' --output json
echo

echo "== 2. Published versions, whose configuration is frozen"
VERS=$(aws_ lambda list-versions-by-function --function-name "$FUNC" \
         --query 'Versions[?Version!=`$LATEST`].Version' --output text 2>&1) || true
if [ -z "$VERS" ] || [ "$VERS" = "None" ]; then
  echo "   none. No version was ever published, so Lambda itself holds no"
  echo "   earlier copy of the block. Step 3 is the remaining route."
else
  for V in $VERS; do
    echo "   --- version $V"
    aws_ lambda get-function-configuration --function-name "$FUNC" \
         --qualifier "$V" --query 'Environment.Variables' --output json
  done
fi
echo

echo "== 3. CloudTrail: every config write that named this function, newest first"
echo "   (management events are retained for 90 days)"
OUT=$(aws_ cloudtrail lookup-events \
        --lookup-attributes AttributeKey=ResourceName,AttributeValue="$FUNC" \
        --max-results 50 --output json 2>&1) || true
case "$OUT" in
  *AccessDenied*|*UnrecognizedClient*|*ExpiredToken*)
    echo "   REFUSED, and that is a fact about this identity, not about the"
    echo "   function. Verbatim:"
    echo "$OUT"
    ;;
  *)
    printf '%s' "$OUT" | python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
except Exception as exc:
    print("   could not parse the CloudTrail response: %s" % exc)
    raise SystemExit(0)
events = doc.get("Events") or []
if not events:
    print("   no events returned. Either nothing wrote to this function in the")
    print("   retention window, or CloudTrail is not recording it.")
    raise SystemExit(0)
shown = 0
for ev in events:
    try:
        detail = json.loads(ev.get("CloudTrailEvent") or "{}")
    except Exception:
        continue
    name = ev.get("EventName", "")
    if name not in ("UpdateFunctionConfiguration", "CreateFunction20150331",
                    "CreateFunction", "UpdateFunctionConfiguration20150331v2"):
        continue
    params = detail.get("requestParameters") or {}
    env = params.get("environment")
    if env is None:
        continue
    shown += 1
    print("   %s  %s" % (ev.get("EventTime"), name))
    print("      %s" % json.dumps(env, sort_keys=True))
if not shown:
    print("   events were returned, but none of them carried an environment")
    print("   block. The old variables are not recoverable from CloudTrail.")
'
    ;;
esac
echo

cat <<'GUIDE'
== HOW TO READ THIS

Compare section 1 against the newest block in section 2 or 3 that is NOT the
one just written.

  Section 1 holds FEWER keys than the earlier block
      Variables were deleted. Every key in the earlier block that is missing
      from section 1 has to go back, in ONE update-function-configuration
      call, because the API replaces rather than merges.

  Section 1 holds the same keys
      Nothing was lost. Only the VALUE of the key that was set needs checking.

  Sections 2 and 3 are both empty
      AWS cannot tell us what was there. The product codes are readable from
      the Marketplace listings instead: each SaaSProduct entity's product code
      is what ResolveCustomer returns for a subscriber to it, and the Bundle D
      and Bundle A entity ids are prod-kkvurtspreofy and prod-f5qkfsxlxs4qg.
      Do NOT guess a value into that block: a wrong product code matches no
      key row and fails silently, which is the state this script exists to
      detect.
GUIDE
