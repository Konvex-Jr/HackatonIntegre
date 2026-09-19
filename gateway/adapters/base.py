from abc import ABC
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity, Quality, Timestamp, Validity
from ..registry.binding import ProtocolBinding
from ..units.conversion import canonical_unit, from_base, to_base
from ..units.tables import INT_RANGE
from .resilience import CircuitBreaker, retry_with_backoff


class ProtocolAdapter(ABC):
    protocol_name: str = "base"
    supports_quality: bool = True
    supports_timestamp: bool = True

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
        engineering = raw * binding.scale + binding.offset
        value_base = to_base(engineering, binding.unit)
        return CanonicalPoint(
            point_id=point_id,
            value=value_base,
            data_type=binding.data_type,
            unit=canonical_unit(binding.unit),
            quality=self._build_quality_from_binding(binding),
            timestamp=self._build_timestamp_from_binding(),
            source_protocol=self.protocol_name,
            source_raw={"address": binding.address, "raw": raw},
        )

    def _build_quality_from_binding(self, binding: ProtocolBinding) -> Quality:
        validity = Validity(binding.native_validity) if binding.native_validity else Validity.GOOD
        quality = Quality(validity=validity)
        for flag in binding.native_quality_flags:
            quality.add_flag(flag)
        return quality

    def _build_timestamp_from_binding(self) -> Timestamp:
        sync = "synchronized" if self.supports_timestamp else "unsynchronized"
        return Timestamp(value_utc=datetime.now(timezone.utc), sync_source=sync)

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        losses = self._detect_metadata_losses(point)
        engineering = from_base(point.value, binding.unit)
        raw, conversion_losses = self._convert_to_raw(engineering, binding, point.source_protocol)
        losses.extend(conversion_losses)
        payload: Dict[str, Any] = {
            "address": binding.address,
            "written_value": raw,
            "losses": [loss.as_dict() for loss in losses],
        }
        if self.supports_quality:
            payload["quality"] = point.quality.as_dict()
        if self.supports_timestamp:
            payload["timestamp"] = point.timestamp.as_dict()
        return payload

    def _detect_metadata_losses(self, point: CanonicalPoint) -> List[LossEvent]:
        losses: List[LossEvent] = []
        if not self.supports_quality:
            losses.append(LossEvent(
                code="quality_unsupported",
                severity=LossSeverity.WARNING,
                source_protocol=point.source_protocol,
                target_protocol=self.protocol_name,
                message=(
                    f"protocolo de destino não representa qualidade nativamente "
                    f"(origem trazia: {point.quality})"
                ),
            ))
        if not self.supports_timestamp:
            losses.append(LossEvent(
                code="timestamp_unsupported",
                severity=LossSeverity.WARNING,
                source_protocol=point.source_protocol,
                target_protocol=self.protocol_name,
                message=(
                    f"protocolo de destino não representa estampa de tempo nativamente "
                    f"(origem trazia: {point.timestamp})"
                ),
            ))
        return losses

    def _convert_to_raw(
        self, engineering: float, binding: ProtocolBinding, source_protocol: str
    ) -> Tuple[Any, List[LossEvent]]:
        losses: List[LossEvent] = []
        raw = (engineering - binding.offset) / binding.scale if binding.scale else engineering

        if binding.min_engineering is not None and engineering < binding.min_engineering:
            losses.append(LossEvent(
                code="out_of_range",
                severity=LossSeverity.ERROR,
                source_protocol=source_protocol,
                target_protocol=self.protocol_name,
                message=(
                    f"valor de engenharia {engineering} abaixo do mínimo "
                    f"permitido {binding.min_engineering}"
                ),
                affected_value=engineering,
            ))
        if binding.max_engineering is not None and engineering > binding.max_engineering:
            losses.append(LossEvent(
                code="out_of_range",
                severity=LossSeverity.ERROR,
                source_protocol=source_protocol,
                target_protocol=self.protocol_name,
                message=(
                    f"valor de engenharia {engineering} acima do máximo "
                    f"permitido {binding.max_engineering}"
                ),
                affected_value=engineering,
            ))

        if binding.data_type == "int":
            rounded = round(raw)
            if abs(rounded - raw) > 1e-9:
                losses.append(LossEvent(
                    code="rounding",
                    severity=LossSeverity.INFO,
                    source_protocol=source_protocol,
                    target_protocol=self.protocol_name,
                    message=f"valor arredondado de {raw} para {rounded} ao converter para inteiro",
                    affected_value=raw,
                ))
            if not (INT_RANGE[0] <= rounded <= INT_RANGE[1]):
                losses.append(LossEvent(
                    code="overflow",
                    severity=LossSeverity.ERROR,
                    source_protocol=source_protocol,
                    target_protocol=self.protocol_name,
                    message=(
                        f"valor {rounded} fora da faixa representável "
                        f"[{INT_RANGE[0]}, {INT_RANGE[1]}] do tipo inteiro"
                    ),
                    affected_value=rounded,
                ))
            raw = rounded

        return raw, losses

    def publish_failure(self, point: CanonicalPoint, binding: ProtocolBinding, reason: str) -> Dict[str, Any]:
        return self._build_failure_payload(point, binding, reason)

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="generic_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"falha genérica não tratada especificamente: {reason}",
        )
        return {
            "address": binding.address,
            "written_value": None,
            "losses": [loss.as_dict()],
        }
