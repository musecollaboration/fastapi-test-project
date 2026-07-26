import uuid

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=text("now()")
    )

    # ---------- Индексы ----------
    __table_args__ = (
        Index("idx_items_name", "name"),                     # B-tree для точного поиска
        Index("idx_items_created_at", "created_at"),         # B-tree для сортировки
        Index(
            "idx_items_description_trgm",
            "description",
            postgresql_using="gin"                          # GIN для поиска по подстроке
        ),
    )
