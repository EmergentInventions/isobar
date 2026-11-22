"""Isobar edition renderer: per-scene encode, animated ticker, pin pulse, bullet reveals, logo sting."""
import argparse, json, math, os, re, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from isobar.common import sentences, yt_title
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

W, H, FPS = 1920, 1080, 30
LEAD, TAIL = 0.35, 0.65
ZM = 3  # map zoom: the story map is drawn at 3x and the camera moves from the whole of it to ~1/3.35
_ap = argparse.ArgumentParser()
_ap.add_argument("edition"); _ap.add_argument("--audio", default="audio_draft"); _ap.add_argument("--out", default="draft.mp4")
_ap.add_argument("--stills", nargs="*")
ARGS = _ap.parse_args()
ED = Path(ARGS.edition); AUD = ED / ARGS.audio
ASSETS = Path(__file__).resolve().parent.parent / "assets"
S = json.load(open(ED / "script.json")); ST = S["stories"]; N = len(ST)
DUR = json.load(open(AUD / "durations.json"))
TIM = json.load(open(AUD / "timings.json")) if (AUD / "timings.json").exists() else {}
PHOTOS = json.load(open(ED / "photos.json")) if (ED / "photos.json").exists() else {}
TEXT = {"01_intro": S["intro"]["narration"], "08a_radar": S.get("radar_bumper", ""), "99_outro": S["outro"]["narration"],
        **{f"{i+2:02d}_story": s["narration"] for i, s in enumerate(S["stories"])}}

def marks(name):
    """[[start, end, sentence], ...] within the scene's audio: measured by the voice step, else estimated by length."""
    if name in TIM: return TIM[name]
    ss = sentences(TEXT.get(name, "")); total = DUR.get(name, 0); n = sum(len(s) for s in ss) or 1; out, pos = [], 0.0
    for s in ss: d = total * len(s) / n; out.append([pos, pos + d, s]); pos += d
    return out

STOP = set("that this with from have been were which their after about more than they will would could said says also into over under were what when where while there these those other some such only just".split())
def toks(s): return {w for w in re.findall(r"[a-z]{4,}|\d[\d,.]*", s.lower()) if w not in STOP}
def when_said(name, text):
    """Seconds into the scene (including LEAD) when the sentence that best matches `text` starts, or None."""
    mk = marks(name); ft = toks(text)
    if not mk or not ft: return None
    j = max(range(len(mk)), key=lambda j: (len(ft & toks(mk[j][2])), -j))
    return LEAD + mk[j][0] if ft & toks(mk[j][2]) else None
MAXSRC = max(s["sources"] or 0 for s in ST)
NTOP = sum(1 for s in ST if s["segment"] == "top")
PAPER, INK, SOFT, LINE, ACC = (247, 244, 238), (22, 24, 29), (112, 112, 118), (214, 208, 198), (176, 52, 40)
FD = str(ASSETS / "fonts") + "/"
def serif(w, s, it=False): return ImageFont.truetype(FD + f"eb-garamond-latin-{w}-{'italic' if it else 'normal'}.ttf", s)
def sans(w, s): return ImageFont.truetype(FD + f"Inter-{w}.otf", s)
MARK = Image.open(ASSETS / "logo" / "isobar-u2.png").convert("RGBA")
def mark(sz): return MARK.resize((sz, sz), Image.LANCZOS)

def wrap(d, t, f, mw):
    out, cur = [], ""
    for w in t.split():
        x = (cur + " " + w).strip()
        if d.textlength(x, font=f) <= mw: cur = x
        else: out.append(cur); cur = w
    return out + [cur]

# ---------- paper with isobar background ----------
def _paper():
    yy, xx = np.mgrid[0:H:4, 0:W:4] / 400.0
    f = (np.exp(-((xx - 3.6) ** 2 + (yy - 1.9) ** 2) / 1.6) * 1.2 - np.exp(-((xx - 0.8) ** 2 + (yy - 0.4) ** 2) / 2.2)
         + 0.35 * np.sin(xx * 1.3 + yy * 0.7) + 0.25 * np.cos(yy * 2.1 - xx * 0.4))
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100); ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.contour(f, levels=22, colors="k", linewidths=1.1, origin="upper", extent=[0, W, H, 0])
    ax.set_xlim(0, W); ax.set_ylim(H, 0); fig.canvas.draw()
    c = (255 - np.asarray(fig.canvas.buffer_rgba())[..., 0].astype(np.float32)) / 255.0; plt.close(fig)
    rng = np.random.default_rng(3)
    a = np.ones((H, W, 3)) * PAPER + rng.normal(0, 1.4, (H, W, 1))
    a = a * (1 - 0.075 * c[..., None])
    return np.clip(a, 0, 255).astype(np.uint8)
PAPER_ARR = _paper()
def paper(): return Image.fromarray(PAPER_ARR.copy())

def wordmark(im, xy, size, alpha=1.0):
    """'Isobar' in ink, '.News' in the accent colour: the domain is part of the mark."""
    name, dot = (S["show"].split(".", 1) + [""])[:2]
    f = serif(600, size); x, y = xy
    for part, col in ((name, INK), ("." + dot if dot else "", ACC)):
        if not part: continue
        w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(part, font=f)) + 4
        m = Image.new("L", (w, int(size * 1.4)), 0)
        ImageDraw.Draw(m).text((0, int(size * 1.05)), part, font=f, fill=int(255 * alpha), anchor="ls")
        im.paste(Image.new("RGB", m.size, col), (int(x), int(y - size * 1.05)), m)
        x += w - 4
    return x - xy[0]

