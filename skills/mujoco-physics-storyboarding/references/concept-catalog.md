# Concept catalog: what to simulate to prove each idea

Scenes prefixed `@scenes/` ship with the `mujoco-explainer-video` skill. "Build" means write a small
MJCF scene with `mujoco-scene-authoring`.

## Mechanics

| Concept | Scene | Vary / show | Proof overlay | Pitfalls |
|---|---|---|---|---|
| Energy conservation | `@scenes/pendulum.xml` | — | `plot: energy` (total flat) | needs RK4 and no damping, which the scene already has |
| Damping / dissipation | `pendulum.xml` + `overrides: {dof.0.damping: 0.3}` | compare damping 0 vs 0.3 | `plot: energy`; total decays | label the units |
| Period ∝ 1/√g | `pendulum.xml` | compare `opt.gravity` Earth / Moon | trails; `plot` of `qpos[0]` | use the same init in both variants |
| Small-angle approximation | `pendulum.xml` | `init: {qpos: [0.2]}` vs `[2.5]` | plot `qpos[0]`, showing that the periods differ | caption: "big swings are slower" |
| Chaos | `@scenes/double_pendulum.xml` | — | long trail on `tip` | needs a high-energy start (keyframe 2.2, 2.0) |
| Sensitive dependence | `@scenes/double_pendulum_twins.xml` | already 1e-3 rad apart | three colored trails | show 8–10 s; divergence takes about 3 s |
| Coulomb friction | `@scenes/friction_ramp.xml` | per-box μ vs tan θ | callouts with μ | `speed: 0.5`, since ice leaves the ramp in ~1.4 s |
| Restitution | `@scenes/bounce.xml` | solref dampratio | trails; plot `body('ball_bouncy').xpos[2]` | MuJoCo contacts are soft, so call it "contact damping" |
| Projectile motion | build: free sphere with `init.qvel` | angle / speed | trail | needs a large floor and a wide camera |
| Gyroscopic precession | build: spinning free cylinder on a point | spin rate | trail on the top, `vis_flags: [com]` | needs a small timestep (≤0.0005) |
| Collisions and momentum | build: two free spheres on a frictionless plane | mass ratio | plot of each `qvel` | set `condim="1"` for frictionless |

## Control and robotics

| Concept | Scene | Vary / show | Proof overlay | Pitfalls |
|---|---|---|---|---|
| Unstable equilibrium | `@scenes/cartpole.xml`, no control | — | callout "falls" | start at a small angle (keyframe 0.12) |
| Feedback / LQR | `cartpole.xml` + `controllers/lqr_balance.py` | `pushes` | plot of the angle and `ctrl[0]` | keep pushes ≤ 8 N·0.1 s |
| Controller tuning | `cartpole.xml` compare | `params: {r: 0.01}` vs `{r: 1}` | plot of the angle | aggressive vs gentle, both should be stable |
| "Catching" a fall | `cartpole.xml` + `enable_after: 1.0` | — | callout at the switch-on time | the angle must stay in the linear region |
| PD position control | build: arm with a `position` actuator | `kp` | plot of target vs actual | add `armature` for stability |
| Inverse kinematics | Menagerie arm + a python controller using `mj_jac` | target path | trail on the end-effector site | damped least squares, λ≈0.05 |
| Legged locomotion | Menagerie quadruped + a policy/controller | gait | track the camera on the trunk | needs a trained policy, so set expectations |

## Simulation internals (for MuJoCo-focused videos)

| Concept | How to show |
|---|---|
| Contact points and forces | `vis_flags: [contactpoint, contactforce]`, `transparent: true` on a pile of boxes |
| Soft contacts / solref | `compare` the same drop with `solref` 0.02 vs 0.005 (penetration depth) |
| Integrators | `compare` pendulum with `overrides: {opt.timestep: 0.04}` and `opt.integrator: 0` (semi-implicit Euler) vs `1` (RK4); plot **only** total energy with a tight `ylim` (e.g. [13.2, 14.4]). Euler wobbles about ±3%, RK4 stays flat. MuJoCo's Euler is semi-implicit, so it wobbles rather than blowing up; say so |
| Timestep stability | compare timestep 0.001 vs 0.02 on the bounce scene |
| Determinism | two identical variants, so the trails overlap perfectly |
| Speed | caption the real-time factor; MuJoCo runs many times faster than real time |

## Hooks that work
- "Same start, three futures." (twins)
- "What keeps this from falling?" (cartpole falling, then caught by LQR)
- "Which box slides?" Freeze the ramp on the title (`warmup: 0`) and ask the viewer to guess.
- "Energy can't be created... so where does it go?" (damping)
