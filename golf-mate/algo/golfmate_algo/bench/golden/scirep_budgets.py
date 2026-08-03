"""Published SciRep 2024 single-wrist budgets (Kim & Park).

Raw MEMS+optical data is not public; we encode the *protocol ceilings* as
reference constants so our gates stay honest about consumer-grade ambition.

Until an author share lands, CI also runs an in-house **200 Hz optical-aligned
protocol twin** (`bench/datasets/optical_aligned.py`) that mirrors this capture
envelope (±16 g / 2000 dps @ 200 Hz + optical markers on IMU/club).

Source: https://doi.org/10.1038/s41598-024-59949-w
"""

from __future__ import annotations

# Whole-swing wrist tracking error reported ~17 cm under their pipeline.
POSITION_CM_WHOLE_SWING = 17.0

# Orientation improvement ~60% vs classical AHRS baseline (relative).
# Absolute degrees vary by subject; we use a soft ceiling for product ambition
# that is tighter than classical failure modes but not tighter than SciRep.
ORIENTATION_DEG_SOFT = 12.0

# Their capture used 200 Hz wrist MEMS with explicit clipping repair.
CAPTURE_FS_HZ = 200.0
GYRO_RANGE_DEG_S = 2000.0
ACCEL_RANGE_G = 16.0

# Golf Mate product ambition on citeable cross_multibody (stricter than SciRep).
PRODUCT_IMPACT_MS = 20.0
PRODUCT_POSITION_CM = 17.0
PRODUCT_ORIENTATION_DEG = 8.0

# Soft ceilings for the in-house optical-aligned protocol twin.
# Twin includes casting / clip / lefty stress specs — ceilings are regression
# detectors, not product ambition (that stays on cross_multibody).
PROTOCOL_TWIN_ORIENTATION_DEG = 25.0
PROTOCOL_TWIN_IMPACT_MS = 400.0
PROTOCOL_TWIN_POSITION_CM = 200.0
