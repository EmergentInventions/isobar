"""Placeholder voice for draft videos (Festival HTS). The final video uses the host's own voice."""
import argparse, json, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def scenes(script):
    out = [("00_sting", "Isobar."), ("01_intro", script["intro"]["narration"])]
    ntop = sum(1 for s in script["stories"] if s["segment"] == "top")
    for i, st in enumerate(script["stories"]):
        if i == ntop:
            out.append(("08a_radar", script["radar_bumper"]))
        out.append((f"{i+2:02d}_story", st["narration"]))
    return out + [("99_outro", script["outro"]["narration"])]


def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); a = ap.parse_args()
    ed = Path(a.edition); out = ed / "audio_draft"; out.mkdir(exist_ok=True)
    sc = scenes(json.load(open(ed / "script.json")))

    def run(item):
        n, t = item
        (out / f"{n}.txt").write_text(t)
        subprocess.run(["text2wave", "-eval", "(voice_cmu_us_slt_arctic_hts)", "-eval", "(Parameter.set 'Duration_Stretch 1.0)",
                        str(out / f"{n}.txt"), "-o", str(out / f"{n}_raw.wav")], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out / f"{n}_raw.wav"), "-af",
                        "highpass=f=80,acompressor=threshold=-18dB:ratio=3,loudnorm=I=-16:TP=-1.5,aresample=48000", "-ac", "2", str(out / f"{n}.wav")], check=True)
        return n, dur(out / f"{n}.wav")

    with ThreadPoolExecutor(4) as ex:
        d = dict(ex.map(run, sc))
    json.dump(d, open(out / "durations.json", "w"), indent=1)
    print("draft voice:", round(sum(d.values()) / 60, 1), "min")


if __name__ == "__main__":
    main()
