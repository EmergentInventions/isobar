"""Build script.json (what the renderer and the voice read) from candidates.json.

If editorial.json exists (written by the Claude editorial step) its picks and wording
win; otherwise a plain automatic draft is produced from the source summaries.
editorial.json shape:
  {"radar": [{"id": ..., "why": ...}, ...],
   "stories": {"<id>": {"headline": ..., "facts": [3], "narration": ..., "category": ..., "place": ...}},
   "intro": ..., "radar_bumper": ..., "outro": ...}
"""
import argparse
import datetime as dt
import re

import geonamescache
from num2words import num2words

from .common import ROOT, edition_dir, load, save, today_utc

FEATURE = ["BBC", "The New York Times", "The Guardian", "Financial Times", "Al Jazeera", "Le Monde", "Der Spiegel",
           "El País", "France 24", "DW", "South China Morning Post", "The Hindu", "NBC News", "CBS News", "PBS",
           "Scientific American", "Science", "The Kyiv Independent", "Dawn", "Euronews", "Reuters", "AP News"]

_gc = None


def geocode(loc):
    """'Kyiv, Ukraine' -> (lat, lon) using offline GeoNames data; falls back to the capital."""
    global _gc
    if not loc:
        return None, None
    _gc = _gc or geonamescache.GeonamesCache()
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    for name in parts[:1]:
        hits = _gc.search_cities(name, case_sensitive=False, contains_search=False)
        if hits:
            c = max(hits, key=lambda h: h.get("population", 0))
            return float(c["latitude"]), float(c["longitude"])
    countries = _gc.get_countries_by_names()
    for p in reversed(parts):
        if p in countries and countries[p].get("capital"):
            hits = _gc.search_cities(countries[p]["capital"], contains_search=False)
            if hits:
                c = max(hits, key=lambda h: h.get("population", 0))
                return float(c["latitude"]), float(c["longitude"])
    return None, None


def feature_line(names, total, k=4):
    pri = [n for n in FEATURE if n in names][:k]
    pri += [n for n in names if n not in pri][: k - len(pri)]
    rest = max(0, total - len(pri))
    return ", ".join(pri) + (f" and {rest} more" if rest else "")


def words(n):
    return num2words(n, lang="en_GB")


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t or "") if len(s.strip()) > 20]


def shorten(t, n=92):
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    return t if len(t) <= n else t[: t.rfind(" ", 0, n)] + "…"


def trim_words(text, limit=120):
    out, n = [], 0
    for sent in sentences(text) or [text]:
        w = len(sent.split())
        if out and n + w > limit:
            break
        out.append(sent); n += w
    return " ".join(out)


def auto_story(s, label_cat):
    facts = [shorten(p) for p in s.get("points", [])][:3] or [shorten(x) for x in sentences(s["summary"])][:3]
    return {"headline": s["title"], "facts": facts, "narration": trim_words(s["summary"]), "category": label_cat,
            "place": s.get("location")}


def build(d, date, strapline=None):
    c = load(d / "candidates.json")
    ed = load(d / "editorial.json") if (d / "editorial.json").exists() else {}
    pool = {s["id"]: s for s in c["radar_pool"]}
    radar = ed.get("radar") or [{"id": i, "why": ""} for i in c["radar_default"]]
    chosen = [(s, "top", None) for s in c["top"]] + [(pool[r["id"]], "radar", r.get("why")) for r in radar if r["id"] in pool]
    stories, all_outlets = [], []
    for k, (s, seg, why) in enumerate(chosen):
        e = {**auto_story(s, s["category"].upper()), **ed.get("stories", {}).get(s["id"], {})}
        n = s["outlet_count"]
        # No spoken rank or outlet count: the intro explains the ranking and the screen shows the numbers.
        if seg == "top":
            cat = e["category"].upper()
        else:
            cat = "BELOW THE RADAR · " + e["category"].upper().replace("BELOW THE RADAR · ", "")
        lat, lon = geocode(e.get("place"))
        stories.append({
            "id": s["id"], "segment": seg, "category": cat, "label": e["category"].replace("BELOW THE RADAR · ", ""), "headline": e["headline"], "facts": e["facts"][:3],
            "narration": e["narration"],
            "place": e.get("place") if lat is not None else None, "country": e.get("country"), "countries": e.get("countries"), "lat": lat, "lon": lon,
            "sources": n, "outlets": s["outlets"], "outlet_line": feature_line(s["outlets"], n),
            "why": why or e.get("why") or "", "card": e.get("card"), "photo": e.get("photo"),
        })
        all_outlets += [o for o in s["outlets"] if o not in all_outlets]
    day = dt.datetime.strptime(date, "%Y-%m-%d")
    nice = f"{day:%A} {day.day} {day:%B %Y}"
    spoken = f"{day:%A} the {num2words(day.day, to='ordinal')} of {day:%B}"
    n_all = len(all_outlets)
    script = {
        "show": "Isobar.News", "date": nice, "strapline": strapline, "source": c["source"],
        "intro": {"narration": ed.get("intro") or (
            f"This is Isobar News for {spoken}. We start with the seven stories that news outlets around the world "
            "covered most today, and then three that got far less attention, but could matter just as much. "
            "Here's the news.")},
        "radar_bumper": ed.get("radar_bumper") or ("Now, three stories from below the radar. They got much less "
                                                   "coverage, but each could make a real difference to people's lives."),
        "outro": {"narration": ed.get("outro") or (
            f"That's Isobar News for today. We drew on reporting from {words(n_all)} outlets around the world. "
            "Thanks for watching, and see you tomorrow.")},
        "stories": stories,
        "all_outlets": sorted(all_outlets, key=lambda x: re.sub(r"^(The|Le|La|El|Der) ", "", x).lower()),
        "credit": ("Story clustering and summaries adapted from Kagi News · CC BY-NC 4.0" if c["source"] == "kagi"
                   else "Stories clustered by Isobar News from outlets' public feeds"),
    }
    return script


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".")
    ap.add_argument("--date", default=today_utc())
    a = ap.parse_args()
    d = edition_dir(a.base, a.date)
    cfg = load(ROOT / "data" / "config.json")
    s = build(d, a.date, cfg.get("strapline"))
    save(d / "script.json", s)
    words_total = sum(len(x.split()) for x in [s["intro"]["narration"], s["radar_bumper"], s["outro"]["narration"]] +
                      [st["narration"] for st in s["stories"]])
    print(f"script: {len(s['stories'])} stories, {words_total} words (~{words_total / 140:.1f} min at a natural pace)")


if __name__ == "__main__":
    main()
