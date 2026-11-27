"""Acceptance checks: does this edition keep the promise its title and intro make?

Writes ED/checks.md with PASS / WARN per check. Run after render (it reads the scene lengths).
Non-blocking for now: it reports, it does not stop the render.
"""
import argparse
import json
import re
from pathlib import Path

LOADED = ["slammed", "slams", "shocking", "regime", "blasted", "blasts", "outrage", "outrageous", "disaster",
          "devastating", "horrific", "brutal", "chaos", "chaotic", "radical", "extremist", "controversial",
          "so-called", "mere", "finally", "admits", "claims victory", "far-right", "far-left", "hardline"]
ATTRIBUTION = re.compile(r"\b(says?|said|according to|reports?|reported|told|announced|stated|confirmed|"
                         r"estimates?|found|shows?|showed|argues?|argued|warned|warns)\b", re.I)
MAX_RUNTIME = 10 * 60      # seconds; the format aims for about ten minutes
RADAR_MAX_OUTLETS = 10     # Below the Radar must be genuinely under-covered
TOP_MUST_INCLUDE = 5       # the five most-covered stories in the pool must be in the top segment


def run(ed: Path, audio: str):
    s = json.load(open(ed / "script.json"))
    c = json.load(open(ed / "candidates.json"))
    rows = []

    def add(ok, name, detail=""):
        rows.append(("PASS" if ok else "WARN", name, detail))

    # 1. The most-covered stories are all in the top segment
    pool = c["top"] + c["radar_pool"]
    must = {x["id"] for x in sorted(pool, key=lambda x: -x["outlet_count"])[:TOP_MUST_INCLUDE]}
    top_ids = {x["id"] for x in s["stories"] if x["segment"] == "top"}
    add(must <= top_ids, f"Top {TOP_MUST_INCLUDE} most-covered stories included", ", ".join(sorted(must - top_ids)))

    # 2. Below the Radar really is under-covered
    loud = [f"{x['headline']} ({x['sources']})" for x in s["stories"]
            if x["segment"] == "radar" and x["sources"] > RADAR_MAX_OUTLETS]
    add(not loud, f"Below the Radar stories have at most {RADAR_MAX_OUTLETS} outlets", "; ".join(loud))

    # 3-6. Per-story rules (EDITORIAL.md section 2)
    for i, st in enumerate(s["stories"], 1):
        n = st["narration"]; wc = len(n.split()); tag = f"{i:02d} {st['headline'][:50]}"
        probs = []
        if len(st["headline"]) > 70: probs.append(f"headline {len(st['headline'])} chars (max 70)")
        if "?" in st["headline"]: probs.append("question mark in headline")
        if len(st["facts"]) != 3: probs.append(f"{len(st['facts'])} facts (need 3)")
        probs += [f"fact {k} is {len(f)} chars (max 90)" for k, f in enumerate(st["facts"], 1) if len(f) > 90]
        if not 90 <= wc <= 150: probs.append(f"narration {wc} words (90-150)")
        hits = [w for w in LOADED if re.search(rf"\b{re.escape(w)}\b", n + " " + st["headline"], re.I)]
        if hits: probs.append("loaded words: " + ", ".join(hits))
        if not ATTRIBUTION.search(n): probs.append("no attribution verb (says, according to…)")
        add(not probs, tag, "; ".join(probs))

    # 7. Runtime
    lf = ed / f"scene_lengths_{audio}.json"
    if lf.exists():
        total = sum(json.load(open(lf)).values())
        add(total <= MAX_RUNTIME, "Runtime at most 10:00", f"{int(total // 60)}:{int(total % 60):02d}")

    warns = sum(r[0] == "WARN" for r in rows)
    out = [f"# Acceptance checks: {ed.name}", "", f"{len(rows) - warns} passed, {warns} to look at.", "",
           "| Result | Check | Detail |", "|---|---|---|"]
    out += [f"| {r} | {n} | {d} |" for r, n, d in rows]
    (ed / "checks.md").write_text("\n".join(out) + "\n")
    print(f"checks: {len(rows) - warns} passed, {warns} warnings")
    return warns


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); ap.add_argument("--audio", default="audio_draft")
    a = ap.parse_args(); run(Path(a.edition), a.audio)


if __name__ == "__main__":
    main()
