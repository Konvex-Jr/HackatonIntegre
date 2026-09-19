from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ProtocolBinding:
    protocol: str
    address: str
    data_type: str
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0
    raw_value: Any = None
    raw_timestamp: Optional[datetime] = None
    native_validity: Optional[str] = None
    native_quality_flags: List[str] = field(default_factory=list)
    min_engineering: Optional[float] = None
    max_engineering: Optional[float] = None
    encoding: Optional[str] = None
    byte_order: Optional[str] = None
    protocol_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.raw_timestamp, str):
            self.raw_timestamp = datetime.fromisoformat(self.raw_timestamp)
