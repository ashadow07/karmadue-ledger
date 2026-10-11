#!/usr/bin/env python3
"""The chain only grows: each day's seq must be >= the previous day's. An anchor file, once committed, must never change (git history shows it)."""
import glob, json
heads = [json.load(open(p)) for p in sorted(glob.glob("heads/*.json"))]
for a, b in zip(heads, heads[1:]):
    assert b["seq"] >= a["seq"], f"seq went backwards: {a['anchored_on']} {a['seq']} -> {b['anchored_on']} {b['seq']}"
print(f"OK {len(heads)} anchors, seq non-decreasing")
