#!/usr/bin/env python3
"""Interface de linha de comando do gateway semântico multiprotocolo.

Comandos:
  map list                          Lista pontos cadastrados
  map show <id>                     Mostra os bindings de um ponto
  map validate [<id>]               Valida um ponto (ou todos) do mapeamento
  map add <arquivo.json>            Cadastra pontos a partir de um arquivo JSON
  convert <id> --from P --to P...   Converte um ponto entre protocolos
  fail <id> --protocol P --to P...  Simula perda de comunicação e converte
  demo                              Roda os 2 exemplos + o cenário de falha
"""

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
        if result["losses"]:
            for loss in result["losses"]:
                print(f"       [perda] {loss}")
        else:
            print("       (sem perda de metadados)")


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
            registry.validate_mapping(registry.get(args.point_id))
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
    print("EXEMPLO 1: IEC 61850 MMS -> Modbus  (perda parcial de metadados)")
    print("=" * 70)
    print_report(engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"]))

    print()
    print("=" * 70)
    print("EXEMPLO 2: DNP3 -> OPC UA  (fidelidade total)")
    print("=" * 70)
    print_report(engine.convert("FDR02.AI12", "dnp3", ["opcua"]))

    print()
    print("=" * 70)
    print("CENÁRIO DE FALHA: perda de comunicação com a origem MMS")
    print("=" * 70)
    engine.adapters["mms"].connected = False
    print_report(engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"]))
    engine.adapters["mms"].connected = True

    print()
    print("=" * 70)
    print("CENÁRIO DE CONFIGURAÇÃO INVÁLIDA: tipos incompatíveis")
    print("=" * 70)
    bad = PointMapping(
        point_id="BAD.POINT",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="BI99", data_type="bool", unit="", raw_value=True),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="V", raw_value=1.0),
        },
    )
    try:
        engine.registry.add(bad)
        print("BAD.POINT: cadastrado (não deveria acontecer!)")
    except ValidationError as e:
        print(f"BAD.POINT: REJEITADO na validação -> {e}")


def main():
    parser = argparse.ArgumentParser(description="Gateway semântico multiprotocolo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_map = sub.add_parser("map", help="operações de mapeamento")
    sub_map = p_map.add_subparsers(dest="map_cmd", required=True)

    p_list = sub_map.add_parser("list", help="lista pontos cadastrados")
    p_list.set_defaults(func=cmd_map_list)

    p_show = sub_map.add_parser("show", help="mostra um ponto")
    p_show.add_argument("point_id")
    p_show.set_defaults(func=cmd_map_show)

    p_val = sub_map.add_parser("validate", help="valida um ponto (ou todos)")
    p_val.add_argument("point_id", nargs="?", default=None)
    p_val.set_defaults(func=cmd_map_validate)

    p_add = sub_map.add_parser("add", help="cadastra pontos a partir de um JSON")
    p_add.add_argument("file")
    p_add.set_defaults(func=cmd_map_add)

    p_conv = sub.add_parser("convert", help="converte um ponto entre protocolos")
    p_conv.add_argument("point_id")
    p_conv.add_argument("--from", dest="source", required=True)
    p_conv.add_argument("--to", dest="targets", nargs="+", required=True)
    p_conv.set_defaults(func=cmd_convert)

    p_fail = sub.add_parser("fail", help="simula perda de comunicação na origem")
    p_fail.add_argument("point_id")
    p_fail.add_argument("--protocol", required=True)
    p_fail.add_argument("--to", dest="targets", nargs="+", required=True)
    p_fail.set_defaults(func=cmd_fail)

    p_demo = sub.add_parser("demo", help="roda os 2 exemplos + cenário de falha")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
