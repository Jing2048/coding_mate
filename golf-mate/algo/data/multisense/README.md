# MultiSenseGolf local cache

doi: [10.7910/DVN/LCCLLW](https://doi.org/10.7910/DVN/LCCLLW) (CC0-1.0)

```bash
cd golf-mate/algo
source .venv/bin/activate
pip install -e ".[dev]"
# Recreational baseline (small archive)
python scripts/fetch_multisense.py --subject Sub07 --max-swings 30
# Elite eval gate (Sub13–24; expertise≥5 or pro license)
python scripts/fetch_multisense.py --subject Sub13 --max-swings 20
python scripts/fetch_multisense.py --subject Sub19 --max-swings 15
# Or pull the priority elite set:
python scripts/fetch_multisense.py --elite --elite-priority Sub13,Sub19,Sub23 --max-swings 15
```

Subject archives are large (~0.7–2 GB; elite often split across `_1`/`_2` zips).
The fetch script extracts only HDF5 stream files + documentation CSVs. Dataverse
file IDs live in `data/reference/multisense_dataverse_file_ids.json`.

Raw wrist MEMS is not published; the adapter derives a lead-wrist IMU from
Perception-Neuron 21-joint mocap kinematics and labels results
`mocap_derived_imu`. Elite subjects are an **external eval gate only** — not an
in-product posture library (`data/reference/multisense_elite_manifest.json`).
