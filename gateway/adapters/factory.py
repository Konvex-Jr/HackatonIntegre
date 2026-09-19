from typing import Dict

from .base import ProtocolAdapter
from .dnp3 import Dnp3Adapter
from .mms import MMSAdapter
from .modbus import ModbusAdapter
from .opcua import OpcUaAdapter

ADAPTER_CLASSES = {
    "mms": MMSAdapter,
    "dnp3": Dnp3Adapter,
    "opcua": OpcUaAdapter,
    "modbus": ModbusAdapter,
}


def build_default_adapters() -> Dict[str, ProtocolAdapter]:
    return {name: adapter_class() for name, adapter_class in ADAPTER_CLASSES.items()}
