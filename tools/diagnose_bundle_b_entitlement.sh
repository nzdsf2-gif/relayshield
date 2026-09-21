#!/bin/sh
# The agreement exists and GetEntitlements returns nothing. Which is it?
# READ ONLY. Writes nothing to AWS.
#
#   AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_entitlement.sh
#   AWS_PROFILE=relayshield sh tools/diagnose_bundle_b_entitlement.sh <agreement-id>
#
# WHERE THIS PICKS UP
# -------------------
# tools/identify_bundle_product_codes.sh asked GetEntitlements for BOTH codes
# ResolveCustomer has returned, filtered to customer fHL5zV6grGn, and got
# nothing for either. So the product code is no longer the only open question,
# and the env var alone cannot clear AWS's audit.
#
# FOUR THINGS PRODUCE THAT EXACT OUTPUT AND THEY HAVE FOUR DIFFERENT FIXES.
#
#   1. THE FILTER, not the data. GetEntitlements filtered by
#      CUSTOMER_IDENTIFIER returns empty when the identifier does not match,
#      and empty is also what "no entitlements at all" looks like. The
#      UNFILTERED call separates them in one request and nothing else does.
#
#   2. THE AGREEMENT IS ON A DIFFERENT PRODUCT than either code. We have the
#      agreement id, so the Agreement Service can be asked directly rather than
#      inferred from a redirect.
#
#   3. THE ENTITLEMENT HAS NOT PROPAGATED. Real, documented, and it is why
#      relayshield_bundle_fulfillment.py carries a comment about AWS sending
#      subscribe-success before GetEntitlements is consistent. But the
#      agreement was accepted 2026-09-19 and this is not minutes later, so it
#      is the least likely of the four and must not be the default assumption.
#
#   4. THE IDENTITY CANNOT READ ENTITLEMENTS and the empty result is a
#      permission answer wearing the shape of a data answer. Section 0 settles
#      that first, because every section below would misread otherwise.
#
# NONE of the four is "the product code is wrong", which is what the previous
# run was testing. That is the finding: a probe that returns the same empty
# answer for four causes has not narrowed anything, and this one is built to
# make each cause produce a DIFFERENT line.

set -u
export AWS_PAGER=""

REGION=us-east-1
ACCOUNT=239677749008
ENTITY=prod-szi2wdww3obry
AGREEMENT="${1:-agmt-29l852u6kqzmjh2me0pglvj9q}"
CUSTOMER=fHL5zV6grGn
CODES="7ws2zmbdyk70tq34pr0pea0s2 cmh79gzztkdtp0dlzbdepa643"

aws_() { command aws --region "$REGION" --no-cli-pager "$@"; }

echo "== 0. Identity, and whether it may read entitlements at all"
if [ -z "${AWS_PROFILE:-}" ]; then
  echo "STOP: AWS_PROFILE is not set. Re-run with AWS_PROFILE=relayshield." >&2
  exit 1
fi
GOT=$(aws_ sts get-caller-identity --query Account --output text 2>&1) || true
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: credentials resolve to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
ARN=$(aws_ sts get-caller-identity --query Arn --output text 2>&1) || ARN="(unknown)"
echo "   account $GOT"
echo "   as      $ARN"
echo "   Simulating the two reads this script depends on, against THIS identity."
echo "   An empty result from an identity that may not read is a permission"
echo "   answer wearing the shape of a data answer, and every section below"
echo "   would misread it."
aws_ iam simulate-principal-policy --policy-source-arn "$ARN" \
  --action-names aws-marketplace:GetEntitlements aws-marketplace:DescribeAgreement \
  --query 'EvaluationResults[].{action:EvalActionName,decision:EvalDecision}' \
  --output table 2>&1 | sed 's/^/   /'
echo "   implicitDeny on GetEntitlements makes every 'no entitlement' below"
echo "   meaningless. Fix that before reading anything else."
echo

echo "== 1. CAUSE 1. GetEntitlements with NO FILTER, per candidate code"
echo "   The previous run filtered on CUSTOMER_IDENTIFIER. A filter that does"
echo "   not match returns exactly what no-entitlements-at-all returns, so the"
echo "   filtered call could never separate them. This one can."
for CODE in $CODES; do
  echo "   -- $CODE"
  OUT=$(aws_ marketplace-entitlement get-entitlements --product-code "$CODE" \
          --query 'Entitlements[].[CustomerIdentifier,Dimension,Value.IntegerValue,ExpirationDate]' \
          --output text 2>&1) || true
  if printf '%s' "$OUT" | grep -qi "error"; then
    echo "      ERROR: $OUT"
  elif [ -z "$OUT" ] || [ "$OUT" = "None" ]; then
    echo "      no entitlements on this product AT ALL, for any customer."
    echo "      So the filter was never the problem for this code, and the"
    echo "      agreement is not on it. Cause 2."
  else
    echo "$OUT" | sed 's/^/      /'
    echo "      ENTITLEMENTS EXIST on this product. Compare the"
    echo "      CustomerIdentifier column against $CUSTOMER: if it differs,"
    echo "      the FILTER was the problem and this IS Bundle B's code."
  fi
