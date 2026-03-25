"""호환 재export — 실제 구현: ``backend.core.db``."""

from backend.core.db import (  # noqa: F401
    DATABASE_URL,
    Base,
    SessionLocal,
    engine,
    get_db,
    get_session,
    init_db,
)


def create_sample_dp():
    """샘플 DP (개발용)."""
    from backend.domain.v1.esg_data.models.bases import DPTypeEnum, DataPoint

    db = get_session()
    try:
        new_dp = DataPoint(
            dp_id="S2-29-a",
            dp_code="IFRS_S2_SCOPE1_EMISSIONS",
            name_ko="Scope 1 온실가스 배출량",
            name_en="Scope 1 GHG emissions",
            standard="IFRS_S2",
            category="E",
            topic="지표 및 목표",
            dp_type=DPTypeEnum.QUANTITATIVE,
            is_active=True,
        )
        db.add(new_dp)
        db.commit()
        return new_dp
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
