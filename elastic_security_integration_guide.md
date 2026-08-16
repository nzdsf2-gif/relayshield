# Ingesting RelayShield Threat Intelligence into Elastic Security

RelayShield serves its IOC corpus over **STIX 2.1 / TAXII 2.1** and a **MISP-compatible REST API**.
Elastic Security ingests both through integrations it already ships, so this is a configuration task,
not a development one.

**What you get:** 5.6M+ indicators sourced from 90 criminal Telegram marketplaces and 20
authoritative feeds, flowing into Elastic's `logs-ti_*` indices where they enrich alerts and power
Indicator Match detection rules.

**Requirements:** a RelayShield API key with a Threat Intelligence subscription, and Elastic Stack
8.x or later (Elastic Cloud or self-managed) with Fleet and an Elastic Agent.

> Every field name, integration name and mapping below was verified against a live Elasticsearch
> 8.15 stack ingesting the production RelayShield feed. If you followed an earlier version of this
> guide, see the note at the end: the integration name and two of the rule mappings have changed.

---

## Option A: STIX/TAXII via Custom Threat Intelligence (recommended)

Use the **Custom Threat Intelligence** integration (package `ti_custom`), which has a built-in
TAXII 2.1 mode. Elastic does not ship a generic "TAXII" integration; this is the one.

### 1. Confirm your key works

```bash
curl -s https://api.relayshield.net/v1/intel/taxii/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

A valid key returns the TAXII discovery document. `X-RS-API-KEY: YOUR_API_KEY` also works and is
equivalent, so use whichever your tooling prefers. Without a valid key you get `401`, which is a useful
way to confirm the endpoint is reachable before adding credentials.

### 2. Add the integration in Kibana

**Management → Integrations → Custom Threat Intelligence → Add**

| Field | Value |
|---|---|
| URL | `https://api.relayshield.net/v1/intel/taxii/collections/iocs/objects/` |
| Enable TAXII 2.1 | **on** |
| API Key | your RelayShield API key |
| API Key Type | `Bearer` |
| Accept header value | leave default (`application/taxii+json;version=2.1`) |
| Interval | `1h` to start; tighten only if your use case needs it |
| IOC Expiration Duration | leave default |

The collection is part of the URL: there is no separate "Collection ID" field. The trailing slash is
optional.

**On API Key Type:** the integration sends your key as `Authorization: <API Key Type> <API Key>`.
`Bearer` is the default and works. It cannot send a custom header name, which is why the URL above
is authenticated with `Authorization` rather than `X-RS-API-KEY`.

**On IOC Expiration Duration:** RelayShield emits `valid_until` on every indicator (90 days from the
sighting), so expiry is handled for you regardless of what you set here.

### 3. Confirm data is arriving

In **Discover**, query the threat intel data stream:

```
data_stream.dataset : "ti_custom.indicator"
```

Indicators land with `threat.indicator.type` set to `ipv4-addr`, `domain-name`, `url`, `file` or
`email-addr` depending on the IOC.

---

## Option B: MISP-compatible REST API

If you already run Elastic's **MISP** integration, RelayShield can be added as an additional source
rather than replacing your existing one.

**Management → Integrations → MISP → Add**, and enable the **Threat Attributes** data stream:

| Field | Value |
|---|---|
| URL | `https://api.relayshield.net/v1/intel/misp` |
| API Key / token | your RelayShield API key |
| Interval | `1h` |

The integration appends `/attributes/restSearch` to that base URL and sends your key in the
`Authorization` header, and both are handled. Confirm ingestion with:

```
data_stream.dataset : "ti_misp.threat_attributes"
```

Attributes are returned with MISP types `ip-dst`, `domain`, `url`, `sha256` and `email-src`, which
Elastic maps to the same `threat.indicator.type` values as Option A.

---

## Using the data

### Enrichment

Once indicators are flowing, Elastic's built-in **Threat Intel enrichment** matches them against your
existing logs automatically. No rule authoring needed: matches appear on the alert under
`threat.enrichments`.

### Indicator Match rule

For explicit detection, create a rule under **Security → Rules → Create new rule → Indicator Match**:

| Setting | Value |
|---|---|
| Index patterns | your source logs (e.g. `logs-*`, `filebeat-*`) |
| Indicator index | `logs-ti_*` |
| Indicator mapping | `destination.ip` → `threat.indicator.ip` |
| | `source.ip` → `threat.indicator.ip` |
| | `dns.question.name` → `threat.indicator.url.original` |
| | `url.full` → `threat.indicator.url.original` |
| | `file.hash.sha256` → `threat.indicator.file.hash.sha256` |

**Note on domain and URL indicators.** Both land in `threat.indicator.url.original`. There is no
`threat.indicator.url.domain` or `threat.indicator.url.full` field on these documents, and mapping
to either produces a rule that never matches and raises no error, so it looks configured while doing
nothing. Values are stored as arrays, which Indicator Match handles natively but is worth knowing if
you write your own queries.

Set severity to match your triage process. Because RelayShield's corpus is sourced from criminal
marketplaces rather than general reputation feeds, a match generally warrants investigation rather
than informational logging.

### A note on timing

RelayShield's Telegram-sourced indicators typically surface **24 to 72 hours ahead** of public feeds,
because the pipeline collects from the marketplaces where credentials and infrastructure are sold
rather than waiting for downstream aggregation. That lead time is the reason to run this alongside,
not instead of, your existing feeds.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `401 Unauthorized` | Key is missing, wrong, or lacks a TI subscription. The TI endpoints require an active TI plan, separate from PAYG API access. |
| `404` on `/v1/taxii/...` | Wrong path. The prefix is `/v1/intel/taxii/`, not `/v1/taxii/`. |
| No "TAXII" integration in Kibana | Correct. Elastic has no generic TAXII integration. Use **Custom Threat Intelligence** and switch on Enable TAXII 2.1. |
| Integration added, no documents | Check the interval has elapsed, then confirm the URL includes the full collection path `/collections/iocs/objects/`. |
| Documents arrive with only `threat.indicator.name` and no type | An expiry field was missing and Elastic's pipeline aborted. RelayShield now emits `valid_until`, so update to the current feed. |
| Indicators arrive but the rule never matches | Almost always the domain/URL mapping. Both must point at `threat.indicator.url.original`. |

---

## Changed from earlier versions of this guide

An earlier version named a "Threat Intel TAXII 2.x" integration, which does not exist in Elastic's
package registry, and gave two Indicator Match mappings (`threat.indicator.url.domain` and
`threat.indicator.url.full`) that match no field. If you configured from it, three changes are needed:

1. Use **Custom Threat Intelligence** with Enable TAXII 2.1, not "Threat Intel TAXII 2.x".
2. Query `ti_custom.indicator`, not `ti_taxii.indicator`.
3. Point both the domain and URL mappings at `threat.indicator.url.original`.

The MISP endpoint is now a real MISP-compatible REST surface at `/v1/intel/misp`; the earlier
documented path returned 404.

---

## Support

`support@relayshield.net`. Include the integration type (Custom Threat Intelligence or MISP) and the
Kibana or Elastic Agent error text if there is one.
