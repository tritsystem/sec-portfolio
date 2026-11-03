# -*- coding: utf-8 -*-
"""Generate the deep-dive page from data/classified.json + real diffs in data/diffs/."""
import json, html, os, re
from collections import Counter, defaultdict

D = json.load(open("data/classified.json"))
prs = [p for p in D["prs"] if "layer" in p]
LN = D["layer_names"]

def esc(s): return html.escape(s or "")

def key_hunk(path, max_lines=24, prefer_modify=True):
    """Pull the most instructive hunk. Prefer a hunk that MODIFIES lines (has both - and +)
    over a pure-addition hunk (e.g. an added test), so the before/after shows a real contrast.
    Skip pure test-file hunks when a source modification exists."""
    if not os.path.exists(path): return ("", "", "none")
    txt = open(path, encoding="utf-8", errors="replace").read()
    cands = []  # (is_modify, is_src, change_count, min_side, fname, lines)
    for sec in re.split(r'(?m)^diff --git ', txt):
        fm = re.search(r'a/(\S+) b/(\S+)', sec)
        fname = fm.group(2) if fm else "?"
        is_src = not re.search(r'(^|/)(test|tests)[/_]', fname) and "test_" not in fname.rsplit("/",1)[-1]
        for hunk in re.split(r'(?m)^(?=@@ )', sec):
            if not hunk.startswith("@@"): continue
            lines = [l for l in hunk.splitlines()[1:] if l[:3] not in ("+++","---")]
            dels = sum(1 for l in lines if l[:1]=="-"); adds = sum(1 for l in lines if l[:1]=="+")
            if dels+adds == 0: continue
            cands.append((dels>0 and adds>0, is_src, dels+adds, min(dels,adds), fname, lines))
    if not cands: return ("", "", "none")
    # rank: real modification first, then source (not test), then swap size, then total change
    cands.sort(key=lambda c: (c[0], c[1], c[3], c[2]), reverse=True)
    is_mod, _is_src, _c, _m, fname, lines = cands[0]
    kind = "modify" if is_mod else "add"
    if len(lines) > max_lines:
        idx = next((i for i,l in enumerate(lines) if l[:1] in "+-"), 0)
        lo = max(0, idx-5); lines = lines[lo:lo+max_lines]
    return (fname, "\n".join(lines), kind)

def diff_html(code):
    rows = []
    for l in code.splitlines():
        c = l[:1]
        cls = "add" if c=="+" else "del" if c=="-" else "ctx"
        rows.append(f'<span class="{cls}">{esc(l) or "&nbsp;"}</span>')
    return "\n".join(rows)

WALKS = json.load(open("data/walks.json"))

def before_after(code):
    """Split the real hunk into BEFORE (context + removed) and AFTER (context + added) columns."""
    before, after = [], []
    for l in code.splitlines():
        c = l[:1]
        if c == "-":   before.append(("del", l[1:]))
        elif c == "+": after.append(("add", l[1:]))
        else:
            txt = l[1:] if c == " " else l
            before.append(("ctx", txt)); after.append(("ctx", txt))
    def col(rows):
        return "\n".join(f'<span class="{k}">{esc(t) or "&nbsp;"}</span>' for k,t in rows)
    return col(before), col(after)

def walkthrough(key):
    steps = WALKS.get(key)
    if not steps: return ""
    icon = {"del":"&minus;", "add":"+", "ctx":"·", "note":"&#9432;"}
    items = []
    for kind, _code, why in steps:
        items.append(f'<li><span class="wk {kind}">{icon.get(kind,"·")}</span><span>{why}</span></li>')
    return f'<div class="walk"><div class="mtitle">Line-by-line: what changed and why</div><ol class="walklist">{"".join(items)}</ol></div>'

def risk_tier(r):
    return ("Low","low") if r < 6 else ("Medium","med") if r < 12 else ("High","high")

# ---- order: layers with most PRs first, bug fixes before features within a layer ----
by_layer = defaultdict(list)
for p in prs: by_layer[p["layer"]].append(p)
layer_order = sorted(by_layer, key=lambda L: -len(by_layer[L]))
for L in by_layer:
    by_layer[L].sort(key=lambda p: (p.get("is_feature",False), -p["risk"]))

layer_counts = Counter(p["layer"] for p in prs)
maxc = max(layer_counts.values())
cls_counts = Counter(p["cls"].split(" (")[0].split(":")[0] for p in prs)