def masthead(im, counter=None):
    d = ImageDraw.Draw(im)
    m = mark(44); im.paste(m, (90, 26), m)
    wordmark(im, (148, 66), 50)
    d.text((W - 90, 60), S["date"], font=sans("Medium", 22), fill=SOFT, anchor="rs")
    if counter:
        dw = d.textlength(S["date"], font=sans("Medium", 22))
        d.text((W - 90 - dw - 36, 60), counter, font=sans("SemiBold", 22), fill=ACC, anchor="rs")
    d.line([90, 92, W - 90, 92], fill=INK, width=2)

# ---------- ticker ----------
TY = H - 90
LABEL_W = 230
def ticker_band(im):
    d = ImageDraw.Draw(im)
    d.line([0, TY, W, TY], fill=LINE, width=1)
    d.rectangle([0, TY, LABEL_W, H], fill=INK)
    d.text((LABEL_W // 2, TY + 45), "HEADLINES", font=sans("Bold", 18), fill=PAPER, anchor="mm")
def make_strip():
    sep = "      ·      "
    text = sep.join(s["headline"] for s in ST) + sep
    f = sans("Medium", 26)
    tw = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)) + 1
    mask = Image.new("L", (tw * 2, H - TY - 1), 0); d = ImageDraw.Draw(mask)
    for k in range(2): d.text((k * tw, (H - TY) // 2), text, font=f, fill=255, anchor="lm")
    return np.array(mask).astype(np.float32) / 255.0, tw
STRIP, TW = make_strip()
STRIP_BG = PAPER_ARR[TY + 1:H, LABEL_W:W].astype(np.float32)

# ---------- map ----------
def flat_map(lat, lon, w, h, span=22):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    yc = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)); yh = math.radians(span) * h / w
    la0 = math.degrees(2 * math.atan(math.exp(yc - yh)) - math.pi / 2); la1 = math.degrees(2 * math.atan(math.exp(yc + yh)) - math.pi / 2)
    m = Basemap(projection="merc", llcrnrlat=la0, urcrnrlat=la1, llcrnrlon=lon - span, urcrnrlon=lon + span, resolution="l", ax=ax, fix_aspect=False)
    m.drawmapboundary(fill_color="#dfe4e6", linewidth=0); m.fillcontinents(color="#efe9de", lake_color="#dfe4e6")
    m.drawcoastlines(color="#8d8a84", linewidth=0.6); m.drawcountries(color="#b8b1a5", linewidth=0.6)
    m.drawparallels(range(-80, 90, 10), color="#cfcac0", linewidth=0.3, dashes=[2, 3]); m.drawmeridians(range(-180, 180, 10), color="#cfcac0", linewidth=0.3, dashes=[2, 3])
    x, y = m(lon, lat); fig.canvas.draw()
    img = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()).convert("RGB").resize((w, h))
    p = ax.transData.transform((x, y)); plt.close(fig)
    return img, (int(p[0] * w / fig.canvas.get_width_height()[0]), int(h - p[1] * h / fig.canvas.get_width_height()[1]))

# ---------- country shading (stories with no single place) ----------
import shapefile, geonamescache
from matplotlib.patches import Polygon as _Poly
_NE = shapefile.Reader(str(ASSETS / "countries" / "naturalearth_lowres.shp"), encoding="latin1")
_NE_SHAPES = {rec["name"]: shp for rec, shp in zip(_NE.records(), _NE.shapes())}
_NE_ISO = {rec["iso_a3"]: rec["name"] for rec in _NE.records()}
_ALIAS = {"DR Congo": "Dem. Rep. Congo", "Democratic Republic of the Congo": "Dem. Rep. Congo", "Congo-Kinshasa": "Dem. Rep. Congo",
          "Republic of the Congo": "Congo", "US": "United States of America", "USA": "United States of America",
          "United States": "United States of America", "UK": "United Kingdom", "Britain": "United Kingdom",
          "Czech Republic": "Czechia", "South Sudan": "S. Sudan", "Central African Republic": "Central African Rep.",
          "Bosnia and Herzegovina": "Bosnia and Herz.", "Dominican Republic": "Dominican Rep.", "Ivory Coast": "Côte d'Ivoire",
          "Eswatini": "eSwatini", "North Macedonia": "North Macedonia", "Western Sahara": "W. Sahara", "Gaza": "Palestine",
          "Palestinian territories": "Palestine", "West Bank": "Palestine"}
_GC = geonamescache.GeonamesCache()

def _capital(name):
    for c in _GC.get_countries().values():
        if c["name"].lower() == name.lower() or c["iso3"] == name.upper():
            hits = _GC.search_cities(c["capital"], contains_search=False)
            if hits:
                h = max(hits, key=lambda x: x.get("population", 0)); return float(h["longitude"]), float(h["latitude"])
    return None

def _ne_name(name):
    n = _ALIAS.get(name, name)
    if n in _NE_SHAPES: return n
    for c in _GC.get_countries().values():
        if c["name"].lower() == name.lower() and _NE_ISO.get(c["iso3"]) in _NE_SHAPES: return _NE_ISO[c["iso3"]]
    return None

