#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gateway.adapters.factory import build_default_adapters
from gateway.domain.canonical import Validity
from gateway.engine.engine import GatewayEngine
from gateway.registry.binding import ProtocolBinding
from gateway.registry.exceptions import BindingNotFoundError, MappingNotFoundError, ValidationError
from gateway.registry.mapping import PointMapping
from gateway.registry.registry import MappingRegistry

DATA_FILE = Path(__file__).parent / "data" / "mappings.json"

PASSED = 0
FAILED = 0


def check(name, condition, detail="") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}")
    else:
        FAILED += 1
        print(f"[FAIL] {name}  {detail}")


def build_engine() -> GatewayEngine:
    registry = MappingRegistry()
    registry.load(str(DATA_FILE))
    adapters = build_default_adapters()
    return GatewayEngine(registry, adapters)


def test_example_1_mms_to_modbus() -> None:
    engine = build_engine()
    report = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    check(
        "exemplo1: valor canônico em V (13800.0)",
        abs(report.canonical.value - 13800.0) < 1e-6,
        report.canonical.value,
    )
    check("exemplo1: unidade canônica é 'V'", report.canonical.unit == "V")
    check(
        "exemplo1: qualidade GOOD sem flags",
        report.canonical.quality.validity == Validity.GOOD and not report.canonical.quality.flags,
    )
    modbus = report.targets["modbus"]
    check("exemplo1: registrador modbus = 138", modbus["written_value"] == 138, modbus["written_value"])
    check(
        "exemplo1: perda de qualidade reportada",
        any("qualidade" in loss["message"] for loss in modbus["losses"]),
        modbus["losses"],
    )
    check(
        "exemplo1: perda de estampa de tempo reportada",
        any("estampa de tempo" in loss["message"] for loss in modbus["losses"]),
        modbus["losses"],
    )
    check("exemplo1: modbus não expõe qualidade no payload publicado", "quality" not in modbus)


def test_example_2_dnp3_to_opcua() -> None:
    engine = build_engine()
    report = engine.convert("FDR02.AI12", "dnp3", ["opcua"])
    check(
        "exemplo2: valor canônico em A (502.3)",
        abs(report.canonical.value - 502.3) < 1e-6,
        report.canonical.value,
    )
    opcua = report.targets["opcua"]
    check(
        "exemplo2: valor publicado em OPC UA = 502.3",
        abs(opcua["written_value"] - 502.3) < 1e-6,
        opcua["written_value"],
    )
    check("exemplo2: nenhuma perda de metadados", opcua["losses"] == [], opcua["losses"])
    check("exemplo2: opcua expõe qualidade no payload publicado", "quality" in opcua)
    check("exemplo2: opcua expõe timestamp no payload publicado", "timestamp" in opcua)


def test_comm_loss() -> None:
    engine = build_engine()
    engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    engine.adapters["mms"].connected = False
    report = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"])
    check("falha: leitura reporta falha", report.failure is not None)
    check("falha: qualidade canônica INVALID", report.canonical.quality.validity == Validity.INVALID)
    check("falha: flag comm_lost presente", "comm_lost" in report.canonical.quality.flags)
    check(
        "falha: valor congelado no último bom (13800.0)",
        abs(report.canonical.value - 13800.0) < 1e-6,
    )
    modbus = report.targets["modbus"]
    check("falha: modbus reporta perda por falta de canal de status", len(modbus["losses"]) > 0)
    opcua = report.targets["opcua"]
    check(
        "falha: opcua sem binding neste ponto retorna erro isolado (não derruba o resto)",
        "error" in opcua,
        opcua,
    )


def test_invalid_config_rejected() -> None:
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


def test_binding_protocol_mismatch_rejected() -> None:
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.KEY",
        bindings={
            "dnp3": ProtocolBinding(protocol="opcua", address="BI99", data_type="bool", unit=""),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="bool", unit=""),
        },
    )
    try:
        registry.add(bad)
        check("chave x protocolo: deveria ter sido rejeitada", False)
    except ValidationError:
        check("chave x protocolo: rejeitada corretamente", True)


def test_zero_scale_rejected() -> None:
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.SCALE",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="BI99", data_type="float", unit="A", scale=0.0),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="A"),
        },
    )
    try:
        registry.add(bad)
        check("escala zero: deveria ter sido rejeitada", False)
    except ValidationError:
        check("escala zero: rejeitada corretamente", True)


def test_overflow_detected_on_publish() -> None:
    engine = build_engine()
    registry = engine.registry
    registry.add(
        PointMapping(
            point_id="OVERFLOW.POINT",
            bindings={
                "dnp3": ProtocolBinding(protocol="dnp3", address="AI:99", data_type="float", unit="A", raw_value=999999.0),
                "modbus": ProtocolBinding(protocol="modbus", address="40099", data_type="int", unit="A"),
            },
        )
    )
    report = engine.convert("OVERFLOW.POINT", "dnp3", ["modbus"])
    modbus = report.targets["modbus"]
    check(
        "overflow: perda reportada ao publicar inteiro fora de faixa",
        any(loss["code"] == "overflow" for loss in modbus["losses"]),
        modbus["losses"],
    )


def test_opcua_status_code_severity() -> None:
    engine = build_engine()
    report = engine.convert("FDR02.AI12", "dnp3", ["opcua"])
    opcua = report.targets["opcua"]
    check(
        "opcua: severidade do StatusCode reportada como 'Good'",
        opcua.get("status_code_severity") == "Good",
        opcua.get("status_code_severity"),
    )


def test_mms_iec61850_validity_code() -> None:
    engine = build_engine()
    report = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    check(
        "mms: validity lida como GOOD antes de qualquer publish em MMS",
        report.canonical.quality.validity == Validity.GOOD,
    )


def test_dnp3_flags_reflect_comm_loss() -> None:
    engine = build_engine()
    engine.registry.add(
        PointMapping(
            point_id="DNP3.ECHO",
            bindings={
                "dnp3": ProtocolBinding(protocol="dnp3", address="AI:50", data_type="float", unit="A", raw_value=10.0),
                "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Echo", data_type="float", unit="A"),
            },
        )
    )
    engine.adapters["dnp3"].connected = False
    engine.convert("DNP3.ECHO", "dnp3", ["opcua"])
    engine.adapters["dnp3"].connected = True
    report = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    check("dnp3: engine seguiu funcionando após religar o adaptador", report.failure is None)


def test_unknown_point() -> None:
    engine = build_engine()
    try:
        engine.convert("NAO.EXISTE", "mms", ["modbus"])
        check("ponto desconhecido: deveria levantar MappingNotFoundError", False)
    except MappingNotFoundError:
        check("ponto desconhecido: MappingNotFoundError levantado corretamente", True)


def test_unknown_source_binding() -> None:
    engine = build_engine()
    try:
        engine.convert("SE01.MMXU1.PhV.phsA", "opcua", ["modbus"])
        check("binding de origem inexistente: deveria levantar BindingNotFoundError", False)
    except BindingNotFoundError:
        check("binding de origem inexistente: BindingNotFoundError levantado corretamente", True)


def main() -> None:
    test_example_1_mms_to_modbus()
    test_example_2_dnp3_to_opcua()
    test_comm_loss()
    test_invalid_config_rejected()
    test_binding_protocol_mismatch_rejected()
    test_zero_scale_rejected()
    test_overflow_detected_on_publish()
    test_opcua_status_code_severity()
    test_mms_iec61850_validity_code()
    test_dnp3_flags_reflect_comm_loss()
    test_unknown_point()
    test_unknown_source_binding()
    print()
    print(f"Total: {PASSED} passaram, {FAILED} falharam")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()