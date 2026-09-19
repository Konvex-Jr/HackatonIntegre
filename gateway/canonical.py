"""Modelo canônico de dado: a representação neutra de protocolo que
transita pelo núcleo do gateway. Todo adaptador de origem produz um
CanonicalPoint; todo adaptador de destino consome um CanonicalPoint.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Set
from datetime import datetime
import copy


class Validity(Enum):
    GOOD = "good"
    INVALID = "invalid"
    QUESTIONABLE = "questionable"


# Superset das flags de qualidade observadas em MMS, DNP3, Modbus e OPC UA.
QUALITY_FLAGS = {
    "overflow", "out_of_range", "forced", "substituted",
    "test", "comm_lost", "stale", "config_error",
}


@dataclass
class Quality:
    validity: Validity = Validity.GOOD
    flags: Set[str] = field(default_factory=set)

    def add_flag(self, flag: str) -> None:
        if flag not in QUALITY_FLAGS:
            raise ValueError(f"Flag de qualidade desconhecida: {flag}")
        self.flags.add(flag)

    def __str__(self) -> str:
        flags = ",".join(sorted(self.flags)) if self.flags else "-"
        return f"{self.validity.value}[{flags}]"


@dataclass
class Timestamp:
    value_utc: datetime
    sync_source: str = "unsynchronized"  # synchronized | unsynchronized | local

    def __str__(self) -> str:
        return f"{self.value_utc.isoformat(timespec='milliseconds')} ({self.sync_source})"


@dataclass
class CanonicalPoint:
    point_id: str
    value: Any
    data_type: str          # bool | int | float | string
    unit: str                # unidade já normalizada para a base canônica
    quality: Quality
    timestamp: Timestamp
    source_protocol: str
    source_raw: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "CanonicalPoint":
        return copy.deepcopy(self)
