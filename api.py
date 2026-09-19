from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gateway.adapters.factory import build_default_adapters
from gateway.domain.canonical import CanonicalPoint
from gateway.engine.engine import GatewayEngine
from gateway.engine.report import ConversionReport
from gateway.registry.binding import ProtocolBinding
from gateway.registry.exceptions import BindingNotFoundError, MappingNotFoundError, ValidationError
from gateway.registry.mapping import PointMapping
from gateway.registry.registry import MappingRegistry
from gateway.registry.validation import validate_mapping

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MAPPINGS_FILE = DATA_DIR / "mappings.json"

app = FastAPI(title="Gateway Semântico Multiprotocolo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR.mkdir(parents=True, exist_ok=True)
if not MAPPINGS_FILE.exists():
    MAPPINGS_FILE.write_text("{}", encoding="utf-8")

registry = MappingRegistry()
registry.load(str(MAPPINGS_FILE))
adapters = build_default_adapters()
engine = GatewayEngine(registry, adapters)

LOG: List[Dict[str, Any]] = []
LOG_LIMIT = 300


def canonical_to_dict(canonical: Optional[CanonicalPoint]) -> Optional[Dict[str, Any]]:
    if canonical is None:
        return None
    return {
        "value": canonical.value,
        "data_type": canonical.data_type,
        "unit": canonical.unit,
        "quality": canonical.quality.as_dict(),
        "timestamp": canonical.timestamp.as_dict(),
        "source_protocol": canonical.source_protocol,
        "source_raw": canonical.source_raw,
    }


def report_to_dict(report: ConversionReport) -> Dict[str, Any]:
    return {
        "point_id": report.point_id,
        "source_protocol": report.source_protocol,
        "failure": report.failure,
        "canonical": canonical_to_dict(report.canonical),
        "targets": report.targets,
    }


def log_event(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    entry = {"id": len(LOG) + 1, "kind": kind, "logged_at": time.time(), **payload}
    LOG.append(entry)
    if len(LOG) > LOG_LIMIT:
        del LOG[: len(LOG) - LOG_LIMIT]
    return entry


class ConvertRequest(BaseModel):
    point_id: str
    source: str
    targets: List[str]


class ConnectionRequest(BaseModel):
    connected: bool


class BindingIn(BaseModel):
    protocol: str
    address: str
    data_type: str
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0
    raw_value: Optional[Any] = None
    native_validity: Optional[str] = None
    native_quality_flags: List[str] = []
    min_engineering: Optional[float] = None
    max_engineering: Optional[float] = None


class MappingIn(BaseModel):
    point_id: str
    bindings: Dict[str, BindingIn]


@app.get("/api/mappings")
def list_mappings():
    return [
        {"point_id": mapping.point_id, "protocols": sorted(mapping.bindings.keys())}
        for mapping in registry.list()
    ]


@app.get("/api/mappings/{point_id}")
def show_mapping(point_id: str):
    try:
        return registry.get(point_id).to_dict()
    except MappingNotFoundError as error:
        raise HTTPException(404, str(error))


@app.post("/api/mappings/validate")
def validate_mappings(point_id: Optional[str] = None):
    if point_id:
        try:
            validate_mapping(registry.get(point_id))
            return {point_id: None}
        except (MappingNotFoundError, ValidationError) as error:
            return {point_id: str(error)}
    return registry.validate_all()


@app.post("/api/mappings")
def add_mapping(mapping_in: MappingIn):
    bindings = {
        proto: ProtocolBinding(**binding.dict()) for proto, binding in mapping_in.bindings.items()
    }
    mapping = PointMapping(point_id=mapping_in.point_id, bindings=bindings)
    try:
        registry.add(mapping)
    except ValidationError as error:
        log_event("error", {"message": str(error)})
        raise HTTPException(422, str(error))
    registry.save(str(MAPPINGS_FILE))
    log_event("info", {"message": f"Mapeamento '{mapping.point_id}' cadastrado"})
    return {"status": "ok", "point_id": mapping.point_id}


@app.delete("/api/mappings/{point_id}")
def delete_mapping(point_id: str):
    try:
        registry.get(point_id)
    except MappingNotFoundError as error:
        raise HTTPException(404, str(error))
    registry.remove(point_id)
    registry.save(str(MAPPINGS_FILE))
    log_event("info", {"message": f"Mapeamento '{point_id}' removido"})
    return {"status": "ok"}


@app.get("/api/adapters")
def list_adapters():
    return {
        name: {"connected": adapter.connected, "circuit_state": adapter.circuit_state}
        for name, adapter in adapters.items()
    }


@app.post("/api/adapters/{protocol}/connection")
def set_connection(protocol: str, req: ConnectionRequest):
    if protocol not in adapters:
        raise HTTPException(404, f"protocolo '{protocol}' desconhecido")
    adapters[protocol].connected = req.connected
    state = "conectado" if req.connected else "desconectado"
    log_event("info", {"message": f"Adaptador '{protocol}' marcado como {state}"})
    return {"protocol": protocol, "connected": req.connected}


@app.post("/api/convert")
def convert(req: ConvertRequest):
    if req.source not in adapters:
        raise HTTPException(404, f"protocolo de origem '{req.source}' desconhecido")
    unknown_targets = [target for target in req.targets if target not in adapters]
    if unknown_targets:
        raise HTTPException(404, f"protocolo(s) de destino desconhecido(s): {unknown_targets}")
    try:
        report = engine.convert(req.point_id, req.source, req.targets)
    except (MappingNotFoundError, BindingNotFoundError) as error:
        log_event("error", {"message": str(error), "point_id": req.point_id})
        raise HTTPException(404, str(error))
    return log_event("convert", report_to_dict(report))


@app.post("/api/demo")
def run_demo():
    results = []

    adapters["mms"].connected = True
    r1 = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus"])
    results.append(log_event("convert", report_to_dict(r1)))

    r2 = engine.convert("FDR02.AI12", "dnp3", ["opcua"])
    results.append(log_event("convert", report_to_dict(r2)))

    adapters["mms"].connected = False
    r3 = engine.convert("SE01.MMXU1.PhV.phsA", "mms", ["modbus", "opcua"])
    results.append(log_event("convert", report_to_dict(r3)))
    adapters["mms"].connected = True

    bad = PointMapping(
        point_id="BAD.POINT",
        bindings={
            "dnp3": ProtocolBinding(protocol="dnp3", address="BI99", data_type="bool", unit="", raw_value=True),
            "opcua": ProtocolBinding(protocol="opcua", address="ns=2;s=Bad", data_type="float", unit="V", raw_value=1.0),
        },
    )
    try:
        registry.add(bad)
    except ValidationError as error:
        results.append(log_event("error", {"message": f"Config inválida rejeitada: {error}"}))

    return results


@app.get("/api/logs")
def get_logs(limit: int = 50, since_id: int = 0):
    entries = [entry for entry in LOG if entry["id"] > since_id]
    return entries[-limit:]


@app.delete("/api/logs")
def clear_logs():
    LOG.clear()
    return {"status": "ok"}


FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
