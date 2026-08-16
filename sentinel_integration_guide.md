# Ingesting RelayShield Threat Intelligence into Microsoft Sentinel

RelayShield serves its IOC corpus over **STIX 2.1 / TAXII 2.1** and a **MISP-compatible REST API**.
Microsoft Sentinel consumes both, so this is a configuration task rather than a development one.

**What you get:** 5.6M+ indicators sourced from 90 criminal Telegram marketplaces and 20
authoritative feeds, landing in Sentinel's `ThreatIntelIndicators` table where they drive analytics
rules, hunting queries and incident enrichment.

**Requirements:** a RelayShield API key with a Threat Intelligence subscription, and a Sentinel
workspace with the **Threat Intelligence** solution installed from Content hub (Microsoft Sentinel
Contributor at the resource group level).

> **Read this first if you have used any earlier Sentinel threat-intel guide.**
> The `ThreatIntelligenceIndicator` table **stopped receiving data on 31 July 2025 and retired on 31 May 2026**.
> Every query, analytics rule, workbook and automation must target
> **`ThreatIntelIndicators`** (and `ThreatIntelObjects` for actors and relationships). A rule still
> pointing at the legacy table matches nothing and raises no error, which is the worst failure mode
> a detection control has.

---

## Option A: STIX/TAXII (recommended)

### 1. Confirm your key works

```bash
curl -s -u "YOUR_API_KEY:YOUR_API_KEY" https://api.relayshield.net/v1/intel/taxii/
```

A valid key returns the TAXII discovery document. Without one you get `401`, which is a useful way
to confirm the endpoint is reachable before adding credentials.

> **Put the key in both the username and the password.** Sentinel exposes Username and Password as
> separate optional fields. The OASIS reference TAXII client skips authentication entirely when the
> password is empty (`if user and password:`), which we confirmed against this feed: key-as-username
> with a blank password returns `401`, and it looks exactly like a bad key. We have not inspected
> Sentinel's own client, so this may not apply to it. RelayShield accepts the key in either
> position regardless, so filling both fields costs nothing and removes the failure mode either way.

### 2. Add the Threat Intelligence - TAXII data connector

**Microsoft Sentinel → Configuration → Data connectors → Threat intelligence - TAXII → Open connector page**

> The connector page button sits at the **bottom of the right-hand detail panel**, which scrolls
> independently of the page. If it is not there, the `...` menu on the connector row has the same
> action. Verified in the portal on 2026-08-15.

| Field | Value |
|---|---|
| Friendly name | `RelayShield` |
| API root URL | `https://api.relayshield.net/v1/intel/taxii/` |
| Collection ID | `iocs` |
| Username | your RelayShield API key |
| Password | your RelayShield API key |
| Import indicators | **All available** |
| Polling frequency | **Once an hour** to start |

Select **Add**. Indicators begin arriving within a few minutes and appear under
**Threat intelligence** in the Sentinel menu.

The API root URL is also the discovery endpoint: RelayShield serves both resources at that one URL,
so you can paste the same value wherever a provider asks for either.

### 3. Confirm indicators are landing

```kusto
ThreatIntelIndicators
| where SourceSystem contains "RelayShield" or Data.external_references contains "relayshield"
| where TimeGenerated > ago(24h)
| summarize Indicators = count() by ObservableKey
| order by Indicators desc
```

You should see five `ObservableKey` values. **Measured in a live Sentinel workspace on 2026-08-15**,
across the first 51,815 indicators ingested in a two-hour window:

| IOC type | `ObservableKey` | Indicators | Share |
|---|---|---|---|
| IP address | `ipv4-addr:value` | 24,929 | 48.1% |
| Domain | `domain-name:value` | 15,613 | 30.1% |
| URL | `url:value` | 8,384 | 16.2% |
| SHA-256 | `file:hashes.'SHA-256'` | 2,870 | 5.5% |
| Email sender | `email-message:from_ref.value` | 19 | 0.04% |

The email-sender type is low volume and appears only intermittently, so do not treat its absence in
a short window as a fault.

**`ThreatIntelObjects` stays empty for this feed.** RelayShield emits STIX `Indicator` objects only,
not `Threat Actor`, `Attack Pattern`, `Identity` or `Relationship` objects. Sentinel's own
documentation points at `ThreatIntelObjects` for actors and relationships; you will not get those
from this connector, and a query joining to that table returns nothing.