def _parts(shp):
    idx = list(shp.parts) + [len(shp.points)]
    return [shp.points[a:b] for a, b in zip(idx[:-1], idx[1:])]

def country_map(names, w, h, zoom_out=3.0):
    """Map with the story's countries shaded (first one darker); tiny countries get a dot at the capital.
    Returns (image, (cx, cy)) where (cx, cy) is the pixel centre of the shaded area; the view spans zoom_out x its extent."""
    shapes, dots = [], []
    for k, n in enumerate(names):
        ne = _ne_name(n)
        if ne:
            # ignore far-flung islands: keep parts within 25 degrees of the largest part (e.g. mainland France)
            ps = _parts(_NE_SHAPES[ne]); big = max(ps, key=len)
            bx = sum(p[0] for p in big) / len(big); by = sum(p[1] for p in big) / len(big)
            shapes.append((k, [p for p in ps if abs(sum(q[0] for q in p) / len(p) - bx) < 25 and abs(sum(q[1] for q in p) / len(p) - by) < 25]))
        else:
            c = _capital(n)
            if c: dots.append((k, c))
    pts = [q for _, ps in shapes for p in ps for q in p] + [c for _, c in dots]
    if not pts: return None, None
    lo0, lo1 = min(p[0] for p in pts), max(p[0] for p in pts); la0, la1 = min(p[1] for p in pts), max(p[1] for p in pts)
    cx, cy = (lo0 + lo1) / 2, (la0 + la1) / 2
    m_ = lambda la: math.log(math.tan(math.pi / 4 + math.radians(max(-80, min(80, la))) / 2))
    tall = math.degrees(m_(la1) - m_(la0))                                # latitude extent as projected (Mercator stretches the north)
    span = max(lo1 - lo0, tall * w / h, 8) * 0.65 * zoom_out             # half-width in degrees of longitude
    cy = math.degrees(2 * math.atan(math.exp((m_(la0) + m_(la1)) / 2)) - math.pi / 2)   # centre in projected space
    yc = m_(cy); yh = math.radians(span) * h / w
    A = math.degrees(2 * math.atan(math.exp(yc - yh)) - math.pi / 2); B = math.degrees(2 * math.atan(math.exp(yc + yh)) - math.pi / 2)
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100); ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    m = Basemap(projection="merc", llcrnrlat=max(-80, A), urcrnrlat=min(80, B), llcrnrlon=cx - span, urcrnrlon=cx + span, resolution="l", ax=ax, fix_aspect=False)
    m.drawmapboundary(fill_color="#dfe4e6", linewidth=0); m.fillcontinents(color="#efe9de", lake_color="#dfe4e6")
    for k, ps in shapes:
        for p in ps:
            xy = [m(x, y) for x, y in p]
            ax.add_patch(_Poly(xy, closed=True, facecolor="#b03428", alpha=0.62 if k == 0 else 0.30, edgecolor="#7a241c", linewidth=0.8, zorder=3))
    m.drawcoastlines(color="#8d8a84", linewidth=0.6); m.drawcountries(color="#b8b1a5", linewidth=0.6)
    for k, (x, y) in dots:
        X, Y = m(x, y); ax.plot(X, Y, "o", ms=16 if k == 0 else 12, mfc="#b03428", mec="#f7f4ee", mew=2, zorder=5)
    X, Y = m(cx, cy); fig.canvas.draw()
    img = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()).convert("RGB").resize((w, h))
    p = ax.transData.transform((X, Y)); W0, H0 = fig.canvas.get_width_height(); plt.close(fig)
    return img, (int(p[0] * w / W0), int(h - p[1] * h / H0))

