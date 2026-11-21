"""Turn the host's single recorded take into per-scene audio (after cleaning: see clean.py).

Record the whole recording script in one take, leaving a clear pause (about two seconds)
between sections where the script says [PAUSE]. We find the longest pauses and cut there.
Also writes recording.md: the script formatted for reading aloud.
"""
import argparse, json, re, subprocess
from pathlib import Path

from .tts_draft import scenes, dur


def recording_script(ed):
    sc = scenes(json.load(open(ed / "script.json")))
    lines = ["# Isobar recording script", "",
             "Read in one take. Pause for about two seconds at every [PAUSE]. Do not read the bold labels.",
             "If you stumble or get interrupted, stop for a moment (under a second) and start that sentence again.",
             "Background noise and the stumbled attempt are removed automatically.", ""]
    for n, t in sc:
        lines += [f"**{n}**", "", t, "", "[PAUSE]", ""]
    (ed / "recording.md").write_text("\n".join(lines))


def split(ed, take):
    from .clean import clean
    cleaned = ed / "voice_clean.wav"
    clean(take, cleaned)
    take = cleaned
    sc = scenes(json.load(open(ed / "script.json")))
    need = len(sc) - 1
    total = dur(take)
    spans = None
    wj = Path(str(take)).with_suffix(".words.json")
    if wj.exists():
        from .align import section_starts
        words = [tuple(x) for sg in json.load(open(wj)) for x in sg["words"]]
        times, cov = section_starts(sc, words)
        if times and cov >= 0.6:
            ends = []
            for k, t0 in enumerate(times):
                t1 = times[k + 1] if k + 1 < len(times) else total
                last = max((e for st_, e, _ in words if t0 <= st_ < t1), default=t1)
                ends.append(min(t1, last + 0.25))
            spans = list(zip(times, ends))
            print(f"voice: cut by matching your words to the script ({cov:.0%} of script words heard)")
            for (n, _), (a_, _) in zip(sc, spans):
                first = " ".join(w for st_, _, w in words if st_ >= a_)[:60]
                print(f"voice:   {n:10s} {a_:7.1f}s  {first}")
        else:
            print(f"voice: script matching unreliable ({cov:.0%}), falling back to pauses")
    if spans is None:
        log = subprocess.run(["ffmpeg", "-i", str(take), "-af", "silencedetect=n=-38dB:d=0.9", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
        gaps = sorted(zip(starts, ends), key=lambda g: g[1] - g[0], reverse=True)
        gaps = sorted([g for g in gaps if g[0] > 0.3 and g[1] < total - 0.25][:need])
        if len(gaps) < need:
            raise SystemExit(f"found {len(gaps)} pauses but need {need}: re-record with clearer pauses at each [PAUSE]")
        # speech runs from the end of one pause to the start of the next
        lead = next((e for s_, e in zip(starts, ends) if s_ < 0.05), 0.0)
        tail = next((s_ for s_, e in zip(starts, ends) if e >= total - 0.25), total)
        spans = list(zip([lead] + [e for _, e in gaps], [s_ for s_, _ in gaps] + [tail]))
    out = ed / "audio_final"; out.mkdir(exist_ok=True)
    d = {}
    for (n, _), (a_, b_) in zip(sc, spans):
        f = out / f"{n}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(take), "-ss", f"{max(0, a_ - 0.08):.3f}", "-to", f"{b_ + 0.12:.3f}", "-af",
                        "highpass=f=70,acompressor=threshold=-20dB:ratio=2.5,loudnorm=I=-16:TP=-1.5,aresample=48000", "-ac", "2", str(f)], check=True)
        d[n] = dur(f)
    json.dump(d, open(out / "durations.json", "w"), indent=1)
    print("final voice:", round(sum(d.values()) / 60, 1), "min across", len(d), "scenes")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); ap.add_argument("--take"); a = ap.parse_args()
    ed = Path(a.edition)
    if a.take:
        split(ed, Path(a.take))
    else:
        recording_script(ed)


if __name__ == "__main__":
    main()
