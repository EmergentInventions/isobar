"""AI voice for draft videos: Kokoro (Apache 2.0, runs on CPU), British male voice "bm_george".
Falls back to Festival HTS if Kokoro is unavailable. The final video uses the host's own voice when a take is uploaded."""
import argparse, json, os, re, subprocess, urllib.request
from pathlib import Path


def scenes(script):
    out = [("00_sting", "Isobar News."), ("01_intro", script["intro"]["narration"])]
    ntop = sum(1 for s in script["stories"] if s["segment"] == "top")
    for i, st in enumerate(script["stories"]):
        if i == ntop:
            out.append(("08a_radar", script["radar_bumper"]))
        out.append((f"{i+2:02d}_story", st["narration"]))
    return out + [("99_outro", script["outro"]["narration"])]


def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
VOICE = os.environ.get("ISOBAR_VOICE", "bm_george")
GAP = 0.32  # seconds of silence between sentences
FILTER = "highpass=f=80,acompressor=threshold=-18dB:ratio=3,loudnorm=I=-16:TP=-1.5,aresample=48000"


def kokoro():
    """Load Kokoro, downloading the model (~350 MB) to a cache dir on first use."""
    from kokoro_onnx import Kokoro
    cache = Path(os.environ.get("KOKORO_DIR", Path.home() / ".cache" / "kokoro")); cache.mkdir(parents=True, exist_ok=True)
    for f in KOKORO_FILES:
        if not (cache / f).exists():
            print("draft voice: downloading", f)
            urllib.request.urlretrieve(KOKORO_URL + f, cache / (f + ".part")); (cache / (f + ".part")).rename(cache / f)
    return Kokoro(str(cache / KOKORO_FILES[0]), str(cache / KOKORO_FILES[1]))


def lexicon(ed):
    """pronunciations.json at the editions repo root (two levels above editions/DATE), if present."""
    f = Path(ed).resolve().parent.parent / "pronunciations.json"
    lex = {k: v for k, v in json.load(open(f)).items() if not k.startswith("_")} if f.exists() else {}
    return lex


YEAR = re.compile(r"(?<![\d$£€.,])(1[1-9]\d\d|20\d\d)(?![\d%]|,\d|\.\d| per ?cent)")


def speak_years(text):
    """Years as people say them: 2030 -> 'twenty thirty', 1990 -> 'nineteen ninety', 2005 -> 'two thousand and five'."""
    from num2words import num2words
    return YEAR.sub(lambda m: num2words(int(m.group(1)), to="year", lang="en_GB"), text)


# Abbreviations the voice would spell out or misread, expanded before speaking.
ABBREV = [(r"\bJr\b\.?", "Junior"), (r"\bSr\b\.?", "Senior"),
          (r"\bSen\.(?= [A-Z])", "Senator"), (r"\bRep\.(?= [A-Z])", "Representative"), (r"\bGov\.(?= [A-Z])", "Governor"),
          (r"\bGen\.(?= [A-Z])", "General"), (r"\bLt\.(?= [A-Z])", "Lieutenant"), (r"\bCol\.(?= [A-Z])", "Colonel"),
          (r"\bSgt\.(?= [A-Z])", "Sergeant"), (r"\bCapt\.(?= [A-Z])", "Captain"), (r"\bProf\.(?= [A-Z])", "Professor")]


# Heteronyms espeak guesses wrong without grammar: (pattern, phonemes) applied as fixed pronunciations.
# "live" is the verb (lɪv) in lists like "live, work or study" and before in/on/with/abroad/together;
# the adjective (laɪv) is left to espeak ("live broadcast", "live music").
HETERONYMS = [(r"\b(live)(?=,| or | and | in | on | with | abroad| together| here| there| longer)", "lɪv"),
              (r"\b(?:to|who|they|we|you|can|could|would|will|people|families|residents)\s+(live)\b", "lɪv")]


CUR = {"£": ("pound", "pounds"), "$": ("dollar", "dollars"), "€": ("euro", "euros")}
SCALE = {"k": "thousand", "m": "million", "bn": "billion", "tn": "trillion",
         "thousand": "thousand", "million": "million", "billion": "billion", "trillion": "trillion"}
MONEY = re.compile(r"([£$€])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s?(k|m|bn|tn|thousand|million|billion|trillion)\b)?")
# Initialisms said as words; every other run of 2-6 capitals is spelled out letter by letter.
WORD_ACRONYMS = {"NATO", "NASA", "OPEC", "UNESCO", "UNICEF", "COVID", "FIFA", "UEFA", "ASEAN", "AWACS", "ISIS",
                 "CERN", "NAFTA", "SWIFT", "AIDS", "OFCOM", "OFGEM", "OFSTED", "FTSE", "NASDAQ", "BRICS", "SARS", "MERS",
                 "UKIP", "ACAS", "SATS", "GCSE", "SCOTUS", "POTUS"} - {"GCSE"}
LETTER = dict(A="eɪ", B="biː", C="siː", D="diː", E="iː", F="ɛf", G="dʒiː", H="eɪtʃ", I="aɪ", J="dʒeɪ", K="keɪ", L="ɛl",
              M="ɛm", N="ɛn", O="əʊ", P="piː", Q="kjuː", R="ɑː", S="ɛs", T="tiː", U="juː", V="viː", W="dˈʌbəljuː",
              X="ɛks", Y="waɪ", Z="zɛd")


def spell(word):
    """'IMF' -> ˌaɪˌɛmˈɛf: letter names, main stress on the last letter, as a newsreader says it."""
    parts = [LETTER[c].replace("ˈ", "") for c in word]
    return "".join("ˌ" + p for p in parts[:-1]) + "ˈ" + parts[-1]


