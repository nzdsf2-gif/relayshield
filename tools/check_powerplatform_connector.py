#!/usr/bin/env python3
"""Re-check the connector against the 11 certification rules, by command.

CERTIFICATION_PREP.md records that all 11 rules passed on 2026-08-16, verified by
hand. Hand-verification does not survive a regeneration. This encodes the rules
so `build_powerplatform_connector.py` can be followed by a check that fails loudly,
which is the same drift discipline the description fix already relies on.

Offline only. It does not replace `paconn validate`, which authenticates against
the Power Platform validation service.

    python3 tools/check_powerplatform_connector.py
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "powerplatform_connector")

BANNED_BRAND = {"#007ee5", "#ffffff"}
BANNED_TITLE_WORDS = ("api", "connector", "microsoft", "power automate", "power apps")

fails, warns = [], []
def fail(rule, m): fails.append("[%s] %s" % (rule, m))
def warn(rule, m): warns.append("[%s] %s" % (rule, m))

swagger = json.load(open(os.path.join(PKG, "relayshield_swagger2.json")))
props = json.load(open(os.path.join(PKG, "apiProperties.json")))["properties"]

# 1. Title: under 30 chars, no "API"/"Connector"/product names
title = swagger["info"].get("title", "")
if not title or len(title) >= 30:
    fail("title", "must be under 30 characters, found %d" % len(title))
for w in BANNED_TITLE_WORDS:
    if w in title.lower():
        fail("title", "must not contain %r" % w)

# 2. Description: 30 to 500 characters
desc = swagger["info"].get("description", "")
if not (30 <= len(desc) <= 500):
    fail("description", "must be 30 to 500 characters, found %d" % len(desc))

# 3. Auth type: OAuth2, anonymous, API key or basic
sec = swagger.get("securityDefinitions") or {}
if not sec:
    fail("auth", "securityDefinitions is required")
for name, s in sec.items():
    if s.get("type") not in ("apiKey", "oauth2", "basic"):
        fail("auth", "%s has unsupported type %r" % (name, s.get("type")))

# 4. Support contact
contact = swagger["info"].get("contact") or {}
if not contact.get("email"):
    fail("contact", "info.contact.email is required")

# 5. Operation summaries: under 80 chars, alphanumeric and parentheses only
# 6. Response schemas: no empty schemas, no empty operations
# 11. operationId: unique, PascalCase
seen = {}
ops = 0
for path, methods in swagger.get("paths", {}).items():
    for method, op in methods.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        ops += 1
        where = "%s %s" % (method.upper(), path)
        oid = op.get("operationId", "")
        if not oid:
            fail("operationId", "%s: required" % where)
        elif not re.match(r"^[A-Z][A-Za-z0-9]*$", oid):
            fail("operationId", "%s: %r must be PascalCase" % (where, oid))
        elif oid in seen:
            fail("operationId", "%s: duplicates %s" % (where, seen[oid]))
        else:
            seen[oid] = where

        summary = op.get("summary", "")
        if not summary:
            fail("summary", "%s: required" % where)
        else:
            if len(summary) >= 80:
                fail("summary", "%s: %d chars, limit 80" % (where, len(summary)))
            if not re.match(r"^[A-Za-z0-9 ()]+$", summary):
                bad = sorted(set(re.sub(r"[A-Za-z0-9 ()]", "", summary)))
                fail("summary", "%s: only alphanumerics and parentheses allowed, found %s"
                     % (where, " ".join(repr(c) for c in bad)))
        if not op.get("description"):
            fail("description", "%s: operation description is required" % where)

        r200 = (op.get("responses") or {}).get("200")
        if r200 is None:
            fail("responses", "%s: a 200 response is required" % where)
        elif not r200.get("schema"):
            fail("responses", "%s: 200 must carry a non-empty schema" % where)

if ops == 0:
    fail("paths", "the connector defines no operations")

# 7. Swagger validity: 2.0, no 3.x leftovers
if swagger.get("swagger") != "2.0":
    fail("swagger", "must be 2.0, found %r" % swagger.get("swagger"))
blob = json.dumps(swagger)
for leftover in ('"oneOf"', '"anyOf"', '"const"', '"prefixItems"', '"examples"',
                 "components/schemas", '"nullable"'):
    if leftover in blob:
        fail("swagger", "OpenAPI 3.x leftover present: %s" % leftover)

# 8. Production host URL, https only
host = swagger.get("host", "")
if not host:
    fail("host", "required")
elif any(t in host.lower() for t in ("staging", "dev.", "test", "localhost", "execute-api")):
    fail("host", "%r looks like a non-production host" % host)
if swagger.get("schemes") != ["https"]:
    fail("host", 'schemes must be exactly ["https"], found %r' % swagger.get("schemes"))

# 9. apiProperties: brand colour, publisher, stackOwner
brand = (props.get("iconBrandColor") or "").lower()
if not re.match(r"^#[0-9a-f]{6}$", brand):
    fail("brand", "iconBrandColor %r must be 6 digit hex" % brand)
elif brand in BANNED_BRAND:
    fail("brand", "iconBrandColor %s is forbidden" % brand)
for key in ("publisher", "stackOwner"):
    if not props.get(key):
        fail("publisher", "apiProperties.properties.%s is required" % key)

# 10. Icon: square, 100 to 230, logo under 70% of the frame, uniform opaque
#     background matching iconBrandColor, not white, not #007ee5
icons = [f for f in os.listdir(PKG) if f.lower().endswith(".png")]
if not icons:
    fail("icon", "no PNG in %s: the re-cut icon was never committed, so the package "
                 "cannot be assembled from this repository" % os.path.basename(PKG))
else:
    try:
        from PIL import Image
        im = Image.open(os.path.join(PKG, icons[0]))
        w, h = im.size
        if w != h:
            fail("icon", "%s must be square, found %dx%d" % (icons[0], w, h))
        if not (100 <= w <= 230):
            fail("icon", "%s must be 100 to 230 px, found %d" % (icons[0], w))
        rgb = im.convert("RGB")
        corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        if len(set(corners)) != 1:
            fail("icon", "background must be uniform, corners differ: %s" % (corners,))
        else:
            hexc = "#%02x%02x%02x" % corners[0]
            if hexc in BANNED_BRAND:
                fail("icon", "background %s is forbidden" % hexc)
            if brand and hexc != brand:
                fail("icon", "background %s does not match iconBrandColor %s" % (hexc, brand))
        if im.mode in ("RGBA", "LA", "P"):
            if min(p[3] for p in im.convert("RGBA").getdata()) < 255:
                fail("icon", "must be fully opaque")
        # logo extent: bounding box of everything that is not the background colour
        bg = corners[0]
        px = rgb.load()
        xs, ys = [], []
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                if px[x, y] != bg:
                    xs.append(x); ys.append(y)
        if xs:
            ew, eh = (max(xs) - min(xs)) / w, (max(ys) - min(ys)) / h
            if ew >= 0.70 or eh >= 0.70:
                fail("icon", "logo extent %.0f%% x %.0f%%, rule is under 70%%"
                     % (ew * 100, eh * 100))
            else:
                warn("icon", "logo extent %.0f%% x %.0f%% (rule: under 70%%)"
                     % (ew * 100, eh * 100))
    except ImportError:
        warn("icon", "Pillow not installed, icon geometry unchecked")

for w_ in warns:
    print("WARN  %s" % w_)
for f in fails:
    print("FAIL  %s" % f)
print("\n%d operations, %d failures, %d warnings" % (ops, len(fails), len(warns)))
sys.exit(1 if fails else 0)
