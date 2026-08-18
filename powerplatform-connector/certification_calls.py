#!/usr/bin/env python3
"""Exercise every connector operation enough times to satisfy certification.

Microsoft requires each operation to have been called successfully, at least
ten times, before a connector is submitted. Twelve operations by ten calls is
the 120 figure. Calls spread across only some operations do NOT satisfy this,
which is the usual cause of a resubmission.

These are METERED endpoints and every successful call is billable. The script
prints an estimate and refuses to run without --run.

    export RELAYSHIELD_API_KEY=...
    python3 certification_calls.py                 # dry run, shows the plan
    python3 certification_calls.py --run           # actually calls
    python3 certification_calls.py --run --only CheckSimSwap
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("RELAYSHIELD_BASE", "https://api.relayshield.net")
CALLS_PER_OP = 10

# Distinct, realistic inputs. Ten different values per operation, so the calls
# look like genuine use rather than one payload replayed ten times.
DOMAINS = ["acme.com", "contoso.com", "fabrikam.com", "northwindtraders.com",
           "adventure-works.com", "wingtiptoys.com", "litwareinc.com",
           "proseware.com", "tailspintoys.com", "woodgrovebank.com"]
EMAILS = ["user%d@%s" % (i, d) for i, d in enumerate(DOMAINS, 1)]
PHONES = ["+1415555%04d" % (1000 + i) for i in range(10)]
IPS = ["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222", "4.2.2.2",
       "64.6.64.6", "77.88.8.8", "80.80.80.80", "84.200.69.80", "185.228.168.9"]
BINS = ["411111", "510510", "378282", "601111", "353011",
        "222100", "401288", "555555", "300000", "620000"]
SECRET_SAMPLES = [
    "config = { 'token': 'placeholder-value-%d' }" % i for i in range(10)
]

OPS = [
    ("CheckEmailBreach",       "/v1/metered/breach",              [{"email": e} for e in EMAILS]),
    ("CheckSimSwap",           "/v1/metered/sim-swap",            [{"phone": p} for p in PHONES]),
    ("CheckLookalikeDomains",  "/v1/metered/domain",              [{"domain": d} for d in DOMAINS]),
    ("CheckOAuthWatchlist",    "/v1/metered/oauth-watchlist",     [{"email": e} for e in EMAILS]),
    ("CheckInfostealer",       "/v1/metered/infostealer",         [{"email": e} for e in EMAILS]),
    ("CheckVendorRisk",        "/v1/metered/supply-chain",        [{"vendor_domains": [d]} for d in DOMAINS]),
    ("ScanTextForSecrets",     "/v1/metered/secret-scan-text",    [{"content": c, "filename": "sample.py"} for c in SECRET_SAMPLES]),
    ("CheckSessionRisk",       "/v1/metered/session-risk",        [{"email": e} for e in EMAILS]),
    ("GetIdentityRiskScore",   "/v1/metered/identity-risk-score", [{"domain": d} for d in DOMAINS]),
    ("CheckCertificateExpiry", "/v1/metered/cert-expiry",         [{"domain": d} for d in DOMAINS]),
    ("CheckCardExposure",      "/v1/metered/card-exposure",       [{"bin": b} for b in BINS]),
    ("CheckIpReputation",      "/v1/metered/ip-intel",            [{"ip": i} for i in IPS]),
]


def call(path, payload, key, timeout=45):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode()[:300] or "")
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="actually issue the billable calls")
    ap.add_argument("--only", help="run a single operationId")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between calls")
    args = ap.parse_args()

    ops = [o for o in OPS if not args.only or o[0] == args.only]
    if not ops:
        sys.exit("no operation named %r" % args.only)

    total = len(ops) * CALLS_PER_OP
    print("%d operations x %d calls = %d billable calls against %s"
          % (len(ops), CALLS_PER_OP, total, BASE))
    if not args.run:
        for name, path, _ in ops:
            print("  %-24s %s" % (name, path))
        print("\nDry run. Re-run with --run to issue them.")
        return

    key = os.environ.get("RELAYSHIELD_API_KEY")
    if not key:
        sys.exit("RELAYSHIELD_API_KEY is not set")

    results, failures = {}, []
    for name, path, payloads in ops:
        ok = 0
        for i in range(CALLS_PER_OP):
            status, body = call(path, payloads[i % len(payloads)], key)
            if status == 200:
                ok += 1
            else:
                failures.append((name, status, body))
            print("  %-24s %2d/%d  HTTP %s" % (name, i + 1, CALLS_PER_OP, status), flush=True)
            time.sleep(args.delay)
        results[name] = ok

    print("\n%-24s %s" % ("OPERATION", "SUCCESSFUL CALLS"))
    short = []
    for name, ok in results.items():
        flag = "" if ok >= CALLS_PER_OP else "   <-- SHORT"
        if ok < CALLS_PER_OP:
            short.append(name)
        print("%-24s %2d/%d%s" % (name, ok, CALLS_PER_OP, flag))

    if failures:
        print("\nFirst few failures:")
        for name, status, body in failures[:8]:
            print("  %s HTTP %s %s" % (name, status, str(body)[:160]))

    if short:
        print("\nNOT READY. These operations are short of %d successful calls: %s"
              % (CALLS_PER_OP, ", ".join(short)))
        sys.exit(1)
    print("\nAll operations have %d successful calls. Certification prerequisite met." % CALLS_PER_OP)


if __name__ == "__main__":
    main()
