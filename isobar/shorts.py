"""Vertical clips (1080x1920) for TikTok, Instagram Reels and YouTube Shorts.

Reads editorial.json "shorts": [{"slot": 1, "hook": "...", "parts": [{"id": story_id, "text": "..."}]}, ...]
(slots 1-3: one top story each; slot 4: the Below the Radar roundup, one part per story). For each clip it
voices hook + parts with the draft voice, then renders: wordmark and date, the story's map/photo/card panel,
headline, burned-in captions (these apps autoplay muted), and an end card. Writes ED/shorts/isobar-DATE-shortN.mp4
and a ready-to-paste post text (shortN.txt). Run after the main draft render: python -m isobar.shorts ED
"""
import json, math, re, subprocess, sys
from pathlib import Path

import numpy as np

W, H, FPS = 1080, 1920, 30
PX, PY, PW, PH = 60, 330, 960, 700          # panel
LEAD, END = 0.3, 2.6                         # silence before the voice; end card length
ZM = 2.5
CAP_Y = 1430                                 # caption centre; everything important stays above ~1560 (app UI below)


def voice(ed, shorts):
    """Voice each clip sentence by sentence; returns {slot: (wav path, [[start, end, sentence, part_index], ...])}."""
    import soundfile as sf
    from .tts_draft import kokoro, lexicon, to_phonemes, VOICE, GAP, FILTER
    from .common import sentences
    k = kokoro(); lex = lexicon(ed); out = {}
    for sh in shorts:
        segs = [(-1, sh["hook"])] + [(j, p["text"]) for j, p in enumerate(sh["parts"])]
        audio, marks, pos, sr = [], [], 0.0, 24000
        for j, text in segs:
            for s in sentences(text):
                a, sr = k.create(to_phonemes(k, s, lex), voice=VOICE, speed=1.0, lang="en-gb", is_phonemes=True)
                if audio: audio.append(np.zeros(int(GAP * sr), dtype=a.dtype)); pos += GAP
                marks.append([round(pos, 3), round(pos + len(a) / sr, 3), s, j]); pos += len(a) / sr; audio.append(a)
        raw = ed / "shorts" / f"short{sh['slot']}_raw.wav"; wav = ed / "shorts" / f"short{sh['slot']}.wav"
        sf.write(raw, np.concatenate(audio), sr)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", FILTER, "-ac", "2", str(wav)], check=True)
        out[sh["slot"]] = (wav, marks)
    return out


def chunks(text, n=30):
    """Caption chunks of at most two lines of ~n characters, broken at commas and clause words where possible."""
    limit = n * 2 - 4
    clauses = re.split(r"(?<=[,;:])\s+|\s+(?=(?:and|but|while|which|who|after|because)\s)", text)
    out, cur = [], ""
    for cl in clauses:
        if cur and len(cur) + 1 + len(cl) <= limit: cur += " " + cl; continue
        if cur: out.append(cur)
        cur = ""
        for w in cl.split():                       # a long clause: pack by words
            if cur and len(cur) + 1 + len(w) > limit: out.append(cur); cur = w
            else: cur = (cur + " " + w).strip()
    out += [cur] if cur else []
    # avoid a tiny last chunk ("list.") by moving a word back
    if len(out) > 1 and len(out[-1]) < 12 and len(out[-2]) + 1 + len(out[-1]) <= limit + 10:
        last = out.pop(); out[-1] += " " + last
    return out