# ---------- scenes: each returns (states, state_fn(t), pin or None, duration) ----------
def sc_sting():
    dur = 3.2
    frames = []
    for k in range(int(dur * FPS)):
        t = k / FPS; im = paper(); d = ImageDraw.Draw(im)
        a = min(1, max(0, (t - 0.15) / 0.7)); e = 1 - (1 - a) ** 3
        sz = int(220 * (0.88 + 0.12 * e))
        TS = 170; tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(S["show"], font=serif(600, TS))
        x0 = int(W // 2 - (220 + 50 + tw) / 2)          # centre mark + wordmark as one group
        if a > 0:
            m = mark(sz); al = m.split()[3].point(lambda v: int(v * a)); m.putalpha(al)
            im.paste(m, (x0 + 110 - sz // 2, H // 2 - sz // 2), m)
        b = min(1, max(0, (t - 0.7) / 0.6))
        if b > 0:
            wordmark(im, (x0 + 270, H // 2 + 50), TS, alpha=b)
        c = min(1, max(0, (t - 1.4) / 0.6))
        if c > 0 and S.get("strapline"):
            txt = Image.new("L", (900, 60), 0); ImageDraw.Draw(txt).text((450, 30), S["strapline"], font=sans("Regular", 30), fill=int(255 * c), anchor="mm")
            im.paste(Image.new("RGB", txt.size, SOFT), (W // 2 - 450, H // 2 + 130), txt)
        frames.append(np.array(im))
    return frames, (lambda t: min(len(frames) - 1, int(t * FPS))), None, dur, False

def sc_intro():
    base = paper(); masthead(base); ticker_band(base); d = ImageDraw.Draw(base)
    d.text((90, 190), "Today's stories", font=serif(600, 72), fill=INK, anchor="ls")
    d.text((90, 236), f"{['Zero','One','Two','Three','Four','Five','Six','Seven','Eight'][NTOP]} most covered, ranked by number of outlets. Then {['zero','one','two','three','four','five'][N - NTOP]} below the radar, picked for impact.", font=sans("Regular", 25), fill=SOFT, anchor="ls")
    d.text((W - 90, 290), "OUTLETS", font=sans("SemiBold", 15), fill=SOFT, anchor="rs")
    rows = []; y = 300
    for i, st in enumerate(ST):
        if i == NTOP:
            y += 36; rows.append(("div", y)); y += 30
        y += 52; rows.append((i, y))
    states = []
    for k in range(len(rows) + 1):
        im = base.copy(); dd = ImageDraw.Draw(im)
        for i, y in rows[:k]:
            if i == "div":
                dd.text((90, y + 8), "BELOW THE RADAR", font=sans("Bold", 17), fill=ACC, anchor="ls")
                dd.line([290, y + 2, W - 90, y + 2], fill=ACC, width=1); continue
            st = ST[i]
            dd.line([90, y - 40, W - 90, y - 40], fill=LINE, width=1)
            dd.text((90, y), f"{i+1:02d}", font=serif(500, 31, True), fill=ACC, anchor="ls")
            dd.text((165, y), st["headline"], font=serif(500, 33), fill=INK, anchor="ls")
            bx, bw = 1420, 300
            dd.rectangle([bx, y - 14, bx + bw, y - 9], fill=LINE)
            dd.rectangle([bx, y - 14, bx + int(bw * st["sources"] / MAXSRC), y - 9], fill=ACC if st["segment"] == "top" else SOFT)
            dd.text((W - 90, y), str(st["sources"]), font=sans("SemiBold", 22), fill=INK, anchor="rs")
        states.append(np.array(im))
    dur = DUR["01_intro"] + LEAD + TAIL
    return states, (lambda t: 0 if t < 0.5 else min(len(rows), int((t - 0.5) / 0.4) + 1)), None, dur, True

def sc_radar():
    base = paper(); masthead(base); ticker_band(base); d = ImageDraw.Draw(base)
    m = mark(120); base.paste(m, (90, 230), m)
    d.text((240, 300), "Below the Radar", font=serif(600, 96), fill=INK, anchor="ls")
    d.text((242, 346), "Less coverage. Picked for impact, with the reason shown.", font=sans("Regular", 28), fill=SOFT, anchor="ls")
    rad = [s for s in ST if s["segment"] == "radar"]
    states = [np.array(base)]
    for k in range(1, 4):
        im = base.copy(); dd = ImageDraw.Draw(im)
        for j, st in enumerate(rad[:k]):
            y = 500 + j * 130
            dd.text((240, y), f"{NTOP+1+j:02d}", font=serif(500, 40, True), fill=ACC, anchor="ls")
            dd.text((320, y), st["headline"], font=serif(600, 44), fill=INK, anchor="ls")
            dd.text((320, y + 42), st["why"], font=sans("Regular", 24), fill=SOFT, anchor="ls")
        states.append(np.array(im))
    dur = DUR["08a_radar"] + LEAD + TAIL
    return states, (lambda t: min(3, int(max(0, t - 1.2) / 1.6) + (1 if t > 1.2 else 0))), None, dur, True

def sc_story(i):
    st = ST[i]; base = paper(); masthead(base, f"{i+1:02d} / {N:02d}"); ticker_band(base); d = ImageDraw.Draw(base)
    LX, MW = 90, 1000
    d.text((LX, 190), f"{i+1:02d}", font=serif(500, 44, True), fill=ACC, anchor="ls")
    cat = st["category"]
    if cat.startswith("BELOW THE RADAR"):
        d.text((LX + 70, 188), "BELOW THE RADAR", font=sans("Bold", 20), fill=ACC, anchor="ls")
        w0 = d.textlength("BELOW THE RADAR", font=sans("Bold", 20))
        d.text((LX + 70 + w0, 188), cat[len("BELOW THE RADAR"):], font=sans("SemiBold", 20), fill=SOFT, anchor="ls")
    else:
        d.text((LX + 70, 188), cat, font=sans("SemiBold", 20), fill=SOFT, anchor="ls")
    y = 220
    for ln in wrap(d, st["headline"], serif(600, 70), MW):
        d.text((LX, y), ln, font=serif(600, 70), fill=INK); y += 78
    y += 64                                   # breathing room between headline and facts
    bl = []
    BF, BLH = sans("Regular", 38), 52           # bullet font and line height
    for f in st["facts"]:
        lines = wrap(d, f, BF, MW - 44); bl.append((y, lines)); y += len(lines) * BLH + 34
    MX, MY, MWd, MH = W - 90 - 620, 150, 620, 460
    name = f"{i+2:02d}_story"; dur = DUR[name] + LEAD + TAIL
    PMASK = Image.new("L", (MWd, MH), 0); ImageDraw.Draw(PMASK).rounded_rectangle([0, 0, MWd - 1, MH - 1], 6, fill=255)
    big, bx, by, has_pin, zmax = None, 0, 0, False, 3.35
    names = st.get("countries") or ([st["country"]] if st.get("country") else [])
    if st["lat"] is None and names:
        big, ctr = country_map(names, MWd * ZM, MH * ZM)
        if big is not None:
            bx, by = ctr; zmax = 2.0     # stop with the whole shaded area in view
            d.text((MX, MY + MH + 38), ", ".join(names), font=serif(400, 30, True), fill=INK, anchor="ls")
    if st["lat"] is not None:
        has_pin = True
        # a 3x, continent-wide map that the camera zooms into (drawn per frame)
        big, (bx, by) = flat_map(st["lat"], st["lon"], MWd * ZM, MH * ZM, span=60)
        d.text((MX, MY + MH + 38), st["place"], font=serif(400, 30, True), fill=INK, anchor="ls")
    elif big is None:
        # no place and no countries (e.g. a global story): a quiet panel built from the mark's contours
        panel = Image.new("RGB", (MWd, MH), (239, 233, 222)); pd = ImageDraw.Draw(panel)
        label = st.get("label") or " ".join(w if w in {"US","UK","EU","UN","AI","NATO","COP31"} else (w.capitalize() if k == 0 else w.lower()) for k, w in enumerate(st["category"].split("·")[-1].strip().split()))
        fs = 110
        while fs > 50 and pd.textlength(label, font=serif(500, fs, True)) > MWd - 70: fs -= 4   # fit the panel
        pd.text((MWd // 2, MH // 2 - 20), label, font=serif(500, fs, True), fill=INK, anchor="mm")
        pd.line([MWd // 2 - 40, MH // 2 + 60, MWd // 2 + 40, MH // 2 + 60], fill=ACC, width=3)
        pd.text((MWd // 2, MH // 2 + 110), f"{st['sources']} OUTLETS", font=sans("SemiBold", 20), fill=SOFT, anchor="mm")
        base.paste(panel, (MX, MY), PMASK)
        if st.get("country") and st["country"] != label:   # one country, no single place: name it (unless the panel already does)
            d.text((MX, MY + MH + 38), st["country"], font=serif(400, 30, True), fill=INK, anchor="ls")
    ty = MY + MH + 90
    d.line([MX, ty - 16, MX + MWd, ty - 16], fill=LINE, width=1)
    d.text((MX, ty + 10), "REPORTED BY", font=sans("SemiBold", 17), fill=SOFT, anchor="lm")
    d.text((MX + MWd, ty + 10), f"{st['sources']} outlets", font=serif(600, 34), fill=INK, anchor="rm")
    d.rectangle([MX, ty + 46, MX + MWd, ty + 52], fill=LINE)
    d.rectangle([MX, ty + 46, MX + int(MWd * st["sources"] / MAXSRC), ty + 52], fill=ACC if st["segment"] == "top" else SOFT)
    oy = ty + 82
    for q, ln in enumerate(wrap(d, "Including " + st["outlet_line"], sans("Regular", 21), MWd)[:2]):
        d.text((MX, oy + q * 28), ln, font=sans("Regular", 21), fill=SOFT, anchor="lm")
    if st.get("why"):
        d.text((MX, ty + 160), "WHY IT'S HERE", font=sans("SemiBold", 17), fill=ACC, anchor="lm")
        for q, ln in enumerate(wrap(d, st["why"], sans("Regular", 22), MWd)):
            d.text((MX, ty + 190 + q * 30), ln, font=sans("Regular", 22), fill=INK, anchor="lm")
    states = []
    for k in range(len(bl) + 1):
        im = base.copy(); dd = ImageDraw.Draw(im)
        for by_, lines in bl[:k]:
            dd.line([LX, by_ + 26, LX + 18, by_ + 26], fill=ACC, width=3)
            for q, ln in enumerate(lines): dd.text((LX + 44, by_ + q * BLH), ln, font=BF, fill=INK)
        states.append(np.array(im))
    # each bullet appears when the narration reaches the sentence it summarises
    reveal, prev = [], -0.5
    for j, f in enumerate(st["facts"]):
        r = when_said(name, f)
        if r is None: r = 0.7 + dur * 0.6 * j / max(1, len(st["facts"]))
        r = min(max(r, prev + 1.2, 0.7), dur - 1.5); reveal.append(r); prev = r
    # panel sequence: map -> photo (when its subject is mentioned) -> card (when its figure or quote is spoken)
    card = st.get("card"); card_img = make_card(card, MWd, MH) if card else None; tc = None
    if card_img is not None and dur > 12:
        w_ = when_said(name, card.get("text") or (card.get("label", "") + " " + card.get("big", "")))
        tc = min(max(w_ or dur * 0.5, 5.0, dur * 0.35), dur - 5)
    pid = st.get("photo"); ph = PHOTOS.get(pid) if pid else None; pf = ED / "photos" / f"use_{pid}.jpg"
    photo_big, tp = None, None
    if ph and pf.exists() and dur > 12:
        tp = max(6.0, when_said(name, ph["subject"]) or dur * 0.3)
        if tc is not None and tp > tc - 6:                 # keep at least 6 s of photo before the card
            tp = max(6.0, tc - 8)
            if tc - tp < 5: tc = tp + 7 if tp + 7 < dur - 4 else None
        if tp < dur - 5:
            photo_big = cover(Image.open(pf).convert("RGB"), int(MWd * 1.12), int(MH * 1.12))
            credit_band = photo_credit(ph, MWd, MH)
        else:
            tp = None
    PIN = [None]
    def view(t):  # continent to region over 5 s (ease-out), then a slow drift closer
        e = min(1, t / 5.0); e = 1 - (1 - e) ** 3
        return 1 + (zmax - 1.35) * e + 0.35 * max(0, t - 5.0) / max(1, dur - 5.0)
    def photo_at(t):  # slow push-in, credit on top
        z = 1 + 0.10 * min(1, (t - tp) / max(1, (tc or dur) - tp))
        cw, ch = MWd * 1.12 / z, MH * 1.12 / z; x0 = (MWd * 1.12 - cw) / 2; y0 = (MH * 1.12 - ch) / 2
        im = photo_big.resize((MWd, MH), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)); im.paste(credit_band, (0, 0), credit_band)
        return im
    def at(t):
        arr = states[sum(1 for r in reveal if t >= r)].copy()
        panel, pin_xy = None, None
        if big is not None:
            z = view(t); cw, ch = MWd * ZM / z, MH * ZM / z
            x0 = min(max(bx - cw / 2, 0), MWd * ZM - cw); y0 = min(max(by - ch / 2, 0), MH * ZM - ch)
            panel = big.resize((MWd, MH), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
            pin_xy = (MX + int((bx - x0) * MWd / cw), MY + int((by - y0) * MH / ch)) if has_pin else None
        for t0, layer in ((tp, photo_at if photo_big is not None else None), (tc, (lambda t: card_img) if card_img is not None else None)):
            if t0 is None or layer is None or t <= t0: continue
            a = min(1.0, (t - t0) / 0.5)
            under = panel if panel is not None else Image.fromarray(arr[MY:MY + MH, MX:MX + MWd])
            top = layer(t); panel = top if a >= 1 else Image.blend(under, top, a)
            if a > 0.3: pin_xy = None
        if panel is not None:
            region = Image.fromarray(arr[MY:MY + MH, MX:MX + MWd]); region.paste(panel, (0, 0), PMASK)
            arr[MY:MY + MH, MX:MX + MWd] = np.array(region)
        PIN[0] = pin_xy
        return arr
    return at, None, (lambda t: PIN[0]), dur, True

def cover(im, w, h):
    """Scale and crop to fill w x h; tall photos are cropped from near the top (faces), wide ones from the centre."""
    s = max(w / im.width, h / im.height); im = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    x = (im.width - w) // 2; y = int((im.height - h) * (0.25 if im.height > im.width else 0.5))
    return im.crop((x, y, x + w, y + h))

def photo_credit(ph, w, h):
    """Translucent band along the bottom of the panel with the photographer and licence."""
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(band)
    d.rectangle([0, h - 34, w, h], fill=(22, 24, 29, 150))
    txt = f"Photo: {ph['artist']} / Wikimedia Commons, {ph['license']}"
    f = sans("Regular", 15)
    while d.textlength(txt, font=f) > w - 24 and len(txt) > 20: txt = txt[:-2]
    d.text((12, h - 17), txt, font=f, fill=(247, 244, 238, 235), anchor="lm")
    return band

def make_card(c, w, h):
    """Key figure ("big" + "label") or quote ("text" + "by") on the panel paper."""
    im = Image.new("RGB", (w, h), (239, 233, 222)); d = ImageDraw.Draw(im)
    if c.get("kind") == "quote":
        d.text((44, 120), "\u201c", font=serif(600, 160), fill=ACC, anchor="ls")
        f = serif(500, 40, True); lines = wrap(d, c["text"], f, w - 100)
        while len(lines) > 5 and f.size > 28: f = serif(500, f.size - 2, True); lines = wrap(d, c["text"], f, w - 100)
        y = 150
        for ln in lines: d.text((50, y), ln, font=f, fill=INK, anchor="ls"); y += int(f.size * 1.25)
        d.text((50, y + 30), "\u2014 " + c.get("by", ""), font=sans("SemiBold", 22), fill=SOFT, anchor="ls")
    else:
        fs = 150
        while fs > 60 and d.textlength(c["big"], font=serif(600, fs)) > w - 80: fs -= 6
        d.text((w // 2, h // 2 - 40), c["big"], font=serif(600, fs), fill=ACC, anchor="mm")
        f = sans("Regular", 27); y = h // 2 + fs // 2 - 6
        for ln in wrap(d, c.get("label", ""), f, w - 90)[:3]:
            d.text((w // 2, y), ln, font=f, fill=INK, anchor="mm"); y += 36
        if c.get("source"):
            d.text((w // 2, h - 34), c["source"], font=sans("Regular", 19), fill=SOFT, anchor="mm")
    return im

def sc_outro():
    base = paper(); masthead(base); ticker_band(base); d = ImageDraw.Draw(base)
    m = mark(130); base.paste(m, (90, 200), m)
    d.text((90, 440), "Back tomorrow", font=serif(600, 92), fill=INK, anchor="ls")
    n = len(S["all_outlets"])
    d.text((92, 510), f"This edition drew on reporting from", font=sans("Regular", 30), fill=SOFT, anchor="ls")
    d.text((90, 590), f"{n} outlets", font=serif(600, 76), fill=ACC, anchor="ls")
    d.text((92, 640), "around the world.", font=sans("Regular", 30), fill=SOFT, anchor="ls")
    d.text((92, 760), "isobar.news", font=serif(600, 36), fill=INK, anchor="ls")
    # credit roll: three columns in a window on the right
    X0, Y0, WW, WH = 960, 130, 870, 820
    names = S["all_outlets"]; cols = 3; rows = math.ceil(len(names) / cols); lh = 40
    roll = Image.new("L", (WW, rows * lh + 40), 0); rd = ImageDraw.Draw(roll)
    for k, nm in enumerate(names):
        c, r = k // rows, k % rows
        rd.text((c * (WW // cols), r * lh + 20), nm, font=serif(500, 27), fill=255, anchor="lm")
    # credit line appended after the names
    tail = Image.new("L", (WW, 200), 0); td = ImageDraw.Draw(tail)
    td.line([WW // 2 - 40, 50, WW // 2 + 40, 50], fill=180, width=2)
    cr = S["credit"]; l1, l2 = (cr.split(" from ", 1) if " from " in cr else (cr, ""))
    td.text((WW // 2, 100), l1 + (" from" if l2 else ""), font=sans("Regular", 24), fill=200, anchor="mm")
    td.text((WW // 2, 140), l2, font=sans("SemiBold", 24), fill=230, anchor="mm")
    full = Image.new("L", (WW, roll.height + 200), 0); full.paste(roll, (0, 0)); full.paste(tail, (0, roll.height))
    roll = full
    R = np.array(roll).astype(np.float32) / 255.0
    fade = np.ones(WH); fade[:90] = np.linspace(0, 1, 90); fade[-90:] = np.linspace(1, 0, 90)
    BASE = np.array(base); BG = BASE[Y0:Y0 + WH, X0:X0 + WW].astype(np.float32)
    dur = DUR["99_outro"] + LEAD + TAIL
    # scroll until the credit line sits mid-window, then hold for the last 2.5 s
    end_off = R.shape[0] - 200 + 100 - WH // 2
    hold = 2.5
    def at(t):
        arr = BASE.copy()
        p = min(1, t / max(0.1, dur - hold))
        off = int(-WH + (end_off + WH) * p)
        win = np.zeros((WH, WW), np.float32)
        s0, s1 = max(0, off), min(R.shape[0], off + WH)
        if s1 > s0: win[s0 - off:s1 - off] = R[s0:s1]
        a = (win * fade[:, None])[..., None]
        arr[Y0:Y0 + WH, X0:X0 + WW] = (BG * (1 - a) + np.array(INK) * a).astype(np.uint8)
        return arr
    return at, None, None, dur, True


# ---------- captions, thumbnail, title ----------
def _ts(x):
    ms = int(round(max(0, x) * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

def _chunks(text, n=84):
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    return out + ([cur] if cur else [])

def _two_lines(s):
    if len(s) <= 42: return s
    sp = [k for k, c in enumerate(s) if c == " "]
    k = min(sp, key=lambda k: abs(k - len(s) / 2)) if sp else None
    return s if k is None else s[:k] + "\n" + s[k + 1:]

def write_captions(L, path):
    """SRT from the sentence timings: one cue per sentence, long sentences split into two-line chunks."""
    cues, g = [], 0.0
    for name, d in L.items():
        if name in TEXT:
            for s0, s1, s in marks(name):
                parts = _chunks(s); tot = sum(len(p) for p in parts) or 1; pos = s0
                for p in parts:
                    dd = (s1 - s0) * len(p) / tot; cues.append((g + LEAD + pos, g + LEAD + pos + dd, p)); pos += dd
        g += d
    path.write_text("".join(f"{k}\n{_ts(a)} --> {_ts(b)}\n{_two_lines(x)}\n\n" for k, (a, b, x) in enumerate(cues, 1)))
    return len(cues)

def make_thumbnail(path):
    """1280x720: wordmark and date, the lead headline large, its map on the right."""
    TW_, TH_ = 1280, 720; lead = ST[0]
    im = Image.fromarray(PAPER_ARR).resize((TW_, TH_), Image.LANCZOS); d = ImageDraw.Draw(im)
    m = mark(62); im.paste(m, (56, 40), m); wordmark(im, (132, 92), 56)
    import datetime as _dt
    day = _dt.datetime.strptime(ED.name, "%Y-%m-%d")
    d.text((TW_ - 56, 88), f"{day.day} {day:%b %Y}", font=sans("SemiBold", 30), fill=SOFT, anchor="rs")
    d.line([56, 124, TW_ - 56, 124], fill=INK, width=3)
    tw = TW_ - 112
    if lead["lat"] is not None:
        MS = 430; mimg, (px, py) = flat_map(lead["lat"], lead["lon"], MS, MS, span=12)
        msk = Image.new("L", (MS, MS), 0); ImageDraw.Draw(msk).rounded_rectangle([0, 0, MS - 1, MS - 1], 10, fill=255)
        mx, my = TW_ - 56 - MS, 170; im.paste(mimg, (mx, my), msk)
        d.ellipse([mx + px - 16, my + py - 16, mx + px + 16, my + py + 16], fill=PAPER)
        d.ellipse([mx + px - 12, my + py - 12, mx + px + 12, my + py + 12], fill=ACC)
        tw = mx - 56 - 40
    fs = 96
    while fs > 48 and len(wrap(d, lead["headline"], serif(600, fs), tw)) > 4: fs -= 4
    y = 170
    for ln in wrap(d, lead["headline"], serif(600, fs), tw):
        d.text((56, y), ln, font=serif(600, fs), fill=INK); y += int(fs * 1.08)
    d.rectangle([56, 618, 120, 624], fill=ACC)
    d.text((56, 668), f"TOP STORY  ·  {lead['sources']} OUTLETS", font=sans("Bold", 28), fill=ACC, anchor="ls")
    im.save(path)

# ---------- compositing ----------
def frame(states, sf, pin, t, gt, dur, has_ticker):
    arr = states(t) if callable(states) else states[sf(t)].copy()
    if callable(pin): pin = pin(t)
    if has_ticker:
        off = int(gt * 110) % TW
        a = STRIP[:, off:off + (W - LABEL_W)][..., None]
        arr[TY + 1:H, LABEL_W:W] = (STRIP_BG * (1 - a) + np.array(INK) * a).astype(np.uint8)
    if pin:
        x, y = pin; ph = (t % 1.6) / 1.6; r = 10 + 34 * ph; al = 1 - ph
        yy, xx = np.ogrid[y - 48:y + 49, x - 48:x + 49]; dist = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
        reg = arr[y - 48:y + 49, x - 48:x + 49].astype(np.float32)
        ring = np.clip(1.5 - np.abs(dist - r), 0, 1) * al * 0.85
        reg = reg * (1 - ring[..., None]) + np.array(ACC) * ring[..., None]
        core = np.clip(9.5 - dist, 0, 1); edge = np.clip(12.5 - dist, 0, 1) - core
        reg = reg * (1 - edge[..., None]) + np.array(PAPER) * edge[..., None]
        reg = reg * (1 - core[..., None]) + np.array(ACC) * core[..., None]
        arr[y - 48:y + 49, x - 48:x + 49] = reg.astype(np.uint8)
    fade = min(1.0, t / 0.25, (dur - t) / 0.2)
    if fade < 1:  # fade through paper, not black
        arr = (arr.astype(np.float32) * max(0, fade) + PAPER_ARR.astype(np.float32) * (1 - max(0, fade))).astype(np.uint8)
    return arr

def scenes():
    out = [("00_sting", sc_sting), ("01_intro", sc_intro)]
    for i in range(N):
        if i == NTOP: out.append(("08a_radar", sc_radar))
        out.append((f"{i+2:02d}_story", (lambda i=i: sc_story(i))))
    return out + [("99_outro", sc_outro)]

def encode(name, b, g):
    states, sf, pin, dur, tk = b(); nf = int(round(dur * FPS)); tmp = str(SCENES_DIR / f"{name}.part.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(nf):
        t = f / FPS; p.stdin.write(frame(states, sf, pin, t, g + t, dur, tk).tobytes())
    p.stdin.close(); assert p.wait() == 0; os.rename(tmp, str(SCENES_DIR / f"{name}.mp4")); return nf / FPS

if __name__ == "__main__":
    SC = ED / ("scenes_" + ARGS.audio); SC.mkdir(exist_ok=True)
    globals()["SCENES_DIR"] = SC
    sc = scenes()
    if ARGS.stills is not None:
        (ED / "stills").mkdir(exist_ok=True)
        for name, b in sc:
            if not ARGS.stills or name in ARGS.stills:
                states, sf, pin, dur, tk = b(); t = min(dur - 1.0, 2.0) if name == "00_sting" else dur - 1.0
                Image.fromarray(frame(states, sf, pin, t, 9.0, dur, tk)).save(ED / "stills" / f"{name}.png")
        sys.exit()
    g = 0.0; L = {}
    for name, b in sc:
        f = SC / f"{name}.mp4"
        L[name] = encode(name, b, g) if not f.exists() else float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))
        g += L[name]; print(name, round(L[name], 2), flush=True)
    lst = SC / "list.txt"; lst.write_text("".join(f"file '{n}.mp4'\n" for n in L))
    alst = SC / "alist.txt"; parts = []
    for n, d in L.items():
        src = AUD / f"{n}.wav"; dst = SC / f"{n}_pad.wav"
        delay = 600 if n == "00_sting" else 350
        if src.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", f"adelay={delay}|{delay},apad,atrim=0:{d}", "-ar", "48000", "-ac", "2", str(dst)], check=True)
        else:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(d), str(dst)], check=True)
        parts.append(f"file '{dst.name}'\n")
    alst.write_text("".join(parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(SC / "v.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c:a", "pcm_s16le", str(SC / "a.wav")], check=True)
    out = ED / ARGS.out
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SC / "v.mp4"), "-i", str(SC / "a.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out) + ".part.mp4"], check=True)
    os.replace(str(out) + ".part.mp4", out)
    json.dump(L, open(ED / f"scene_lengths_{ARGS.audio}.json", "w"), indent=1)
    print("captions:", write_captions(L, out.with_suffix(".srt")), "cues")
    make_thumbnail(ED / "thumbnail.png")
    (ED / "title.txt").write_text(yt_title(ST[0]["headline"], ED.name) + "\n")
    print("wrote", out)
