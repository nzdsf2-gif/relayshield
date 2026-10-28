# WAFR / FTR gap plan, 2026-10-27

Solution `soln-aicwx4eiyofnm`, product `prod-kkvurtspreofy`. Workload "RelayShield API", account 239677749008.

## 1. Do we have to clear all 37 High risks? No. Only the 24 in Security, Operational Excellence and Reliability.

**CONFIRMED 2026-10-28 from AWS's own FTR page, pasted by Andrew.** For a WAFR report the FTR requires:

1. Report is less than 1 year old.
2. **Zero high-risk issues (HRIs) in the Security, Operational Excellence and Reliability pillars.**
3. The specific partner solution is referenced in the workload name or description.
4. The reviewer's full name and email address are in the reviewer owner field.
5. The WAFR is done in the AWS Well-Architected Tool (self-service is allowed).

Performance, Cost and Sustainability do not gate. Still UNVERIFIED from AWS's text: the PDF size limit (3 MB, from search) and
whether only *open* HRIs count (a third-party checker says so).

**Two items to check now, both free:** the workload name or description must name the solution (`RS Agentic Attack Surface API`
or the listing name), and the reviewer owner field must hold Andrew's full name and email. Either missing fails the report
regardless of the risk count.

## 2. The per-pillar split (read from Andrew's console chart, 2026-10-28)

| Pillar | High | Medium | Gates the FTR? |
|---|---|---|---|
| Operational Excellence | 5 | 5 | yes |
| Security | 9 | 1 | yes |
| Reliability | 10 | 2 | yes |
| Performance Efficiency | 4 | 1 | no |
| Cost Optimization | 9 | 0 | no |
| Sustainability | 0 | 6 | no |

Total 37 High, 15 Medium, matching the earlier figure. **If the three-pillar rule is confirmed, the target is 24 High risks
(5 OPS + 9 SEC + 10 REL), not 37.** The 13 in Performance and Cost need no work for the gate. Still unknown: the one question left unanswered on 2026-10-12.

## 3. Why "fix" means "do it", not "tick it"

A High risk disappears when the practice is ticked. Ticking without the thing existing is what fails an FTR review (the 2026-10-18
check found the Bundle B listing claiming per-function IAM roles that did not exist). So every gap below is closed by building the
control, then re-ticking with evidence in the Notes.

## 4. Done this session (committed, tested)

* **Tests now run in CI (OPS, REL 8).** `.github/workflows/tests.yml` runs `tools/run_test_suite.py` on every push to main and every
  pull request, with no AWS credentials. 104 test files: 91 pass, 13 already failed and are pinned in `tests_known_failing.txt`
  (the list may only shrink). Any new failing file turns the job red. Proven by mutation: a new failing file exits 1; a passing
  file listed as known prints a notice. **Not yet seen running on GitHub**; the first push to main is its first real run.
  After that run, REL 8's "tests are not yet run in CI" Note can change, and its practice may be re-ticked once a run is green.

* **Reliability hardening tool (REL 1, 6, 7, 10; written 2026-10-28, NOT run against AWS).** `tools/wafr_hardening.py`, numbers in
  `tools/wafr_hardening_spec.json`. Three steps, dry run by default: reserved concurrency (api 100, bundle-fulfillment 10,
  stripe-webhook 10; never overwrites a different value; respects AWS's 100-unreserved floor), three alarms on `relayshield-api`
  (errors, throttles, concurrency share) sent to the same place the existing Lambda error alarms go, and 90-day retention on log
  groups that have none. 13 tests; requests checked against the real lambda, cloudwatch and logs service models with botocore
  Stubber; six planted bugs each turned the suite red.

## 5. Remaining gaps, from the repo's own records (what is known, not what is guessed)

| Pillar | Gap | State | Who |
|---|---|---|---|
| REL | Reserved concurrency (quota raised to 1,000 on 2026-10-12) | no tool yet | I can build a dry-run-default script |
| REL | Alarm on `relayshield-api` errors and throttles | no tool yet | I can build it |
| REL | Lambda versions + alias for rollback | none exist | I can build it; deploy workflow change |
| REL | PITR on customer-state tables | `tools/protect_dynamodb_tables.sh` exists, run status unknown | Andrew runs it |
| REL | AWS Backup plan, DLQ, tracing, API Gateway throttling/logging, load test, DR plan | not started | mixed |
| REL | Log retention on 8 groups with none | not started | I can build it |
| SEC | One IAM role per Lambda (41 functions share one, 26 inline policies) | tooling exists (`iam_role_split.md`), not applied | Andrew runs, in stages |
| SEC | GuardDuty, WAF: none enabled | not started | Andrew decides (cost) |
| OPS | `relayshield_weekly_metrics.py` has no CI deploy path or drift check | open | I can do it, but needs an IAM grant first |
| OPS | Tag standardisation | not started | I can build the script |
| OPS / SEC | The saved answers for these two pillars were given in chat and never saved | gap | send me the question numbers still High |

## 6. Recommended order (mine, overrule freely)

1. Andrew sends the per-pillar High counts and confirms the "zero HRIs in SEC/OPS/REL" line in Partner Central. About ten minutes.
2. I build, in one session, the three cheapest AWS-write tools: reserved concurrency, the API alarm, log retention. Each is
   dry-run by default and checked against the real boto3 service models (botocore Stubber). Andrew runs each once.
3. IAM role split, in stages. This is the largest SEC finding and the slowest, so start it early.
4. Re-tick, re-word Notes, save a milestone, generate the PDF under 3 MB, request validation again.
5. Email Dave Shapiro only after the FTR passes (Andrew's instruction, 2026-10-26).

## 7. Status 2026-10-28 night
REL tool dry run on Andrew's Mac: clean, nothing applied. Order of work and the full TODO list: `docs/claude_memory/LOG_CURRENT.md`, section "WHERE 2026-10-28 LEFT THINGS".
