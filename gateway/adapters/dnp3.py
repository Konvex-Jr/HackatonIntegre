from typing import Any, Dict, List

from ..domain.canonical import CanonicalPoint, LossEvent, LossSeverity, Validity
from ..registry.binding import ProtocolBinding
from .base import ProtocolAdapter


class Dnp3Adapter(ProtocolAdapter):
    protocol_name = "dnp3"
    supports_quality = True
    supports_timestamp = True

    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        payload = super().publish(point, binding)
        dnp3 = {
            "group": binding.protocol_metadata.get("group"),
            "variation": binding.protocol_metadata.get("variation"),
            "index": binding.protocol_metadata.get("index"),
            "event_class": binding.protocol_metadata.get("event_class"),
            "flags": self._native_flags(point),
            "encoding": binding.encoding,
        }
        variation = binding.protocol_metadata.get("variation")
        if variation in {3, 4, 5, 6}:
            payload.pop("timestamp", None)
        payload["dnp3"] = dnp3
        losses = self._native_flag_losses(point)
        payload["losses"].extend(loss.as_dict() for loss in losses)
        return payload

    def _native_flags(self, point: CanonicalPoint) -> List[str]:
        flags: List[str] = []
        if point.quality.validity == Validity.GOOD and "comm_lost" not in point.quality.flags:
            flags.append("ONLINE")
        else:
            flags.append("OFFLINE")
        mapping = {
            "comm_lost": "COMM_LOST",
            "forced": "FORCED",
            "out_of_range": "OVER_RANGE",
            "overflow": "OVER_RANGE",
        }
        for flag in sorted(point.quality.flags):
            native = mapping.get(flag)
            if native and native not in flags:
                flags.append(native)
        return flags

    def _native_flag_losses(self, point: CanonicalPoint) -> List[LossEvent]:
        representable = {"comm_lost", "forced", "out_of_range", "overflow"}
        losses: List[LossEvent] = []
        for flag in sorted(point.quality.flags - representable):
            losses.append(LossEvent(
                code="dnp3_quality_flag_unsupported",
                severity=LossSeverity.WARNING,
                source_protocol=point.source_protocol,
                target_protocol=self.protocol_name,
                message=f"flag de qualidade '{flag}' não possui representação nativa equivalente no DNP3",
                field="quality.flags",
                source_value=flag,
                target_value=None,
            ))
        return losses

    def _build_failure_payload(
        self, point: CanonicalPoint, binding: ProtocolBinding, reason: str
    ) -> Dict[str, Any]:
        loss = LossEvent(
            code="dnp3_comm_lost",
            severity=LossSeverity.ERROR,
            source_protocol=point.source_protocol,
            target_protocol=self.protocol_name,
            message=f"COMM_LOST refletido nos flags do ponto DNP3 ({reason})",
            field="quality.flags",
            source_value=point.quality.as_dict(),
            target_value={"COMM_LOST": True},
        )
        return {
            "address": binding.address,
            "written_value": None,
            "quality": point.quality.as_dict(),
            "timestamp": point.timestamp.as_dict(),
            "dnp3": {
                "group": binding.protocol_metadata.get("group"),
                "variation": binding.protocol_metadata.get("variation"),
                "index": binding.protocol_metadata.get("index"),
                "event_class": binding.protocol_metadata.get("event_class"),
                "flags": ["OFFLINE", "COMM_LOST"],
                "encoding": binding.encoding,
            },
            "losses": [loss.as_dict()],
        }
