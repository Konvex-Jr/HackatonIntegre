"""Tabelas de unidades: dimensão física e fator de conversão para a
unidade base do sistema (um SI simplificado, só com o necessário para
o protótipo). Usadas pelo núcleo para saber se duas unidades são
compatíveis entre si e para normalizar valores para a base canônica.
"""

UNIT_DIMENSION = {
    "V": "tensao", "kV": "tensao",
    "A": "corrente", "kA": "corrente",
    "W": "potencia", "kW": "potencia",
    "Hz": "frequencia",
    "": "adimensional",
}

UNIT_TO_BASE = {
    "V": 1.0, "kV": 1000.0,
    "A": 1.0, "kA": 1000.0,
    "W": 1.0, "kW": 1000.0,
    "Hz": 1.0,
    "": 1.0,
}

BASE_UNIT_NAME = {
    "V": "V", "kV": "V",
    "A": "A", "kA": "A",
    "W": "W", "kW": "W",
    "Hz": "Hz",
    "": "",
}

NUMERIC_TYPES = {"int", "float"}


def canonical_unit(unit: str) -> str:
    return BASE_UNIT_NAME.get(unit, unit)


def dimension_of(unit: str):
    """Retorna a dimensão física da unidade, ou None se desconhecida."""
    return UNIT_DIMENSION.get(unit)


def to_base(value: float, unit: str) -> float:
    return value * UNIT_TO_BASE.get(unit, 1.0)


def from_base(value: float, unit: str) -> float:
    factor = UNIT_TO_BASE.get(unit, 1.0)
    return value / factor if factor else value
