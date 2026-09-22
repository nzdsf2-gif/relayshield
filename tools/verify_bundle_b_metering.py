#!/usr/bin/env python3
"""Did a metered call actually LAND against one Bundle B product code?

READ ONLY. Shells out to the AWS CLI -- no boto3, because a tool that adds a
dependency adds a reason it can fail that the reader cannot see (the
wa_front_door_link.py lesson).

WHY THIS EXISTS RATHER THAN tools/diagnose_bundle_b_audit.sh SECTION 5.

  1. THAT SECTION SEARCHES THREE LOG STRINGS AND THE FUNCTION WRITES SIX.
     The three it misses are exactly the ones the 2026-09-21 fix ADDED --
     "NOT metered", "UNPROCESSED", "no Results". So a REJECTED metering record
     printed "none" there, which reads identically to "nothing was ever
     metered" and is a completely different finding. The patterns here are
     EXTRACTED from relayshield_api.py rather than retyped, and the extraction
     asserts a floor: fewer than five and it raises rather than reporting a
     false absence.

  2. IT PRINTS THE DECISIVE SECTION LAST. Three rounds on 2026-09-21 ended with
     a pasted terminal cut off before section 5. The VERDICT here is printed
     FIRST, from values gathered before anything is written to the screen.

  3. THE LOG LINE CANNOT NAME THE PRODUCT, AND THAT IS THE WHOLE DIFFICULTY.
     _report_marketplace_usage logs account= and dimension=. The product is
     carried in the LicenseArn, which is not logged, and `is_bundle_b_call` is

         bool(key_record["bundle_b_access"]) and bool(key_record["aws_customer_id"])
         and path in BUNDLE_B_DIMENSION_NAMES

     -- it never looks at the product code. So a key row provisioned against
     the WRONG Bundle B product meters happily against the wrong licence, and
     the log line looks identical. The product code is a property of the KEY
     ROW, so the join is: key row -> (aws_account_id, aws_license_arn) -> the
     log lines carrying that account on a Bundle B dimension.
"""
import ast
import json
import re
import subprocess
import sys
import time

ACCOUNT = "239677749008"
LOG_GROUP = "/aws/lambda/relayshield-api"
KEY_TABLE = "relayshield_api_keys"
DEFAULT_CODE = "cmh79gzztkdtp0dlzbdepa643"
SOURCE = "relayshield_api.py"
CODE_RE = re.compile(r"^[a-z0-9]{25}$")


def aws(*args, **kw):
    """Returns (ok, text). NEVER RAISES.

    The first version let subprocess.TimeoutExpired propagate, so a slow read
    killed the process before the VERDICT printed and the run produced a
    traceback instead of an answer. Verdict-first is worthless if a failure in
    gathering can prevent the verdict being reached at all: every read here
    returns a recorded error and the verdict is always printed.

    A CLI error comes back VERBATIM -- a summary of a refusal is how
    AccessDenied and ExpiredToken become one indistinguishable 'it did not
    work'."""
    try:
        p = subprocess.run(["aws", "--no-cli-pager", *args],
                           capture_output=True, text=True,
                           timeout=kw.get("timeout", 120))
    except subprocess.TimeoutExpired:
        return False, (f"timed out after {kw.get('timeout', 120)}s: aws "
                       + " ".join(args[:3]))
    except FileNotFoundError:
        return False, "the AWS CLI is not on PATH."
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip()
    return True, p.stdout.strip()


