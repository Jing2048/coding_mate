"""Pro-regime event cues for high-dynamic swings.

Amateur and pro swings share Address/Top/Impact/Finish semantics, but pros have
higher peak rates, more axial twist, and often a translating centre. Scale-free
segmental detection remains the backbone; these cues only refine ambiguous Top /
kinematic-Impact decisions when peak |ω| enters a tour-like regime.

References
----------
* Kim & Park, Sensors 2020 — single-IMU phase boundaries (ms-level).
* Cheetham et al. — proximal→distal peak timing vs impact.
* SciRep 2024 — wrist IMU swing-plane geometry under high dynamics.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.events.segmental import SegmentationDiagnostics
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]

# ~700 deg/s ≈ 12 rad/s — below typical tour driver peaks but above casual chips.
_PRO_PEAK_OMEGA = 12.0


def is_pro_regime(peak_omega_rad_s: float) -> bool:
    return float(peak_omega_rad_s) >= _PRO_PEAK_OMEGA


def _secondary_axis(gyro: ArrayF, omega: ArrayF, primary: ArrayF) -> ArrayF:
    """Second principal rotation axis (often twist / out-of-plane)."""
    w = gyro * omega[:, None]
    _, _, vh = np.linalg.svd(w - w.mean(axis=0), full_matrices=False)
    for row in vh:
        a = row / (np.linalg.norm(row) + 1e-12)
        if abs(float(np.dot(a, primary))) < 0.85:
            return a
    # Orthogonalize vh[1] against primary
    a = vh[min(1, vh.shape[0] - 1)]
    a = a - float(np.dot(a, primary)) * primary
    n = np.linalg.norm(a)
    if n < 1e-9:
        return primary.copy()
    return a / n


def refine_phases_pro(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    phases: SwingPhases,
    diag: SegmentationDiagnostics,
) -> tuple[SwingPhases, dict[str, float]]:
    """Refine Top / Impact for high-dynamic (pro-like) regimes.

    Returns possibly-updated phases and a small meta dict. No-op when peak |ω|
    is below the pro-regime threshold, preserving consumer behaviour.
    """
    meta: dict[str, float] = {"pro_refine_applied": 0.0}
    peak = float(diag.quality.get("peak_omega_rad_s", 0.0))
    if not is_pro_regime(peak):
        return phases, meta

    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = t.shape[0]
    omega = diag.omega
    signed = diag.signed_rate
    axis = diag.dominant_axis

    addr, top, imp, fin = (
        phases.address_idx,
        phases.top_idx,
        phases.impact_idx,
        phases.finish_idx,
    )

    # Dual-axis Top: blend primary signed rate with secondary (twist) magnitude
    # valley — pro swings often stall plane-rate while twist continues.
    sec = _secondary_axis(gyro, omega, axis)
    signed2 = gyro @ sec
    # Soft energy that is low near true top
    energy = 0.65 * np.abs(signed) + 0.35 * np.abs(signed2)
    lo_t = max(addr + 1, 0)
    hi_t = max(lo_t + 1, min(imp - 1, n - 2))
    if hi_t > lo_t:
        cand = lo_t + int(np.argmin(energy[lo_t : hi_t + 1]))
        # Accept only if close to existing top (don't rewrite amateur timing)
        if abs(cand - top) <= max(3, int(0.04 * (1.0 / float(np.median(np.diff(t)))))):
            top = cand

    # Kinematic impact: for collision-mode keep shock; for proxy, late-weighted energy
    if diag.impact_mode == "kinematic_proxy":
        acc_mag = np.linalg.norm(accel, axis=1)
        peak_o = float(np.max(omega) + 1e-9)
        peak_a = float(np.max(acc_mag) + 1e-9)
        # Prefer samples in the last 40% of top→finish motion window
        lo_k = top + 1
        hi_k = min(fin, n - 1)
        if hi_k > lo_k:
            idx = np.arange(lo_k, hi_k + 1)
            prog = (idx - lo_k) / max(hi_k - lo_k, 1)
            late = 0.55 + 0.45 * prog  # weight toward impact
            kin = late * (
                0.5 * (omega[lo_k : hi_k + 1] / peak_o)
                + 0.5 * (acc_mag[lo_k : hi_k + 1] / peak_a)
            )
            imp = lo_k + int(np.argmax(kin))

    top = int(np.clip(top, addr + 1, max(addr + 2, imp - 1)))
    imp = int(np.clip(imp, top + 1, max(top + 2, fin - 1)))
    fin = int(np.clip(fin, imp + 1, n - 1))
    out = SwingPhases(
        address_idx=int(addr),
        top_idx=int(top),
        impact_idx=int(imp),
        finish_idx=int(fin),
    )
    out.validate_order()
    meta = {
        "pro_refine_applied": 1.0,
        "pro_peak_omega_rad_s": peak,
        "pro_top_delta": float(out.top_idx - phases.top_idx),
        "pro_impact_delta": float(out.impact_idx - phases.impact_idx),
    }
    return out, meta


def pro_hybrid_params(peak_omega_rad_s: float) -> dict[str, float]:
    """Adaptive hybrid trajectory knobs for translating-centre pro swings."""
    if not is_pro_regime(peak_omega_rad_s):
        return {
            "center_var_threshold": 0.07,
            "center_gain": 0.15,
            "constrained_blend": 0.40,
            "plane_blend": 0.15,
        }
    # Slightly more willing to engage translating-centre + ZUPT blend
    return {
        "center_var_threshold": 0.05,
        "center_gain": 0.20,
        "constrained_blend": 0.45,
        "plane_blend": 0.22,
    }
