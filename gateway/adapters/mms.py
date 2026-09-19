from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class MMSAdapter(ProtocolAdapter):
    protocol_name = "mms"
    supports_quality = True
    supports_timestamp = True

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        payload = super().publish(point, binding)
        payload["mms"] = {
            "object_reference": binding.address,
            "encoding": binding.encoding or "BER",
            "functional_constraint": binding.protocol_metadata.get("functional_constraint"),
        }
        return payload

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="mms_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"falha na comunicação MMS; último valor permanece com qualidade inválida ({reason})",
            field="communication",
            source_value=point.value,
            target_value=None,
        )
        return {
            "address": binding.address,
            "written_value": None,
            "quality": point.quality.as_dict(),
            "timestamp": point.timestamp.as_dict(),
            "mms": {
                "object_reference": binding.address,
                "encoding": binding.encoding or "BER",
                "functional_constraint": binding.protocol_metadata.get("functional_constraint"),
            },
            "losses": [loss.as_dict()],
        }
