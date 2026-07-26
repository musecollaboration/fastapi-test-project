"""Create items table

Revision ID: 09ec4d84d827
Revises: 
Create Date: 2026-07-25 11:56:47.255578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09ec4d84d827'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Расширение для GIN-индексов по тексту
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Таблица items
    op.create_table('items',
                    sa.Column('id', sa.UUID(), nullable=False),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.Column('description', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Индексы
    op.create_index('idx_items_name', 'items', ['name'])
    op.create_index('idx_items_created_at', 'items', ['created_at'])
    op.create_index(
        'idx_items_description_trgm',
        'items',
        ['description'],
        postgresql_using='gin',
        postgresql_ops={'description': 'gin_trgm_ops'}
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_items_description_trgm', table_name='items')
    op.drop_index('idx_items_created_at', table_name='items')
    op.drop_index('idx_items_name', table_name='items')
    op.drop_table('items')
    # ### end Alembic commands ###
