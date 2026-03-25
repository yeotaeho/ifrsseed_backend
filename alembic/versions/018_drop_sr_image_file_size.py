"""Drop sr_report_images.image_file_size.

크기는 image_blob 길이 또는 extracted_data.size_bytes 등으로 유도합니다.
Revision ID는 alembic_version VARCHAR(32) 이하.

Revision ID: 018_drop_sr_image_file_size
Revises: 017_sr_images_blob
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

revision = "018_drop_sr_image_file_size"
down_revision = "017_sr_images_blob"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sr_report_images DROP COLUMN IF EXISTS image_file_size")


def downgrade() -> None:
    op.add_column(
        "sr_report_images",
        sa.Column("image_file_size", sa.BigInteger(), nullable=True),
    )