done
echo

echo "== 2. CAUSE 2. Which product is the agreement actually on?"
echo "   agreement: $AGREEMENT"
echo "   Asking the Agreement Service directly rather than inferring it from a"
echo "   redirect. This is the one read that names the product without a guess."
OUT=$(aws_ marketplace-agreement describe-agreement --agreement-id "$AGREEMENT" \
        --output json 2>&1) || true
if printf '%s' "$OUT" | grep -qi "Invalid choice\|argument command"; then
  echo "   this AWS CLI does not know the marketplace-agreement service."
  echo "   Upgrade the CLI, or read it in the Marketplace Management Portal:"
  echo "   Agreements, open $AGREEMENT, and note the product it names."
elif printf '%s' "$OUT" | grep -qi "error"; then
  echo "   could not read, verbatim:"
  echo "$OUT" | sed 's/^/   /'
  echo "   AccessDenied here is a fact about the identity. ResourceNotFound"
  echo "   means this account is not a party to that agreement, which would"
  echo "   itself be the finding."
else
  echo "$OUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for k in ("agreementId","status","startTime","endTime","agreementType"):
    if k in d: print("   %-16s %s" % (k, d[k]))
pr=d.get("proposer") or {}; ac=d.get("acceptor") or {}
print("   %-16s %s" % ("proposer", pr.get("accountId","")))
print("   %-16s %s" % ("acceptor", ac.get("accountId","")))
for r in d.get("proposalSummary",{}).get("resources",[]) or []:
    print("   %-16s %s  (%s)" % ("resource", r.get("id",""), r.get("type","")))
' 2>&1 | sed 's/^/   /'
  echo "   READING IT: the resource id is the OFFER or the PRODUCT the"
  echo "   agreement is against. If it names an entity that is not"
  echo "   $ENTITY, the E2E subscription was taken out on a different"
  echo "   product and that is why no entitlement exists on either code."
fi
echo

echo "== 3. What product code does AWS say $ENTITY has?"
echo "   DescribeEntity on the product itself. UNVERIFIED whether a SaaSProduct"
echo "   carries the product code in its details -- the only DescribeEntity"
echo "   capture in this repo is of an Offer. If nothing product-code-shaped"
echo "   comes back, that is a finding about the API, not about the product."
OUT=$(aws_ marketplace-catalog describe-entity --catalog AWSMarketplace \
        --entity-id "$ENTITY" --output json 2>&1) || true
if printf '%s' "$OUT" | grep -qi "error"; then
  echo "   could not read, verbatim:"
  echo "$OUT" | sed 's/^/   /'
  echo "   AccessDenied means relayshield-deployer's catalog grant is on the"
  echo "   GitHub role and not on this one. Read it in the portal instead."
else
  echo "$OUT" | python3 -c '
import json,re,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    # The CLI can prefix a deprecation or credential warning onto stdout, so a
    # whole-stream parse fails on output that CONTAINS valid JSON. Recover from
    # the first brace rather than reporting "unparseable", which says nothing
    # the reader can act on and is what this printed on 2026-09-21.
    i = raw.find("{")
    try:
        d = json.loads(raw[i:]) if i >= 0 else {}
    except Exception:
        print("   could not parse the response. Verbatim, first 400 chars:")
        print("   " + raw.strip()[:400].replace("\n", "\n   "))
        raise SystemExit(0)
det=d.get("DetailsDocument") or d.get("Details") or {}
if isinstance(det,str):
    try: det=json.loads(det)
    except Exception: det={}
flat=json.dumps(det)
hits=sorted(set(re.findall(r"\"([a-z0-9]{25})\"", flat)))
print("   entity   ", d.get("EntityIdentifier",""))
print("   type     ", d.get("EntityType",""))
print("   modified ", d.get("LastModifiedDate",""))
if hits:
    print("   product-code-shaped values found in the details:")
    for h in hits: print("     ", h)
else:
    print("   NO product-code-shaped value in the details document.")
    print("   That is the expected answer if DescribeEntity does not carry it.")
' 2>&1 | sed 's/^/   /'
fi
echo

echo "== 4. THE ONE READ THIS SCRIPT CANNOT DO"
cat <<'EOT'
   The Marketplace Management Portal's product page shows a Product code field,
   seller side, and it is authoritative. If sections 1 to 3 disagree or all come
   back empty, open it and read that field rather than spending another probe:

     AWS Marketplace Management Portal -> SaaS products ->
     RelayShield - Attack Surface & Supply Chain API -> Product code

   A value there that matches NEITHER candidate means the two codes the
   fulfillment log recorded belong to something else entirely, and the
   subscription was taken out on a different product.
EOT
echo
echo "== DONE. Nothing above wrote to AWS."