def say_money(m):
    from num2words import num2words as _n2w
    num2words = lambda *a, **k: _n2w(*a, **k).replace(",", "")
    sym, num, scale = m.group(1), m.group(2).replace(",", ""), m.group(3)
    one, many = CUR[sym]
    if scale:
        return f"{num2words(float(num) if '.' in num else int(num), lang='en_GB')} {SCALE[scale]} {many}"
    if "." in num:
        whole, frac = num.split(".", 1)
        w = num2words(int(whole), lang="en_GB")
        unit = one if whole == "1" else many
        return f"{w} {unit} {num2words(int(frac), lang='en_GB')}" if int(frac) else f"{w} {unit}"
    return f"{num2words(int(num), lang='en_GB')} {one if num == '1' else many}"


def expand(text):
    for pat, rep in ABBREV:
        text = re.sub(pat, rep, text)
    text = MONEY.sub(say_money, text)
    text = re.sub(r"\b1p\b", "one penny", text)
    text = re.sub(r"\b(\d+)p\b", r"\1 pence", text)
    return speak_years(text)


def heteronyms(text):
    """Mark heteronyms with a private-use placeholder the phonemiser passes through as fixed phonemes."""
    fixed = []
    for pat, ph in HETERONYMS:
        def sub(m, ph=ph):  # replace only the captured word, keep any context the pattern matched
            fixed.append(ph); w = m.group(0); a, b = m.start(1) - m.start(0), m.end(1) - m.start(0)
            return w[:a] + f"\uE000{len(fixed) - 1}\uE001" + w[b:]
        text = re.sub(pat, sub, text, flags=re.I)
    return text, fixed


def to_phonemes(k, text, lex):
    """espeak (en-gb) phonemes, with listed words replaced by their fixed pronunciation."""
    text, fixed = heteronyms(expand(text))
    keys = sorted(lex, key=len, reverse=True)
    lexalt = (r"(?<![\w&-])(" + "|".join(map(re.escape, keys)) + r")('s|’s)?(?![\w&-])") if keys else r"(?!x)x()()"
    rx = re.compile(r"\uE000(\d+)\uE001|" + lexalt + r"|(?<![\w&-])([A-Z]{2,6})(s|'s|’s)?(?![\w&-])")
    out, pos = [], 0
    for m in rx.finditer(text):
        if text[pos:m.start()].strip():
            out.append(k.tokenizer.phonemize(text[pos:m.start()], "en-gb"))
        if m.group(1) is not None:
            out.append(fixed[int(m.group(1))])
        elif m.group(2) is not None:
            out.append(lex[m.group(2)] + ("z" if m.group(3) else ""))
        elif m.group(4).upper() in WORD_ACRONYMS:
            out.append(k.tokenizer.phonemize(m.group(0), "en-gb"))
        else:
            out.append(spell(m.group(4)) + ("z" if m.group(5) else ""))
        pos = m.end()
    if text[pos:].strip():
        out.append(k.tokenizer.phonemize(text[pos:], "en-gb"))
    return re.sub(r" +([.,;:!?])", r"\1", " ".join(x.strip() for x in out if x.strip()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); a = ap.parse_args()
    ed = Path(a.edition); out = ed / "audio_draft"; out.mkdir(exist_ok=True)
    sc = scenes(json.load(open(ed / "script.json")))
    try:
        import soundfile as sf
        k = kokoro()

        lex = lexicon(ed)
        print(f"draft voice: {len(lex)} pronunciation fixes loaded")

        import numpy as np
        from .common import sentences

        def synth(n, t):
            """Voice each sentence separately, joined by a short pause, and record when each one is spoken.
            The timings drive captions and the bullet reveals."""
            parts, marks, pos, sr = [], [], 0.0, 24000
            for s in sentences(t):
                audio, sr = k.create(to_phonemes(k, s, lex), voice=VOICE, speed=1.0, lang="en-gb", is_phonemes=True)
                if parts:
                    parts.append(np.zeros(int(GAP * sr), dtype=audio.dtype)); pos += GAP
                marks.append([round(pos, 3), round(pos + len(audio) / sr, 3), s]); pos += len(audio) / sr
                parts.append(audio)
            sf.write(out / f"{n}_raw.wav", np.concatenate(parts), sr)
            timings[n] = marks
        engine = f"kokoro/{VOICE}"
    except Exception as e:  # never block a draft on the AI voice
        print(f"draft voice: Kokoro unavailable ({e!r}), using Festival")

        def synth(n, t):
            subprocess.run(["text2wave", "-eval", "(voice_cmu_us_slt_arctic_hts)", "-eval", "(Parameter.set 'Duration_Stretch 1.0)",
                            str(out / f"{n}.txt"), "-o", str(out / f"{n}_raw.wav")], check=True)
        engine = "festival"

    d, timings = {}, {}
    for n, t in sc:  # sequential: Kokoro already uses every CPU core
        (out / f"{n}.txt").write_text(t)
        synth(n, t)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out / f"{n}_raw.wav"), "-af", FILTER, "-ac", "2", str(out / f"{n}.wav")], check=True)
        d[n] = dur(out / f"{n}.wav")
    json.dump(d, open(out / "durations.json", "w"), indent=1)
    if timings:
        json.dump(timings, open(out / "timings.json", "w"), indent=1, ensure_ascii=False)
    print(f"draft voice ({engine}):", round(sum(d.values()) / 60, 1), "min")


if __name__ == "__main__":
    main()
