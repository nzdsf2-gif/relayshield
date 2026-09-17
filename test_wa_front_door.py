"""The WhatsApp front door: the link, the token, and the order they run in.

WHAT THIS EXISTS TO STOP, in one sentence each.

1. THE PARSE RUNNING AFTER THE USER LOOKUP. A front-door arrival is BY
   DEFINITION somebody we have never seen, and the handler's `if not user`
   branch sends a welcome and returns 200. So a parse placed after the lookup
   attributes every arrival the link ever produces to nothing, forever, while
   reading perfectly in a diff. That is the only defect here that cannot be
   seen by running the code, so it is checked against source ORDER.

2. A wa.me LINK WITH A HOLE IN IT. wa.me answers a malformed or missing number
   with HTTP 200 and a "phone number shared via url is invalid" page, not a
   404 -- so a broken front door looks live to every probe we own. Both
   Workers render nothing at all while WA_NUMBER is unset.

3. THE TWO WORKERS DRIFTING APART. Two constants that must agree with nothing
   checking that they do is the shape this repo has paid for five times.

4. A RAW PHONE NUMBER IN CLOUDWATCH. Personal data, and log retention is not
   where we get to decide it stops being that.
"""

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WA_PY = ROOT / "relayshield_whatsapp_webhook.py"
BLOG_JS = ROOT / "cloudflare_worker_blog.js"
MINI_JS = ROOT / "cloudflare_worker_miniapp.js"

WA_SRC = WA_PY.read_text(encoding="utf-8")


def strip_js_comments(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    js = re.sub(r"(?m)^\s*//.*$", " ", js)
    js = re.sub(r"<!--.*?-->", " ", js, flags=re.S)
    return js


def load_parser():
    """Execute parse_wa_source itself, without importing the handler.

    The module imports boto3 and builds clients at import time. Lifting the
    two definitions out and exec'ing them runs the REAL source -- a copy of
    the regex written into the test would prove only that the copy works.
    """
    tree = ast.parse(WA_SRC)
    wanted = {"WA_SOURCE_RE", "parse_wa_source"}
    picked = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            picked.append(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in wanted:
                    picked.append(node)
    ns = {"re": re}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "<wa>", "exec"), ns)
    return ns["parse_wa_source"]


parse_wa_source = load_parser()


class TestTheTokenParse(unittest.TestCase):
    """EXECUTED against real message shapes, never grepped."""

    def test_a_bare_prefill_yields_the_key_and_an_empty_body(self):
        self.assertEqual(parse_wa_source("SRC_wa-blog"), ("wa-blog", ""))

    def test_the_token_is_stripped_so_the_first_real_command_survives(self):
        # This is the whole reason it is stripped. The prefill IS the user's
        # first message; anything they typed after it is a real instruction,
        # and leaving the token in front of it hands our command parsing a
        # string it has never seen.
        self.assertEqual(parse_wa_source("SRC_wa-blog SCAN"), ("wa-blog", "SCAN"))
        self.assertEqual(parse_wa_source("SRC_wa-miniapp check this"),
                         ("wa-miniapp", "check this"))

    def test_case_is_irrelevant(self):
        for raw in ("src_wa-blog", "Src_Wa-Blog", "SRC_WA-BLOG"):
            self.assertEqual(parse_wa_source(raw)[0], "wa-blog", raw)

    def test_a_hyphen_is_accepted_because_a_retype_is_the_likely_slip(self):
        self.assertEqual(parse_wa_source("SRC-wa-blog")[0], "wa-blog")

    def test_trailing_punctuation_a_human_would_add(self):
        self.assertEqual(parse_wa_source("SRC_wa-blog. hello"), ("wa-blog", "hello"))

    def test_an_ordinary_message_is_returned_untouched(self):
        for raw in ("SCAN", "", "check https://example.com", "SRCwa-blog",
                    "please SRC_wa-blog"):
            key, body = parse_wa_source(raw)
            self.assertEqual(key, "", raw)
            self.assertEqual(body, raw, raw)

    def test_a_long_key_is_truncated_rather_than_stored_whole(self):
        key, _ = parse_wa_source("SRC_" + "a" * 100)
        self.assertLessEqual(len(key), 32)


class TestTheParseRunsBeforeTheUserLookup(unittest.TestCase):
    """THE DEFECT THAT CANNOT BE SEEN BY RUNNING THE CODE.

    Both orderings pass every behavioural test above, because they test the
    parser in isolation. Only source order distinguishes "attributes every
    front-door arrival" from "attributes none of them, forever"."""

    def handler_body(self) -> str:
        tree = ast.parse(WA_SRC)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "handler":
                return ast.get_source_segment(WA_SRC, node) or ""
        self.fail("no handler() in the WhatsApp webhook")

    def test_parse_wa_source_is_called_before_get_user_by_whatsapp(self):
        body = self.handler_body()
        parse_at = body.find("parse_wa_source(")
        lookup_at = body.find("get_user_by_whatsapp(")
        self.assertNotEqual(parse_at, -1, "handler never calls parse_wa_source")
        self.assertNotEqual(lookup_at, -1, "handler never looks the user up")
        self.assertLess(
            parse_at, lookup_at,
            "parse_wa_source must run BEFORE get_user_by_whatsapp. A "
            "front-door arrival is an unknown number, and the unknown branch "
            "returns 200 -- so parsing after the lookup attributes nothing, "
            "forever, and looks correct in the diff")

    def test_the_source_is_logged_in_the_shape_the_funnel_counts(self):
        # The funnel filters this literal out of a log group. A second
        # spelling means a second filter, and a filter written against what
        # the code SHOULD log is the false absence this repo has had four of.
        self.assertIn('"acquisition source=%s wa=%s"', WA_SRC)
        funnel = (ROOT / "tools" / "miniapp_funnel.py").read_text(encoding="utf-8")
        self.assertIn('r"acquisition source=(wa-[a-z0-9-]*)"', funnel,
                      "the funnel has no WhatsApp stage, so arrivals are "
                      "uncountable and a zero would be meaningless")


