# RelayShield connector for Microsoft Power Platform

Identity threat intelligence for Power Automate, Power Apps and Copilot Studio. Twelve operations
over the RelayShield public API, covering breach, SIM swap, infostealer, session, vendor, domain,
certificate, card and IP exposure.

## Files

| File | Purpose |
|---|---|
| `apiDefinition.swagger.json` | Swagger 2.0 connector definition, 12 operations |
| `apiProperties.json` | Connection parameters, brand colour, publisher |
| `settings.json` | `paconn` settings |
| `icon.png` | 230x230 connector icon |
| `intro.md` | Certification submission document |
| `certcheck.py` | Offline pre-submission checks |
| `certification_calls.py` | Exercises every operation 10 times |

## How the definition is produced

`apiDefinition.swagger.json` is **derived from `relayshield_openapi_spec.py`**, the OpenAPI 3.1
contract whose schemas are read off the live handlers in `relayshield_api.py`. It is not
hand-maintained. When a handler changes, regenerate rather than hand-edit, so the connector cannot
drift from the API the way the old synthesised spec did.

The generator selects 12 of the 29 metered endpoints and downgrades 3.1 to Swagger 2.0: `$ref`
targets are remapped to `#/definitions`, nullable type arrays become `x-nullable`, `const` becomes a
single-value `enum`, and `oneOf`/`anyOf` branches are collapsed, since Swagger 2.0 has no equivalent.

## Before submitting

```bash
python3 certcheck.py                      # offline rules, no login needed
paconn validate --api-def apiDefinition.swagger.json   # requires a Power Platform login

export RELAYSHIELD_API_KEY=...
python3 certification_calls.py            # dry run, shows the plan
python3 certification_calls.py --run      # 120 billable calls
```

`certcheck.py` covers what can be checked offline: Swagger version, HTTPS only, operationId casing
and uniqueness, summary length and duplication, required descriptions, `x-ms-summary` on every
request field, forbidden brand colours, and icon dimensions, transparency and background match.
It does not replace `paconn validate`, which authenticates against the Power Platform validation
service.

## Operation set

The 12 operations were chosen for the Power Automate audience, which is IT operations rather than
developers. `ransomware-risk` is deliberately **excluded**: its upstream feed (`joshhighet/ransomwatch`)
has been archived since June 2025 and returns no 2026 records, so the endpoint would ship into a
Microsoft certification review returning stale data. See INTEL-4-SOURCE. Do not add it back until
the migration to `api.ransomware.live` has landed.
