"""Isobar's own music bed and sound design, generated in code (no licence needed, same every day, fully automatic).

Score: A minor, 76 bpm, i-VI-III-VII. The texture changes with the part of the show, never with a story's emotion:
  cold open  - low drone only
  sting      - one soft low hit and a bell
  main/doc   - pad, quiet arpeggio, soft heartbeat pulse
  radar      - pad an octave up, sparse bells, no pulse (a different "room")
  outro      - pad fading out
Sound effects come from render's sfx_events_<audio>.json: paper (clipping lands), marker (highlight), tick (timeline),
rise (chart), soft (card), plus a quiet whoosh at each story change. The bed ducks under the voice.

Usage: python -m isobar.music ED --video isobar-DATE-draft.mp4 [--audio audio_draft]
"""
import argparse, json, subprocess
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
BPM = 76.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
A4 = 440.0
# chords as semitones from A4 (A minor, F, C, G), voiced low
CHORDS = [[-24, -12, -9, -5], [-28, -16, -12, -9], [-21, -9, -5, -2], [-26, -14, -10, -7]]
LEVEL_DB = -16.0          # music relative to the voice's speech level, before ducking
DUCK = 0.5                # how far the bed dips under speech (0..1): about -6 dB


def hz(semi):
    return A4 * 2 ** (semi / 12)


def env_adsr(n, a, r):
    e = np.ones(n, dtype=np.float32); na, nr = int(a * SR), int(r * SR)
    if na: e[:na] = np.linspace(0, 1, na)
    if nr: e[-nr:] *= np.linspace(1, 0, nr)
    return e


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x).astype(np.float32)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x).astype(np.float32)


def soft_saw(f, n, detune=0.0, phase=0.0):
    t = np.arange(n, dtype=np.float32) / SR
    return sum(np.sin(2 * np.pi * f * (1 + detune) * k * t + phase * k) / k for k in range(1, 7)).astype(np.float32)