# ---- 13-layer stack SVG (full stack, touched layers highlighted) ----
STACK = [(1,"Mathematics"),(2,"Learning theory"),(3,"Data"),(4,"Architecture"),(5,"Training"),
 (6,"Framework"),(7,"Kernels"),(8,"Hardware"),(9,"Inference / serving"),(10,"Systems around model"),
 (11,"Evaluation"),(12,"Security & integrity"),(13,"Deployment & org")]
rows_svg=[]
for i,(num,name) in enumerate(STACK):
    y=i*30+6; cnt=layer_counts.get(num,0)
    frac = cnt/maxc if maxc else 0
    fill = f"rgba(31,95,208,{0.12+0.55*frac:.2f})" if cnt else "var(--card)"
    tcol = "var(--fg)" if cnt else "var(--muted)"
    rows_svg.append(f'<rect x="0" y="{y}" width="560" height="26" rx="6" fill="{fill}" stroke="var(--line)"/>'
      f'<text x="12" y="{y+17}" font-size="12.5" fill="{tcol}" font-weight="{600 if cnt else 400}">L{num} · {name}</text>'
      f'<text x="548" y="{y+17}" font-size="12" fill="{tcol}" text-anchor="end" font-family="monospace">{str(cnt)+(" PR" if cnt==1 else " PRs") if cnt else ""}</text>')
stack_svg = f'<svg viewBox="0 0 560 {len(STACK)*30+6}" width="100%" role="img" aria-label="13-layer stack with merged-PR counts">{"".join(rows_svg)}</svg>'

# ---- layer magnitude bars (single hue, labelled) ----
bars=[]
for L in sorted(layer_counts, key=lambda L:-layer_counts[L]):
    c=layer_counts[L]; w=int(100*c/maxc)
    bars.append(f'<div class="barrow"><span class="blab">L{L} {esc(LN[str(L)])}</span>'
      f'<span class="btrack"><span class="bfill" style="width:{w}%"></span></span><span class="bval">{c}</span></div>')
bars_html="".join(bars)

# ---- per-PR card ----
def card(p):
    tier,tc = risk_tier(p["risk"])
    meters="".join(
      f'<div class="mrow"><span class="mlab">{lab}</span><span class="mtrack"><span class="mfill" style="width:{v*20}%"></span></span><span class="mval">{v}</span></div>'
      for lab,v in [("Exposure",p["exposure"]),("Ease",p["ease"]),("Attacker gain",p["gain"]),("Blast radius",p["blast"])])
    feat = '<span class="chip feat">feature</span>' if p.get("is_feature") else ''
    key = f"{p['repo']}#{p['number']}"
    fn, code, hkind = key_hunk(f"data/diffs/{p['repo'].replace('/','__')}__{p['number']}.diff")
    if not code:
        codeblock = '<p class="muted" style="font-size:13px">Diff spans multiple files — see the PR link.</p>'
    else:
        before, after = before_after(code)
        ctx = sum(1 for l in code.splitlines() if l[:1]==" ")
        dels = sum(1 for l in code.splitlines() if l[:1]=="-")
        before_label = "Before" if (dels or ctx>=2) else "Before (new code — nothing here prior)"
        note = ("" if (dels or ctx>=2) else
                '<p class="muted" style="font-size:12.5px;margin:6px 0 0">This hunk only adds new code, so the Before side is the empty/surrounding region; the After side is the added lines.</p>')
        codeblock = (f'<div class="ba"><div class="bacol"><div class="balabel before">{before_label}</div>'
                     f'<pre class="diff">{before or "&nbsp;"}</pre></div>'
                     f'<div class="bacol"><div class="balabel after">After</div>'
                     f'<pre class="diff">{after}</pre></div></div>{note}'
                     f'<div class="difftitle">unified diff — {esc(fn)}</div><pre class="diff">{diff_html(code)}</pre>')
    return f'''<article class="pr" id="pr-{p['number']}">
  <div class="prhead">
    <div><a class="prtitle" href="{esc(p['url'])}">{esc(p['repo'])} <b>#{p['number']}</b></a>
      <div class="meta">+{p.get('additions','?')}/&minus;{p.get('deletions','?')} · {p.get('files','?')} files · merged {esc(p.get('mergedAt',''))}</div></div>
    <div class="chips"><span class="chip layer">L{p['layer']} {esc(p['layer_name'])}</span><span class="chip risk {tc}">{tier} · {p['risk']}/25</span>{feat}</div>
  </div>
  <h4>{esc(p['title'])}</h4>
  <p class="cls"><b>Class:</b> {esc(p['cls'])}</p>
  <p class="threat"><b>Threat model:</b> {esc(p['threat'])}</p>
  <p class="plain">{p['plain']}</p>
  {codeblock}
  {walkthrough(key)}
  <div class="meters"><div class="mtitle">Risk rubric (likelihood &times; impact)</div>{meters}</div>
</article>'''

