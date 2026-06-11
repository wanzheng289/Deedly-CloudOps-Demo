from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from project.backend.db.postgres import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_user_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_ref_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    rag_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("ChatSession", back_populates="messages")


class ParentChunk(Base):
    __tablename__ = "parent_chunks"

    chunk_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_chunk_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    root_chunk_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    chunk_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CustomerProfile(Base):
    """Structured long-term customer profile used by customer-ops memory."""

    __tablename__ = "customer_profiles"

    customer_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    industries: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    products: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    common_issue_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    channels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sentiments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    urgencies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    primary_intents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    outcomes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_priority_ticket_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    sample_ticket_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupportTicket(Base):
    """Support ticket distilled from a customer conversation."""

    __tablename__ = "support_tickets"

    ticket_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    product: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    issue_type: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(40), default="medium", nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    overall_sentiment: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    overall_urgency: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    primary_intent: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    first_message_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_message_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class MemoryItem(Base):
    """Atomic memory record shared by session/profile/domain memory."""

    __tablename__ = "memory_items"

    __table_args__ = (
        UniqueConstraint("customer_id", "memory_type", "content", name="uq_customer_memory_content"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="manual", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
