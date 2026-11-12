---
name: mujoco-physics-storyboarding
description: Plan the narrative of a physics, robotics or control explainer video before rendering it with MuJoCo - turn a topic, paper, lecture note or question into a shot list (hook, setup, demonstration, contrast, takeaway), pick the simulation that proves each claim, write tight captions/narration, and map them to the mujoco-explainer-video storyboard YAML. Use when the user gives a topic ("explain chaos", "show how LQR works", "video on friction for students") rather than a ready storyboard, or asks for a script, outline, shot list or narration for a simulation video.
---

# Physics Storyboarding for MuJoCo Explainers

A good explainer **makes one claim per shot and then proves it with the simulation on screen**.
This skill produces a storyboard YAML for `mujoco-explainer-video`.

## Process

1. **Audience and length.** Decide the audience (curious public, students, engineers) and the format: 30–60 s
   short (5–7 shots), 1–3 min explainer (8–14 shots), or chapters of a lecture. Default to a
   60–90 s explainer for a general audience if the user doesn't say.
2. **One-sentence takeaway.** Write it first, for example "Deterministic does not mean predictable". Every
   shot must serve it.
3. **Find the visual proof.** Look the concept up in `references/concept-catalog.md`. It gives the scene,
   the parameter to vary, the overlay that proves it, and pitfalls. Prefer existing
   `@scenes/…`. If a concept needs a new model, write it with `mujoco-scene-authoring`.
4. **Shot list with the arc below.** Write it as a table first (shot · claim · visual · caption)
   and then convert it to YAML.
5. **Write captions/narration** following the writing rules below. Add `say:` lines if narration is wanted.
6. **Render a preview, look at the contact sheet, and revise.** Typical fixes are reframing, cutting a shot that
   doesn't prove anything, and slowing down fast events.

## The arc

| beat | shot type | job | duration |
|---|---|---|---|
| Hook | `title` or a striking `sim` | pose a question or show the surprise | 3–5 s |
| Setup | `bullets` | name the idea and give the one equation if any | 5–8 s |
| Demonstration | `sim` + overlay | show the phenomenon and prove it with data (plot/trail/callout) | 6–10 s each |
| Contrast | `compare` | change ONE parameter and keep everything else fixed | 6–8 s |
| Twist / application | `sim` with control or a robot | where it matters in the real world | 6–10 s |
| Takeaway | `title` | the sentence from step 2 and a link | 3–4 s |

## Writing rules

- **Caption = claim, not description.** "Total energy stays flat" beats "The graph shows lines".
- ≤ 14 words per caption, ≤ 2 captions per shot; the second caption delivers the payoff.
- Use the viewer's words first and the jargon second: "tiny differences explode (chaos)".
- Number chapters in headings ("2 · Chaos"). Use subheadings for experimental conditions
  ("three starts, 0.001 rad apart", "half speed").
- Be honest about the simulation: say "simulated" and mention slow motion. Don't claim realism
  that the contact model doesn't provide (MuJoCo contacts are soft; restitution is approximate).
- Narration (`say:`) runs at about 2.5 words/s. A 6 s shot fits about 13 words. Use `duration: auto` to fit.

## Output

Write the storyboard YAML (see the `mujoco-explainer-video` skill's `references/storyboard-spec.md`)
into its own folder, and render it with that skill. Also hand the user the shot table so they can edit it.
