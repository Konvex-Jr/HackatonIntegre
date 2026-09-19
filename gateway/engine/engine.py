from datetime import datetime, timezone
from typing import Any, Dict, List

from ..adapters.base import ProtocolAdapter
from ..domain.canonical import CanonicalPoint, Quality, Timestamp, Validity
from ..registry.exceptions import BindingNotFoundError
from ..registry.mapping import PointMapping
from ..registry.registry import MappingRegistry
from .report import ConversionReport


class GatewayEngine:
    def __init__(self, registry: MappingRegistry, adapters: Dict[str, ProtocolAdapter]) -> None:
        self.registry = registry
        self.adapters = adapters
        self._last_good: Dict[str, CanonicalPoint] = {}

    def convert(self, point_id: str, source_protocol: str, target_protocols: List[str]) -> ConversionReport:
        mapping = self.registry.get(point_id)
        if source_protocol not in mapping.bindings:
            raise BindingNotFoundError(
                f"Ponto '{point_id}' não tem binding cadastrado para o "
                f"protocolo de origem '{source_protocol}'"
            )

        report = ConversionReport(point_id=point_id, source_protocol=source_protocol)
        report.canonical = self._read_source_point(mapping, source_protocol, point_id, report)
        self._publish_all_targets(mapping, report, target_protocols)
        return report

    def _read_source_point(
        self, mapping: PointMapping, source_protocol: str, point_id: str, report: ConversionReport
    ) -> CanonicalPoint:
        source_adapter = self.adapters[source_protocol]
        source_binding = mapping.bindings[source_protocol]
        try:
            canonical = source_adapter.read(source_binding, point_id)
            self._last_good[point_id] = canonical.clone()
            return canonical
        except ConnectionError as error:
            report.failure = str(error)
            return self._build_stale_point(point_id, source_protocol)

    def _build_stale_point(self, point_id: str, source_protocol: str) -> CanonicalPoint:
        frozen = self._last_good.get(point_id)
        canonical = frozen.clone() if frozen is not None else CanonicalPoint(
            point_id=point_id,
            value=None,
            data_type="unknown",
            unit="",
            quality=Quality(validity=Validity.GOOD),
            timestamp=Timestamp(value_utc=datetime.now(timezone.utc)),
            source_protocol=source_protocol,
        )
        canonical.quality.validity = Validity.INVALID
        canonical.quality.add_flag("comm_lost")
        canonical.quality.add_flag("stale")
        return canonical

    def _publish_all_targets(
        self, mapping: PointMapping, report: ConversionReport, target_protocols: List[str]
    ) -> None:
        for target in target_protocols:
            report.targets[target] = self._publish_one_target(mapping, report, target)

    def _publish_one_target(
        self, mapping: PointMapping, report: ConversionReport, target: str
    ) -> Dict[str, Any]:
        if target not in mapping.bindings:
            return {"error": f"sem binding cadastrado para '{target}' neste ponto"}
        sink = self.adapters[target]
        binding = mapping.bindings[target]
        try:
            if report.failure:
                return sink.publish_failure(report.canonical, binding, report.failure)
            return sink.publish(report.canonical, binding)
        except Exception as error:
            return {"error": str(error)}
