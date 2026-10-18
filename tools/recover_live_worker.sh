#!/bin/sh
# Download a DEPLOYED Cloudflare Worker's source, so it can be diffed against
# the repo BEFORE anything is redeployed over it.
#
#   sh tools/recover_live_worker.sh relayshield-ti-demo cloudflare_worker_ti_demo.js
#
# WHY THIS EXISTS. The DRIFT RULE in CLAUDE.md has carried the same open item
# for weeks: "The TI demo Cloudflare Worker -- still outstanding.
# recover_live_handler.yml does this for Lambdas. Nothing does it for Workers
# yet." So every Worker in this repo has the exact combination that has now cost
# this repo three recoveries: source in the repo, live traffic, and no way to
# see what is actually deployed.
#
# relayshield-ti-demo is the worst of them. No workflow deploys it -- grep
# .github/workflows and nothing matches -- so every version of it that ever went
# live was pushed by hand from somebody's machine, and a hand-deployed Worker is
# precisely where an uncommitted edit survives. `wrangler deploy` would replace
# it with the repo copy and report success.
#
# wrangler has no download command. The Workers API does, and it is one GET.
#
# KNOWN LIMIT: it compares ONE repo file against the whole deployed bundle. A Worker that
# imports other repo modules (cloudflare_worker_blog.js pulls in blog_posts.js and two
# image modules) has those modules inlined in the bundle, so every name from them is
# reported as live-only however clean the deploy is. Pass such a Worker's own file and
# read the list knowing that; it is not drift. Verified 2026-10-18 by bundling every
# cloudflare_worker_*.js and shopify/worker.js through esbuild --keep-names: all compare
# clean except that one.
#
# READ-ONLY. It writes a file into the scratch directory and never near the
# repo copy, so the diff is something you look at rather than something that has
# already overwritten your working tree.
set -e

SCRIPT_NAME=$1
REPO_FILE=$2
[ -n "$SCRIPT_NAME" ] || { echo "usage: $0 <worker-script-name> [repo-file-to-diff]"; exit 2; }

# The token is READ, never taken as an argument and never assigned inline: an
# argument is in the process table and in shell history, and this one can deploy
# Workers. `read -rs` is the zsh form and works in sh here too; -s suppresses
# the echo. Needs "Workers Scripts: Read" at minimum.
if [ -z "$CF_API_TOKEN" ]; then
  printf 'Cloudflare API token (input hidden): '
  stty -echo 2>/dev/null || true
  read CF_API_TOKEN
  stty echo 2>/dev/null || true
  printf '\n'
fi
[ -n "$CF_API_TOKEN" ] || { echo "no token, nothing to do"; exit 2; }

# THE ACCOUNT ID IS DISCOVERED, NOT ASKED FOR, AND THE FIRST VERSION ASKED.
# It prompted "Cloudflare account id:" and the answer was an EMAIL ADDRESS --
# which is a perfectly reasonable thing to type at that prompt, and produced a
# 404 whose reading guide said "no deployed script by that name", sending the
# reader to check the Worker. The Worker was never the problem. A Cloudflare
# account id is a 32-character hex string buried in the dashboard sidebar, and
# a prompt that does not say so is rule 11's placeholder wearing a question
# mark: it looks like an instruction to whoever wrote it and is unanswerable to
# whoever reads it.
#
# The token can list the accounts it can see, so the question does not need
# asking at all. One extra GET removes a whole class of wrong answer.
if [ -z "$CF_ACCOUNT_ID" ]; then
  ACCTS="${TMPDIR:-/tmp}/cf-accounts.json"
  ACODE=$(curl -sS -o "$ACCTS" -w '%{http_code}' \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    "https://api.cloudflare.com/client/v4/accounts?per_page=50" 2>/dev/null) || true
  if [ "$ACODE" = "200" ]; then
    # PARSED, NOT GREPPED. The first version matched '"id":"..."' with no
    # space after the colon and silently extracted nothing from JSON that had
    # one -- an empty result that reads identically to "the token sees no
    # accounts". Grepping JSON is the same class as grepping the source of a
    # template literal: it works until the shape shifts by one character.
    CF_ACCOUNT_ID=$(python3 - "$ACCTS" <<'PYEOF'
import json, sys
try:
    rows = json.load(open(sys.argv[1])).get("result") or []
except Exception:
    rows = []
for r in rows:
    if isinstance(r, dict) and isinstance(r.get("id"), str) and len(r["id"]) == 32:
        print(r["id"]); break
PYEOF
)
    NAMES=$(python3 - "$ACCTS" <<'PYEOF'
import json, sys
try:
    rows = json.load(open(sys.argv[1])).get("result") or []
except Exception:
    rows = []
print(", ".join(str(r.get("name", "?")) for r in rows if isinstance(r, dict)))
PYEOF
)
    if [ -n "$CF_ACCOUNT_ID" ]; then
      echo "Account discovered from the token: $CF_ACCOUNT_ID"
      echo "  (accounts this token can see: $NAMES)"
      # MORE THAN ONE ACCOUNT IS A DECISION, NOT A DEFAULT. Taking the first
      # silently is how a read lands in the wrong account -- the same shape as
      # AWS_PROFILE defaulting to the pre-audit account.
      COUNT=$(python3 -c "import json,sys;print(len(json.load(open(sys.argv[1])).get('result') or []))" "$ACCTS" 2>/dev/null || echo 1)
      if [ "$COUNT" != "1" ]; then
        echo "  NOTE: $COUNT accounts are visible and the FIRST was taken. If the"
        echo "  Worker is in another one, re-run with CF_ACCOUNT_ID set."
      fi
    fi
  else
    echo "Could not list accounts (HTTP $ACODE). Body:"
    cat "$ACCTS" 2>/dev/null; echo
  fi
