# Gateway semântico multiprotocolo (protótipo)

Protótipo mínimo do desafio: recebe dados de um protocolo (IEC 61850 MMS,
DNP3, Modbus ou OPC UA), normaliza para um **modelo canônico** (tipo,
unidade, qualidade, timestamp) e publica em qualquer outro protocolo,
explicitando as perdas de metadados quando o destino não consegue
representar tudo o que a origem trazia.

## Por que essa arquitetura atende os requisitos não funcionais

- **Sem dependência de libs industriais**: `gateway/` (o núcleo) nunca
  importa nada de protocolo. Só `gateway/adapters.py` "conheceria"
  bibliotecas reais — aqui elas estão simuladas para manter o exemplo
  autocontido, mas a interface `ProtocolAdapter` é exatamente o ponto
  onde entraria `libiec61850`, `pydnp3`, `pymodbus`, `open62541` etc.
- **Extensível**: um protocolo novo = uma nova subclasse de
  `ProtocolAdapter` em `adapters.py` + uma entrada no dicionário
  `ADAPTER_CLASSES`. Nada mais muda.
- **Particularidades abstraídas**: `CanonicalPoint` (em `canonical.py`)
  é um superset de tipo/unidade/qualidade/timestamp que cobre os 4
  protocolos citados no edital.

## Estrutura

```
gateway/
  canonical.py   modelo canônico (CanonicalPoint, Quality, Timestamp)
  units.py       tabela de unidades e dimensões físicas
  registry.py    registro de mapeamento + validação estática
  adapters.py    adaptadores simulados de MMS, DNP3, Modbus, OPC UA
  engine.py      motor de normalização/denormalização
data/mappings.json     mapeamento padrão (os 2 exemplos do desafio)
examples/invalid_mapping.json  exemplo de config inválida p/ testar 'map add'
cli.py          interface de linha de comando
tests.py        testes automatizados, via terminal
```

## Como rodar

Requer só Python 3.9+ (biblioteca padrão, sem dependências externas).

```bash
cd protocol_gateway

# roda os 2 exemplos de fluxo + cenário de falha + config inválida, tudo de uma vez
python3 cli.py demo

# testes automatizados (17 verificações)
python3 tests.py
```

## Comandos da CLI

```bash
# consultar mapeamentos
python3 cli.py map list
python3 cli.py map show SE01.MMXU1.PhV.phsA

# validar (estático: tipo, unidade/dimensão, nº mínimo de protocolos)
python3 cli.py map validate                      # valida todos
python3 cli.py map validate SE01.MMXU1.PhV.phsA   # valida um ponto

# cadastrar novos pontos a partir de um JSON (tenta um mapeamento inválido de propósito)
python3 cli.py map add examples/invalid_mapping.json

# converter um ponto manualmente entre protocolos
python3 cli.py convert FDR02.AI12 --from dnp3 --to opcua
python3 cli.py convert SE01.MMXU1.PhV.phsA --from mms --to modbus

# simular perda de comunicação na origem
python3 cli.py fail SE01.MMXU1.PhV.phsA --protocol mms --to modbus opcua
```

## Os 2 exemplos do desafio

1. **IEC 61850 MMS → Modbus**: 13,8 kV (float, com qualidade e timestamp)
   vira o registrador `138` (int, escala x10) — perde qualidade e
   timestamp porque Modbus não tem esses canais. A perda é reportada
   explicitamente, não fica silenciosa.
2. **DNP3 → OPC UA**: 502,3 A (com flags e CTO resolvido) vira uma
   variável OPC UA com `EngineeringUnits`, `StatusCode` e
   `SourceTimestamp` — conversão sem perda, porque OPC UA representa
   tudo que o modelo canônico carrega.

## Cenário de falha

`cli.py demo` desliga o adaptador MMS (`connected = False`) e converte de
novo: o ponto canônico vira `invalid[comm_lost,stale]`, o valor fica
congelado no último bom conhecido, e cada destino reflete a falha do seu
jeito (Modbus via convenção de coil, DNP3 via bit `COMM_LOST`, OPC UA via
`StatusCode = Bad_CommunicationFailure`) — sem derrubar a conversão para
os outros destinos.

## Limitações conscientes (é um protótipo, não um produto)

- Adaptadores simulam leitura/escrita em memória, não fazem I/O de rede real.
- Conversão de unidade cobre só tensão/corrente/potência/frequência —
  suficiente para demonstrar o mecanismo, fácil de estender em `units.py`.
- Sem persistência de estado entre execuções além do arquivo de
  mapeamento (`data/mappings.json`).
