import importlib.util, re, subprocess, sys
spec=importlib.util.spec_from_file_location("bb","build_blog.py"); bb=importlib.util.module_from_spec(spec); spec.loader.exec_module(bb)

md = open("blog_bundle_d_launch.md").read()
title = md.split("\n")[0].lstrip("# ").strip()
body  = "\n".join(md.split("\n")[1:]).lstrip("\n")

# Medium has no tables. Convert the bundle table to a definition-style list so
# it survives instead of flattening into loose lines.
def table_to_list(m):
    rows=[r.strip() for r in m.group(0).strip().split("\n")]
    cells=[[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    if len(cells)<3: return m.group(0)
    out=[]
    for r in cells[2:]:
        if len(r)>=3:
            out.append(f"- **{r[0]}**: {r[1]} *({r[2]} per call)*")
        else:
            out.append("- " + ": ".join(r))
    return "\n".join(out) + "\n\n"
body = re.sub(r"(?m)^\|.*\|[ \t]*\n\|[ \t:\-|]+\|[ \t]*\n(?:\|.*\|[ \t]*\n)+", table_to_list, body)

html = bb.md_to_html(body)
doc = f"<h1>{title}</h1>\n{html}"
open("/tmp/medium_post.html","w").write(doc)

# macOS clipboard as public.html so Medium's editor converts it natively.
hexed = doc.encode("utf-8").hex()
subprocess.run(["osascript","-e",f'set the clipboard to «data HTML{hexed}»'], check=True)
print(f"title      : {title}")
print(f"html bytes : {len(doc)}")
print(f"tables     : {doc.count('<table')} (should be 0 for Medium)")
print(f"lists      : {doc.count('<ul>')} | items: {doc.count('<li>')}")
print(f"code blocks: {doc.count('<pre>')}")
print(f"paragraphs : {doc.count('<p>')}")
print("clipboard  : loaded as public.html")
