from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..domain.canonical import CanonicalPoint


@dataclass
class ConversionReport:
    point_id: str
    source_protocol: str
    canonical: Optional[CanonicalPoint] = None
    failure: Optional[str] = None
    targets: Dict[str, Any] = field(default_factory=dict)
