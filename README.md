# Security & correctness track record

Live: **https://tritsystem.github.io/sec-portfolio/**
Deep-dive (all 35 merges, real diffs): **https://tritsystem.github.io/sec-portfolio/deep-dive.html**

Every claim links to a public GitHub artifact. Contributions counted only when merged; filed/open work labelled.

## Reproducible pipeline (no model in the loop)

The deep-dive page is generated deterministically from the real merged diffs — the automation tier-1 from the
operating plan (model-free, so no hallucination risk):

```
python pull_diffs.py      # deterministic: pull merged PRs + real diffs via gh; flags UNCLASSIFIED PRs
python data/classify.py   # 13-layer placement + risk rubric (human-authored table)
python data/annotate.py   # per-line walkthroughs (human-authored)
python gen_deepdive.py     # render before/after + rubric + walkthrough for all 35
```

- `.github/workflows/regenerate.yml` runs this on a weekly timer and on demand; new PRs appear as `UNCLASSIFIED`
  until a human adds their ~4-line entry to `classify.py` + `annotate.py`.
- `bench/size_sweep.py` is the pre-registered model-size benchmark harness: it measures each step's accuracy
  against a human-labelled held-out set, or reports nothing. It fabricates no numbers, and marks the steps that
  lack an exact checker as *not* safe to automate unattended.

The division of labour is the point: the mechanical work (pull, extract, rubric arithmetic, render) is deterministic
or exact-checkable; the judgment (which layer, the walkthrough) is human-authored, because there is no program that
can verify it and a small model would be confidently wrong.
