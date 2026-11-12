"""2D graphics for explainer videos: fonts, title cards, captions, plots, callouts.

Everything works on numpy uint8 RGB frames (H, W, 3) and uses Pillow only, so it
runs anywhere MuJoCo runs.
"""
from __future__ import annotations

import functools
import math
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------- fonts
_FONT_CANDIDATES = {
    "regular": [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
    "bold": [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
    "mono": [
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ],
}


@functools.lru_cache(maxsize=None)
def font(kind: str, size: int, override: str | None = None) -> ImageFont.FreeTypeFont:
    paths = ([override] if override else []) + _FONT_CANDIDATES.get(kind, _FONT_CANDIDATES["regular"])
    for p in paths:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


# --------------------------------------------------------------------------- theme
def hex_rgb(h: str | tuple | list) -> tuple[int, int, int]:
    if isinstance(h, (tuple, list)):
        return tuple(int(c) for c in h[:3])
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class Theme:
    bg: str = "#0d1017"
    fg: str = "#f2f4f8"
    muted: str = "#9aa4b5"
    accent: str = "#4cc9f0"
    accent2: str = "#f72585"
    accent3: str = "#ffd166"
    panel: str = "#141a24"
    font_regular: str | None = None
    font_bold: str | None = None
    font_mono: str | None = None
    palette: list = field(default_factory=lambda: ["#4cc9f0", "#f72585", "#ffd166", "#06d6a0", "#b388ff"])

    @classmethod
    def from_dict(cls, d: dict | None) -> "Theme":
        t = cls()
        for k, v in (d or {}).items():
            if hasattr(t, k):
                setattr(t, k, v)
        return t

    def f(self, kind: str, size: int):
        return font(kind, int(size), {"regular": self.font_regular, "bold": self.font_bold,
                                      "mono": self.font_mono}.get(kind))

    def color(self, c, alpha: int = 255):
        if isinstance(c, int):
            c = self.palette[c % len(self.palette)]
        if isinstance(c, str) and hasattr(self, c) and c.startswith(("acc", "fg", "bg", "muted", "panel")):
            c = getattr(self, c)
        return (*hex_rgb(c), alpha)


# --------------------------------------------------------------------------- easing
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease(x: float, kind: str = "in_out") -> float:
    x = clamp01(x)
    if kind == "linear":
        return x
    if kind == "in":
        return x ** 3
    if kind == "out":
        return 1 - (1 - x) ** 3
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def window_alpha(t: float, start: float, end: float, fade: float = 0.3) -> float:
    """Opacity of an element visible in [start, end] with soft fades."""
    if t < start or t > end:
        return 0.0
    return min(1.0, (t - start) / max(fade, 1e-6), (end - t) / max(fade, 1e-6))


# --------------------------------------------------------------------------- helpers
def wrap(text: str, fnt, max_w: int) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        words, cur = para.split(), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if fnt.getlength(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


class Canvas:
    """RGBA overlay on top of a frame; call .result() to get the composited RGB array."""

    def __init__(self, frame: np.ndarray):
        self.base = Image.fromarray(frame).convert("RGBA")
        self.layer = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.layer)
        self.W, self.H = self.base.size

    def result(self) -> np.ndarray:
        return np.asarray(Image.alpha_composite(self.base, self.layer).convert("RGB"))


def solid(W: int, H: int, theme: Theme) -> np.ndarray:
    """Background with a subtle radial vignette."""
    bg = np.array(hex_rgb(theme.bg), dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W * 0.5) / W) ** 2 + ((yy - H * 0.42) / H) ** 2)
    glow = np.clip(1.0 - r * 1.6, 0, 1)[..., None]
    lift = np.array(hex_rgb(theme.panel), dtype=np.float32)
    img = bg * (1 - glow * 0.9) + lift * glow * 0.9
    return np.clip(img, 0, 255).astype(np.uint8)


def fade_to(frame: np.ndarray, alpha: float, color=(0, 0, 0)) -> np.ndarray:
    """alpha=1 -> frame unchanged, alpha=0 -> solid color."""
    if alpha >= 1:
        return frame
    c = np.array(color, dtype=np.float32)
    return (frame.astype(np.float32) * alpha + c * (1 - alpha)).astype(np.uint8)


