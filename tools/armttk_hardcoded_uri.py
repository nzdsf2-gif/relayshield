#!/usr/bin/env python3
"""Faithful Python port of arm-ttk's DeploymentTemplate-Must-Not-Contain-Hardcoded-Uri test."""
import re, sys

DISALLOWED = ["management.core.windows.net","gallery.azure.com","management.azure.com",
 "database.windows.net","core.windows.net","login.microsoftonline.com","graph.windows.net",
 "vault.azure.net","datalake.azure.net","azuredatalakestore.net","azuredatalakeanalytics.net",
 "api.loganalytics.io","api.loganalytics.iov1","asazure.windows.net","region.asazure.windows.net",
 "batch.core.windows.net"]

def parameters_span(raw):
    m = re.search(r'"parameters"\s*:\s*\{', raw)
    if not m:
        return None
    start = m.end() - 1
    depth = 0; i = start; instr = False; esc = False
    while i < len(raw):
        c = raw[i]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return (start, i + 1)
        i += 1
    return (start, len(raw))

def run(path):
    raw = open(path, encoding='utf-8-sig').read()
    rx = re.compile("|".join(h.replace('.', r'\.') for h in DISALLOWED), re.I)
    span = parameters_span(raw)
    errors = []
    for m in rx.finditer(raw):
        i = m.start()
        if span and span[0] <= i < span[1]:
            continue
        before = raw[:i].lower()
        if before.endswith('https://schema.') or before.endswith('https://devopsgallerystorage.blob.'):
            continue
        errors.append((raw.count('\n', 0, i) + 1, m.group(0), raw[max(0, i-150):i+90].replace('\n', ' ')))
    return errors

if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        errs = run(p)
        print(f"{p}: {len(errs)} Hardcoded.Url.Reference error(s)")
        for line, host, ctx in errs:
            print(f"  line {line}: Found hardcoded reference to {host}")
            print(f"    ...{ctx}...")
        bad += len(errs)
    sys.exit(1 if bad else 0)
