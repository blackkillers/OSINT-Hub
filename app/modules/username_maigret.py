"""OSINT-Hub — Maigret Username Module (Real Implementation)"""

import json
import re
import time
from uuid import UUID
from typing import List

import structlog

from app.modules.base import BaseOSINTModule
from app.worker import execute_cli_command
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)


class MaigretModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "username_maigret"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.USERNAME]

    async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
        start = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        root_id = f"username:{target.lower()}"
        nodes: List[NodeModel] = [
            NodeModel(id=root_id, label=target, type=NodeTypeEnum.PERSON,
                      metadata={"is_target": True})
        ]
        edges: List[EdgeModel] = []
        raw: dict = {}

        try:
            # maigret --json /tmp/out.json <username>
            cmd = ["maigret", "--json", f"/tmp/maigret_{target}.json",
                   "--no-color", "--timeout", "30", target]
            exit_code, stdout, stderr = await execute_cli_command(cmd, timeout_seconds=120)

            # Parse JSON output
            try:
                import os
                json_path = f"/tmp/maigret_{target}.json"
                if os.path.exists(json_path):
                    with open(json_path) as f:
                        data = json.load(f)
                    raw = data
                    for site_name, site_info in data.items():
                        if isinstance(site_info, dict) and site_info.get("status", {}).get("status") == "Claimed":
                            url = site_info.get("url_user", "")
                            node_id = f"social:{site_name.lower()}"
                            nodes.append(NodeModel(
                                id=node_id,
                                label=f"{site_name}",
                                type=NodeTypeEnum.SOCIAL_ACCOUNT,
                                metadata={"platform": site_name, "url": url, "status": "claimed"}
                            ))
                            edges.append(EdgeModel(
                                source=root_id, target=node_id,
                                relation="HAS_ACCOUNT_ON", confidence=0.9
                            ))
            except Exception as e:
                log.warning("JSON parse error", error=str(e))
                # Fallback: parse stdout
                for line in stdout.splitlines():
                    if "[+]" in line:
                        match = re.search(r"\[\+\]\s+(.+?):", line)
                        if match:
                            site = match.group(1).strip()
                            node_id = f"social:{site.lower()}"
                            nodes.append(NodeModel(
                                id=node_id, label=site,
                                type=NodeTypeEnum.SOCIAL_ACCOUNT,
                                metadata={"platform": site}
                            ))
                            edges.append(EdgeModel(
                                source=root_id, target=node_id,
                                relation="HAS_ACCOUNT_ON", confidence=0.85
                            ))

            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.SUCCESS,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges, raw_data=raw,
                error=None if exit_code == 0 else stderr[:300]
            )

        except FileNotFoundError:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges, raw_data={},
                error="maigret CLI not found. Install: pip install maigret"
            )
        except Exception as exc:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.FAILED,
                execution_time_ms=int((time.time() - start) * 1000),
                error=str(exc)
            )
