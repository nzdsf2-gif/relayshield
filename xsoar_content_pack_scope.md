# RelayShield Cortex XSOAR content pack — scoped, not built

Status: scoped 2026-07-21, on-deck next build after the LangChain gate /
John6666 reply work finishes. Not started.

## Why a pack, given the SIEM connector already exists

`relayshield_siem_connector.py` already lets any customer create XSOAR
incidents from RelayShield alerts via a generic webhook — zero pack needed
for that. A real content pack's added value is different: it lets
RelayShield act as an **enrichment source inside existing playbooks**, the
same role VirusTotal/other TI integrations play. That means implementing
XSOAR's generic reputation commands (`domain`, `ip`, `email`), which XSOAR
auto-routes to any integration implementing them — any customer's existing
enrichment playbook picks up RelayShield with zero playbook changes. That's
the highest-leverage thing to build, not a repackaged webhook.

## Submission path

Community-supported via the Marketplace UI or a GitHub PR to the XSOAR
content repo. No formal Palo Alto Networks technology-partner status
required — MIT license, sign the CLA, complete a registration form. Full
partner program (Author_image mandatory, dedicated support contact) is a
separate, stricter tier — not required for a first submission.

## File structure

```
Packs/RelayShield/
├── pack_metadata.json                 # name, support: community, category: "Data Enrichment & Threat Intelligence"
├── README.md                          # pack overview, setup, link to api.relayshield.net/developers
├── Author_image.png                   # 120x50, ≤4KB — cheap to make, adds polish even on the community path
├── Integrations/
│   └── RelayShield/
│       ├── RelayShield.yml            # params: api_key (type 9, encrypted); commands below
│       ├── RelayShield.py             # command implementations
│       ├── RelayShield_description.md # shown in the integration config panel
│       ├── RelayShield_image.png      # 128x128 logo in the integration list
│       ├── Pipfile / Pipfile.lock     # pinned: requests
│       ├── test_data/                 # mock JSON fixtures per command
│       └── RelayShield_test.py        # pytest, demisto-sdk conventions
├── Playbooks/
│   └── RelayShield_Enrich_Domain.yml  # sample playbook demonstrating the domain command in context
├── TestPlaybooks/
│   └── RelayShield_Test.yml           # SDK-run integration test
└── doc_files/
    └── relayshield_setup.png          # referenced from README
```

## Command set, in priority order

| Command | Type | Maps to | Notes |
|---|---|---|---|
| `domain` | generic reputation | `/v1/metered/domain` (or nearest domain-risk endpoint) | auto-invoked by any playbook enriching a domain |
| `ip` | generic reputation | `/v1/metered/ip-intel` | auto-invoked for IP enrichment |
| `email` | generic reputation | `/v1/metered/breach` + `/v1/metered/session-risk` combined | auto-invoked for identity enrichment |
| `relayshield-mcp-registry-risk` | custom | `/v1/metered/mcp-registry-risk` | not a generic type — analyst/playbook calls it explicitly; ties back to the John6666 gate work |
| `relayshield-cert-expiry` | custom | `/v1/metered/cert-expiry` | |
| `relayshield-supply-chain` | custom | `/v1/metered/supply-chain` | |

## DBotScore mapping — decided 2026-07-21

`no_known_finding` → `Unknown(0)`, **not** `Good(1)`. CRITICAL/HIGH →
`Bad(3)`, MEDIUM → `Suspicious(2)`.

Founder's call: it's more credible to report `Unknown` than `Good` when
RelayShield honestly doesn't have a result, consistent with the same
principle already established in `relayshield_smolagents_tool.py`'s
docstring ("`no_known_finding` deliberately does not mean 'safe'"). The
tradeoff, worth remembering if this ever gets revisited: RelayShield won't
contribute to a playbook's "verdict is clean, auto-close" logic the way a
`Good` score would, since `Unknown` doesn't participate in XSOAR's aggregate
"all sources clean" checks the same way. Accepted as the right tradeoff —
consistency of the honesty claim across every RelayShield surface outweighs
the playbook-convenience loss.

## Not yet done

No `RelayShield.py`, `RelayShield.yml`, or tests written. Needs a
`demisto-sdk` dev environment and a Docker image for the integration
runtime before real implementation work can start.
