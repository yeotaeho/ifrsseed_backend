"""sr_report_images: optional image_blob (BYTEA) for in-DB raster storage.

SR_IMAGE_STORAGE=memory 등에서 픽셀을 DB에 둘 때 사용(선택).
Revision ID는 alembic_version VARCHAR(32) 이하.

Revision ID: 017_sr_images_blob
Revises: 016_drop_sr_paths
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

revision = "017_sr_images_blob"
down_revision = "016_drop_sr_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sr_report_images",
        sa.Column("image_blob", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sr_report_images", "image_blob")
