"""GitLab credential detection, added 2026-09-16 while reading CVE-2026-85706.

WHY THIS EXISTS. There was no GitLab credential pattern anywhere -- not in
relayshield_api.py's NHI_PATTERNS, not in rsscan's mirror, not in the intel
monitor -- while GitHub was covered TWICE. So the corpus count for GitLab
tokens was UNMEASURED, not zero, which is exactly the BOT-TOKEN-1 finding in a
second place. A GitLab token in a criminal channel was collected as ordinary
text and counted as nothing.

It surfaced because CVE-2026-85706 is an unauthenticated arbitrary file read on
self-hosted GitLab whose entire value to an attacker is the credentials inside
the files -- and we could not have recognised one.

EVERY TEST EXECUTES THE REGEX. The pattern tables have been wrong before in ways
reading cannot catch: BOT-TOKEN-1's second entry exists only because RUNNING the
first showed it could not see the commonest leak shape.

THE TEST THIS SUITE EXISTS TO CARRY IS test_routable_is_not_swallowed_by_classic.
`glpat-[\\w-]{20}` matches the first twenty characters of a routable token, so a
table that tries classic first reports the wrong token type with the wrong
remediation and never says it was unsure. Same shape as TON's friendly form
sitting inside Solana's base58 range, which this repo has already paid for.
"""

import ast
import random
import re
import string
import unittest

LOWER = string.ascii_lowercase + string.digits
ALNUM = string.ascii_letters + string.digits


def rnd(n: int, alpha: str = ALNUM) -> str:
    return "".join(random.choice(alpha) for _ in range(n))


def load(path: str, var: str):
    """The (name, regex, severity) triples, in TABLE ORDER.

    Order is read from the file rather than sorted, because order is the thing
    two of these tests are about.
    """
    tree = ast.parse(open(path).read())
    for n in ast.walk(tree):
        tgt = getattr(n, "target", None)
        if tgt is None and isinstance(n, ast.Assign):
            tgt = n.targets[0]
        if getattr(tgt, "id", "") == var and isinstance(n.value, ast.List):
            out = []
            for e in n.value.elts:
                if not isinstance(e.elts[0], ast.Constant):
                    continue
                rx = e.elts[1]
                out.append((e.elts[0].value,
                            rx.value if isinstance(rx, ast.Constant) else None,
                            e.elts[2].value))
            return out
    raise AssertionError(f"{var} not found in {path}")


TABLES = {
    "relayshield_api.py":           ("NHI_PATTERNS", load("relayshield_api.py", "NHI_PATTERNS")),
    "rsscan/rsscan/patterns.py":    ("NHI_PATTERNS", load("rsscan/rsscan/patterns.py", "NHI_PATTERNS")),
    "relayshield_intel_monitor.py": ("_NHI_PATS", load("relayshield_intel_monitor.py", "_NHI_PATS")),
}

EXPECTED = {
    "gitlab_pat_routable", "gitlab_pat", "gitlab_deploy_token",
    "gitlab_runner_token", "gitlab_oauth_secret", "gitlab_agent_token",
    "gitlab_pipeline_trigger", "gitlab_ci_job_token",
}


def gitlab_rules(table):
    return [(n, r, s) for n, r, s in table if n.startswith("gitlab_")]


def first_match(table, text):
    """Resolve the way a scanner walking the table in order would."""
    for name, rx, sev in gitlab_rules(table):
        if rx and re.search(rx, text):
            return name, sev
    return None, None


def sample(kind: str) -> str:
    return {
        "gitlab_pat":              "glpat-" + rnd(20),
        "gitlab_pat_routable":     "glpat-" + rnd(27) + "." + rnd(9, LOWER),
        "gitlab_deploy_token":     "gldt-" + rnd(20),
        "gitlab_runner_token":     "glrt-" + rnd(20),
        "gitlab_oauth_secret":     "gloas-" + rnd(64),
        "gitlab_agent_token":      "glagent-" + rnd(50),
        "gitlab_pipeline_trigger": "glptt-" + rnd(40, "0123456789abcdef"),
        "gitlab_ci_job_token":     "glcbt-" + rnd(5) + "_" + rnd(20),
    }[kind]


class TestCoverageExists(unittest.TestCase):

    def test_all_three_tables_carry_the_same_gitlab_rules(self):
        """Four tables must agree is this repo's most repeated defect shape.

        _LLM_KEY_PATTERNS is the fourth and is deliberately excluded: it is the
        LLMjacking surface and a GitLab token is not an LLM credential.
        """
        for path, (var, table) in TABLES.items():
            with self.subTest(path=path):
                names = {n for n, _, _ in gitlab_rules(table)}
                self.assertEqual(names, EXPECTED, f"{path}:{var} disagrees")

    def test_the_severities_agree_across_tables(self):
        """A token that is CRITICAL in the scanner and HIGH in collection makes
        the same finding mean two things depending on where it was seen."""
        ref = {n: s for n, _, s in gitlab_rules(TABLES["relayshield_api.py"][1])}
        for path, (_, table) in TABLES.items():
            for n, _, s in gitlab_rules(table):
                with self.subTest(path=path, rule=n):
                    self.assertEqual(s, ref[n])

    def test_source_of_truth_and_rsscan_mirror_are_identical(self):
        """rsscan/rsscan/patterns.py is GENERATED by tools/sync_patterns.py.
        A hand edit there drifts silently, which is what --check exists for."""
        self.assertEqual(gitlab_rules(TABLES["relayshield_api.py"][1]),
                         gitlab_rules(TABLES["rsscan/rsscan/patterns.py"][1]))


