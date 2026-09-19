import json
from pathlib import Path
from typing import Dict, Union

from .binding import ProtocolBinding
from .mapping import PointMapping


def save_mappings(path: Union[str, Path], mappings: Dict[str, PointMapping]) -> None:
    data = {point_id: mapping.to_dict() for point_id, mapping in mappings.items()}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def load_mappings(path: Union[str, Path]) -> Dict[str, PointMapping]:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    mappings: Dict[str, PointMapping] = {}
    for point_id, entry in raw.items():
        bindings = {
            proto: ProtocolBinding(**binding_data)
            for proto, binding_data in entry["bindings"].items()
        }
        mappings[point_id] = PointMapping(point_id=point_id, bindings=bindings)
    return mappings
