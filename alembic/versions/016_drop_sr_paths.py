"""Drop pdf_file_path (historical_sr_reports), image_file_path (sr_report_images).

로컬 파일 경로 컬럼 제거. PDF/이미지는 bytes·API 전달 등으로 처리합니다.
sr_report_index / sr_report_body 는 원래 file_path 컬럼이 없습니다.

Revision ID: 016_drop_sr_paths (alembic_version.version_num VARCHAR(32) 이하)
Revises: 015_sr_body_toc_path
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

revision = "016_drop_sr_paths"
down_revision = "015_sr_body_toc_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF EXISTS: 이전에 긴 revision id로 버전 기록만 실패한 경우 컬럼은 이미 DROP 됐을 수 있음
    op.execute("ALTER TABLE historical_sr_reports DROP COLUMN IF EXISTS pdf_file_path")
    op.execute("ALTER TABLE sr_report_images DROP COLUMN IF EXISTS image_file_path")


def downgrade() -> None:
    op.add_column(
        "historical_sr_reports",
        sa.Column("pdf_file_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "sr_report_images",
        sa.Column("image_file_path", sa.Text(), nullable=True),
    )
