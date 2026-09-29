#!/bin/sh
# relayshield-weekly-metrics runs under the shared relayshield-breach-check-
# role-1sapnwdl role and, as of 2026-09-28, its new _unique_indicators()
# raises on every invocation:
#
#   AccessDeniedException ... dynamodb:Scan ... table/relayshield_intel_first_seen
#   ... assumed-role/relayshield-breach-check-role-1sapnwdl/relayshield-weekly-metrics
#
# tools/setup_first_seen.sh already granted relayshield-intel-monitor -- the
# SAME shared role -- PutItem on this table, via an inline policy named
# relayshield-first-seen-write. That grant is WRITE ONLY. Nothing has ever
# granted READ on this table to this role, so a Scan from ANY function
# running under it (not just weekly-metrics) was always going to fail.
#
#   sh tools/grant_weekly_metrics_first_seen_scan.sh
#
# READ-MERGE-WRITE, DELIBERATELY. put-role-policy REPLACES the named policy's
# entire document -- it does not merge -- exactly like Lambda's
# update-function-configuration --environment replacing the whole env block
# rather than merging it, which this repo has already been burned by once.
# Writing a Scan-only document under the relayshield-first-seen-write name
# would silently DELETE the PutItem grant the intel monitor depends on. So
# this reads whatever Actions already exist under that policy name first and
# writes back the union, never a replacement.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_intel_first_seen
FUNC=relayshield-weekly-metrics
POLICY=relayshield-first-seen-write

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT." >&2
  echo "Nothing has been changed. Fix the profile in ~/.aws/config first." >&2
  exit 1
fi
echo "   $GOT  (correct)"

echo
echo "== 2. Which role does $FUNC run as?"
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" --query Role --output text)
ROLE=${ROLE_ARN##*/}
echo "   $ROLE"

echo
echo "== 3. Does any policy on $ROLE already grant Scan on $TABLE?"
FOUND_POLICY=""
FOUND_IS_MANAGED=0

for P in $(aws iam list-role-policies --role-name "$ROLE" --query 'PolicyNames[]' --output text); do
  BODY=$(aws iam get-role-policy --role-name "$ROLE" --policy-name "$P" --query 'PolicyDocument' --output json 2>/dev/null || echo "")
  case "$BODY" in
    *"$TABLE"*)
      FOUND_POLICY="$P"
      echo "   found inline policy $P referencing $TABLE:"
      printf '%s\n' "$BODY" | grep -iE '"Action"|"Scan"|"PutItem"|"GetItem"|"Query"' | sed 's/^/     /'
      case "$BODY" in
        *'"dynamodb:Scan"'*|*'"dynamodb:*"'*)
          echo "   -- already includes Scan. Nothing to do."
          echo
          echo "If the function is STILL denied, this isn't the cause -- paste the new"
          echo "CloudWatch traceback rather than assuming this script's job."
          exit 0
          ;;
      esac
      ;;
  esac
  [ -n "$FOUND_POLICY" ] && break
done

if [ -z "$FOUND_POLICY" ]; then
  echo "   no inline policy on $ROLE references $TABLE -- checking managed policies"
  for ARN in $(aws iam list-attached-role-policies --role-name "$ROLE" --query 'AttachedPolicies[].PolicyArn' --output text); do
    VID=$(aws iam get-policy --policy-arn "$ARN" --query 'Policy.DefaultVersionId' --output text)
    BODY=$(aws iam get-policy-version --policy-arn "$ARN" --version-id "$VID" --query 'PolicyVersion.Document' --output json 2>/dev/null || echo "")
    case "$BODY" in
      *"$TABLE"*)
        FOUND_POLICY="$ARN"
        FOUND_IS_MANAGED=1
        echo "   found managed policy $ARN referencing $TABLE:"
        printf '%s\n' "$BODY" | grep -iE '"Action"|"Scan"|"PutItem"|"GetItem"|"Query"' | sed 's/^/     /'
        case "$BODY" in
          *'"dynamodb:Scan"'*|*'"dynamodb:*"'*)
            echo "   -- already includes Scan. Nothing to do."
            exit 0
            ;;
        esac
        ;;
    esac
    [ -n "$FOUND_POLICY" ] && break
  done