fi

if [ -z "$CF_ACCOUNT_ID" ]; then
  echo "No account id, and the token could not list one."
  echo "Find it in the Cloudflare dashboard: open any zone, and the right-hand"
  echo "sidebar shows 'Account ID' as a 32-character hex string. It is NOT an"
  echo "email address and NOT the account name."
  exit 2
fi

# Validated rather than trusted, because the failure it prevents reads as a
# missing Worker. `expr` for portability: sh has no [[ =~ ]].
if ! expr "$CF_ACCOUNT_ID" : '[0-9a-f]\{32\}$' >/dev/null; then
  echo "That is not a Cloudflare account id: $CF_ACCOUNT_ID"
  echo "It must be exactly 32 hexadecimal characters. An email address or an"
  echo "account name here returns a 404 that reads like a missing Worker."
  exit 2
fi

OUT="${TMPDIR:-/tmp}/live-worker-$SCRIPT_NAME.js"
API="https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME"

echo "GET $API"
# `|| true` because `set -e` would otherwise ABORT HERE ON A FAILED CONNECTION,
# silently and with exit 0 further down the pipe -- caught by running it against
# a blocked host rather than by reading it. A script that cannot reach the API
# must SAY SO; exiting quietly is the worst of the three outcomes, because it
# reads as "nothing to recover".
CODE=$(curl -sS -o "$OUT" -w '%{http_code}' \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Accept: application/javascript" "$API" 2>"${TMPDIR:-/tmp}/cf-curl.err") || true

if [ -z "$CODE" ] || [ "$CODE" = "000" ]; then
  echo "NO ANSWER from the Cloudflare API. This says NOTHING about the Worker:"
  echo "it is a fact about this machine's network, not about what is deployed."
  cat "${TMPDIR:-/tmp}/cf-curl.err" 2>/dev/null
  exit 1
fi

# THE BODY IS PRINTED ON A FAILURE, NOT A SUMMARY OF IT. A 403 from a token
# missing Workers:Read and a 404 from a misspelled script name are different
# problems with different fixes, and the status code alone separates neither
# from "this Worker was never deployed under that name".
if [ "$CODE" != "200" ]; then
  echo "HTTP $CODE -- not recovered. Body:"
  cat "$OUT"; echo
  echo
  echo "  403  the token cannot read Workers Scripts. Mint one with that scope."
  echo "  404  no deployed script by that name in this account. Check the name"
  echo "       against the 'name' line in the matching wrangler.*.toml, and"
  echo "       check you are in the right Cloudflare account."
  exit 1
fi

echo "Recovered $(wc -c < "$OUT") bytes -> $OUT"

[ -n "$REPO_FILE" ] || exit 0
[ -f "$REPO_FILE" ] || { echo "no such repo file: $REPO_FILE"; exit 2; }

echo
echo "=============================================================="
echo "DIFF: repo ($REPO_FILE) vs LIVE"
echo "=============================================================="
if diff -u "$REPO_FILE" "$OUT" > "${TMPDIR:-/tmp}/worker-drift.diff"; then
  echo "IDENTICAL. The repo copy is what is deployed, so a redeploy is safe"
  echo "and there is nothing to recover."
else
  echo "THEY DIFFER. Full diff: ${TMPDIR:-/tmp}/worker-drift.diff"
  echo
  head -60 "${TMPDIR:-/tmp}/worker-drift.diff"
  echo
  echo "  READ IT BEFORE DEPLOYING ANYTHING. A line present on the LIVE side"
  echo "  and in no commit is hand-deployed work, and 'wrangler deploy' would"
  echo "  delete it with no error anywhere. Recover it into git FIRST, exactly"
  echo "  as the four Lambda handlers were on 2026-08-26."
  echo
  echo "=============================================================="
  echo "BUT A RAW DIFF CANNOT ANSWER THIS, AND THE FIRST VERSION OF"
  echo "THIS SCRIPT PRETENDED IT COULD."
  echo "=============================================================="
  cat <<'WHY'
  wrangler bundles with esbuild before it uploads, and esbuild STRIPS
  COMMENTS. So the API hands back a BUILD ARTEFACT and this script was
  diffing it against the SOURCE. Those are different documents by
  construction, and a heavily commented Worker therefore reports
  "THEY DIFFER" in thousands of lines while being identical in every
  line that executes.

  Measured on relayshield-checkemail, 2026-09-21: the repo file is
  79,906 bytes with comments and about 41,000 without; the deployed
  script is 44,106. The diff was comments.

  That made "only IDENTICAL makes the deploy safe" UNREACHABLE for any
  Worker deployed through wrangler -- a guard that can never pass, which
  is a guard that gets ignored. Same family as the template-literal
  defect: verify the artefact at the right end of the pipe.

  THE COMPARISON BELOW IS THE ONE THAT ANSWERS THE QUESTION. It extracts
  every identifier and every string literal from each side and reports
  what exists in LIVE and in no commit. Comments in the source cannot
  create a live-only token, and wrangler does not minify by default, so
  names survive the bundle. An empty list means there is nothing
  deployed that the repo does not have.
WHY
  echo
  python3 - "$REPO_FILE" "$OUT" <<'PYEOF'
import re, sys

# THE DOWNLOAD IS NOT THE BUNDLE. The Workers API returns a multipart/form-data
# BODY: a boundary line, Content-Disposition and Content-Type headers, the bundle,
# and a closing boundary. wrangler/esbuild then adds its own `// <file>` banner, a
# `var <stem>_default` name for the default export, a sourceMappingURL comment, and
# escapes non-ASCII as \uXXXX / \xXX. None of that is hand-deployed code, and the
# first version of this comparison reported all of it as "live carries something the
# repo does not": on relayshield-privacy, 2026-10-11, eight names, every one of them
# one of these. A check that cries wolf on a clean Worker gets ignored, and then the
# day it is right nobody reads it.
_MULTIPART = re.compile(
    r"^(--[0-9A-Za-z'()+_,./:=?-]{16,}(--)?|Content-(Disposition|Type):.*|//# sourceMappingURL=.*)$")


# esbuild's --keep-names (wrangler turns it on) rewrites every function and class so
# its name survives bundling, in three shapes:
#     __name(fn, "fn");                                     after a declaration
#     var f = /* @__PURE__ */ __name((x) => ..., "f");      around an expression
#     __name(this, "K");                                    inside a class constructor
# plus two helper lines that define it. Every one of those name strings is a copy of
# an identifier the source already has, and the helper's own parameters (`target`,
# `configurable`) are not in the source at all. Reported as "LIVE carries something the
# repo does not" on relayshield-order-screening, 2026-10-17: 2 identifiers and 47
# strings, every one of them this. A regex over lines cannot do it, because the second
# shape spans arbitrary nested code: find each call's matching paren and cut only the
# trailing name string. Cutting NOTHING ELSE is the point: a hand-added string literal
# inside the call, or anywhere else, must still be reported.
_NAME_ARG = re.compile(r',\s*"[A-Za-z_$][A-Za-z0-9_$]*"\s*$')


def _skip_quoted(t, i):
    """t[i] opens a string or template literal; return the index just past it."""
    q = t[i]
    i += 1
    while i < len(t):
        c = t[i]
        if c == "\\":
            i += 2
            continue
        if q == "`" and c == "$" and t[i + 1:i + 2] == "{":
            i = _skip_balanced(t, i + 1, "{", "}")
            continue
        if c == q:
            return i + 1
        i += 1
    return i


def _skip_balanced(t, i, op, cl):
    """t[i] == op; return the index just past the matching close, quotes honoured."""
    depth = 0
    while i < len(t):
        c = t[i]
        if c in "\"'`":
            i = _skip_quoted(t, i)
            continue
        if c == op:
            depth += 1
        elif c == cl:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def strip_keep_names(text):
    cuts = []
    for m in re.finditer(r"\b__name\(", text):
        end = _skip_balanced(text, m.end() - 1, "(", ")")
        inner = text[m.end():end - 1]
        # Only a TRAILING plain string argument is the injected name.
        tail = _NAME_ARG.search(inner)
        if tail:
            cuts.append((m.end() + tail.start(), m.end() + tail.end()))
    for a, b in sorted(cuts, reverse=True):
        text = text[:a] + text[b:]
    # The helper definitions: `var __defProp = ...;` and `var __name = ...;`.
    return re.sub(r"^var __[A-Za-z0-9_$]+ = [^\n]*;[ \t]*$", "", text, flags=re.M)


def clean_live(text, stem):
    out = []
    for line in text.splitlines():
        if _MULTIPART.match(line.strip()):
            continue
        out.append(line)
    text = "\n".join(out)
    # esbuild's `// <path>.js` banner. The path is the entry as wrangler saw it, which
    # is not the basename: `// shopify/worker.js` for a file in a subdirectory.
    text = re.sub(r"^// \S+\.js\s*$", "", text, flags=re.M)
    return strip_keep_names(text)


# THE STRING EXTRACTOR IS A LEXER, NOT A REGEX. The first one was
#     '([^'\\\n]{4,})'   and   "([^"\\\n]{4,})"
# and it fails in three ways that each produce live-only strings out of a clean
# Worker, found by bundling every Worker in the repo through esbuild and comparing:
#   * the 4-character minimum sits INSIDE the pattern, so `"raw"` (3) is not matched,
#     the scan resumes at its closing quote, and every later pair on the line is
#     matched one quote out of step. The two sides lay a line out differently, so they
#     fall out of step in different places.
#   * a comment with an apostrophe ("doesn't") or a regex literal (/'/g) opens a
#     string that is not one. The source has comments and the bundle does not.
#   * esbuild folds "a " + "b" into "a b", a string the source never contains whole.
# So: skip comments and regex literals, pair quotes properly, keep strings of every
# length until the end, and treat a run of up to 8 adjacent source strings joined
# together as known. Nothing is dropped from the LIVE side except what is provably
# the source's own text.
_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KW = ("return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await", "delete")


def js_strings(src):
    out, i, n, prev, word = [], 0, len(src), "", ""
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            out.append((src[i + 1:j], i, j + 1))
            i, prev, word = j + 1, c, ""
        elif c == "`":
            i, prev, word = _skip_quoted(src, i), "`", ""
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "/" and (prev == "" or prev in _REGEX_PREV or word in _REGEX_KW):
            j, in_class = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            i, prev, word = j + 1, "/", ""
        else:
            if c.isalnum() or c in "_$":
                word = (word + c) if (prev == "w") else c
                prev = "w"
            elif not c.isspace():
                prev, word = c, ""
            i += 1
    return out


# esbuild re-quotes every string with the quote that needs fewer escapes, and writes any
# non-ASCII character as \uXXXX or \u{X}. So 'say "hi"' in the source is "say \"hi\"" in
# the bundle, and a literal arrow is \u2190. Compared as written, a clean Worker differs
# from its own bundle in every such string; compared as VALUES they are equal.
_ESC = re.compile(r"\\(u\{[0-9A-Fa-f]+\}|u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|\r?\n|.)", re.S)
_UNI = re.compile(r"\\(u\{[0-9A-Fa-f]+\}|u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2})")
_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _one(m, only_unicode=False):
    g = m.group(1)
    if g[0] == "u":
        return chr(int(g[2:-1] if g[1] == "{" else g[1:], 16))
    if g[0] == "x" and len(g) == 3:
        return chr(int(g[1:], 16))
    if only_unicode:
        return m.group(0)
    if g in ("\n", "\r\n"):
        return ""
    return _SIMPLE.get(g, g)


def _repair(x):
    # \ud83d\ude00 decodes to two lone surrogates; make them the one character.
    try:
        return x.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeError:
        return x


def js_value(piece):
    return _repair(_ESC.sub(_one, piece))


def tokens(path, live=False):
    src = open(path, encoding="utf-8", errors="replace").read()
    if live:
        import os
        src = clean_live(src, os.path.basename(sys.argv[1]).rsplit(".", 1)[0])
    # Identifiers of 3+ characters: shorter ones are loop variables and noise.
    # Simple escapes (\n, \t) are blanked first: "\n\nIt often" would otherwise yield the
    # identifier `nIt`, which the source never contains because there the string is split.
    flat = _repair(_UNI.sub(lambda m: _one(m, True), src))
    idents = set(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]{2,}",
                            re.sub(r"\\[ntrbfv0]", " ", flat)))
    spans = js_strings(src)
    pieces = [js_value(v) for v, _, _ in spans]
    # esbuild folds "a " + "b" into "a b". Only strings joined by a bare `+` are folded
    # by it, so every contiguous run inside such a chain is a value the bundle may hold.
    # Chains are short; a long run of unrelated strings is NOT chained, which keeps this
    # linear in practice and stops it vouching for strings that were never adjacent.
    known = set()
    a = 0
    while a < len(spans):
        b = a
        while b + 1 < len(spans) and src[spans[b][2]:spans[b + 1][1]].strip() == "+":
            b += 1
        for x in range(a, b + 1):
            acc = ""
            for y in range(x, b + 1):
                acc += pieces[y]
                known.add(acc)
        a = b + 1
    strings = {x for x in pieces if len(x) >= 4}
    return idents, strings, known

