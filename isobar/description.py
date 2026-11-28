"""Write the YouTube description: chapters, outlets, then attribution last."""
import argparse, json
from pathlib import Path

from .common import yt_title


def mmss(x):
    x = int(x); return f"{x // 60}:{x % 60:02d}"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); ap.add_argument("--audio", default="audio_draft"); a = ap.parse_args()
    ed = Path(a.edition); s = json.load(open(ed / "script.json"))
    L = json.load(open(ed / f"scene_lengths_{a.audio}.json"))
    t, at = 0.0, {}
    for k, v in L.items():
        at[k] = t; t += v
    first_radar = next((i for i, x in enumerate(s["stories"]) if x["segment"] == "radar"), None)
    out = [yt_title(s.get("title_lead") or s["stories"][0]["headline"], ed.name, len(s["stories"]) - 1, s.get("title_tags")), "", "Chapters", "0:00 Today's stories"]
    for i, st in enumerate(s["stories"]):
        if i == first_radar and "08a_radar" in at:
            out.append(f"{mmss(at['08a_radar'])} Below the Radar")
        out.append(f"{mmss(at[f'{i+2:02d}_story'])} {st['headline']} ({st['sources']} outlets)")
    out += [f"{mmss(at['99_outro'])} Credits", "", "Website: https://isobar.news",
            "How stories are chosen: https://github.com/EmergentInventions/isobar", "",
            f"This edition drew on reporting from {len(s['all_outlets'])} outlets:", ", ".join(s["all_outlets"]), ""]
    if s.get("source") == "kagi":
        out.append("Attribution: story clustering and summaries adapted from Kagi News (https://news.kagi.com), licensed under "
                   "CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/). Isobar News has edited, re-ranked and rewritten the material for video.")
    mj = ed.parent.parent / "assets" / "music" / "music.json"      # licensed music bed: its credit line, if it needs one
    if mj.exists() and json.load(open(mj)).get("credit"):
        out += ["", "Music: " + json.load(open(mj))["credit"]]
    (ed / "description.txt").write_text("\n".join(out) + "\n")
    print("description written")


if __name__ == "__main__":
    main()