# --------------------------------------------------------------------------- cards
def title_card(W, H, theme: Theme, t: float, dur: float, title: str, subtitle: str = "",
               kicker: str = "") -> np.ndarray:
    cv = Canvas(solid(W, H, theme))
    s = H / 720
    a_in = ease(t / 0.8, "out")
    rise = (1 - a_in) * 30 * s
    tf, sf, kf = theme.f("bold", 64 * s), theme.f("regular", 28 * s), theme.f("bold", 20 * s)
    lines = wrap(title, tf, int(W * 0.8))
    lh = tf.size * 1.15
    block_h = lh * len(lines) + (sf.size * 1.8 if subtitle else 0)
    y = H / 2 - block_h / 2 + rise
    if kicker:
        cv.draw.text((W / 2, y - kf.size * 2.2), kicker.upper(), font=kf, anchor="mm",
                     fill=theme.color(theme.accent, int(255 * a_in)))
    for ln in lines:
        cv.draw.text((W / 2, y + lh / 2), ln, font=tf, anchor="mm", fill=theme.color(theme.fg, int(255 * a_in)))
        y += lh
    bar = ease((t - 0.3) / 0.8, "out") * W * 0.12
    cv.draw.rounded_rectangle((W / 2 - bar, y + 8 * s, W / 2 + bar, y + 14 * s), radius=3 * s,
                              fill=theme.color(theme.accent))
    if subtitle:
        a2 = ease((t - 0.5) / 0.8, "out")
        cv.draw.text((W / 2, y + sf.size * 1.6), subtitle, font=sf, anchor="mm",
                     fill=theme.color(theme.muted, int(255 * a2)))
    return cv.result()


def bullets_card(W, H, theme: Theme, t: float, dur: float, heading: str, bullets: list[str],
                 equation: str = "") -> np.ndarray:
    cv = Canvas(solid(W, H, theme))
    s = H / 720
    hf, bf, ef = theme.f("bold", 46 * s), theme.f("regular", 30 * s), theme.f("mono", 34 * s)
    x0 = W * 0.12
    a = ease(t / 0.6, "out")
    cv.draw.rounded_rectangle((x0 - 24 * s, H * 0.16, x0 - 16 * s, H * 0.16 + hf.size * 1.1), radius=3,
                              fill=theme.color(theme.accent, int(255 * a)))
    cv.draw.text((x0, H * 0.16), heading, font=hf, fill=theme.color(theme.fg, int(255 * a)))
    y = H * 0.16 + hf.size * 2.0
    n = max(len(bullets), 1)
    reveal = max(0.5, min(1.2, (dur - 1.5) / n))
    for i, b in enumerate(bullets):
        ab = ease((t - 0.6 - i * reveal) / 0.5, "out")
        if ab <= 0:
            continue
        dx = (1 - ab) * 24 * s
        col = theme.palette[i % len(theme.palette)]
        cv.draw.ellipse((x0 + dx, y + bf.size * 0.35, x0 + dx + 12 * s, y + bf.size * 0.35 + 12 * s),
                        fill=theme.color(col, int(255 * ab)))
        for j, ln in enumerate(wrap(b, bf, int(W * 0.7))):
            cv.draw.text((x0 + 32 * s + dx, y), ln, font=bf, fill=theme.color(theme.fg, int(255 * ab)))
            y += bf.size * 1.3
        y += bf.size * 0.5
    if equation:
        ae = ease((t - 0.6 - n * reveal) / 0.6, "out")
        if ae > 0:
            box_w = ef.getlength(equation) + 60 * s
            ey = max(y + 20 * s, H * 0.72)
            cv.draw.rounded_rectangle((x0, ey, x0 + box_w, ey + ef.size * 2), radius=12 * s,
                                      fill=theme.color(theme.panel, int(230 * ae)),
                                      outline=theme.color(theme.accent, int(255 * ae)), width=max(1, int(2 * s)))
            cv.draw.text((x0 + 30 * s, ey + ef.size), equation, font=ef, anchor="lm",
                         fill=theme.color(theme.accent3, int(255 * ae)))
    return cv.result()