def pad(n, t0, octave=0):
    """Chord pad from absolute time t0 (so chords stay on the bar grid across segments)."""
    out = np.zeros(n, dtype=np.float32); start = 0
    while start < n:
        abs_t = t0 + start / SR; ci = int(abs_t // (2 * BAR)) % len(CHORDS)
        seg_end = min(n, start + int(((int(abs_t // (2 * BAR)) + 1) * 2 * BAR - abs_t) * SR) + 1)
        m = seg_end - start; chunk = np.zeros(m, dtype=np.float32)
        for s in CHORDS[ci]:
            f = hz(s + 12 * octave)
            chunk += 0.5 * soft_saw(f, m, 0.0025) + 0.5 * soft_saw(f, m, -0.0025, 1.3)
        out[start:seg_end] += chunk * env_adsr(m, min(0.9, m / SR / 3), min(0.9, m / SR / 3))
        start = seg_end
    return lp(out, 900 if octave <= 0 else 1500) * 0.08


def pluck(f, dur=0.9):
    n = int(dur * SR); t = np.arange(n, dtype=np.float32) / SR
    return ((np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 5.5)).astype(np.float32)


def arps(n, t0, octave=2, every=0.5, gain=0.05):
    out = np.zeros(n + SR, dtype=np.float32); k0 = int(np.ceil(t0 / (every * BEAT)))
    k = k0
    while True:
        at = k * every * BEAT - t0
        if at >= n / SR: break
        ci = int((k * every * BEAT) // (2 * BAR)) % len(CHORDS); notes = CHORDS[ci][1:]
        f = hz(notes[k % len(notes)] + 12 * octave); p = pluck(f); i = int(at * SR)
        out[i:i + len(p)] += p[: len(out) - i] * gain; k += 1
    return out[:n]


def pulse(n, t0):
    out = np.zeros(n + SR, dtype=np.float32); k = int(np.ceil(t0 / (2 * BEAT)))
    while True:
        at = k * 2 * BEAT - t0
        if at >= n / SR: break
        m = int(0.5 * SR); t = np.arange(m, dtype=np.float32) / SR
        hit = np.sin(2 * np.pi * (48 + 30 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
        i = int(at * SR); out[i:i + m] += hit[: len(out) - i] * 0.16; k += 1
    return out[:n]


def drone(n):
    t = np.arange(n, dtype=np.float32) / SR
    x = (np.sin(2 * np.pi * hz(-36) * t) + 0.6 * np.sin(2 * np.pi * hz(-29) * t) + 0.25 * np.sin(2 * np.pi * hz(-24) * t * 1.002))
    return (lp(x.astype(np.float32), 400) * 0.10 * env_adsr(n, 1.2, 0.8))


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def sfx(kind, seed=0):
    if kind == "paper":
        n = int(0.42 * SR); t = np.arange(n) / SR; x = bp(noise(n, seed), 1500, 7000)
        e = np.exp(-t * 14) + 0.6 * np.exp(-np.maximum(0, t - 0.12) * 18) * (t > 0.12)
        return (x * e * 0.22).astype(np.float32)
    if kind == "marker":
        n = int(0.5 * SR); t = np.arange(n) / SR; x = bp(noise(n, seed), 2500, 5500)
        return (x * np.sin(np.pi * t / t[-1]) ** 2 * 0.05).astype(np.float32)
    if kind == "tick":
        n = int(0.12 * SR); t = np.arange(n) / SR
        return ((np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 60)) * 0.16).astype(np.float32)
    if kind == "rise":
        n = int(0.9 * SR); t = np.arange(n) / SR; f = 300 + 500 * t / t[-1]
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / t[-1]) * 0.05).astype(np.float32)
    if kind == "whoosh":
        n = int(0.7 * SR); t = np.arange(n) / SR; x = noise(n, seed)
        x = bp(x, 200, 2400) * np.sin(np.pi * t / t[-1]) ** 2
        return (x * 0.07).astype(np.float32)
    if kind == "sting":
        n = int(2.5 * SR); t = np.arange(n) / SR
        hit = np.sin(2 * np.pi * (45 + 25 * np.exp(-t * 25)) * t) * np.exp(-t * 4) * 0.35
        bell = sum(np.sin(2 * np.pi * hz(3) * r * t) * a for r, a in ((1, 1), (2.76, 0.4), (5.4, 0.2))) * np.exp(-t * 2.2) * 0.06
        return (hit + bell).astype(np.float32)
    n = int(0.08 * SR); t = np.arange(n) / SR       # "soft"
    return (np.sin(2 * np.pi * 900 * t) * np.exp(-t * 70) * 0.06).astype(np.float32)


def part_of(name, radar_names):
    if name == "00_cold": return "cold"
    if name == "00_sting": return "sting"
    if name == "99_outro": return "outro"
    if name in radar_names: return "radar"
    return "main"


def build(ed: Path, audio: str, total: float):
    meta = json.load(open(ed / f"sfx_events_{audio}.json")); scenes = meta["scenes"]
    script = json.load(open(ed / "script.json"))
    radar_ids = {f"{i+2:02d}_story" for i, s in enumerate(script["stories"]) if s["segment"] == "radar"} | {"08a_radar"}
    n = int(total * SR) + SR; bed = np.zeros(n, dtype=np.float32); fx = np.zeros(n, dtype=np.float32)
    t = 0.0; XF = 1.0
    for name, d in scenes.items():
        part = part_of(name, radar_ids); i0 = int(max(0, t - XF / 2) * SR); m = int((d + XF) * SR); t0 = i0 / SR
        if part == "cold":
            x = drone(m)
        elif part == "sting":
            x = np.zeros(m, dtype=np.float32); fx[int(t * SR):int(t * SR) + int(2.5 * SR)] += sfx("sting")[: n - int(t * SR)]
        elif part == "radar":
            x = pad(m, t0, octave=1) * 0.8 + arps(m, t0, octave=3, every=2, gain=0.035)
        elif part == "outro":
            x = pad(m, t0) * np.linspace(1, 0, m, dtype=np.float32) ** 1.5
        else:
            x = pad(m, t0) + arps(m, t0) + pulse(m, t0)
        x = x * env_adsr(m, XF, XF)
        bed[i0:i0 + m] += x[: n - i0]
        if name.endswith("_story") or name.endswith("_timeline") or name.endswith("_clips"):
            w = sfx("whoosh", seed=int(t * 10)); j = int(max(0, t - 0.25) * SR); fx[j:j + len(w)] += w[: n - j]
        t += d
    for k, (at, kind) in enumerate(meta["events"]):
        s = sfx(kind, seed=k); j = int(at * SR)
        if j < n: fx[j:j + len(s)] += s[: n - j]
    return bed, fx


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); ap.add_argument("--video", required=True)
    ap.add_argument("--audio", default="audio_draft"); a = ap.parse_args()
    ed = Path(a.edition); vid = ed / a.video; tmp = ed / "_mix"; tmp.mkdir(exist_ok=True)
    import soundfile as sf
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-vn", "-ac", "1", "-ar", str(SR), str(tmp / "voice.wav")], check=True)
    voice, _ = sf.read(tmp / "voice.wav", dtype="float32"); total = len(voice) / SR
    bed, fx = build(ed, a.audio, total); bed, fx = bed[: len(voice)], fx[: len(voice)]
    # levels: set the bed relative to the voice's speech level, then duck it under speech
    env = np.sqrt(np.maximum(lp(voice ** 2, 6), 0))
    speech = np.percentile(env[env > 1e-4], 70) if np.any(env > 1e-4) else 0.05
    bed_rms = np.sqrt(np.mean(bed ** 2)) + 1e-9
    bed *= speech * 10 ** (LEVEL_DB / 20) / bed_rms
    talk = np.clip(env / (speech * 0.35), 0, 1)
    gain = lp((1 - DUCK * talk).astype(np.float32), 3)
    fx *= speech / 0.5 * 0.9
    mix = voice + bed * gain + fx
    peak = np.max(np.abs(mix))
    if peak > 0.98: mix *= 0.98 / peak
    sf.write(tmp / "mix.wav", np.stack([mix, mix], 1), SR)
    out = vid.with_name(vid.stem + ".music.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(tmp / "mix.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=True)
    out.replace(vid)
    print(f"music: bed {LEVEL_DB} dB under speech, ducked {int(DUCK * 100)}%, {len(json.load(open(ed / f'sfx_events_{a.audio}.json'))['events'])} effects")


if __name__ == "__main__":
    main()
