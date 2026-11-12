#!/usr/bin/env python3
"""Render a MuJoCo explainer video from a YAML storyboard.

Usage:
  python make_video.py storyboard.yaml                 # full quality
  python make_video.py storyboard.yaml --preview       # half-res, half-fps, fast iteration
  python make_video.py storyboard.yaml --shots 2,3     # render a subset (0-based indices)
  python make_video.py storyboard.yaml --tts           # synthesize `say:` lines offline (pyttsx3)

Outputs <output>.mp4, <output>.srt (captions) and <output>_contact.png (one frame per shot).
On headless Linux set MUJOCO_GL=egl (GPU) or MUJOCO_GL=osmesa (CPU) first.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mjexplainer import render  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--shots", type=str, help="comma-separated shot indices to render")
    ap.add_argument("--tts", action="store_true", help="generate narration for `say:` lines with pyttsx3")
    ap.add_argument("--no-contact", action="store_true")
    a = ap.parse_args()
    only = [int(x) for x in a.shots.split(",")] if a.shots else None
    render(a.spec, a.out, preview=a.preview, only=only, snapshots=not a.no_contact, tts=a.tts)


if __name__ == "__main__":
    main()