sections=[]
for L in layer_order:
    cards="".join(card(p) for p in by_layer[L])
    sections.append(f'<section class="layer"><h3 id="layer-{L}">Layer {L} — {esc(LN[str(L)])} <span class="lc">{layer_counts[L]} merged</span></h3>{cards}</section>')

HTML = f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Every merge, broken down — threat model, 13 layers, rubric</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧬</text></svg>">
<style>
 :root{{--bg:#fbfbfd;--fg:#1b1b1f;--muted:#5f6069;--line:#e4e4ea;--card:#fff;--accent:#1f5fd0;--add:#1f7a3a;--del:#b3261e;--addbg:rgba(31,122,58,.10);--delbg:rgba(179,38,30,.09);--low:#1f7a3a;--med:#9a6a00;--high:#b3261e;--mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace}}
 @media (prefers-color-scheme:dark){{:root{{--bg:#111216;--fg:#e9e9ee;--muted:#9aa0ac;--line:#262830;--card:#191b21;--accent:#7aa2ff;--add:#6cc68a;--del:#ff8a80;--addbg:rgba(108,198,138,.12);--delbg:rgba(255,138,128,.12);--low:#6cc68a;--med:#e0b45e;--high:#ff8a80}}}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
 main{{max-width:900px;margin:0 auto;padding:36px 20px 80px}}
 h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.5px}} h2{{font-size:21px;margin:40px 0 10px}} h3{{font-size:19px;margin:34px 0 6px;border-top:2px solid var(--line);padding-top:22px}}
 h4{{margin:10px 0 6px;font-size:16.5px}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
 .lede{{color:var(--muted);font-size:17px;margin:0 0 18px}}
 .lc{{font:600 12px/1 var(--mono);color:var(--muted);float:right;margin-top:6px}}
 .panel{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}}
 .barrow{{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:13px}} .blab{{width:230px;color:var(--muted);flex:none}}
 .btrack{{flex:1;height:14px;background:color-mix(in srgb,var(--accent) 9%,transparent);border-radius:7px;overflow:hidden}}
 .bfill{{display:block;height:100%;background:var(--accent);border-radius:7px}} .bval{{width:24px;text-align:right;font:600 12px var(--mono)}}
 .pr{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}}
 .prhead{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start}}
 .prtitle{{font:600 15px var(--mono)}} .meta{{color:var(--muted);font-size:12px;margin-top:3px}}
 .chips{{display:flex;gap:6px;flex-wrap:wrap}} .chip{{font:600 11px/1 var(--mono);padding:5px 9px;border-radius:20px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}}
 .chip.layer{{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 40%,var(--line))}}
 .chip.risk.low{{color:var(--low)}} .chip.risk.med{{color:var(--med)}} .chip.risk.high{{color:var(--high);border-color:color-mix(in srgb,var(--high) 45%,var(--line))}}
 .chip.feat{{color:var(--muted)}}
 .cls,.threat{{font-size:14px;margin:4px 0}} .threat{{color:var(--fg)}} .plain{{font-size:14.5px;margin:8px 0}}
 code{{font:12.5px var(--mono);background:color-mix(in srgb,var(--accent) 10%,transparent);padding:1px 5px;border-radius:5px}}
 .difftitle{{font:600 11.5px var(--mono);color:var(--muted);margin:10px 0 0;padding:6px 10px;background:color-mix(in srgb,var(--accent) 7%,transparent);border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0}}
 pre.diff{{margin:0;padding:10px 12px;background:var(--card);border:1px solid var(--line);border-radius:0 0 8px 8px;overflow-x:auto;font:12px/1.5 var(--mono);white-space:pre}}
 pre.diff span{{display:block}} .diff .add{{background:var(--addbg);color:var(--add)}} .diff .del{{background:var(--delbg);color:var(--del)}} .diff .ctx{{color:var(--muted)}}
 .ba{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}} @media(max-width:640px){{.ba{{grid-template-columns:1fr}}}}
 .bacol{{min-width:0}} .balabel{{font:600 11px var(--mono);padding:5px 10px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0}}
 .balabel.before{{color:var(--del);background:var(--delbg)}} .balabel.after{{color:var(--add);background:var(--addbg)}}
 .ba pre.diff{{border-radius:0 0 8px 8px}}
 .walk{{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}}
 .walklist{{margin:4px 0;padding-left:0;list-style:none;counter-reset:w}}
 .walklist li{{display:flex;gap:9px;align-items:flex-start;margin:7px 0;font-size:13.5px;counter-increment:w}}
 .walklist li::before{{content:counter(w);flex:none;width:18px;height:18px;border-radius:50%;background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);font:600 11px/18px var(--mono);text-align:center;margin-top:1px}}
 .wk{{flex:none;width:16px;text-align:center;font:700 13px var(--mono)}} .wk.del{{color:var(--del)}} .wk.add{{color:var(--add)}} .wk.note,.wk.ctx{{color:var(--muted)}}
 .meters{{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}} .mtitle{{font:600 12px var(--mono);color:var(--muted);margin-bottom:6px}}
 .mrow{{display:flex;align-items:center;gap:10px;margin:3px 0;font-size:12.5px}} .mlab{{width:96px;color:var(--muted);flex:none}}
 .mtrack{{flex:1;height:9px;background:color-mix(in srgb,var(--accent) 9%,transparent);border-radius:5px;overflow:hidden}} .mfill{{display:block;height:100%;background:var(--accent)}} .mval{{width:14px;text-align:right;font:600 11px var(--mono)}}
 .muted{{color:var(--muted)}} footer{{margin-top:44px;border-top:1px solid var(--line);padding-top:16px;color:var(--muted);font-size:13px}}
 svg text{{font-family:-apple-system,sans-serif}}
