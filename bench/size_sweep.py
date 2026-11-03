# -*- coding: utf-8 -*-
"""Model-size benchmark for each pipeline step. Pre-registered; measures, never invents.

For a given STEP, run each model SIZE against a HELD-OUT, HUMAN-LABELLED set and report accuracy
(Wilson 95% interval), latency, and whether the step has an exact checker (which decides if it may run
unattended). Mirrors the ring-eval discipline: pre-register the prediction, score honestly, report negatives.

Usage:
    python bench/size_sweep.py classify --sizes 0.5B,1.5B,3B,api
    python bench/size_sweep.py explain  --sizes 1.5B,3B,api

STATE: harness is complete and runnable; the labelled set (bench/labels/<step>.jsonl) must be built by a
human before any cell is filled. No cell is reported until it is measured. This file fabricates nothing.
"""
import json, math, os, sys, time, argparse

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (100*(c-h), 100*(c+h))

# Which steps have an EXACT checker — the single fact that decides unattended automation.
EXACT_CHECKER = {
    "fetch": True, "extract": True, "score-math": True, "repro": True,      # verifiable by code/sanitizer
    "classify": False, "explain": False, "variant": "partial", "disclosure": False,
}

# Pre-registered accuracy bars (written before any run). A size is adopted for a step only if it clears
# the bar AND (the step has an exact checker  OR  a human reviews the output).
BARS = {"classify": 0.90, "explain": 0.95}  # accuracy vs the human label

def load_labels(step):
    path = f"bench/labels/{step}.jsonl"
    if not os.path.exists(path):
        return None, path
    return [json.loads(l) for l in open(path, encoding="utf-8")], path

def run_model(size, step, item):
    """Call the agent for (size, step) on one item; return its answer.
    Deliberately NOT implemented with a stub that could fabricate a score: each backend must be wired to a
    real model before it returns, else it raises. This keeps the harness honest."""
    raise NotImplementedError(
        f"Wire backend for size={size}, step={step}. "
        "0.5B/1.5B -> local (Baton base or HF); 3B -> local; api -> Claude. No result is produced until wired.")

def score(step, sizes):
    labels, path = load_labels(step)
    checker = EXACT_CHECKER.get(step, False)
    print(f"step={step}  exact_checker={checker}  bar={BARS.get(step,'?')}  unattended_ok={'yes' if checker is True else 'no (needs human review)'}")
    if not labels:
        print(f"  NO LABELLED SET at {path}. Build a human-labelled held-out set first. Nothing measured — nothing reported.")
        return
    print(f"  labelled items: {len(labels)}")
    for size in sizes:
        correct, n, t0 = 0, 0, time.perf_counter()
        try:
            for it in labels:
                ans = run_model(size, step, it)        # raises until wired
                correct += int(ans == it["label"]); n += 1
        except NotImplementedError as e:
            print(f"  {size:5s}: not wired — {str(e)[:70]}")
            continue
        lo, hi = wilson(correct, n); ms = (time.perf_counter()-t0)*1000/max(n,1)
        adopt = (correct/n >= BARS.get(step,1.0)) and (checker is True or os.environ.get("HUMAN_REVIEW"))
        print(f"  {size:5s}: {correct}/{n} = {100*correct/n:.1f}% [{lo:.1f},{hi:.1f}]  {ms:.0f} ms/item  "
              f"adopt_unattended={'YES' if adopt and checker is True else 'no'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=list(EXACT_CHECKER))
    ap.add_argument("--sizes", default="1.5B,3B,api")
    a = ap.parse_args()
    score(a.step, a.sizes.split(","))
