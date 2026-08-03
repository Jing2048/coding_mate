# MultiSenseGolf local cache

doi: [10.7910/DVN/LCCLLW](https://doi.org/10.7910/DVN/LCCLLW) (CC0-1.0)

```bash
cd golf-mate/algo
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/fetch_multisense.py --subject Sub07 --max-swings 30
```

Subject archives are large (~0.7–2 GB). The fetch script extracts only HDF5
stream files + documentation CSVs. Raw wrist MEMS is not published; the adapter
derives a lead-wrist IMU from Perception-Neuron 21-joint mocap kinematics and
labels results `mocap_derived_imu`.
