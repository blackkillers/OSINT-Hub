"""
OSINT-Hub Scans API & WebSocket Router
======================================
Endpoints for creating investigations, polling scan status, retrieving Graph-Ready data,
and broadcasting real-time module updates over WebSocket.
"""

import asyncio
from typing import Dict, List
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
import structlog

from app.schemas import (
    AggregateScanResponse,
    EdgeModel,
    NodeModel,
    NodeTypeEnum,
    ScanRequest,
    ScanResult,
    StatusEnum,
    TargetTypeEnum,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory storage for active scan results (Backed by PostgreSQL in production script)
SCANS_DB: Dict[str, Dict] = {}


class ConnectionManager:
    """Manages WebSocket connections for real-time investigation graph updates."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, scan_id: str, websocket: WebSocket):
        await websocket.accept()
        if scan_id not in self.active_connections:
            self.active_connections[scan_id] = []
        self.active_connections[scan_id].append(websocket)
        logger.info("WebSocket client connected", scan_id=scan_id)

    def disconnect(self, scan_id: str, websocket: WebSocket):
        if scan_id in self.active_connections:
            if websocket in self.active_connections[scan_id]:
                self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]
        logger.info("WebSocket client disconnected", scan_id=scan_id)

    async def broadcast_update(self, scan_id: str, message: dict):
        if scan_id in self.active_connections:
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning("Error broadcasting WebSocket message", error=str(e))


manager = ConnectionManager()


def get_applicable_modules(target_type: TargetTypeEnum) -> List[str]:
    """Returns list of active OSINT module names matching the target type."""
    mapping = {
        TargetTypeEnum.EMAIL: [
            "email_holehe",
            "email_mosint",
            "email_ghunt",
            "email_epieos",
            "darkweb_onionsearch",
            "leak_daprofiler",
        ],
        TargetTypeEnum.USERNAME: [
            "username_whatsmyname",
            "username_maigret",
            "username_sherlock",
            "username_tookie",
            "darkweb_onionsearch",
        ],
        TargetTypeEnum.PHONE: [
            "phone_phoneinfoga",
            "phone_toutatis",
            "phone_epieos",
        ],
        TargetTypeEnum.IP: [
            "geoint_shodan",
            "geoint_censys",
            "geoint_shadowbroker",
            "geoint_overpass",
        ],
        TargetTypeEnum.DOMAIN: [
            "domain_builtwith",
            "domain_osintsh",
            "geoint_shodan",
            "geoint_censys",
            "darkweb_onionsearch",
        ],
    }
    return mapping.get(target_type, ["email_holehe"])


@router.post("/scans", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def create_scan(payload: ScanRequest):
    """
    Triggers a new multi-module OSINT investigation.
    Enqueues Celery tasks for each applicable module and returns scan_id.
    """
    scan_id = uuid4()
    scan_id_str = str(scan_id)

    modules_to_run = payload.selected_modules
    if "all" in modules_to_run or not modules_to_run:
        modules_to_run = get_applicable_modules(payload.target_type)

    logger.info("Creating new OSINT scan", scan_id=scan_id_str, target=payload.target, modules=modules_to_run)

    # Initialize Scan Entry
    SCANS_DB[scan_id_str] = {
        "scan_id": scan_id_str,
        "target": payload.target,
        "target_type": payload.target_type,
        "status": StatusEnum.RUNNING.value,
        "modules_total": len(modules_to_run),
        "modules_completed": 0,
        "results": [],
        "nodes": [
            {
                "id": f"target:{payload.target}",
                "label": payload.target,
                "type": NodeTypeEnum.PERSON.value if payload.target_type == TargetTypeEnum.USERNAME else payload.target_type.value,
                "metadata": {"is_root": True},
            }
        ],
        "edges": [],
    }

    # Dispatch tasks to Celery asynchronous queue
    from app.worker import run_module_task

    for module_name in modules_to_run:
        run_module_task.delay(
            scan_id_str=scan_id_str,
            target=payload.target,
            target_type_str=payload.target_type.value,
            module_name=module_name,
        )

    return {"scan_id": scan_id_str, "status": "scan_initiated"}


@router.get("/scans/{scan_id}", response_model=AggregateScanResponse)
async def get_scan_results(scan_id: str):
    """Retrieves current aggregate results, graph nodes, and edges for a scan."""
    if scan_id not in SCANS_DB:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    scan_data = SCANS_DB[scan_id]
    return AggregateScanResponse(
        scan_id=UUID(scan_data["scan_id"]),
        target=scan_data["target"],
        target_type=TargetTypeEnum(scan_data["target_type"]),
        overall_status=StatusEnum(scan_data["status"]),
        created_at="2026-07-28T11:45:00Z",
        completed_modules_count=scan_data["modules_completed"],
        total_modules_count=scan_data["modules_total"],
        nodes=[NodeModel(**n) for n in scan_data["nodes"]],
        edges=[EdgeModel(**e) for e in scan_data["edges"]],
        module_results=[ScanResult(**r) for r in scan_data.get("results", [])],
        ai_summary=scan_data.get("ai_summary"),
    )


@router.websocket("/ws/scans/{scan_id}")
async def scan_websocket(websocket: WebSocket, scan_id: str):
    """WebSocket endpoint for real-time investigation progress streaming."""
    await manager.connect(scan_id, websocket)
    try:
        while True:
            # Keepalive / listen for client ping messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(scan_id, websocket)
