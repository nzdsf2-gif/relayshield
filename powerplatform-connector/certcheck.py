#!/usr/bin/env python3
"""Offline pre-submission checks for the RelayShield Power Platform connector.

Covers the certification rules that can be verified without a Power Platform
login. It does NOT replace `paconn validate`, which authenticates against the
Power Platform validation service and must still be run before submitting.
"""
import json, re, sys
from PIL import Image

FORBIDDEN_BRAND = {"#007ee5", "#ffffff"}
fails, warns = [], []


def fail(m): fails.append(m)
def warn(m): warns.append(m)


swagger = json.load(open("apiDefinition.swagger.json"))
props = json.load(open("apiProperties.json"))

# --- swagger level -----------------------------------------------------------
if swagger.get("swagger") != "2.0":
    fail("apiDefinition must be Swagger 2.0, found %r" % swagger.get("swagger"))

info = swagger.get("info", {})
for key in ("title", "description", "version"):
    if not info.get(key):
        fail("info.%s is required" % key)
if info.get("title", "").lower().startswith("the "):
    warn("info.title should not start with an article")
if len(info.get("description", "")) < 30:
    fail("info.description is too short to be useful in the gallery")

if "host" not in swagger:
    fail("host is required")
if swagger.get("schemes") != ["https"]:
    fail("schemes must be exactly [\"https\"]; certification rejects plain http")
if not swagger.get("securityDefinitions"):
    fail("securityDefinitions is required")

# --- operations --------------------------------------------------------------
seen_ids, seen_summaries = set(), {}
for path, ops in swagger.get("paths", {}).items():
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        where = "%s %s" % (method.upper(), path)
        oid = op.get("operationId")
        if not oid:
            fail("%s: operationId is required" % where)
        else:
            if oid in seen_ids:
                fail("%s: duplicate operationId %r" % (where, oid))
            seen_ids.add(oid)
            if not re.match(r"^[A-Z][A-Za-z0-9]*$", oid):
                fail("%s: operationId %r must be PascalCase, letters and digits only" % (where, oid))
        summary = op.get("summary", "")
        if not summary:
            fail("%s: summary is required" % where)
        else:
            if len(summary) > 80:
                fail("%s: summary is %d chars, limit is 80" % (where, len(summary)))
            if summary.endswith("."):
                fail("%s: summary must not end with a full stop" % where)
            if summary in seen_summaries:
                fail("%s: summary duplicates %s" % (where, seen_summaries[summary]))
            seen_summaries[summary] = where
        desc = op.get("description", "")
        if not desc:
            fail("%s: description is required" % where)
        elif not desc.rstrip().endswith("."):
            warn("%s: description should end with a full stop" % where)
        if desc and summary and desc.strip() == summary.strip():
            fail("%s: description merely repeats the summary" % where)
        if "x-ms-visibility" in op and op["x-ms-visibility"] not in ("important", "advanced", "internal"):
            fail("%s: invalid x-ms-visibility %r" % (where, op["x-ms-visibility"]))
        # responses
        responses = op.get("responses", {})
        if "200" not in responses:
            fail("%s: a 200 response must be defined" % where)
        for code, r in responses.items():
            if not r.get("description"):
                fail("%s: response %s needs a description" % (where, code))
        # request body fields need designer labels
        for p in op.get("parameters", []):
            if p.get("in") == "body":
                for name, ps in (p.get("schema", {}).get("properties") or {}).items():
                    if isinstance(ps, dict):
                        if not ps.get("x-ms-summary"):
                            fail("%s: body field %r needs x-ms-summary" % (where, name))
                        if not ps.get("description"):
                            warn("%s: body field %r has no description" % (where, name))

# --- apiProperties -----------------------------------------------------------
p = props.get("properties", {})
brand = (p.get("iconBrandColor") or "").lower()
if not brand:
    fail("apiProperties.iconBrandColor is required")
elif brand in FORBIDDEN_BRAND:
    fail("iconBrandColor %s is explicitly forbidden by certification" % brand)
elif not re.match(r"^#[0-9a-f]{6}$", brand):
    fail("iconBrandColor %r must be a 6 digit hex colour" % brand)
if not p.get("publisher"):
    fail("apiProperties.publisher is required")
if not p.get("stackOwner"):
    fail("apiProperties.stackOwner is required")
if not p.get("connectionParameters"):
    fail("apiProperties.connectionParameters is required")

# --- icon --------------------------------------------------------------------
try:
    im = Image.open("icon.png")
    if im.size != (230, 230):
        fail("icon.png must be 230x230, found %dx%d" % im.size)
    if im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        if min(px[3] for px in rgba.getdata()) < 255:
            fail("icon.png must not have a transparent background")
    corner = im.convert("RGB").getpixel((3, 3))
    hexc = "#%02x%02x%02x" % corner
    if hexc in FORBIDDEN_BRAND or corner == (255, 255, 255):
        fail("icon.png background must not be white")
    if brand and hexc != brand:
        fail("icon.png background %s does not match iconBrandColor %s" % (hexc, brand))
except FileNotFoundError:
    fail("icon.png is missing")

# --- report ------------------------------------------------------------------
for w in warns:
    print("WARN  %s" % w)
for f in fails:
    print("FAIL  %s" % f)
print("\n%d operations checked, %d failures, %d warnings"
      % (len(seen_ids), len(fails), len(warns)))
sys.exit(1 if fails else 0)
