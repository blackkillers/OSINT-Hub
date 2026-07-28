"""OSINT-Hub — Sherlock Username Module (Real Implementation)"""

import re
import time
from uuid import UUID
from typing import List

import structlog

from app.modules.base import BaseOSINTModule
from app.worker import execute_cli_command
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)


class SherlockModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "username_sherlock"

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

        try:
            cmd = ["sherlock", "--no-color", "--timeout", "10", target]
            exit_code, stdout, stderr = await execute_cli_command(cmd, timeout_seconds=120)

            # Parse: [+] SiteName: https://site.com/user
            for line in stdout.splitlines():
                if line.strip().startswith("[+]"):
                    match = re.search(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
                    if match:
                        site_name = match.group(1).strip()
                        url = match.group(2).strip()
                        node_id = f"social:{site_name.lower()}"
                        if not any(n.id == node_id for n in nodes):
                            nodes.append(NodeModel(
                                id=node_id, label=site_name,
                                type=NodeTypeEnum.SOCIAL_ACCOUNT,
                                metadata={"platform": site_name, "url": url}
                            ))
                            edges.append(EdgeModel(
                                source=root_id, target=node_id,
                                relation="HAS_ACCOUNT_ON", confidence=0.9
                            ))

            log.info("Sherlock done", found=len(nodes) - 1)
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.SUCCESS,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges,
                raw_data={"raw_output": stdout[:2000]}
            )

        except FileNotFoundError:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges,
                error="sherlock CLI not found. Install: pip install sherlock-project"
            )
        except Exception as exc:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.FAILED,
                execution_time_ms=int((time.time() - start) * 1000),
                error=str(exc)
            )
