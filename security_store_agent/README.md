# MS-3: Security Copilot agent for Microsoft Security Store

RelayShield Identity Exposure. Built 2026-08-16 against Microsoft's agent manifest reference and
Security Store packaging docs read the same day.

## What the agent does

An analyst mid-incident holds one identifier, usually an email address, and has to decide whether to
force a reset, revoke sessions, or close the alert. Answering that properly means four separate
lookups against four different products. This agent runs them in one pass and returns a verdict with
the evidence behind it.

| Input | Checks run |
|---|---|
| Email address | breach records, infostealer logs, stolen sessions, exposed OAuth tokens |
| Phone number | SIM swap |

The instruction block carries three rules that matter more than the tool calls:

- **Report only what the tools returned.** No inferred exposure, no softened findings.
- **A failed check is reported as unknown, never as clean.** An analyst reading "no exposure found"
  has to be able to trust that every check actually ran. This is the same false-clean failure that
  has bitten this codebase repeatedly.
- **A clean result states which checks it covers**, so the analyst knows the scope of the all-clear.

## Files

```
PackageManifest.yaml                          <- must be at the ROOT of the zip
RelayShieldIdentityExposure/
    AgentManifest.yaml
```

## Verified against the docs

| Rule | Status |
|---|---|
| Three top-level keys: Descriptor, SkillGroups, AgentDefinitions | ✅ |
| `Descriptor.Name` excludes `/ , \ ? # @` and whitespace | ✅ |
| `AgentDefinitions.Name` has no whitespace or period | ✅ |
| `DisplayName` under 30 chars, or Security Copilot truncates it | ✅ 29 |
| API auth is one of the supported schemes | ✅ ApiKey, custom header |
| Operation IDs exist in the live spec | ✅ pulled from `/openapi.json`, not invented |
| At least one trigger, with `Name` and `ProcessSkill` | ✅ |
| `PackageManifest.yaml` type is `CopilotAgent` | ✅ |

## Open questions, stated rather than assumed

**1. Does Security Copilot accept OpenAPI 3.1?** `OpenApiSpecUrl` points at
`https://api.relayshield.net/openapi.json`, which is **3.1.0**. Power Platform rejects anything above
2.0, and I have not found the equivalent statement for Security Copilot either way. **If it rejects
3.1**, `tools/build_powerplatform_connector.py` already converts to 2.0 and can be pointed at a
different operation set, so the fix is small. Not a rewrite, but do not assume it will import.

**2. Sixty-two operations is a lot to expose.** The spec advertises all 62 paths, and the agent's
`ChildSkills` list constrains which five it actually calls. That should be fine, but a scoped spec
would be cleaner if the import is noisy.

**3. The packaged `openapispec_<n>.yaml` alternative is untested.** Security Store's package format
allows an OpenAPI spec as a file inside the zip, while the agent manifest schema documents
`OpenApiSpecUrl` as a URL. Whether a packaged file can be referenced instead of a public URL is not
something I could confirm. The public URL works and is the safer choice.

## Building the zip

**Do not use Finder's Compress.** Microsoft documents this: the macOS archiver adds `.DS_Store` and
`__MACOSX` entries that break publishing.

```
cd security_store_agent && zip -r ../relayshield_agent_package.zip . -x ".*" -x "__MACOSX"
```

Subfolders go at the root of the zip, not inside a parent directory.

## Submitting

Partner Center, using the **Commercial Marketplace** enrolment we already hold:

1. **Marketplace offers → New offer → Software as a Service**. SaaS is the offer type for every
   Security Store listing, agents included.
2. **Sell through Microsoft: Yes.** It is the only supported option. $0 is allowed.
3. **License management: No**, unless we want Microsoft billing the agent.
4. **Microsoft integrations:** tick that the offer integrates with Microsoft Security services, and
   nothing else.
5. Under **Microsoft Security services**: Integrated services must include **Security Copilot**.
   Solution type **Deployable solution**. Tick **Security Copilot agent** so it appears in the Agents
   category. Upload the zip.
6. **Technical configuration:** landing page is the fixed
   `securitystore.microsoft.com/mysolutions`, plus a connection webhook, and the Entra Tenant ID and
   Application ID.
7. After publishing, submit the **NIST CSF 2.0 self-attestation** to appear in the NIST view.

**Tenant ID:** `4abf9bc4-9257-4c71-8b6b-a8afc934b4a5`. An **Entra Application ID** still needs
registering; we do not have one.

**Agents auto-update to the latest version for every customer.** A bad publish reaches everyone at
once, so the preview audience is worth using.
