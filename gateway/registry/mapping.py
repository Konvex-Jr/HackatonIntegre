from dataclasses import asdict, dataclass, field
from typing import Dict

from .binding import ProtocolBinding


@dataclass
class PointMapping:
    point_id: str
    bindings: Dict[str, ProtocolBinding] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "point_id": self.point_id,
            "bindings": {proto: asdict(binding) for proto, binding in self.bindings.items()},
        }
