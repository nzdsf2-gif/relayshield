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
SPACE = "relayshield-agentic-attack-surface"
API = f"https://huggingface.co/api/spaces/{OWNER}/{SPACE}"
FRONT = f"https://{OWNER}-{SPACE}.hf.space/"

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = {"space": f"{OWNER}/{SPACE}", "front_url": FRONT}

    api_code, api_body = _get(API)
    result["api_status"] = api_code
    stage = ""
    if api_code == 200:
        try:
            stage = ((json.loads(api_body) or {}).get("runtime") or {}).get("stage", "")
        except json.JSONDecodeError:
            stage = ""
    result["stage"] = stage

    front_code, _ = _get(FRONT)
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

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['verdict']}: {result['detail']}")
        print(f"  api    {API} -> {api_code}")
        print(f"  front  {FRONT} -> {front_code}")
        print(f"  stage  {stage or '(none reported)'}")
    print(f"HF_SPACE_STATUS={result['verdict']}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
