"""Render MuJoCo simulation shots: camera choreography, trails, controllers, pushes, data capture."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import mujoco
import numpy as np

from . import graphics as g


# --------------------------------------------------------------------------- model / state
def load_model(path: Path, W: int, H: int, energy: bool) -> mujoco.MjModel:
    model = mujoco.MjModel.from_xml_path(str(path))
    model.vis.global_.offwidth = max(int(model.vis.global_.offwidth), W)
    model.vis.global_.offheight = max(int(model.vis.global_.offheight), H)
    if energy:
        model.opt.enableflags |= mujoco.mjtEnableBit.mjENBL_ENERGY
    return model


def apply_overrides(model: mujoco.MjModel, overrides: dict | None):
    """overrides: {"opt.timestep": 0.001, "opt.gravity": [0,0,-1.62], "geom.box1.friction": [0.2, 0.005, 1e-4]}"""
    for key, val in (overrides or {}).items():
        parts = key.split(".")
        if parts[0] == "opt":
            setattr(model.opt, parts[1], val)
        elif len(parts) == 3:  # kind.name.attr, e.g. geom.ball.rgba / body.pole.mass / dof.0.damping
            kind, name, attr = parts
            key_id = int(name) if name.isdigit() else name
            # joint.<name>.<dof field> (damping, armature, frictionloss) -> the joint's first dof
            if kind == "joint" and hasattr(model, f"dof_{attr}"):
                kind, key_id = "dof", int(model.joint(key_id).dofadr[0])
            acc_fn = getattr(model, kind, None)
            if callable(acc_fn) and hasattr(acc_fn(key_id), attr):
                getattr(acc_fn(key_id), attr)[...] = val
            else:  # raw arrays without accessors, e.g. model.dof_damping[i]
                arr = getattr(model, f"{kind}_{attr}")
                if not isinstance(key_id, int):
                    raise ValueError(f"{kind} has no names; use an index in '{key}'")
                arr[key_id] = val
        else:
            raise ValueError(f"Unsupported override key: {key}")


def init_state(model, data, init: dict | None):
    init = init or {}
    if "keyframe" in init:
        mujoco.mj_resetDataKeyframe(model, data, model.keyframe(init["keyframe"]).id)
    elif model.nkey and init.get("use_first_keyframe", True):
        mujoco.mj_resetDataKeyframe(model, data, 0)
    if "qpos" in init:
        data.qpos[: len(init["qpos"])] = init["qpos"]
    if "qvel" in init:
        data.qvel[: len(init["qvel"])] = init["qvel"]
    for idx, delta in (init.get("qpos_offset") or {}).items():
        data.qpos[int(idx)] += delta
    for jname, val in (init.get("joints") or {}).items():
        j = model.joint(jname)
        data.qpos[j.qposadr[0]] = val
    mujoco.mj_forward(model, data)


# --------------------------------------------------------------------------- controllers
def make_controller(spec: dict | None, base_dir: Path, scene_dirs: list[Path] | None = None):
    """Return f(model, data) -> None that writes data.ctrl, or None.

    Built-ins: {type: sine, actuator, amplitude, frequency, bias}
               {type: constant, values: [...]}
               {type: python, file: ctrl.py, function: control, params: {...}}
    """
    if not spec:
        return None
    kind = spec.get("type", "python")
    if kind == "sine":
        a = spec.get("actuator", 0)
        amp, freq, bias = spec.get("amplitude", 1.0), spec.get("frequency", 0.5), spec.get("bias", 0.0)

        def ctrl(m, d):
            idx = m.actuator(a).id if isinstance(a, str) else a
            d.ctrl[idx] = bias + amp * math.sin(2 * math.pi * freq * d.time)
        return ctrl
    if kind == "constant":
        vals = np.asarray(spec["values"], dtype=float)

        def ctrl(m, d):
            d.ctrl[: len(vals)] = vals
        return ctrl
    if kind == "python":
        path = resolve_scene(spec["file"], base_dir, scene_dirs or []).resolve()
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(mod)
        params = spec.get("params", {})
        fn = getattr(mod, spec.get("function", "control"))
        if hasattr(mod, "setup"):  # setup(model, data, params) -> state, called once on first step
            box = {}

            def ctrl(m, d):
                if "state" not in box:
                    box["state"] = mod.setup(m, d, params)
                fn(m, d, box["state"])
            return ctrl
        return lambda m, d: fn(m, d, params)
    raise ValueError(f"Unknown controller type {kind}")


# --------------------------------------------------------------------------- camera
def _interp(v, p):
    """v is a scalar, [a, b], or [[vec], [vec]] -> interpolated value at progress p."""
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], (list, tuple)):
        a, b = np.asarray(v[0], float), np.asarray(v[1], float)
        return a + (b - a) * p
    if isinstance(v, (list, tuple)) and len(v) == 2 and not isinstance(v[0], (list, tuple)) and \
            all(isinstance(x, (int, float)) for x in v):
        return v[0] + (v[1] - v[0]) * p
    return np.asarray(v, float) if isinstance(v, (list, tuple)) else v


class CameraRig:
    """camera spec:
       {name: fixed_cam_name}
       {lookat: [x,y,z] | [[a],[b]], distance: d | [a,b], azimuth: .., elevation: .., ease: in_out,
        track: body_name, track_smooth: 0.1}
    """

    def __init__(self, model, data, spec: dict | None):
        self.model, self.spec = model, spec or {}
        self.cam = mujoco.MjvCamera()
        self.fixed = "name" in self.spec
        if self.fixed:
            self.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
            self.cam.fixedcamid = model.camera(self.spec["name"]).id
            self.fovy = float(model.cam_fovy[self.cam.fixedcamid])
            return
        self.fovy = float(model.vis.global_.fovy)
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        ext = float(model.stat.extent)
        self.defaults = {"lookat": list(model.stat.center), "distance": 1.6 * ext, "azimuth": 135.0,
                         "elevation": -20.0}
        self.track = self.spec.get("track")
        self.smooth = float(self.spec.get("track_smooth", 0.12))
        self._track_pos = None
        self.update(data, 0.0)

    def update(self, data, progress: float):
        if self.fixed:
            return
        p = g.ease(progress, self.spec.get("ease", "in_out"))
        for k in ("distance", "azimuth", "elevation"):
            setattr(self.cam, k, float(_interp(self.spec.get(k, self.defaults[k]), p)))
        lookat = np.asarray(_interp(self.spec.get("lookat", self.defaults["lookat"]), p), float)
        if self.track:
            target = data.body(self.track).xpos.copy() + np.asarray(self.spec.get("track_offset", [0, 0, 0]))
            self._track_pos = target if self._track_pos is None else \
                self._track_pos + (target - self._track_pos) * self.smooth
            lookat = self._track_pos
        self.cam.lookat[:] = lookat


# --------------------------------------------------------------------------- trails
class Trail:
    """Fading capsule trail behind a body or site."""

    def __init__(self, model, spec: dict, theme: g.Theme, idx: int):
        self.model = model
        self.kind = "site" if "site" in spec else "body"
        self.name = spec.get("site") or spec.get("body")
        self.length = int(spec.get("length", 90))
        self.width = float(spec.get("width", 0.01))
        rgb = g.hex_rgb(theme.palette[idx % len(theme.palette)] if "color" not in spec else
                        (spec["color"] if not isinstance(spec["color"], int) else theme.palette[spec["color"]]))
        self.rgb = np.array(rgb, float) / 255.0
        self.pts: list[np.ndarray] = []

    def record(self, data):
        p = (data.site(self.name).xpos if self.kind == "site" else data.body(self.name).xpos).copy()
        self.pts.append(p)
        if len(self.pts) > self.length:
            self.pts.pop(0)

    def draw(self, scene: mujoco.MjvScene):
        n = len(self.pts)
        for i in range(1, n):
            if scene.ngeom >= scene.maxgeom:
                return
            a, b = self.pts[i - 1], self.pts[i]
            if np.linalg.norm(b - a) < 1e-6:
                continue
            fade = i / n
            geom = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3), np.eye(3).flatten(),
                                np.array([*self.rgb, 0.15 + 0.85 * fade], np.float32))
            mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, self.width * (0.4 + 0.6 * fade), a, b)
            scene.ngeom += 1


# --------------------------------------------------------------------------- data series
def make_probe(expr: str):
    """Compile an expression evaluated against the sim each frame.

    Available names: qpos, qvel, qacc, ctrl, act, sensordata, time, energy, kinetic, potential,
    body(name) -> data.body accessor, joint(name), np, math.
    """
    code = compile(expr, "<probe>", "eval")

    def probe(model, data):
        env = {"qpos": data.qpos, "qvel": data.qvel, "qacc": data.qacc, "ctrl": data.ctrl, "act": data.act,
               "sensordata": data.sensordata, "time": data.time, "energy": data.energy,
               "potential": float(data.energy[0]), "kinetic": float(data.energy[1]),
               "body": data.body, "joint": data.joint, "site": data.site, "np": np, "math": math}
        return float(eval(code, {"__builtins__": {}}, env))  # noqa: S307 - spec authored by the user
    return probe


PRESET_PLOTS = {
    "energy": {"title": "Energy (J)", "series": [
        {"label": "kinetic", "expr": "kinetic"},
        {"label": "potential", "expr": "potential"},
        {"label": "total", "expr": "kinetic + potential"}]},
}


# --------------------------------------------------------------------------- the renderer
class SimView:
    """One simulated view (a full shot, or one panel of a compare shot)."""

    def __init__(self, shot: dict, variant: dict, W: int, H: int, fps: int, theme: g.Theme, base_dir: Path,
                 scene_dirs: list[Path]):
        self.W, self.H, self.fps, self.theme = W, H, fps, theme
        plot_spec = variant.get("plot", shot.get("plot"))
        if isinstance(plot_spec, str):
            plot_spec = PRESET_PLOTS[plot_spec]
        self.plot_spec = plot_spec
        uses_energy = bool(plot_spec) and any(
            k in s["expr"] for s in plot_spec["series"] for k in ("energy", "kinetic", "potential"))
        scene_path = resolve_scene(variant.get("scene", shot["scene"]), base_dir, scene_dirs)
        self.model = load_model(scene_path, W, H, uses_energy)
        apply_overrides(self.model, {**(shot.get("overrides") or {}), **(variant.get("overrides") or {})})
        self.data = mujoco.MjData(self.model)
        init_state(self.model, self.data, variant.get("init", shot.get("init")))
        self.ctrl = make_controller(variant.get("control", shot.get("control")), base_dir, scene_dirs)
        self.pushes = shot.get("pushes", [])
        self.renderer = mujoco.Renderer(self.model, H, W, max_geom=20000)
        self.opt = mujoco.MjvOption()
        for flag in shot.get("vis_flags", []):  # e.g. ["contactpoint", "contactforce", "com"]
            self.opt.flags[getattr(mujoco.mjtVisFlag, "mjVIS_" + flag.upper())] = 1
        if shot.get("transparent"):
            self.opt.flags[mujoco.mjtVisFlag.mjVIS_TRANSPARENT] = 1
        self.rig = CameraRig(self.model, self.data, variant.get("camera", shot.get("camera")))
        self.trails = [Trail(self.model, tspec, theme, i)
                       for i, tspec in enumerate(variant.get("trails", shot.get("trails", [])))]
        self.series = []
        if plot_spec:
            for sp in plot_spec["series"]:
                self.series.append({"label": sp["label"], "color": sp.get("color", len(self.series)),
                                    "probe": make_probe(sp["expr"]), "values": []})
        self.callouts = variant.get("callouts", shot.get("callouts", []))
        self.label = variant.get("label")
        self.label_color = variant.get("color")
        self.label_pos = variant.get("label_pos", "top-right")
        self.speed = float(shot.get("speed", 1.0))
        self.t0 = self.data.time
        warm = float(shot.get("warmup", 0.0))
        while self.data.time - self.t0 < warm:
            self._step()
        self.t0 = self.data.time

    def _step(self):
        d, m = self.data, self.model
        d.xfrc_applied[:] = 0
        t_rel = d.time - self.t0
        for p in self.pushes:
            if p["t"] <= t_rel < p["t"] + p.get("duration", 0.1):
                bid = m.body(p["body"]).id
                d.xfrc_applied[bid, :3] = p.get("force", [0, 0, 0])
                d.xfrc_applied[bid, 3:] = p.get("torque", [0, 0, 0])
        if self.ctrl:
            self.ctrl(m, d)
        mujoco.mj_step(m, d)

    def frame(self, i: int, n_frames: int) -> np.ndarray:
        target = self.t0 + i * self.speed / self.fps
        while self.data.time < target - 1e-9:
            self._step()
        for tr in self.trails:
            tr.record(self.data)
        for sr in self.series:
            sr["values"].append(sr["probe"](self.model, self.data))
        self.rig.update(self.data, i / max(n_frames - 1, 1))
        self.renderer.update_scene(self.data, camera=self.rig.cam, scene_option=self.opt)
        for tr in self.trails:
            tr.draw(self.renderer.scene)
        px = self.renderer.render()
        t = i / self.fps
        need_overlay = self.callouts or self.label or self.plot_spec
        if not need_overlay:
            return px
        cv = g.Canvas(px)
        for c in self.callouts:
            start, end = c.get("t", [0, 1e9]) if isinstance(c.get("t"), list) else (c.get("t", 0), 1e9)
            a = g.window_alpha(t, start, end)
            if a <= 0:
                continue
            pt = (self.data.site(c["site"]).xpos if "site" in c else self.data.body(c["body"]).xpos)
            pt = pt + np.asarray(c.get("offset", [0, 0, 0]))
            px2 = g.project(pt, self.renderer.scene.camera[0], self.rig.fovy, self.W, self.H)
            g.callout(cv, self.theme, c["text"], px2, a, c.get("color"))
        if self.label:
            g.label(cv, self.theme, self.label, self.label_pos, color=self.label_color)
        if self.plot_spec:
            s = self.H / 720
            box = self.plot_spec.get("box")
            if box is None:
                narrow = self.W < self.H * 1.2  # a panel of a compare shot
                w = min(360 * s, 0.55 * self.W)
                h = 200 * s
                top = 130 * s if narrow else 30 * s + (60 * s if self.label else 0)
                box = (self.W - w - 24 * s, top, self.W - 24 * s, top + h)
            else:
                box = tuple(b * (self.W if k % 2 == 0 else self.H) for k, b in enumerate(box))
            g.plot(cv, self.theme, self.series, box, self.plot_spec.get("title", ""),
                   window=self.plot_spec.get("window"), ylim=self.plot_spec.get("ylim"))
        return cv.result()

    def close(self):
        self.renderer.close()


def resolve_scene(name: str, base_dir: Path, scene_dirs: list[Path]) -> Path:
    if name.startswith("@scenes/"):
        name = name[len("@scenes/"):]
        for d in scene_dirs:
            if (d / name).exists():
                return d / name
        raise FileNotFoundError(f"Scene {name} not in library {scene_dirs}")
    p = (base_dir / name)
    if not p.exists():
        raise FileNotFoundError(p)
    return p
