"""Editorial photos from Wikimedia Commons (freely licensed, credited on screen).

Daily flow:
  1. The editorial step writes editions/DATE/subjects.json: the people and named places each story could show.
  2. `python -m isobar.photos candidates ED` (GitHub Actions) finds up to 3 reusable photos per subject, saves
     320px thumbnails as ED/photos/<story><letter>.jpg (e.g. 3B) and writes photos.json + photos.md (contact sheet).
  3. The editorial step looks at the thumbnails and sets "photo": "3B" (or nothing) per story in editorial.json.
  4. At render time `python -m isobar.photos fetch ED` downloads each chosen photo at 1280px, and
     `python -m isobar.photos sheet ED` re-writes the contact sheet with the choices starred.
Overrides: change "photo" in editorial.json ("3B", or remove it) and re-render.
"""
import argparse, json, re, string, sys, time, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "IsobarNewsBot/0.2 (https://isobar.news; editorial photo selection)"}
API = "https://commons.wikimedia.org/w/api.php?"
REUSABLE = re.compile(r"^(CC BY(-SA)? [0-9.]+( [A-Za-z-]+)?|CC0( 1\.0)?|Public domain|PD[- ].*)$", re.I)
NOT_PHOTO = re.compile(r"(?i)\b(map|maps|osm|openstreetmap|flag|logo|coat of arms|emblem|seal|diagram|chart|graph|infographic|transits|signature|locator|icon|poster|stamp|banknote|coin|plaque)\b|\.svg$|\.tif+$")
PER_SUBJECT, MAX_SUBJECTS = 3, 2


def _get(url, tries=3):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        except Exception:
            if k == tries - 1: raise
            time.sleep(2 * (k + 1))


def _api(**p):
    return json.loads(_get(API + urllib.parse.urlencode({**p, "format": "json"})))


def _clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def search(subject, width=320):
    r = _api(action="query", generator="search", gsrsearch="filetype:bitmap " + subject, gsrnamespace=6, gsrlimit=12,
             prop="imageinfo", iiprop="url|extmetadata|size", iiurlwidth=width,
             iiextmetadatafilter="LicenseShortName|Artist|DateTimeOriginal|ImageDescription")
    out = []
    for pg in sorted(r.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {}); title = pg["title"][5:]
        lic = _clean(m.get("LicenseShortName", {}).get("value"))
        if not REUSABLE.match(lic) or NOT_PHOTO.search(title) or (ii.get("width") or 0) < 800 or not ii.get("thumburl"):
            continue
        out.append({"subject": subject, "title": title, "page": ii["descriptionurl"], "thumb": ii["thumburl"],
                    "license": lic, "artist": _clean(m.get("Artist", {}).get("value"))[:80] or "unknown",
                    "date": (re.findall(r"\d{4}(?:-\d\d(?:-\d\d)?)?", _clean(m.get("DateTimeOriginal", {}).get("value"))) or [""])[0],
                    "description": _clean(m.get("ImageDescription", {}).get("value"))[:160],
                    "width": ii.get("width"), "height": ii.get("height")})
        if len(out) == PER_SUBJECT: break
    return out


def credit(c):
    return f"Photo: {c['artist']} / Wikimedia Commons, {c['license']}"


def candidates(ed):
    ed = Path(ed); req = json.loads((ed / "subjects.json").read_text())
    (ed / "photos").mkdir(exist_ok=True)
    cands = {}
    for n, sid in enumerate(req["order"], 1):
        letters = iter(string.ascii_uppercase)
        for subject in req["subjects"].get(sid, [])[:MAX_SUBJECTS]:
            try:
                found = search(subject)
            except Exception as e:
                print(f"photos: search failed for {subject!r}: {e!r}"); found = []
            for c in found:
                pid = f"{n}{next(letters)}"
                (ed / "photos" / f"{pid}.jpg").write_bytes(_get(c["thumb"]))
                cands[pid] = {**c, "story": sid, "n": n}
            time.sleep(0.5)
    (ed / "photos.json").write_text(json.dumps(cands, indent=1, ensure_ascii=False))
    sheet(ed); print(f"photos: {len(cands)} candidates for {len(req['order'])} stories")


def chosen(ed):
    """{story_id: photo_id} from editorial.json."""
    e = json.loads((Path(ed) / "editorial.json").read_text()) if (Path(ed) / "editorial.json").exists() else {}
    return {sid: s["photo"] for sid, s in e.get("stories", {}).items() if s.get("photo")}


def sheet(ed):
    """photos.md: every candidate with its ID, subject, date, licence and credit; chosen ones starred."""
    ed = Path(ed); cands = json.loads((ed / "photos.json").read_text())
    pick = set(chosen(ed).values()); heads = {}
    sp = ed / "script.json"
    if sp.exists():
        heads = {s["id"]: s["headline"] for s in json.loads(sp.read_text())["stories"]}
    md = [f"# Photo candidates for {ed.name}", "",
          "★ = used in the video. To change: reply with e.g. `3: use 3B` or `5: no photo`.", ""]
    by_story = {}
    for pid, c in cands.items(): by_story.setdefault(c["n"], []).append((pid, c))
    for n in sorted(by_story):
        sid = by_story[n][0][1]["story"]
        md += [f"## {n}. {heads.get(sid, sid)}", "", "| ID | Photo | Details |", "|---|---|---|"]
        for pid, c in by_story[n]:
            star = " ★" if pid in pick else ""
            md.append(f"| **{pid}**{star} | <img src=\"photos/{pid}.jpg\" width=\"240\"> | **{c['subject']}**<br>"
                      f"[{c['title'][:60]}]({c['page']})<br>{c['date'] or 'date unknown'} · {c['license']}<br>{c['artist']} |")
        md.append("")
    (ed / "photos.md").write_text("\n".join(md))


def fetch(ed, width=1280):
    """Download each chosen photo at render size. Missing or failed downloads just mean no photo for that story."""
    ed = Path(ed)
    if not (ed / "photos.json").exists(): return
    cands = json.loads((ed / "photos.json").read_text())
    for sid, pid in chosen(ed).items():
        c = cands.get(pid)
        if not c: print(f"photos: {pid} not among the candidates"); continue
        try:
            r = _api(action="query", titles="File:" + c["title"], prop="imageinfo", iiprop="url", iiurlwidth=width)
            url = next(iter(r["query"]["pages"].values()))["imageinfo"][0]["thumburl"]
            (ed / "photos" / f"use_{pid}.jpg").write_bytes(_get(url)); print(f"photos: {pid} downloaded")
        except Exception as e:
            print(f"photos: could not fetch {pid}: {e!r}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["candidates", "fetch", "sheet"]); ap.add_argument("edition")
    a = ap.parse_args()
    {"candidates": candidates, "fetch": fetch, "sheet": sheet}[a.cmd](a.edition)
