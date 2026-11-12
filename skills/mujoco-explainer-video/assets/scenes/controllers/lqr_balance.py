"""LQR stabiliser for any model with an upright equilibrium at qpos = qpos0 (e.g. cartpole.xml).

Linearises the dynamics with MuJoCo's finite-difference derivatives (mjd_transitionFD), solves the
discrete Riccati equation by iteration, and applies u = -K (x - x0).

Storyboard usage:
  control: {type: python, file: "@scenes/controllers/lqr_balance.py", params: {q_angle: 50, r: 0.1}}
"""
import mujoco
import numpy as np


def setup(model, data, params):
    lin = mujoco.MjData(model)
    qpos0 = np.asarray(params.get("qpos0", np.zeros(model.nq)), float)
    lin.qpos[:] = qpos0
    lin.qvel[:] = 0
    lin.ctrl[:] = 0
    mujoco.mj_forward(model, lin)
    nx, nu = 2 * model.nv + model.na, model.nu
    A, B = np.zeros((nx, nx)), np.zeros((nx, nu))
    mujoco.mjd_transitionFD(model, lin, 1e-6, True, A, B, None, None)

    q = np.ones(nx) * float(params.get("q_default", 1.0))
    for j in range(model.njnt):  # heavier weight on hinge angles (the thing we balance)
        if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            q[model.jnt_dofadr[j]] = float(params.get("q_angle", 50.0))
    Q, R = np.diag(q), np.eye(nu) * float(params.get("r", 0.1))
    P = Q.copy()
    for _ in range(20000):
        K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
        P_next = Q + A.T @ P @ (A - B @ K)
        if np.max(np.abs(P_next - P)) < 1e-9:
            P = P_next
            break
        P = P_next
    K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
    return {"K": K, "qpos0": qpos0, "model": model,
            "enable_after": float(params.get("enable_after", 0.0))}


def control(model, data, state):
    if data.time < state["enable_after"]:
        data.ctrl[:] = 0
        return
    dq = np.zeros(model.nv)
    mujoco.mj_differentiatePos(model, dq, 1.0, state["qpos0"], data.qpos)
    x = np.concatenate([dq, data.qvel, data.act])
    u = -state["K"] @ x
    lo, hi = model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1]
    data.ctrl[:] = np.clip(u, lo, hi)
