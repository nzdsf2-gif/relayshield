#!/usr/bin/env python3
"""The hosted MCP URL is named in several files. They must not disagree.

FD-15 is the decision that a stranger gets ONE hosted URL, whichever directory
they arrived from. That decision is only worth anything if the files that carry
the URL agree, and there is no reason to expect them to: they are edited months
apart, by different sessions, for different destinations.

This repo has paid for that shape repeatedly -- the deployer's LAMBDA_MAP against
iam_github_deploy_invoke.json, marketplace.json against plugin.json, four copies
of one pattern table. Every time, both files were individually correct and the
pair was wrong, and nothing said so.

The specific failure here is worse than untidy. If smithery.yaml advertises a URL
that check_hf_space.py does not probe, then the URL handed to strangers is the
one nothing watches, and the watcher goes green while the listing 404s. That is
the quiet alarm pointed at exactly the wrong target.

No pyyaml, no network: this must run anywhere, including a fresh checkout in CI.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SMITHERY = ROOT / "mcp_registry" / "smithery.yaml"
WATCHER = ROOT / "tools" / "check_hf_space.py"
WORKFLOW = ROOT / ".github" / "workflows" / "hf_space_watch.yml"


def _smithery() -> str:
    return SMITHERY.read_text(encoding="utf-8")


def _watcher() -> str:
    return WATCHER.read_text(encoding="utf-8")


def _config_only() -> str:
    """smithery.yaml without its comments.

    The file explains WHY it no longer runs `uvx`, so a naive
    "assertNotIn('uvx')" fails on the explanation rather than on a regression.
    An assertion about configuration must read configuration; the comments are
    prose and are allowed to name the thing they are warning about.
    """
    return "\n".join(line for line in _smithery().splitlines()
                      if not line.lstrip().startswith("#"))


class TestHostedPointer(unittest.TestCase):
    def test_smithery_advertises_the_url_the_watcher_probes(self):
        advertised = re.search(r"^\s*url:\s*(\S+)\s*$", _config_only(), re.M).group(1)

        w = _watcher()
        owner = re.search(r'^OWNER\s*=\s*"([^"]+)"', w, re.M).group(1)
        path = re.search(r'^MCP_PATH\s*=\s*"([^"]+)"', w, re.M).group(1)
        # The public Space, which is the one a Smithery visitor gets: the -aws
        # Space scrubs the signup page for AWS's Tier-1 audit and is wrong here.
        space = re.search(r'\(\s*"public",\s*"([^"]+)"', w).group(1)
        probed = f"https://{owner}-{space}.hf.space{path}"

        self.assertEqual(advertised, probed,
                         "smithery.yaml advertises a URL the watcher does not probe")

    def test_it_is_the_public_space_not_the_aws_one(self):
        """The -aws Space runs the same code with AWS_MARKETPLACE_MODE=true,
        which removes every reference to the signup page. Pointing a public
        directory at it would hide the way to buy from everyone who arrives."""
        self.assertNotIn("-aws.hf.space", _config_only())

    def test_the_target_is_remote_and_the_stdio_command_is_gone(self):
        """A stdio listing tells a visitor to install a Python package. That is
        a different listing for a different visitor, and having it here is what
        made FD-11 look blocked when it was not."""
        s = _config_only()
        self.assertTrue(re.search(r"^target:\s*remote\s*$", s, re.M),
                        "smithery.yaml does not declare target: remote")
        self.assertNotIn("commandFunction", s)
        self.assertNotIn("uvx", s)
        self.assertNotIn("stdio", s)

    def test_the_cli_reads_these_two_keys_so_they_must_be_present(self):
        """@smithery/cli 4.11.1 parses {name?, target?} and keeps the rest.
        Everything else in that file is documentation."""
        s = _config_only()
        # re.search with re.M, not assertRegex: assertRegex dumps the ENTIRE
        # file into the failure message, which buries the one line that matters.
        self.assertTrue(re.search(r"^name:\s*\S+\s*$", s, re.M), "no top-level name:")
        self.assertTrue(re.search(r"^target:\s*(local|remote)\s*$", s, re.M),
                        "no top-level target:")

    def test_the_watcher_actually_checks_the_mcp_path(self):
        """A front door returning 200 says the Gradio app serves a web page. It
        says nothing about whether the MCP route is mounted, and that route is
        the entire product from a directory visitor's point of view."""
        w = _watcher()
        self.assertIn("def _probe_mcp", w)
        self.assertIn("mcp_url", w)
        self.assertIn("base + MCP_PATH", w)

    def test_a_missing_mcp_endpoint_is_DOWN_and_not_a_warning(self):
        """404 and 405 on the advertised path are unambiguous: it is not there.
        Only an unambiguous answer may block, and this one must."""
        w = _watcher()
        block = w[w.index("mcp_code in (404, 405, 410)"):]
        block = block[:block.index("elif mcp_ok")]
        self.assertIn('"DOWN", 1', block)

    def test_an_inconclusive_mcp_probe_does_not_cry_wolf(self):
        """A waking Space refuses connections for a minute. A probe that cannot
        tell has no standing to stop the work, or the alarm gets ignored."""
        w = _watcher()
        self.assertIn("waking or mcp_code is None", w)

    def test_the_workflow_runs_the_checker_and_can_open_an_issue(self):
        y = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("tools/check_hf_space.py", y)
        self.assertIn("hf-space-down", y)
        self.assertIn("schedule:", y)


if __name__ == "__main__":
    unittest.main(verbosity=2)
