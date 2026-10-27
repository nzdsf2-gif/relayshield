# WAFR / FTR gap plan, 2026-10-27

Solution `soln-aicwx4eiyofnm`, product `prod-kkvurtspreofy`. Workload "RelayShield API", account 239677749008.

## 1. Do we have to clear all 37 High risks? No, probably not. Three pillars, not six.

AWS's Partner Central builder guide ("Request Foundational Technical Review", `requesting-ftr`), as reported by web search:
the WAFR report must be **less than a year old**, show **zero high-risk issues in Security, Operational Excellence and Reliability**,
name the partner solution in the workload name or description, name the reviewer, and be a PDF **under 3 MB**. A failed submission can be
fixed and resubmitted as many times as needed. Performance, Cost and Sustainability are not part of that gate.

**UNVERIFIED, and it matters.** `docs.aws.amazon.com` is blocked from this container, so I could not read the guide itself. The
pillar rule comes from search summaries of it. One third-party tool also says only *open* High risks count, so a risk you fix and
re-tick no longer counts; that is not in AWS's text. Before spending effort, open the FTR section in Partner Central and confirm
the "zero HRIs in SEC, OPS, REL" line. If it is there, the target shrinks from 37 to whatever those three pillars hold.

The FTR also has an alternative evidence path (a SOC 2 report). Not realistic for us; noted so it is not forgotten.

## 2. The number I need from Andrew

The 37 High / 15 Medium split by pillar is not in the repo. **ANDREW READS THIS:** Well-Architected Tool, workload "RelayShield API",
Overview. Send the High count shown for each of OPS, SEC, REL (PERF/COST/SUS can be ignored for the gate).
Also still unknown from 2026-10-12: which one question was unanswered.

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
