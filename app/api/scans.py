"""
OSINT-Hub Scans API & WebSocket Router - COMPLETE REWRITE
==========================================================
Full pipeline: create scan → Celery dispatch → poll Celery results → aggregate graph → WebSocket push.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from celery.result import AsyncResult
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

# In-memory scan store: scan_id -> scan metadata + list of Celery task IDs
SCANS_DB: Dict[str, Dict[str, Any]] = {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, scan_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(scan_id, []).append(websocket)

    def disconnect(self, scan_id: str, websocket: WebSocket):
        if scan_id in self.active_connections:
            self.active_connections[scan_id] = [
                ws for ws in self.active_connections[scan_id] if ws != websocket
            ]

    async def broadcast(self, scan_id: str, message: dict):
        for ws in self.active_connections.get(scan_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def get_applicable_modules(target_type: TargetTypeEnum) -> List[str]:
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
        ],
        TargetTypeEnum.PHONE: [
            "phone_phoneinfoga",
            "phone_toutatis",
        ],
        TargetTypeEnum.IP: [
            "geoint_shodan",
            "geoint_censys",
        ],
        TargetTypeEnum.DOMAIN: [
            "domain_builtwith",
            "domain_osintsh",
            "geoint_shodan",
            "geoint_censys",
        ],
    }
    return mapping.get(target_type, ["email_holehe"])


def _collect_celery_results(scan_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Poll all Celery task IDs for a scan and collect completed results.
    Merges new nodes/edges into the scan store.
    """
    from app.worker import celery_app

    completed_results: List[Dict] = []
    all_nodes: Dict[str, dict] = {n["id"]: n for n in scan_data.get("nodes", [])}
    all_edges: List[dict] = list(scan_data.get("edges", []))
    tasks_done = 0

    for task_id in scan_data.get("task_ids", []):
        result = AsyncResult(task_id, app=celery_app)
        if result.ready():
            tasks_done += 1
            try:
                module_result = result.get(timeout=1)
                if isinstance(module_result, dict):
                    completed_results.append(module_result)
                    # Merge nodes (deduplicate by id)
                    for node in module_result.get("nodes", []):
                        if node["id"] not in all_nodes:
                            all_nodes[node["id"]] = node
                    # Merge edges (deduplicate by source+target+relation)
                    existing_edge_keys = {
                        f"{e['source']}-{e['target']}-{e['relation']}" for e in all_edges
                    }
                    for edge in module_result.get("edges", []):
                        key = f"{edge['source']}-{edge['target']}-{edge['relation']}"
                        if key not in existing_edge_keys:
                            all_edges.append(edge)
                            existing_edge_keys.add(key)
            except Exception as e:
                logger.warning("Failed to collect Celery result", task_id=task_id, error=str(e))

    total_tasks = len(scan_data.get("task_ids", []))
    overall_status = (
        StatusEnum.RUNNING.value if tasks_done < total_tasks else StatusEnum.SUCCESS.value
    )

    # Update scan_data in place
    scan_data["nodes"] = list(all_nodes.values())
    scan_data["edges"] = all_edges
    scan_data["results"] = completed_results
    scan_data["modules_completed"] = tasks_done
    scan_data["status"] = overall_status

    return scan_data


@router.post("/scans", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def create_scan(payload: ScanRequest):
    """Triggers a new multi-module OSINT investigation."""
    from app.worker import run_module_task

    scan_id = uuid4()
    scan_id_str = str(scan_id)

    modules_to_run = payload.selected_modules
    if "all" in modules_to_run or not modules_to_run:
        modules_to_run = get_applicable_modules(payload.target_type)

    logger.info(
        "Creating new scan",
        scan_id=scan_id_str,
        target=payload.target,
        modules=modules_to_run,
    )

    # Root node for the target
    root_node_type = (
        NodeTypeEnum.PERSON.value
        if payload.target_type == TargetTypeEnum.USERNAME
        else payload.target_type.value
    )

    # Dispatch all tasks and collect task IDs
    task_ids = []
    for module_name in modules_to_run:
        task = run_module_task.delay(
            scan_id_str=scan_id_str,
            target=payload.target,
            target_type_str=payload.target_type.value,
            module_name=module_name,
        )
        task_ids.append(task.id)

    SCANS_DB[scan_id_str] = {
        "scan_id": scan_id_str,
        "target": payload.target,
        "target_type": payload.target_type.value,
        "status": StatusEnum.RUNNING.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modules_total": len(modules_to_run),
        "modules_completed": 0,
        "task_ids": task_ids,
        "results": [],
        "nodes": [
            {
                "id": f"target:{payload.target}",
                "label": payload.target,
                "type": root_node_type,
                "metadata": {"is_root": True},
            }
        ],
        "edges": [],
        "ai_summary": None,
    }

    return {"scan_id": scan_id_str, "status": "scan_initiated"}


@router.get("/scans/{scan_id}", response_model=AggregateScanResponse)
async def get_scan_results(scan_id: str):
    """Polls Celery tasks, aggregates results, and returns the current graph state."""
    if scan_id not in SCANS_DB:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    scan_data = _collect_celery_results(SCANS_DB[scan_id])
    SCANS_DB[scan_id] = scan_data

    return AggregateScanResponse(
        scan_id=UUID(scan_data["scan_id"]),
        target=scan_data["target"],
        target_type=TargetTypeEnum(scan_data["target_type"]),
        overall_status=StatusEnum(scan_data["status"]),
        created_at=scan_data["created_at"],
        completed_modules_count=scan_data["modules_completed"],
        total_modules_count=scan_data["modules_total"],
        nodes=[NodeModel(**n) for n in scan_data["nodes"]],
        edges=[EdgeModel(**e) for e in scan_data["edges"]],
        module_results=[ScanResult(**r) for r in scan_data.get("results", [])],
        ai_summary=scan_data.get("ai_summary"),
    )


@router.websocket("/ws/scans/{scan_id}")
async def scan_websocket(websocket: WebSocket, scan_id: str):
    """WebSocket for real-time push of graph updates as modules complete."""
    await manager.connect(scan_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(scan_id, websocket)
