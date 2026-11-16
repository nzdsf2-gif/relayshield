#!/usr/bin/env python3
"""Option B v9b: insert handle_passport_revoke and its route. REVIEW ONLY.

Run from /Users/andrewgibbs/dev/relayshield, after downloading
intent_binding_passport_revoke_handler_v9.py to ~/Downloads and
reviewing intent-binding-option-b-v9-passport-revoke-review-2026-11-01.md.

Anchors, from the code pasted 2026-11-01, checked exactly once:
- Handler anchor: "def handle_passport_status(passport_id: str) -> dict:"
  at relayshield_api.py:14519. The revoke handler is inserted
  immediately before it, after handle_passport_check.
- Route anchor: the status route return at 18793:
  'return handle_passport_status(path[len("/v1/passport/"):-len("/status")])'
  The revoke route is inserted immediately before the status route
  if statement. The script finds the start of that if statement by
  searching backwards from the return line to the nearest line
  starting with "if method".

Handler source: the function text is extracted from
~/Downloads/intent_binding_passport_revoke_handler_v9.py, starting at
"def handle_passport_revoke", not the whole file, so the module
docstring in that file is not inserted into relayshield_api.py.

Aborts with no file written if any anchor count is not 1, or if
handle_passport_revoke is already present. Does NOT commit, deploy,
or run the Gateway. After it succeeds, run py_compile and review
git diff before any commit or Deploy Changed Lambdas run.
"""
import sys
from pathlib import Path

API = Path("relayshield_api.py")
HANDLER_FILE = Path.home() / "Downloads" / "intent_binding_passport_revoke_handler_v9.py"
text = API.read_text(encoding="utf-8")

if "handle_passport_revoke" in text:
    print("ABORT: handle_passport_revoke already present in relayshield_api.py. No file written.")
    sys.exit(1)

handler_text = HANDLER_FILE.read_text(encoding="utf-8")
start = handler_text.find("def handle_passport_revoke")
if start < 0:
    print("ABORT: def handle_passport_revoke not found in handler file. No file written.")
    sys.exit(1)
handler = handler_text[start:].rstrip() + "\n"

anchor_handler = "def handle_passport_status(passport_id: str) -> dict:"
if text.count(anchor_handler) != 1:
    print(f"ABORT: handler anchor count is {text.count(anchor_handler)}, expected 1. No file written.")
    sys.exit(1)
text = text.replace(anchor_handler, handler + "\n" + anchor_handler, 1)

anchor_route = 'return handle_passport_status(path[len("/v1/passport/"):-len("/status")])'
if text.count(anchor_route) != 1:
    print(f"ABORT: route anchor count is {text.count(anchor_route)}, expected 1. No file written.")
    sys.exit(1)
pos = text.index(anchor_route)
line_start = text.rfind("\n", 0, pos) + 1
# Find the start of the if statement for the status route, searching backwards.
if_start = text.rfind('if method', 0, pos)
if if_start < 0:
    print("ABORT: status route if statement not found. No file written.")
    sys.exit(1)
# Ensure if_start is on its own line start.
if_start = text.rfind("\n", 0, if_start) + 1
route = (
    '    if method == "POST" and path == "/v1/passport/revoke":\n'
    '        return handle_passport_revoke(_body(event))\n'
)
text = text[:if_start] + route + text[if_start:]
API.write_text(text, encoding="utf-8")
print("WROTE relayshield_api.py with handle_passport_revoke and route. Review with git diff before any commit or deploy.")
