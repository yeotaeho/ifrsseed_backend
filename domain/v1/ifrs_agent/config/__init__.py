"""ifrs_agent 설정 패키지.

기존 패키지 import 호환을 위해 공통 설정을 재노출한다.
"""

from backend.core.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]

