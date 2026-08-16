# RelayShield Sentinel solution content

Analytic Rules and Hunting Queries for the RelayShield threat intelligence feed, staged here for
the PR into `Solutions/RelayShield/` in `Azure/Azure-Sentinel` (MS-1).

Kept in this repo, not only in the fork, so the content is versioned with the product it describes
and does not live solely in a scratch clone.

## What is here

| File | Kind | Needs a customer log source? |
|---|---|---|
| `Analytic Rules/RelayShieldMultiFamilyConvergence.yaml` | Scheduled, High | Yes, `CommonSecurityLog` |
| `Analytic Rules/RelayShieldFeedIngestionStopped.yaml` | Scheduled, Medium | No |
| `Hunting Queries/RelayShieldFamilyPrevalence.yaml` | Hunt | No |
| `Hunting Queries/RelayShieldEmergingFamilies.yaml` | Hunt | No |
| `Hunting Queries/RelayShieldCredentialTheftFamilies.yaml` | Hunt | Yes, `CommonSecurityLog` |

Three of the five work the moment the TAXII connector is configured, with no other data source.
That matters for a Content Hub listing: a solution whose content only works for CEF customers
demos as an empty screen for everyone else.

## Why these five and not the obvious ones

The Threat Intelligence solutions in this repo already ship **52 analytic rule templates** of the
form `<Entity>Entity_<LogSource>`, covering IP, domain, URL, file-hash and email indicators against
roughly twenty log sources. "Match feed IPs against firewall traffic" is thoroughly covered, and
duplicating it would add nothing and read as padding to a reviewer.

Checked directly against `Solutions/Threat Intelligence (NEW)` at upstream commit `5f94754`:

- **No rule or hunting query anywhere in that solution reads `Data.labels` for a malware family.**
  The only family-adjacent extraction is `ActivityGroupNames`, a regex for an `ActivityGroup:`
  prefix that this feed does not emit.
- Every template is single-entity and single-source, so a host touching a stealer domain and a
  loader IP produces two unrelated low-signal alerts and nothing correlates them.
- Nothing detects the feed itself going silent.

So the content here leads with what the corpus uniquely has: **family attribution from criminal
marketplace observation**, correlation across families, and a guard against the silent-failure mode.

## The label rough edge, and why every query handles it

`malware:<family>` labels are not normalised at source. Casing is inconsistent, some labels carry
several comma-joined values in one string, and the namespace also holds behaviours (`phishing`),
platforms (`windows`), vendor names and malformed identifiers.

Measured against a live workspace on 2026-08-15: an exact match on `clearfake` returned **196**
indicators; folding case and splitting joined values returned **608**. An exact-match hunt was
silently missing about two thirds of its matches.

Every query here therefore folds case, splits on commas, excludes the known non-family tags and
requires a well-formed name. This is a **mitigation, not a fix**. The fix belongs at the writer
that populates `labels` (INTEL-LABELS-1), and when that lands these queries get simpler.

## Validation

```bash
/usr/bin/python3 sentinel_solution/validate_rules.py
```

Re-implements the parts of the upstream .NET CI that are cheap to re-implement, reading the enums
and schemas out of the fork rather than hardcoding them: required fields, tactic and entity-type
enums, entity identifier names, valid connector IDs, timespan and threshold ranges, entity and
field mapping cardinality, ASCII-only content, GUID uniqueness, and whether every column referenced
on `ThreatIntelIndicators` exists. It also fails a rule whose `entityMappings` or `customDetails`
point at a column the query never produces, which is the defect that ships an alert with empty
entities.

Note `/usr/bin/python3` specifically: the default `python3` on this machine has no PyYAML and is
an externally managed environment.

## Verification status

**Schema-validated, not executed.** See `VERIFY.md` for the checks to run in the QA workspace
**before** MS-1b tears it down, including which results would be a false pass.

## Still to do for MS-1

The Content Hub package (`SolutionMetadata.json`, `Data/Solution_*.json`, `Package/mainTemplate.json`,
logo, `ReleaseNotes.md`) is not built yet. Search keyword GUID
`f1de974b-f438-4719-b423-8bf704ba2aef` is **mandatory on the offer** or the solution never appears
in Sentinel.
