# Device validation protocol — Watch gold

Companion to `README.md` and the commercial release gate.

## 1. Session setup

- Confirm consent / license recorded before any capture is indexed.
- Note strap fit (`snug` | `normal` | `loose`), wrist side, handedness, club class.
- Note terrain / lie (`flat` | `uphill` | `downhill` | `sidehill` | `bunker_edge` | `other`).
- Prefer outdoor or net sessions that stress saturation (hard iron impact).

## 2. Capture modes

| Stratum | Hardware | Mode | Nominal rates |
|---------|----------|------|---------------|
| Series 8+ high-rate | Series 8 / 9 / Ultra / Ultra 2+ | `high_rate` | accel ~800 Hz, motion ~200 Hz |
| Series 5 compat | Series 5 (and other non-batched) | `compat` | accel ~100 Hz, motion ~100 Hz |

Both strata are mandatory for commercial readiness. Loader compares **manifest
declared rates** to **decoded measured rates** within 10% or a practical floor
(5 Hz motion / 20 Hz accel) — mode alone is not enough.

## 3. Reference labels (required + claim-specific)

Every indexed swing **must** declare:

- `reference.impact_timestamp_s` — capture-relative seconds (numeric ≥ 0)
- `reference.impact_timestamp_source`

| Source | Meaning | Independent gold? |
|--------|---------|-------------------|
| `collision_accel` | Dense accel transient | **No** — device provenance only |
| `kinematic` | Gyro / kinematic peak | **No** — device provenance only |
| `slow_mo_aligned` | Phone slow-mo frame aligned | Yes (via `slow_mo` block) |
| `optical_aligned` | Optical / marker time | Yes (via `optical` block) |
| `launch_monitor` | LM impact / ball time | Yes (via `launch_monitor` block) |
| `metronome_aligned` | Known tempo metronome | Tempo only — **not** Impact/path |
| `manual` | Human scrub (degraded) | No |

When a reference family is `present: true`, it **must** carry:

- `artifact_id` — opaque provenance id (no PII; external files not required in-repo)
- `labels` — type-appropriate flags

| Block | Required labels when present |
|-------|------------------------------|
| `optical` | `trajectory_available`, `phase_labels_available` (bool); path claim needs trajectory or `wrist_path_available` |
| `launch_monitor` | optional `impact_marked`, opaque `shot_id` |
| `metronome` | `bpm` (>0); optional `phase_offset_s` |
| `slow_mo` | optional `impact_frame_marked`, `tempo_visible` |

### Claim-specific gates (all required for `commercial_ready`)

These are **minimum structural evidence**, **not** an accuracy pass:

| Claim gate | Independent refs | Threshold |
|------------|------------------|-----------|
| Impact alignment | `slow_mo` \| `optical` \| `launch_monitor` | ≥ max(3, 10% of valid) |
| Wrist / path | `optical` with path labels + `artifact_id` | ≥ 3 |
| Tempo | `metronome` \| `slow_mo` | ≥ 3 |

**Metronome alone cannot unlock Impact or path commercial evidence.**

## 4. Hashing & integrity

```bash
sha256sum captures/<id>.gmpc
```

Store lowercase hex in `capture.sha256`. Gate fails on mismatch, unreadable
packed v2 / JSON, or declared-vs-measured rate mismatch.

## 5. Domain gap checklist

Must be represented **or** listed under `documented_limitations`:

- Strap fit variants (snug vs loose)
- Left vs right handedness
- Iron and wood (driver counts as wood)
- Terrain / lie diversity (flat alone is insufficient for “no terrain gap” claims)
- Impact saturation / clip stress (hard strikes)

## 6. Honesty boundary

| Gate family | What it proves | Commercial biomech claim? |
|-------------|----------------|---------------------------|
| Algorithm synthetic (`cross_multibody`, optical twin, …) | CI regressable kinematics | **No** |
| External mocap-derived IMU (MultiSense, CMU64) | Human motion distribution | **No** (not Watch MEMS) |
| This Watch gold catalog + claim refs | Real Watch MEMS + independent provenance structure | **Only if** commercial gate passes |

Never relabel synthetic / mocap-derived swings as `evidence_class: real_device`.
Passing claim reference gates does **not** certify numerical Impact/path/tempo accuracy.
