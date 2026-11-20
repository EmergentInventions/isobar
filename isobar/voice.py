"""Turn the host's single recorded take into per-scene audio.

Record the whole recording script in one take, leaving a clear pause (about two seconds)
between sections where the script says [PAUSE]. We find the longest pauses and cut there.
Also writes recording.md: the script formatted for reading aloud.
"""
import argparse, json, re, subprocess
from pathlib import Path

from .tts_draft import scenes, dur


def recording_script(ed):
    sc = scenes(json.load(open(ed / "script.json")))
    lines = ["# Isobar recording script", "", "Read in one take. Pause for about two seconds at every [PAUSE].", ""]
    for n, t in sc:
        lines += [f"**{n}**", "", t, "", "[PAUSE]", ""]
    (ed / "recording.md").write_text("\n".join(lines))


def split(ed, take):
    sc = scenes(json.load(open(ed / "script.json")))
    need = len(sc) - 1
    log = subprocess.run(["ffmpeg", "-i", str(take), "-af", "silencedetect=n=-38dB:d=0.9", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    gaps = sorted(zip(starts, ends), key=lambda g: g[1] - g[0], reverse=True)
    total = dur(take)
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
