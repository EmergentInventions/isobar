"""Ready-to-post social copy for each platform, written from the edition's script.json and editorial.json.

Writes ED/social/isobar-<DATE>-social-<platform>.txt, one file per platform, each holding every post for the day:
the main bulletin plus clips 1-4 (clip 4, Below the Radar, is for later in the day). Every post is checked
against the platform's length limit and trimmed at a word boundary if needed. Credits (photos, Kagi licence)
go in the post where they fit, otherwise in a "First reply" block to paste under it.

Run after the render and shorts steps:  python -m isobar.social ED
Only uses text already in the edition (headlines, hooks, clip text, outlet counts), so it adds no new facts.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

SITE = "isobar.news"
URL = "https://isobar.news"
YT_HANDLE = "@IsobarNews"
YT_URL = "https://youtube.com/@IsobarNews"
MORE = f"Ten stories, once a day: the full bulletin is on YouTube ({YT_HANDLE}) and at {SITE}"
MORE_REPLY = f"Ten stories, once a day: the full bulletin is on YouTube {YT_URL}"
KAGI = "Attribution: story clustering and summaries adapted from Kagi News, licensed under CC BY-NC 4.0."

# Platform limits (characters). X counts any link as 23. Instagram allows at most 5 hashtags; we use 3.
LIMITS = {"x": 280, "bluesky": 300, "threads": 500, "instagram": 2200, "tiktok": 4000, "facebook": 5000,
          "linkedin": 3000, "youtube_title": 100, "youtube": 5000}
TAGS = {"x": 2, "bluesky": 2, "threads": 1, "instagram": 3, "tiktok": 5, "facebook": 0, "linkedin": 3, "youtube": 3}


def safe(pid):
    return re.sub(r"[^A-Za-z0-9_-]", "_", pid)


def tag(s):
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s or "")
    return "#" + "".join(w if w.isupper() else w.capitalize() for w in s.split()) if s.strip() else ""


def country_of(st):
    if st.get("countries"): return st["countries"][0]
    if st.get("country"): return st["country"]
    if st.get("place"): return st["place"].split(",")[-1].strip()
    return ""


def tags_for(sts, n):
    """Neutral hashtags from the stories' category and main country, then #news; #IsobarNews always last."""
    if n <= 0: return []
    t = [tag(x) for st in sts for x in (st.get("label"), country_of(st))] + ["#news"]
    t = [x for x in dict.fromkeys(t) if x and len(x) > 2 and x.lower() != "#isobarnews"]
    return t[:max(0, n - 1)] + ["#IsobarNews"]


def x_len(s):
    """Length as X counts it: every URL is 23 characters."""
    return len(re.sub(r"https?://\S+", "x" * 23, s))


def fit(text, limit, count=len):
    """Trim to count(text) <= limit: a list (several lines) loses whole lines from the end; prose is cut at a word."""
    if count(text) <= limit: return text
    lines = text.split("\n")
    if len(lines) > 1:
        while len(lines) > 1 and count("\n".join(lines)) > limit: lines.pop()
        if count("\n".join(lines)) <= limit: return "\n".join(lines)
        text = lines[0]
    words = text.split()
    while words and count(" ".join(words) + "…") > limit: words.pop()
    return " ".join(words).rstrip(",;:") + "…"


def first_fitting(options, limit, count=len):
    """The first option (a list of blocks) whose joined text fits the limit; else the last option trimmed."""
    for blocks in options:
        out = "\n\n".join(b for b in blocks if b)
        if count(out) <= limit: return out
    return assemble(options[-1], limit, count)


def assemble(blocks, limit, count=len, squeeze=0):
    """Join non-empty blocks with blank lines; if too long, trim block `squeeze` (the body) to fit."""
    blocks = [b for b in blocks if b]
    out = "\n\n".join(blocks)
    if count(out) <= limit: return out
    rest = count("\n\n".join(b for i, b in enumerate(blocks) if i != squeeze)) + 2
    blocks[squeeze] = fit(blocks[squeeze], max(20, limit - rest), count)
    out = "\n\n".join(blocks)
    assert count(out) <= limit, (count(out), limit, out)
    return out


