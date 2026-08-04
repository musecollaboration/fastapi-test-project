# models.py

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("now()")
    )

    # Связь с Item (один ко многим)
    items: Mapped[list["Item"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    # Индексы
    __table_args__ = (
        Index("idx_users_username", "username", unique=True),
        Index("idx_users_email", "email"),
        Index("idx_users_created_at", "created_at"),
        Index("idx_users_role", "role"),
        # если нужен поиск по full_name через ILIKE, добавьте GIN-индекс:
        # Index("idx_users_full_name_trgm", "full_name", postgresql_using="gin",
        #       postgresql_ops={"full_name": "gin_trgm_ops"}),
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("now()")
    )
    # Внешний ключ на пользователя
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Связь с пользователем-владельцем
    owner: Mapped["UserModel"] = relationship(
        back_populates="items"
    )

    # Индексы
    __table_args__ = (
        Index("idx_items_name", "name"),
        Index("idx_items_created_at", "created_at"),
        Index(
            "idx_items_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"}
        ),
    )


class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("now()"))
