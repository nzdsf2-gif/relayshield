#!/usr/bin/env python3
"""Fail when the intel pipeline's parallel vocabularies drift apart.

WHY THIS EXISTS
---------------
This pipeline has now shipped the SAME class of defect three times:

  1. `cves` — extract_iocs() produced them, _store_iocs()'s type_map never
     listed them, so not one CVE was ever persisted. Found 2026-07-24.
  2. Five more IOC types (tg_mentions, onions, md5, sha1, ransomware_victims)
     with the identical cause. Found 2026-08-20.
  3. Channel categories — relayshield_intel_discovery.py and
     relayshield_intel_classifier.py could both assign "ransomware", "crypto"
     and "phaas", which appeared in neither CATEGORY_LABELS nor SEVERITY, so
     alerts from those channels rendered with no severity word and a raw
     category key. A ransomware channel displayed as less severe than a card
     shop. Found 2026-08-21.

Every one was silent: no exception, no log line, no failing request. The common
shape is two lists in two places that must agree and nothing checking that they
do. This checks it.

PARSED, NOT IMPORTED. These modules import boto3 and telethon at module level
and construct AWS clients on import, so this reads the source with `ast`
instead. That also means the test runs anywhere, including CI, with no
credentials and no dependencies.

Run: python3 test_intel_category_drift.py   (exit 0 = agree, 1 = drifted)
"""

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent

MONITOR    = ROOT / "relayshield_intel_monitor.py"
CLASSIFIER = ROOT / "relayshield_intel_classifier.py"
DISCOVERY  = ROOT / "relayshield_intel_discovery.py"

failures: list[str] = []


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _assign(tree: ast.Module, name: str):
    """The value node of a module-level `name = ...`, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return node.value
    return None


def _literal(tree: ast.Module, name: str, path: pathlib.Path):
    node = _assign(tree, name)
    if node is None:
        failures.append(f"{path.name}: `{name}` not found — was it renamed? "
                        f"This test is now blind to whatever replaced it.")
        return None
    try:
        return ast.literal_eval(node)
    except ValueError:
        failures.append(f"{path.name}: `{name}` is no longer a literal and "
                        f"cannot be checked statically.")
        return None


# ---------------------------------------------------------------------------
# 1. Channel categories agree across all four places that assign or render one
# ---------------------------------------------------------------------------

def check_categories() -> None:
    mon, cls, dis = _tree(MONITOR), _tree(CLASSIFIER), _tree(DISCOVERY)

    canonical = _literal(mon, "INTEL_CATEGORIES", MONITOR)
    valid     = _literal(cls, "VALID_CATEGORIES", CLASSIFIER)
    seeds     = _literal(dis, "CROSS_PROMOTION_SEED_CATEGORIES", DISCOVERY)
    pivots    = _literal(mon, "PIVOT_SEED_CATEGORIES", MONITOR)
    keywords  = _literal(dis, "SEARCH_KEYWORDS", DISCOVERY)
    if canonical is None:
        return

    known = set(canonical)

    # Every category the monitor knows must carry BOTH a label and a severity.
    # This is what actually renders on a user alert.
    for cat, pair in canonical.items():
        if not (isinstance(pair, tuple) and len(pair) == 2 and all(pair)):
            failures.append(
                f"INTEL_CATEGORIES['{cat}'] must be a (label, severity) pair, "
                f"both non-empty — got {pair!r}")

    # The classifier assigns categories directly onto channel rows. Anything it
    # can emit that the monitor cannot render degrades every future alert from
    # that channel, silently.
    if valid is not None:
        for cat in sorted(set(valid) - known):
            failures.append(
                f"relayshield_intel_classifier.VALID_CATEGORIES has '{cat}', "
                f"which is missing from INTEL_CATEGORIES. The classifier can "
                f"assign it; the monitor would render a raw key and no severity.")
        for cat in sorted(known - set(valid)):
            failures.append(
                f"INTEL_CATEGORIES has '{cat}' but the classifier cannot assign "
                f"it — a dead branch in the alert formatter, like card_shop was.")

    # Discovery infers a category from the keyword that matched.
    if keywords is not None:
        for entry in keywords:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                continue
            _kw, cat = entry
            if cat not in known:
                failures.append(
                    f"relayshield_intel_discovery.SEARCH_KEYWORDS assigns "
                    f"'{cat}' (keyword {_kw!r}), which is not in INTEL_CATEGORIES.")

    # These two only SELECT from existing categories, so they need to be a
    # subset. A stale name here silently narrows collection instead of widening
    # it — the crawl or the pivot quietly stops covering that category.
    for label, subset, where in (
        ("CROSS_PROMOTION_SEED_CATEGORIES", seeds,  "relayshield_intel_discovery"),
        ("PIVOT_SEED_CATEGORIES",           pivots, "relayshield_intel_monitor"),
    ):
        if subset is None:
            continue
        for cat in sorted(set(subset) - known):
            failures.append(
                f"{where}.{label} names '{cat}', which is not a real category. "
                f"It selects nothing and no error is raised.")


# ---------------------------------------------------------------------------
# 2. Every IOC type extract_iocs() returns is persisted by _store_iocs()
# ---------------------------------------------------------------------------
# This is defects 1 and 2 above, which is why it is here and not only in a
# comment. `type_map` is a list of (extract_iocs field, ioc_type) pairs; a field
# produced but not mapped is collected and thrown away.

# Fields deliberately not written to the IOC table, each with its reason.
# Anything else that goes unmapped is a bug until proven otherwise.
INTENTIONALLY_UNMAPPED = {
    # Victim ORGANISATIONS, not attacker indicators. They have their own table
    # (relayshield_ransomware_victims); writing them here would let a customer's
    # own company name match as though it were an IOC.
    "ransomware_victims",
}


def check_ioc_type_map() -> None:
    tree = _tree(MONITOR)

    extracted: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "extract_iocs":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    for k in sub.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            extracted.add(k.value)
            break
    if not extracted:
        failures.append("Could not read extract_iocs()'s returned dict — this "
                        "test is no longer checking the type_map defect.")
        return

    mapped: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_store_iocs":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name) and t.id == "type_map":
                            try:
                                for field, _ioc_type in ast.literal_eval(sub.value):
                                    mapped.add(field)
                            except ValueError:
                                failures.append(
                                    "_store_iocs.type_map is no longer a literal "
                                    "and cannot be checked statically.")
            break
    if not mapped:
        failures.append("Could not read _store_iocs()'s type_map — this test is "
                        "no longer checking the type_map defect.")
        return

    for field in sorted(extracted - mapped - INTENTIONALLY_UNMAPPED):
        failures.append(
            f"extract_iocs() returns '{field}' but _store_iocs()'s type_map "
            f"never stores it. Every value of this type is being extracted and "
            f"discarded — the exact `cves` defect. Add it to type_map, or to "
            f"INTENTIONALLY_UNMAPPED in this test with the reason.")

    for field in sorted(mapped - extracted):
        failures.append(
            f"_store_iocs()'s type_map reads '{field}', which extract_iocs() "
            f"does not return. That mapping stores nothing.")


def main() -> int:
    check_categories()
    check_ioc_type_map()

    if failures:
        print("INTEL VOCABULARY DRIFT\n" + "=" * 70)
        for f in failures:
            print(f"  ✗ {f}\n")
        print(f"{len(failures)} problem(s). Each one fails silently in "
              f"production — that is why this test exists.")
        return 1

    print("✅ intel vocabularies agree (categories + IOC type_map)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
