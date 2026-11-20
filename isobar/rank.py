"""Isobar's published selection rule.

1. Count distinct outlets per story (aggregators and platforms excluded).
2. Merge stories that are clearly the same event (similar text, same place).
3. Most covered: the 7 World/USA stories with the most outlets, at most 2 per country.
4. Below the Radar: 3 stories with at most half the 7th story's outlets (and at most 12), picked for impact (editorial step,
   with the reason shown on screen). The default pick here is a fallback only.
"""
import argparse
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .common import edition_dir, load, save, today_utc, unique_outlets

TOP_N, RADAR_N, PER_COUNTRY, RADAR_MAX = 7, 3, 2, 12
TOP_CATS = {"world", "usa"}
MERGE_SIM = 0.42


def country(loc):
    return (loc or "").split(",")[-1].strip().lower() or None


def merge_duplicates(stories):
    if len(stories) < 2:
        return stories
    txt = [f"{s['title']} {s['summary']}" for s in stories]
    sim = cosine_similarity(TfidfVectorizer(stop_words="english", sublinear_tf=True).fit_transform(txt))
    order = sorted(range(len(stories)), key=lambda i: -stories[i]["outlet_count"])
    absorbed, out = set(), []
    for i in order:
        if i in absorbed:
            continue
        s = dict(stories[i])
        for j in order:
            if j == i or j in absorbed:
                continue
            loc_i, loc_j = (s.get("location") or "").lower(), (stories[j].get("location") or "").lower()
            same_city = bool(loc_i) and loc_i == loc_j
            same_place = country(loc_i) and country(loc_i) == country(loc_j)
            if (same_city and sim[i, j] >= 0.22) or (sim[i, j] >= MERGE_SIM and (same_place or sim[i, j] >= 0.6)):
                o = stories[j]
                s["domains"] = sorted(set(s["domains"]) | set(o["domains"]))
                s["points"] = s.get("points", []) + [p for p in o.get("points", []) if p not in s.get("points", [])]
                s.setdefault("merged_titles", []).append(o["title"])
                absorbed.add(j)
        s["outlets"] = unique_outlets(s["domains"])
        s["outlet_count"] = len(s["outlets"])
        out.append(s)
    return sorted(out, key=lambda s: -s["outlet_count"])


def select(stories):
    stories = merge_duplicates(stories)
    top, per = [], {}
    for s in stories:
        if s["category"].lower() not in TOP_CATS:
            continue
        c = country(s.get("location"))
        if c and per.get(c, 0) >= PER_COUNTRY:
            continue
        top.append(s)
        per[c] = per.get(c, 0) + 1
        if len(top) == TOP_N:
            break
    floor = min(s["outlet_count"] for s in top) if top else 0
    taken = {s["id"] for s in top}
    ceiling = max(4, min(RADAR_MAX, floor // 2))
    pool = [s for s in stories if s["id"] not in taken and 3 <= s["outlet_count"] <= ceiling][:25]
    default, seen = [], set()
    for s in pool:  # fallback: one per category, most covered first
        if s["category"] not in seen:
            default.append(s["id"]); seen.add(s["category"])
        if len(default) == RADAR_N:
            break
    for s in pool:  # not enough categories: fill from the rest of the pool
        if len(default) == RADAR_N:
            break
        if s["id"] not in default:
            default.append(s["id"])
    return top, pool, default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".")
    ap.add_argument("--date", default=today_utc())
    a = ap.parse_args()
    d = edition_dir(a.base, a.date)
    data = load(d / "stories.json")
    top, pool, default = select(data["stories"])
    save(d / "candidates.json", {"source": data["source"], "top": top, "radar_pool": pool, "radar_default": default})
    print("most covered:", [(s["outlet_count"], s["title"][:50]) for s in top])
    print("radar pool:", len(pool), "default:", default)


if __name__ == "__main__":
    main()