# Filtered so the CLEAN case reports zero and the verdict is unambiguous. A
# list that always has four rows in it is a list nobody reads.
#   __-prefixed  esbuild's own helpers (__toESM, __defProp, __commonJS)
#   keywords     a keyword the source happens not to use is not drift
BUNDLER = re.compile(r"^(__|[ux][0-9A-Fa-f]{2,4}$)")  # esbuild helpers, and \\u2190 / \\xA9 escapes
KEYWORDS = {
    "var", "let", "const", "function", "return", "typeof", "instanceof",
    "await", "async", "class", "extends", "super", "yield", "delete", "void",
    "null", "true", "false", "undefined", "this", "new", "throw", "catch",
    "finally", "switch", "case", "default", "continue", "break", "else",
    "while", "for", "try", "import", "export", "from", "static", "get", "set",
    "Object", "defineProperty", "prototype", "hasOwnProperty", "call", "apply",
}

def strip_noise(names):
    import os
    stem = re.sub(r"[^A-Za-z0-9_$]", "_", os.path.basename(sys.argv[1]).rsplit(".", 1)[0])
    # esbuild names the default export `<stem>_default`; a source map is `map`.
    own = {stem, stem + "_default", "map", "sourceMappingURL"}
    return {n for n in names if not BUNDLER.match(n) and n not in KEYWORDS and n not in own}

