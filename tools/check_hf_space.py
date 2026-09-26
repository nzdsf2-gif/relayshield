#!/usr/bin/env python3
"""Is the RelayShield HF Space answering? Read-only, two public requests.

WHY THIS EXISTS. The Space is one of five MCP surfaces and the ONLY hosted one we
point strangers at. FD-15 is about handing a URL to Grok Bot, Smithery and
possibly OpenAI, and mcp_surfaces_inventory.md already records the failure mode:
a hosted surface does not show "disconnected" in a client, it presents as a
failing URL, which nobody sees unless something is looking.

Advertising a URL in three directories while nothing watches whether it answers
is the quiet-alarm shape with an audience attached.

THREE CHECKS, BECAUSE THEY FAIL DIFFERENTLY:

  1. The Space's HTTP front door. A sleeping or crashed Space answers 404 or 503
     here while the HF API still says the repo exists.
  2. The HF API's runtime stage. This is what says SLEEPING, BUILDING, RUNTIME_ERROR
     or RUNNING, and it distinguishes "asleep and will wake" from "broken".
  3. THE MCP ENDPOINT ITSELF, which is the one that actually matters and was
     missing until 2026-09-09. The front door answering 200 says the Gradio app
     is serving a web page. It says NOTHING about whether the MCP server is
     mounted, and that is precisely the URL we hand to Smithery, to AWS
     Marketplace and to anyone else who takes a hosted server.

     The failure this catches is not hypothetical: app.py passes mcp_server=True
     to demo.launch(), and its own comments record a previous Gradio upgrade
     changing how that route is mounted. Drop that argument, or upgrade Gradio
     past a rename, and the Space stays green on checks 1 and 2 forever while
     every advertised URL 404s. Checking the front door and calling it a check
     of the MCP server is the "a status code describes the request you made"
     mistake in its most expensive form.

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

# A THIRD SPACE, ADDED 2026-09-26, WITH A DIFFERENT TRANSPORT ENTIRELY.
#
# relayshieldadmin/relayshield-free-mcp is the dedicated free/keyless server
# (check_link, check_wallet, check_email keyless; check_breach key-optional)
# that mcp_registry/smithery.yaml (FD-11) now points at. It is a plain MCP
# server speaking the spec's Streamable HTTP transport at /mcp -- POST a
# JSON-RPC message, get one back -- not a Gradio app mounting mcp_server=True
# at /gradio_api/mcp/sse. Different framework, different wire shape, so it
# gets its own probe function (check_streamable) rather than being squeezed
# into check_one's Gradio-specific SSE logic.
#
# UNVERIFIED FROM THIS CONTAINER: hf.space is not reachable through this
# repo's egress proxy, so this probe has never actually been run against the
# live server. Run `python3 tools/check_hf_space.py --only free-mcp` from
# somewhere that can reach it and confirm it reports UP before this joins the
# scheduled workflow -- a wrong probe running unattended either cries wolf
# forever or, worse, stays green while the endpoint is actually down, which
# is the exact quiet-alarm failure this whole file exists to prevent.
STREAMABLE_SPACES = [
    ("free-mcp", "relayshield-free-mcp",
     "the keyless MCP server Smithery (FD-11) points at"),
]
STREAMABLE_MCP_PATH = "/mcp"

# THE ADVERTISED PATH, AND THE ONE THAT REPLACES IT IF GRADIO EVER MOVES IT.
#
# `/gradio_api/mcp/sse` is what the AWS Marketplace entity registers as Bundle
# D's EndpointUrl, and what mcp_registry/smithery.yaml now points at. One URL in
# every directory, deliberately: three directories holding three different URLs
# is three things to keep alive.
#
# Gradio also serves streamable HTTP at `/gradio_api/mcp/`. It is probed as
# INFORMATION ONLY and never fails the run, because it is not what anybody was
# handed. Its value is the morning the SSE route disappears in a Gradio upgrade:
# "sse is 404 and streamable is 200" is a one-line diagnosis and a one-line fix,
# where "the MCP endpoint is down" is an afternoon.
MCP_PATH = "/gradio_api/mcp/sse"
MCP_ALT_PATH = "/gradio_api/mcp/"

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


def _probe_mcp(url, timeout=45):
    """Ask for the SSE stream and read only the first bytes.

    An SSE endpoint holds the connection open by design, so this must never
    consume it: urlopen returns as soon as the HEADERS arrive, and the body read
    is deliberately tiny and allowed to time out. A read timeout on a stream
    that already answered 200 with an event-stream content type is not a
    failure -- it means the server accepted the subscription and had nothing to
    say yet, which is a working MCP endpoint.
    """
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "text/event-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            ctype = (fh.headers.get("content-type") or "").lower()
            try:
                head = fh.read(256)
            except Exception:
                head = b""            # see the docstring: not a failure
            return fh.status, ctype, head
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("content-type") or "").lower() if e.headers else "", b""
    except Exception as e:
        return None, "", str(e).encode()


def _probe_streamable_http(url, timeout=45):
    """POST a real MCP `initialize` request and read whatever comes back.

    Streamable HTTP answers a POST with EITHER application/json (one
    response) or text/event-stream (the same response framed as an SSE
    event) -- both are valid per spec, so this reads the body and lets the
    caller decide whether it parses as JSON-RPC, rather than assuming one
    content-type is the only correct answer.
    """
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "relayshield-hf-space-watch", "version": "1.0"},
        },
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            ctype = (fh.headers.get("content-type") or "").lower()
            return fh.status, ctype, fh.read(4096)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(4096)
        except Exception:
            body = b""
        ctype = (e.headers.get("content-type") or "").lower() if e.headers else ""
        return e.code, ctype, body
    except Exception as e:
        return None, "", str(e).encode()


def _is_jsonrpc_response(ctype: str, body: bytes) -> bool:
    """A real server answers `initialize` with a JSON-RPC envelope, whether
    delivered as a plain JSON body or as one `data:` line of an SSE event."""
    try:
        if "event-stream" in ctype:
            for line in body.decode("utf-8", "replace").splitlines():
                if line.startswith("data:"):
                    return "jsonrpc" in json.loads(line[len("data:"):].strip())
            return False
        return "jsonrpc" in json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return False


def check_streamable(label: str, space: str, why: str) -> dict:
    front = f"https://{OWNER}-{space}.hf.space/"
    mcp_url = front.rstrip("/") + STREAMABLE_MCP_PATH
    result = {"label": label, "space": f"{OWNER}/{space}", "why_it_matters": why,
              "front_url": front, "mcp_url": mcp_url, "api_url": None, "stage": ""}

    code, ctype, body = _probe_streamable_http(mcp_url)
    result["mcp_status"] = code
    result["mcp_content_type"] = ctype
    ok = code == 200 and _is_jsonrpc_response(ctype, body)

    if code is None:
        result["verdict"], rc = "UNREACHABLE", 2
        result["detail"] = ("Could not reach the endpoint at all. A fact about this "
                            "runner's network, not proof the Space is down.")
    elif code in (404, 405, 410):
        result["verdict"], rc = "DOWN", 1
        result["detail"] = f"{STREAMABLE_MCP_PATH} returned {code}: the MCP route is not there."
    elif ok:
        result["verdict"], rc = "UP", 0
        result["detail"] = f"{STREAMABLE_MCP_PATH} answered a real JSON-RPC response to initialize."
    else:
        # Includes 5xx and a cold start: a probe that cannot tell has no
        # standing to stop the work, same rule as the Gradio checker.
        result["verdict"], rc = "UNCLEAR", 2
        result["detail"] = (f"{STREAMABLE_MCP_PATH} returned {code} with content-type "
                            f"'{ctype or 'none'}' and no recognisable JSON-RPC response. "
                            "This probe's request shape has not been confirmed against a "
                            "live run yet -- see the UNVERIFIED note above STREAMABLE_SPACES "
                            "before treating a red result here as proof of an outage.")
    result["exit"] = rc
    return result


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

    # The front door request above also WAKES a sleeping Space, so the MCP probe
    # runs afterwards on purpose rather than racing it.
    base = front.rstrip("/")
    mcp_url = base + MCP_PATH
    mcp_code, mcp_ctype, _ = _probe_mcp(mcp_url)
    result["mcp_url"] = mcp_url
    result["mcp_status"] = mcp_code
    result["mcp_content_type"] = mcp_ctype
    mcp_ok = mcp_code == 200 and "event-stream" in mcp_ctype

    alt_code, alt_ctype, _ = _probe_mcp(base + MCP_ALT_PATH)
    result["mcp_alt_url"] = base + MCP_ALT_PATH
    result["mcp_alt_status"] = alt_code           # information only, never fatal

    waking = stage in ("SLEEPING", "BUILDING", "RUNNING_APP_STARTING", "RUNNING_BUILDING")

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
    elif mcp_code is not None and mcp_code in (404, 405, 410):
        # THE FAILURE THIS CHECK EXISTS FOR, and it is invisible to the two
        # checks above: the app is serving, and the endpoint we published is not
        # there. Unambiguous, so it blocks -- unlike the inconclusive cases below.
        result["verdict"], rc = "DOWN", 1
        result["detail"] = (f"The Space is up but {MCP_PATH} returned {mcp_code}. "
                            f"The MCP endpoint published to Smithery and registered "
                            f"on the AWS Marketplace listing is GONE, while every "
                            f"front-door check stays green."
                            + (f" {MCP_ALT_PATH} answered {alt_code}, so the server "
                               f"is probably mounted at a different path after a "
                               f"Gradio upgrade." if alt_code == 200 else ""))
    elif mcp_ok:
        result["verdict"], rc = "UP", 0
        result["detail"] = (f"stage={stage or 'unknown'}, front door {front_code}, "
                            f"{MCP_PATH} streaming."
                            + (" Asleep, which is not an outage: the next request wakes it."
                               if stage == "SLEEPING" else ""))
    elif waking or mcp_code is None or (mcp_code is not None and mcp_code >= 500):
        # A probe that could not tell has no standing to stop the work. A waking
        # Space refuses connections for a minute, and a 5xx here is as likely to
        # be the wake-up as a fault.
        result["verdict"], rc = "UNCLEAR", 2
        result["detail"] = (f"stage={stage or 'unknown'}, front door {front_code}, "
                            f"{MCP_PATH} -> {mcp_code} ({mcp_ctype or 'no content-type'}). "
                            "Could not confirm the MCP endpoint. Re-run; if it persists "
                            "with the Space RUNNING, treat it as down.")
    elif stage in OK_STAGES or (front_code is not None and front_code < 400):
        result["verdict"], rc = "UNCLEAR", 2
        result["detail"] = (f"The Space answers ({front_code}) but {MCP_PATH} returned "
                            f"{mcp_code} with content-type "
                            f"'{mcp_ctype or 'none'}', which is not an event stream.")
    else:
        result["verdict"], rc = "UNCLEAR", 2
        result["detail"] = (f"api={api_code} stage={stage or 'unknown'} front={front_code} "
                            f"mcp={mcp_code}. Not a state this check knows how to read.")

    result["exit"] = rc
    return result


def main() -> int:
    all_labels = [s[0] for s in SPACES] + [s[0] for s in STREAMABLE_SPACES]
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", choices=all_labels,
                    help="check one Space instead of all of them")
    args = ap.parse_args()

    gradio_targets = [s for s in SPACES if not args.only or s[0] == args.only]
    stream_targets = [s for s in STREAMABLE_SPACES if not args.only or s[0] == args.only]
    results = [check_one(*t) for t in gradio_targets] + \
              [check_streamable(*t) for t in stream_targets]

    if args.json:
        print(json.dumps({"spaces": results}, indent=2))
    else:
        for r in results:
            print(f"[{r['label']}] {r['verdict']}: {r['detail']}")
            print(f"    {r['why_it_matters']}")
            if r.get("api_url") is not None:
                print(f"    api   {r['api_url']} -> {r.get('api_status')}")
                print(f"    front {r['front_url']} -> {r.get('front_status')}")
            print(f"    mcp   {r['mcp_url']} -> {r['mcp_status']} "
                  f"({r['mcp_content_type'] or 'no content-type'})")
            if "mcp_alt_url" in r:
                print(f"    alt   {r['mcp_alt_url']} -> {r['mcp_alt_status']}  (information only)")
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
