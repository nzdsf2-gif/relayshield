#!/usr/bin/env python3
"""Check the RelayShield Sentinel rules against Azure-Sentinel's own CI constraints.

The upstream validators are .NET (detectionTemplateSchemaValidation, KqlvalidationsTests,
NonAsciiValidationsTests) and dotnet is not installed here, so this re-implements the
checks that are cheap to re-implement and would otherwise only fail after the PR is open:
required fields, the tactic and entity-type enums, valid connector IDs, the timespan and
threshold ranges, entity/field-mapping cardinality, ASCII-only content, and -- the one
that actually bites -- whether every column referenced on ThreatIntelIndicators exists in
the schema the KQL validator checks against.

It reads the enums and schemas out of the fork rather than hardcoding them, so it stays
correct as upstream changes.

Run:  python3 sentinel_solution/validate_rules.py [path-to-Azure-Sentinel-fork]
"""
import glob
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: python3 -m pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FORK = (
    "/private/tmp/claude-501/-Users-andrewgibbs-Side-SaaS-Hustle/"
    "f2173087-3e6f-4790-812f-23063a586e1c/scratchpad/Azure-Sentinel"
)

RULE_REQUIRED = [
    "id", "name", "description", "severity", "query", "tactics", "relevantTechniques",
    "requiredDataConnectors", "queryFrequency", "queryPeriod", "triggerOperator",
    "triggerThreshold", "kind",
]
HUNT_REQUIRED = ["id", "name", "description", "query", "requiredDataConnectors", "tactics"]
SEVERITIES = {"Informational", "Low", "Medium", "High"}
TRIGGER_OPERATORS = {"gt", "lt", "eq", "ne", "GreaterThan", "LessThan", "Equal", "NotEqual"}

failures, warnings = [], []


def fail(f, msg):
    failures.append("%s: %s" % (os.path.basename(f), msg))


def warn(f, msg):
    warnings.append("%s: %s" % (os.path.basename(f), msg))


def load_enum(path, pattern=r"^\s+([A-Za-z]+),?\s*$"):
    if not os.path.exists(path):
        return None
    out = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(pattern, line)
        if m and m.group(1) not in ("public", "enum", "using", "namespace"):
            out.add(m.group(1))
    return out


