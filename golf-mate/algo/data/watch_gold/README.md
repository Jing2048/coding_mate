# Watch device-gold catalog (`watch-gold-v1`)

Real Apple Watch MEMS captures for **commercial release evidence**.

This directory is a **contract + empty catalog** in the repository. It must never
be filled with fake captures or marked `ready` without consented real-device
sessions. Algorithm synthetic gates (`cross_multibody`, optical twins, etc.) are
**not** device evidence and **must not** be converted into commercial readiness.

## Status

| Field | Value |
|-------|-------|
| Schema | `watch-gold-manifest-v1` (see `manifest.schema.json`) |
| Repo catalog | `manifest.json` — **empty / not ready** |
| Captures | Drop under `captures/` (gitignored optional blobs) or absolute paths listed in the manifest |

## Protocol (capture)

1. Active HealthKit workout; use the Golf Mate Watch app dual-rail path.
2. **Series 8+ / Ultra**: `captureMode=high_rate` (~800 Hz accel + ~200 Hz Device Motion).
3. **Series 5 compat**: `captureMode=compat` (~100 Hz dual stream via `CMMotionManager`).
4. Export as packed v2 (`.gmpc` / binary) or JSON `golfmate-watch-capture-v1`.
5. Record metadata in `manifest.json` (pseudonym only — no names, emails, photos, GPS).
6. Every swing: `impact_timestamp_s` (capture-relative) + source. Independent refs
   (`slow_mo` / `optical` / `launch_monitor` / `metronome`) need opaque `artifact_id`
   + type labels when `present=true` (files need not live in git).
7. Compute SHA-256 of the capture file bytes; store as `capture.sha256`.
8. Declared rates must match decoded measured rates (10% / floor).

## Privacy

- Subject IDs are **opaque pseudonyms** (`sub_a`, `S01`, …) — never real names.
- No face video, phone numbers, exact course GPS, or medical identifiers in-repo.
- Consent / license fields must be present before a record counts toward the gate.
- Raw captures may live outside git; the manifest may point at local paths.
- Reference `artifact_id` values are opaque provenance ids (no PII).

## Commercial gate (summary)

Fail-closed unless all hold (see `golfmate_algo.bench.commercial_release_gate`):

- ≥30 **valid** swings, ≥2 subjects
- Series 8+ high-rate **and** Series 5 compat strata
- Left and right handedness **or** an explicit documented limitation
- Strap-fit variants, iron **and** wood clubs
- Claim-specific independent refs (all three): Impact (slow_mo|optical|LM),
  optical path (≥3), tempo (metronome|slow_mo) — **structural evidence, not accuracy**
- Evidence class `real_device` only — synthetic fixtures never unlock commercial ready
- Metronome alone does **not** unlock Impact/path readiness

## Files

| Path | Role |
|------|------|
| `manifest.schema.json` | Manifest + record schema |
| `manifest.json` | Catalog (empty in CI) |
| `PROTOCOL.md` | Full validation / labeling protocol |
| `captures/` | Optional on-disk captures (not shipped) |

## CLI

```bash
cd golf-mate/algo
python scripts/commercial_release_gate.py --json
```
