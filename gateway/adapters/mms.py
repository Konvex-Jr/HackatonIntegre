from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class MMSAdapter(ProtocolAdapter):
    protocol_name = "mms"
    supports_quality = True
    supports_timestamp = True

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="mms_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"Objeto MMS marcado com Quality inválida/oldData ({reason})",
        )
        return {
            "address": binding.address,
            "written_value": "Quality.validity=invalid, detailQual=oldData",
            "losses": [loss.as_dict()],
        }
