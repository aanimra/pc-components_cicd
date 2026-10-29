"""Create items table (code-first model in app/models.py)

Revision ID: 001_create_items
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "001_create_items"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("product_type", sa.String(80), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("items")
