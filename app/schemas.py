"""
OSINT-Hub Universal Data Schemas (Pydantic v2)
==============================================
Graph-Ready normalized schemas for OSINT workers, API payloads, and React Flow frontend visualization.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, ConfigDict, field_validator


class TargetTypeEnum(str, Enum):
    """Supported target input types for OSINT investigations."""
    EMAIL = "email"
    PHONE = "phone"
    USERNAME = "username"
    IP = "ip"
    DOMAIN = "domain"


class StatusEnum(str, Enum):
    """Scan execution status across workers and orchestrator."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    PARTIAL = "partial"


class NodeTypeEnum(str, Enum):
    """Node classifications for React Flow graph visualization."""
    PERSON = "person"
    EMAIL = "email"
    PHONE = "phone"
    SOCIAL_ACCOUNT = "social_account"
    DOMAIN = "domain"
    IP = "ip"
    LEAK = "leak"
    LOCATION = "location"
    OTHER = "other"


class NodeModel(BaseModel):
    """Representation of an entity node in the investigation graph."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(
        ...,
        description="Unique identifier for the node (e.g., email address, social handle, IP)",
        examples=["user@example.com", "github:octocat"]
    )
    label: str = Field(
        ...,
        description="Human-readable label displayed on graph nodes",
        examples=["octocat (GitHub)", "user@example.com"]
    )
    type: NodeTypeEnum = Field(
        ...,
        description="Categorization of the entity node"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata attached to entity node"
    )


class EdgeModel(BaseModel):
    """Representation of a relationship edge between two nodes in the graph."""
    model_config = ConfigDict(extra="ignore")

    source: str = Field(
        ...,
        description="Source node ID",
        examples=["target:john_doe"]
    )
    target: str = Field(
        ...,
        description="Target node ID",
        examples=["email:john@gmail.com"]
    )
    relation: str = Field(
        ...,
        description="Relationship type description",
        examples=["HAS_EMAIL", "REGISTERED_ON", "ASSOCIATED_IP"]
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the relation between 0.0 (unverifiable) and 1.0 (certain)"
    )


class ScanRequest(BaseModel):
    """Payload sent by the user / frontend to trigger an investigation scan."""
    target: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Target string (email, username, phone, IP, domain)",
        examples=["john_doe", "target@example.com", "+33612345678", "8.8.8.8", "example.com"]
    )
    target_type: TargetTypeEnum = Field(
        ...,
        description="Type of the target to guide module selection"
    )
    selected_modules: List[str] = Field(
        default=["all"],
        description="List of specific module names to run, or ['all'] to trigger all applicable engines"
    )

    @field_validator("target")
    @classmethod
    def sanitize_target(cls, value: str) -> str:
        """Strip whitespaces and basic control characters from input target."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Target string cannot be empty or whitespace-only.")
        return cleaned


class ScanResult(BaseModel):
    """
    Universal Graph-Ready Scan Result schema.
    All OSINT modules and Celery workers MUST return data strictly matching this structure.
    """
    model_config = ConfigDict(extra="ignore")

    scan_id: UUID = Field(
        default_factory=uuid4,
        description="UUID identifying the parent scan job"
    )
    target: str = Field(
        ...,
        description="The original target queried"
    )
    target_type: TargetTypeEnum = Field(
        ...,
        description="The type of target queried"
    )
    module_name: str = Field(
        ...,
        description="Name of the module that generated this result",
        examples=["email_holehe", "username_sherlock", "geoint_shodan"]
    )
    status: StatusEnum = Field(
        ...,
        description="Execution status of this specific module"
    )
    execution_time_ms: int = Field(
        default=0,
        ge=0,
        description="Execution duration in milliseconds"
    )
    nodes: List[NodeModel] = Field(
        default_factory=list,
        description="List of entity nodes extracted by the module"
    )
    edges: List[EdgeModel] = Field(
        default_factory=list,
        description="List of relationship edges extracted by the module"
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw output dictionary from the underlying tool CLI/API"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if status is failed or timeout"
    )


class AggregateScanResponse(BaseModel):
    """Combined response returned by FastAPI aggregating all worker results for a scan_id."""
    scan_id: UUID
    target: str
    target_type: TargetTypeEnum
    overall_status: StatusEnum
    created_at: str
    completed_modules_count: int
    total_modules_count: int
    nodes: List[NodeModel] = Field(default_factory=list)
    edges: List[EdgeModel] = Field(default_factory=list)
    module_results: List[ScanResult] = Field(default_factory=list)
    ai_summary: Optional[str] = None
