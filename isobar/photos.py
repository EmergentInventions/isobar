"""Editorial photos from Wikimedia Commons (freely licensed, credited on screen).

Daily flow:
  1. The editorial step writes editions/DATE/subjects.json: the people and named places each story could show.
  2. `python -m isobar.photos candidates ED` (GitHub Actions) finds up to 3 reusable images per subject and saves
     320px thumbnails as ED/photos/<story><letter>.jpg (e.g. 3B), with photos.json + photos.md (contact sheet).
     How each subject is searched, best first:
       a. Wikidata: the subject's item (e.g. Q-number for a person) and its main image (P18) - the picture Wikipedia uses;
       b. the subject's own Commons category (Wikidata P373);
       c. plain Commons text search - weakest: a match on words in the file name, NOT a confirmed picture of the subject.
     Every candidate records which of these matched it, and the contact sheet shows it.
  3. The editorial step looks at the thumbnails and sets "photo": "3B" (or nothing) per story in editorial.json.
     A specific Commons file can be named instead: "photo": "File:Some_file.jpg".
  4. At render time `python -m isobar.photos fetch ED` downloads each chosen image at 1280px, and
     `python -m isobar.photos sheet ED` re-writes the contact sheet with the choices starred.
"""
import argparse, io, json, re, string, time, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "IsobarNewsBot/0.3 (https://isobar.news; editorial photo selection)"}
COMMONS = "https://commons.wikimedia.org/w/api.php?"
WIKIDATA = "https://www.wikidata.org/w/api.php?"
REUSABLE = re.compile(r"^(CC BY(-SA)? [0-9.]+( [A-Za-z-]+)?|CC0( 1\.0)?|Public domain|PD[- ].*)$", re.I)
# applied to category and text-search results only; a subject's own Wikidata image is trusted (it may be an official poster)
NOT_PHOTO = re.compile(r"(?i)\b(map|maps|osm|openstreetmap|flag|logo|coat of arms|emblem|seal|diagram|chart|graph|infographic|"
                       r"transits|signature|locator|icon|poster|stamp|banknote|coin|plaque)\b|\.svg$|\.tif+$|\.pdf$")
PER_SUBJECT, MAX_SUBJECTS = 5, 2
# per subject: up to 1 Wikidata main image, 2 from its Commons category, 2 from text search (so good plain matches still show)
QUOTA = {"wikidata": 1, "category": 2, "text": 2}
II = dict(prop="imageinfo", iiprop="url|extmetadata|size", iiextmetadatafilter="LicenseShortName|Artist|DateTimeOriginal|ImageDescription")


def _get(url, tries=3):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        except Exception:
            if k == tries - 1: raise
            time.sleep(2 * (k + 1))


def _api(base=COMMONS, **p):
    return json.loads(_get(base + urllib.parse.urlencode({**p, "format": "json"})))


def _clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def safe(pid):
    """File-name-safe form of a photo id ('3B' stays '3B'; 'File:X y.jpg' becomes 'File_X_y_jpg')."""
    return re.sub(r"[^A-Za-z0-9]+", "_", pid).strip("_")[:80]


def _info(pg, width_ok=800):
    """Candidate dict from an imageinfo page, or None if unusable (licence, size)."""
    if "imageinfo" not in pg: return None
    ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {})
    lic = _clean(m.get("LicenseShortName", {}).get("value"))
    if not REUSABLE.match(lic) or (ii.get("width") or 0) < width_ok or not ii.get("thumburl"): return None
    return {"title": pg["title"][5:], "page": ii["descriptionurl"], "thumb": ii["thumburl"], "license": lic,
            "artist": _clean(m.get("Artist", {}).get("value"))[:80] or "unknown",
            "date": (re.findall(r"\d{4}(?:-\d\d(?:-\d\d)?)?", _clean(m.get("DateTimeOriginal", {}).get("value"))) or [""])[0],
            "description": _clean(m.get("ImageDescription", {}).get("value"))[:200],
            "width": ii.get("width"), "height": ii.get("height")}


def file_info(title, width=320):
    r = _api(action="query", titles="File:" + title.removeprefix("File:"), iiurlwidth=width, **II)
    return _info(next(iter(r["query"]["pages"].values())), width_ok=400)


def wikidata(subject):
    """(Q-id, label, description, [P18 image file names], Commons category or None) for the best match, else None."""
    r = _api(WIKIDATA, action="wbsearchentities", search=subject, language="en", type="item", limit=1)
    if not r.get("search"): return None
    hit = r["search"][0]; q = hit["id"]
    ent = _api(WIKIDATA, action="wbgetentities", ids=q, props="claims")["entities"][q]["claims"]
    imgs = [c["mainsnak"]["datavalue"]["value"] for c in ent.get("P18", []) if "datavalue" in c["mainsnak"]]
    cat = next((c["mainsnak"]["datavalue"]["value"] for c in ent.get("P373", []) if "datavalue" in c["mainsnak"]), None)
    return q, hit.get("label", subject), hit.get("description", ""), imgs, cat


