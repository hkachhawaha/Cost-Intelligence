"""ORM models. Importing this package registers all metadata on `Base`
(used by Alembic env.py and the test fixtures)."""

from app.models.advanced import (
    AnomalyFlag,
    ExtractionQueueItem,
    IndexRegisterEntry,
    StewardProposal,
)
from app.models.agent_run import AgentRun
from app.models.audit_event import AuditEvent
from app.models.automation import (
    ApprovalGate,
    ConnectorCredential,
    LearningLabel,
    ModelCalibration,
    Task,
    TaskReminder,
)
from app.models.base import Base, TenantScopedMixin, TimestampMixin
from app.models.commitment import (
    CommitmentCheck,
    PortfolioRollup,
    SpendTierMetadata,
    TenantQuota,
)
from app.models.contract import Contract, ContractClause, ContractLineItem
from app.models.cost_intelligence import CiDataSource, CiMemorySnapshot
from app.models.entity import Entity
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.matching import MatchResult, UnmatchedQueue
from app.models.memory import ContractEmbedding, MemoryEmbedding, SyncRun, TenantMemory
from app.models.nirvana import (
    DocumentDraft,
    ModelUsageEvent,
    NirvanaConversation,
    NirvanaMessage,
)
from app.models.opportunity import Opportunity, RecoveryItem, RecoveryPack
from app.models.rate_card import ContractRateCard, RateCardTier
from app.models.role import Role
from app.models.spend import SpendRecord
from app.models.staging import DataSource, IngestionBatch, StagedRecord
from app.models.tenant import Tenant
from app.models.user import User
from app.models.vendor import Vendor, VendorAlias

__all__ = [
    "Base",
    "TimestampMixin",
    "TenantScopedMixin",
    "Tenant",
    "Entity",
    "Role",
    "User",
    "AgentRun",
    "AuditEvent",
    # Phase 1
    "Vendor",
    "VendorAlias",
    "Contract",
    "ContractLineItem",
    "ContractClause",
    "SpendRecord",
    "Invoice",
    "InvoiceLineItem",
    "DataSource",
    "IngestionBatch",
    "StagedRecord",
    # Phase 2
    "MatchResult",
    "UnmatchedQueue",
    # Phase 3
    "Opportunity",
    "RecoveryItem",
    # Phase 4
    "TenantMemory",
    "ContractEmbedding",
    "MemoryEmbedding",
    "SyncRun",
    # Phase 6
    "NirvanaConversation",
    "NirvanaMessage",
    "DocumentDraft",
    "ModelUsageEvent",
    # Phase 7
    "ExtractionQueueItem",
    "AnomalyFlag",
    "StewardProposal",
    "IndexRegisterEntry",
    # Phase 8
    "ContractRateCard",
    "RateCardTier",
    "RecoveryPack",
    # Phase 9
    "Task",
    "ApprovalGate",
    "TaskReminder",
    "ConnectorCredential",
    "LearningLabel",
    "ModelCalibration",
    # Phase 10
    "CommitmentCheck",
    "PortfolioRollup",
    "TenantQuota",
    "SpendTierMetadata",
    # Cost Intelligence (single-workspace, Sheets-driven)
    "CiDataSource",
    "CiMemorySnapshot",
]
