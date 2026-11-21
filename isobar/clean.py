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
PAD = 0.18          # seconds kept either side of each word
MIN_GAP_GATE = 0.35  # only gate gaps longer than this


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


def transcribe(wav):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("clean: faster-whisper not installed, skipping retakes and speech gate")
        return None
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    from scipy.signal import resample_poly
    sr, x = wavfile.read(wav)  # pass samples directly (avoids PyAV version issues)
    x = x.astype(np.float32) / 32768.0
    audio16 = resample_poly(x, 1, sr // 16000).astype(np.float32)
    segs, _ = model.transcribe(audio16, word_timestamps=True, condition_on_previous_text=False, beam_size=5)
    out = []
    for s in segs:
        words = [(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        if words:
            out.append({"start": words[0][0], "end": words[-1][1], "text": s.text.strip(), "words": words})
    print(f"clean: transcribed {len(out)} segments")
    return out


def find_retakes(segs):
    """A restart: you stop briefly, then say again what you had just said, from its first word.
    So the stumbled attempt w[i:j] is (mostly) a prefix of what follows w[j:], there is a short
    stop before w[j], and the stumble is at most 15 words long."""
    w = []
    for sg in segs:
        for st, en, raw in sg["words"]:
            n = re.sub(r"[^a-z0-9']", "", raw.lower())
            if n:
                w.append((st, en, n, raw.strip()))
    drop, i = [], 0
    while i < len(w) - 3:
        hit = None
        for j in range(i + 2, min(i + 16, len(w) - 2)):
            if w[j][0] - w[j - 1][1] < 0.25:          # no stop before the restart
                continue
            L = j - i
            m = 0
            while j + m < len(w) and i + m < j and w[i + m][2] == w[j + m][2]:
                m += 1
            finished = w[j - 1][3][-1:] in ".?!"   # first attempt was a complete sentence
            if m >= 3 and m >= 0.6 * L and not (finished and m < L):
                hit = j
                break
        if hit is not None:
            drop.append((w[i][0], w[hit][0]))
            i = hit
        else:
            i += 1
    return drop


def keep_mask(n, segs, drop):
    """True where audio is kept: near words, never inside a dropped retake."""
    speech = np.zeros(n, bool)
    for s in segs:
        for st, en, _ in s["words"]:
            speech[max(0, int((st - PAD) * SR)): min(n, int((en + PAD) * SR))] = True
    # short gaps between words stay as they are (natural rhythm)
    edges = np.flatnonzero(np.diff(speech.astype(np.int8)))
    for i in range(1, len(edges) - 1, 2):
        a, b = edges[i] + 1, edges[i + 1] + 1
        if (b - a) / SR < MIN_GAP_GATE:
            speech[a:b] = True
    return speech


def apply(wav, out, segs):
    sr, x = wavfile.read(wav)
    x = x.astype(np.float32)
    n = len(x)
    if not segs:
        wavfile.write(out, sr, x.astype(np.int16)); return 0.0
    drop = find_retakes(segs)
    gate = keep_mask(n, segs, drop).astype(np.float32)
    # 20 ms fades at every gate edge to avoid clicks
    k = int(0.02 * sr); win = np.ones(k) / k
    gate = np.convolve(gate, win, mode="same")
    y = x * gate
    cut = np.ones(n, bool)
    for a, b in drop:
        cut[int(a * sr): int(b * sr)] = False
    y = y[cut]
    wavfile.write(out, sr, np.clip(y, -32768, 32767).astype(np.int16))
    removed = (n - len(y)) / sr
    for a, b in drop:
        print(f"clean: removed retake {a:.1f}s to {b:.1f}s")
    return removed


def clean(take, out):
    with tempfile.TemporaryDirectory() as d:
        raw, den = Path(d) / "take.wav", Path(d) / "den.wav"
        to_wav(take, raw)
        denoise(raw, den)
        segs = transcribe(den)
        removed = apply(den, out, segs)
        if segs:
            json.dump(segs, open(Path(out).with_suffix(".words.json"), "w"))
    print(f"clean: wrote {out} ({removed:.1f}s of retakes removed)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("take"); ap.add_argument("out"); a = ap.parse_args()
    clean(a.take, a.out)


if __name__ == "__main__":
    main()
