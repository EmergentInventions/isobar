"""AI voice for draft videos: Kokoro (Apache 2.0, runs on CPU), British male voice "bm_george".
Falls back to Festival HTS if Kokoro is unavailable. The final video uses the host's own voice when a take is uploaded."""
import argparse, json, os, subprocess, urllib.request
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("edition"); a = ap.parse_args()
    ed = Path(a.edition); out = ed / "audio_draft"; out.mkdir(exist_ok=True)
    sc = scenes(json.load(open(ed / "script.json")))
    try:
        import soundfile as sf
        k = kokoro()

        def synth(n, t):
            audio, sr = k.create(t, voice=VOICE, speed=1.0, lang="en-gb")
            sf.write(out / f"{n}_raw.wav", audio, sr)
        engine = f"kokoro/{VOICE}"
    except Exception as e:  # never block a draft on the AI voice
        print(f"draft voice: Kokoro unavailable ({e!r}), using Festival")

        def synth(n, t):
            subprocess.run(["text2wave", "-eval", "(voice_cmu_us_slt_arctic_hts)", "-eval", "(Parameter.set 'Duration_Stretch 1.0)",
                            str(out / f"{n}.txt"), "-o", str(out / f"{n}_raw.wav")], check=True)
        engine = "festival"

    d = {}
    for n, t in sc:  # sequential: Kokoro already uses every CPU core
        (out / f"{n}.txt").write_text(t)
        synth(n, t)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out / f"{n}_raw.wav"), "-af", FILTER, "-ac", "2", str(out / f"{n}.wav")], check=True)
        d[n] = dur(out / f"{n}.wav")
    json.dump(d, open(out / "durations.json", "w"), indent=1)
    print(f"draft voice ({engine}):", round(sum(d.values()) / 60, 1), "min")


if __name__ == "__main__":
    main()
