"""
OSINT-Hub Base Module Interface
================================
Abstract Base Class ensuring isolation, universal schema enforcement, and standard interface across modules.
"""

from abc import ABC, abstractmethod
from uuid import UUID
from app.schemas import ScanResult, TargetTypeEnum


class BaseOSINTModule(ABC):
    """Abstract base class for all OSINT plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the module (e.g., 'email_holehe')."""
        pass

    @property
    @abstractmethod
    def supported_target_types(self) -> list[TargetTypeEnum]:
        """List of target types supported by this module."""
        pass

    @abstractmethod
    async def run(
        self, scan_id: UUID, target: str, target_type: TargetTypeEnum
    ) -> ScanResult:
        """
        Execute module logic against target. Must return a valid ScanResult instance.
        """
        pass
