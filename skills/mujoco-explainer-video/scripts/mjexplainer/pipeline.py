"""Spec -> frames -> MP4 (+ SRT captions, contact sheet, mixed audio)."""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import yaml
from PIL import Image

from . import graphics as g
from .sim import SimView

SKILL_DIR = Path(__file__).resolve().parents[2]
SCENE_LIBRARY = [SKILL_DIR / "assets" / "scenes"]


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# --------------------------------------------------------------------------- narration (optional)
def synth_tts(text: str, out_wav: Path, voice: str | None = None, rate: int | None = None) -> float | None:
    """Offline TTS via pyttsx3 (SAPI5 on Windows, NSSpeech on macOS, eSpeak on Linux). Returns seconds."""
    try:
        import pyttsx3
    except ImportError:
        print("  ! pyttsx3 not installed; skipping TTS (pip install pyttsx3)", file=sys.stderr)
        return None
    eng = pyttsx3.init()
    if rate:
        eng.setProperty("rate", rate)
    if voice:
        for v in eng.getProperty("voices"):
            if voice.lower() in (v.name or "").lower() or voice.lower() in (v.id or "").lower():
                eng.setProperty("voice", v.id)
                break
    eng.save_to_file(text, str(out_wav))
    eng.runAndWait()
    eng.stop()
    return wav_seconds(out_wav)


def wav_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, FileNotFoundError, EOFError):
        return None