If `ObservableKey` and `ObservableValue` come back **empty**, Sentinel could not parse the STIX
pattern. That is worth reporting to support@relayshield.net. It should not happen against the
current feed (see "Changed from earlier versions" below), and it was confirmed working in a live
workspace on 2026-08-15, including the SHA-256 path.

---

## Option B: MISP via misp2sentinel

Sentinel has no first-party MISP connector. The community standard is
[`cudeso/misp2sentinel`](https://github.com/cudeso/misp2sentinel), an Azure Function that reads a
MISP instance with PyMISP and pushes indicators through Sentinel's Upload Indicators API.

RelayShield exposes a MISP-compatible surface, so misp2sentinel can point at it directly with no
MISP server of your own.

In the misp2sentinel configuration:

| Setting | Value |
|---|---|
| `misp_domain` | `https://api.relayshield.net/v1/intel/misp/` |
| `misp_key` | your RelayShield API key |
| `misp_verifycert` | `True` |

> **The trailing slash on `misp_domain` is required.** PyMISP joins paths with `urljoin`, which
> replaces the last segment when the base has no trailing slash, so `/v1/intel/misp` silently becomes
> `/v1/intel/servers/getVersion` and every call 404s.

Prefer Option A unless you are already running misp2sentinel. TAXII is a first-party connector with
no function app to host, monitor or pay for.

---

## Using the indicators

### Analytics rule: match feed IPs against firewall traffic

```kusto
let lookback = 1h;
let relayshield_ips =
    ThreatIntelIndicators
    | where TimeGenerated > ago(14d)
    | where ObservableKey == "ipv4-addr:value"
    | summarize arg_max(TimeGenerated, *) by Id
    | where IsDeleted == false
    | project IndicatorValue = ObservableValue, Confidence, ThreatDescription = tostring(Data.description);
CommonSecurityLog
| where TimeGenerated > ago(lookback)
| join kind=inner relayshield_ips on $left.DestinationIP == $right.IndicatorValue
| project TimeGenerated, SourceIP, DestinationIP, ThreatDescription, Confidence, DeviceVendor
```

`summarize arg_max(TimeGenerated, *) by Id` followed by `where IsDeleted == false` is the pattern
Microsoft's own examples use, and it matters here: the feed republishes every unexpired indicator on
a 7 to 10 day cycle, so without it you count the same indicator many times.

### Analytics rule: match feed domains against DNS

```kusto
let relayshield_domains =
    ThreatIntelIndicators
    | where TimeGenerated > ago(14d)
    | where ObservableKey == "domain-name:value"
    | summarize arg_max(TimeGenerated, *) by Id
    | where IsDeleted == false
    | project IndicatorValue = ObservableValue, ThreatDescription = tostring(Data.description);
DnsEvents
| where TimeGenerated > ago(1h)
| join kind=inner relayshield_domains on $left.Name == $right.IndicatorValue
| project TimeGenerated, Computer, ClientIP, Name, ThreatDescription
```

### Hunting query: which malware families is the feed seeing?

RelayShield tags each indicator with the family it was observed alongside, as a `malware:<family>`
label. This is the part a generic TAXII feed cannot give you, and it is what makes the corpus
huntable by campaign rather than only by indicator.

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(7d)
| summarize arg_max(TimeGenerated, *) by Id
| where IsDeleted == false
| mv-expand Label = Data.labels
| where tostring(Label) startswith "malware:"
// Labels are not case-normalised at source: ClearFake and clearfake both occur.
// Fold case before grouping, or the same family lands in two rows and every
// count is understated. Some labels also carry comma-joined values, so split
// them rather than treating the whole string as one family name.
| extend Family = tolower(replace_string(tostring(Label), "malware:", ""))
| mv-expand Family = split(Family, ",")
| extend Family = trim(" ", tostring(Family))
| where isnotempty(Family)
| summarize Indicators = count() by Family
| top 25 by Indicators
```

Measured against a live workspace on 2026-08-15, the highest-volume labels in a two-hour window were
`phishing` (4,012), `mirai` (2,341), `qakbot` (855), `clearfake` (608), `efimer` (309),
`agenttesla` (304), `trickbot` (255), `formbook` (255), `vidar` (254), `remcosrat` (254),
`bumblebee` (251), `wannacry` (155), `emotet` (103) and `stealc` (98).

> **The `malware:` namespace is not purely malware families, so filter with that in mind.** It also
> carries behaviours (`phishing`, `coinminer`), platforms (`windows`), vendor names
> (`connectwise`), and occasional malformed identifiers. Treat a label as a hint, not a taxonomy.
>
> **Case folding is not cosmetic.** Without the `tolower` and comma-split above, `clearfake` returns
> **196** indicators in this window. With them it returns **608**. An exact-match filter silently
> drops roughly two thirds of the matches and gives you no indication it did.

To hunt one family, always fold case on both sides:

```kusto
ThreatIntelIndicators
| where TimeGenerated > ago(7d)
| summarize arg_max(TimeGenerated, *) by Id
| where IsDeleted == false
| mv-expand Label = Data.labels
| where tolower(tostring(Label)) == "malware:clearfake"
| project TimeGenerated, ObservableKey, ObservableValue, Confidence
```

### Reading the legacy-shaped fields

If you are porting rules written against `ThreatIntelligenceIndicator`, this reconstructs the old
column names from the new schema:

```kusto
ThreatIntelIndicators
| extend NetworkIP  = iff(ObservableKey == "ipv4-addr:value",   ObservableValue, ""),
         DomainName = iff(ObservableKey == "domain-name:value", ObservableValue, ""),
         Url        = iff(ObservableKey == "url:value",         ObservableValue, ""),
         FileHashValue = iff(ObservableKey has "file:hashes",   ObservableValue, ""),
         FileHashType  = iff(ObservableKey has "SHA-256", "SHA-256", "")
```

---

## Cost note

`ThreatIntelIndicators` is a billed Log Analytics table, and the feed republishes every unexpired
indicator every 7 to 10 days. Before importing **All available**, consider whether your detection
surface needs the full corpus. Two levers:

- Set the connector to import a narrower indicator group.
- Apply a workspace transformation to drop the `Data` column, which carries the full STIX object:

  ```kusto
  source | project-away Data
  ```

  The hunting queries above read `Data.labels` and `Data.description`, so drop it only if you do not
  need those.

---

## Changed from earlier versions

Four defects were found and fixed in the RelayShield feed on **2026-07-30**, while preparing this
guide, by running the OASIS reference TAXII client against production:

1. The API Root resource omitted the required `versions` field, so a conformant TAXII client aborted
   before requesting anything.
2. `GET /{api-root}/collections/{id}/` returned 404. Clients fetch this before requesting objects,
   so object polling failed without ever reaching the objects endpoint.
3. The object envelope was served as `application/stix+json` rather than
   `application/taxii+json;version=2.1`.
4. SHA-256 patterns were emitted as `[file:hashes.SHA-256 = '...']`, which is **invalid STIX 2.1 patterning**.
   The hash key must be quoted. Sentinel derives `ObservableKey`/`ObservableValue` by
   parsing the pattern, so SHA-256 indicators would have arrived with both fields empty.

**If you configured RelayShield in Sentinel before 2026-07-30**, remove and re-add the connector so
it re-polls from the start of the collection, and re-check any rule keyed on file hashes.

## Verification status

Stated plainly, because a threat-intel guide that overstates its testing is worse than no guide:

**Verified against live systems.** Every RelayShield-side claim (the API root and collection URLs,
the auth behaviour including the blank-password trap, the TAXII protocol walk end to end, the
validity of every STIX pattern in a 1,000-object live sample, and the PyMISP handshake) was
measured against the production feed with the OASIS `taxii2-client`, `stix2-patterns` validator, and
PyMISP.

**Measured in a live Microsoft Sentinel workspace, 2026-08-15.** The `ObservableKey` values, the
table names and the malware-family label queries were previously *derived* from Microsoft's
published schema rather than run. They have now been executed against a real workspace ingesting
this feed:

- `ThreatIntelIndicators` and `ThreatIntelObjects` are confirmed as the current table names, both
  plural. Some Microsoft solution descriptions render the first as singular; that text is wrong.
- All five `ObservableKey` values above were returned with populated `ObservableValue`, confirming
  Sentinel parses every STIX pattern this feed emits, SHA-256 included.
- `ThreatIntelObjects` remained empty, as expected for an Indicator-only feed.
- The `malware:<family>` label queries return real families.

**Known rough edge in the family labels.** Label values are not normalised: casing is inconsistent
(`ClearFake` and `clearfake` both occur), some labels carry several comma-joined values in a single
string, and a few describe a behaviour rather than a family (`phishing`, `coinminer`). **Match
case-insensitively** (`where tolower(Family) == "clearfake"` rather than an exact comparison), or
you will silently miss indicators. This is being fixed at source.

---

Questions: [support@relayshield.net](mailto:support@relayshield.net) ·
[api.relayshield.net/developers](https://api.relayshield.net/developers)
