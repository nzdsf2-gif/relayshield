# Verifying the RelayShield Sentinel rules before teardown

**Why this file exists.** The rules are schema-validated but **not executed**. `validate_rules.py`
checks them against the Azure-Sentinel repo's own enums, connector list and the
`ThreatIntelIndicators` column schema that its KQL validator uses, which catches wrong column
names, invalid tactics and bad entity mappings. It cannot catch a query that parses fine and
returns the wrong answer. Only running them does that.

Run these in **Microsoft Sentinel > Logs** on `relayshield-sentinel-ws` before MS-1b tears the
workspace down. Once the resource group is gone there is no way to check any of this.

## Read this before interpreting an empty result

**Three of the five queries join against `CommonSecurityLog`, and the QA workspace has no firewall
feeding it.** Those queries will return zero rows, and zero rows means "no log source", not
"verified, nothing matched". Treat an empty result from checks 4 and 5 as **not verified**, not as
a pass. That distinction is the entire point of check 0.

## Check 0: what data does this workspace actually have?

```kusto
union withsource=TableName *
| where TimeGenerated > ago(24h)
| summarize Rows = count() by TableName
| order by Rows desc
```

Expected: `ThreatIntelIndicators` present with a large count. If `CommonSecurityLog` is absent,
checks 4 and 5 cannot be verified here and must be verified against a customer workspace later.

## Check 1: the label normalisation still holds

This is the measurement the guide and three of the queries depend on. It re-runs the
2026-08-15 finding.

```kusto
let not_families = dynamic([
  "phishing", "coinminer", "cryptominer", "spam", "scam", "ransomware", "loader",
  "stealer", "botnet", "trojan", "backdoor", "downloader", "malware", "apt",
  "windows", "linux", "macos", "android", "ios"
]);
ThreatIntelIndicators
| where TimeGenerated > ago(7d)
| where SourceSystem has "RelayShield" or tostring(Data.external_references) has "relayshield"
| summarize arg_max(TimeGenerated, *) by Id
| where IsActive and (isnull(ValidUntil) or ValidUntil > now())
| mv-expand Label = Data.labels
| where tostring(Label) startswith "malware:"
| extend Tag = tolower(replace_string(tostring(Label), "malware:", ""))
| mv-expand Tag = split(Tag, ",")
| extend Tag = trim(" ", tostring(Tag))
| where isnotempty(Tag)
| extend IsWellFormed = Tag matches regex @"^[a-z][a-z0-9._-]{2,}$"
| extend Kind = case(Tag in (not_families), "behaviour or platform", IsWellFormed == false, "malformed", "family")
| summarize Indicators = dcount(Id) by Tag, Kind
| order by Indicators desc
```

**Pass:** rows come back, `clearfake` appears once (not as `ClearFake` and `clearfake` separately),
and the `Kind` column correctly sorts `phishing` and `windows` away from real families.

**Fail worth catching:** if `SourceSystem has "RelayShield"` matches nothing, every rule in this
solution is scoped to nothing. Confirm by removing that line and seeing whether counts change.

## Check 2: which branch of the source filter is actually matching

Every rule scopes itself with `SourceSystem has "RelayShield" or Data.external_references has
"relayshield"`. If only one branch ever matches, the other is dead code, and if **neither** matches
in a customer workspace the rules silently do nothing.

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(24h)
| extend BySourceSystem = SourceSystem has "RelayShield",
         ByExternalRef  = tostring(Data.external_references) has "relayshield"
| summarize Indicators = count() by BySourceSystem, ByExternalRef, SourceSystem
| order by Indicators desc
```

**Record the answer.** If `BySourceSystem` is false everywhere, the friendly name set on the
connector is not what lands in `SourceSystem`, and the guide's instruction to name the connector
`RelayShield` becomes load-bearing in a way it is not currently documented to be.

## Check 3: feed ingestion rule (RelayShieldFeedIngestionStopped)

Paste the rule's `query:` block verbatim. It should return **zero rows** on a healthy feed.

Then force the alarm state by shortening the threshold, to prove it fires rather than being
silently empty:

```kusto
let stale_after = 1s;
let lookback = 14d;
ThreatIntelIndicators
| where TimeGenerated > ago(lookback)
| where SourceSystem has "RelayShield" or tostring(Data.external_references) has "relayshield"
| summarize LastIndicator = max(TimeGenerated), IndicatorsInWindow = count()
| where isnull(LastIndicator) or LastIndicator < ago(stale_after)
| extend HoursSinceLastIndicator =
    iff(isnull(LastIndicator), real(null), round(datetime_diff('minute', now(), LastIndicator) / 60.0, 1))
| project LastIndicator, IndicatorsInWindow, HoursSinceLastIndicator
```

**Pass:** exactly one row, with a real `LastIndicator` and a plausible hours value. This proves the
rule produces a row when it should. A rule that never produces a row under any condition is the
failure mode this rule exists to prevent, so it is worth proving both directions.

Also prove the null branch, which is the case a naive freshness check misses:

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(14d)
| where SourceSystem has "ThisWillNeverMatchAnything"
| summarize LastIndicator = max(TimeGenerated), IndicatorsInWindow = count()
| where isnull(LastIndicator) or LastIndicator < ago(6h)
```

**Pass:** one row, `LastIndicator` empty, `IndicatorsInWindow` 0. **If this returns zero rows the
rule is broken** and would go quiet exactly when the feed is fully dead.

## Check 4: emerging families (RelayShieldEmergingFamilies)

Substitute the placeholders, then run:

```
{{StartTimeISO}}  ->  ago(8d) equivalent, e.g. datetime_add('day', -8, now())
{{EndTimeISO}}    ->  now()
```

Concretely, replace the first two lines with:

```kusto
let starttime = datetime_add('day', -8, now());
let endtime = now();
```

**Pass:** the query parses and returns rows, or returns nothing *with a non-empty baseline*. The
QA workspace has only had the feed for a short window, so `Status == "new"` may dominate; that is
expected, not a defect. What matters is that `baseline_days` is positive and `GrowthFactor` is not
`NaN` or infinite.

## Check 5: the two CommonSecurityLog queries

`RelayShieldMultiFamilyConvergence` and `RelayShieldCredentialTheftFamilies`.

**These cannot be functionally verified in the QA workspace.** Verify the TI half in isolation by
running only the `RelayShield_Indicators` / `Stealer_Indicators` `let` block followed by
`| take 20`, which proves the indicator selection, the label handling and the family filter work.

```kusto
// paste the let block, then:
RelayShield_Indicators | take 20
```

**Pass:** 20 rows with populated `Family`, `IndicatorValue` and `Confidence`.

For `Stealer_Indicators`, also check the family list is not empty in practice:

```kusto
Stealer_Indicators | summarize Indicators = dcount(IndicatorId) by Family | order by Indicators desc
```

**If this returns nothing**, the hardcoded `stealer_families` list does not intersect the feed's
actual labels, and the hunting query would ship as a permanently empty result. Cross-check the
list against the output of Check 1 and adjust before the PR.

## After verification

Record what passed and what did not in TODO.md, **then** run MS-1b. Anything unverified here has
to be marked as unverified in the solution readme rather than left implied, on the same principle
the guide's verification-status section already follows.
