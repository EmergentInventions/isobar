"""Shared helpers: paths, dates, outlet names."""
import datetime as dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
UA = "IsobarBot/0.1 (+https://isobar.news)"

# Aggregators and platforms are not outlets: they never count towards coverage.
AGGREGATORS = {
    "news.kagi.com", "kagi.com", "youtube.com", "allsides.com", "techmeme.com", "politicalwire.com",
    "news.google.com", "msn.com", "yahoo.com", "flipboard.com", "reddit.com", "x.com", "twitter.com",
    "ground.news", "newsnow.co.uk", "apple.news",
}


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def edition_dir(base: str, date: str) -> Path:
    p = Path(base) / "editions" / date
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(p):
    return json.loads(Path(p).read_text())


def save(p, obj):
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def norm_domain(d: str) -> str:
    d = (d or "").lower().strip()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    for pre in ("www.", "m.", "amp.", "edition.", "mobile."):
        if d.startswith(pre):
            d = d[len(pre):]
    return d


_NAMES = None


def outlet_name(domain: str) -> str:
    global _NAMES
    if _NAMES is None:
        f = ROOT / "data" / "outlet_names.json"
        _NAMES = json.loads(f.read_text()) if f.exists() else {}
    d = norm_domain(domain)
    if d in _NAMES:
        return _NAMES[d]
    base = d.split(".")[0]
    return base.replace("-", " ").title() if len(base) > 3 else base.upper()


def unique_outlets(domains):
    """Distinct outlet names, aggregators removed, first-seen order."""
    seen, out = set(), []
    for d in domains:
        nd = norm_domain(d)
        if not nd or nd in AGGREGATORS:
            continue
        name = outlet_name(nd)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


_NOSPLIT = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "no", "vs", "gen", "sen", "rep", "gov", "lt", "col", "prof", "capt", "sgt", "u.s", "u.k"}


def sentences(text: str):
    """Split narration into spoken sentences, without breaking on initials (Robert F. Kennedy) or titles (Sen.)."""
    out, start = [], 0
    for m in re.finditer(r"[.!?][\"”’)]*\s+(?=[A-Z\"“‘(0-9])", text or ""):
        word = re.findall(r"[\w.]+$", text[start:m.start()])
        w = word[0].lower() if word else ""
        if len(w) == 1 or w in _NOSPLIT:
            continue
        out.append(text[start:m.end()].strip()); start = m.end()
    tail = (text or "")[start:].strip()
    return out + ([tail] if tail else [])


def yt_title(headline: str, date: str) -> str:
    """'Lead headline | Isobar News, 22 Nov 2026', at most 100 characters (YouTube's limit)."""
    d = dt.datetime.strptime(date, "%Y-%m-%d")
    tail = f" | Isobar News, {d.day} {d:%b %Y}"
    h = headline if len(headline) + len(tail) <= 100 else headline[:100 - len(tail) - 1].rsplit(" ", 1)[0] + "…"
    return h + tail