# --------------------------------------------------------------------------- overlays
def caption(cv: Canvas, theme: Theme, text: str, alpha: float):
    if alpha <= 0 or not text:
        return
    s = cv.H / 720
    fnt = theme.f("regular", 28 * s)
    lines = wrap(text, fnt, int(cv.W * 0.72))
    lh = fnt.size * 1.3
    box_w = max(fnt.getlength(ln) for ln in lines) + 48 * s
    box_h = lh * len(lines) + 26 * s
    x0, y1 = (cv.W - box_w) / 2, cv.H - 38 * s
    y0 = y1 - box_h
    cv.draw.rounded_rectangle((x0, y0, x0 + box_w, y1), radius=14 * s, fill=(8, 10, 14, int(190 * alpha)))
    cv.draw.rectangle((x0 + 14 * s, y1 - 4 * s, x0 + 14 * s + (box_w - 28 * s), y1 - 2 * s),
                      fill=theme.color(theme.accent, int(160 * alpha)))
    y = y0 + 13 * s
    for ln in lines:
        cv.draw.text((cv.W / 2, y + lh / 2), ln, font=fnt, anchor="mm", fill=theme.color(theme.fg, int(255 * alpha)))
        y += lh


def heading(cv: Canvas, theme: Theme, text: str, alpha: float, sub: str = ""):
    if alpha <= 0 or not text:
        return
    s = cv.H / 720
    hf, sf = theme.f("bold", 30 * s), theme.f("regular", 20 * s)
    x, y = 36 * s, 30 * s
    w = max(hf.getlength(text), sf.getlength(sub) if sub else 0) + 40 * s
    h = hf.size * 1.4 + (sf.size * 1.4 if sub else 0) + 12 * s
    cv.draw.rounded_rectangle((x, y, x + w, y + h), radius=10 * s, fill=(8, 10, 14, int(170 * alpha)))
    cv.draw.rectangle((x, y + 8 * s, x + 5 * s, y + h - 8 * s), fill=theme.color(theme.accent, int(255 * alpha)))
    cv.draw.text((x + 20 * s, y + 8 * s), text, font=hf, fill=theme.color(theme.fg, int(255 * alpha)))
    if sub:
        cv.draw.text((x + 20 * s, y + 8 * s + hf.size * 1.35), sub, font=sf,
                     fill=theme.color(theme.muted, int(255 * alpha)))


def label(cv: Canvas, theme: Theme, text: str, pos, alpha: float = 1.0, color=None, size: int = 22):
    """Small pill label. pos is (x, y) in pixels or one of top-left/top-right/bottom-left/bottom-right/top."""
    s = cv.H / 720
    fnt = theme.f("bold", size * s)
    w, h = fnt.getlength(text) + 28 * s, fnt.size * 1.6
    m = 30 * s
    anchors = {"top-left": (m, m), "top-right": (cv.W - w - m, m), "top": ((cv.W - w) / 2, m),
               "bottom-left": (m, cv.H - h - m), "bottom-right": (cv.W - w - m, cv.H - h - m)}
    x, y = anchors.get(pos, pos) if isinstance(pos, str) else pos
    col = theme.color(color if color is not None else theme.accent, int(255 * alpha))
    cv.draw.rounded_rectangle((x, y, x + w, y + h), radius=h / 2, fill=(8, 10, 14, int(180 * alpha)),
                              outline=col, width=max(1, int(2 * s)))
    cv.draw.text((x + w / 2, y + h / 2), text, font=fnt, anchor="mm", fill=theme.color(theme.fg, int(255 * alpha)))


def callout(cv: Canvas, theme: Theme, text: str, px: tuple[float, float], alpha: float, color=None,
            side: str = "auto"):
    """Dot on a projected 3D point with a leader line to a text label."""
    if alpha <= 0 or px is None:
        return
    s = cv.H / 720
    col = theme.color(color if color is not None else theme.accent3, int(255 * alpha))
    x, y = px
    r = 7 * s
    cv.draw.ellipse((x - r, y - r, x + r, y + r), outline=col, width=max(2, int(3 * s)))
    right = (x < cv.W * 0.6) if side == "auto" else side == "right"
    lx = x + (70 if right else -70) * s
    ly = y - 50 * s
    cv.draw.line((x + (r if right else -r) * 0.7, y - r * 0.7, lx, ly), fill=col, width=max(1, int(2 * s)))
    fnt = theme.f("bold", 22 * s)
    tw = fnt.getlength(text)
    tx = lx + 8 * s if right else lx - tw - 8 * s
    cv.draw.line((lx, ly, tx + (tw if not right else 0), ly), fill=col, width=max(1, int(2 * s)))
    cv.draw.text((tx, ly - 6 * s), text, font=fnt, anchor="lb", fill=theme.color(theme.fg, int(255 * alpha)))