r_id, r_str, r_known = tokens(sys.argv[1])
l_id, l_str, _ = tokens(sys.argv[2], live=True)
r_id, l_id = strip_noise(r_id), strip_noise(l_id)

only_id = sorted(l_id - r_id)
only_str = sorted(l_str - r_str - r_known)

print("  identifiers in LIVE and not in the repo : %d" % len(only_id))
for t in only_id[:40]:
    print("      %s" % t)
if len(only_id) > 40:
    print("      ... and %d more" % (len(only_id) - 40))
print()
print("  string literals in LIVE and not in the repo : %d" % len(only_str))
for t in only_str[:25]:
    print("      %r" % t[:100])
if len(only_str) > 25:
    print("      ... and %d more" % (len(only_str) - 25))
print()
if not only_id and not only_str:
    print("  NOTHING IS DEPLOYED THAT THE REPO DOES NOT HAVE.")
    print("  The raw diff above is comments and bundling. A redeploy is safe.")
else:
    print("  LIVE CARRIES SOMETHING THE REPO DOES NOT. Read the names above")
    print("  before deploying: wrangler deploy would delete whatever they")
    print("  belong to, with no error anywhere. Recover it into git first.")
    print()
    print("  esbuild's own helpers and bare keywords are already filtered out,")
    print("  so anything listed above is a real name that only the deployed")
    print("  script has.")
PYEOF
fi
