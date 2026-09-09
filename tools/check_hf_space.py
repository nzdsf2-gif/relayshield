#!/usr/bin/env python3
"""Is the RelayShield HF Space answering? Read-only, two public requests.

WHY THIS EXISTS. The Space is one of five MCP surfaces and the ONLY hosted one we
point strangers at. FD-15 is about handing a URL to Grok Bot, Smithery and
possibly OpenAI, and mcp_surfaces_inventory.md already records the failure mode:
a hosted surface does not show "disconnected" in a client, it presents as a
failing URL, which nobody sees unless something is looking.

Advertising a URL in three directories while nothing watches whether it answers
is the quiet-alarm shape with an audience attached.

TWO CHECKS, BECAUSE THEY FAIL DIFFERENTLY:

  1. The Space's HTTP front door. A sleeping or crashed Space answers 404 or 503
     here while the HF API still says the repo exists.
  2. The HF API's runtime stage. This is what says SLEEPING, BUILDING, RUNTIME_ERROR
     or RUNNING, and it distinguishes "asleep and will wake" from "broken".

A Space on the free tier SLEEPS after inactivity, and sleeping is not an outage:
the first request wakes it. So SLEEPING is reported and does NOT fail the run.
RUNTIME_ERROR, BUILD_ERROR and a front door that will not answer at all are the
states worth waking somebody for.

Exit 0 when it is up or merely asleep, 1 when it is down, 2 when the check itself
could not answer -- which is a different thing again and must not be read as
"the Space is fine".

    python3 tools/check_hf_space.py
    python3 tools/check_hf_space.py --json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

OWNER = "relayshieldadmin"

# TWO SPACES, NOT ONE, AND THE SECOND ONE IS THE HIGHER-STAKES ONE.
#
# Found 2026-09-09 by reading the live AWS Marketplace entity. The first version
# of this checker watched only the public Space, because that is the one every
# blog post links. But hf-space-mcp-server/app.py says outright that the SAME
# file is deployed as two Spaces, and the AWS one -- AWS_MARKETPLACE_MODE=true,
# which scrubs every reference to the self-serve signup page -- is registered on
# the Bundle D listing as its MCP endpoint:
#
#   ApiType: MCP_SERVER
#   EndpointUrl: https://relayshieldadmin-relayshield-agentic-attack-surface-aws
#                .hf.space/gradio_api/mcp/sse
#
# So if THAT Space stops answering, a PUBLISHED AWS Marketplace product's own
# declared endpoint is dead, in front of buyers who reached it through AWS. That
# is worse than the public Space going quiet, and it was the one nothing watched.
#
# The env var difference is not cosmetic: AWS's Tier-1 audit treats a reachable
# link to an external payment page as a violation, and that is what failed
# Bundle D's visibility request twice. Both Spaces must stay up and stay
# identical except for that variable.
SPACES = [
    ("public", "relayshield-agentic-attack-surface",
     "linked from every post and the MCP registry"),
    ("aws", "relayshield-agentic-attack-surface-aws",
     "Bundle D's registered MCP endpoint on AWS Marketplace"),
]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Asleep is not down. A free-tier Space sleeps on inactivity and the next request
# wakes it, so paging on SLEEPING is how an alarm gets muted.
OK_STAGES = {"RUNNING", "RUNNING_APP_STARTING", "SLEEPING", "PAUSED"}
BAD_STAGES = {"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "DELETING"}


def _get(url, timeout=45):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)          # huggingface.co is behind a CDN that
    req.add_header("Accept", "*/*")           # rejects urllib's default agent.
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, fh.read(65536)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, str(e).encode()


def check_one(label: str, space: str, why: str) -> dict:
    api = f"https://huggingface.co/api/spaces/{OWNER}/{space}"
    front = f"https://{OWNER}-{space}.hf.space/"
    result = {"label": label, "space": f"{OWNER}/{space}",
              "why_it_matters": why, "front_url": front, "api_url": api}

    api_code, api_body = _get(api)
    result["api_status"] = api_code
    stage = ""
    if api_code == 200:
        try:
            stage = ((json.loads(api_body) or {}).get("runtime") or {}).get("stage", "")
        except json.JSONDecodeError:
            stage = ""
    result["stage"] = stage

    front_code, _ = _get(front)
    result["front_status"] = front_code

    # Decide. Unreachable is its own verdict: a check that could not run must
    # never be reported as a pass.
    if api_code is None and front_code is None:
        result["verdict"], rc = "UNREACHABLE", 2
        result["detail"] = ("Neither the HF API nor the Space front door could be "
                            "reached. That is a fact about this runner's network, "
                            "not proof the Space is down.")
    elif stage in BAD_STAGES:
        result["verdict"], rc = "DOWN", 1
        result["detail"] = f"HF reports runtime stage {stage}."
    elif front_code is not None and front_code >= 500:
        result["verdict"], rc = "DOWN", 1
        result["detail"] = f"The Space front door returned {front_code}."
    elif api_code == 404:
        result["verdict"], rc = "DOWN", 1
        result["detail"] = "The HF API returns 404: the Space is missing, renamed or private."
    elif stage in OK_STAGES or (front_code is not None and front_code < 400):
        result["verdict"], rc = "UP", 0
        result["detail"] = (f"stage={stage or 'unknown'}, front door {front_code}."
                            + (" Asleep, which is not an outage: the next request wakes it."
                               if stage == "SLEEPING" else ""))
    else:
        result["verdict"], rc = "UNCLEAR", 2
        result["detail"] = (f"api={api_code} stage={stage or 'unknown'} front={front_code}. "
                            "Not a state this check knows how to read.")

    result["exit"] = rc
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", choices=[s[0] for s in SPACES],
                    help="check one Space instead of both")
    args = ap.parse_args()

    targets = [s for s in SPACES if not args.only or s[0] == args.only]
    results = [check_one(*t) for t in targets]

    if args.json:
        print(json.dumps({"spaces": results}, indent=2))
    else:
        for r in results:
            print(f"[{r['label']}] {r['verdict']}: {r['detail']}")
            print(f"    {r['why_it_matters']}")
            print(f"    api   {r['api_url']} -> {r['api_status']}")
            print(f"    front {r['front_url']} -> {r['front_status']}")
            print(f"    stage {r['stage'] or '(none reported)'}")

    # The worst verdict wins. A DOWN on either Space is a DOWN overall, and the
    # AWS one being down is the more expensive of the two.
    down = [r for r in results if r["exit"] == 1]
    unclear = [r for r in results if r["exit"] == 2]
    verdict = "DOWN" if down else ("UNREACHABLE" if unclear else "UP")
    print(f"HF_SPACE_STATUS={verdict}", file=sys.stderr)
    print(f"HF_SPACE_DOWN={','.join(r['label'] for r in down)}", file=sys.stderr)
    return 1 if down else (2 if unclear else 0)


if __name__ == "__main__":
    raise SystemExit(main())
