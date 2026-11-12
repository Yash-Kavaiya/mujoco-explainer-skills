# Storyboard YAML reference

Paths are relative to the YAML file. `@scenes/<file>` resolves to `assets/scenes/` in this skill.

## Top level

| key | default | meaning |
|---|---|---|
| `title` | – | for humans only |
| `output` | `<yaml stem>.mp4` | output path (also writes `.srt` and `_contact.png` next to it) |
| `resolution` | `[1280, 720]` | `[W, H]`; use 1920x1080 for finals and 1080x1920 for shorts/reels |
| `fps` | `30` | 60 works for very fast motion |
| `crf` | `18` | H.264 quality (lower is better, 16–23 is sensible) |
| `progress_bar` | `true` | thin accent bar along the bottom |
| `theme` | dark | `bg fg muted accent accent2 accent3 panel palette[] font_regular font_bold font_mono` |
| `music` | – | `{file, volume: 0.25, loop: true}` |
| `voice` | – | TTS options `{voice: "Zira", rate: 175, volume: 1.0}` |
| `say_as_captions` | `true` | shots with `say:` and no `captions` show the said text as a caption |
| `shots` | – | list of shots, rendered in order |

Theme colors accept `"#rrggbb"`. Wherever a `color` is accepted you may pass an **int**, which
indexes `theme.palette`: 0 cyan, 1 pink, 2 gold, 3 mint, 4 violet.

## Common shot keys

| key | default | meaning |
|---|---|---|
| `type` | `sim` | `title` · `bullets` · `sim` · `compare` · `image` |
| `duration` | – | seconds, or `auto` (voice clip length + `pad`, default 1.0) |
| `heading` / `subheading` | – | top-left chapter label |
| `captions` | – | a string, or a list of `{t, text, until?}`; `until` defaults to the next caption's `t` |
| `fade_in` / `fade_out` | `0.35` | seconds of fade to/from the background |
| `say` | – | narration text (used with `--tts`) |
| `voiceover` | – | WAV file for this shot; starts at shot start + `voice_delay` (0.2 s) |
| `snapshot_at` | `0.6` | fraction of the shot captured in the contact sheet |

## `title`
`kicker` (small caps above), `title`, `subtitle`.

## `bullets`
`title`, `bullets: [..]` (revealed one by one), `equation` (monospace, shown last in a box; plain
text or Unicode such as `τ = J^T f`).

## `sim`

| key | meaning |
|---|---|
| `scene` | MJCF path or `@scenes/name.xml` |
| `init` | `{keyframe: name}`, `{qpos: [...], qvel: [...]}`, `{joints: {j1: 0.3}}`, `{qpos_offset: {0: 0.001}}`; the first keyframe is used by default |
| `speed` | sim seconds per video second (0.5 = half-speed slow motion) |
| `warmup` | sim seconds to run before the first frame |
| `overrides` | model edits: `opt.timestep`, `opt.gravity`, `geom.<name>.friction`, `body.<name>.mass`, `dof.<i>.damping`, `actuator.<name>.gear`… |
| `camera` | see below |
| `trails` | list of `{site\|body, length: 90 frames, width: 0.01 m, color}` |
| `callouts` | list of `{body\|site, text, t: [start, end], offset: [x,y,z], color}`: a dot, a leader line and a label that follow the 3D point |
| `plot` | `energy` (preset), or `{title, series: [{label, expr, color}], ylim: [lo, hi], window: N frames, box: [x0,y0,x1,y1] as fractions}` |
| `control` | `{type: sine, actuator, amplitude, frequency, bias}` · `{type: constant, values}` · `{type: python, file, function: control, params}` |
| `pushes` | list of `{t, body, force: [fx,fy,fz], torque: [..], duration: 0.1}` external wrenches (seconds relative to shot start) |
| `vis_flags` | MuJoCo viz flags, e.g. `[contactpoint, contactforce, com, inertia, jointaxis, actuator]` |
| `transparent` | `true` makes bodies see-through (pairs well with `contactforce`) |

### Camera

```yaml
camera: {name: front}                       # a <camera> defined in the XML
camera:                                     # free camera; any value may be [start, end]
  lookat: [0, 0, 1]                         # or [[0,0,1], [0.5,0,1]]
  distance: [3.5, 2.8]
  azimuth: [70, 110]                        # degrees; 90 looks along +y (the x-z plane faces you)
  elevation: -12                            # negative looks down
  ease: in_out                              # in_out | in | out | linear
  track: cart                               # lookat follows this body (smoothed)
  track_smooth: 0.12
  track_offset: [0, 0, 0.3]
```
With no camera, the shot uses `lookat = model.stat.center`, `distance = 1.6 × extent`,
`azimuth 135`, `elevation −20`.

### Probe expressions (plot series)
These are evaluated each frame with these names in scope: `qpos qvel qacc ctrl act sensordata time energy
kinetic potential body(name) joint(name) site(name) np math`. Examples:
`qpos[0]`, `body('ball').xpos[2]`, `np.linalg.norm(qvel)`, `kinetic + potential`, `sensordata[3]`.

### Python controllers
```python
def setup(model, data, params):      # optional, runs once on the first step
    return {"gain": params.get("gain", 10)}

def control(model, data, state):     # every physics step; write data.ctrl
    data.ctrl[0] = -state["gain"] * data.qpos[0]
```
`@scenes/controllers/lqr_balance.py` is a generic LQR stabiliser (params: `qpos0`, `q_angle`,
`q_default`, `r`, `enable_after`). Turning it on late (`enable_after: 1.5`) makes a nice
"falling → caught" beat.

## `compare`
Same keys as `sim`, plus `variants: [...]` and `columns` (default: all in one row). Each variant can
override `scene`, `init`, `overrides`, `control`, `camera`, `trails`, `callouts`, `plot`, and adds
`label` (keep ≤ 12 characters so it clears the heading), `color` and `label_pos` (default `top-right`). All variants share `duration`, `speed`, `captions` and `heading`.

## `image`
`file`: a PNG/JPG fitted onto the themed background.

## CLI

```
python scripts/make_video.py spec.yaml [-o out.mp4] [--preview] [--shots 0,3] [--tts] [--no-contact]
```
