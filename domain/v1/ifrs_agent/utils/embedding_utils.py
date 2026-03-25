"""임베딩 생성 유틸리티 모듈 (Deprecated)

이 모듈은 하위 호환성을 위해 유지됩니다.
새로운 코드는 `ifrs_agent.service.embedding_text_service.EmbeddingTextService`를 사용하세요.

각 테이블의 컬럼들을 종합적으로 결합하여 임베딩 텍스트를 생성합니다.
"""
from typing import Dict, List, Any, Optional
import warnings
from backend.domain.v1.ifrs_agent.service.embedding_text_service import EmbeddingTextService
from backend.domain.v1.esg_data.models.bases import (
    DataPoint,
    Glossary,
    Rulebook,
    Standard,
    SynonymGlossary,
    UnifiedColumnMapping,
)

# 싱글톤 인스턴스
_embedding_text_service = EmbeddingTextService()


def generate_data_point_embedding_text(dp: DataPoint) -> str:
    """DataPoint 테이블의 포괄적인 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_data_point_text()` 사용 권장
    
    Args:
        dp: DataPoint 객체
        
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_data_point_embedding_text()는 deprecated입니다. "
        "EmbeddingTextService.generate_data_point_text()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_data_point_text(dp)


def generate_synonym_glossary_embedding_text(term: SynonymGlossary) -> str:
    """SynonymGlossary/Glossary 테이블의 포괄적인 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_glossary_text()` 사용 권장
    
    Args:
        term: SynonymGlossary/Glossary 객체
        
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_synonym_glossary_embedding_text()는 deprecated입니다. "
        "EmbeddingTextService.generate_glossary_text()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_glossary_text(term)


def generate_glossary_embedding_text(term: Glossary) -> str:
    """Glossary 테이블의 포괄적인 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_glossary_text()` 사용 권장
    
    Args:
        term: Glossary 객체
        
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_glossary_embedding_text()는 deprecated입니다. "
        "EmbeddingTextService.generate_glossary_text()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_glossary_text(term)


def generate_rulebook_embedding_text(rule: Rulebook) -> str:
    """Rulebook 테이블의 포괄적인 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_rulebook_text()` 사용 권장
    
    Args:
        rule: Rulebook 객체
        
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_rulebook_embedding_text()는 deprecated입니다. "
        "EmbeddingTextService.generate_rulebook_text()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_rulebook_text(rule)


def generate_standard_embedding_text(std: Standard) -> str:
    """Standard 테이블의 포괄적인 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_standard_text()` 사용 권장
    
    Args:
        std: Standard 객체
        
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_standard_embedding_text()는 deprecated입니다. "
        "EmbeddingTextService.generate_standard_text()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_standard_text(std)


# 편의 함수: 딕셔너리에서 직접 생성 (DB 객체가 아닌 경우)
def generate_data_point_embedding_text_from_dict(dp_data: Dict[str, Any]) -> str:
    """DataPoint 딕셔너리에서 임베딩 텍스트 생성 (Deprecated)
    
    Deprecated: `EmbeddingTextService.generate_data_point_text_from_dict()` 사용 권장
    
    Args:
        dp_data: DataPoint 딕셔너리
    
    Returns:
        임베딩 생성에 사용될 텍스트
    """
    warnings.warn(
        "generate_data_point_embedding_text_from_dict()는 deprecated입니다. "
        "EmbeddingTextService.generate_data_point_text_from_dict()를 사용하세요.",
        DeprecationWarning,
        stacklevel=2
    )
    return _embedding_text_service.generate_data_point_text_from_dict(dp_data)