def category_files(cat, names=(), n=40, width=320):
    """Files in the subject's Commons category, those naming the subject first, then the most recent."""
    r = _api(action="query", generator="categorymembers", gcmtitle="Category:" + cat, gcmtype="file", gcmlimit=n,
             gcmsort="timestamp", gcmdir="desc", iiurlwidth=width, **II)
    xs = [x for x in (_info(p) for p in r.get("query", {}).get("pages", {}).values()) if x and not NOT_PHOTO.search(x["title"])]
    return sorted(xs, key=lambda x: (not names_in(x, names), x["date"] == "", "".join(chr(255 - ord(c)) for c in x["date"])))


def text_search(subject, n=12, width=320):
    r = _api(action="query", generator="search", gsrsearch="filetype:bitmap " + subject, gsrnamespace=6, gsrlimit=n,
             iiurlwidth=width, **II)
    pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 0))
    return [x for x in (_info(p) for p in pages) if x and not NOT_PHOTO.search(x["title"])]


def _fold(s):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(ch))


def names_in(c, names):
    """True if the file name or caption mentions any significant word of the subject (accents and case ignored)."""
    text = _fold(c.get("title", "") + " " + c.get("description", ""))
    words = {w for n in names for w in re.findall(r"[a-z0-9]{4,}", _fold(n))} - {"municipality", "governorate", "campus", "city", "strait"}
    return any(w in text for w in words) if words else True


def find(subject):
    """Candidates per QUOTA, strongest evidence first, each with a 'match' explaining why it is here."""
    out, seen, query = [], set(), {"subject": subject, "wikidata": None}
    used = {k: 0 for k in QUOTA}
    def add(c, match, kind):
        if c and c["title"] not in seen and used[kind] < QUOTA[kind] and len(out) < PER_SUBJECT:
            seen.add(c["title"]); used[kind] += 1; out.append({**c, "subject": subject, "match": match})
    try:
        wd = wikidata(subject)
    except Exception as e:
        print(f"photos: wikidata lookup failed for {subject!r}: {e!r}"); wd = None
    if wd:
        q, label, desc, imgs, cat = wd
        query["wikidata"] = {"id": q, "label": label, "description": desc, "category": cat}
        for f in imgs[:1]:
            add(file_info(f), f"Wikidata main image of {label} ({q})", "wikidata")
        if cat:
            for c in category_files(cat, (subject, label)): add(c, f"In Commons category “{cat}” (from Wikidata {q})", "category")
    for c in text_search(subject): add(c, f"Text search for “{subject}”: file name matches, not verified", "text")
    return out, query


def _thumb_jpeg(url, dest):
    data = _get(url)
    try:                                    # SVG/PNG thumbnails become JPEG so they display everywhere
        from PIL import Image
        Image.open(io.BytesIO(data)).convert("RGB").save(dest, "JPEG", quality=88)
    except Exception:
        dest.write_bytes(data)


def candidates(ed):
    ed = Path(ed); req = json.loads((ed / "subjects.json").read_text())
    (ed / "photos").mkdir(exist_ok=True)
    cands, queries = {}, {}
    for n, sid in enumerate(req["order"], 1):
        letters = iter(string.ascii_uppercase); queries[str(n)] = []
        for subject in req["subjects"].get(sid, [])[:MAX_SUBJECTS]:
            try:
                found, q = find(subject)
            except Exception as e:
                print(f"photos: search failed for {subject!r}: {e!r}"); found, q = [], {"subject": subject, "wikidata": None}
            q["ids"] = []
            for c in found:
                pid = f"{n}{next(letters)}"; _thumb_jpeg(c["thumb"], ed / "photos" / f"{pid}.jpg")
                cands[pid] = {**c, "story": sid, "n": n}; q["ids"].append(pid)
            queries[str(n)].append(q); time.sleep(0.5)
    (ed / "photos.json").write_text(json.dumps(cands, indent=1, ensure_ascii=False))
    (ed / "photo_queries.json").write_text(json.dumps({"order": req["order"], "queries": queries}, indent=1, ensure_ascii=False))
    sheet(ed); print(f"photos: {len(cands)} candidates for {len(req['order'])} stories")


def chosen(ed):
    """{story_id: photo} from editorial.json, where photo is a candidate id ('3B') or 'File:...'."""
    p = Path(ed) / "editorial.json"
    e = json.loads(p.read_text()) if p.exists() else {}
    return {sid: s["photo"] for sid, s in e.get("stories", {}).items() if s.get("photo")}


