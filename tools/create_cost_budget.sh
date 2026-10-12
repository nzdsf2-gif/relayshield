#!/bin/sh
# Create one monthly AWS cost budget with email alerts. Dry run by default.
#
#   AWS_PROFILE=relayshield sh tools/create_cost_budget.sh                  # prints what it would create
#   AMOUNT=75 AWS_PROFILE=relayshield sh tools/create_cost_budget.sh --apply
#   Run again with a different AMOUNT to CHANGE an existing budget's limit (alerts untouched).
#
# WHY. tools/wafr_evidence.sh found NO budgets on the account (one cost anomaly monitor
# exists). The Well-Architected cost questions ask for budgets, forecasts and
# notifications, and "none" is an honest but weak answer to all three.
#
# WHAT THIS DOES NOT COVER, AND IT IS THE PART THAT HURT. AWS Budgets sees AWS charges
# only. The spend that has actually surprised this business is VENDOR spend: Twilio
# lookups and the shared VirusTotal key. Neither appears here. A Twilio usage trigger
# (Console > Monitor > Usage > Triggers) and the existing VT budget in the API are the
# controls for those, and this budget must not be read as covering them.
#
# AMOUNT is a guess at a sensible ceiling: Cost Explorer returned near-zero figures for
# the last month (free tier and credits), so there is no baseline to derive one from.
# Raise or lower it once a real month is on record. EMAIL defaults to the mailbox this
# repo already trusts for alerts, because Cloudflare Email Routing has silently dropped
# mail to the relayshield.net addresses before.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
NAME="${NAME:-relayshield-monthly-cost}"
AMOUNT="${AMOUNT:-10}"
EMAIL="${EMAIL:-relayshieldadmin@gmail.com}"
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was created." >&2
  exit 1
fi

if aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$NAME" >/dev/null 2>&1; then
  CUR=$(aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$NAME" --query 'Budget.BudgetLimit.Amount' --output text)
  echo "budget '$NAME' already exists, limit USD $CUR per month."
  if python3 -c "import sys; sys.exit(0 if float(sys.argv[1])==float(sys.argv[2]) else 1)" "$CUR" "$AMOUNT"; then
    echo "Already at USD $AMOUNT. Nothing to do."
    exit 0
  fi
  echo "Would change the limit to USD $AMOUNT. The existing alerts are left exactly as they are."
  if [ "$1" != "--apply" ]; then
    echo
    echo "DRY RUN. Re-run with --apply to change it."
    exit 0
  fi
  # update-budget replaces the budget definition and does not touch its notifications.
  UPD=$(python3 -c "
import json,sys
print(json.dumps({'BudgetName':sys.argv[1],'BudgetLimit':{'Amount':sys.argv[2],'Unit':'USD'},'TimeUnit':'MONTHLY','BudgetType':'COST'}))" "$NAME" "$AMOUNT")
  aws budgets update-budget --account-id "$ACCOUNT" --new-budget "$UPD" && echo "limit updated."
  aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$NAME" --query 'Budget.[BudgetName,BudgetLimit.Amount,BudgetLimit.Unit,TimeUnit]' --output text
  exit 0
fi

BUDGET=$(python3 -c "
import json,sys
print(json.dumps({'BudgetName':sys.argv[1],'BudgetLimit':{'Amount':sys.argv[2],'Unit':'USD'},'TimeUnit':'MONTHLY','BudgetType':'COST'}))" "$NAME" "$AMOUNT")
NOTIF=$(python3 -c "
import json,sys
sub=[{'SubscriptionType':'EMAIL','Address':sys.argv[1]}]
print(json.dumps([
 {'Notification':{'NotificationType':'ACTUAL','ComparisonOperator':'GREATER_THAN','Threshold':80,'ThresholdType':'PERCENTAGE'},'Subscribers':sub},
 {'Notification':{'NotificationType':'FORECASTED','ComparisonOperator':'GREATER_THAN','Threshold':100,'ThresholdType':'PERCENTAGE'},'Subscribers':sub}]))" "$EMAIL")

echo "budget: $NAME, USD $AMOUNT per month"
echo "alerts: at 80% of actual spend, and when the forecast passes 100%, to $EMAIL"
echo "(AWS charges only. It does not see Twilio or VirusTotal.)"
if [ "$1" != "--apply" ]; then
  echo
  echo "DRY RUN. Re-run with --apply to create it."
  exit 0
fi
aws budgets create-budget --account-id "$ACCOUNT" --budget "$BUDGET" --notifications-with-subscribers "$NOTIF" && echo "created."
aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$NAME" --query 'Budget.[BudgetName,BudgetLimit.Amount,BudgetLimit.Unit,TimeUnit]' --output text