</style></head><body><main>
 <p style="font-size:13px"><a href="./">&larr; Back to the summary portfolio</a></p>
 <h1>Every merge, broken down</h1>
 <p class="lede">All 35 merged fixes, each placed in a threat model and the 13-layer ML stack, scored on the risk rubric, with the <b>real diff</b>. Pulled live from GitHub — every card links to the public PR.</p>

 <h2>How the rubric works</h2>
 <div class="panel">
  <p style="margin:2px 0 10px;font-size:14.5px">Each finding scores four factors from 1&ndash;5. Two make <b>likelihood</b>, two make <b>impact</b>. <b>Risk = likelihood &times; impact</b>, out of 25 (NIST SP 800-30 / OWASP shape).</p>
  <div class="barrow"><span class="blab"><b>Exposure</b> — who can reach it</span><span class="btrack"></span><span class="bval muted">L</span></div>
  <div class="barrow"><span class="blab"><b>Ease</b> — how hard to trigger</span><span class="btrack"></span><span class="bval muted">L</span></div>
  <div class="barrow"><span class="blab"><b>Attacker gain</b> — what success gives</span><span class="btrack"></span><span class="bval muted">I</span></div>
  <div class="barrow"><span class="blab"><b>Blast radius</b> — how far it spreads</span><span class="btrack"></span><span class="bval muted">I</span></div>
  <p class="muted" style="font-size:13px;margin-top:8px">Most ML-integrity bugs here score Low: trusted usage, and the payoff is a quietly wrong number rather than attacker control. That is the honest reading — and exactly why they are dangerous, because nothing crashes. The authorization and memory-safety fixes score higher.</p>
 </div>

 <h2>Where the 35 fixes land in the stack</h2>
 <div class="panel">{stack_svg}</div>
 <div class="panel"><div class="mtitle" style="margin-bottom:8px">Merged PRs per layer</div>{bars_html}</div>
 <p class="muted" style="font-size:13.5px">Bug classes across the set: {", ".join(f"{esc(k)} ({v})" for k,v in cls_counts.most_common())}.</p>

 <h2>The 35, layer by layer</h2>
 {"".join(sections)}

 <footer>Diffs and metadata pulled live via the GitHub API against <a href="https://github.com/tritsystem">@tritsystem</a> on generation. Risk scores are my analysis on the stated rubric; every diff is the real merged change — click any PR to verify. Feature additions are labelled and scored 1/1/1/1 (not bugs). No unsolicited testing of third-party systems.</footer>
</main></body></html>'''
open("deep-dive.html","w",encoding="utf-8").write(HTML)
print("wrote deep-dive.html", len(HTML), "bytes;", len(prs), "cards")
