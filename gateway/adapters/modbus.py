from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class ModbusAdapter(ProtocolAdapter):
    protocol_name = "modbus"
    supports_quality = False
    supports_timestamp = False

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="modbus_comm_lost",
            severity=LossSeverity.WARNING,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=(
                f"Modbus não tem canal nativo de qualidade/estampa de tempo; usando "
                f"convenção de coil de status separado para refletir a falha ({reason}). "
                f"Um master que não leia esse coil não perceberá a falha."
            ),
        )
        return {
            "address": binding.address,
            "written_value": "valor mantido congelado no registrador",
            "losses": [loss.as_dict()],
        }
