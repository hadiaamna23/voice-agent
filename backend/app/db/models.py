from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    Float,
    JSON,
)

from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(512), nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tenant_id = Column(
        String(128),
        nullable=False,
        index=True,
    )

    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    call_logs = relationship(
        "CallLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    memories = relationship(
        "MemorySlot",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    workflows = relationship(
        "Workflow",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    analytics_events = relationship(
        "AnalyticsEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    crm_leads = relationship(
        "CrmLead",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    session_id = Column(
        String(128),
        nullable=False,
        index=True,
    )

    role = Column(String(32), nullable=False)

    content = Column(
        Text,
        nullable=False,
    )

    source = Column(
        String(64),
        nullable=False,
        default="agent",
    )

    language = Column(
        String(16),
        nullable=False,
        default="en",
    )

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="conversations",
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    language = Column(
        String(16),
        nullable=False,
        default="en",
    )

    duration_seconds = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    transcript = Column(
        Text,
        nullable=False,
    )

    sentiment = Column(
        String(64),
        nullable=True,
    )

    call_metadata = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="call_logs",
    )


class MemorySlot(Base):
    __tablename__ = "memory_slots"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    key = Column(
        String(255),
        nullable=False,
    )

    value = Column(
        Text,
        nullable=False,
    )

    source = Column(
        String(64),
        nullable=False,
        default="conversation",
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="memories",
    )


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(
        String(128),
        nullable=False,
    )

    trigger_type = Column(
        String(64),
        nullable=False,
    )

    config = Column(
        JSON,
        nullable=False,
    )

    active = Column(
        Boolean,
        default=True,
    )

    last_run_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    user = relationship(
        "User",
        back_populates="workflows",
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type = Column(
        String(128),
        nullable=False,
    )

    event_metadata = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="analytics_events",
    )


class CrmLead(Base):
    __tablename__ = "crm_leads"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_id = Column(
        String(255),
        nullable=False,
    )

    status = Column(
        String(64),
        nullable=False,
    )

    lead_metadata = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="crm_leads",
    )