def render(ed, sh, wav, marks, R, story_by_id):
    from PIL import Image, ImageDraw
    INK, PAPER, ACC, SOFT = R.INK, R.PAPER, R.ACC, R.SOFT
    serif, sans = R.serif, R.sans
    paper = np.ascontiguousarray(R.PAPER_ARR.transpose(1, 0, 2))       # portrait paper with the same contours
    adur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)]))
    total = LEAD + adur + END
    radar = len(sh["parts"]) > 1
    # part time ranges (the hook belongs to the first part)
    ranges = []
    for j in range(len(sh["parts"])):
        ms = [m for m in marks if m[3] == j or (j == 0 and m[3] == -1)]
        ranges.append((LEAD + (0 if j == 0 else ms[0][0]), LEAD + ms[-1][1] + (GAP_NEXT if j < len(sh["parts"]) - 1 else 0.6)))

    PMASK = Image.new("L", (PW, PH), 0); ImageDraw.Draw(PMASK).rounded_rectangle([0, 0, PW - 1, PH - 1], 10, fill=255)
    parts = []
    for j, p in enumerate(sh["parts"]):
        st = story_by_id[p["id"]]; n_story = next(i for i, s in enumerate(R.ST) if s["id"] == p["id"]) + 1
        base = Image.fromarray(paper.copy()); d = ImageDraw.Draw(base)
        m = R.mark(56); base.paste(m, (PX, 150), m); R.wordmark(base, (PX + 72, 200), 52)
        d.text((W - 120, 196), R.S["date"].split(" ", 1)[1] if " " in R.S["date"] else R.S["date"], font=sans("Medium", 28), fill=SOFT, anchor="rs")
        d.line([PX, 236, W - 120, 236], fill=INK, width=3)
        label = (f"BELOW THE RADAR  ·  {j + 1}/{len(sh['parts'])}" if radar else f"TOP STORY {n_story:02d}") + "   " + st.get("label", "").upper()
        d.text((PX, 300), label, font=sans("Bold", 30), fill=ACC, anchor="ls")
        y = PY + PH + 50
        for ln in R.wrap(d, st["headline"], serif(600, 62), W - 2 * PX - 60)[:3]:
            d.text((PX, y), ln, font=serif(600, 62), fill=INK); y += 70
        # panel layers: map (or shaded countries), photo, card
        big, pin, layers = None, None, []
        names = st.get("countries") or ([st["country"]] if st.get("country") else [])
        if st.get("lat") is not None:
            big, pin = R.flat_map(st["lat"], st["lon"], int(PW * ZM), int(PH * ZM), span=60); has_pin = True
        elif names:
            big, pin = R.country_map(names, int(PW * ZM), int(PH * ZM)); has_pin = False
        else:
            has_pin = False
        if big is not None: layers.append("map")
        pid = st.get("photo"); ph = R.PHOTOS.get(pid) if pid else None
        pf = ed / "photos" / f"use_{R.photo_safe(pid)}.jpg" if pid else None
        photo = None
        if ph and pf and pf.exists():
            photo = R.cover(Image.open(pf).convert("RGB"), int(PW * 1.1), int(PH * 1.1)); credit = R.photo_credit(ph, PW, PH)
            layers.append("photo")
        card = R.make_card(st["card"], 620, 460).resize((PW, PH), Image.LANCZOS) if st.get("card") else None
        if card is not None: layers.append("card")
        if not layers:
            panel = Image.new("RGB", (PW, PH), (239, 233, 222)); pd = ImageDraw.Draw(panel)
            pd.text((PW // 2, PH // 2), st.get("label", ""), font=serif(500, 96, True), fill=INK, anchor="mm"); card = panel; layers = ["card"]
        t0, t1 = ranges[j]; seg = (t1 - t0) / len(layers)
        starts = {name: t0 + k * seg for k, name in enumerate(layers)}
        parts.append(dict(base=np.array(base), big=big, pin=pin, has_pin=has_pin, photo=photo,
                          credit=credit if photo is not None else None, card=card, starts=starts, t0=t0, t1=t1))

    # caption cues from sentence timings
    cues = []
    for s0, s1, s, _ in marks:
        cs = chunks(s); tot = sum(len(c) for c in cs) or 1; pos = s0
        for c in cs:
            dd = (s1 - s0) * len(c) / tot; cues.append((LEAD + pos, LEAD + pos + dd, c)); pos += dd
    cap_cache = {}
    def caption(text):
        if text in cap_cache: return cap_cache[text]
        f = sans("Bold", 50); im = Image.new("RGBA", (W - 2 * PX, 200), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
        lines = R.wrap(dd, text, f, W - 2 * PX - 160)[:2]; lh = 64; hgt = lh * len(lines) + 34
        wmax = max(dd.textlength(l, font=f) for l in lines) + 60; x0 = (im.width - wmax) / 2; y0 = (200 - hgt) / 2
        dd.rounded_rectangle([x0, y0, x0 + wmax, y0 + hgt], 18, fill=(22, 24, 29, 225))
        for q, l in enumerate(lines): dd.text((im.width / 2, y0 + 17 + lh / 2 + q * lh), l, font=f, fill=(247, 244, 238, 255), anchor="mm")
        cap_cache[text] = im; return im

    end = Image.fromarray(paper.copy()); de = ImageDraw.Draw(end)
    m = R.mark(170); end.paste(m, (W // 2 - 85, 640), m)
    tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(R.S["show"], font=serif(600, 96))
    R.wordmark(end, ((W - tw) / 2, 940), 96)
    de.text((W // 2, 1030), "Ten stories. Once a day.", font=sans("Regular", 40), fill=SOFT, anchor="mm")
    de.text((W // 2, 1100), "Full bulletin on YouTube: Isobar News", font=sans("SemiBold", 38), fill=INK, anchor="mm")
    END_ARR = np.array(end)

    def frame(t):
        if t >= LEAD + adur + 0.2:
            return END_ARR
        P = next((p for p in parts if p["t0"] <= t < p["t1"]), parts[-1] if t >= parts[-1]["t0"] else parts[0])
        arr = P["base"].copy(); lt = max(0.0, t - P["t0"])
        panel, pin_xy = None, None
        if P["big"] is not None:
            e = 1 - (1 - min(1, lt / 4.0)) ** 3; z = 1 + 1.6 * e + 0.2 * max(0, lt - 4) / 20
            if not P["has_pin"]: z = 1 + 0.9 * e
            bw, bh = P["big"].size; cw, ch = bw / z, bh / z; bx, by = P["pin"]
            x0 = min(max(bx - cw / 2, 0), bw - cw); y0 = min(max(by - ch / 2, 0), bh - ch)
            panel = P["big"].resize((PW, PH), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
            if P["has_pin"]: pin_xy = (int((bx - x0) * PW / cw), int((by - y0) * PH / ch))
        for name in ("photo", "card"):
            ts = P["starts"].get(name)
            if ts is None or t < ts: continue
            if name == "photo":
                zz = 1 + 0.08 * min(1, (t - ts) / 8); iw, ih = P["photo"].size; cw, ch = iw / zz, ih / zz
                top = P["photo"].resize((PW, PH), Image.BILINEAR, box=((iw - cw) / 2, (ih - ch) / 2, (iw + cw) / 2, (ih + ch) / 2))
                top.paste(P["credit"], (0, 0), P["credit"])
            else:
                top = P["card"]
            a = min(1.0, (t - ts) / 0.4)
            under = panel if panel is not None else Image.fromarray(arr[PY:PY + PH, PX:PX + PW])
            panel = top if a >= 1 else Image.blend(under, top, a)
            if a > 0.3: pin_xy = None
        if panel is not None:
            if pin_xy:
                dp = ImageDraw.Draw(panel); r = 8 + 26 * ((t % 1.6) / 1.6); x, y = pin_xy
                dp.ellipse([x - r, y - r, x + r, y + r], outline=ACC, width=3); dp.ellipse([x - 13, y - 13, x + 13, y + 13], fill=PAPER)
                dp.ellipse([x - 10, y - 10, x + 10, y + 10], fill=ACC)
            reg = Image.fromarray(arr[PY:PY + PH, PX:PX + PW]); reg.paste(panel, (0, 0), PMASK); arr[PY:PY + PH, PX:PX + PW] = np.array(reg)
        cue = next((c for c in cues if c[0] <= t < c[1]), None)
        if cue:
            cim = caption(cue[2]); reg = Image.fromarray(arr[CAP_Y - 100:CAP_Y + 100, PX:W - PX]); reg.paste(cim, (0, 0), cim)
            arr[CAP_Y - 100:CAP_Y + 100, PX:W - PX] = np.array(reg)
        return arr

    out = ed / "shorts" / f"isobar-{ed.name}-short{sh['slot']}.mp4"; tmp = ed / "shorts" / f"v{sh['slot']}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        p.stdin.write(frame(f / FPS).tobytes())
    p.stdin.close(); assert p.wait() == 0
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-i", str(wav), "-filter_complex",
                    f"[1:a]adelay={int(LEAD * 1000)}|{int(LEAD * 1000)},apad[a]", "-map", "0:v", "-map", "[a]", "-shortest",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], check=True)
    tmp.unlink(); return out, total


def tag(s):
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s or ""); return "#" + "".join(w.capitalize() if not w.isupper() else w for w in s.split()) if s.strip() else ""


def post_text(sh, R, story_by_id):
    sts = [story_by_id[p["id"]] for p in sh["parts"]]
    tags = ["#news", "#worldnews"] + [tag(x) for st in sts for x in ([st.get("label")] + (st.get("countries") or [st.get("country") or ""]))]
    tags = list(dict.fromkeys(t for t in tags if t and len(t) > 2))[:8] + ["#IsobarNews"]
    lines = [sh["hook"], ""]
    if len(sts) > 1:
        lines += [f"{k}. {st['headline']}" for k, st in enumerate(sts, 1)] + [""]
    lines += ["Ten stories, once a day: the full bulletin is on YouTube (@IsobarNews) and at isobar.news", "", " ".join(tags), ""]
    for st in sts:
        ph = R.PHOTOS.get(st.get("photo")) if st.get("photo") else None
        if ph: lines.append(f"Photo: {ph['artist']} / Wikimedia Commons, {ph['license']}")
    if R.S.get("source") == "kagi":
        lines.append("Attribution: story clustering and summaries adapted from Kagi News, licensed under CC BY-NC 4.0.")
    return "\n".join(lines) + "\n"


GAP_NEXT = 0.32


def main():
    ed = Path(sys.argv[1]); e = json.loads((ed / "editorial.json").read_text())
    shorts = e.get("shorts") or []
    if not shorts: print("shorts: none in editorial.json"); return
    (ed / "shorts").mkdir(exist_ok=True)
    sys.argv = ["render.py", str(ed), "--audio", "audio_draft", "--out", "unused.mp4"]
    from . import render as R                       # reuse maps, cards, photos, fonts and the paper
    story_by_id = {s["id"]: s for s in R.ST}
    shorts = [s for s in shorts if all(p["id"] in story_by_id for p in s["parts"])]
    voiced = voice(ed, shorts)
    for sh in shorts:
        wav, marks = voiced[sh["slot"]]
        out, total = render(ed, sh, wav, marks, R, story_by_id)
        (ed / "shorts" / f"isobar-{ed.name}-short{sh['slot']}.txt").write_text(post_text(sh, R, story_by_id))
        print(f"shorts: {out.name} {total:.0f}s", flush=True)


if __name__ == "__main__":
    main()
