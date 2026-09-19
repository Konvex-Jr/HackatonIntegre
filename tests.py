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
    return GatewayEngine(registry, build_default_adapters())


def test_example_1_mms_to_modbus():
    report = build_engine().convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    check("mms->modbus: valor canônico 13800 V", abs(report.canonical.value - 13800.0) < 1e-6)
    check("mms->modbus: unidade canônica V", report.canonical.unit == "V")
    check("mms->modbus: timestamp veio da origem", report.canonical.timestamp.sync_source == "source")
    modbus = report.targets["modbus"]
    check("mms->modbus: raw 138", modbus["written_value"] == 138)
    check("mms->modbus: qualidade não representável", any(x["code"] == "quality_unsupported" for x in modbus["losses"]))
    check("mms->modbus: timestamp não representável", any(x["code"] == "timestamp_unsupported" for x in modbus["losses"]))


def test_example_2_dnp3_to_opcua():
    report = build_engine().convert("FDR02.AI12", "dnp3", ["opcua"])
    opcua = report.targets["opcua"]
    check("dnp3->opcua: valor 502.3 A", abs(report.canonical.value - 502.3) < 1e-6)
    check("dnp3->opcua: valor publicado 502.3", abs(opcua["written_value"] - 502.3) < 1e-6)
    check("dnp3->opcua: status Good", opcua["status_code"] == "Good")
    check("dnp3->opcua: timestamp preservado", opcua["timestamp"]["value_utc"].startswith("2026-09-19T10:31:42.125"))
    check("dnp3->opcua: metadados de origem preservados", opcua["source_metadata"]["source_metadata"]["group"] == 32)
    check("dnp3->opcua: sem perda canônica", opcua["losses"] == [])


def test_all_destinations_are_registered():
    engine = build_engine()
    for point_id in ["SE01.MMXU1.PhV.phsA", "FDR02.AI12"]:
        mapping = engine.registry.get(point_id)
        check(f"{point_id}: quatro protocolos cadastrados", set(mapping.bindings) == {"mms", "dnp3", "modbus", "opcua"})


def test_comm_loss():
    engine = build_engine()
    engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    engine.adapters["mms"].connected = False
    report = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"])
    check("falha: origem marcada como inválida", report.canonical.quality.validity == Validity.INVALID)
    check("falha: comm_lost presente", "comm_lost" in report.canonical.quality.flags)
    check("falha: stale presente", "stale" in report.canonical.quality.flags)
    check("falha: último valor mantido", abs(report.canonical.value - 13800.0) < 1e-6)
    check("falha: modbus sem valor escrito", report.targets["modbus"]["written_value"] is None)
    check("falha: modbus status coil configurado", report.targets["modbus"]["modbus"]["status_coil"]["value"] is True)
    check("falha: opcua Bad_CommunicationFailure", report.targets["opcua"]["status_code"] == "Bad_CommunicationFailure")


def test_invalid_config_rejected():
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.POINT",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="BI99", data_type="bool", unit="", protocol_metadata={"group": 1, "variation": 1, "index": 99}),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="V", protocol_metadata={"namespace": 2, "identifier_type": "s"}),
        },
    )
    try:
        registry.add(bad)
        check("config inválida: rejeitada", False)
    except ValidationError:
        check("config inválida: rejeitada", True)


def test_binding_protocol_mismatch_rejected():
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.KEY",
        bindings={
            "dnp3": ProtocolBinding(protocol="opcua", address="BI99", data_type="float", unit="A", protocol_metadata={}),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="A", protocol_metadata={"namespace": 2, "identifier_type": "s"}),
        },
    )
    try:
        registry.add(bad)
        check("chave x protocolo: rejeitada", False)
    except ValidationError:
        check("chave x protocolo: rejeitada", True)


def test_zero_scale_rejected():
    registry = MappingRegistry()
    bad = PointMapping(
        point_id="BAD.SCALE",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="AI:99", data_type="float", unit="A", scale=0.0, protocol_metadata={"group": 30, "variation": 5, "index": 99}),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="A", protocol_metadata={"namespace": 2, "identifier_type": "s"}),
        },
    )
    try:
        registry.add(bad)
        check("escala zero: rejeitada", False)
    except ValidationError:
        check("escala zero: rejeitada", True)


def test_overflow_detected_on_publish():
    engine = build_engine()
    engine.registry.add(
        PointMapping(
            point_id="OVERFLOW.POINT",
            bindings={
                "dnp3": ProtocolBinding(protocol="dnp3", address="AI:99", data_type="float", unit="A", raw_value=999999.0, protocol_metadata={"group": 30, "variation": 5, "index": 99}),
                "modbus": ProtocolBinding(protocol="modbus", address="40099", data_type="uint8", unit="A", protocol_metadata={"function_code": 3, "register": 40099}),
            },
        )
    )
    report = engine.convert("OVERFLOW.POINT", "dnp3", ["modbus"])
    check("overflow: reportado", any(x["code"] == "overflow" for x in report.targets["modbus"]["losses"]))


def test_all_dnp3_native_metadata():
    mapping = build_engine().registry.get("FDR02.AI12")
    dnp3 = mapping.bindings["dnp3"]
    check("dnp3: group 32 para evento analógico", dnp3.protocol_metadata["group"] == 32)
    check("dnp3: variation 7 inclui float e event time", dnp3.protocol_metadata["variation"] == 7)
    check("dnp3: index preservado", dnp3.protocol_metadata["index"] == 12)


def test_mms_native_metadata():
    mapping = build_engine().registry.get("SE01.MMXU1.PhV.phsA")
    mms = mapping.bindings["mms"]
    check("mms: logical node preservado", mms.protocol_metadata["logical_node"] == "MMXU1")
    check("mms: functional constraint MX", mms.protocol_metadata["functional_constraint"] == "MX")
    check("mms: BER configurado", mms.encoding == "BER")


def test_modbus_security_metadata():
    mapping = build_engine().registry.get("FDR02.AI12")
    modbus = mapping.bindings["modbus"]
    check("modbus security: port 802", modbus.protocol_metadata["port"] == 802)
    check("modbus security: TLS", modbus.protocol_metadata["security"] == "tls")
    check("modbus security: mutual authentication", modbus.protocol_metadata["mutual_authentication"] is True)


def test_unknown_point():
    try:
        build_engine().convert("NAO.EXISTE", "mms", ["modbus"])
        check("ponto desconhecido", False)
    except MappingNotFoundError:
        check("ponto desconhecido", True)


def test_unknown_source_binding():
    try:
        build_engine().convert("SE01.MMXU1.PhV.phsA", "foo", ["modbus"])
        check("origem inexistente", False)
    except BindingNotFoundError:
        check("origem inexistente", True)


def main():
    test_example_1_mms_to_modbus()
    test_example_2_dnp3_to_opcua()
    test_all_destinations_are_registered()
    test_comm_loss()
    test_invalid_config_rejected()
    test_binding_protocol_mismatch_rejected()
    test_zero_scale_rejected()
    test_overflow_detected_on_publish()
    test_all_dnp3_native_metadata()
    test_mms_native_metadata()
    test_modbus_security_metadata()
    test_unknown_point()
    test_unknown_source_binding()
    print()
    print(f"Total: {PASSED} passaram, {FAILED} falharam")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
