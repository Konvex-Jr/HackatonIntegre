from abc import ABC
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity, Quality, Timestamp, Validity
from ..registry.binding import ProtocolBinding
from ..units.conversion import canonical_unit, from_base, to_base
from ..units.tables import INTEGER_TYPES, TYPE_RANGES
from .resilience import CircuitBreaker, retry_with_backoff


class ProtocolAdapter(ABC):
    protocol_name = "base"
    supports_quality = True
    supports_timestamp = True

    def __init__(self) -> None:
        self.connected = True
        self._circuit_breaker = CircuitBreaker()

    @property
    def circuit_state(self) -> str:
        return self._circuit_breaker.state.value

    def read(self, binding: ProtocolBinding, point_id: str) -> CanonicalPoint:
        if not self._circuit_breaker.allow_request():
            raise ConnectionError(
                f"[{self.protocol_name}] circuito aberto para leitura de '{point_id}'; "
                f"comunicação considerada indisponível"
            )
        try:
            point = retry_with_backoff(
                lambda: self._read_once(binding, point_id),
                retry_on=ConnectionError,
            )
        except ConnectionError:
            self._circuit_breaker.record_failure()
            raise
        self._circuit_breaker.record_success()
        return point

    def _read_once(self, binding: ProtocolBinding, point_id: str) -> CanonicalPoint:
        if not self.connected:
            raise ConnectionError(
                f"[{self.protocol_name}] comunicação indisponível ao ler '{point_id}'"
            )
        raw = binding.raw_value if binding.raw_value is not None else 0
        engineering = raw * binding.scale + binding.offset if isinstance(raw, (int, float)) and binding.data_type not in {"bool", "string"} else raw
        value_base = to_base(engineering, binding.unit) if isinstance(engineering, (int, float)) and binding.data_type not in {"bool", "string"} else engineering
        return CanonicalPoint(
            point_id=point_id,
            value=value_base,
            data_type=binding.data_type,
            unit=canonical_unit(binding.unit),
            quality=self._build_quality_from_binding(binding),
            timestamp=self._build_timestamp_from_binding(binding),
            source_protocol=self.protocol_name,
            source_address=binding.address,
            source_raw={"address": binding.address, "value": raw},
            source_metadata=dict(binding.protocol_metadata),
        )

    def _build_quality_from_binding(self, binding: ProtocolBinding) -> Quality:
        validity = Validity(binding.native_validity) if binding.native_validity else Validity.GOOD
        quality = Quality(validity=validity)
        for flag in binding.native_quality_flags:
            quality.add_flag(flag)
        return quality

    def _build_timestamp_from_binding(self, binding: ProtocolBinding) -> Timestamp:
        if binding.raw_timestamp is not None:
            value = binding.raw_timestamp.astimezone(timezone.utc) if binding.raw_timestamp.tzinfo else binding.raw_timestamp.replace(tzinfo=timezone.utc)
            return Timestamp(value_utc=value, sync_source="source")
        return Timestamp(value_utc=datetime.now(timezone.utc), sync_source="gateway")

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        losses = self._detect_metadata_losses(point, binding)
        engineering = from_base(point.value, binding.unit) if isinstance(point.value, (int, float)) else point.value
        raw, conversion_losses = self._convert_to_raw(engineering, binding, point.source_protocol)
        losses.extend(conversion_losses)
        payload: Dict[str, Any] = {
            "address": binding.address,
            "written_value": raw,
            "engineering_value": engineering,
            "target_unit": binding.unit,
            "target_type": binding.data_type,
            "encoding": binding.encoding,
            "byte_order": binding.byte_order,
            "losses": [loss.as_dict() for loss in losses],
        }
        if self.supports_quality:
            payload["quality"] = point.quality.as_dict()
        if self.supports_timestamp:
            payload["timestamp"] = point.timestamp.as_dict()
        return payload

    def _detect_metadata_losses(self, point: CanonicalPoint, binding: ProtocolBinding) -> List[LossEvent]:
        losses: List[LossEvent] = []
        quality_supported = self.supports_quality
        timestamp_supported = self.supports_timestamp
        if self.protocol_name == "dnp3":
            variation = binding.protocol_metadata.get("variation")
            if variation in {1, 2, 5, 6}:
                timestamp_supported = False
        if not quality_supported:
            losses.append(LossEvent(
                code="quality_unsupported",
                severity=LossSeverity.WARNING,
                source_protocol=point.source_protocol,
                target_protocol=self.protocol_name,
                message="protocolo de destino não representa qualidade de forma nativa",
                field="quality",
                source_value=point.quality.as_dict(),
            ))
        if not timestamp_supported:
            losses.append(LossEvent(
                code="timestamp_unsupported",
                severity=LossSeverity.WARNING,
                source_protocol=point.source_protocol,
                target_protocol=self.protocol_name,
                message="protocolo de destino não representa estampa de tempo para a variação configurada",
                field="timestamp",
                source_value=point.timestamp.as_dict(),
            ))
        return losses

    def _convert_to_raw(
        self, engineering: Any, binding: ProtocolBinding, source_protocol: str
    ) -> Tuple[Any, List[LossEvent]]:
        losses: List[LossEvent] = []
        if not isinstance(engineering, (int, float)) or binding.data_type in {"bool", "string"}:
            return self._convert_non_numeric(engineering, binding, source_protocol)
        raw = (engineering - binding.offset) / binding.scale if binding.scale else engineering
        if binding.min_engineering is not None and engineering < binding.min_engineering:
            losses.append(LossEvent(
                code="out_of_range",
                severity=LossSeverity.ERROR,
                source_protocol=source_protocol,
                target_protocol=self.protocol_name,
                message=f"valor de engenharia {engineering} abaixo do mínimo permitido {binding.min_engineering}",
                field="value",
                source_value=engineering,
                affected_value=engineering,
            ))
        if binding.max_engineering is not None and engineering > binding.max_engineering:
            losses.append(LossEvent(
                code="out_of_range",
                severity=LossSeverity.ERROR,
                source_protocol=source_protocol,
                target_protocol=self.protocol_name,
                message=f"valor de engenharia {engineering} acima do máximo permitido {binding.max_engineering}",
                field="value",
                source_value=engineering,
                affected_value=engineering,
            ))
        if binding.data_type in INTEGER_TYPES:
            rounded = round(raw)
            if abs(rounded - raw) > 1e-9:
                losses.append(LossEvent(
                    code="rounding",
                    severity=LossSeverity.INFO,
                    source_protocol=source_protocol,
                    target_protocol=self.protocol_name,
                    message=f"valor arredondado de {raw} para {rounded} ao converter para {binding.data_type}",
                    field="value",
                    source_value=raw,
                    target_value=rounded,
                    affected_value=raw,
                ))
            minimum, maximum = TYPE_RANGES[binding.data_type]
            if not (minimum <= rounded <= maximum):
                losses.append(LossEvent(
                    code="overflow",
                    severity=LossSeverity.ERROR,
                    source_protocol=source_protocol,
                    target_protocol=self.protocol_name,
                    message=f"valor {rounded} fora da faixa representável [{minimum}, {maximum}] do tipo {binding.data_type}",
                    field="value",
                    source_value=engineering,
                    target_value=rounded,
                    affected_value=rounded,
                ))
            raw = rounded
        elif binding.data_type == "float":
            raw = float(raw)
        return raw, losses

    def _convert_non_numeric(self, engineering: Any, binding: ProtocolBinding, source_protocol: str) -> Tuple[Any, List[LossEvent]]:
        if binding.data_type == "bool":
            return bool(engineering), []
        if binding.data_type == "string":
            return str(engineering), []
        return engineering, []

    def publish_failure(self, point: CanonicalPoint, binding: ProtocolBinding, reason: str) -> Dict[str, Any]:
        return self._build_failure_payload(point, binding, reason)

    def _build_failure_payload(self, point: CanonicalPoint, binding: ProtocolBinding, reason: str) -> Dict[str, Any]:
        loss = LossEvent(
            code="generic_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=reason,
            field="communication",
            source_value=point.value,
            target_value=None,
        )
        return {
            "address": binding.address,
            "written_value": None,
            "losses": [loss.as_dict()],
        }
