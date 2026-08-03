"""Modern Monte-Carlo aggregation: bootstrap CIs and stratified summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

ArrayF = NDArray[np.float64]


@dataclass(frozen=True)
class Summary:
    mean: float
    std: float
    median: float
    p95: float
    maximum: float
    n: int
    ci95_lo: float
    ci95_hi: float
    extras: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _finite(values: Iterable[float]) -> ArrayF:
    arr = np.asarray(list(values), dtype=np.float64)
    return arr[np.isfinite(arr)]


def bootstrap_ci(
    values: Sequence[float] | ArrayF,
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
    statistic: str = "mean",
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for mean or median. Returns (point, lo, hi)."""
    arr = _finite(values)
    if arr.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    if statistic == "median":
        point = float(np.median(arr))
        fn = np.median
    else:
        point = float(np.mean(arr))
        fn = np.mean
    if arr.size == 1:
        return point, point, point
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    samples = fn(arr[idx], axis=1)
    lo = float(np.percentile(samples, 100.0 * alpha / 2.0))
    hi = float(np.percentile(samples, 100.0 * (1.0 - alpha / 2.0)))
    return point, lo, hi


def summarize(
    values: Iterable[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    extras: dict[str, float] | None = None,
) -> Summary:
    arr = _finite(values)
    if arr.size == 0:
        return Summary(
            mean=float("nan"),
            std=float("nan"),
            median=float("nan"),
            p95=float("nan"),
            maximum=float("nan"),
            n=0,
            ci95_lo=float("nan"),
            ci95_hi=float("nan"),
            extras=extras or {},
        )
    mean, lo, hi = bootstrap_ci(arr, n_boot=n_boot, seed=seed)
    return Summary(
        mean=mean,
        std=float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        median=float(np.median(arr)),
        p95=float(np.percentile(arr, 95)),
        maximum=float(np.max(arr)),
        n=int(arr.size),
        ci95_lo=lo,
        ci95_hi=hi,
        extras=extras or {},
    )
