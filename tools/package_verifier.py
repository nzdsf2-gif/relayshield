#!/usr/bin/env python3
"""Build the verifier Lambda zip, and prove it is complete before anyone uploads it.

    python3 tools/package_verifier.py                 # build dist/relayshield-tap-verifier.zip
    python3 tools/package_verifier.py --with-ti       # also bundle relayshield_api.py and what it imports
    python3 tools/package_verifier.py --check         # verify only, build nothing

WHY THIS EXISTS. The verifier's modules are imported behind try/except so a package missing
one still verifies TAP. That is the right failure mode for production and the wrong one for
packaging: a zip that lacks x401_rp.py does not fail, it silently answers "x401 unavailable"
for every customer. This repo has shipped that shape before (a Lambda deployed without the
module it imports; run 134's denied probe). So the build is not trusted until:

  1. EVERY file in the manifest exists;
  2. EVERY import, at module top or inside a function, of a module that lives in this repo
     resolves to a file in the manifest (an AST walk, not a grep);
  3. the unzipped package, run in isolation with only its own directory on the path, answers
     a TAP request, issues an x401 challenge, and loads the telemetry and nonce modules.

Nothing secret is packaged: x401_issuers.json and x401_policies.json are configuration, the
signing key is read from Secrets Manager at runtime, and tests and the testkit are excluded.

Handler: relayshield_tap_verifier.lambda_handler
"""
import argparse
import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

CORE = [
    "relayshield_tap_verifier.py",       # the handler: TAP + dispatch
    "x401_rp.py",                        # the relying party (current draft)
    "x401_jose.py",                      # ES256 / JWS / JWK, pure stdlib
    "x401_net.py",                       # the one guarded outbound fetch
    "x401_verifier.py",                  # the earlier bespoke mode, still dispatched
    "relayshield_verifier_telemetry.py", # opt-in rejection telemetry
    "relayshield_verifier_nonces.py",    # shared single-use store
    "relayshield_tap_ti.py",             # TI screen (inert unless VERIFIER_TI_SCREEN=1)
    "x401_issuers.json",                 # trust registry (public keys only)
    "x401_policies.json",                # DCQL policies
]
NEVER = ("test_", "x401_testkit", "tools/", "CLAUDE")


def repo_modules():
    return {p.stem for p in ROOT.glob("*.py")}