def load_entity_identifiers(path):
    if not os.path.exists(path):
        return None
    src = open(path, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(
        r"EntityType\.(\w+),\s*new EntityIdentifiers\(\)\s*\{\s*Identifiers = new List<string>\(\)\s*\{([^}]*)\}",
        src,
    ):
        out[m.group(1)] = set(re.findall(r'"(\w+)"', m.group(2)))
    return out


def parse_timespan(v):
    """Accept 1h / 14d / PT1H style and return seconds, or None if unparseable."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.fullmatch(r"(\d+)([mhd])", s)
    if m:
        return int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", s)
    if m and any(m.groups()):
        d, h, mi = (int(x or 0) for x in m.groups())
        return d * 86400 + h * 3600 + mi * 60
    return None


def check_columns(f, query, ti_columns):
    """Flag columns used against ThreatIntelIndicators that the table does not have."""
    if "ThreatIntelIndicators" not in query or not ti_columns:
        return
    # Strip comments and {{placeholders}} first. Without this the check reports
    # every capitalised word of English prose in a comment as a missing column,
    # which buries the real findings.
    query = re.sub(r"//[^\n]*", "", query)
    query = re.sub(r"\{\{\w+\}\}", "", query)
    # String literals are values, not column references. Analyst-facing remediation
    # text mentioning "Threat intelligence - TAXII" is not a schema error.
    query = re.sub(r'@?"(?:[^"\\]|\\.)*"', '""', query)
    query = re.sub(r"@?'(?:[^'\\]|\\.)*'", "''", query)
    # Columns the query introduces itself are legitimate; collect them so they are
    # not reported as missing.
    declared = set(re.findall(r"\b(?:extend|project|summarize|as|mv-expand|parse)\s+(\w+)\s*=", query))
    declared |= set(re.findall(r",\s*(\w+)\s*=", query))
    declared |= set(re.findall(r"\blet\s+(\w+)\s*=", query))
    declared |= set(re.findall(r"\$(?:left|right)\.(\w+)", query))
    declared |= set(re.findall(r"^\s*(\w+)\s*=", query, re.M))
    known_funcs = {
        "ago", "now", "count", "max", "min", "avg", "round", "iff", "case", "strcat",
        "tostring", "tolower", "toupper", "split", "trim", "replace_string", "dcount",
        "dcountif", "make_set", "make_set_if", "isnull", "isnotempty", "isempty",
        "coalesce", "datetime_diff", "format_datetime", "parse_url", "column_ifexists",
        "materialize", "todatetime", "union", "arg_max", "strcat_array", "real",
        "ingestion_time", "dynamic", "count_", "countif", "sum", "bin", "toscalar",
    }
    # Candidate bare identifiers that look like column references.
    used = set(re.findall(r"(?<![\w.$])([A-Z]\w{2,})\b", query))
    suspicious = {
        c for c in used
        if c not in declared
        and c not in known_funcs
        and c not in ti_columns
        and not c.startswith("RelayShield")
        and c not in {
            # Other tables and their columns, checked by the real validator instead.
            "CommonSecurityLog", "ThreatIntelIndicators", "DestinationIP", "SourceIP",
            "DeviceName", "RequestURL", "DestinationHostName", "Host", "Scheduled",
            "Configuration", "API", "BOTH", "TAXII", "No", "Check", "Confirm",
        }
    }
    for c in sorted(suspicious):
        warn(f, "possible unknown column on ThreatIntelIndicators: %s" % c)


def main():
    fork = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FORK
    models = os.path.join(fork, ".script/tests/detectionTemplateSchemaValidation/Models")

    tactics = load_enum(os.path.join(models, "AttackTactic.cs"))
    entities = load_enum(os.path.join(models, "EntityType.cs"))
    identifiers = load_entity_identifiers(os.path.join(models, "EntityMappingIdentifiers.cs"))

    conn_path = os.path.join(fork, ".script/tests/detectionTemplateSchemaValidation/ValidConnectorIds.json")
    connectors = set(json.load(open(conn_path))) if os.path.exists(conn_path) else None

    ti_path = os.path.join(fork, ".script/tests/KqlvalidationsTests/CustomTables/ThreatIntelIndicators.json")
    ti_columns = None
    if os.path.exists(ti_path):
        d = json.load(open(ti_path))
        cols = d.get("Properties") or d.get("Columns") or []
        ti_columns = {c["Name"] for c in cols}

    for src, missing in (
        (tactics, "AttackTactic.cs"), (entities, "EntityType.cs"),
        (identifiers, "EntityMappingIdentifiers.cs"), (connectors, "ValidConnectorIds.json"),
        (ti_columns, "ThreatIntelIndicators.json"),
    ):
        if not src:
            sys.exit("could not read %s under %s -- pass the fork path as argv[1]" % (missing, fork))

    seen_ids = {}
    files = sorted(glob.glob(os.path.join(HERE, "*", "*.yaml")))
    if not files:
        sys.exit("no YAML found under %s" % HERE)

    for f in files:
        is_rule = os.path.basename(os.path.dirname(f)) == "Analytic Rules"
        raw = open(f, encoding="utf-8").read()

        # NonAsciiValidationsTests rejects non-ASCII in template content.
        for i, line in enumerate(raw.split("\n"), 1):
            bad = [ch for ch in line if ord(ch) > 127]
            if bad:
                fail(f, "non-ASCII on line %d: %r" % (i, bad))

        doc = yaml.safe_load(raw)
        for k in (RULE_REQUIRED if is_rule else HUNT_REQUIRED):
            if k not in doc:
                fail(f, "missing required field '%s'" % k)

        rid = str(doc.get("id", ""))
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", rid):
            fail(f, "id is not a lowercase GUID: %r" % rid)
        if rid in seen_ids:
            fail(f, "duplicate id, also used by %s" % os.path.basename(seen_ids[rid]))
        seen_ids[rid] = f

        for t in doc.get("tactics") or []:
            if t not in tactics:
                fail(f, "invalid tactic '%s'" % t)

        for t in doc.get("relevantTechniques") or []:
            if not re.fullmatch(r"T\d{4}(\.\d{3})?", str(t)):
                fail(f, "malformed technique '%s'" % t)

        for c in doc.get("requiredDataConnectors") or []:
            cid = c.get("connectorId")
            if cid not in connectors:
                fail(f, "connectorId '%s' is not in ValidConnectorIds.json" % cid)
            if not c.get("dataTypes"):
                fail(f, "connector '%s' has no dataTypes" % cid)

        ems = doc.get("entityMappings") or []
        if len(ems) > 10:
            fail(f, "%d entityMappings, max is 10" % len(ems))
        query = doc.get("query", "")
        for em in ems:
            et = em.get("entityType")
            if et not in entities:
                fail(f, "invalid entityType '%s'" % et)
            fms = em.get("fieldMappings") or []
            if not 1 <= len(fms) <= 3:
                fail(f, "%s has %d fieldMappings, must be 1 to 3" % (et, len(fms)))
            for fm in fms:
                ident, col = fm.get("identifier"), fm.get("columnName")
                if et in identifiers and ident not in identifiers[et]:
                    fail(f, "%s has no identifier '%s'" % (et, ident))
                # A mapped column that the query never projects yields an empty entity.
                if col and not re.search(r"\b%s\b" % re.escape(col), query):
                    fail(f, "entity column '%s' is never produced by the query" % col)

        for name, col in (doc.get("customDetails") or {}).items():
            if not re.search(r"\b%s\b" % re.escape(str(col)), query):
                fail(f, "customDetails '%s' points at column '%s' which the query never produces" % (name, col))

        if is_rule:
            if doc.get("severity") not in SEVERITIES:
                fail(f, "invalid severity '%s'" % doc.get("severity"))
            if doc.get("triggerOperator") not in TRIGGER_OPERATORS:
                fail(f, "invalid triggerOperator '%s'" % doc.get("triggerOperator"))
            thr = doc.get("triggerThreshold")
            if not isinstance(thr, int) or not 0 <= thr <= 10000:
                fail(f, "triggerThreshold %r out of range 0..10000" % thr)
            for k in ("queryFrequency", "queryPeriod"):
                secs = parse_timespan(doc.get(k))
                if secs is None:
                    fail(f, "%s %r is not a parseable timespan" % (k, doc.get(k)))
                elif not 300 <= secs <= 14 * 86400:
                    fail(f, "%s %r outside 5 minutes..14 days" % (k, doc.get(k)))
            if doc.get("kind") != "Scheduled":
                fail(f, "kind is %r, expected Scheduled" % doc.get("kind"))
            freq, period = parse_timespan(doc.get("queryFrequency")), parse_timespan(doc.get("queryPeriod"))
            if freq and period and freq > period:
                fail(f, "queryFrequency is longer than queryPeriod")
        else:
            for ph in ("{{StartTimeISO}}", "{{EndTimeISO}}"):
                if ph not in query and "endtime" in query:
                    warn(f, "hunting query does not use %s" % ph)

        check_columns(f, query, ti_columns)

    print("checked %d file(s) against %s\n" % (len(files), os.path.basename(fork)))
    for w in warnings:
        print("  WARN  %s" % w)
    if warnings:
        print()
    for x in failures:
        print("  FAIL  %s" % x)
    if failures:
        print("\n%d failure(s)" % len(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
