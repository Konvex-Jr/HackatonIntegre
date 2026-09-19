# Gateway semântico multiprotocolo

Protótipo do desafio da WEG para normalização semântica e conversão entre IEC 61850 MMS, DNP3, Modbus e OPC UA. O fluxo central é adapter de origem, modelo canônico, mapeamento, análise de perdas e adapter de destino.

## Estrutura

```text
gateway/
  adapters/
  domain/
  engine/
  registry/
  units/
data/mappings.json
examples/invalid_mapping.json
cli.py
api.py
tests.py
```

## Modelo canônico

O modelo canônico mantém valor, tipo, unidade, qualidade, timestamp, endereço de origem e metadados de origem. Detalhes específicos de cada protocolo permanecem no binding.

## Bindings

Cada ponto possui um binding por protocolo. O binding contém endereço, tipo, unidade, escala, offset, timestamp de origem, codificação e metadados específicos. Isso permite representar DNP3 por grupo, variação e índice, IEC 61850 MMS por estrutura de objeto e functional constraint, Modbus por function code e registrador e OPC UA por NodeId e namespace.

## Protocolos

IEC 61850 MMS é tratado como comunicação cliente-servidor sobre o stack MMS/ACSE/ISO-on-TCP, com codificação BER no protótipo. DNP3 é modelado com tipos de dados, flags, grupos, variações e índices. Modbus usa function code, registrador e escala; o segundo exemplo de Modbus do arquivo de mapeamento usa o perfil Modbus/TCP Security, com mbap/TLS/TCP, porta 802 e metadados de autenticação. OPC UA é modelado por NodeId, namespace, DataType, StatusCode e SourceTimestamp.

## Conversão

```text
PROTOCOLO DE ORIGEM
        ↓
     ADAPTER
        ↓
  MODELO CANÔNICO
        ↓
    MAPEAMENTO
        ↓
 ANÁLISE DE PERDAS
        ↓
     ADAPTER
        ↓
PROTOCOLO DE DESTINO
```

A relação da escala é `engineering = raw * scale + offset`. A conversão para o protocolo de destino usa a transformação inversa.

## Tratamento de perdas

Quando o destino não representa um metadado, a conversão gera um `LossEvent` com campo, valor de origem e valor de destino. Conversões de tipo que exigem arredondamento, overflow ou incompatibilidades também são registradas.

## Falha de comunicação

O gateway conserva o último valor bom conhecido, marca a qualidade canônica como inválida com `comm_lost` e `stale` e adapta a falha ao protocolo de destino. No exemplo Modbus há um coil de status configurado como convenção de aplicação; esse coil não é uma capacidade semântica nativa do protocolo. No OPC UA a falha é refletida como `Bad_CommunicationFailure`.

## Como rodar

```bash
python3 cli.py demo
python3 cli.py map validate
python3 tests.py
```

Para a API:

```bash
pip install -r requirements.txt
python3 -m uvicorn api:app --reload
```

A aplicação fica em `http://127.0.0.1:8000`.
