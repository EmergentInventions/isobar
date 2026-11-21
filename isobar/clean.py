"""Clean the host's take before it is cut into sections.

1. Denoise: DeepFilterNet (deep-filter binary) removes steady noise: traffic, hum, hiss, fans.
2. Transcribe: faster-whisper gives word timings.
3. Retakes: when a sentence is restarted, the earlier attempt is cut out.
4. Speech gate: everything more than a moment away from a spoken word is silenced, which removes
   barks, doors, gates and coughs that fall between words and sentences.
Each step is skipped (with a message) if its tool is missing, so a take always gets through.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SR = 48000
PAD_BEFORE = 0.25   # seconds kept before each word
PAD_AFTER = 0.55    # Whisper word ends run early: keep generous tails so endings are never clipped
MIN_GAP_GATE = 1.0  # only silence gaps longer than this (pauses between sentences or sections)


def to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", str(dst)], check=True)


def denoise(wav, out):
    exe = os.environ.get("DEEP_FILTER") or shutil.which("deep-filter")
    if not exe:
        print("clean: deep-filter not found, using ffmpeg afftdn instead")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", "afftdn=nr=18:nf=-40", str(out)], check=True)
        return
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([exe, "-D", "-o", d, str(wav)], check=True, capture_output=True)
        shutil.move(str(Path(d) / Path(wav).name), str(out))
    print("clean: denoised with DeepFilterNet")


# Fillers only: Whisper copies the verbatim style, and anything that leaks is a filler we ignore
PROMPT = "Um, uh, er- erm, uh- um. Hmm, uh, um- er."
# A second pass with a fuller example finds more restarts but can invent words, so its cuts
# are only used when the first transcript confirms them (see retakes.confirmed)
PROMPT2 = "Umm, so, uh, the the president- the president said, um, that- that it was, uh, it was fine."
LONG_WORD = 0.9      # a word timed longer than this usually hides a restart Whisper skipped


def _words(model, audio16, offset=0.0, prompt=PROMPT):
    segs, _ = model.transcribe(audio16, language="en", word_timestamps=True, beam_size=5,
                               condition_on_previous_text=False, initial_prompt=prompt)
    return [(w.start + offset, w.end + offset, w.word) for s in segs for w in s.words]


def _refine(model, audio16, words, prompt=PROMPT):
    """Re-transcribe a short clip around each over-long word. On a clip of a few seconds Whisper
    usually writes out both attempts instead of smoothing one away."""
    out, k, fixed = [], 0, 0
    while k < len(words):
        if words[k][1] - words[k][0] <= LONG_WORD:
            out.append(words[k]); k += 1; continue
        a_i, b_i = max(0, k - 3), min(len(words), k + 4)
        while b_i < len(words) and words[b_i][1] - words[b_i][0] > LONG_WORD:
            b_i = min(len(words), b_i + 3)
        a, b = words[a_i][0], words[b_i - 1][1]
        clip = audio16[int(max(0, a - 0.1) * 16000): int((b + 0.1) * 16000)]
        new = [w for w in _words(model, clip, max(0, a - 0.1), prompt) if a - 0.2 <= w[0] <= b + 0.1]
        old = words[a_i:b_i]
        if len(new) > len(old):
            out = [w for w in out if w[0] < a]
            out += new; fixed += 1
        else:
            out += [w for w in old if not out or w[0] > out[-1][0]]
        k = b_i
    if fixed:
        print(f"clean: re-checked {fixed} passages where words seemed to be missing")
    return out


def transcribe(wav):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("clean: faster-whisper not installed, skipping retakes and speech gate")
        return None
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8")
    from scipy.signal import resample_poly
    sr, x = wavfile.read(wav)  # pass samples directly (avoids PyAV version issues)
    x = x.astype(np.float32) / 32768.0
    audio16 = resample_poly(x, 1, sr // 16000).astype(np.float32)
    words = _refine(model, audio16, _words(model, audio16))
    second = None
    if os.environ.get("ISOBAR_SECOND_PASS", "1") == "1":
        second = _refine(model, audio16, _words(model, audio16, prompt=PROMPT2), PROMPT2)
    # group into sentences so the rest of the pipeline keeps its segment format
    out, cur = [], []
    for w in words:
        cur.append(w)
        if w[2].strip()[-1:] in ".?!":
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    out = [{"start": c[0][0], "end": c[-1][1], "text": "".join(x[2] for x in c).strip(), "words": c} for c in out]
    print(f"clean: transcribed {len(words)} words")
    if second:
        out[0]["second_pass"] = second
    return out


def find_retakes(segs, script_text=None):
    """Earlier attempts of a phrase you then said again. Needs the script (see retakes.py)."""
    if not script_text:
        return []
    from .retakes import find, confirmed
    words = [tuple(w) for s in segs for w in s["words"]]
    drops = find(words, script_text)
    second = segs[0].get("second_pass") if segs else None
    if second:
        drops += find([tuple(w) for w in second], script_text)
    return confirmed(drops, words, script_text)


def keep_mask(n, segs, drop):
    """True where audio is kept: near words, never inside a dropped retake."""
    speech = np.zeros(n, bool)
    for s in segs:
        for st, en, _ in s["words"]:
            speech[max(0, int((st - PAD_BEFORE) * SR)): min(n, int((en + PAD_AFTER) * SR))] = True
    # short gaps between words stay as they are (natural rhythm)
    edges = np.flatnonzero(np.diff(speech.astype(np.int8)))
    for i in range(1, len(edges) - 1, 2):
        a, b = edges[i] + 1, edges[i + 1] + 1
        if (b - a) / SR < MIN_GAP_GATE:
            speech[a:b] = True
    return speech


def apply(wav, out, segs, script_text=None):
    sr, x = wavfile.read(wav)
    x = x.astype(np.float32)
    n = len(x)
    if not segs:
        wavfile.write(out, sr, x.astype(np.int16)); return 0.0, []
    drop = find_retakes(segs, script_text)
    gate = keep_mask(n, segs, drop).astype(np.float32)
    # 20 ms fades at every gate edge to avoid clicks
    k = int(0.08 * sr); win = np.ones(k) / k  # gentle 80 ms fades
    gate = np.convolve(gate, win, mode="same")
    y = x * gate
    cut = np.ones(n, bool)
    for a, b in drop:
        cut[int(a * sr): int(b * sr)] = False
    y = y[cut]
    wavfile.write(out, sr, np.clip(y, -32768, 32767).astype(np.int16))
    removed = (n - len(y)) / sr
    for a, b in drop:
        print(f"clean: removed retake {a:.1f}s to {b:.1f}s: {said(segs, a, b)}")
    return removed, drop


def said(segs, a, b):
    return "".join(w for s in segs for st, _, w in s["words"] if a <= st < b).strip()[:80]


def shift_words(segs, drop):
    """Move word timings to match the audio after retakes were cut out."""
    def moved(t):
        return t - sum(min(b, t) - a for a, b in drop if a < t)
    out = []
    for sg in segs:
        ws = [(moved(a), moved(b), w) for a, b, w in sg["words"] if not any(x <= a < y for x, y in drop)]
        if ws:
            out.append({**sg, "start": ws[0][0], "end": ws[-1][1], "words": ws})
    return out


def clean(take, out, script_text=None):
    with tempfile.TemporaryDirectory() as d:
        raw, den = Path(d) / "take.wav", Path(d) / "den.wav"
        to_wav(take, raw)
        denoise(raw, den)
        segs = transcribe(den)
        removed, drop = apply(den, out, segs, script_text)
        if segs:
            json.dump(shift_words(segs, drop), open(Path(out).with_suffix(".words.json"), "w"))
    print(f"clean: wrote {out} ({removed:.1f}s of retakes removed)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("take"); ap.add_argument("out")
    ap.add_argument("--script", help="script.json, to recognise restarted phrases"); a = ap.parse_args()
    text = None
    if a.script:
        from .tts_draft import scenes
        text = " ".join(t for _, t in scenes(json.load(open(a.script))))
    clean(a.take, a.out, text)


if __name__ == "__main__":
    main()
