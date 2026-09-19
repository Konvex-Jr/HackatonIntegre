from pathlib import Path
from typing import Dict, List, Optional, Union

from .exceptions import MappingNotFoundError, ValidationError
from .mapping import PointMapping
from .persistence import load_mappings, save_mappings
from .validation import validate_mapping


class MappingRegistry:
    def __init__(self) -> None:
        self._points: Dict[str, PointMapping] = {}

    def add(self, mapping: PointMapping, validate: bool = True) -> None:
        if validate:
            validate_mapping(mapping)
        self._points[mapping.point_id] = mapping

    def get(self, point_id: str) -> PointMapping:
        try:
            return self._points[point_id]
        except KeyError as error:
            raise MappingNotFoundError(
                f"Ponto '{point_id}' não cadastrado no mapeamento"
            ) from error

    def list(self) -> List[PointMapping]:
        return list(self._points.values())

    def remove(self, point_id: str) -> None:
        self._points.pop(point_id, None)

    def validate_all(self) -> Dict[str, Optional[str]]:
        results: Dict[str, Optional[str]] = {}
        for point_id, mapping in self._points.items():
            try:
                validate_mapping(mapping)
                results[point_id] = None
            except ValidationError as error:
                results[point_id] = str(error)
        return results

    def save(self, path: Union[str, Path]) -> None:
        save_mappings(path, self._points)

    def load(self, path: Union[str, Path], validate: bool = True) -> None:
        for mapping in load_mappings(path).values():
            self.add(mapping, validate=validate)
