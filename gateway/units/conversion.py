from typing import Optional

from .tables import BASE_UNIT_NAME, UNIT_DIMENSION, UNIT_TO_BASE


def canonical_unit(unit: str) -> str:
    return BASE_UNIT_NAME.get(unit, unit)


def dimension_of(unit: str) -> Optional[str]:
    return UNIT_DIMENSION.get(unit)


def is_known_unit(unit: str) -> bool:
    return unit in UNIT_DIMENSION


def to_base(value: float, unit: str) -> float:
    return value * UNIT_TO_BASE.get(unit, 1.0)


def from_base(value: float, unit: str) -> float:
    factor = UNIT_TO_BASE.get(unit, 1.0)
    return value / factor if factor else value