def sheet(ed):
    """photos.md: per story, each search made and its results with how they matched; chosen ones starred."""
    ed = Path(ed); cands = json.loads((ed / "photos.json").read_text())
    qf = ed / "photo_queries.json"; qs = json.loads(qf.read_text()) if qf.exists() else {"order": [], "queries": {}}
    picks = chosen(ed); pick = set(picks.values())
    heads = {}
    if (ed / "script.json").exists():
        heads = {s["id"]: s["headline"] for s in json.loads((ed / "script.json").read_text())["stories"]}
    order = qs["order"] or sorted({c["story"] for c in cands.values()}, key=lambda s: min(c["n"] for c in cands.values() if c["story"] == s))
    md = [f"# Photo candidates for {ed.name}", "",
          "★ = used in the video. Reply with e.g. `3: use 3B`, `5: no photo`, or `1: use File:Name_on_Commons.jpg`.",
          "Each image shows **✓/⚠**: whether its own file name or caption names what was searched for. ⚠ means look closely: "
          "the caption may describe something else (e.g. a different ship).",
          "**Matched by** says how it was found: a *Wikidata main image* or *Commons category* is good evidence but not proof; "
          "a *text search* match only means words in the file name matched.", ""]
    def check(c):
        """Quick guide: does the file's own name or caption name what we searched for?"""
        if c.get("match") == "Chosen by hand": return "Chosen by hand"
        if names_in(c, [c["subject"]]): return f"✓ File name or caption names “{c['subject']}”"
        if c.get("description") and not re.search(r"[A-Za-z]{3}", c["description"]):
            return f"? Caption is not in English: check the image shows “{c['subject']}”"
        return f"⚠ File name and caption don't mention “{c['subject']}”. Caption says: “{c.get('description', '')[:110] or 'nothing'}”"
    row = lambda pid, c: (f"| **{pid}**{' ★' if pid in pick else ''} | <img src=\"photos/{safe(pid)}.jpg\" width=\"240\"> | "
                          f"**{check(c)}**<br>[{c['title'][:70]}]({c['page']})<br>{c.get('description', '')[:120]}<br>"
                          f"{c['date'] or 'date unknown'} · {c['license']} · {c['artist']}<br>*Matched by: {c.get('match', '')}* |")
    for n, sid in enumerate(order, 1):
        md += [f"## {n}. {heads.get(sid, sid)}", ""]
        for q in qs["queries"].get(str(n), []):
            wd = q.get("wikidata")
            md.append(f"**Search: “{q['subject']}”** — " + (f"Wikidata: [{wd['label']}](https://www.wikidata.org/wiki/{wd['id']}) ({wd['description'] or 'no description'})"
                                                             if wd else "no Wikidata match, text search only"))
            md.append("")
            if q.get("ids"):
                md += ["| ID | Image | Details |", "|---|---|---|"] + [row(pid, cands[pid]) for pid in q["ids"]]
            else:
                md.append("_No reusable images found._")
            md.append("")
        manual = picks.get(sid, "")
        if manual.startswith("File:") and manual in cands:
            md += ["**Chosen by hand**", "", "| ID | Image | Details |", "|---|---|---|", row(manual, cands[manual]), ""]
        if not qs["queries"].get(str(n)) and not manual.startswith("File:"):
            md += ["_No photo subjects for this story._", ""]
    (ed / "photos.md").write_text("\n".join(md))


def fetch(ed, width=1280):
    """Download each chosen image at render size (and register hand-picked 'File:' choices).
    A missing or failed download just means no photo for that story."""
    ed = Path(ed); pj = ed / "photos.json"
    cands = json.loads(pj.read_text()) if pj.exists() else {}
    (ed / "photos").mkdir(exist_ok=True)
    for sid, pid in chosen(ed).items():
        try:
            if pid.startswith("File:") and pid not in cands:
                c = file_info(pid)
                if not c: print(f"photos: {pid} not usable (licence or size)"); continue
                n = next((x["n"] for x in cands.values() if x["story"] == sid), 0)
                cands[pid] = {**c, "subject": "chosen by hand", "match": "Chosen by hand", "story": sid, "n": n}
                _thumb_jpeg(c["thumb"], ed / "photos" / f"{safe(pid)}.jpg")
            c = cands.get(pid)
            if not c: print(f"photos: {pid} not among the candidates"); continue
            big = file_info(c["title"], width=width)
            _thumb_jpeg(big["thumb"], ed / "photos" / f"use_{safe(pid)}.jpg"); print(f"photos: {pid} downloaded")
        except Exception as e:
            print(f"photos: could not fetch {pid}: {e!r}")
    pj.write_text(json.dumps(cands, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["candidates", "fetch", "sheet"]); ap.add_argument("edition")
    a = ap.parse_args()
    {"candidates": candidates, "fetch": fetch, "sheet": sheet}[a.cmd](a.edition)