def local_imports(path: pathlib.Path):
    """Top-level names of every repo module this file imports, anywhere in the file."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names & repo_modules()


def api_closure():
    """relayshield_api.py and every repo module reachable from it (for the TI screen)."""
    seen, todo = set(), ["relayshield_api"]
    while todo:
        mod = todo.pop()
        if mod in seen or not (ROOT / f"{mod}.py").exists():
            continue
        seen.add(mod)
        todo.extend(local_imports(ROOT / f"{mod}.py") - seen)
    return sorted(f"{m}.py" for m in seen)


def manifest(with_ti=False):
    files = list(CORE)
    if with_ti:
        files += [f for f in api_closure() if f not in files]
    return files


# The ONE import allowed to be absent, and only without --with-ti: the TI screen loads
# relayshield_api lazily, and the handler turns the screen on only when VERIFIER_TI_SCREEN=1.
OPTIONAL_IMPORTS = {"relayshield_tap_ti.py": {"relayshield_api"}}


def problems(files, with_ti=False):
    out = []
    for f in files:
        if not (ROOT / f).exists():
            out.append(f"missing from the repo: {f}")
        if any(f.startswith(n) for n in NEVER):
            out.append(f"must not be packaged: {f}")
    have = {pathlib.Path(f).stem for f in files if f.endswith(".py")}
    for f in files:
        if f.endswith(".py") and (ROOT / f).exists():
            optional = set() if with_ti else OPTIONAL_IMPORTS.get(f, set())
            for dep in sorted(local_imports(ROOT / f) - have - optional):
                out.append(f"{f} imports {dep}, which is not in the package")
    for f in ("x401_issuers.json", "x401_policies.json"):
        if f in files:
            try:
                doc = json.loads((ROOT / f).read_text())
            except Exception as exc:
                out.append(f"{f} is not valid JSON: {exc}")
                continue
            if "d" in json.dumps(doc) and '"d":' in json.dumps(doc):
                out.append(f"{f} appears to contain a private key member")
    return out


SMOKE = r'''
import json, os, sys
sys.path.insert(0, sys.argv[1])                   # -I keeps the repo and cwd off the path; the package wins
os.environ["VERIFIER_TELEMETRY_DISABLED"] = "1"
import relayshield_tap_verifier as tap
assert tap._rp is not None, "x401_rp did not import from the package"
assert tap._net is not None, "x401_net did not import from the package"
assert tap._x401 is not None, "x401_verifier did not import from the package"
import relayshield_verifier_telemetry, relayshield_verifier_nonces, relayshield_tap_ti, x401_jose
for m in (tap, tap._rp, tap._net, tap._x401, x401_jose, relayshield_verifier_telemetry):
    assert os.path.realpath(m.__file__).startswith(os.path.realpath(sys.argv[1])), ("imported from outside the package", m.__file__)
r = tap.lambda_handler({"body": "{}", "headers": {}}, None)
assert r["statusCode"] == 403, r
import x401_jose as j
os.environ["X401_SIGNING_JWK"] = json.dumps(j.generate_p256_jwk())
os.environ["X401_POLICIES"] = json.dumps({"policies": {"p": {
    "dcql_query": {"credentials": [{"id": "c", "format": "dc+sd-jwt", "meta": {"vct_values": ["v"]},
                                    "claims": [{"path": ["a"]}]}]},
    "trusted_issuers": ["https://i.example"], "expected_origins": ["https://m.example"]}}})
r = tap.lambda_handler({"body": json.dumps({"action": "x401_challenge", "x401_policy": "p",
                                            "path": "/x", "method": "POST"}), "headers": {}}, None)
assert r["statusCode"] == 200, r
payload = j.b64u_json_decode(json.loads(r["body"])["proof_request"])
assert payload["scheme"] == "x401" and payload["version"] == "0.2.0", payload
issuers = json.load(open(os.path.join(sys.argv[1], "x401_issuers.json")))
assert isinstance(issuers.get("issuers"), dict)
print("SMOKE OK", len(os.listdir(sys.argv[1])), "files")
'''


def smoke(zip_path):
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(td)
        r = subprocess.run([sys.executable, "-I", "-B", "-c", SMOKE, td], capture_output=True, text=True, cwd=td, timeout=60)
        return r.returncode == 0 and "SMOKE OK" in r.stdout, (r.stdout + r.stderr).strip()


def build(files, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            info = zipfile.ZipInfo(f, date_time=(2026, 1, 1, 0, 0, 0))   # reproducible bytes
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, (ROOT / f).read_bytes())
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-ti", action="store_true")
    ap.add_argument("--check", action="store_true", help="verify without leaving a zip behind")
    ap.add_argument("--out", default=str(ROOT / "dist" / "relayshield-tap-verifier.zip"))
    args = ap.parse_args()
    files = manifest(args.with_ti)
    bad = problems(files, args.with_ti)
    if bad:
        print("NOT PACKAGED. Fix these first:")
        for b in bad:
            print("  -", b)
        return 1
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "check.zip" if args.check else pathlib.Path(args.out)
        sha = build(files, out)
        ok, log = smoke(out)
        print(f"{len(files)} files{' (with the TI screen and relayshield_api)' if args.with_ti else ''}")
        for f in files:
            print("  ", f)
        if not ok:
            print("SMOKE TEST FAILED:\n" + log)
            return 1
        print(log)
        if not args.check:
            print(f"built {out}  sha256 {sha}  {out.stat().st_size:,} bytes")
            print("Handler: relayshield_tap_verifier.lambda_handler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
