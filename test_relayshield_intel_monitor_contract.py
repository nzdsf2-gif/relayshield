"""Guard the extract_iocs() <-> _store_iocs() type_map contract.

This has broken silently twice. Both times extract_iocs() was pulling a new
indicator class out of every monitored message and _store_iocs()'s type_map
never listed it, so every one of those indicators was extracted, counted in the
stats, and then dropped on the floor. Nothing failed; the corpus was just
quietly smaller than the logs claimed. The first occurrence cost the CVE history
(found 2026-07-24), the second cost five more types (found 2026-08-20).

The failure is invisible at runtime by construction -- a missing key is simply a
loop iteration that never happens -- so it needs a static check.

Parses the source with `ast` instead of importing the module:
relayshield_intel_monitor pulls in telethon and boto3, and a contract test that
only runs where those are installed is a contract test that stops running.
"""

import ast
import sys
import unittest
from pathlib import Path

MONITOR = Path(__file__).with_name("relayshield_intel_monitor.py")

# extract_iocs returns these but _store_iocs must NOT map them, with a reason.
# Anything dropped without a reason recorded here is the bug this test exists
# to catch.
INTENTIONALLY_UNMAPPED = {
    "ransomware_victims": "stored by _store_victims into relayshield_ransomware_victims, "
                          "which is a different table with a different confidence",
}


def _module() -> ast.Module:
    return ast.parse(MONITOR.read_text())


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in {MONITOR.name}")


def extracted_keys() -> set[str]:
    """Keys of the dict literal extract_iocs() returns."""
    fn = _function(_module(), "extract_iocs")
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return {
                k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    raise AssertionError("extract_iocs() has no dict return literal")


def mapped_fields() -> dict[str, str]:
    """field -> ioc_type pairs from _store_iocs()'s type_map list literal."""
    fn = _function(_module(), "_store_iocs")
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "type_map" for t in node.targets)
                and isinstance(node.value, ast.List)):
            pairs = {}
            for elt in node.value.elts:
                if (isinstance(elt, ast.Tuple) and len(elt.elts) == 2
                        and all(isinstance(e, ast.Constant) for e in elt.elts)):
                    pairs[elt.elts[0].value] = elt.elts[1].value
            return pairs
    raise AssertionError("_store_iocs() has no type_map list literal")


class TestIocContract(unittest.TestCase):
    def test_every_extracted_type_is_stored_or_explicitly_excused(self):
        extracted = extracted_keys()
        mapped = set(mapped_fields())
        dropped = extracted - mapped - set(INTENTIONALLY_UNMAPPED)
        self.assertEqual(
            dropped, set(),
            "extract_iocs() produces these and _store_iocs() never persists them, so "
            "they are extracted and thrown away:\n  "
            + "\n  ".join(sorted(dropped))
            + "\n\nAdd each to type_map, or to INTENTIONALLY_UNMAPPED with the reason.",
        )

    def test_no_mapping_for_a_type_that_is_never_extracted(self):
        """The mirror image: a type_map entry whose field extract_iocs() no longer
        returns is dead, and reads as coverage that does not exist."""
        orphans = set(mapped_fields()) - extracted_keys()
        self.assertEqual(
            orphans, set(),
            "type_map maps fields extract_iocs() never returns: " + ", ".join(sorted(orphans)),
        )

    def test_excuses_still_apply(self):
        """An excused key that is now mapped, or no longer extracted, means this
        file has drifted from the code and should be re-read rather than trusted."""
        extracted, mapped = extracted_keys(), set(mapped_fields())
        for key in INTENTIONALLY_UNMAPPED:
            self.assertIn(key, extracted, f"{key} is excused but no longer extracted")
            self.assertNotIn(key, mapped, f"{key} is excused but is now mapped — drop the excuse")

    def test_ioc_types_are_unique(self):
        """Two fields sharing an ioc_type would silently merge two indicator
        classes into one bucket."""
        pairs = mapped_fields()
        types = list(pairs.values())
        dupes = {t for t in types if types.count(t) > 1}
        self.assertEqual(dupes, set(), f"ioc_type reused across fields: {sorted(dupes)}")

    def test_the_five_types_found_missing_on_2026_08_20_are_still_mapped(self):
        """Regression pin for the second occurrence, so a refactor cannot quietly
        undo it."""
        mapped = mapped_fields()
        for field, ioc_type in (
            ("tg_mentions", "tg_handle"),
            ("onions", "onion"),
            ("md5", "hash_md5"),
            ("sha1", "hash_sha1"),
            ("cves", "cve"),
        ):
            self.assertEqual(mapped.get(field), ioc_type,
                             f"{field} lost its {ioc_type} mapping again")


if __name__ == "__main__":
    unittest.main(verbosity=2)
