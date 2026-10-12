#!/bin/sh
# Show, and optionally change, the EventBridge schedule of the SIM swap monitor.
#
#   AWS_PROFILE=relayshield sh tools/set_sim_swap_monitor_schedule.sh            # read only
#   AWS_PROFILE=relayshield sh tools/set_sim_swap_monitor_schedule.sh --apply    # rate(4 hours)
#   NEW='rate(6 hours)' AWS_PROFILE=relayshield sh tools/set_sim_swap_monitor_schedule.sh --apply
#
# WHY. relayshield_sim_swap_monitor.py documents `rate(4 hours)`, and the rule on the
# account was rate(1 hour), measured 2026-10-11. Every extra run is one paid Twilio
# lookup per enrolled number, so hourly is six times the cost of four-hourly: about
# 168 lookups a day at 7 enrolled numbers against about 42. Nobody recorded who set
# it, and Andrew confirmed on 2026-10-11 that hourly detection was never promised.
#
# AN EVENTBRIDGE SCHEDULE IS AWS STATE AND LIVES IN NO FILE, so this change leaves no
# commit. CLAUDE.md records it for exactly that reason.
#
# put-rule REPLACES the rule's definition, so this reads the current description,
# role and state first and passes them back, then lists the targets afterward to show
# the function is still attached. The function is not touched and nothing is deleted.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
RULE="${RULE:-relayshield-sim-swap-monitor-schedule}"
NEW="${NEW:-rate(4 hours)}"
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was changed." >&2
  exit 1
fi

echo "== rule $RULE, now"
aws events describe-rule --name "$RULE" --query '{Name:Name,Schedule:ScheduleExpression,State:State,Description:Description,Role:RoleArn}' --output table || exit 1
echo "-- targets"
aws events list-targets-by-rule --rule "$RULE" --query 'Targets[].Arn' --output text

if [ "$1" != "--apply" ]; then
  echo
  echo "DRY RUN. Would set the schedule to: $NEW"
  echo "Re-run with --apply to change it."
  exit 0
fi

DESC=$(aws events describe-rule --name "$RULE" --query Description --output text)
ROLE=$(aws events describe-rule --name "$RULE" --query RoleArn --output text)
set -- --name "$RULE" --schedule-expression "$NEW" --state ENABLED
[ -n "$DESC" ] && [ "$DESC" != "None" ] && set -- "$@" --description "$DESC"
[ -n "$ROLE" ] && [ "$ROLE" != "None" ] && set -- "$@" --role-arn "$ROLE"

echo
echo "== applying: $NEW"
aws events put-rule "$@" --query RuleArn --output text || { echo "put-rule failed; nothing else was changed." >&2; exit 1; }

echo
echo "== rule $RULE, after"
aws events describe-rule --name "$RULE" --query '{Schedule:ScheduleExpression,State:State}' --output table
echo "-- targets (must still list the monitor)"
aws events list-targets-by-rule --rule "$RULE" --query 'Targets[].Arn' --output text
