from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ProtocolBinding:
    protocol: str
    address: str
    data_type: str
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0
    raw_value: Any = None
    native_validity: Optional[str] = None
    native_quality_flags: List[str] = field(default_factory=list)
    min_engineering: Optional[float] = None
    max_engineering: Optional[float] = None
