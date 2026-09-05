#!/bin/sh
# Why did /v1/mpp answer with relayshield-api's 404? Read-only.
#
#   sh tools/diagnose_mpp_routes.sh
#
# WHY THIS EXISTS
# ---------------
# create_mpp_settlement_lambda.sh reported both routes "wired to
# relayshield-mpp-settlement", deployed the stage, and then step 8 got:
#
#     {"ok": false, "error": "unknown endpoint: /v1/mpp"}
#
# That string appears in exactly ONE file in this repo -- relayshield_api.py --
# and relayshield_api.py is NOT in the MPP deployment package. The MPP handler's
# own miss returns {"error": "Not found"}. So the request was answered by
# relayshield-api and never reached the function the script had just created.
#
# The script asserted the ACTION IT TOOK ("wired to"), never the OUTCOME. That is
# the same defect as the 402 that quoted $0.25: a step that reports success
# because the API call returned 200, not because the thing is true.
#
# FOUR CANDIDATE CAUSES, DIFFERENT FIXES, AND GUESSING IS EXPENSIVE
# -----------------------------------------------------------------
#   A. the method exists but its integration URI names the wrong function
#   B. no method on the explicit resource for that verb, so a greedy
#      /{proxy+} catches the request and hands it to relayshield-api
#   C. the resources exist but the STAGE was never redeployed with them
#      (or was deployed to a different stage), so prod still serves the old map
#   D. the resource ids the script wired are not the ids on the path we tested
#      -- a duplicate /v1/mpp elsewhere in the tree
#
# Every command below is a read. Nothing here changes anything.

set -eu

PROFILE=relayshield
REGION=us-east-1
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-mpp-settlement

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Account -- must be 239677749008"
aws sts get-caller-identity --query Account --output text
echo

echo "== 2. Does the function exist, and what is its ENTRYPOINT?"
# A function whose --handler names the wrong module runs someone else's code and
# looks perfectly healthy from the outside.
aws lambda get-function-configuration --function-name "$FUNC" \
  --query '{handler:Handler,runtime:Runtime,modified:LastModified,size:CodeSize}' \
  --output table 2>/dev/null || echo "   $FUNC DOES NOT EXIST"
echo

echo "== 3. Every gateway resource whose path mentions mpp"
# Cause D shows up here as more than one row per path.
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'mpp')].[id,path]" --output text | sort -k2
echo

echo "== 4. For each of those, which METHODS exist and which FUNCTION do they call?"
# This is the question the create script never asked. Causes A and B both
# resolve here, and they look nothing alike:
#   A -> a uri naming some other function
#   B -> "(no methods)" on the resource, so the proxy wins
for ROW in $(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
               --query "items[?contains(path,'mpp')].[id,path]" --output text \
             | awk '{print $1 "=" $2}'); do
  RID=${ROW%%=*}
  RPATH=${ROW#*=}
  echo "   $RPATH  ($RID)"
  METHODS=$(aws apigateway get-resource --rest-api-id "$API_ID" --resource-id "$RID" \
              --query 'resourceMethods' --output json 2>/dev/null || echo '{}')
  if [ "$METHODS" = "{}" ] || [ "$METHODS" = "null" ]; then
    echo "       (no methods)  <-- cause B: a greedy proxy will answer this path"
    continue
  fi
  for M in $(echo "$METHODS" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin) or {}))"); do
    URI=$(aws apigateway get-integration --rest-api-id "$API_ID" --resource-id "$RID" \
            --http-method "$M" --query 'uri' --output text 2>/dev/null || echo "(none)")
    # The function name is the last :function:NAME/invocations segment.
    TARGET=$(printf '%s' "$URI" | sed -n 's#.*:function:\([^/]*\)/invocations#\1#p')
    [ -n "$TARGET" ] || TARGET="(not a lambda integration: $URI)"
    if [ "$TARGET" = "$FUNC" ]; then
      echo "       $M -> $TARGET   OK"
    else
      echo "       $M -> $TARGET   <-- cause A: WRONG FUNCTION"
    fi
  done
done
echo

echo "== 5. Is there a greedy proxy that would catch /v1/mpp?"
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'{proxy+}')].[id,path]" --output text | sort -k2
echo "   An EXPLICIT resource beats a greedy proxy -- but only if that resource"
echo "   has a method for the verb being used. Read this next to step 4."
echo

echo "== 6. When was the $STAGE stage last deployed, and does that predate the resources?"
# Cause C. A gateway change is invisible until the stage is redeployed, and a
# console showing the routes says nothing about what prod is serving.
DEPID=$(aws apigateway get-stage --rest-api-id "$API_ID" --stage-name "$STAGE" \
          --query 'deploymentId' --output text)
echo "   stage $STAGE is serving deployment $DEPID"
aws apigateway get-deployment --rest-api-id "$API_ID" --deployment-id "$DEPID" \
  --query '{created:createdDate,description:description}' --output table
echo "   Newest three deployments on this API:"
aws apigateway get-deployments --rest-api-id "$API_ID" \
  --query 'reverse(sort_by(items,&createdDate))[:3].[id,createdDate,description]' \
  --output text
echo

echo "== 7. Ask the function DIRECTLY, with the gateway taken out of the path"
# If this returns the descriptor, the function is fine and the whole problem is
# routing. If it returns relayshield-api's 'unknown endpoint', the handler
# entrypoint is wrong -- step 2 will already have shown that.
aws lambda invoke --function-name "$FUNC" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"path":"/v1/mpp","httpMethod":"GET"}' \
  /tmp/mpp_direct.json --query 'StatusCode' --output text >/dev/null 2>&1 \
  && head -c 400 /tmp/mpp_direct.json \
  || echo "   (direct invoke failed -- see the error above)"
echo
echo

echo "HOW TO READ THIS"
echo "  Step 4 names a wrong function      -> cause A. Re-put the integration."
echo "  Step 4 says (no methods)           -> cause B. put-method never landed."
echo "  Step 4 is clean but step 6's       -> cause C. Redeploy the stage:"
echo "    deployment predates the resource      aws apigateway create-deployment \\"
echo "                                            --rest-api-id $API_ID --stage-name $STAGE"
echo "  Step 3 lists a path twice          -> cause D. Two resources, one path."
echo "  Step 2 shows the wrong handler     -> not a routing bug at all."