def log_patterns():
    """The substrings _report_marketplace_usage can write, read out of the
    function that writes them with `ast` -- NOT by searching the text.

    The first version of this used a regex over the function body and returned
    a bare "Marketplace usage" plus a truncated "Marketplace usage reported",
    because the function's own DOCSTRING explains the logging convention and
    therefore contains the words. That is the seventh time in this repo that
    prose describing a rule has been matched by the guard for it, and it is
    why strip-the-comments is supposed to be in the FIRST version. `ast` walks
    the logger calls themselves, so prose cannot reach it at all.
    """
    tree = ast.parse(open(SOURCE, encoding="utf-8").read())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == "_report_marketplace_usage"), None)
    if fn is None:
        raise SystemExit(f"REFUSED: no _report_marketplace_usage in {SOURCE}.")
    pats = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        fmt = node.args[0].value
        if not isinstance(fmt, str):
            continue
        # CloudWatch filter patterns are literals, so the substring stops at
        # the first %-placeholder. Implicit concatenation is already joined by
        # the parser, which the regex version could not do either.
        frag = fmt.split("%")[0].strip()
        if frag and frag not in pats:
            pats.append(frag)
    if len(pats) < 5:
        raise SystemExit(
            f"REFUSED: extracted only {len(pats)} log patterns from {SOURCE}.\n"
            "       The function writes six. An under-extracted filter reports a\n"
            "       live failure as 'none', which is the defect this tool exists\n"
            "       to end. Fix the extraction before trusting any verdict.")
    return pats


