UNIT_DIMENSION = {
    "V": "tensao",
    "kV": "tensao",
    "A": "corrente",
    "kA": "corrente",
    "W": "potencia",
    "kW": "potencia",
    "Hz": "frequencia",
    "": "adimensional",
}

UNIT_TO_BASE = {
    "V": 1.0,
    "kV": 1000.0,
    "A": 1.0,
    "kA": 1000.0,
    "W": 1.0,
    "kW": 1000.0,
    "Hz": 1.0,
    "": 1.0,
}

BASE_UNIT_NAME = {
    "V": "V",
    "kV": "V",
    "A": "A",
    "kA": "A",
    "W": "W",
    "kW": "W",
    "Hz": "Hz",
    "": "",
}

INTEGER_TYPES = {
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
}

NUMERIC_TYPES = {
    *INTEGER_TYPES,
    "float",
}

ALLOWED_DATA_TYPES = {
    "bool",
    *NUMERIC_TYPES,
    "string",
}

TYPE_RANGES = {
    "int": (-32768, 32767),
    "int8": (-128, 127),
    "int16": (-32768, 32767),
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
    "uint8": (0, 255),
    "uint16": (0, 65535),
    "uint32": (0, 4294967295),
    "uint64": (0, 18446744073709551615),
}

INT_RANGE = TYPE_RANGES["int"]
