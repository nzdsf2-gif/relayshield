# Scam-Kit Fingerprint Specification

**Spec version:** 1.0.0
**Status:** Draft for community review
**License:** MIT (see LICENSE)

> This spec defines the FORMAT of scam-kit fingerprint records. RelayShield's
> threat-intelligence corpus data is NOT included. The format is open; the
> corpus that populates it is not.

## 1. Purpose

Phishing kits (Tycoon 2FA, Evilginx, Mamba 2FA, and dozens of others) are
reused across campaigns with small modifications. Defenders need a stable,
shareable identifier for "this is the same kit we saw last week" that
survives domain rotation, hosting changes, and minor HTML edits.

This spec defines `kit_<sha256>` fingerprint IDs: deterministic identifiers
computed from structural features of kit HTML, so the same kit produces the
same ID across sightings regardless of where it is hosted.

## 2. Fingerprint ID format

A fingerprint ID has the shape:

```
kit_<64 lowercase hex characters>
```

The full regular expression for validation:

```
(kit|malware)_[0-9a-f]{64}
```

The `malware_` prefix is a reserved extension point for a future malware
fingerprint track. Implementations of this spec version MUST accept both
prefixes when validating ID shape, and MUST only emit `kit_` IDs unless
implementing the malware track.

## 3. How the digest is computed

### 3.1 Signal extraction

From the kit's rendered HTML and its URL, extract a signal dictionary. The
reference signal set (skfp-v2) is:

| Signal | Description |
|---|---|
| `brand_marks` | Sorted list of impersonated brand names found in visible text |
| `dom_skeleton_hash` | SHA256 of the DOM tag skeleton (tags only, text stripped) |
| `exfil_endpoints` | Sorted list of external hosts in anchors, iframes, form actions |
| `form_action_hosts` | Sorted list of hosts in form action attributes |
| `script_hashes` | Sorted list of SHA256 hashes of script sources and normalized inline scripts |
| `sms_lure_template_hash` | SHA256 of the normalized lure text template |
| `url_pattern_class` | Classification of the URL structure (e.g. random-subdomain, path-lure) |
| `kit_uri_markers` | Sorted list of known kit URI path markers found in HTML/JS |
| `kit_appid_marks` | Sorted list of hardcoded application ID markers |
| `hardcoded_ua_marks` | Sorted list of hardcoded user-agent markers |
| `socketio_kit_events` | Sorted list of Socket.IO relay event names |
| `title_marks` | Page title markers |
| `email_hosts` | Hosts found in email-related contexts |
| `favicon_data_hash` | SHA256 of inline/data-URI favicon, when present |
| `kind` | Always `"kit"` for this track |
| `fingerprint_version` | The signal schema version (see section 5) |

### 3.2 Secret stripping

Before hashing, victim-shaped secrets MUST be replaced with typed
placeholders that preserve shape but not value: private keys, JWTs, API
keys, bearer tokens, and basic-auth credentials in URLs. This keeps the
fingerprint stable across sightings (the same kit with different victim
data still matches) and keeps fingerprints safe to share.

### 3.3 Canonical form and digest

1. Serialize the signal dictionary as JSON with sorted keys and compact
   separators: `json.dumps(signals, sort_keys=True, separators=(",", ":"))`.
2. Prepend the fingerprint version and a colon: `"<version>:<canonical>"`.
3. Compute SHA256 over the UTF-8 encoding of that string.
4. The fingerprint ID is `"kit_"` followed by the 64-character lowercase
   hex digest.

In pseudocode:

```
canonical = json_dumps(signals, sort_keys=True, separators=(",", ":"))
digest_input = version + ":" + canonical
digest = sha256_utf8(digest_input).hex()
fingerprint_id = "kit_" + digest
```

The version namespace in step 2 means fingerprints computed under older
signal schemas remain valid and do not collide with newer ones.

## 4. Kit fingerprint record (JSON schema)

A shareable kit fingerprint record:

