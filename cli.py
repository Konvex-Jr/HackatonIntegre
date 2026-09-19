import argparse
import json
import sys
from pathlib import Path

from gateway.registry import MappingRegistry, PointMapping, ProtocolBinding, ValidationError
from gateway.adapters import build_default_adapters
from gateway.engine import GatewayEngine, ConversionReport

DEFAULT_MAPPINGS = Path(__file__).parent / "data" / "mappings.json"


def build_default_engine() -> GatewayEngine:
    registry = MappingRegistry()
    registry.load(str(DEFAULT_MAPPINGS))
    adapters = build_default_adapters()
    return GatewayEngine(registry, adapters)


def print_canonical(c):
    print(f"  canônico: valor={c.value}  tipo={c.data_type}  unidade='{c.unit}'")
    print(f"            qualidade={c.quality}  timestamp={c.timestamp}")
    if c.source_address:
        print(f"            endereço_origem={c.source_address}")


def print_report(report: ConversionReport):
    print(f"ponto: {report.point_id}  origem: {report.source_protocol}")
    if report.failure:
        print(f"  [FALHA NA LEITURA] {report.failure}")
    print_canonical(report.canonical)
    for proto, result in report.targets.items():
        print(f"  -> {proto}:")
        if "error" in result:
            print(f"       erro: {result['error']}")
            continue
        print(f"       endereço={result['address']}  valor_escrito={result['written_value']}")
        if result.get("engineering_value") is not None:
            print(f"       valor_engenharia={result['engineering_value']} {result.get('target_unit', '')}".rstrip())
        if result.get("encoding"):
            print(f"       codificação={result['encoding']}")
        if "status_code" in result:
            print(f"       status_code={result['status_code']}")
        if result.get("losses"):
            for loss in result["losses"]:
                print(f"       [perda] {loss}")
        else:
            print("       (sem perda de informação canônica)")


def cmd_map_list(args):
    registry = MappingRegistry()
    registry.load(str(DEFAULT_MAPPINGS), validate=False)
    for m in registry.list():
        print(f"{m.point_id}: protocolos={sorted(m.bindings.keys())}")


def cmd_map_show(args):
    registry = MappingRegistry()
    registry.load(str(DEFAULT_MAPPINGS), validate=False)
    m = registry.get(args.point_id)
    print(json.dumps(m.to_dict(), indent=2, ensure_ascii=False))


def cmd_map_validate(args):
    registry = MappingRegistry()
    registry.load(str(DEFAULT_MAPPINGS), validate=False)
    if args.point_id:
        try:
            from gateway.registry.validation import validate_mapping
            validate_mapping(registry.get(args.point_id))
            print(f"{args.point_id}: OK")
        except ValidationError as e:
            print(f"{args.point_id}: INVÁLIDO -> {e}")
            sys.exit(1)
    else:
        results = registry.validate_all()
        ok = True
        for pid, err in results.items():
            if err is None:
                print(f"{pid}: OK")
            else:
                ok = False
                print(f"{pid}: INVÁLIDO -> {err}")
        sys.exit(0 if ok else 1)


def cmd_map_add(args):
    registry = MappingRegistry()
    if DEFAULT_MAPPINGS.exists():
        registry.load(str(DEFAULT_MAPPINGS), validate=False)
    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    for pid, m in data.items():
        bindings = {proto: ProtocolBinding(**b) for proto, b in m["bindings"].items()}
        mapping = PointMapping(point_id=pid, bindings=bindings)
        try:
            registry.add(mapping)
            print(f"{pid}: cadastrado com sucesso")
        except ValidationError as e:
            print(f"{pid}: REJEITADO -> {e}")
            continue
    registry.save(str(DEFAULT_MAPPINGS))


def cmd_convert(args):
    engine = build_default_engine()
    report = engine.convert(args.point_id, args.source, args.targets)
    print_report(report)


def cmd_fail(args):
    engine = build_default_engine()
    engine.adapters[args.protocol].connected = False
    report = engine.convert(args.point_id, args.protocol, args.targets)
    print_report(report)


def cmd_demo(args):
    engine = build_default_engine()

    print("=" * 70)
    print("EXEMPLO 1: IEC 61850 MMS -> Modbus")
    print("=" * 70)
    print_report(engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"]))

    print()
    print("=" * 70)
    print("EXEMPLO 2: DNP3 -> OPC UA")
    print("=" * 70)
    print_report(engine.convert("FDR02.AI12", "dnp3", ["opcua"]))

    print()
    print("=" * 70)
    print("CENÁRIO DE FALHA: perda de comunicação com a origem MMS")
    print("=" * 70)
    engine = build_default_engine()
    engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    engine.adapters["mms"].connected = False
    print_report(engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"]))

    print()
    print("=" * 70)
    print("CENÁRIO DE CONFIGURAÇÃO INVÁLIDA: tipos incompatíveis")
    print("=" * 70)
    registry = MappingRegistry()
    registry.load(str(DEFAULT_MAPPINGS), validate=False)
    bad = PointMapping(
        point_id="BAD.POINT",
        bindings={
            "dnp3": ProtocolBinding(
                protocol="dnp3",
                address="BI99",
                data_type="bool",
                unit="",
                protocol_metadata={"group": 1, "variation": 1, "index": 99},
            ),
            "opcua": ProtocolBinding(
                protocol="opcua",
                address="ns=2;s=Bad",
                data_type="float",
                unit="V",
                protocol_metadata={"namespace": 2, "identifier_type": "s"},
            ),
        },
    )
    try:
        registry.add(bad)
        print("BAD.POINT: deveria ter sido rejeitado")
    except ValidationError as error:
        print(f"BAD.POINT: REJEITADO na validação -> {error}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub_map = sub.add_parser("map")
    sub_map_sub = sub_map.add_subparsers(dest="map_command", required=True)

    p_list = sub_map_sub.add_parser("list")
    p_list.set_defaults(func=cmd_map_list)

    p_show = sub_map_sub.add_parser("show")
    p_show.add_argument("point_id")
    p_show.set_defaults(func=cmd_map_show)

    p_validate = sub_map_sub.add_parser("validate")
    p_validate.add_argument("point_id", nargs="?")
    p_validate.set_defaults(func=cmd_map_validate)

    p_add = sub_map_sub.add_parser("add")
    p_add.add_argument("file")
    p_add.set_defaults(func=cmd_map_add)

    p_conv = sub.add_parser("convert")
    p_conv.add_argument("point_id")
    p_conv.add_argument("--from", dest="source", required=True)
    p_conv.add_argument("--to", dest="targets", nargs="+", required=True)
    p_conv.set_defaults(func=cmd_convert)

    p_fail = sub.add_parser("fail")
    p_fail.add_argument("point_id")
    p_fail.add_argument("--protocol", required=True)
    p_fail.add_argument("--to", dest="targets", nargs="+", required=True)
    p_fail.set_defaults(func=cmd_fail)

    p_demo = sub.add_parser("demo")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
