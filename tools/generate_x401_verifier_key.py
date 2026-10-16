#!/usr/bin/env python3
"""Create the x401 verifier's request-signing key, store the PRIVATE half in Secrets Manager,
and publish the PUBLIC half.

    AWS_PROFILE=relayshield python3 tools/generate_x401_verifier_key.py            # dry run
    AWS_PROFILE=relayshield python3 tools/generate_x401_verifier_key.py --apply

WHAT IT DOES, in order, each step refusing to continue if the one before it was wrong:
  1. confirms the AWS account is 239677749008 (a write to the audit account would "succeed");
  2. refuses if the secret already exists, unless --rotate (replacing a live signing key
     changes the key wallets resolve at did:web:api.relayshield.net, and invalidates every
     challenge still in flight);
  3. generates a fresh P-256 key with the OS random source;
  4. writes the private JWK to a 0600 file in a private temp directory, hands THAT FILE to
     `aws secretsmanager` (so the key is never on a command line, in shell history or in
     this tool's output), and overwrites and deletes the file;
  5. rewrites relayshield_x401_pubkey.py with the public JWK, the only thing that ever
     goes in the repo.

The private key is printed nowhere. The public key is printed so it can be checked against
https://api.relayshield.net/.well-known/did.json once relayshield-api has deployed.

AFTER IT RUNS (the tool prints these too): commit relayshield_x401_pubkey.py, merge, push,
then let the verifier Lambda read the secret with tools/grant_x401_secret_access.py.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import x401_jose as jose  # noqa: E402

ACCOUNT = "239677749008"
DEFAULT_SECRET = "relayshield/x401_verifier_key"
DEFAULT_PUBKEY_FILE = ROOT / "relayshield_x401_pubkey.py"
KID = "did:web:api.relayshield.net#x401-1"


def aws(*args, check=True):
    cmd = ["aws", "--no-cli-pager", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        # The error text can name the secret but never contains its value: the value is passed as a file.
        raise SystemExit(f"aws {' '.join(args[:2])} failed: {r.stderr.strip()[:400]}")
    return r


def secret_exists(name, region):
    r = aws("secretsmanager", "describe-secret", "--secret-id", name, "--region", region, check=False)
    if r.returncode == 0:
        return True
    if "ResourceNotFoundException" in r.stderr:
        return False
    raise SystemExit(f"could not tell whether {name} exists: {r.stderr.strip()[:300]}")


def shred(path):
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as fh:
            fh.write(os.urandom(size))
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.unlink(path)


def write_pubkey_module(path, public_jwk):
    text = pathlib.Path(path).read_text()
    line = "PUBLIC_JWK = " + json.dumps(public_jwk, indent=4, sort_keys=True).replace("\n", "\n")
    new, n = re.subn(r"(?ms)^PUBLIC_JWK = .*?(?=^KID = )", line + "\n", text)
    if n != 1:
        raise SystemExit(f"could not find PUBLIC_JWK in {path}")
    pathlib.Path(path).write_text(new)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rotate", action="store_true", help="replace an existing key")
    ap.add_argument("--secret-name", default=DEFAULT_SECRET)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--pubkey-file", default=str(DEFAULT_PUBKEY_FILE))
    args = ap.parse_args(argv)

    got = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text").stdout.strip()
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to account {got}, not {ACCOUNT}. Prefix the command with AWS_PROFILE=relayshield.")
        return 2
    exists = secret_exists(args.secret_name, args.region)
    print(f"account {got} (correct); secret {args.secret_name}: {'EXISTS' if exists else 'not present'}")
    if exists and not args.rotate:
        print("STOP: the secret already exists. Re-run with --rotate only if you mean to replace the live signing key.")
        return 3
    if not args.apply:
        print(f"DRY RUN. With --apply this would generate a P-256 key, {'replace' if exists else 'create'} the secret, "
              f"and write the public key into {args.pubkey_file}. Nothing was changed.")
        return 0

    private = jose.generate_p256_jwk()
    private["kid"] = KID
    public = dict(jose.public_jwk(private), kid=KID, alg="ES256", use="sig")
    tmpdir = tempfile.mkdtemp(prefix="x401key-")
    os.chmod(tmpdir, 0o700)
    keyfile = os.path.join(tmpdir, "key.json")
    fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(private, fh)
        verb = "put-secret-value" if exists else "create-secret"
        extra = ["--secret-id", args.secret_name] if exists else ["--name", args.secret_name]
        aws("secretsmanager", verb, *extra, "--secret-string", f"file://{keyfile}", "--region", args.region,
            "--query", "Name", "--output", "text")
    finally:
        if os.path.exists(keyfile):
            shred(keyfile)
        os.rmdir(tmpdir)
    write_pubkey_module(args.pubkey_file, public)
    print(f"stored the private key in Secrets Manager as {args.secret_name}; the key file was overwritten and deleted.")
    print(f"wrote the PUBLIC key into {args.pubkey_file}:")
    print(json.dumps(public, indent=2, sort_keys=True))
    print("\nNEXT, in this order:")
    print("  1. git add relayshield_x401_pubkey.py && git commit, merge, and push main (this deploys relayshield-api)")
    print("  2. curl -sS https://api.relayshield.net/.well-known/did.json   (the key above must appear)")
    print("  3. AWS_PROFILE=relayshield python3 tools/grant_x401_secret_access.py --function <verifier lambda name>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
