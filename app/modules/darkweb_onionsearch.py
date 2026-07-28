"""OSINT-Hub — OnionSearch Dark Web Module (Real Implementation)"""

import time
from uuid import UUID
from typing import List

import structlog

from app.modules.base import BaseOSINTModule
from app.worker import execute_cli_command
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)

TOR_SOCKS = "socks5://tor:9050"


class OnionSearchModule(BaseOSINTModule):
    @property
    def name(self) -> str:
        return "darkweb_onionsearch"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.EMAIL, TargetTypeEnum.USERNAME, TargetTypeEnum.DOMAIN]

    async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
        start = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        root_id = f"{target_type.value}:{target.lower()}"
        nodes: List[NodeModel] = [
            NodeModel(id=root_id, label=target,
                      type=NodeTypeEnum.EMAIL if target_type == TargetTypeEnum.EMAIL else NodeTypeEnum.PERSON,
                      metadata={"is_target": True})
        ]
        edges: List[EdgeModel] = []
        raw: dict = {}

        try:
            cmd = ["onionsearch", target]
            exit_code, stdout, stderr = await execute_cli_command(
                cmd, timeout_seconds=60, socks_proxy=TOR_SOCKS
            )
            raw = {"stdout": stdout[:3000]}

            # Parse results - onionsearch outputs URLs with context
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("http") and ".onion" in line:
                    onion_id = f"darkweb:{line[:60].replace('/', '_')}"
                    nodes.append(NodeModel(
                        id=onion_id,
                        label=line[:50] + "..." if len(line) > 50 else line,
                        type=NodeTypeEnum.OTHER,
                        metadata={"type": "onion_url", "url": line}
                    ))
                    edges.append(EdgeModel(
                        source=root_id, target=onion_id,
                        relation="MENTIONED_ON_DARKWEB", confidence=0.7
                    ))

            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name,
                status=StatusEnum.SUCCESS if exit_code == 0 else StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges, raw_data=raw
            )

        except FileNotFoundError:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.PARTIAL,
                execution_time_ms=int((time.time() - start) * 1000),
                nodes=nodes, edges=edges,
                error="onionsearch not installed. Install: pip install onionsearch"
            )
        except Exception as exc:
            return ScanResult(
                scan_id=scan_id, target=target, target_type=target_type,
                module_name=self.name, status=StatusEnum.FAILED,
                execution_time_ms=int((time.time() - start) * 1000),
                error=str(exc)
            )
