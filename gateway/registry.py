"""Registro de mapeamento semântico: para cada ponto canônico, guarda o
'binding' (endereço, tipo, unidade, escala) em cada protocolo onde ele
existe. É aqui que mora a validação estática de compatibilidade — a
primeira linha de defesa contra configuração inválida.
"""

import json
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any

from .units import dimension_of, NUMERIC_TYPES


class ValidationError(Exception):
    pass


@dataclass
class ProtocolBinding:
    protocol: str
    address: str
    data_type: str            # bool | int | float | string
    unit: str = ""
    scale: float = 1.0        # valor_de_engenharia = raw * scale + offset
    offset: float = 0.0
    raw_value: Any = None      # valor bruto simulado, como se viesse do "dispositivo"


@dataclass
class PointMapping:
    point_id: str
    bindings: Dict[str, ProtocolBinding] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "point_id": self.point_id,
            "bindings": {p: asdict(b) for p, b in self.bindings.items()},
        }


class MappingRegistry:
    def __init__(self):
        self._points: Dict[str, PointMapping] = {}

    # ---- CRUD -----------------------------------------------------------
    def add(self, mapping: PointMapping, validate: bool = True) -> None:
        if validate:
            self.validate_mapping(mapping)
        self._points[mapping.point_id] = mapping

    def get(self, point_id: str) -> PointMapping:
        if point_id not in self._points:
            raise KeyError(f"Ponto '{point_id}' não cadastrado no mapeamento")
        return self._points[point_id]

    def list(self) -> List[PointMapping]:
        return list(self._points.values())

    def remove(self, point_id: str) -> None:
        self._points.pop(point_id, None)

    # ---- Validação --------------------------------------------------------
    def validate_mapping(self, mapping: PointMapping) -> None:
        if len(mapping.bindings) < 2:
            raise ValidationError(
                f"{mapping.point_id}: um mapeamento precisa de ao menos 2 "
                f"protocolos para fazer sentido em um gateway"
            )

        dtypes = {b.data_type for b in mapping.bindings.values()}
        if len(dtypes) > 1 and not dtypes.issubset(NUMERIC_TYPES):
            raise ValidationError(
                f"{mapping.point_id}: tipos de dado incompatíveis entre "
                f"protocolos: {sorted(dtypes)}"
            )

        dims = set()
        for proto, b in mapping.bindings.items():
            dim = dimension_of(b.unit)
            if dim is None:
                raise ValidationError(
                    f"{mapping.point_id}/{proto}: unidade desconhecida '{b.unit}'"
                )
            dims.add(dim)
        if len(dims) > 1:
            raise ValidationError(
                f"{mapping.point_id}: dimensões físicas incompatíveis entre "
                f"protocolos: {sorted(dims)}"
            )

    def validate_all(self) -> Dict[str, Optional[str]]:
        """Revalida tudo que está cadastrado; retorna erro por ponto (ou None)."""
        results = {}
        for pid, mapping in self._points.items():
            try:
                self.validate_mapping(mapping)
                results[pid] = None
            except ValidationError as e:
                results[pid] = str(e)
        return results

    # ---- Persistência -------------------------------------------------
    def save(self, path: str) -> None:
        data = {pid: m.to_dict() for pid, m in self._points.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, path: str, validate: bool = True) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for pid, m in data.items():
            bindings = {
                proto: ProtocolBinding(**b) for proto, b in m["bindings"].items()
            }
            mapping = PointMapping(point_id=pid, bindings=bindings)
            self.add(mapping, validate=validate)
