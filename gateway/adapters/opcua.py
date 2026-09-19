from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity, Validity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter

# Mapeamento da validade canônica para a severidade de StatusCode do OPC UA
# (OPC UA Part 8: Good / Uncertain / Bad).
_STATUS_CODE_SEVERITY = {
    Validity.GOOD: "Good",
    Validity.QUESTIONABLE: "Uncertain",
    Validity.INVALID: "Bad",
}


class OpcUaAdapter(ProtocolAdapter):
    protocol_name = "opcua"
    supports_quality = True
    supports_timestamp = True

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        payload = super().publish(point, binding)
        payload["status_code_severity"] = _STATUS_CODE_SEVERITY.get(
            point.quality.validity, "Bad"
        )
        return payload

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="opcua_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=(
                f"StatusCode alterado para Bad_CommunicationFailure; "
                f"SourceTimestamp mantido congelado no último valor bom ({reason})"
            ),
        )
        return {
            "address": binding.address,
            "written_value": "StatusCode=Bad_CommunicationFailure",
            "status_code_severity": "Bad",
            "losses": [loss.as_dict()],
        }
