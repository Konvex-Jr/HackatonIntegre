#!/usr/bin/env python3
"""Testes do gateway, executados via terminal (sem framework externo,
só para manter a coisa o mais simples possível).

Uso:
    python tests.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gateway.registry import MappingRegistry, PointMapping, ProtocolBinding, ValidationError
from gateway.adapters import build_default_adapters
from gateway.engine import GatewayEngine
from gateway.canonical import Validity

DATA_FILE = Path(__file__).parent / "data" / "mappings.json"

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}")
    else:
        FAILED += 1
        print(f"[FAIL] {name}  {detail}")


def build_engine():
    registry = MappingRegistry()
    registry.load(str(DATA_FILE))
    adapters = build_default_adapters()
    return GatewayEngine(registry, adapters)


def test_example_1_mms_to_modbus():
    engine = build_engine()
    r = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    check("exemplo1: valor canônico em V (13800.0)",
          abs(r.canonical.value - 13800.0) < 1e-6, r.canonical.value)
    check("exemplo1: unidade canônica é 'V'", r.canonical.unit == "V")
    check("exemplo1: qualidade GOOD sem flags",
          r.canonical.quality.validity == Validity.GOOD and not r.canonical.quality.flags)
    modbus = r.targets["modbus"]
    check("exemplo1: registrador modbus = 138",
          modbus["written_value"] == 138, modbus["written_value"])
    check("exemplo1: perda de qualidade reportada",
          any("qualidade" in l for l in modbus["losses"]), modbus["losses"])
    check("exemplo1: perda de estampa de tempo reportada",
          any("estampa de tempo" in l for l in modbus["losses"]), modbus["losses"])


def test_example_2_dnp3_to_opcua():
    engine = build_engine()
    r = engine.convert("FDR02.AI12", "dnp3", ["opcua"])
    check("exemplo2: valor canônico em A (502.3)",
          abs(r.canonical.value - 502.3) < 1e-6, r.canonical.value)
    opcua = r.targets["opcua"]
    check("exemplo2: valor publicado em OPC UA = 502.3",
          abs(opcua["written_value"] - 502.3) < 1e-6, opcua["written_value"])
    check("exemplo2: nenhuma perda de metadados", opcua["losses"] == [], opcua["losses"])


def test_comm_loss():
    engine = build_engine()
    engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])  # popula último valor bom
    engine.adapters["mms"].connected = False
    r = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"])
    check("falha: leitura reporta falha", r.failure is not None)
    check("falha: qualidade canônica INVALID", r.canonical.quality.validity == Validity.INVALID)
    check("falha: flag comm_lost presente", "comm_lost" in r.canonical.quality.flags)
    check("falha: valor congelado no último bom (13800.0)",
          abs(r.canonical.value - 13800.0) < 1e-6)
    modbus = r.targets["modbus"]
    check("falha: modbus reporta perda por falta de canal de status",
          len(modbus["losses"]) > 0)
    opcua = r.targets["opcua"]
    check("falha: opcua sem binding neste ponto retorna erro isolado (não derruba o resto)",
          "error" in opcua, opcua)


def test_invalid_config_rejected():
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.POINT",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="BI99", data_type="bool", unit="", raw_value=True),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="V", raw_value=1.0),
        },
    )
    try:
        registry.add(bad)
        check("config inválida: deveria ter sido rejeitada", False)
    except ValidationError:
        check("config inválida: rejeitada corretamente", True)


def test_unknown_point():
    engine = build_engine()
    try:
        engine.convert("NAO.EXISTE", "mms", ["modbus"])
        check("ponto desconhecido: deveria levantar KeyError", False)
    except KeyError:
        check("ponto desconhecido: KeyError levantado corretamente", True)


def main():
    test_example_1_mms_to_modbus()
    test_example_2_dnp3_to_opcua()
    test_comm_loss()
    test_invalid_config_rejected()
    test_unknown_point()
    print()
    print(f"Total: {PASSED} passaram, {FAILED} falharam")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
