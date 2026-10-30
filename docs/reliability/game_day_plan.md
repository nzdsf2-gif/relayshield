# Game day plan (resilience tests)

**STATUS: DRAFT, written 2026-10-29 by Claude. NO GAME DAY HAS BEEN HELD.** Nothing here may be cited as a test result
until a dated record exists in section 5. Covers WAFR Reliability: *Test resiliency using chaos engineering*, *Conduct game
days regularly*, *Test disaster recovery implementation*, and *Integrate resiliency testing as part of your deployment*
(partly: the rollback drill exercises the deploy path).

**Cadence (PROPOSAL):** quarterly, one hour, owner present. Every scenario has an abort condition; stop and restore on it.
**Where:** production is the only environment. So every scenario is small, reversible and run at a quiet hour.

## Scenarios

### 1. Restore a table from point-in-time recovery (REL 9, REL 13)
Restore one protected table to a `_restoretest` copy (command in `recovery_objectives_and_dr_plan.md` section 4). Compare item
counts with the original, read five items, delete the copy.
- **Pass:** restore completes, counts within the writes made since the restore time, copy deleted.
- **Abort:** nothing to abort; it creates a new table and changes no existing one.
- **Evidence to keep:** the restore command output, the two item counts, the time taken (this is the measured RTO).

### 2. Bulkhead test: starve a background function, prove the API is unaffected (REL 10)
The point of reserved concurrency (`tools/wafr_hardening.py --step concurrency`) is that a runaway background job cannot
starve the public API. Prove it. Pick one low-value scheduled function, set its reserved concurrency to 0 (it can then run
nowhere), watch the public API for ten minutes, restore the setting.
- **Pass:** `relayshield-api` error rate and throttles stay flat on the `relayshield-service-health` dashboard.
- **Abort:** any `relayshield-api` alarm fires, or customers are affected: restore concurrency immediately.
- **Needs first:** reserved concurrency applied on `relayshield-api`, otherwise this test proves nothing.

### 3. Rollback drill (REL 8)
Dispatch `rollback_lambda.yml` for `relayshield-api` with `version = previous`, confirm the import probe passes, then deploy
forward again.
- **Pass:** workflow green, `/v1` endpoints answer, the alias `live` matches the restored version, then the forward deploy is green.
- **Abort:** the probe step fails; the workflow leaves the code restored but the alias unmoved, so redeploy `main`.
- **Needs first:** at least two published versions of the function, which exist only after deploys following the IAM grant.

### 4. Alarm path test (REL 6, REL 11 "send notifications when events impact availability")
Force one of the new alarms into ALARM with `aws cloudwatch set-alarm-state` and confirm the notification arrives where
Andrew will actually see it. An alarm whose email goes unread is not a control.
- **Pass:** notification received within five minutes; state returns to OK on its own.

### 5. Missing-route check (REL 13)
List the API Gateway routes and confirm each is created by a script in `tools/create_*.sh`. Any route that is not scripted
cannot be rebuilt from the repository: file it as a gap.

## 5. Record of game days (append, never edit)

| Date | Scenarios run | Result | Measured restore time | Follow-ups |
|---|---|---|---|---|
| (none yet) | | | | |
