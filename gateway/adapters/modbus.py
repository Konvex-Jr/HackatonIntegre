from typing import Any, Dict

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class ModbusAdapter(ProtocolAdapter):
    protocol_name = "modbus"
    supports_quality = False
    supports_timestamp = False

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        payload = super().publish(point, binding)
        payload["modbus"] = {
            "function_code": binding.protocol_metadata.get("function_code"),
            "register": binding.protocol_metadata.get("register"),
            "register_count": binding.protocol_metadata.get("register_count", 1),
            "transport": binding.protocol_metadata.get("transport", "mbap/tcp"),
            "port": binding.protocol_metadata.get("port", 502),
            "security": binding.protocol_metadata.get("security", "plain"),
        }
        if binding.protocol_metadata.get("security") == "tls":
            payload["modbus"]["port"] = binding.protocol_metadata.get("port", 802)
            payload["modbus"]["tls"] = {
                "version": binding.protocol_metadata.get("tls_version", "TLS 1.2"),
                "mutual_authentication": binding.protocol_metadata.get("mutual_authentication", True),
                "certificate_authentication": binding.protocol_metadata.get("certificate_authentication", True),
                "role_authorization": binding.protocol_metadata.get("role_authorization", True),
            }
        return payload

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="modbus_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"não é possível publicar o valor enquanto a comunicação da origem está indisponível ({reason})",
            field="communication",
            source_value=point.value,
            target_value=None,
        )
        payload = {
            "address": binding.address,
            "written_value": None,
            "modbus": {
                "function_code": binding.protocol_metadata.get("function_code"),
                "register": binding.protocol_metadata.get("register"),
                "register_count": binding.protocol_metadata.get("register_count", 1),
                "transport": binding.protocol_metadata.get("transport", "mbap/tcp"),
                "port": binding.protocol_metadata.get("port", 502),
                "security": binding.protocol_metadata.get("security", "plain"),
            },
            "losses": [loss.as_dict()],
        }
        status_coil = binding.protocol_metadata.get("status_coil")
        if status_coil:
            payload["modbus"]["status_coil"] = {
                "address": status_coil,
                "value": True,
                "meaning": "source_communication_lost",
            }
        return payload
