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
ALLOWED_DATA_TYPES = {"bool", "int", "float", "string"}
INT_RANGE = (-32768, 32767)
