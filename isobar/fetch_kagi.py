"""Primary source: Kagi News (https://news.kagi.com). Polls until today's batch exists.

Kagi publishes once a day at around 12:00 UTC; translation can take ~30 minutes, but
English is requested directly. We only accept a batch created today (UTC) at or after
11:00 UTC, so a stale or partial batch is never used.
"""
import argparse
import datetime as dt
import sys
import time

import requests

from .common import UA, edition_dir, save, today_utc, unique_outlets

BASE = "https://kite.kagi.com/api"
WANTED = ["world", "business", "science", "technology", "usa"]
MIN_WORLD_STORIES = 5


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params={"lang": "en", **params}, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def fresh_batch(date: str):
    b = get("/batches/latest")
    created = dt.datetime.fromisoformat(b["createdAt"].replace("Z", "+00:00"))
    ok = created.strftime("%Y-%m-%d") == date and created.hour >= 11
    return (b if ok else None), created


def story_record(s, category):
    domains = [a.get("domain", "") for a in (s.get("articles") or [])]
    names = unique_outlets(domains)
    return {
        "id": s.get("id") or f"{category}-{s.get('cluster_number')}",
        "category": category,
        "title": s.get("title", "").strip(),
        "summary": (s.get("short_summary") or "").strip(),
        "points": [p for p in (s.get("talking_points") or []) if p][:6],
        "location": s.get("location"),
        "domains": sorted({d for d in domains if d}),
        "outlets": names,
        "outlet_count": len(names),
        "kagi_unique_domains": s.get("unique_domains"),
        "context": context(s),
    }


CONTEXT_LISTS = ["perspectives", "timeline", "historical_background", "other_angles", "humanitarian_impact",
                 "international_reactions", "technical_details", "scientific_significance", "industry_impact",
                 "business_angle_points", "user_action_items", "did_you_know"]


def context(s):
    """The rest of Kagi's record, for the editorial step: 'what next' lines, framing and quotes come only from here.
    Every item keeps its [domain#n] source tags so claims stay attributable."""
    out = {}
    for k in CONTEXT_LISTS:
        v = s.get(k)
        if not v: continue
        if isinstance(v, list):
            v = [x.get("text") or (f"{x.get('date', '')}: {x.get('content', '')}" if "content" in x else str(x))
                 if isinstance(x, dict) else x for x in v]
        out[k] = v
    if s.get("suggested_qna"):
        out["qna"] = [{"q": x.get("question"), "a": x.get("answer")} for x in s["suggested_qna"]]
    if s.get("quote"):
        out["quote"] = {"text": s["quote"], "author": s.get("quote_author"), "via": s.get("quote_attribution")}
    # one headline per outlet: how each framed the story (used for the "how outlets framed it" segment)
    seen, heads = set(), []
    for a in s.get("articles") or []:
        dmn = a.get("domain", "")
        if dmn and dmn not in seen and a.get("title"):
            seen.add(dmn); heads.append({"domain": dmn, "title": a["title"].strip()})
    out["headlines"] = heads[:40]
    return out


def fetch(date: str):
    b, created = fresh_batch(date)
    if not b:
        return None, created
    cats = get(f"/batches/{b['id']}/categories").get("categories", [])
    stories = []
    for c in cats:
        name = (c.get("categoryName") or c.get("categoryId") or "").strip()
        if name.lower() not in WANTED:
            continue
        data = get(f"/batches/{b['id']}/categories/{c['id']}/stories", limit=40)
        stories += [story_record(s, name) for s in data.get("stories", [])]
    if sum(1 for s in stories if s["category"].lower() == "world") < MIN_WORLD_STORIES:
        return None, created  # batch exists but is not filled in yet
    return {"source": "kagi", "batch_id": b["id"], "created_at": b["createdAt"], "stories": stories}, created


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".")
    ap.add_argument("--date", default=today_utc())
    ap.add_argument("--deadline", default="12:45", help="give up at this UTC time (HH:MM)")
    ap.add_argument("--every", type=int, default=60, help="seconds between checks")
    a = ap.parse_args()
    hh, mm = map(int, a.deadline.split(":"))
    deadline = dt.datetime.strptime(a.date, "%Y-%m-%d").replace(hour=hh, minute=mm, tzinfo=dt.timezone.utc)
    out = edition_dir(a.base, a.date) / "stories.json"
    while True:
        try:
            data, created = fetch(a.date)
            if data:
                save(out, data)
                print(f"kagi: saved {len(data['stories'])} stories from batch {data['batch_id']} ({data['created_at']})")
                return 0
            print(f"kagi: latest batch is from {created:%Y-%m-%d %H:%M} UTC, waiting")
        except Exception as e:  # network blips or API changes: keep polling until deadline
            print(f"kagi: error {e!r}, retrying")
        if dt.datetime.now(dt.timezone.utc) >= deadline:
            print("kagi: no fresh batch before deadline")
            return 2
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
