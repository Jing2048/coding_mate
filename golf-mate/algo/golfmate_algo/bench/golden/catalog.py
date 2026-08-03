"""Ranked golden / external evaluation sources for Golf Mate.

Licensing rule: NC / research-only corpora stay on eval tracks — never ship
weights derived from them in commercial core.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenSource:
    name: str
    rank: int
    license: str
    commercial_eval_ok: bool
    signals: str
    ground_truth: str
    n_note: str
    rate_note: str
    integration: str
    url: str
    honesty: str


CATALOG: tuple[GoldenSource, ...] = (
    GoldenSource(
        name="MultiSenseGolf",
        rank=1,
        license="CC0 1.0",
        commercial_eval_ok=True,
        signals="PN 21-bone mocap-derived wrist IMU (not raw MEMS)",
        ground_truth="Joint kinematics + annotated impact + launch monitor",
        n_note="24 subjects / 1557 swings; local Sub07 extracted; elite Sub13–24 in manifest",
        rate_note="Irregular PN timestamps → fixed-grid resample in adapter",
        integration="bench/datasets/multisense.py + strata (elite / high club-speed)",
        url="https://doi.org/10.7910/DVN/LCCLLW",
        honesty="External human motion distribution; NOT wrist MEMS noise/mount",
    ),
    GoldenSource(
        name="CMU Subject 64 golf mocap",
        rank=2,
        license="Free for research & commercial products (do not resell mocap)",
        commercial_eval_ok=True,
        signals="Synth wrist IMU via ASF/AMC FK → body ω + specific force",
        ground_truth="Optical mocap joint orientations @ 120 Hz",
        n_note="~30 swing/putt trials, one subject (2003)",
        rate_note="120 Hz native",
        integration="bench/datasets/cmu64.py",
        url="http://mocap.cs.cmu.edu/search.php?subjectnumber=64",
        honesty="Real human golf kinematics; IMU is synthetic from mocap (like MultiSense)",
    ),
    GoldenSource(
        name="cross_multibody robust regimes",
        rank=3,
        license="In-house MIT synth",
        commercial_eval_ok=True,
        signals="Independent 4-link multibody + MEMS error model",
        ground_truth="Analytic segment quats / positions / event indices",
        n_note="pro sway/lift, casting club-mount, fs∈{50,100}, clip, lefty",
        rate_note="Configurable (default 200 Hz; fs-stress lower)",
        integration="bench/harness.build_cases_robust_golden",
        url="in-repo",
        honesty="Citeable cross-generator; still synthetic — not tour MEMS",
    ),
    GoldenSource(
        name="SciRep 2024 Kim & Park protocol",
        rank=4,
        license="Paper open; raw data on request",
        commercial_eval_ok=False,
        signals="Bosch wrist MEMS ±16g/2000dps @ 200 Hz vs optical",
        ground_truth="Optical markers on IMU / arm / club",
        n_note="20 RH golfers; 389 usable swings",
        rate_note="200 Hz",
        integration="bench/golden/scirep_budgets.py (published ceilings only)",
        url="https://doi.org/10.1038/s41598-024-59949-w",
        honesty="Best published single-wrist MEMS protocol; data not public",
    ),
    GoldenSource(
        name="WIT-KinNet 2026",
        rank=5,
        license="Unknown until release",
        commercial_eval_ok=False,
        signals="Huawei Watch lead-wrist 9-axis @ 100 Hz",
        ground_truth="OMC 120 Hz full-body joints",
        n_note="36 golfers × clubs × amplitudes",
        rate_note="acc/gyro 100 Hz",
        integration="stub: bench/datasets/wit_kinnet.py (download hook)",
        url="https://arxiv.org/abs/2606.22876",
        honesty="Highest product-fit when released; chase author share",
    ),
)


def ranked_catalog() -> list[GoldenSource]:
    return sorted(CATALOG, key=lambda s: s.rank)


def catalog_as_markdown() -> str:
    lines = [
        "# Golden source catalog (Golf Mate)",
        "",
        "| Rank | Source | Commercial eval | Honesty |",
        "|-----:|--------|:---------------:|---------|",
    ]
    for s in ranked_catalog():
        ok = "yes" if s.commercial_eval_ok else "no / pending"
        lines.append(f"| {s.rank} | {s.name} | {ok} | {s.honesty} |")
    lines.append("")
    for s in ranked_catalog():
        lines.extend(
            [
                f"## {s.rank}. {s.name}",
                "",
                f"- License: {s.license}",
                f"- Signals: {s.signals}",
                f"- GT: {s.ground_truth}",
                f"- Scale: {s.n_note}",
                f"- Rate: {s.rate_note}",
                f"- Integration: {s.integration}",
                f"- URL: {s.url}",
                f"- Honesty: {s.honesty}",
                "",
            ]
        )
    return "\n".join(lines)
