from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class Dnp3Adapter(ProtocolAdapter):
    protocol_name = "dnp3"
    supports_quality = True
    supports_timestamp = True

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="dnp3_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=(
                f"Bit COMM_LOST setado nos flags do objeto DNP3; "
                f"evento Class 1 gerado ({reason})"
            ),
        )
        return {
            "address": binding.address,
            "written_value": "flags |= COMM_LOST",
            "losses": [loss.as_dict()],
        }
