"""Motor de normalização/denormalização: orquestra adaptadores + registro
de mapeamento. Não conhece nenhum protocolo diretamente — só a interface
comum ProtocolAdapter.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .canonical import CanonicalPoint, Quality, Timestamp, Validity
from .registry import MappingRegistry
from .adapters import ProtocolAdapter


@dataclass
class ConversionReport:
    point_id: str
    source_protocol: str
    canonical: Optional[CanonicalPoint] = None
    failure: Optional[str] = None
    targets: Dict[str, Any] = field(default_factory=dict)


class GatewayEngine:
    def __init__(self, registry: MappingRegistry, adapters: Dict[str, ProtocolAdapter]):
        self.registry = registry
        self.adapters = adapters
        self._last_good: Dict[str, CanonicalPoint] = {}

    def convert(self, point_id: str, source_protocol: str, target_protocols: List[str]) -> ConversionReport:
        mapping = self.registry.get(point_id)
        if source_protocol not in mapping.bindings:
            raise KeyError(
                f"Ponto '{point_id}' não tem binding cadastrado para o "
                f"protocolo de origem '{source_protocol}'"
            )
        source_adapter = self.adapters[source_protocol]
        source_binding = mapping.bindings[source_protocol]

        report = ConversionReport(point_id=point_id, source_protocol=source_protocol)
        try:
            canonical = source_adapter.read(source_binding, point_id)
            self._last_good[point_id] = canonical.clone()
        except ConnectionError as e:
            report.failure = str(e)
            frozen = self._last_good.get(point_id)
            if frozen is not None:
                canonical = frozen.clone()
            else:
                canonical = CanonicalPoint(
                    point_id=point_id, value=None, data_type="unknown", unit="",
                    quality=Quality(validity=Validity.GOOD),
                    timestamp=Timestamp(value_utc=datetime.now(timezone.utc)),
                    source_protocol=source_protocol,
                )
            canonical.quality.validity = Validity.INVALID
            canonical.quality.add_flag("comm_lost")
            canonical.quality.add_flag("stale")

        report.canonical = canonical

        for target in target_protocols:
            if target not in mapping.bindings:
                report.targets[target] = {
                    "error": f"sem binding cadastrado para '{target}' neste ponto"
                }
                continue
            sink = self.adapters[target]
            binding = mapping.bindings[target]
            try:
                if report.failure:
                    result = sink.publish_failure(canonical, binding, report.failure)
                else:
                    result = sink.publish(canonical, binding)
                report.targets[target] = result
            except Exception as e:
                report.targets[target] = {"error": str(e)}

        return report
