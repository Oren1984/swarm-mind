"""Builds the demo video from real footage, real charts and measured numbers.

    python scripts/build_video.py --footage build/footage

Steps: fill the narration script with numbers from experiments/results/summary.json,
synthesize narration (offline Windows SAPI voice), synthesize the background music
(original, generated here), assemble scenes with FFmpeg, burn in subtitles, validate.
Requires: ffmpeg/ffprobe on PATH, PowerShell 7 (pwsh) on Windows, numpy, Pillow.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "showcase" / "video"
DOCS = ROOT / "docs" / "demo-video"
W, H, FPS, SR = 1920, 1080, 30, 44100
BAND = 150  # bottom strip reserved for subtitles, so captions never cover footage or metrics
PAGE = (11, 11, 14)
LEAD, GAP, TAIL = 0.7, 0.35, 0.8
MUSIC_BELOW_SPEECH_DB = 21.0
FONT_DIR = Path("C:/Windows/Fonts")


def run(cmd: list, cwd: Path | None = None) -> str:
    res = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}\n{res.stderr[-3000:]}")
    return res.stdout + res.stderr


# ------------------------------------------------------------------- script
def measured_numbers() -> dict:
    """Every number spoken or shown in the video comes from the stored experiment."""
    summary = json.loads((ROOT / "experiments/results/summary.json").read_text(encoding="utf-8"))
    r, spec = summary["results"], summary["manifest"]["spec"]
    e1 = r["exp1_baseline_food_collection"]["food_delivered"]
    e3 = r["exp3_communication_failure"]
    sens = r["exp6_sensitivity"]
    stale = sens["evaporation=0.0+food_capacity=10"]["communication_effect"]
    if not (stale["relative_difference_pct"] < 0 < sens["evaporation=0.2"]["communication_effect"]["relative_difference_pct"]):
        raise SystemExit("the narration's wording about sensitivity no longer matches the measured results; edit video_script.json")
    return {
        "n_seeds": len(spec["seeds"]),
        "steps": spec["steps"],
        "cut_step": spec["interruption_step"],
        "agents": summary["manifest"]["default_config"]["agent_count"],
        "independent": round(e1["independent"]["mean"]),
        "collective": round(e1["collective"]["mean"]),
        "relative": round(e1["communication_effect"]["relative_difference_pct"]),
        "post_collective": round(e3["post_deliveries"]["collective"]["mean"]),
        "post_interrupted": round(e3["post_deliveries"]["interrupted"]["mean"]),
        "post_independent": round(e3["post_deliveries"]["independent"]["mean"]),
        "fast_evap_relative": round(sens["evaporation=0.2"]["communication_effect"]["relative_difference_pct"]),
        "stale_relative": round(sens["evaporation=0.0+food_capacity=10"]["communication_effect"]["relative_difference_pct"]),
        "stale_relative_abs": abs(round(sens["evaporation=0.0+food_capacity=10"]["communication_effect"]["relative_difference_pct"])),
    }


def load_script(numbers: dict) -> list[dict]:
    scenes = json.loads((ROOT / "scripts/video_script.json").read_text(encoding="utf-8"))
    for scene in scenes:
        for line in scene["lines"]:
            line["text"] = line["text"].format(**numbers)
            line["say"] = line.get("say", line["text"]).format(**numbers)
    return scenes


# ---------------------------------------------------------------- narration
def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as fh:
        assert fh.getframerate() == SR and fh.getsampwidth() == 2
        data = np.frombuffer(fh.readframes(fh.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
        return data.reshape(-1, fh.getnchannels()).mean(axis=1)


def write_wav(path: Path, stereo: np.ndarray) -> None:
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(2), fh.setsampwidth(2), fh.setframerate(SR)
        fh.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())


def trim_silence(audio: np.ndarray, threshold=0.004, keep=0.04) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if len(loud) == 0:
        return audio
    pad = int(keep * SR)
    return audio[max(0, loud[0] - pad): loud[-1] + pad]


def synthesize_narration(scenes: list[dict], work: Path, voice: str, rate: int) -> None:
    """Adds `audio` (numpy) to every line. One utterance per subtitle cue."""
    tts = work / "tts"
    tts.mkdir(parents=True, exist_ok=True)
    jobs, k = [], 0
    for scene in scenes:
        for line in scene["lines"]:
            line["wav"] = tts / f"line_{k:02d}.wav"
            jobs.append({"file": str(line["wav"]), "text": line["say"]})
            k += 1
    (tts / "lines.json").write_text(json.dumps(jobs), encoding="utf-8")
    run(["pwsh", "-NoProfile", "-File", ROOT / "scripts/tts.ps1", "-Lines", tts / "lines.json", "-Voice", voice, "-Rate", rate])
    for scene in scenes:
        for line in scene["lines"]:
            line["audio"] = trim_silence(read_wav(line["wav"]))


def schedule(scenes: list[dict]) -> float:
    """Assigns start/end times to scenes and cues from the real audio lengths."""
    t = 0.0
    for scene in scenes:
        scene["start"] = t
        t += LEAD
        for line in scene["lines"]:
            line["start"] = t
            line["end"] = t + len(line["audio"]) / SR
            t = line["end"] + GAP
        t += TAIL - GAP
        scene["end"] = t
        scene["duration"] = round((scene["end"] - scene["start"]) * FPS) / FPS
        t = scene["end"] = scene["start"] + scene["duration"]
    return t


# -------------------------------------------------------------------- music
def synthesize_music(duration: float, seed: int = 7) -> np.ndarray:
    """Original ambient bed generated from sine waves — no samples, no third-party material."""
    rng = np.random.default_rng(seed)
    n = int(round(duration * SR))
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    midi = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    chords = [[45, 52, 57, 60, 64], [41, 48, 57, 60, 65], [48, 55, 60, 64, 67], [43, 50, 59, 62, 67]]  # Am F C G
    bar, fade = 8.0, 3.0
    for i in range(int(duration / bar) + 1):
        start = i * bar - fade / 2
        local = t - start
        env = np.clip(local / fade, 0, 1) * np.clip((bar + fade - local) / fade, 0, 1)
        env = np.sin(env * np.pi / 2) ** 2
        active = env > 0
        for note in chords[i % 4]:
            f = midi(note)
            for ch, detune in ((0, 0.9985), (1, 1.0015)):
                tone = np.sin(2 * np.pi * f * detune * t[active]) + 0.25 * np.sin(2 * np.pi * 2 * f * detune * t[active] + 1.0)
                out[active, ch] += tone * env[active] * (0.5 if note < 50 else 0.3)
    out *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * t)[:, None]
    scale = [69, 72, 74, 76, 79, 81]  # A minor pentatonic bells
    when = 4.0
    while when < duration - 6:
        f, pan = midi(int(rng.choice(scale))), rng.uniform(0.25, 0.75)
        i0 = int(when * SR)
        seg = np.arange(min(n - i0, int(3.0 * SR))) / SR
        bell = np.sin(2 * np.pi * f * seg) * np.exp(-seg * 1.6) * np.clip(seg / 0.02, 0, 1) * 0.5
        out[i0:i0 + len(seg), 0] += bell * (1 - pan)
        out[i0:i0 + len(seg), 1] += bell * pan
        when += rng.uniform(2.5, 5.0)
    edge = np.clip(t / 2.5, 0, 1) * np.clip((duration - t) / 3.5, 0, 1)
    out *= edge[:, None]
    return out / np.abs(out).max()


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12))


# ------------------------------------------------------------------ visuals
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        if (FONT_DIR / name).exists():
            return ImageFont.truetype(str(FONT_DIR / name), size)
    return ImageFont.load_default(size)


def card(path: Path, title: str, subtitle: str, lines: list[str], backdrop: Path) -> None:
    """Title/closing card: text over a blurred, darkened REAL screenshot of the app."""
    img = Image.new("RGB", (W, H), PAGE)
    if backdrop.exists():
        shot = Image.open(backdrop).convert("RGB")
        scale = max(W / shot.width, H / shot.height)
        shot = shot.resize((int(shot.width * scale) + 1, int(shot.height * scale) + 1))
        shot = shot.crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(7))
        img = ImageEnhance.Brightness(shot).enhance(0.3)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - BAND, W, H], fill=PAGE)
    y = 300
    d.text((W / 2, y), title, font=font(104, True), fill="white", anchor="mm")
    d.text((W / 2, y + 110), subtitle, font=font(52), fill=(195, 194, 183), anchor="mm")
    d.line([(W / 2 - 180, y + 180), (W / 2 + 180, y + 180)], fill=(224, 86, 160), width=4)
    for i, text in enumerate(lines):
        d.text((W / 2, y + 250 + i * 56), text, font=font(34), fill=(225, 225, 220), anchor="mm")
    img.save(path)


FIT = (f"scale={W}:{H - BAND}:force_original_aspect_ratio=decrease,"
       f"pad={W}:{H}:(ow-iw)/2:({H - BAND}-ih)/2:color=0x0b0b0e,fps={FPS},format=yuv420p")
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an"]


def render_scene(scene: dict, work: Path, footage: Path, index: int) -> Path:
    target = work / f"scene_{index}_{scene['id']}.mp4"
    visual, dur = scene["visual"], scene["duration"]
    if visual["type"] == "clip":
        meta = {c["file"]: c for c in json.loads((footage / "footage.json").read_text())}[visual["file"]]
        if meta["seconds"] < dur:
            raise SystemExit(f"{visual['file']} has {meta['seconds']}s of footage, scene needs {dur:.1f}s")
        crop = meta.get("crop")
        vf = (f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}," if crop else "") + FIT
        run(["ffmpeg", "-y", "-ss", meta["trimStart"], "-i", footage / visual["file"], "-t", f"{dur:.4f}",
             "-vf", vf, *ENC, target])
        scene["source"] = f"{visual['file']} (simulation steps {meta['firstStep']}+, recorded live)"
    elif visual["type"] == "images":
        # image i is shown while line i is spoken
        cuts = [scene["start"]] + [l["start"] - GAP / 2 for l in scene["lines"][1:]] + [scene["end"]]
        parts = []
        for i, image in enumerate(visual["files"]):
            part = work / f"scene_{index}_part{i}.mp4"
            frames = round((cuts[i + 1] - cuts[i]) * FPS)
            run(["ffmpeg", "-y", "-loop", "1", "-i", ROOT / image, "-frames:v", frames, "-vf", FIT, *ENC, part])
            parts.append(part)
        concat(parts, target, work)
        scene["source"] = ", ".join(visual["files"])
    else:  # title / closing card
        png = work / f"card_{scene['id']}.png"
        card(png, visual["title"], visual["subtitle"], visual["lines"], ROOT / visual["backdrop"])
        run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-frames:v", round(dur * FPS), "-vf", f"fps={FPS},format=yuv420p", *ENC, target])
        scene["source"] = f"text card over blurred {visual['backdrop']}"
    return target


def concat(parts: list[Path], target: Path, work: Path) -> None:
    listing = work / f"{target.stem}.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", target])


# ---------------------------------------------------------------- subtitles
def stamp(t: float, sep: str) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def write_captions(scenes: list[dict]) -> list[dict]:
    cues = [l for s in scenes for l in s["lines"]]
    srt, vtt = [], ["WEBVTT", ""]
    for i, cue in enumerate(cues, 1):
        end = min(cue["end"] + 0.25, cues[i]["start"] - 0.05) if i < len(cues) else cue["end"] + 0.25
        cue["cue_end"] = end
        srt += [str(i), f"{stamp(cue['start'], ',')} --> {stamp(end, ',')}", cue["text"], ""]
        vtt += [f"{stamp(cue['start'], '.')} --> {stamp(end, '.')}", cue["text"], ""]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "captions-en.srt").write_text("\n".join(srt), encoding="utf-8")
    (DOCS / "captions-en.vtt").write_text("\n".join(vtt), encoding="utf-8")
    return cues


# --------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--footage", type=Path, default=ROOT / "build/footage")
    parser.add_argument("--work", type=Path, default=ROOT / "build/video")
    parser.add_argument("--voice", default="Microsoft Zira Desktop")
    parser.add_argument("--rate", type=int, default=1)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    numbers = measured_numbers()
    scenes = load_script(numbers)
    synthesize_narration(scenes, work, args.voice, args.rate)
    total = schedule(scenes)
    cues = write_captions(scenes)

    silent = work / "silent.mp4"
    concat([render_scene(s, work, args.footage.resolve(), i) for i, s in enumerate(scenes)], silent, work)

    n = int(round(total * SR))
    speech = np.zeros(n)
    for cue in cues:
        i0 = int(cue["start"] * SR)
        speech[i0:i0 + len(cue["audio"])] += cue["audio"][: n - i0]
    spoken = np.concatenate([c["audio"] for c in cues])
    music = synthesize_music(total)
    gain = 10 ** ((rms_db(spoken) - MUSIC_BELOW_SPEECH_DB - rms_db(music)) / 20)
    music *= gain
    mix = speech[:, None] + music
    mix *= 0.89 / np.abs(mix).max()
    write_wav(work / "mix.wav", mix)
    write_wav(work / "music-bed.wav", music / np.abs(music).max() * 0.5)

    final = OUT / "swarm-mind-demo.mp4"
    (work / "captions.srt").write_text((DOCS / "captions-en.srt").read_text(encoding="utf-8"), encoding="utf-8")
    style = ("FontName=Segoe UI,FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=1,Shadow=0,MarginV=7,MarginL=24,MarginR=24,Alignment=2")
    fade = f"fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.8:.2f}:d=0.8"
    run(["ffmpeg", "-y", "-i", "silent.mp4", "-i", "mix.wav",
         "-vf", f"subtitles=captions.srt:force_style='{style}',{fade}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", final], cwd=work)

    # ---- validation: measured from the rendered file, not assumed ----
    probe = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", final]))
    streams = {s["codec_type"]: s for s in probe["streams"]}
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"], capture_output=True, text=True)
    frames = work / "frames"
    frames.mkdir(exist_ok=True)
    checks = []
    for s in scenes:
        for label, at in (("first-cue", s["lines"][0]["start"] + 0.6), ("last-cue", s["lines"][-1]["start"] + 0.6)):
            png = frames / f"{s['id']}_{label}.png"
            run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", final, "-frames:v", "1", png])
            band = np.asarray(Image.open(png).convert("L"))[H - BAND:, :]
            checks.append({"scene": s["id"], "time": round(at, 2), "frame": png.name,
                           "subtitle_pixels_in_band": int((band > 200).sum())})
    report = {
        "file": str(final.relative_to(ROOT).as_posix()),
        "size_mb": round(final.stat().st_size / 1e6, 2),
        "duration_seconds": round(float(probe["format"]["duration"]), 2),
        "video": {k: streams["video"][k] for k in ("codec_name", "width", "height", "r_frame_rate", "pix_fmt", "nb_frames")},
        "audio": {k: streams["audio"][k] for k in ("codec_name", "sample_rate", "channels")},
        "full_decode_errors": decode.stderr.strip() or None,
        "narration": {"voice": args.voice, "rate": args.rate, "utterances": len(cues),
                      "speech_rms_db": round(rms_db(spoken), 1),
                      "music_rms_db_under_speech": round(rms_db(music), 1),
                      "speech_minus_music_db": round(rms_db(spoken) - rms_db(music), 1)},
        "subtitles": {
            "cues": len(cues),
            "each_cue_starts_with_its_own_utterance": True,
            "max_chars": max(len(c["text"]) for c in cues),
            "max_chars_per_second": round(max(len(c["text"]) / (c["cue_end"] - c["start"]) for c in cues), 1),
            "shortest_cue_seconds": round(min(c["cue_end"] - c["start"] for c in cues), 2),
            "overlapping_cues": sum(1 for a, b in zip(cues, cues[1:]) if a["cue_end"] > b["start"]),
            "subtitle_band_px": BAND,
        },
        "frame_checks": checks,
        "numbers_from_summary_json": numbers,
        "scenes": [{"id": s["id"], "start": round(s["start"], 2), "end": round(s["end"], 2), "source": s["source"],
                    "cues": [{"start": round(l["start"], 2), "end": round(l["cue_end"], 2), "text": l["text"]}
                             for l in s["lines"]]} for s in scenes],
    }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("file", "size_mb", "duration_seconds", "narration", "subtitles")}, indent=2))


if __name__ == "__main__":
    main()
