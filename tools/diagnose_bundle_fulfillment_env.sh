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

echo "== 4. The SAME product codes on the functions that were NOT touched"
echo "   relayshield_api.py and relayshield_agentic_api.py both read"
echo "   BUNDLE_D_PRODUCT_CODE from their OWN environment blocks, which this"
echo "   incident did not write to. If either carries it, the value is"
echo "   recovered without guessing."
echo "   Only the named keys are printed. These blocks also hold live secrets"
echo "   and a full dump would put them in this terminal and its scrollback."
for FN in relayshield-api relayshield-agentic-api; do
  for KEY in BUNDLE_D_PRODUCT_CODE BUNDLE_A_PRODUCT_CODE BUNDLE_B_PRODUCT_CODE; do
    V=$(aws_ lambda get-function-configuration --function-name "$FN" \
          --query "Environment.Variables.$KEY" --output text 2>&1) || true
    case "$V" in
      ""|None) V="(not set)" ;;
      *Error*|*error*) V="(could not read: $V)" ;;
    esac
    printf '   %-26s %-24s %s\n' "$FN" "$KEY" "$V"
  done
done
echo

echo "== 5. Can GitHub Actions do the write, so a terminal step is not needed?"
echo "   Simulating on relayshield-github-deploy, the role Actions assumes."
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/relayshield-github-deploy"
FN_ARN="arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FUNC}"
SIM=$(aws_ iam simulate-principal-policy \
        --policy-source-arn "$ROLE_ARN" \
        --action-names lambda:GetFunctionConfiguration lambda:UpdateFunctionConfiguration \
        --resource-arns "$FN_ARN" \
        --query 'EvaluationResults[].[EvalActionName,EvalDecision]' \
        --output text 2>&1) || true
case "$SIM" in
  *Error*|*error*|*Denied*Access*) : ;;
esac
if printf '%s' "$SIM" | grep -qi "error"; then
  echo "   could not simulate, verbatim:"
  echo "$SIM"
  echo "   This says nothing about the role. It says this identity may not"
  echo "   call iam:SimulatePrincipalPolicy."
else
  printf '%s\n' "$SIM" | sed 's/^/   /'
  echo "   allowed on BOTH means the env write can run in Actions and you"
  echo "   never paste it. implicitDeny on either means it stays a terminal"
  echo "   command until that grant is added."
fi
echo

cat <<'GUIDE'
== HOW TO READ THIS

Section 1 is the block as it stands. Compare it against section 4 first,
because that is the route most likely to answer.

  SECTION 3 SHOWING {} IS NOT AN EMPTY RESULT.
      CloudTrail deliberately OMITS Lambda environment variables from
      requestParameters, because they routinely carry secrets. So an
      UpdateFunctionConfiguration event proves a config write HAPPENED and
      its timestamp, and can never carry the values. Do not read {} as
      "nothing was set".

  SECTION 4 CARRIES A PRODUCT CODE
      That is the value. It belongs in the block alongside whatever else
      section 1 should hold, in ONE call, because the API replaces.

  SECTION 4 SAYS (not set) EVERYWHERE
      Then no function carries it and the code was never configured, which
      also means the emptied block deleted nothing. Bundle D fulfillment
      resolves its product from ResolveCustomer on the redirect path and
      was already blind on the SNS and scan paths. That is a finding in its
      own right, not a non-answer.

  NEVER GUESS A PRODUCT CODE.
      A wrong one matches no key row, raises nothing, and reports success.
      The authoritative value is what ResolveCustomer returns for a
      subscriber, and it is visible in the Marketplace console against
      prod-kkvurtspreofy (Bundle D) and prod-f5qkfsxlxs4qg (Bundle A).
GUIDE