# --------------------------------------------------------------------------- shots
def shot_frames(shot: dict, W: int, H: int, fps: int, theme: g.Theme, base_dir: Path):
    """Yield RGB frames for one shot (before global fades/captions)."""
    kind = shot.get("type", "sim")
    n = max(1, int(round(float(shot["duration"]) * fps)))
    if kind == "title":
        for i in range(n):
            yield g.title_card(W, H, theme, i / fps, shot["duration"], shot.get("title", ""),
                               shot.get("subtitle", ""), shot.get("kicker", ""))
        return
    if kind in ("bullets", "text"):
        for i in range(n):
            yield g.bullets_card(W, H, theme, i / fps, shot["duration"], shot.get("title", ""),
                                 shot.get("bullets", []), shot.get("equation", ""))
        return
    if kind == "sim":
        view = SimView(shot, shot, W, H, fps, theme, base_dir, SCENE_LIBRARY)
        try:
            for i in range(n):
                yield view.frame(i, n)
        finally:
            view.close()
        return
    if kind == "compare":
        variants = shot["variants"]
        k = len(variants)
        cols = shot.get("columns", k)
        rows = math.ceil(k / cols)
        pw, ph = (W // cols) // 2 * 2, (H // rows) // 2 * 2
        views = [SimView(shot, v, pw, ph, fps, theme, base_dir, SCENE_LIBRARY) for v in variants]
        gap = max(2, W // 400)
        try:
            for i in range(n):
                canvas = np.zeros((H, W, 3), np.uint8)
                canvas[:] = g.hex_rgb(theme.bg)
                for j, v in enumerate(views):
                    r, c = divmod(j, cols)
                    fr = v.frame(i, n)
                    y0, x0 = r * ph, c * pw
                    canvas[y0:y0 + ph, x0:x0 + pw] = fr
                for c in range(1, cols):
                    canvas[:, c * pw - gap // 2: c * pw + gap // 2] = g.hex_rgb(theme.bg)
                for r in range(1, rows):
                    canvas[r * ph - gap // 2: r * ph + gap // 2, :] = g.hex_rgb(theme.bg)
                yield canvas
        finally:
            for v in views:
                v.close()
        return
    if kind == "image":
        img = Image.open(base_dir / shot["file"]).convert("RGB")
        img.thumbnail((W, H))
        bg = Image.fromarray(g.solid(W, H, theme))
        bg.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
        arr = np.asarray(bg)
        for i in range(n):
            yield arr
        return
    raise ValueError(f"Unknown shot type: {kind}")


def caption_events(shot: dict) -> list[tuple[float, float, str]]:
    """Normalise captions into (start, end, text) relative to shot start."""
    caps = shot.get("captions") or []
    if isinstance(caps, str):
        caps = [{"t": 0.3, "text": caps}]
    dur = float(shot["duration"])
    out = []
    for i, c in enumerate(caps):
        start = float(c.get("t", 0.3))
        end = float(c.get("until", caps[i + 1]["t"] - 0.05 if i + 1 < len(caps) else dur - 0.2))
        out.append((start, end, c["text"]))
    return out


def decorate(frame: np.ndarray, shot: dict, t: float, theme: g.Theme, caps, global_frac: float | None):
    dur = float(shot["duration"])
    head = shot.get("heading")
    if head or caps or global_frac is not None:
        cv = g.Canvas(frame)
        if head:
            g.heading(cv, theme, head, g.window_alpha(t, 0.0, dur, 0.5), shot.get("subheading", ""))
        for (s, e, text) in caps:
            a = g.window_alpha(t, s, e, 0.25)
            if a > 0:
                g.caption(cv, theme, text, a)
        if global_frac is not None:
            g.progress_bar(cv, theme, global_frac)
        frame = cv.result()
    fi, fo = float(shot.get("fade_in", 0.35)), float(shot.get("fade_out", 0.35))
    alpha = min(1.0, t / fi if fi > 0 else 1.0, (dur - t) / fo if fo > 0 else 1.0)
    return g.fade_to(frame, max(0.0, alpha), g.hex_rgb(theme.bg))


# --------------------------------------------------------------------------- outputs
def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def write_srt(path: Path, events):
    with open(path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(events, 1):
            f.write(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{text}\n\n")


def contact_sheet(images: list[np.ndarray], path: Path, cols: int = 4):
    if not images:
        return
    h, w = images[0].shape[:2]
    tw, th = 480, int(480 * h / w)
    rows = math.ceil(len(images) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
    for i, im in enumerate(images):
        sheet.paste(Image.fromarray(im).resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(path)


def mux_audio(video: Path, tracks: list[dict], total: float, out: Path):
    """tracks: [{file, start, volume, loop}] -> mixed AAC muxed with video."""
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video)]
    filters = []
    for k, tr in enumerate(tracks):
        if tr.get("loop"):
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", str(tr["file"])]
        ms = int(tr.get("start", 0) * 1000)
        filters.append(f"[{k + 1}:a]adelay={ms}|{ms},volume={tr.get('volume', 1.0)}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(tracks)))
    filters.append(f"{mix}amix=inputs={len(tracks)}:duration=longest:normalize=0[aout]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", str(out)]
    subprocess.run(cmd, check=True)


# --------------------------------------------------------------------------- main entry
def render(spec_path: Path, out: Path | None = None, preview: bool = False, only: list[int] | None = None,
           snapshots: bool = True, tts: bool = False) -> Path:
    spec_path = Path(spec_path).resolve()
    base_dir = spec_path.parent
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    W, H = spec.get("resolution", [1280, 720])
    fps = int(spec.get("fps", 30))
    if preview:
        W, H, fps = W // 2 // 2 * 2, H // 2 // 2 * 2, max(12, fps // 2)
    theme = g.Theme.from_dict(spec.get("theme"))
    out = Path(out) if out else (base_dir / spec.get("output", spec_path.stem + ".mp4"))
    if preview:
        out = out.with_name(out.stem + "_preview" + out.suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    shots = spec["shots"]
    if only:
        shots = [shots[i] for i in only]

    # Narration: generate/measure voice clips first so `duration: auto` can follow the voice.
    work = out.with_name(out.stem + "_build")
    work.mkdir(exist_ok=True)
    audio_tracks: list[dict] = []
    voice_cfg = spec.get("voice", {})
    for k, shot in enumerate(shots):
        clip, secs = None, None
        if shot.get("voiceover"):
            clip = base_dir / shot["voiceover"]
            secs = wav_seconds(clip)
        elif shot.get("say") and tts:
            clip = work / f"say_{k:02d}.wav"
            secs = synth_tts(shot["say"], clip, voice_cfg.get("voice"), voice_cfg.get("rate"))
            if secs is None:
                clip = None
        shot["_voice"] = (clip, secs)
        if shot.get("duration", "auto") == "auto":
            shot["duration"] = (secs + float(shot.get("pad", 1.0))) if secs else 5.0
        if shot.get("say") and not shot.get("captions") and spec.get("say_as_captions", True):
            shot["captions"] = [{"t": 0.3, "text": shot["say"]}]

    total = sum(float(s["duration"]) for s in shots)
    print(f"Rendering {len(shots)} shots, {total:.1f}s @ {W}x{H} {fps}fps -> {out}")
    silent = work / "video_silent.mp4"
    writer = imageio.get_writer(str(silent), fps=fps, codec="libx264", quality=None, bitrate=None,
                                pixelformat="yuv420p", macro_block_size=2,
                                ffmpeg_params=["-crf", str(spec.get("crf", 18)), "-preset", "medium"])
    srt_events, snaps = [], []
    t_global = 0.0
    show_progress = spec.get("progress_bar", True)
    for k, shot in enumerate(shots):
        dur = float(shot["duration"])
        n = max(1, int(round(dur * fps)))
        caps = caption_events(shot)
        srt_events += [(t_global + s, t_global + e, txt) for s, e, txt in caps]
        clip, _ = shot["_voice"]
        if clip:
            audio_tracks.append({"file": clip, "start": t_global + float(shot.get("voice_delay", 0.2)),
                                 "volume": voice_cfg.get("volume", 1.0)})
        print(f"  [{k + 1}/{len(shots)}] {shot.get('type', 'sim'):8s} {dur:5.1f}s  {shot.get('heading') or shot.get('title', '')}")
        for i, fr in enumerate(shot_frames(shot, W, H, fps, theme, base_dir)):
            t = i / fps
            frac = (t_global + t) / total if show_progress and shot.get("type", "sim") not in ("title",) else None
            fr = decorate(fr, shot, t, theme, caps, frac)
            writer.append_data(fr)
            if i == int(n * float(shot.get("snapshot_at", 0.6))):
                snaps.append(fr)
        t_global += dur
    writer.close()

    music = spec.get("music")
    if music:
        audio_tracks.insert(0, {"file": base_dir / music["file"], "start": 0, "volume": music.get("volume", 0.25),
                                "loop": music.get("loop", True)})
    if audio_tracks:
        mux_audio(silent, audio_tracks, total, out)
    else:
        shutil.copyfile(silent, out)
    write_srt(out.with_suffix(".srt"), srt_events)
    if snapshots:
        contact_sheet(snaps, out.with_name(out.stem + "_contact.png"))
    print(f"Done: {out}  (+ {out.with_suffix('.srt').name}, {out.stem}_contact.png)")
    return out