def main():
    code = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CODE).strip()
    if code.startswith("prod-"):
        raise SystemExit(
            f"REFUSED: {code!r} is a Catalog API ENTITY ID, not a product code.\n"
            "       A product code is what ResolveCustomer returns at fulfillment\n"
            "       and what BatchMeterUsage bills against.")
    if not CODE_RE.match(code):
        raise SystemExit(
            f"REFUSED: {code!r} is not a product code (25 lowercase alphanumerics).\n"
            "       A 40-hex value is a git commit SHA. The real one is on the key\n"
            "       row as aws_product_code, or in the Management Portal.")

    ok, acct = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text")
    if not ok:
        raise SystemExit(f"Could not reach AWS. Verbatim:\n{acct}")
    if acct != ACCOUNT:
        raise SystemExit(
            f"REFUSED: credentials resolve to {acct}, not {ACCOUNT}.\n"
            "       Re-run with AWS_PROFILE=relayshield.")

    print(f"Reading key rows and 14 days of {LOG_GROUP}. Read-only, ~30s.",
          file=sys.stderr)

    # 1. The key rows that name this product code. This is the ONLY thing that
    #    ties metering to a product, for the reason in the docstring.
    ok, raw = aws("dynamodb", "scan", "--table-name", KEY_TABLE,
                  "--filter-expression", "aws_product_code = :c",
                  "--expression-attribute-values", json.dumps({":c": {"S": code}}),
                  "--projection-expression",
                  "aws_customer_id, aws_account_id, aws_license_arn, bundle_b_access",
                  "--output", "json")
    rows, rows_err = [], ""
    if not ok:
        rows_err = raw
    else:
        for it in json.loads(raw).get("Items", []):
            rows.append({k: list(v.values())[0] for k, v in it.items()})

    accounts = {r.get("aws_account_id", "") for r in rows if r.get("aws_account_id")}

    # 1b. DOES THAT ACCOUNT METER FOR ANY OTHER PRODUCT?
    #
    # The log line names the ACCOUNT and the DIMENSION, never the product. So
    # "a success line carrying an account that holds a key row for this product
    # code" is one notch weaker than "metered against this product code", and
    # the notch matters precisely here: three SaaS products carry the Bundle B
    # display name, and if this account also holds a meterable key row under a
    # DIFFERENT product code then the record could belong to that one.
    #
    # A key row can only meter when it carries a licence ARN, so the question
    # is how many DISTINCT product codes this account holds a licenced row for.
    # One means the attribution is unambiguous. More than one means it is not,
    # and saying so is the whole reason this step exists.
    siblings, sib_err = {}, ""
    for acct in sorted(a for a in accounts if a):
        ok, raw = aws("dynamodb", "scan", "--table-name", KEY_TABLE,
                      "--filter-expression", "aws_account_id = :a",
                      "--expression-attribute-values", json.dumps({":a": {"S": acct}}),
                      "--projection-expression",
                      "aws_product_code, aws_license_arn",
                      "--output", "json")
        if not ok:
            sib_err = raw
            break
        for it in json.loads(raw).get("Items", []):
            r = {k: list(v.values())[0] for k, v in it.items()}
            if r.get("aws_license_arn"):
                siblings.setdefault(r.get("aws_product_code", "(none)"), set()).add(acct)

    # 2. Every metering line, in ONE Logs Insights query.
    #
    # THIS SHIPPED ON filter-log-events AND TIMED OUT AFTER 180 SECONDS ON THE
    # FIRST PATTERN, having printed nothing. filter-log-events is a SCAN: it
    # returns a nextToken to keep walking log streams even when the page it
    # just returned held no match, so a rare pattern over 14 days of
    # /aws/lambda/relayshield-api -- the busiest group we have -- is thousands
    # of sequential round trips. --max-items 25 does not bound it either; it
    # bounds MATCHES, so a pattern with no matches walks the whole group.
    #
    # tools/miniapp_funnel.py and tools/ti_demo_metrics.py each paid for this
    # already and CLAUDE.md records both. This is the third time, and writing
    # it down twice evidently did not stop me, so the shape is here in the
    # file that would otherwise repeat it: if a read is over a log group and
    # it is not Insights, it is a scan.
    #
    # One query for all six substrings rather than six queries: the
    # classification back to a pattern is done client-side below, so the
    # filter and the classifier cannot drift apart.
    since = int(time.time() - 14 * 86400)
    now = int(time.time())
    pats = log_patterns()
    where = " or ".join(f'@message like "{p}"' for p in pats)
    query = f"fields @timestamp, @message | filter {where} | sort @timestamp desc | limit 200"

    found = {p: [] for p in pats}
    log_err = ""
    print("  querying Logs Insights (one query, ~15s) ...", file=sys.stderr, flush=True)
    ok, out = aws("logs", "start-query", "--log-group-name", LOG_GROUP,
                  "--start-time", str(since), "--end-time", str(now),
                  "--query-string", query, "--limit", "200",
                  "--query", "queryId", "--output", "text")
    if not ok:
        log_err = out
    else:
        qid, deadline = out.strip(), time.time() + 120
        while True:
            ok, raw = aws("logs", "get-query-results", "--query-id", qid,
                          "--output", "json", timeout=60)
            if not ok:
                log_err = raw
                break
            resp = json.loads(raw)
            status = resp.get("status")
            if status == "Complete":
                for row in resp.get("results", []):
                    msg = next((f.get("value", "") for f in row
                                if f.get("field") == "@message"), "")
                    msg = msg.strip()
                    for pat in pats:
                        if pat in msg:
                            found[pat].append(msg)
                            break
                break
            if status in ("Failed", "Cancelled", "Timeout"):
                log_err = f"Insights returned status {status} -- the query did not run."
                break
            if time.time() >= deadline:
                aws("logs", "stop-query", "--query-id", qid, timeout=30)
                log_err = ("Insights did not finish inside 120s. That is a fact "
                           "about the query, NOT a zero.")
                break
            time.sleep(2)

    succeeded = [l for p, ls in found.items() if "status=Success" in p or "reported" in p
                 for l in ls if "status=Success" in l]
    rejected = [l for p, ls in found.items() for l in ls
                if "NOT metered" in l or "UNPROCESSED" in l or "no Results" in l]
    never = [l for p, ls in found.items() for l in ls if "Skipping bundle usage report" in l]
    ours = [l for l in succeeded if any(a and a in l for a in accounts)]

    # ---- VERDICT FIRST. Everything above ran silently so this survives a
    #      terminal that truncates.
    print("=" * 72)
    print(f"VERDICT for product code {code}")
    print("=" * 72)
    if rows_err or log_err:
        print("  COULD NOT TELL. A read was refused, so this is a fact about the")
        print("  identity or the network and NOT about the metering. Do not read")
        print("  it as a zero. Verbatim error is in the evidence below.")
    elif not rows:
        print("  NO KEY ROW carries this product code.")
        print("  So nothing can ever have metered against it: the licence ARN")
        print("  BatchMeterUsage needs is only ever read off a key row.")
        print("  -> The fulfillment redirect for this product has not provisioned")
        print("     a key. Submitting for visibility now will be refused again.")
    elif ours and len(siblings) == 1 and code in siblings:
        print(f"  YES. {len(ours)} successful metering record(s), and the attribution")
        print("  is unambiguous: the account that produced them holds a meterable")
        print(f"  key row for {code} and for no other product code.")
        print("  -> This is the evidence AWS's audit error 2 asks for.")
    elif ours and sib_err:
        print(f"  PROBABLY, NOT PROVEN. {len(ours)} successful metering record(s) from")
        print("  an account that holds a meterable key row for this product code.")
        print("  The read that would rule out a sibling product was refused, so")
        print("  the attribution is unconfirmed rather than confirmed.")
    elif ours:
        others = sorted(k for k in siblings if k != code)
        print(f"  NOT PROVEN. {len(ours)} successful metering record(s) from an account")
        print("  that holds a meterable key row for this product code -- AND for:")
        for k in others:
            print(f"      {k}")
        print("  The log line names the account and the dimension, never the")
        print("  product, so these records cannot be attributed to one of them.")
        print("  -> Resolve the duplicate key rows before resubmitting, or the")
        print("     audit may be reading the same ambiguity.")
    elif succeeded:
        print(f"  NO -- and this is the dangerous one. {len(succeeded)} metering call(s)")
        print("  SUCCEEDED, but none carries an account that holds a key row for")
        print(f"  {code}. Something metered against a DIFFERENT product.")
        print("  -> Read the accounts in the evidence against the key rows below.")
    elif rejected:
        print(f"  NO. {len(rejected)} metering call(s) were made and AWS REJECTED them.")
        print("  BatchMeterUsage returned 200 and the records did not land.")
        print("  -> The audit is right. Fix the rejection reason before resubmitting.")
    elif never:
        print(f"  NO. {len(never)} call(s) were served and never metered at all")
        print("  (missing account, licence ARN or dimension on the key row).")
        print("  -> A key that cannot meter cannot clear audit error 2.")
    else:
        print("  NO METERING LINES AT ALL in the last 14 days.")
        print("  The fix that writes these lines IS deployed -- deploy_lambdas")
        print("  run 159 shipped 4f0ca0e and logged 'relayshield-api imports")
        print("  cleanly' at 2026-09-21T20:01:54Z, which carries 447105b. So for")
        print("  any call after that time this means no metered Bundle B endpoint")
        print("  was called at all, NOT that logging is missing.")
        print("  -> There is nothing for AWS's audit to find. A metered call has")
        print("     to be MADE with this product's key before resubmitting.")
    print()

    print("-" * 72)
    print(f"EVIDENCE 1. Key rows with aws_product_code = {code}")
    if rows_err:
        print(f"  could not read, verbatim: {rows_err}")
    elif not rows:
        print("  none")
    for r in rows:
        print(f"  account={r.get('aws_account_id','') or '(none)'}"
              f"  customer={r.get('aws_customer_id','') or '(none)'}"
              f"  bundle_b_access={r.get('bundle_b_access','')}")
        print(f"    licence: {r.get('aws_license_arn','') or '(NONE -- cannot meter)'}")

    print()
    print("-" * 72)
    print("EVIDENCE 1b. Product codes this account can meter for")
    print("  (a key row can only meter if it carries a licence ARN)")
    if sib_err:
        print(f"  could not read, verbatim: {sib_err}")
    elif not siblings:
        print("  none")
    for pc, accts in sorted(siblings.items()):
        mark = "  <-- the one asked about" if pc == code else "  <-- ANOTHER PRODUCT"
        print(f"  {pc}{mark}")
        print(f"    accounts: {', '.join(sorted(accts))}")

    print()
    print("-" * 72)
    print(f"EVIDENCE 2. Metering lines, last 14 days, {LOG_GROUP}")
    if log_err:
        print(f"  could not read, verbatim: {log_err}")
    for pat in found:
        print(f"  -- {pat}")
        for line in found[pat] or ["     none"]:
            print(f"     {line}")
    print()
    print("Nothing above wrote to AWS.")


if __name__ == "__main__":
    main()