def plot(cv: Canvas, theme: Theme, series: list[dict], box: tuple, title: str = "", window: int | None = None,
         ylim: tuple | None = None, alpha: float = 1.0):
    """Live line plot. series = [{label, values(list), color}]; box = (x0, y0, x1, y1) in pixels."""
    if alpha <= 0:
        return
    s = cv.H / 720
    x0, y0, x1, y1 = box
    cv.draw.rounded_rectangle(box, radius=12 * s, fill=(8, 10, 14, int(185 * alpha)),
                              outline=(255, 255, 255, int(30 * alpha)))
    tf, lf = theme.f("bold", 18 * s), theme.f("regular", 15 * s)
    if title:
        cv.draw.text((x0 + 14 * s, y0 + 10 * s), title, font=tf, fill=theme.color(theme.fg, int(255 * alpha)))
    px0, py0, px1, py1 = x0 + 14 * s, y0 + (38 if title else 14) * s, x1 - 14 * s, y1 - 30 * s
    vals = [np.asarray(sr["values"][-window:] if window else sr["values"], dtype=float) for sr in series]
    allv = np.concatenate([v for v in vals if len(v)]) if any(len(v) for v in vals) else np.array([0.0, 1.0])
    lo, hi = ylim if ylim else (float(np.nanmin(allv)), float(np.nanmax(allv)))
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    if lo < 0 < hi:
        zy = py1 - (0 - lo) / (hi - lo) * (py1 - py0)
        cv.draw.line((px0, zy, px1, zy), fill=(255, 255, 255, int(40 * alpha)), width=1)
    n_max = window or max((len(v) for v in vals), default=1)
    for i, (sr, v) in enumerate(zip(series, vals)):
        if len(v) < 2:
            continue
        xs = px0 + np.arange(len(v)) / max(n_max - 1, 1) * (px1 - px0)
        ys = py1 - (v - lo) / (hi - lo) * (py1 - py0)
        col = theme.color(sr.get("color", i), int(255 * alpha))
        cv.draw.line(list(zip(xs.tolist(), ys.tolist())), fill=col, width=max(2, int(3 * s)), joint="curve")
        cv.draw.ellipse((xs[-1] - 4 * s, ys[-1] - 4 * s, xs[-1] + 4 * s, ys[-1] + 4 * s), fill=col)
    lx = px0
    for i, sr in enumerate(series):
        col = theme.color(sr.get("color", i), int(255 * alpha))
        cv.draw.rectangle((lx, y1 - 20 * s, lx + 12 * s, y1 - 12 * s), fill=col)
        txt = sr.get("label", f"s{i}")
        cv.draw.text((lx + 18 * s, y1 - 24 * s), txt, font=lf, fill=theme.color(theme.muted, int(255 * alpha)))
        lx += lf.getlength(txt) + 40 * s


def progress_bar(cv: Canvas, theme: Theme, frac: float):
    s = cv.H / 720
    cv.draw.rectangle((0, cv.H - 4 * s, cv.W * clamp01(frac), cv.H), fill=theme.color(theme.accent, 200))


def project(point, gl_cam, fovy_deg: float, W: int, H: int):
    """Project a world point to pixel coords using an mjvGLCamera. Returns None if behind camera."""
    pos = np.asarray(gl_cam.pos)
    fwd = np.asarray(gl_cam.forward)
    up = np.asarray(gl_cam.up)
    right = np.cross(fwd, up)
    v = np.asarray(point) - pos
    z = float(v @ fwd)
    if z <= 1e-6:
        return None
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2)
    ndc_x = (v @ right) / z * f / (W / H)
    ndc_y = (v @ up) / z * f
    return ((ndc_x + 1) / 2 * W, (1 - ndc_y) / 2 * H)
