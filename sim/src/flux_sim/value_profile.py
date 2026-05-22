from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


PROFILE_CONFIG_KEY = "value_profile"
PRODUCTION_PROFILE_CONFIG_KEY = "production_profile"


@dataclass(frozen=True)
class ProfileSample:
    x: float
    value: float


@dataclass(frozen=True)
class ValueProfile:
    kind: str
    coefficients: tuple[float, float, float] | None = None
    baseline: float = 0.0
    amplitude: float = 1.0
    period: float = 60.0
    phase: float = 0.0
    source: str = "fallback"

    @classmethod
    def sine_fallback(
        cls,
        samples: Iterable[ProfileSample] = (),
        *,
        period: float | None = None,
    ) -> "ValueProfile":
        sample_list = list(samples)
        values = [sample.value for sample in sample_list]
        baseline = sum(values) / len(values) if values else 0.0
        amplitude = (max(values) - min(values)) / 2.0 if len(values) >= 2 else 1.0
        if amplitude == 0.0:
            amplitude = 1.0
        inferred_period = period or period_for_samples(sample_list) or 60.0
        return cls(
            kind="sine",
            baseline=baseline,
            amplitude=amplitude,
            period=inferred_period,
            source="fallback",
        )

    @classmethod
    def fit_second_order(cls, samples: Iterable[ProfileSample]) -> "ValueProfile":
        sample_list = list(samples)
        if len(sample_list) < 3:
            return cls.sine_fallback(sample_list)
        coefficients = solve_second_order_least_squares(sample_list)
        if coefficients is None:
            return cls.sine_fallback(sample_list)
        return cls(kind="polynomial2", coefficients=coefficients, source="fit")

    def evaluate(self, x: float) -> float:
        if self.kind == "polynomial2" and self.coefficients is not None:
            a, b, c = self.coefficients
            return (a * x * x) + (b * x) + c
        period = self.period if self.period else 60.0
        return self.baseline + (self.amplitude * math.sin(((2.0 * math.pi) * x / period) + self.phase))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "source": self.source,
        }
        if self.coefficients is not None:
            payload["coefficients"] = list(self.coefficients)
        if self.kind == "sine":
            payload.update(
                {
                    "baseline": self.baseline,
                    "amplitude": self.amplitude,
                    "period": self.period,
                    "phase": self.phase,
                }
            )
        return payload

    def to_metadata(self) -> dict[str, Any]:
        return {PROFILE_CONFIG_KEY: self.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValueProfile":
        coefficients = payload.get("coefficients")
        return cls(
            kind=str(payload.get("kind") or "sine"),
            coefficients=tuple(float(value) for value in coefficients) if coefficients is not None else None,
            baseline=float_or_default(payload.get("baseline"), 0.0),
            amplitude=float_or_default(payload.get("amplitude"), 1.0),
            period=float_or_default(payload.get("period"), 60.0),
            phase=float_or_default(payload.get("phase"), 0.0),
            source=str(payload.get("source") or "fallback"),
        )

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "ValueProfile | None":
        payload = metadata.get(PROFILE_CONFIG_KEY) or metadata.get(PRODUCTION_PROFILE_CONFIG_KEY)
        if not isinstance(payload, Mapping):
            return None
        return cls.from_dict(payload)


def fit_value_profile(samples: Iterable[tuple[float, float] | ProfileSample]) -> ValueProfile:
    return ValueProfile.fit_second_order(normalize_samples(samples))


def float_or_default(value: Any, default: float) -> float:
    return default if value is None else float(value)


def normalize_samples(samples: Iterable[tuple[float, float] | ProfileSample]) -> tuple[ProfileSample, ...]:
    normalized: list[ProfileSample] = []
    for sample in samples:
        if isinstance(sample, ProfileSample):
            normalized.append(sample)
        else:
            x, value = sample
            normalized.append(ProfileSample(float(x), float(value)))
    return tuple(normalized)


def solve_second_order_least_squares(samples: Iterable[ProfileSample]) -> tuple[float, float, float] | None:
    sample_list = list(samples)
    matrix = [
        [sum(sample.x**4 for sample in sample_list), sum(sample.x**3 for sample in sample_list), sum(sample.x**2 for sample in sample_list)],
        [sum(sample.x**3 for sample in sample_list), sum(sample.x**2 for sample in sample_list), sum(sample.x for sample in sample_list)],
        [sum(sample.x**2 for sample in sample_list), sum(sample.x for sample in sample_list), float(len(sample_list))],
    ]
    vector = [
        sum((sample.x**2) * sample.value for sample in sample_list),
        sum(sample.x * sample.value for sample in sample_list),
        sum(sample.value for sample in sample_list),
    ]
    return solve_3x3(matrix, vector)


def solve_3x3(matrix: list[list[float]], vector: list[float]) -> tuple[float, float, float] | None:
    rows = [matrix[index][:] + [vector[index]] for index in range(3)]
    for pivot_index in range(3):
        pivot_row = max(range(pivot_index, 3), key=lambda row_index: abs(rows[row_index][pivot_index]))
        if abs(rows[pivot_row][pivot_index]) < 1e-12:
            return None
        rows[pivot_index], rows[pivot_row] = rows[pivot_row], rows[pivot_index]
        pivot = rows[pivot_index][pivot_index]
        rows[pivot_index] = [value / pivot for value in rows[pivot_index]]
        for row_index in range(3):
            if row_index == pivot_index:
                continue
            factor = rows[row_index][pivot_index]
            rows[row_index] = [
                value - (factor * rows[pivot_index][column_index])
                for column_index, value in enumerate(rows[row_index])
            ]
    return rows[0][3], rows[1][3], rows[2][3]


def period_for_samples(samples: list[ProfileSample]) -> float | None:
    if len(samples) < 2:
        return None
    span = max(sample.x for sample in samples) - min(sample.x for sample in samples)
    return span if span > 0.0 else None