fi

echo
if [ -n "$FOUND_POLICY" ] && [ "$FOUND_IS_MANAGED" = "0" ]; then
  echo "== 4. Extending inline policy $FOUND_POLICY: adding dynamodb:Scan, keeping every existing action"
  CUR=$(aws iam get-role-policy --role-name "$ROLE" --policy-name "$FOUND_POLICY" --query 'PolicyDocument.Statement[0].Action' --output json)
  case "$CUR" in
    \[*) ACTIONS=$(printf '%s' "$CUR" | tr -d '[]"' | tr ',' '\n' | sed '/^[[:space:]]*$/d') ;;
    *)   ACTIONS=$(printf '%s' "$CUR" | tr -d '"') ;;
  esac
  NEW_LIST=""
  HAS_SCAN=0
  for A in $ACTIONS; do
    [ "$A" = "dynamodb:Scan" ] && HAS_SCAN=1
    NEW_LIST="${NEW_LIST}\"$A\","
  done
  if [ "$HAS_SCAN" = "1" ]; then
    echo "   (Scan already present on re-read -- nothing to do)"
    exit 0
  fi
  NEW_LIST="${NEW_LIST}\"dynamodb:Scan\""
  DOC="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[${NEW_LIST}],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"}]}"
  echo "   new document: $DOC"
  aws iam put-role-policy --role-name "$ROLE" --policy-name "$FOUND_POLICY" --policy-document "$DOC"
  echo "   updated $FOUND_POLICY"
elif [ -n "$FOUND_POLICY" ] && [ "$FOUND_IS_MANAGED" = "1" ]; then
  echo "== 4. Extending managed policy $FOUND_POLICY: adding dynamodb:Scan, keeping every existing action"
  # Same read-merge-write as the inline branch, and for the identical reason:
  # create-policy-version --set-as-default REPLACES the policy's document, it
  # does not merge, so writing a Scan-only doc here would delete the PutItem
  # grant relayshield-intel-monitor depends on.
  VID=$(aws iam get-policy --policy-arn "$FOUND_POLICY" --query 'Policy.DefaultVersionId' --output text)
  CUR=$(aws iam get-policy-version --policy-arn "$FOUND_POLICY" --version-id "$VID" \
          --query 'PolicyVersion.Document.Statement[0].Action' --output json)
  RES=$(aws iam get-policy-version --policy-arn "$FOUND_POLICY" --version-id "$VID" \
          --query 'PolicyVersion.Document.Statement[0].Resource' --output json)
  case "$CUR" in
    \[*) ACTIONS=$(printf '%s' "$CUR" | tr -d '[]"' | tr ',' '\n' | sed '/^[[:space:]]*$/d') ;;
    *)   ACTIONS=$(printf '%s' "$CUR" | tr -d '"') ;;
  esac
  NEW_LIST=""
  HAS_SCAN=0
  for A in $ACTIONS; do
    [ "$A" = "dynamodb:Scan" ] && HAS_SCAN=1
    NEW_LIST="${NEW_LIST}\"$A\","
  done
  if [ "$HAS_SCAN" = "1" ]; then
    echo "   (Scan already present on re-read -- nothing to do)"
    exit 0
  fi
  NEW_LIST="${NEW_LIST}\"dynamodb:Scan\""
  DOC="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[${NEW_LIST}],\"Resource\":${RES}}]}"
  echo "   new document: $DOC"
  # A managed policy keeps at most 5 versions. Prune the oldest non-default
  # one first, or a role that has been through this once already starts
  # refusing every subsequent grant with LimitExceeded.
  COUNT=$(aws iam list-policy-versions --policy-arn "$FOUND_POLICY" --query 'length(Versions)' --output text)
  if [ "$COUNT" -ge 5 ]; then
    OLD=$(aws iam list-policy-versions --policy-arn "$FOUND_POLICY" \
            --query 'sort_by(Versions[?IsDefaultVersion==`false`], &CreateDate)[0].VersionId' --output text)
    if [ -n "$OLD" ] && [ "$OLD" != "None" ]; then
      aws iam delete-policy-version --policy-arn "$FOUND_POLICY" --version-id "$OLD"
      echo "   pruned oldest non-default version $OLD (5-version cap)"
    fi
  fi
  aws iam create-policy-version --policy-arn "$FOUND_POLICY" --policy-document "$DOC" --set-as-default \
    --query 'PolicyVersion.VersionId' --output text
  echo "   new default version created on $FOUND_POLICY"
  echo -n "   verify -- new default version's Action list: "
  NEWVID=$(aws iam get-policy --policy-arn "$FOUND_POLICY" --query 'Policy.DefaultVersionId' --output text)
  aws iam get-policy-version --policy-arn "$FOUND_POLICY" --version-id "$NEWVID" \
    --query 'PolicyVersion.Document.Statement[0].Action' --output text
