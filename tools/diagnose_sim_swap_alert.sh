#!/bin/sh
# Was that port-out alert real, and which carrier strings produced it?
#
# READ-ONLY. It reads CloudWatch and DynamoDB and writes nothing.
#
# WHY IT EXISTS. On 2026-09-16 the monitor sent a CRITICAL alert saying a
# number had been "transferred from T-Mobile USA to T-Mobile USA" -- the same
# carrier on both sides, which is not a port-out under any reading. The
# detector was a raw string comparison of a VENDOR DISPLAY NAME, and the two
# strings that produced it differed in bytes while rendering identically on a
# phone. Nothing on the phone can show you that difference. The log can.
#
# It answers three separate questions, because they have three different
# answers and "the alert was wrong" does not distinguish them:
#
#   A. Did Twilio report an actual SIM change (swapped=True)? That is the
#      independent signal and it is NOT what a port-out alert is built from.
#      If it is True on any recent run, treat the number as compromised
#      regardless of what the carrier strings say.
#   B. What were the two carrier strings, byte for byte? repr() is deliberate:
#      "T-Mobile USA" and "T‑Mobile USA, Inc." look the same in a message
#      and are different strings.
#   C. What is stored as the baseline right now? That is what the NEXT run
#      compares against.
#
# USAGE (the phone number is optional; without it you get every user):
#   sh tools/diagnose_sim_swap_alert.sh
#   sh tools/diagnose_sim_swap_alert.sh +15551234567
#
# The number is an ARGUMENT and is never written into this file. It is personal
# data and this repository is public.
set -u
export AWS_PAGER=""
REGION=us-east-1
FN=relayshield-sim-swap-monitor
GROUP=/aws/lambda/$FN
PHONE="${1:-}"
DAYS="${DAYS:-7}"
SINCE=$(python3 -c "import time,sys;print(int((time.time()-86400*float(sys.argv[1]))*1000))" "$DAYS")

# An empty section reads identically to a query that failed and printed nothing,
# and this repo has paid for that ambiguity before. Say which one it was.
show() {
  out=$(cat)
  if [ -z "$(printf '%s' "$out" | tr -d '[:space:]')" ]; then
    echo "   (no matching lines)"
  else
    printf '%s\n' "$out" | sed 's/^/   /'
  fi
}

echo "== 1. Which account?"
AWS_PROFILE=relayshield aws sts get-caller-identity \
  --query Account --output text --no-cli-pager 2>&1 | sed 's/^/   /'
echo "   (must be 239677749008 -- 620534471984 is the pre-audit account and"
echo "    holds no RelayShield resource, so a read there returns NotFound)"
echo

echo "== 2. Is the deployed code the version with the fixed detector?"
# A fix that has not shipped cannot change anything, and the LastModified is
# the only thing that says which version produced the alert being diagnosed.
AWS_PROFILE=relayshield aws lambda get-function-configuration \
  --function-name "$FN" --region "$REGION" --no-cli-pager \
  --query '[LastModified,State,CodeSize]' --output text 2>&1 | sed 's/^/   /'
echo "   The port-out fix (detect_port_out + MCC/MNC) landed 2026-09-16."
echo "   A LastModified earlier than that means the alert came from the raw"
echo "   string comparison and the log below will NOT carry a network= field."
echo

echo "== 3. A. Did Twilio ever report an actual SIM change? (swapped=True)"
echo "   This is the question that matters for your phone, and it is separate"
echo "   from the carrier-name comparison that fired the alert."
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$SINCE" \
  --filter-pattern '"swapped=True"' \
  --query 'events[].message' --output text 2>&1 | show
echo "   NO LINES HERE IS THE GOOD ANSWER: Twilio saw no SIM/eSIM change."
echo

echo "== 4. B. Every carrier read in the last $DAYS day(s), oldest first"
if [ -n "$PHONE" ]; then
  PATTERN="\"Twilio Lookup $PHONE\""
else
  PATTERN='"Twilio Lookup"'
fi
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$SINCE" \
  --filter-pattern "$PATTERN" \
  --query 'events[].message' --output text 2>&1 | show
echo "   Compare consecutive carrier= values for ONE number. Two spellings of"
echo "   one carrier across runs is the false positive. A different carrier is"
echo "   a real port-out. Lines from before the fix print carrier without"
echo "   repr(), so an invisible difference stays invisible in those."
echo

echo "== 5. Every alert this monitor sent in the last $DAYS day(s)"
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$SINCE" \
  --filter-pattern '"Alert sent"' \
  --query 'events[].message' --output text 2>&1 | show
echo "   alert_type=port_out is the carrier-comparison alert."
echo "   alert_type=sim_swap is Twilio's own swap verdict and is the serious one."
echo

echo "== 6. Errors and refusals, kept separate from the verdicts above"
# A raise BEFORE the lookup (Secrets Manager, KMS decrypt) is a different cause
# with a different fix, and it is invisible in the sections above because those
# only match successful reads.
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$SINCE" \
  --filter-pattern '?"Traceback" ?"AccessDenied" ?"error_code" ?"ResourceNotFound"' \
  --query 'events[].message' --output text 2>&1 | show
echo "   error_code=60606 means Twilio's SIM swap package answered 'not enabled'"
echo "   for that number. The monitor returns None rather than a clean result,"
echo "   which is correct. Twilio approved the US on 2026-09-12, so a US number"
echo "   should no longer produce it and a non-US number still will."
echo

echo "== 7. C. What the NEXT run will compare against"
if [ -n "$PHONE" ]; then
  echo "   (a full-table scan of monitored users; the phone is encrypted at"
  echo "    rest so it cannot be used as a filter here)"
fi
AWS_PROFILE=relayshield aws dynamodb scan \
  --table-name relayshield_users --region "$REGION" --no-cli-pager \
  --filter-expression "attribute_exists(last_known_carrier)" \
  --projection-expression "user_id, last_known_carrier, last_known_network, last_swap_alerted_at" \
  --query 'Items' --output json 2>&1 | show
echo
echo "   last_known_network empty means this record predates the MCC/MNC"
echo "   baseline and the next comparison falls back to the normalised name."
echo "   That is the intended degradation, not a fault."
