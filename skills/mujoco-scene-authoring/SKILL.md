---
name: mujoco-scene-authoring
description: Write and debug MuJoCo MJCF (XML) models that look great on camera and simulate stably - pendulums, linkages, robots, contact/friction demos, actuated mechanisms - using a shared camera-ready visual style (skybox, reflective grid floor, shadows, palette materials, named cameras/sites). Includes a validator that lists referenceable names, checks stability, penetration and energy drift, and renders a 2x2 preview sheet. Use when creating or editing an MJCF/XML scene, importing a robot from MuJoCo Menagerie, choosing solref/solimp/friction/timestep/integrator, or when a simulation explodes, jitters or looks wrong.
---

# MuJoCo Scene Authoring (camera-ready MJCF)

The goal is a model that is **physically honest** (it demonstrates the concept for the right reason)
and **telegenic** (high contrast, readable at 720p, nothing important hidden).

## Workflow

1. Start from `assets/template.xml`, which has the shared look (skybox, grid floor, key and fill
   lights, palette materials `cyan pink gold mint violet steel dark`, and a `front` camera).
2. Build the mechanism. Name everything a storyboard will reference: bodies, joints, **sites at
   points of interest** (tips, end-effectors) and actuators. Add a `<keyframe name="start">` for the
   interesting initial state.
3. Validate and look at it:
   ```bash
   python scripts/validate_scene.py my_scene.xml --seconds 5        # prints names, stability, drift
   ```
   Open the generated `my_scene_preview.png` and fix anything that is too small, too dark,
   clipping the floor, or intersecting.
4. Iterate until you get `OK`. Then reference it from a storyboard (`scene: my_scene.xml`).

## Design rules

**Scale and framing**
- Work in metres and kilograms with real-world sizes, so gravity reads correctly.
- Keep the action within roughly a 3 m cube around the origin, above the floor (z > 0).
- Put the camera so the subject fills 40–70% of frame height. In `front` cameras, `xyaxes="1 0 0 0 0.1 1"`
  looks along +y with a slight downward tilt.

**Looks**
- Use contrasting palette materials for parts that must be told apart; use `dark`/`steel` for scaffolding.
- Thin parts need a radius of at least 0.012 m or they shimmer at 720p.
- Decorative/scaffold geoms: `contype="0" conaffinity="0"` so they never collide.
- `offsamples="8"` (anti-aliasing) and `shadowsize="4096"` are in the template; keep them.

**Physics accuracy**
- Energy demos: `integrator="RK4"`, small `timestep` (0.0005–0.001), and no damping. The validator should
  report drift under 0.1%.
- Contact demos: `timestep ≤ 0.001`. Restitution is controlled by `solref="timeconst dampratio"`
  (dampratio < 1 bounces). Use `priority="1"` on the geom whose params should win the pair.
- Friction: MuJoCo combines the **max** of the two geoms' friction (unless `priority` is set). Make
  the surface low-friction to let each object's value decide. Use `cone="elliptic" impratio="10"` to reduce creep.
- Penetration over 1 cm is visible on camera; lower timestep or use `solref="0.005 1"`.
- Use `limited="true" range=…` on slide joints that must not run away.
- Use free bodies inside a tilted `<frame euler="…">` to place objects on slopes easily.

**Robots**
- Prefer MuJoCo Menagerie models (github.com/google-deepmind/mujoco_menagerie). Copy the robot folder
  next to your scene and `<include file="robot/robot.xml"/>`, or load it directly and add the
  floor/lights/skybox from the template into a wrapper scene.

## Cheatsheet

See `references/mjcf-cheatsheet.md` for elements, attributes, actuator types, sensors and common
fixes. The official reference is https://mujoco.readthedocs.io/en/stable/XMLreference.html
