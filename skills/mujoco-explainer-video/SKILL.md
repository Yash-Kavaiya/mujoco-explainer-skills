---
name: mujoco-explainer-video
description: Render polished physics/robotics explainer videos (MP4 + SRT captions) from MuJoCo simulations using a YAML storyboard - title cards, bullet slides, simulated shots with cinematic camera moves, motion trails, 3D-anchored callouts, live energy/state plots, side-by-side parameter comparisons, feedback controllers, scripted pushes, and optional offline narration. Use whenever the user wants a video, animation, GIF, clip or visual explanation of a physics concept, a robot, a controller, or a MuJoCo / MJCF model, mentions mujoco.org or google-deepmind/mujoco together with video, or asks to "show", "animate" or "explain with a simulation".
---

# MuJoCo Explainer Video

Turn a concept into a narrated-looking explainer video: **storyboard YAML → MuJoCo offscreen
render → PIL overlays → ffmpeg H.264**. One command, deterministic output, built for an agent
to iterate on by *looking at* a contact sheet.

```
skills/mujoco-explainer-video/
├── scripts/make_video.py          # CLI entry point
├── scripts/mjexplainer/           # pipeline.py · sim.py · graphics.py
├── assets/scenes/*.xml            # camera-ready scene library (referenced as @scenes/…)
├── assets/scenes/controllers/     # lqr_balance.py (generic LQR from mjd_transitionFD)
├── references/storyboard-spec.md  # every YAML key, with defaults
└── templates/storyboard.yaml      # copy-and-edit starter
```

## Setup (once)

```bash
pip install -r requirements.txt   # mujoco>=3.2 imageio imageio-ffmpeg pillow numpy pyyaml  (+ pyttsx3 for --tts)
```
Headless Linux / CI: `export MUJOCO_GL=egl` (NVIDIA) or `MUJOCO_GL=osmesa` (CPU). Windows/macOS need nothing.

## Workflow

1. **Plan the story.** If the user gave only a topic, use the `mujoco-physics-storyboarding`
   skill to pick 4–8 shots (hook → concept → sim → contrast → takeaway). Each sim shot should
   prove exactly one claim the caption states.
2. **Choose or build scenes.** Check `assets/scenes/` first (run
   `python ../mujoco-scene-authoring/scripts/validate_scene.py <xml>` to list its bodies/sites/joints).
   New models: follow the `mujoco-scene-authoring` skill, and keep the shared visual style.
3. **Write the storyboard.** Start from `templates/storyboard.yaml`, and check keys against
   `references/storyboard-spec.md`. Put it in its own folder with any custom XML and controllers;
   paths resolve relative to the YAML, and `@scenes/x.xml` resolves to the library.
4. **Preview fast.**
   ```bash
   python scripts/make_video.py path/to/storyboard.yaml --preview            # 1/2 res, 1/2 fps
   python scripts/make_video.py path/to/storyboard.yaml --preview --shots 3,4 # just the shots you changed
   ```
5. **Look at `<output>_contact.png`** (one frame per shot at 60% of its duration) with your image
   viewer/Read tool. Check: subject in frame and not tiny, callouts on screen, captions not covering
   the action, plot not hiding the subject, trails visible. Fix the camera/timing and re-render only those shots.
6. **Final render** without `--preview`. Deliver the `.mp4`, the `.srt` and a short summary of what each shot shows.
7. Optional narration: give shots `say:` text and render with `--tts` (offline pyttsx3), or supply
   recorded `voiceover:` WAVs. `duration: auto` fits a shot to its voice clip. Background music: top-level `music:`.

## Minimal storyboard

```yaml
title: Why pendulums conserve energy
output: out/pendulum.mp4
resolution: [1280, 720]
fps: 30
shots:
  - {type: title, kicker: "Physics", title: "Energy in a Pendulum", subtitle: "a MuJoCo explainer", duration: 3}
  - type: sim
    scene: "@scenes/pendulum.xml"
    duration: 6
    heading: "Energy sloshes, total stays put"
    camera: {lookat: [0, 0, 1.2], distance: [3.6, 3.0], azimuth: [80, 100], elevation: -10}
    trails: [{site: bob, length: 50}]
    plot: energy                         # preset: kinetic / potential / total
    captions:
      - {t: 0.4, text: "Kinetic and potential energy trade places..."}
      - {t: 3.2, text: "...but their sum is constant."}
```

## Shot types (details in references/storyboard-spec.md)

| type | use for | key fields |
|---|---|---|
| `title` | hook, chapter cards, outro | `kicker`, `title`, `subtitle` |
| `bullets` | definitions, recap, equations | `title`, `bullets[]`, `equation` |
| `sim` | one simulation | `scene`, `camera`, `init`, `speed`, `trails`, `callouts`, `plot`, `control`, `pushes`, `overrides`, `vis_flags` |
| `compare` | A/B parameter contrasts, side by side | `variants[]` each with `label`, `overrides`, `init`, `trails`… |
| `image` | a diagram or screenshot | `file` |

Every shot also takes `duration`, `heading`, `subheading`, `captions`, `fade_in`, `fade_out`, `say`, and `voiceover`.

## Craft rules that make videos look good

- **Move the camera slowly**: interpolate `azimuth` by 15–40° and `distance` by 10–20% per shot.
  Static shots are fine for comparisons; fast orbits cause nausea.
- **Trail the point that tells the story** (pendulum tip, end-effector, ball). Use 40–160 frames,
  and `width` 0.01–0.02 m for metre-scale scenes.
- **One idea per caption**, ≤ 14 words, with at most 2 captions per 6 s shot. Use the heading for the chapter
  ("2 · Chaos") and the subheading for the setup ("three starts, 0.001 rad apart").
- **Slow down fast events** with `speed: 0.25–0.5` and say so in the subheading ("half speed").
  Use `warmup:` to skip boring settling time.
- **Prove claims with data**: `plot: energy` for conservation; custom `series` exprs
  (`qpos[1]`, `ctrl[0]/100`, `body('ball').xpos[2]`) for anything else.
- **Contrast beats description**: `compare` with `overrides` (e.g. `opt.gravity`, `geom.ball.friction`)
  to show cause and effect with everything else held fixed.
- Keep 5–10 shots and 45–90 s for social; chapters of 2–4 minutes for tutorials.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mujoco.FatalError: gladLoadGL` / no display | set `MUJOCO_GL=egl` or `osmesa` |
| Subject tiny or off-screen | reduce `distance`, set `lookat` to the subject, or `track: body_name` |
| Callout missing | its point is behind the camera or off-frame; check the contact sheet and move the camera |
| Simulation explodes (NaN) | validate the scene; lower `opt.timestep` via `overrides`, add joint damping |
| Plot flat or invisible | set `ylim`; for energy, the scene needs non-zero masses (energy is enabled automatically) |
| Need a GIF | `ffmpeg -i out.mp4 -vf "fps=15,scale=640:-1:flags=lanczos" out.gif` |
