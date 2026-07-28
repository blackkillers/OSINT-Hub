"""
OSINT-Hub Email Engine Module: Holehe Integration
===================================================
Checks email address registration across 120+ web services using Holehe CLI tool.
Parses output into Universal Graph-Ready JSON format (Nodes & Edges).
"""

import json
import re
import time
from uuid import UUID
from typing import List

import structlog

from app.modules.base import BaseOSINTModule
from app.schemas import (
    EdgeModel,
    NodeModel,
    NodeTypeEnum,
    ScanResult,
    StatusEnum,
    TargetTypeEnum,
)

logger = structlog.get_logger(__name__)


class HoleheModule(BaseOSINTModule):
    """Module executing Holehe CLI to find account registrations associated with an email."""

    @property
    def name(self) -> str:
        return "email_holehe"

    @property
    def supported_target_types(self) -> List[TargetTypeEnum]:
        return [TargetTypeEnum.EMAIL]

    async def run(
        self, scan_id: UUID, target: str, target_type: TargetTypeEnum
    ) -> ScanResult:
        """
        Executes Holehe CLI tool against an email address and converts findings
        into entity nodes (email, social accounts) and relationship edges.
        """
        start_time = time.time()
        log = logger.bind(scan_id=str(scan_id), module=self.name, target=target)

        if target_type != TargetTypeEnum.EMAIL:
            return ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=self.name,
                status=StatusEnum.FAILED,
                error=f"Unsupported target type '{target_type}'. Expected 'email'.",
            )

        # Import subprocess runner from app.worker
        from app.worker import execute_cli_command

        # Holehe command args (sanitized list, no shell=True)
        # Note: holehe target email
        cmd = ["holehe", target, "--only-used", "--no-color"]

        nodes: List[NodeModel] = []
        edges: List[EdgeModel] = []
        raw_data = {"found_services": [], "raw_output": ""}

        # Create root node for the target email
        target_node_id = f"email:{target.lower()}"
        nodes.append(
            NodeModel(
                id=target_node_id,
                label=target,
                type=NodeTypeEnum.EMAIL,
                metadata={"is_target": True, "target_type": "email"},
            )
        )

        try:
            log.info("Executing Holehe CLI command", cmd=cmd)
            exit_code, stdout, stderr = await execute_cli_command(cmd=cmd, timeout_seconds=150)
            raw_data["raw_output"] = stdout

            # Parse stdout lines to extract registered platforms
            # Typical holehe output line format for found sites:
            # [+] website.com
            # or re matching [+] platform
            found_services = []
            for line in stdout.splitlines():
                line_clean = line.strip()
                if "[+]" in line_clean or "REGISTERED" in line_clean.upper():
                    # Extract platform name/domain
                    match = re.search(r"\[\+\]\s+([a-zA-Z0-9.\-_]+)", line_clean)
                    if match:
                        service_name = match.group(1).strip()
                        found_services.append(service_name)
                    else:
                        # Fallback simple split
                        parts = line_clean.split()
                        if len(parts) >= 2:
                            found_services.append(parts[-1])

            raw_data["found_services"] = found_services
            log.info("Holehe execution completed", found_count=len(found_services))

            # Build Graph Nodes & Edges for each found registered service
            for service in found_services:
                service_node_id = f"service:{service.lower()}"
                
                # Check if node already added
                if not any(n.id == service_node_id for n in nodes):
                    nodes.append(
                        NodeModel(
                            id=service_node_id,
                            label=f"{service} Account",
                            type=NodeTypeEnum.SOCIAL_ACCOUNT,
                            metadata={
                                "platform": service,
                                "status": "registered",
                                "confidence": 0.95,
                            },
                        )
                    )

                edges.append(
                    EdgeModel(
                        source=target_node_id,
                        target=service_node_id,
                        relation="REGISTERED_ON",
                        confidence=0.95,
                    )
                )

            execution_time_ms = int((time.time() - start_time) * 1000)
            return ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=self.name,
                status=StatusEnum.SUCCESS,
                execution_time_ms=execution_time_ms,
                nodes=nodes,
                edges=edges,
                raw_data=raw_data,
                error=None if exit_code == 0 else f"CLI exit code {exit_code}: {stderr[:200]}",
            )

        except FileNotFoundError:
            # Holehe CLI binary not installed in environment fallback simulator for dev/demo
            log.warning("Holehe CLI not found in PATH. Using structured fallback analysis.")
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=self.name,
                status=StatusEnum.PARTIAL,
                execution_time_ms=execution_time_ms,
                nodes=nodes,
                edges=edges,
                raw_data={"warning": "Holehe CLI binary missing from environment. Install via pip install holehe."},
                error="Holehe CLI binary not found in container environment.",
            )

        except Exception as exc:
            execution_time_ms = int((time.time() - start_time) * 1000)
            log.error("Error executing Holehe module", error=str(exc))
            return ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=self.name,
                status=StatusEnum.FAILED,
                execution_time_ms=execution_time_ms,
                nodes=nodes,
                edges=edges,
                raw_data=raw_data,
                error=str(exc),
            )