else
  echo "== 4. No existing policy references $TABLE at all. Granting fresh read access"
  echo "      (GetItem, Query, Scan -- this role has never had any of the three)."
  NEWPOLICY=relayshield-first-seen-read
  DOC="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:Query\",\"dynamodb:Scan\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"}]}"
  set +e
  if aws iam put-role-policy --role-name "$ROLE" --policy-name "$NEWPOLICY" --policy-document "$DOC" 2>/tmp/rs_iam_err; then
    echo "   attached as inline policy $NEWPOLICY"
  else
    echo "   inline failed (the role's inline budget is very likely spent -- 26 policies, ~10.1KB of 10.24KB as of the last snapshot):"
    sed 's/^/     /' /tmp/rs_iam_err
    echo "   falling back to a customer-managed policy, which has its own separate budget"
    ARN="arn:aws:iam::${ACCOUNT}:policy/${NEWPOLICY}"
    if aws iam get-policy --policy-arn "$ARN" >/dev/null 2>&1; then
      aws iam create-policy-version --policy-arn "$ARN" --policy-document "$DOC" --set-as-default --query 'PolicyVersion.VersionId' --output text
    else
      aws iam create-policy --policy-name "$NEWPOLICY" --policy-document "$DOC" --query 'Policy.Arn' --output text
    fi
    if ! aws iam attach-role-policy --role-name "$ROLE" --policy-arn "$ARN" 2>/tmp/rs_iam_err; then
      sed 's/^/     /' /tmp/rs_iam_err
      echo
      echo "!! NOT GRANTED. Both the inline and managed-policy budgets on $ROLE appear spent"
      echo "!! (11 of 10 managed slots as of the last snapshot). The real fix at that point"
      echo "!! is moving $FUNC onto its own role, the way relayshield-intel-feed already was:"
      echo "!!   AWS_PROFILE=$PROFILE python3 tools/iam_split_roles.py --from-snapshot <snapshot> --only $FUNC --apply"
      rm -f /tmp/rs_iam_err
      exit 1
    fi
    echo "   attached $ARN to $ROLE"
  fi
  rm -f /tmp/rs_iam_err
  set -e
fi

echo
echo "Done. Re-invoke to confirm -- IAM changes can take a few seconds to propagate,"
echo "so if this immediately fails again with the same AccessDeniedException, wait"
echo "30s and try once more before treating it as a real second problem:"
echo "  AWS_PROFILE=$PROFILE aws lambda invoke --no-cli-pager --function-name $FUNC /tmp/weekly_metrics_out.json"
echo "  cat /tmp/weekly_metrics_out.json"