def credits(sts, photos, source, ed=Path('.')):
    lines = []
    for st in sts:
        pid = st.get("photo")
        if not pid: continue
        ph = photos.get(pid)
        if ph:
            artist = ph.get("artist") or ""
            if not artist or re.search(r"(?i)unknown", artist): artist = "Unknown author"
            lines.append(f"Photo: {artist} / Wikimedia Commons, {ph.get('license')}")
        elif pid.startswith("File:") and (ed / "photos" / f"use_{safe(pid)}.jpg").exists(): lines.append(f"Photo: Wikimedia Commons, {pid} (see file page for author and licence)")
    if source == "kagi": lines.append(KAGI)
    return "\n".join(lines)


def first_sentences(text, n_chars):
    """Whole sentences from the start of text, up to about n_chars."""
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        if out and len(out) + len(s) + 1 > n_chars: break
        out = (out + " " + s).strip()
    return out


def replies(cred, limit):
    """Replies to paste under a short post: first the YouTube line and the Kagi attribution,
    then photo credits, each reply within the platform limit."""
    lines = [l for l in (cred or "").split("\n") if l]
    first = [MORE_REPLY] + [l for l in lines if l == KAGI]
    rest = [l for l in lines if l != KAGI]
    chunks, cur = ["\n\n".join(first)], ""
    for line in rest:
        line = fit(line, limit)
        if cur and len(cur) + 1 + len(line) > limit: chunks.append(cur); cur = line
        else: cur = (cur + "\n" + line).strip()
    if cur: chunks.append(cur)
    names = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth"]
    return [f"{names[min(i, 5)]} reply{'' if i == 0 else ' (photo credits)'}:\n{c}" for i, c in enumerate(chunks)]


