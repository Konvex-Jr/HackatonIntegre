from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity, Validity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


STATUS_CODE = {
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
        payload["status_code"] = STATUS_CODE.get(point.quality.validity, "Bad")
        payload["opcua"] = {
            "node_id": binding.address,
            "namespace": binding.protocol_metadata.get("namespace"),
            "identifier_type": binding.protocol_metadata.get("identifier_type"),
            "browse_name": binding.protocol_metadata.get("browse_name"),
            "encoding": binding.encoding or "UA Binary",
        }
        payload["source_metadata"] = {
            "source_protocol": point.source_protocol,
            "source_address": point.source_address,
            "source_metadata": point.source_metadata,
        }
        return payload

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="opcua_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"StatusCode refletido como Bad_CommunicationFailure ({reason})",
            field="status_code",
            source_value=point.quality.as_dict(),
            target_value="Bad_CommunicationFailure",
        )
        return {
            "address": binding.address,
            "written_value": None,
            "status_code": "Bad_CommunicationFailure",
            "timestamp": point.timestamp.as_dict(),
            "opcua": {
                "node_id": binding.address,
                "namespace": binding.protocol_metadata.get("namespace"),
                "identifier_type": binding.protocol_metadata.get("identifier_type"),
                "browse_name": binding.protocol_metadata.get("browse_name"),
                "encoding": binding.encoding or "UA Binary",
            },
            "losses": [loss.as_dict()],
        }
