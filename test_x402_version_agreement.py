"""The OpenAPI spec's per-endpoint x402_version is a claim about what the
live 402 challenge actually sends. It is not read by the challenge code at
all -- _build_payment_requirements decides the real version at request time
from X402_V2_ENABLED_PATHS in relayshield_api.py or relayshield_agentic_api.py,
whichever file owns the path. So the spec and the code are two places that
must agree with nothing checking that they do, and they have already
disagreed once: /v1/payg/secret-scan-text launched 2026-07-31, ten days
after the last V2 migration batch closed, and was simply never added to the
allowlist -- the spec kept saying x402_version: 1 (which was, at the time,
actually true) while every sibling endpoint moved to 2 around it.

Fixing only the spec's number without touching the allowlist would have been
the wrong repair: a client built from the spec would then expect a V2
challenge that the live endpoint never sends, which is worse than the
original staleness -- CLAUDE.md's own "a spec that drifts is worse than no
spec" rule, landing on the version field of an endpoint's price rather than
on missing paths themselves. This guard reads both real sources (the
allowlist sets, not a hand-typed list) and fails if either drifts from the
other, in both directions: spec says 2 where code says 1, or the reverse.
"""
import re
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def _v2_enabled_paths(src: str) -> set[str]:
    m = re.search(r"X402_V2_ENABLED_PATHS: set\[str\] = \{(.*?)\n\}", src, re.S)
    assert m, "could not find X402_V2_ENABLED_PATHS -- the regex broke, not the data"
    return set(re.findall(r'"(/v1/payg/[a-z0-9-]+)"', m.group(1)))


def _spec_versions(src: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for path, version in re.findall(
            r"'(/v1/payg/[a-z0-9-]+)':\s*\{.*?'x402_version':\s*(\d)",
            src, re.S):
        out[path] = int(version)
    return out


class SpecMatchesTheLiveChallengeVersion(unittest.TestCase):
    def setUp(self):
        api_v2 = _v2_enabled_paths((ROOT / "relayshield_api.py").read_text())
        agentic_v2 = _v2_enabled_paths((ROOT / "relayshield_agentic_api.py").read_text())
        self.assertGreater(len(api_v2), 20,
                            "parsed a suspiciously small allowlist from relayshield_api.py "
                            "-- the regex broke, not the data")
        # A path must not be claimed live-V2 by both files -- that would mean
        # the two allowlists disagree about which file even owns the route.
        overlap = api_v2 & agentic_v2
        self.assertFalse(overlap, f"path(s) in both files' V2 allowlists: {overlap}")
        self.live_v2 = api_v2 | agentic_v2

        self.spec = _spec_versions((ROOT / "relayshield_openapi_spec.py").read_text())
        self.assertGreater(len(self.spec), 20,
                            "parsed a suspiciously small spec table -- the regex broke, "
                            "not the data")

    def test_every_spec_entry_matches_the_real_allowlist(self):
        mismatched = []
        for path, spec_version in self.spec.items():
            live_version = 2 if path in self.live_v2 else 1
            if spec_version != live_version:
                mismatched.append((path, spec_version, live_version))
        self.assertFalse(
            mismatched,
            f"spec (version, then real) disagree for: {mismatched} -- a client built "
            f"from the spec will send the wrong x402Version and get a 402 it cannot pay")

    def test_secret_scan_text_specifically_is_v2(self):
        """The exact defect that prompted this guard, pinned directly so a
        future refactor of the regex-based checks above cannot silently stop
        covering the one path that already broke."""
        self.assertIn("/v1/payg/secret-scan-text", self.live_v2)
        self.assertEqual(self.spec.get("/v1/payg/secret-scan-text"), 2)


if __name__ == "__main__":
    unittest.main()
