# MJCF cheatsheet for explainer scenes

## Skeleton
```xml
<mujoco model="name">
  <compiler angle="degree"/>                 <!-- default; euler/axisangle/range in degrees -->
  <option timestep="0.001" integrator="RK4" gravity="0 0 -9.81"/>
  <visual>…</visual>  <asset>…</asset>        <!-- copy from assets/template.xml -->
  <default> <geom rgba="…"/> </default>
  <worldbody>
    <light …/> <geom type="plane" …/> <camera name="front" …/>
    <body name="b" pos="x y z" euler="…">
      <joint name="j" type="hinge|slide|ball|free" axis="0 1 0" damping="0" range="-90 90"/>
      <freejoint/>                              <!-- shorthand for a floating body -->
      <geom type="box|sphere|capsule|cylinder|ellipsoid|mesh" size="…" fromto="…" mass="…" material="…"/>
      <site name="tip" pos="…"/>
      <inertial pos="0 0 0" mass="1" diaginertia="…"/>   <!-- optional, otherwise computed from geoms -->
    </body>
  </worldbody>
  <actuator> <motor joint="j" gear="1" ctrlrange="-1 1"/> </actuator>
  <sensor> <jointpos joint="j"/> <framepos objtype="site" objname="tip"/> </sensor>
  <keyframe> <key name="start" qpos="…" qvel="…"/> </keyframe>
</mujoco>
```

## Geom sizes
| type | size | notes |
|---|---|---|
| sphere | r | |
| capsule / cylinder | r [half-length] | or use `fromto="x1 y1 z1 x2 y2 z2"` with just `r` |
| box | hx hy hz | half-extents |
| ellipsoid | rx ry rz | |
| plane | hx hy spacing | `0 0 …` = infinite (rendered 2× extent) |

## qpos layout
- hinge/slide: 1 value; ball: 4 (quaternion w x y z); free: 7 (xyz + quaternion).
- `qvel` has 6 per free joint and 3 per ball joint. The validator prints `nq`/`nv`.
- A free body's qpos is absolute in world coordinates. Its `pos` attribute sets the default (qpos0).

## Actuators
| element | control means | typical use |
|---|---|---|
| `motor` | force/torque = gear·ctrl | torque control, LQR |
| `position kp=…` | PD to the target ctrl | servo joints, robot arms |
| `velocity kv=…` | velocity target | wheels, conveyors |
| `general` | anything (dyn/gain/bias) | muscles, custom |

## Contact parameters
- `friction="slide torsion roll"`, default `1 0.005 0.0001`. Pairs take the element-wise **max**.
- `solref="timeconst dampratio"`, default `0.02 1`. Smaller timeconst = stiffer (keep it ≥ 2·timestep).
- `solimp="dmin dmax width"`, default `0.9 0.95 0.001`. Higher values = harder contact.
- `condim`: 1 frictionless, 3 regular, 4 adds torsion, 6 adds rolling.
- `priority="1"`: that geom's solref/friction are used for the pair.
- `margin`/`gap`: activate contacts early (soft "magnetic" look). Avoid them for explainers.

## Visual knobs
- `<visual><global fovy="40" offwidth="1920" offheight="1080"/>`: the renderer needs off-screen buffers ≥ video size
  (the pipeline raises them automatically).
- `<quality shadowsize="4096" offsamples="8"/>` gives crisp shadows and AA.
- `<headlight ambient diffuse/>` sets the camera-attached light. Turn it down if the scene looks flat.
- Material `reflectance` (0–0.3) makes mirror floors; `emission` makes glowing parts.
- Camera: `<camera name="c" pos="…" xyaxes="x_axis y_axis"/>` or `mode="targetbody" target="b"`
  for tracking cameras defined in XML.

## Common fixes
| Problem | Fix |
|---|---|
| Explodes / NaN | lower timestep; add `damping`/`armature`; check that masses are > 0 and not wildly mismatched (>1:1000) |
| Objects jitter at rest | `cone="elliptic" impratio="10"`, `noslip_iterations="3"` in option |
| Sinks into the floor | stiffer `solref="0.005 1"`, smaller timestep |
| Energy drifts in an ideal system | RK4 + smaller timestep; make sure no joint has damping or frictionloss |
| Weird shading/black model | add a `<light>`; check `material` names; raise the headlight ambient |
| Mesh too big | meshes are in file units; set `<mesh scale="0.001 0.001 0.001"/>` for mm |

## Python API essentials
```python
m = mujoco.MjModel.from_xml_path("scene.xml"); d = mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m, d, m.keyframe("start").id)
mujoco.mj_step(m, d)                     # advance by m.opt.timestep
d.body("tip").xpos, d.site("tip").xpos, d.joint("j1").qpos, d.sensordata
m.geom("ball").friction[:] = [0.2, 0.005, 1e-4]   # edit parameters at runtime
A, B = …; mujoco.mjd_transitionFD(m, d, 1e-6, True, A, B, None, None)  # linearise
r = mujoco.Renderer(m, 720, 1280); r.update_scene(d, camera="front"); rgb = r.render()
```
