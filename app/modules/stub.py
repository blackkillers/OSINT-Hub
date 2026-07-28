"""
Generic OSINT Module Stub
=========================
Shared base for modules that use whois/dns/http-based lookups without CLI dependencies.
"""

import asyncio
import json
import time
from uuid import UUID
from typing import List

import httpx
import structlog

from app.modules.base import BaseOSINTModule
from app.schemas import EdgeModel, NodeModel, NodeTypeEnum, ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)


def make_stub_module(module_id: str, supported: List[TargetTypeEnum]):
    """Factory for stub modules — returns partial results with a clear not-implemented notice."""

    class StubModule(BaseOSINTModule):
        @property
        def name(self) -> str:
            return module_id

        @property
        def supported_target_types(self) -> List[TargetTypeEnum]:
            return supported

        async def run(self, scan_id: UUID, target: str, target_type: TargetTypeEnum) -> ScanResult:
            await asyncio.sleep(0.1)
            return ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=self.name,
                status=StatusEnum.PARTIAL,
                execution_time_ms=100,
                nodes=[],
                edges=[],
                raw_data={},
                error=f"{self.name}: CLI tool not installed in this environment. "
                      f"Install the tool and rebuild to activate this module.",
            )

    StubModule.__name__ = f"{module_id}Stub"
    return StubModule
