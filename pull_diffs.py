# -*- coding: utf-8 -*-
"""Deterministic (no-model) step 1: pull merged PRs + real diffs via gh. Flags NEW/unclassified PRs."""
import json, subprocess, os, sys

def gh(args, **kw):
    return subprocess.run(["gh"]+args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)

def main():
    r = gh(["api","-X","GET","search/issues","-f","q=author:tritsystem is:pr is:merged -user:tritsystem",
            "-f","per_page=100","--jq",'.items[] | {repo:(.repository_url|sub(".*/repos/";"")), number:.number, title:.title, url:.html_url}'])
    prs = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    os.makedirs("data/diffs", exist_ok=True)
    for p in prs:
        fn = f"data/diffs/{p['repo'].replace('/','__')}__{p['number']}.diff"
        d = gh(["pr","diff",str(p["number"]),"-R",p["repo"]])
        open(fn,"w",encoding="utf-8").write(d.stdout or "")
        m = gh(["pr","view",str(p["number"]),"-R",p["repo"],"--json","additions,deletions,changedFiles,mergedAt"])
        meta = json.loads(m.stdout) if m.stdout.strip().startswith("{") else {}
        p.update(additions=meta.get("additions"), deletions=meta.get("deletions"),
                 files=meta.get("changedFiles"), mergedAt=(meta.get("mergedAt") or "")[:10])
    json.dump(prs, open("data/prs.json","w"), indent=1)
    # flag PRs not yet classified / annotated
    try:
        from data.classify import C as CLS  # noqa
    except Exception:
        CLS = {}
    known = set()
    cf = "data/classify.py"
    if os.path.exists(cf):
        txt = open(cf, encoding="utf-8").read()
        known = {k for k in [f"{p['repo']}#{p['number']}" for p in prs] if f'"{k}"' in txt}
    new = [f"{p['repo']}#{p['number']}" for p in prs if f"{p['repo']}#{p['number']}" not in known]
    print(f"pulled {len(prs)} merged PRs; {len(new)} UNCLASSIFIED: {new}")
    json.dump(new, open("data/unclassified.json","w"), indent=1)
    return 0

if __name__ == "__main__":
    sys.exit(main())