class TestEachTokenIsRecognised(unittest.TestCase):
    """Executed, not read. A table of cases proves nothing about a regex that
    was never run against the shape it claims to match."""

    def test_every_rule_matches_its_own_token_shape(self):
        table = TABLES["relayshield_api.py"][1]
        for kind in sorted(EXPECTED):
            with self.subTest(kind=kind):
                name, _ = first_match(table, sample(kind))
                self.assertEqual(name, kind)

    def test_routable_is_not_swallowed_by_classic(self):
        """THE ONE THIS SUITE EXISTS FOR.

        Asserts the ORDERING, not merely that both rules exist. Proven by
        swapping the two entries and watching this fail.
        """
        table = TABLES["relayshield_api.py"][1]
        classic = next(r for n, r, _ in gitlab_rules(table) if n == "gitlab_pat")
        token = sample("gitlab_pat_routable")

        # The premise: the classic rule really does match a routable token.
        self.assertTrue(re.search(classic, token),
                        "premise gone: if classic no longer matches a routable "
                        "token this test is no longer testing anything")
        # The property: table order still resolves it correctly.
        self.assertEqual(first_match(table, token)[0], "gitlab_pat_routable")

    def test_routable_wins_in_every_table(self):
        for path, (_, table) in TABLES.items():
            with self.subTest(path=path):
                self.assertEqual(
                    first_match(table, sample("gitlab_pat_routable"))[0],
                    "gitlab_pat_routable")


class TestTheShapesThatActuallyLeak(unittest.TestCase):
    """No _ctx_key on any GitLab rule, deliberately: the `gl*-` prefix carries
    the precision. Requiring an assignment operator would miss all of these,
    which is the defect BOT-TOKEN-1's second entry was added to fix."""

    def ctx_cases(self):
        return [
            ("clone URL",   "git clone https://oauth2:" + sample("gitlab_pat") + "@gitlab.example.com/acme/app.git"),
            ("curl header", "curl --header 'PRIVATE-TOKEN: " + sample("gitlab_pat") + "' https://gitlab.example.com/api/v4/projects"),
            ("CI yaml",     "variables:\n  DEPLOY: " + sample("gitlab_deploy_token")),
            ("runner toml", "  token = \"" + sample("gitlab_runner_token") + "\""),
            ("job log",     "fatal: Authentication failed using " + sample("gitlab_pat")),
        ]

    def test_tokens_are_found_without_an_assignment_operator(self):
        table = TABLES["relayshield_api.py"][1]
        for label, text in self.ctx_cases():
            with self.subTest(label=label):
                self.assertIsNotNone(first_match(table, text)[0],
                                     f"missed a GitLab token in: {label}")


class TestDecoys(unittest.TestCase):
    """A false positive in a pre-commit hook is a developer who disables it."""

    def test_nothing_unrelated_matches(self):
        table = TABLES["relayshield_api.py"][1]
        decoys = {
            "github pat":    "ghp_" + rnd(36),
            "openai key":    "sk-" + rnd(48),
            "prose":         "Put your glpat- token in the CI settings page.",
            "too short":     "glpat-" + rnd(10),
            "word glpat":    "import glpatterns as gp",
            "hex blob":      rnd(64, "0123456789abcdef"),
            "gitlab url":    "https://gitlab.example.com/acme/app/-/blob/main/README.md",
        }
        for label, text in decoys.items():
            with self.subTest(label=label):
                self.assertIsNone(first_match(table, text)[0],
                                  f"false positive on {label}: {text[:40]}")


class TestRemediationIsQueryable(unittest.TestCase):

    def test_every_gitlab_rule_has_a_code_search_prefix(self):
        """The prefix table drives GitHub code search. A rule with no literal
        cannot be hunted for, which is why telegram_bot_token has an empty
        tuple and says so -- GitLab tokens all carry one, so none should."""
        src = open("relayshield_api.py").read()
        tree = ast.parse(src)
        table = None
        for n in ast.walk(tree):
            if isinstance(n, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == "gitlab_pat" for k in n.keys
            ):
                table = {k.value: ast.literal_eval(v)
                         for k, v in zip(n.keys, n.values)
                         if isinstance(k, ast.Constant)}
                break
        self.assertIsNotNone(table, "prefix table not found")
        for rule in sorted(EXPECTED):
            with self.subTest(rule=rule):
                self.assertTrue(table.get(rule), f"{rule} has no search prefix")


if __name__ == "__main__":
    unittest.main(verbosity=2)