```json
{
  "fingerprint_id": "kit_<64 hex chars>",
  "spec_version": "1.0.0",
  "fingerprint_version": "skfp-v2",
  "kind": "kit",
  "family": "tycoon-2fa",
  "family_status": "suggested",
  "signals": { "...": "..." },
  "indicators": ["..."],
  "first_seen": "2026-10-08T00:00:00Z",
  "sightings": 3
}
```

Field notes:

* `fingerprint_id`: the `kit_<sha256>` ID from section 3. Required.
* `spec_version`: the version of THIS spec the record conforms to. Required.
* `fingerprint_version`: the signal schema version (`skfp-v1`, `skfp-v2`).
  Required.
* `kind`: `"kit"`. Reserved `"malware"` for the future track. Required.
* `family`: human-readable kit family name (e.g. `tycoon-2fa`), or null if
  unassigned. Family assignment is suggestive, never authoritative; see
  section 7.
* `family_status`: `"approved"` or `"suggested"`. Only `"approved"` means a
  human reviewer confirmed the family assignment.
* `signals`: the full signal dictionary used to compute the ID. Optional
  but recommended for verification.
* `indicators`: associated indicators (URLs, domains, IPs, hashes). Capped
  at 25 per record (see section 6). Optional.
* `first_seen`: ISO 8601 timestamp of first observation. Optional.
* `sightings`: count of distinct sightings resolving to this ID. Optional.

## 5. Versioning

Two version lines, kept separate:

* **Spec version** (`spec_version`): this document. Follows semantic
  versioning. `1.0.0` is the first public release. Breaking changes to the
  record format bump the major version.
* **Fingerprint version** (`fingerprint_version`): the signal schema used to
  compute the digest. Current values: `skfp-v1`, `skfp-v2`. The digest input
  includes this version, so fingerprints from older schemas stay valid when
  the schema evolves. Implementations MUST reject unknown fingerprint
  versions rather than guessing.

When the signal schema changes in a way that alters digests, the
fingerprint version MUST be bumped and the old version MUST remain in the
supported set so existing records keep resolving.

## 6. The 25-indicator cap

A kit fingerprint record carries at most 25 associated indicators. This is
a deliberate bound, not a technical limit:

* It keeps records small enough to share freely (email, chat, API).
* It forces prioritization: the 25 most representative indicators, not an
  exhaustive dump.
* The full indicator set for a kit lives in the publisher's corpus; the
  record is a pointer, not the corpus.

Implementations MUST truncate or refuse records with more than 25
indicators in the `indicators` array.

## 7. Family names are suggestive, not authoritative

A `family` name (e.g. `evilginx`, `mamba-2fa`) is a human-assigned label
suggesting which kit family a fingerprint resembles. It is derived from
marker hints and reviewer judgment. It is NOT part of the digest input:
two records with the same fingerprint ID are the same kit even if their
family labels differ, and family labels MUST NOT be used as match keys.

`family_status: "approved"` means a human reviewer confirmed the label.
`"suggested"` means it came from automated hints. Consumers SHOULD treat
suggested labels as leads, not facts.

## 8. Reserved: malware track

The `malware_<sha256>` ID shape and `"kind": "malware"` record value are
reserved for a future malware fingerprint track using the same digest
construction over malware-appropriate signals. This spec version does not
define that signal set. Implementations MUST NOT emit `malware_` IDs under
this spec version.

## 9. Conformance

A conforming implementation:

1. Computes IDs exactly per section 3 (same canonicalization, same
   version namespacing, same secret stripping).
2. Validates ID shape per section 2.
3. Emits records per the section 4 schema with at most 25 indicators.
4. Rejects unknown fingerprint versions instead of guessing.
5. Never treats `family` as a match key.

A conforming record validates against the section 4 schema and its
`fingerprint_id` recomputes from its `signals` per section 3.

## 10. What this spec does not cover

* The corpus data itself: sightings, full indicator sets, and historical
  records are the publisher's private data.
* Family taxonomy governance: who approves family names is up to each
  publisher.
* Transport: how records are shared (API, feed, file) is out of scope.
* Legal or enforcement use: fingerprints are investigative leads, not
  proof of criminal activity.
