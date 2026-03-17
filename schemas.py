from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlagType(str, Enum):
    RISK = "Emerging Risk"
    BLOCKER = "Blocker"
    ACTION_ITEM = "Unresolved Action Item"
    SCOPE_CREEP = "Scope Creep"
    RESOURCE_BOTTLENECK = "Resource Bottleneck"
    TIMELINE_DELAY = "Timeline Delay"
    TECH_DEBT = "Technical Architecture Risk"
    STAKEHOLDER_MISALIGNMENT = "Stakeholder Misalignment"


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class HealthStatus(str, Enum):
    HEALTHY = "Healthy"
    AT_RISK = "At Risk"
    CRITICAL = "Critical"


class AttentionFlag(BaseModel):
    project_name: Optional[str] = Field(
        description="Name of the project, if mentioned (e.g., Project Phoenix)."
    )
    flag_types: list[FlagType] = Field(description="The categories of the issue.")
    severity: Severity = Field(
        description="Estimated impact on the project timeline, budget, or resources."
    )
    summary: str = Field(
        description="A concise, 1-2 sentence summary of the issue designed for an executive audience."
    )
    is_resolved: bool = Field(
        description="True if the thread shows a clear and agreed-upon resolution, False if it remains open or ambiguous."
    )
    reported_by: str = Field(
        description="The anonymized role of the person who first raised the issue (e.g., Senior Developer)."
    )
    assigned_to: Optional[str] = Field(
        description="The anonymized role of the person responsible for resolving it, if mentioned."
    )
    date_reported: str = Field(
        description="The date the issue was first raised in the email thread."
    )
    evidence_quote: str = Field(
        description="A short, direct quote from the email thread that proves this flag exists. Helps prevent hallucinations."
    )


class PortfolioHealthReport(BaseModel):
    project_name: str = Field(
        description="The name of the project being discussed in the email thread."
    )
    overall_health_status: HealthStatus = Field(
        description="The overall health assessment of the project based on the communications."
    )
    extracted_flags: list[AttentionFlag] = Field(
        default_factory=list,
        description="List of attention flags extracted from the communication thread.",
    )
