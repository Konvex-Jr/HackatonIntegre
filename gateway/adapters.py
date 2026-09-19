"""Adaptadores: a única camada que, num sistema real, importaria
bibliotecas de protocolo industrial (libiec61850, pydnp3, pymodbus,
open62541...). Aqui elas são simuladas, para manter o exemplo
autocontido e o núcleo livre de qualquer dependência de protocolo.

Cada adaptador sabe ler seu protocolo nativo e produzir um
CanonicalPoint, e sabe publicar um CanonicalPoint no seu protocolo
nativo — nada além disso vaza para o resto do sistema. Adicionar um
novo protocolo é só criar uma nova subclasse.
"""

from abc import ABC
from datetime import datetime, timezone
from typing import Dict, Any

from .canonical import CanonicalPoint, Quality, Timestamp, Validity
from .registry import ProtocolBinding
from .units import canonical_unit, to_base, from_base


class ProtocolAdapter(ABC):
    protocol_name: str = "base"
    supports_quality: bool = True
    supports_timestamp: bool = True

    def __init__(self):
        self.connected = True  # liga/desliga para simular perda de comunicação

    # ---- leitura (papel de origem) -------------------------------------
    def read(self, binding: ProtocolBinding, point_id: str) -> CanonicalPoint:
        if not self.connected:
            raise ConnectionError(
                f"[{self.protocol_name}] comunicação indisponível ao ler '{point_id}'"
            )
        raw = binding.raw_value if binding.raw_value is not None else 0
        engineering = raw * binding.scale + binding.offset
        value_base = to_base(engineering, binding.unit)
        quality = Quality(validity=Validity.GOOD)
        sync = "synchronized" if self.supports_timestamp else "unsynchronized"
        timestamp = Timestamp(value_utc=datetime.now(timezone.utc), sync_source=sync)
        return CanonicalPoint(
            point_id=point_id,
            value=value_base,
            data_type=binding.data_type,
            unit=canonical_unit(binding.unit),
            quality=quality,
            timestamp=timestamp,
            source_protocol=self.protocol_name,
            source_raw={"address": binding.address, "raw": raw},
        )

    # ---- publicação (papel de destino) --------------------------------
    def publish(self, point: CanonicalPoint, binding: ProtocolBinding) -> Dict[str, Any]:
        losses = []
        if not self.supports_quality:
            losses.append(
                f"[{self.protocol_name}] protocolo de destino não representa "
                f"qualidade nativamente (origem trazia: {point.quality})"
            )
        if not self.supports_timestamp:
            losses.append(
                f"[{self.protocol_name}] protocolo de destino não representa "
                f"estampa de tempo nativamente (origem trazia: {point.timestamp})"
            )
        engineering = from_base(point.value, binding.unit)
        raw = (engineering - binding.offset) / binding.scale if binding.scale else engineering
        if binding.data_type == "int":
            raw = round(raw)
        return {"address": binding.address, "written_value": raw, "losses": losses}

    # ---- publicação de um estado de falha -------------------------------
    def publish_failure(self, point: CanonicalPoint, binding: ProtocolBinding, reason: str) -> Dict[str, Any]:
        return {
            "address": binding.address,
            "written_value": None,
            "losses": [f"[{self.protocol_name}] falha genérica não tratada especificamente: {reason}"],
        }


class MMSAdapter(ProtocolAdapter):
    protocol_name = "mms"
    supports_quality = True
    supports_timestamp = True

    def publish_failure(self, point, binding, reason):
        return {
            "address": binding.address,
            "written_value": "Quality.validity=invalid, detailQual=oldData",
            "losses": [f"Objeto MMS marcado com Quality inválida/oldData ({reason})"],
        }


class Dnp3Adapter(ProtocolAdapter):
    protocol_name = "dnp3"
    supports_quality = True
    supports_timestamp = True

    def publish_failure(self, point, binding, reason):
        return {
            "address": binding.address,
            "written_value": "flags |= COMM_LOST",
            "losses": [
                f"Bit COMM_LOST setado nos flags do objeto DNP3; evento "
                f"Class 1 gerado ({reason})"
            ],
        }


class OpcUaAdapter(ProtocolAdapter):
    protocol_name = "opcua"
    supports_quality = True
    supports_timestamp = True

    def publish_failure(self, point, binding, reason):
        return {
            "address": binding.address,
            "written_value": "StatusCode=Bad_CommunicationFailure",
            "losses": [
                f"StatusCode alterado para Bad_CommunicationFailure; "
                f"SourceTimestamp mantido congelado no último valor bom ({reason})"
            ],
        }


class ModbusAdapter(ProtocolAdapter):
    protocol_name = "modbus"
    supports_quality = False
    supports_timestamp = False

    def publish_failure(self, point, binding, reason):
        return {
            "address": binding.address,
            "written_value": "valor mantido congelado no registrador",
            "losses": [
                f"Modbus não tem canal nativo de qualidade/estampa de tempo; "
                f"usando convenção de coil de status separado para refletir "
                f"a falha ({reason}). Um master que não leia esse coil não "
                f"perceberá a falha."
            ],
        }


ADAPTER_CLASSES = {
    "mms": MMSAdapter,
    "dnp3": Dnp3Adapter,
    "opcua": OpcUaAdapter,
    "modbus": ModbusAdapter,
}


def build_default_adapters() -> Dict[str, ProtocolAdapter]:
    return {name: cls() for name, cls in ADAPTER_CLASSES.items()}