def build(ed):
    ed = Path(ed); S = json.loads((ed / "script.json").read_text())
    E = json.loads((ed / "editorial.json").read_text())
    photos = json.loads((ed / "photos.json").read_text()) if (ed / "photos.json").exists() else {}
    date = ed.name; d = dt.datetime.strptime(date, "%Y-%m-%d")
    day = f"{d.day} {d:%B %Y}"; short_day = f"{d.day} {d:%b}"
    src = S.get("source")
    sts = S["stories"]; by_id = {s["id"]: s for s in sts}
    top = [s for s in sts if s.get("segment") == "top"] or sts[:7]
    radar = [s for s in sts if s.get("segment") != "top"] if any(s.get("segment") == "top" for s in sts) else sts[7:]
    yt_title = (ed / "title.txt").read_text().strip() if (ed / "title.txt").exists() else ""
    yt_desc = (ed / "description.txt").read_text().strip() if (ed / "description.txt").exists() else ""
    if not yt_title and yt_desc: yt_title = yt_desc.splitlines()[0]
    method = ("Isobar News ranks the day's stories by how many news outlets covered them, "
              "then adds three that got far less coverage but matter.")
    n_out = len(S.get("all_outlets") or [])
    lead = top[0]

    # ---------- main bulletin ----------
    list_top = "\n".join(f"{i}. {s['headline']} ({s.get('sources', '?')} outlets)" for i, s in enumerate(top, 1))
    list_radar = "\n".join(f"• {s['headline']}" for s in radar)
    bul = {}
    def short_main(link, ntags, limit, count):
        head = f"Isobar News, {short_day}: {lead['headline']}."
        tail = [f"Ten stories, ranked by coverage: {link}", " ".join(tags_for(top[:1], ntags))]
        also = lambda k: "Also today:\n" + "\n".join(f"• {s['headline']}" for s in top[1:1 + k]) if k else ""
        return first_fitting([[head, also(k)] + tail for k in (3, 2, 1, 0)], limit, count)
    bul["x"] = short_main(URL, TAGS["x"], LIMITS["x"], x_len)
    bul["bluesky"] = short_main(SITE, TAGS["bluesky"], LIMITS["bluesky"], len)
    bul["threads"] = assemble([f"Today on Isobar News ({short_day}), ranked by how many outlets covered each story:",
                               "\n".join(f"{i}. {s['headline']}" for i, s in enumerate(top[:5], 1)),
                               f"Plus three stories below the radar. Full bulletin: {SITE}",
                               " ".join(tags_for([], TAGS["threads"]))], LIMITS["threads"], squeeze=1)
    long_body = [f"Isobar News, {day}", method, f"Most covered today:\n{list_top}", f"Below the Radar:\n{list_radar}",
                 f"Drawn from reporting by {n_out} outlets." if n_out else "",
                 f"Watch the full bulletin on YouTube ({YT_HANDLE}) or at {URL}"]
    bul["facebook"] = assemble(long_body + [credits(sts, photos, src, ed)], LIMITS["facebook"], squeeze=2)
    bul["linkedin"] = assemble(long_body + [" ".join(tags_for(top[:2], TAGS["linkedin"])), credits(sts, photos, src, ed)],
                               LIMITS["linkedin"], squeeze=2)
    bul["youtube"] = (f"TITLE ({len(yt_title)}/100):\n{yt_title}\n\nDESCRIPTION:\n{yt_desc}") if yt_title else ""

    # ---------- clips ----------
    clips = []
    for sh in E.get("shorts") or []:
        cs = [by_id[p["id"]] for p in sh["parts"] if p["id"] in by_id]
        if not cs: continue
        slot = sh["slot"]; hook = sh["hook"].strip()
        is_radar = len(cs) > 1
        body = ("\n".join(f"{k}. {s['headline']}" for k, s in enumerate(cs, 1)) if is_radar
                else sh["parts"][0]["text"].strip())
        short_body = body if is_radar else first_sentences(body, 280)
        cred = credits(cs, photos, src, ed)
        more = MORE
        p = {}
        p["tiktok"] = assemble([hook, body, more, " ".join(tags_for(cs, TAGS["tiktok"])), cred], LIMITS["tiktok"], squeeze=1)
        p["instagram"] = assemble([hook, body, more, " ".join(tags_for(cs, TAGS["instagram"])), cred],
                                  LIMITS["instagram"], squeeze=1)
        yt_s_title = fit(hook.rstrip(".") + " #Shorts", LIMITS["youtube_title"])
        p["youtube"] = (f"SHORTS TITLE ({len(yt_s_title)}/100):\n{yt_s_title}\n\nSHORTS DESCRIPTION:\n"
                        + assemble([body, more, " ".join(tags_for(cs, TAGS["youtube"])), cred], LIMITS["youtube"], squeeze=0))
        p["facebook"] = assemble([hook, body, more, cred], LIMITS["facebook"], squeeze=1)
        p["linkedin"] = assemble([hook, body, more, " ".join(tags_for(cs, TAGS["linkedin"])), cred],
                                 LIMITS["linkedin"], squeeze=1)
        p["threads"] = assemble([hook, short_body, more, " ".join(tags_for(cs, TAGS["threads"]))],
                                LIMITS["threads"], squeeze=1)
        lst = "\n".join(f"• {s['headline']}" for s in cs) if is_radar else ""
        p["x"] = first_fitting([[hook, lst, f"Full bulletin: {URL}", " ".join(tags_for(cs, TAGS["x"]))],
                                [hook, f"Full bulletin: {URL}", " ".join(tags_for(cs, TAGS["x"]))]], LIMITS["x"], x_len)
        p["bluesky"] = first_fitting([[hook, lst, f"Full bulletin: {SITE}", " ".join(tags_for(cs, TAGS["bluesky"]))],
                                      [hook, f"Full bulletin: {SITE}", " ".join(tags_for(cs, TAGS["bluesky"]))]], LIMITS["bluesky"])
        clips.append((slot, is_radar, f"isobar-{date}-short{slot}.mp4", p, cred))

    # ---------- write one file per platform ----------
    names = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook", "x": "X",
             "threads": "Threads", "bluesky": "Bluesky", "linkedin": "LinkedIn"}
    short_only = {"tiktok", "instagram"}            # vertical-video platforms: clips only
    no_credit_room = {"x", "bluesky", "threads"}
    out = ed / "social"; out.mkdir(exist_ok=True); written = []
    for key, name in names.items():
        parts = [f"Isobar News, {day}: {name} posts. Each post is ready to paste; lengths are within the platform's limits."]
        if key not in short_only and bul.get(key):
            parts.append(f"=== MAIN BULLETIN (isobar-{date}.mp4 or the YouTube link) ===\n{bul[key]}")
            if key in no_credit_room: parts += replies(credits(sts, photos, src, ed), LIMITS[key])
        for slot, is_radar, fn, p, cred in clips:
            if key not in p: continue
            when = "post later in the day" if is_radar else "post with the bulletin"
            parts.append(f"=== CLIP {slot}: {fn} ({when}) ===\n{p[key]}")
            if key in no_credit_room: parts += replies(cred, LIMITS[key])
        f = out / f"isobar-{date}-social-{key}.txt"
        f.write_text("\n\n".join(parts) + "\n"); written.append(f)
    return written


def main():
    for f in build(sys.argv[1]): print(f"social: {f.name}")


if __name__ == "__main__":
    main()
