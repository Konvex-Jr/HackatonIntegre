from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Set
import copy


class Validity(Enum):
    GOOD = "good"
    INVALID = "invalid"
    QUESTIONABLE = "questionable"


class LossSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


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

    def as_dict(self) -> Dict[str, Any]:
        return {"validity": self.validity.value, "flags": sorted(self.flags)}

    def __str__(self) -> str:
        flags = ",".join(sorted(self.flags)) if self.flags else "-"
        return f"{self.validity.value}[{flags}]"


@dataclass
class Timestamp:
    value_utc: datetime
    sync_source: str = "unsynchronized"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "value_utc": self.value_utc.isoformat(timespec="milliseconds"),
            "sync_source": self.sync_source,
        }

    def __str__(self) -> str:
        return f"{self.value_utc.isoformat(timespec='milliseconds')} ({self.sync_source})"


@dataclass
class LossEvent:
    code: str
    severity: LossSeverity
    source_protocol: str
    target_protocol: str
    message: str
    affected_value: Optional[Any] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "source_protocol": self.source_protocol,
            "target_protocol": self.target_protocol,
            "message": self.message,
            "affected_value": self.affected_value,
        }


@dataclass
class CanonicalPoint:
    point_id: str
    value: Any
    data_type: str
    unit: str
    quality: Quality
    timestamp: Timestamp
    source_protocol: str
    source_raw: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "CanonicalPoint":
        return copy.deepcopy(self)
