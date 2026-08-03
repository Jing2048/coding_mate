# WIT-KinNet drop contract

Source: https://arxiv.org/abs/2606.22876
Version: `wit-kinnet-contract-v1`

```json
{
  "contract_version": "wit-kinnet-contract-v1",
  "root": "/workspace/golf-mate/algo/data/wit_kinnet",
  "per_swing": {
    "watch_imu": "watch_imu.npz|.h5 with keys t, gyro(N,3 rad/s), accel(N,3 m/s^2)",
    "omc_joints": "omc_joints.npz|.h5 with keys t, quats(N,4 wxyz), pos(N,3 m), optional impact_idx",
    "fs_watch_hz": 100.0,
    "fs_omc_hz": 120.0
  },
  "handedness": "lead wrist; Right-handed golfer \u2192 LeftHand lead by default",
  "arxiv": "https://arxiv.org/abs/2606.22876"
}
```
