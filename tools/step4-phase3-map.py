#!/usr/bin/env python3
"""Phase 3: map the two Step 4 license Lambdas in the deploy workflow
and the drift check. Idempotent: a second run reports SKIP for each
edit that is already present and makes no changes.

Run from the relayshield repo root on the Mac:
    python3 tools/step4-phase3-map.py

Edits:
  1. .github/workflows/deploy_lambdas.yml, on.push.paths list: add the
     two files after relayshield_bundle_fulfillment.py.
  2. .github/workflows/deploy_lambdas.yml, manual-dispatch CHANGED list:
     append the two files after relayshield_bundle_fulfillment.py.
  3. .github/workflows/deploy_lambdas.yml, LAMBDA_MAP: add the two
     file-to-function mappings after the bundle-fulfillment entry.
  4. .github/workflows/lambda_drift_check.yml, its map: add the same
     two entries after the bundle-fulfillment entry.

The LAMBDA_MAP edit uses a regex so it matches the bundle-fulfillment
entry regardless of leading whitespace, and reuses that indentation
for the two new lines. If the anchor is not found exactly once, the
script aborts with no writes to that file.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DEPLOY = REPO / ".github" / "workflows" / "deploy_lambdas.yml"
DRIFT = REPO / ".github" / "workflows" / "lambda_drift_check.yml"

LS = "relayshield_license_service.py"
SL = "relayshield_stripe_license.py"


def edit_paths(text: str) -> str:
    anchor = "      - 'relayshield_bundle_fulfillment.py'\n"
    add = "      - 'relayshield_license_service.py'\n      - 'relayshield_stripe_license.py'\n"
    if anchor + add in text:
        print("SKIP paths list: already present")
        return text
    if text.count(anchor) != 1:
        print(f"FAIL paths list: anchor found {text.count(anchor)} times, expected 1")
        sys.exit(1)
    print("OK paths list: added the two files")
    return text.replace(anchor, anchor + add, 1)


def edit_changed(text: str) -> str:
    if "relayshield_bundle_fulfillment.py relayshield_license_service.py relayshield_stripe_license.py" in text:
        print("SKIP CHANGED list: already present")
        return text
    # Anchor on the two files in sequence (watchlist_monitor, then
    # bundle_fulfillment). That sequence appears only in the CHANGED
    # variable, never in the LAMBDA_MAP (where each file is on its own
    # line in ["..."] form). The old anchor
    # 'relayshield_bundle_fulfillment.py"' matched inside the LAMBDA_MAP
    # entry instead of the CHANGED variable, corrupting the map in memory
    # and making the map edit fail.
    anchor = 'relayshield_watchlist_monitor.py relayshield_bundle_fulfillment.py'
    if text.count(anchor) != 1:
        print(f"FAIL CHANGED list: anchor found {text.count(anchor)} times, expected 1")
        sys.exit(1)
    print("OK CHANGED list: appended the two files")
    return text.replace(
        anchor,
        'relayshield_watchlist_monitor.py relayshield_bundle_fulfillment.py relayshield_license_service.py relayshield_stripe_license.py',
        1,
    )


def edit_map(text: str, label: str) -> str:
    if '["relayshield_license_service.py"]="relayshield-license-service"' in text and '["relayshield_stripe_license.py"]="relayshield-stripe-license"' in text:
        print(f"SKIP {label} map: already present")
        return text
    # Case B: a combined key (three files in one key). This happens if a
    # previous edit inserted the license files into the bundle key instead
    # of adding separate entries. Replace the whole line with three
    # separate entries.
    combined = re.compile(
        r'^(\s*)\["relayshield_bundle_fulfillment\.py relayshield_license_service\.py relayshield_stripe_license\.py"\]="relayshield-bundle-fulfillment"\s*$',
        re.MULTILINE,
    )
    cm = list(combined.finditer(text))
    if len(cm) == 1:
        m = cm[0]
        indent = m.group(1)
        replacement = (
            f'{indent}["relayshield_bundle_fulfillment.py"]="relayshield-bundle-fulfillment"'
            f'\n{indent}["relayshield_license_service.py"]="relayshield-license-service"'
            f'\n{indent}["relayshield_stripe_license.py"]="relayshield-stripe-license"'
        )
        print(f"OK {label} map: split the combined bundle key into three entries")
        return text[:m.start()] + replacement + text[m.end():]
    # Case A: the normal single-file bundle key. Match regardless of
    # leading whitespace and reuse that indentation for the new lines.
    pattern = re.compile(
        r'^(\s*)\["relayshield_bundle_fulfillment\.py"\]="relayshield-bundle-fulfillment"\s*$',
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        print(f"FAIL {label} map: anchor found {len(matches)} times, expected 1")
        print(f"--- diagnostic: lines in {label} mentioning LAMBDA_MAP or bundle-fulfillment ---")
        for i, line in enumerate(text.splitlines(), 1):
            if "LAMBDA_MAP" in line or "bundle-fulfillment" in line or "bundle_fulfillment" in line:
                print(f"{i}: {line}")
        print("--- end diagnostic: paste the above so the anchor can be fixed ---")
        sys.exit(1)
    m = matches[0]
    indent = m.group(1)
    add = (
        f'\n{indent}["relayshield_license_service.py"]="relayshield-license-service"'
        f'\n{indent}["relayshield_stripe_license.py"]="relayshield-stripe-license"'
    )
    print(f"OK {label} map: added the two mappings")
    return text[:m.end()] + add + text[m.end():]


def main() -> None:
    if not DEPLOY.exists():
        print(f"FAIL: {DEPLOY} not found. Run from the relayshield repo root.")
        sys.exit(1)
    if not DRIFT.exists():
        print(f"FAIL: {DRIFT} not found. Run from the relayshield repo root.")
        sys.exit(1)

    deploy_text = DEPLOY.read_text()
    deploy_text = edit_paths(deploy_text)
    deploy_text = edit_changed(deploy_text)
    deploy_text = edit_map(deploy_text, "deploy_lambdas.yml")
    DEPLOY.write_text(deploy_text)

    drift_text = DRIFT.read_text()
    drift_text = edit_map(drift_text, "lambda_drift_check.yml")
    DRIFT.write_text(drift_text)

    print("DONE: Phase 3 mapping edits applied (or already present).")
    print("Verify with the grep counts from the deploy sequence.")


if __name__ == "__main__":
    main()
