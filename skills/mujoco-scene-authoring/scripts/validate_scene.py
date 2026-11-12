#!/usr/bin/env python3
"""Validate an MJCF scene for explainer-video use and render a 2x2 preview sheet.

Checks: compiles, lists named bodies/joints/sites/cameras/actuators/keyframes (what a storyboard can
reference), simulates N seconds checking for NaN / solver warnings / deep penetration / energy drift,
and renders a preview PNG (fixed cameras + three orbit angles) so you can *look* at the result.

Usage:
  python validate_scene.py scene.xml [--seconds 5] [--keyframe start] [--out preview.png] [--size 640x360]
Exit code 1 if the scene is unstable.  Headless Linux: MUJOCO_GL=egl or osmesa.
"""
import argparse
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw


def names(model, kind, count):
    return [getattr(model, kind)(i).name or f"<{i}>" for i in range(count)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", type=Path)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--keyframe", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--size", default="640x360")
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.split("x"))

    try:
        model = mujoco.MjModel.from_xml_path(str(a.scene))
    except Exception as e:  # noqa: BLE001
        print(f"COMPILE ERROR: {e}")
        sys.exit(1)
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, W)
    model.vis.global_.offheight = max(model.vis.global_.offheight, H)
    model.opt.enableflags |= mujoco.mjtEnableBit.mjENBL_ENERGY
    data = mujoco.MjData(model)
    if a.keyframe:
        mujoco.mj_resetDataKeyframe(model, data, model.keyframe(a.keyframe).id)
    elif model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)

    print(f"Model '{a.scene.name}': nq={model.nq} nv={model.nv} nu={model.nu} nbody={model.nbody} "
          f"ngeom={model.ngeom} timestep={model.opt.timestep} integrator={mujoco.mjtIntegrator(model.opt.integrator).name}")
    print(f"  extent={model.stat.extent:.2f}  center={np.round(model.stat.center, 2).tolist()}")
    for label, kind, n in [("bodies", "body", model.nbody), ("joints", "joint", model.njnt),
                           ("sites", "site", model.nsite), ("cameras", "camera", model.ncam),
                           ("actuators", "actuator", model.nu), ("sensors", "sensor", model.nsensor),
                           ("keyframes", "keyframe", model.nkey)]:
        if n:
            print(f"  {label:9s}: {', '.join(names(model, kind, n))}")

    e0 = float(data.energy.sum())
    max_pen, steps, ok = 0.0, int(a.seconds / model.opt.timestep), True
    for _ in range(steps):
        mujoco.mj_step(model, data)
        if data.ncon:
            max_pen = max(max_pen, float(-min(c.dist for c in data.contact[: data.ncon])))
        if not np.all(np.isfinite(data.qpos)):
            print(f"  UNSTABLE: NaN in qpos at t={data.time:.3f}s -> lower timestep, add damping, check masses")
            ok = False
            break
    warns = [(mujoco.mjtWarning(i).name, w.number) for i, w in enumerate(data.warning) if w.number]
    if warns:
        print(f"  WARNINGS: {warns}")
        ok = ok and not any(n in ("mjWARN_BADQACC", "mjWARN_BADQPOS", "mjWARN_BADQVEL") for n, _ in warns)
    e1 = float(data.energy.sum())
    drift = (e1 - e0) / (abs(e0) + 1e-9)
    print(f"  simulated {data.time:.2f}s  max_penetration={max_pen * 1000:.1f}mm  "
          f"energy {e0:.3f} -> {e1:.3f} J (drift {drift * 100:+.1f}%)  -> {'OK' if ok else 'FAIL'}")
    if max_pen > 0.01:
        print("  hint: penetration >1cm looks bad on camera; lower timestep or stiffen solref (e.g. 0.005 1)")

    # ---- preview sheet (rendered from the initial state)
    mujoco.mj_resetData(model, data)
    if a.keyframe or model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, model.keyframe(a.keyframe).id if a.keyframe else 0)
    mujoco.mj_forward(model, data)
    r = mujoco.Renderer(model, H, W)
    views = []
    for c in range(min(model.ncam, 1)):
        r.update_scene(data, camera=c)
        views.append((f"camera '{model.camera(c).name}'", r.render()))
    for az, el in [(90, -12), (135, -25), (45, -45)][: 4 - len(views)]:
        cam = mujoco.MjvCamera()
        cam.lookat[:] = model.stat.center
        cam.distance, cam.azimuth, cam.elevation = 2.2 * model.stat.extent, az, el
        r.update_scene(data, camera=cam)
        views.append((f"free az={az} el={el}", r.render()))
    r.close()
    sheet = Image.new("RGB", (2 * W, 2 * H))
    for i, (lbl, img) in enumerate(views):
        im = Image.fromarray(img)
        ImageDraw.Draw(im).text((10, 10), lbl, fill=(255, 255, 255))
        sheet.paste(im, ((i % 2) * W, (i // 2) * H))
    out = a.out or a.scene.with_name(a.scene.stem + "_preview.png")
    sheet.save(out)
    print(f"  preview -> {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
