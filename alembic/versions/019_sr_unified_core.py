"""Create SR unified core tables.

Creates:
- environmental_data
- social_data
- governance_data
- company_info
- unmapped_data_points
- sr_report_unified_data

Revision ID: 019_sr_unified_core
Revises: 018_drop_sr_image_file_size
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "019_sr_unified_core"
down_revision = "018_drop_sr_image_file_size"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return inspect(bind).has_table(table_name)


def upgrade() -> None:
    # FK 부모 테이블이 없는 환경(분리 DB/신규 DB)에서도 019가 단독 실행되도록
    # 최소 부모 스키마를 부트스트랩한다.
    if not _has_table("companies"):
        op.create_table(
            "companies",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("name", sa.Text(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("email", sa.Text(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("unified_column_mappings"):
        op.create_table(
            "unified_column_mappings",
            sa.Column("unified_column_id", sa.String(length=50), nullable=False),
            sa.Column("column_name_ko", sa.String(length=200), nullable=False),
            sa.Column("column_name_en", sa.String(length=200), nullable=False),
            sa.Column("column_category", sa.String(length=1), nullable=False),
            sa.Column("mapped_dp_ids", postgresql.ARRAY(sa.String()), nullable=False),
            sa.Column("column_type", sa.String(length=20), nullable=False),
            sa.Column("unit", sa.String(length=50), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("unified_column_id"),
            sa.CheckConstraint("column_category IN ('E', 'S', 'G')", name="chk_ucm_bootstrap_category"),
            sa.CheckConstraint(
                "column_type IN ('quantitative', 'qualitative', 'narrative', 'binary')",
                name="chk_ucm_bootstrap_type",
            ),
        )
        op.create_index("idx_ucm_bootstrap_dp_ids", "unified_column_mappings", ["mapped_dp_ids"], unique=False, postgresql_using="gin")

    if not _has_table("environmental_data"):
        op.create_table(
            "environmental_data",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("period_year", sa.Integer(), nullable=False),
            sa.Column("period_month", sa.Integer(), nullable=True),
            sa.Column("scope1_total_tco2e", sa.Numeric(18, 4), nullable=True),
            sa.Column("scope2_location_tco2e", sa.Numeric(18, 4), nullable=True),
            sa.Column("scope2_market_tco2e", sa.Numeric(18, 4), nullable=True),
            sa.Column("scope3_total_tco2e", sa.Numeric(18, 4), nullable=True),
            sa.Column("total_energy_consumption_mwh", sa.Numeric(18, 4), nullable=True),
            sa.Column("renewable_energy_mwh", sa.Numeric(18, 4), nullable=True),
            sa.Column("renewable_energy_ratio", sa.Numeric(5, 2), nullable=True),
            sa.Column("total_waste_generated", sa.Numeric(18, 4), nullable=True),
            sa.Column("waste_recycled", sa.Numeric(18, 4), nullable=True),
            sa.Column("waste_incinerated", sa.Numeric(18, 4), nullable=True),
            sa.Column("waste_landfilled", sa.Numeric(18, 4), nullable=True),
            sa.Column("hazardous_waste", sa.Numeric(18, 4), nullable=True),
            sa.Column("water_withdrawal", sa.Numeric(18, 4), nullable=True),
            sa.Column("water_consumption", sa.Numeric(18, 4), nullable=True),
            sa.Column("water_discharge", sa.Numeric(18, 4), nullable=True),
            sa.Column("water_recycling", sa.Numeric(18, 4), nullable=True),
            sa.Column("nox_emission", sa.Numeric(18, 4), nullable=True),
            sa.Column("sox_emission", sa.Numeric(18, 4), nullable=True),
            sa.Column("voc_emission", sa.Numeric(18, 4), nullable=True),
            sa.Column("dust_emission", sa.Numeric(18, 4), nullable=True),
            sa.Column("iso14001_certified", sa.Boolean(), nullable=True),
            sa.Column("iso14001_cert_date", sa.Date(), nullable=True),
            sa.Column("carbon_neutral_certified", sa.Boolean(), nullable=True),
            sa.Column("carbon_neutral_cert_date", sa.Date(), nullable=True),
            sa.Column("ghg_data_source", sa.Text(), nullable=True),
            sa.Column("ghg_calculation_version", sa.Text(), nullable=True),
            sa.Column("status", sa.Text(), server_default="draft", nullable=True),
            sa.Column("approved_by", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("final_approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        )
        op.create_index("idx_env_company", "environmental_data", ["company_id", "period_year"], unique=False)
        op.create_index("idx_env_status", "environmental_data", ["company_id", "status"], unique=False)

    if not _has_table("social_data"):
        op.create_table(
            "social_data",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("data_type", sa.Text(), nullable=False),
            sa.Column("period_year", sa.Integer(), nullable=False),
            sa.Column("total_employees", sa.Integer(), nullable=True),
            sa.Column("male_employees", sa.Integer(), nullable=True),
            sa.Column("female_employees", sa.Integer(), nullable=True),
            sa.Column("disabled_employees", sa.Integer(), nullable=True),
            sa.Column("average_age", sa.Numeric(5, 2), nullable=True),
            sa.Column("turnover_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("total_incidents", sa.Integer(), nullable=True),
            sa.Column("fatal_incidents", sa.Integer(), nullable=True),
            sa.Column("lost_time_injury_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("total_recordable_injury_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("safety_training_hours", sa.Numeric(10, 2), nullable=True),
            sa.Column("total_suppliers", sa.Integer(), nullable=True),
            sa.Column("supplier_purchase_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("esg_evaluated_suppliers", sa.Integer(), nullable=True),
            sa.Column("social_contribution_cost", sa.Numeric(18, 2), nullable=True),
            sa.Column("volunteer_hours", sa.Numeric(10, 2), nullable=True),
            sa.Column("status", sa.Text(), server_default="draft", nullable=True),
            sa.Column("approved_by", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("final_approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.CheckConstraint(
                "data_type IN ('workforce', 'safety', 'supply_chain', 'community')",
                name="chk_social_data_type",
            ),
        )
        op.create_index("idx_social_company", "social_data", ["company_id", "period_year"], unique=False)
        op.create_index("idx_social_status", "social_data", ["company_id", "status"], unique=False)

    if not _has_table("governance_data"):
        op.create_table(
            "governance_data",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("data_type", sa.Text(), nullable=False),
            sa.Column("period_year", sa.Integer(), nullable=False),
            sa.Column("total_board_members", sa.Integer(), nullable=True),
            sa.Column("female_board_members", sa.Integer(), nullable=True),
            sa.Column("board_meetings", sa.Integer(), nullable=True),
            sa.Column("board_attendance_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("board_compensation", sa.Numeric(18, 2), nullable=True),
            sa.Column("corruption_cases", sa.Integer(), nullable=True),
            sa.Column("corruption_reports", sa.Integer(), nullable=True),
            sa.Column("legal_sanctions", sa.Integer(), nullable=True),
            sa.Column("security_incidents", sa.Integer(), nullable=True),
            sa.Column("data_breaches", sa.Integer(), nullable=True),
            sa.Column("security_fines", sa.Numeric(18, 2), nullable=True),
            sa.Column("status", sa.Text(), server_default="draft", nullable=True),
            sa.Column("approved_by", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("final_approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.CheckConstraint(
                "data_type IN ('board', 'compliance', 'ethics', 'risk')",
                name="chk_governance_data_type",
            ),
        )
        op.create_index("idx_gov_company", "governance_data", ["company_id", "period_year"], unique=False)
        op.create_index("idx_gov_status", "governance_data", ["company_id", "status"], unique=False)

    if not _has_table("company_info"):
        op.create_table(
            "company_info",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_name_ko", sa.Text(), nullable=False),
            sa.Column("company_name_en", sa.Text(), nullable=True),
            sa.Column("business_registration_number", sa.Text(), nullable=True),
            sa.Column("representative_name", sa.Text(), nullable=True),
            sa.Column("industry", sa.Text(), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("phone", sa.Text(), nullable=True),
            sa.Column("email", sa.Text(), nullable=True),
            sa.Column("website", sa.Text(), nullable=True),
            sa.Column("mission", sa.Text(), nullable=True),
            sa.Column("vision", sa.Text(), nullable=True),
            sa.Column("esg_goals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("carbon_neutral_target_year", sa.Integer(), nullable=True),
            sa.Column("total_employees", sa.Integer(), nullable=True),
            sa.Column("major_shareholders", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("stakeholders", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("submitted_to_final_report", sa.Boolean(), server_default="false", nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.UniqueConstraint("company_id", name="uq_company_info_company_id"),
        )

    if not _has_table("unmapped_data_points"):
        op.create_table(
            "unmapped_data_points",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("dp_id", sa.Text(), nullable=False),
            sa.Column("dp_code", sa.Text(), nullable=True),
            sa.Column("standard_code", sa.String(length=50), nullable=False),
            sa.Column("name_ko", sa.String(length=200), nullable=False),
            sa.Column("name_en", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=1), nullable=False),
            sa.Column("topic", sa.String(length=100), nullable=True),
            sa.Column("subtopic", sa.String(length=100), nullable=True),
            sa.Column("dp_type", sa.String(length=20), nullable=False),
            sa.Column("unit", sa.String(length=50), nullable=True),
            sa.Column("validation_rules", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
            sa.Column("value_range", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("disclosure_requirement", sa.String(length=20), nullable=True),
            sa.Column("reporting_frequency", sa.String(length=20), nullable=True),
            sa.Column("candidate_unified_column_id", sa.String(length=50), nullable=True),
            sa.Column("mapping_status", sa.Text(), server_default="pending", nullable=False),
            sa.Column("mapping_confidence", sa.Numeric(5, 2), nullable=True),
            sa.Column("mapping_notes", sa.Text(), nullable=True),
            sa.Column("mapped_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("mapped_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
            sa.Column("source_type", sa.Text(), server_default="data_points", nullable=True),
            sa.Column("source_ref_id", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("standard_code", "dp_id", name="uq_unmapped_standard_dp"),
            sa.ForeignKeyConstraint(["candidate_unified_column_id"], ["unified_column_mappings.unified_column_id"]),
            sa.ForeignKeyConstraint(["mapped_by"], ["users.id"]),
            sa.CheckConstraint("category IN ('E', 'S', 'G')", name="chk_unmapped_category"),
            sa.CheckConstraint(
                "dp_type IN ('quantitative', 'qualitative', 'narrative', 'binary')",
                name="chk_unmapped_dp_type",
            ),
            sa.CheckConstraint(
                "disclosure_requirement IN ('필수', '권장', '선택') OR disclosure_requirement IS NULL",
                name="chk_unmapped_disclosure_requirement",
            ),
            sa.CheckConstraint(
                "mapping_status IN ('pending', 'reviewing', 'mapped', 'rejected', 'deferred')",
                name="chk_unmapped_mapping_status",
            ),
        )
        op.create_index("idx_unmapped_dp_id", "unmapped_data_points", ["dp_id"], unique=False)
        op.create_index("idx_unmapped_standard", "unmapped_data_points", ["standard_code"], unique=False)
        op.create_index("idx_unmapped_category_topic", "unmapped_data_points", ["category", "topic"], unique=False)
        op.create_index("idx_unmapped_type", "unmapped_data_points", ["dp_type"], unique=False)
        op.create_index("idx_unmapped_status", "unmapped_data_points", ["mapping_status"], unique=False)
        op.create_index("idx_unmapped_candidate_ucm", "unmapped_data_points", ["candidate_unified_column_id"], unique=False)

    if not _has_table("sr_report_unified_data"):
        op.create_table(
            "sr_report_unified_data",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("period_year", sa.Integer(), nullable=False),
            sa.Column("period_month", sa.Integer(), nullable=True),
            sa.Column("source_entity_type", sa.Text(), nullable=False),
            sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unified_column_id", sa.String(length=50), nullable=True),
            sa.Column("unmapped_dp_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("data_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("data_type", sa.Text(), nullable=False),
            sa.Column("unit", sa.Text(), nullable=True),
            sa.Column("data_source", sa.Text(), nullable=True),
            sa.Column("calculation_method", sa.Text(), nullable=True),
            sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
            sa.Column("included_in_final_report", sa.Boolean(), server_default="false", nullable=True),
            sa.Column("final_report_version", sa.Text(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["unified_column_id"], ["unified_column_mappings.unified_column_id"]),
            sa.ForeignKeyConstraint(["unmapped_dp_id"], ["unmapped_data_points.id"]),
            sa.CheckConstraint(
                "source_entity_type IN ('environmental', 'social', 'governance', 'company_info', 'content', 'chart')",
                name="chk_sr_unified_source_entity_type",
            ),
            sa.CheckConstraint(
                "data_type IN ('quantitative', 'qualitative', 'narrative', 'binary')",
                name="chk_sr_unified_data_type",
            ),
            sa.CheckConstraint(
                "(unified_column_id IS NOT NULL AND unmapped_dp_id IS NULL) "
                "OR (unified_column_id IS NULL AND unmapped_dp_id IS NOT NULL)",
                name="chk_unified_or_unmapped",
            ),
        )
        op.create_index("idx_sr_unified_company", "sr_report_unified_data", ["company_id", "period_year"], unique=False)
        op.create_index("idx_sr_unified_column", "sr_report_unified_data", ["unified_column_id"], unique=False)
        op.create_index("idx_sr_unified_unmapped", "sr_report_unified_data", ["unmapped_dp_id"], unique=False)
        op.create_index("idx_sr_unified_source", "sr_report_unified_data", ["source_entity_type", "source_entity_id"], unique=False)
        op.create_index("idx_sr_unified_final", "sr_report_unified_data", ["company_id", "included_in_final_report"], unique=False)


def downgrade() -> None:
    if _has_table("sr_report_unified_data"):
        op.drop_index("idx_sr_unified_final", table_name="sr_report_unified_data", if_exists=True)
        op.drop_index("idx_sr_unified_source", table_name="sr_report_unified_data", if_exists=True)
        op.drop_index("idx_sr_unified_unmapped", table_name="sr_report_unified_data", if_exists=True)
        op.drop_index("idx_sr_unified_column", table_name="sr_report_unified_data", if_exists=True)
        op.drop_index("idx_sr_unified_company", table_name="sr_report_unified_data", if_exists=True)
        op.drop_table("sr_report_unified_data")

    if _has_table("unmapped_data_points"):
        op.drop_index("idx_unmapped_candidate_ucm", table_name="unmapped_data_points", if_exists=True)
        op.drop_index("idx_unmapped_status", table_name="unmapped_data_points", if_exists=True)
        op.drop_index("idx_unmapped_type", table_name="unmapped_data_points", if_exists=True)
        op.drop_index("idx_unmapped_category_topic", table_name="unmapped_data_points", if_exists=True)
        op.drop_index("idx_unmapped_standard", table_name="unmapped_data_points", if_exists=True)
        op.drop_index("idx_unmapped_dp_id", table_name="unmapped_data_points", if_exists=True)
        op.drop_table("unmapped_data_points")

    if _has_table("company_info"):
        op.drop_table("company_info")

    if _has_table("governance_data"):
        op.drop_index("idx_gov_status", table_name="governance_data", if_exists=True)
        op.drop_index("idx_gov_company", table_name="governance_data", if_exists=True)
        op.drop_table("governance_data")

    if _has_table("social_data"):
        op.drop_index("idx_social_status", table_name="social_data", if_exists=True)
        op.drop_index("idx_social_company", table_name="social_data", if_exists=True)
        op.drop_table("social_data")

    if _has_table("environmental_data"):
        op.drop_index("idx_env_status", table_name="environmental_data", if_exists=True)
        op.drop_index("idx_env_company", table_name="environmental_data", if_exists=True)
        op.drop_table("environmental_data")

    # NOTE:
    # companies/users/unified_column_mappings는 다른 도메인에서 공용으로 사용될 수 있으므로
    # 019 downgrade에서 자동 삭제하지 않는다.

