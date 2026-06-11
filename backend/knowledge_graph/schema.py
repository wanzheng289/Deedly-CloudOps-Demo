"""Enterprise knowledge graph schema definitions."""
from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 and below
    from enum import Enum

    class StrEnum(str, Enum):
        pass

from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    CUSTOMER = "Customer"
    PRODUCT = "Product"
    MODULE = "Module"
    SUPPORT_TICKET = "SupportTicket"
    DOCUMENT = "Document"
    ISSUE = "Issue"
    TEAM = "Team"
    SERVICE = "Service"
    DEPLOYMENT_ENV = "DeploymentEnv"
    SLA = "SLA"
    FAQ = "FAQ"
    VERSION = "Version"
    SOURCE = "Source"
    AGENT = "Agent"


class RelationType(StrEnum):
    CUSTOMER_OPENED_TICKET = "CUSTOMER_OPENED_TICKET"
    TICKET_MENTIONS_PRODUCT = "TICKET_MENTIONS_PRODUCT"
    TICKET_MENTIONS_MODULE = "TICKET_MENTIONS_MODULE"
    DOCUMENT_EXPLAINS_PRODUCT = "DOCUMENT_EXPLAINS_PRODUCT"
    DOCUMENT_EXPLAINS_MODULE = "DOCUMENT_EXPLAINS_MODULE"
    ISSUE_RELATED_TO_VERSION = "ISSUE_RELATED_TO_VERSION"
    TEAM_OWNS_SERVICE = "TEAM_OWNS_SERVICE"
    PRODUCT_DEPENDS_ON_SERVICE = "PRODUCT_DEPENDS_ON_SERVICE"
    CUSTOMER_USES_PRODUCT = "CUSTOMER_USES_PRODUCT"
    FAQ_ANSWERS_ISSUE_TYPE = "FAQ_ANSWERS_ISSUE_TYPE"
    DOCUMENT_FROM_SOURCE = "DOCUMENT_FROM_SOURCE"
    DOCUMENT_MENTIONS_SERVICE = "DOCUMENT_MENTIONS_SERVICE"
    DOCUMENT_MENTIONS_TEAM = "DOCUMENT_MENTIONS_TEAM"
    SERVICE_RUNS_IN_ENV = "SERVICE_RUNS_IN_ENV"
    TICKET_HAS_ISSUE = "TICKET_HAS_ISSUE"
    TICKET_HANDLED_BY_AGENT = "TICKET_HANDLED_BY_AGENT"


class KGNode(BaseModel):
    node_id: str
    type: NodeType
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class KGRelation(BaseModel):
    source_id: str
    target_id: str
    type: RelationType
    properties: dict[str, Any] = Field(default_factory=dict)