class TestNoRawPhoneNumberIsLogged(unittest.TestCase):

    def test_the_inbound_line_hashes_the_number(self):
        self.assertIn(
            "hash_phone(from_number), len(message_body), num_media", WA_SRC,
            "the inbound log line must hash the number; it wrote a customer's "
            "phone number in the clear into CloudWatch on every message")

    def test_no_logger_call_passes_from_number_raw(self):
        tree = ast.parse(WA_SRC)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name) and f.value.id == "logger"):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id == "from_number":
                    bad.append(getattr(node, "lineno", "?"))
        self.assertEqual(bad, [],
                         f"raw from_number passed to logger at lines {bad}")


class TestTheLinkIsNeverRenderedWithAHole(unittest.TestCase):

    BLOG = BLOG_JS.read_text(encoding="utf-8")
    MINI = MINI_JS.read_text(encoding="utf-8")

    NUM = re.compile(r'^const WA_NUMBER = "([^"]*)";', re.M)

    def numbers(self):
        b = self.NUM.search(self.BLOG)
        m = self.NUM.search(self.MINI)
        self.assertIsNotNone(b, "cloudflare_worker_blog.js has no WA_NUMBER")
        self.assertIsNotNone(m, "cloudflare_worker_miniapp.js has no WA_NUMBER")
        return b.group(1), m.group(1)

    def test_the_two_workers_agree(self):
        blog, mini = self.numbers()
        self.assertEqual(blog, mini,
                         "the blog Worker and the Mini App must carry the same "
                         "WhatsApp number; two constants that must agree with "
                         "nothing checking them is how this drifts")

    def test_the_number_is_bare_digits_or_empty(self):
        # wa.me rejects "+", spaces and punctuation by rendering an "invalid"
        # page with a 200 status, so a wrong shape here is a link that passes
        # every probe and reaches nobody.
        for name, value in zip(("blog", "miniapp"), self.numbers()):
            if value == "":
                continue
            self.assertRegex(value, r"^[1-9]\d{6,14}$",
                             f"{name}: WA_NUMBER must be bare E.164 digits "
                             f"with no leading + and no spaces, got {value!r}")

    def test_an_unset_number_renders_no_link_in_either_worker(self):
        blog, mini = self.numbers()
        if blog or mini:
            self.skipTest("the number is set, so this branch is not the live one")
        # Comments are stripped FIRST. Both files explain the wa.me trap in
        # prose directly above the code, and a guard that searched the raw
        # source would match its own explanation -- which is the failure this
        # suite has now recorded seven times.
        for name, src in (("blog", self.BLOG), ("miniapp", self.MINI)):
            self.assertNotIn("wa.me/\"", strip_js_comments(src), name)
            self.assertNotIn("https://wa.me/?", strip_js_comments(src), name)

    def test_the_miniapp_slot_is_substituted_not_read_from_worker_scope(self):
        # Worker scope is not page scope. A constant declared in the Worker
        # and read from inside the PAGE template is a ReferenceError at load
        # that node --check cannot see -- the INLINE_TEXT defect.
        code = strip_js_comments(self.MINI)
        self.assertIn("__WA_LINK__", code,
                      "the page must take the link through a substitution")
        self.assertIn('.replaceAll("__WA_LINK__", waLink())', code,
                      "the Worker must substitute __WA_LINK__ at request time")


class TestTheLinkToolRefusesABadNumber(unittest.TestCase):
    TOOL = ROOT / "tools" / "wa_front_door_link.py"

    def run_tool(self, number):
        return subprocess.run(
            [sys.executable, str(self.TOOL), "--number", number],
            capture_output=True, text=True)

    def test_a_good_number_prints_bare_digits_and_every_route(self):
        r = self.run_tool("+15551234567")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('WA_NUMBER = "15551234567"', r.stdout)
        for key in ("wa-blog", "wa-miniapp", "wa-devs"):
            self.assertIn(f"?text=SRC_{key}", r.stdout)

    def test_a_malformed_number_is_refused_rather_than_printed(self):
        for bad in ("not-a-number", "555", "+0123456789"):
            r = self.run_tool(bad)
            self.assertNotEqual(r.returncode, 0, f"{bad!r} was accepted")
            self.assertIn("E.164", r.stderr)

    def test_every_route_key_the_tool_prints_matches_the_funnel_filter(self):
        # A key the tool hands out that the funnel cannot match is a link that
        # is tapped, logged, and counted as nothing.
        r = self.run_tool("+15551234567")
        keys = re.findall(r"\?text=SRC_([a-z0-9-]+)", r.stdout)
        self.assertTrue(keys)
        wa_key = re.compile(r"^wa-[a-z0-9-]*$")
        for k in keys:
            self.assertRegex(k, wa_key,
                             f"{k!r} does not match the funnel's wa- filter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
