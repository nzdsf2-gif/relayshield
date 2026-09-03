"""The landing page's source-attribution table must stay coherent.

    python3 test_developer_signup_banners.py

Parses relayshield_developer_signup.py with ast rather than importing it, so it
runs anywhere: no boto3, no AWS, no network.

WHY THIS EXISTS
---------------
Every failure this guards has already happened at least once.

* ?source=rsscan shipped in a published PyPI package pointing at a key that did
  not exist. Every arrival logged unmatched: and rendered no banner.
* rsscan was later ALIASED to "github" while also having a banner of its own.
  The alias wins in _resolve_source, so the specific banner was unreachable --
  a key that exists and still renders the wrong thing, which is worse than a
  missing key because nothing looks broken.
* The official MCP registry pointed at a bare URL with no key for four months.
* On 2026-09-03 the live function was found holding eight banners main had
  never seen. Reconciling that by hand is exactly when a table like this loses
  an entry silently.

So: aliases must resolve, aliases must not shadow banners, and the keys that
have been paid for in incidents must still be there.
"""

import ast
import sys
import unittest

SOURCE = "relayshield_developer_signup.py"

# Keys that exist because an incident, a listing or a published link created
# them. Losing one is a regression even though nothing raises.
REQUIRED = {
    "langchain", "apify", "mcp-registry", "tg-widget", "n8n", "x402",
    "discord-bot", "npm-worm", "fourth-party", "ansible-galaxy", "bluenoroff",
    "rsscan", "rsscan-deps", "metamask-snap",
}


def _table(tree, name):
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node.value
    raise AssertionError(f"{name} not found in {SOURCE}")


def _keys(tree, name):
    return [k.value for k in _table(tree, name).keys if isinstance(k, ast.Constant)]


class TestSourceBanners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SOURCE) as fh:
            cls.tree = ast.parse(fh.read())
        cls.banners = _keys(cls.tree, "_SOURCE_BANNERS")
        cls.aliases = _table(cls.tree, "_SOURCE_ALIASES")

    def alias_pairs(self):
        return [(k.value, v.value)
                for k, v in zip(self.aliases.keys, self.aliases.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)]

    def test_no_duplicate_banner_keys(self):
        dupes = {k for k in self.banners if self.banners.count(k) > 1}
        self.assertFalse(dupes, f"duplicate banner keys, the later wins: {dupes}")

    def test_no_duplicate_alias_keys(self):
        raw = [k for k, _ in self.alias_pairs()]
        dupes = {k for k in raw if raw.count(k) > 1}
        self.assertFalse(dupes, f"duplicate alias keys: {dupes}")

    def test_every_alias_resolves_to_a_registered_banner(self):
        unresolved = sorted({v for _, v in self.alias_pairs() if v not in self.banners})
        self.assertFalse(unresolved,
                         f"aliases point at keys with no banner: {unresolved}. "
                         "_resolve_source logs unmatched: and renders nothing.")

    def test_no_alias_shadows_a_banner_of_its_own(self):
        # _resolve_source does aliases.get(raw, raw) BEFORE looking at the
        # banner table, so a key that is both an alias source and a banner key
        # can never reach its own banner. This is the rsscan bug exactly.
        shadowed = sorted({k for k, v in self.alias_pairs()
                           if k in self.banners and v != k})
        self.assertFalse(shadowed,
                         f"these have a banner AND an alias pointing elsewhere, so their "
                         f"own banner is unreachable: {shadowed}")

    def test_keys_bought_with_incidents_are_still_registered(self):
        missing = sorted(REQUIRED - set(self.banners))
        self.assertFalse(missing, f"registered banner keys have been lost: {missing}")

    def test_tg_widget_claims_no_referer_hosts(self):
        # Deliberate, and the reason is in the source: the widget always appends
        # ?source=tg-widget, so claiming t.me would attribute every un-keyed
        # click from our own bot and blog channel to third-party installs.
        for key, value in zip(self.banners, _table(self.tree, "_SOURCE_BANNERS").values):
            if key == "tg-widget":
                hosts = value.elts[0]
                self.assertEqual(len(hosts.elts), 0,
                                 "tg-widget must claim no referer hosts")
                return
        self.fail("tg-widget not registered")

    def test_no_referer_host_is_claimed_by_two_banners(self):
        # First match wins in _resolve_source's referer loop, and dict order is
        # not a decision anyone made.
        seen = {}
        clashes = []
        for key, value in zip(self.banners, _table(self.tree, "_SOURCE_BANNERS").values):
            for host in value.elts[0].elts:
                if isinstance(host, ast.Constant):
                    if host.value in seen:
                        clashes.append(f"{host.value}: {seen[host.value]} and {key}")
                    seen[host.value] = key
        self.assertFalse(clashes, f"referer hosts claimed twice: {clashes}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
