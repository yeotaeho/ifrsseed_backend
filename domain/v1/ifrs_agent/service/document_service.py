"""문서 처리 통합 서비스

PDF 파싱, 청크 분할, 임베딩 생성. document_chunks 테이블 제거로 벡터 DB 저장은 비활성화되어 있습니다.
"""
from typing import List, Optional, Dict, Any
from pathlib import Path
from loguru import logger

from backend.domain.v1.ifrs_agent.repository.vector_store_repository import VectorStoreRepository

from .embedding_service import EmbeddingService
from .image_caption_service import ImageCaptionService
from .pdf_parser_service import PDFParserService
from backend.core.config.settings import get_settings


class DocumentService:
    """문서 처리 통합 서비스
    
    PDF를 파싱하여 벡터 DB에 저장하는 전체 프로세스를 담당합니다.
    """
    
    def __init__(
        self,
        parser_service: Optional[PDFParserService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        image_caption_service: Optional[ImageCaptionService] = None,
        vector_repository: Optional[VectorStoreRepository] = None
    ):
        """문서 서비스 초기화
        
        Args:
            parser_service: PDF 파서 서비스 (None이면 자동 생성)
            embedding_service: 임베딩 서비스 (None이면 자동 생성)
            image_caption_service: 이미지 캡셔닝 서비스 (None이면 자동 생성)
            vector_repository: 벡터 저장소 Repository (None이면 자동 생성)
        """
        self.settings = get_settings()
        
        self.parser_service = parser_service or PDFParserService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.image_caption_service = image_caption_service or ImageCaptionService()
        self.vector_repository = vector_repository or VectorStoreRepository()
    
    def store_pdf_to_vector_db(
        self,
        pdf_path: str,
        document_type: str = "standard",
        standard: Optional[str] = None,
        company_id: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        parser_type: str = "auto",
        extract_images: bool = True,
        image_min_size: int = 1000,
        filter_meaningless_images: bool = True
    ) -> int:
        """PDF 벡터 DB 저장 (비활성화)

        document_chunks 테이블 제거로 저장 기능이 꺼져 있습니다. 0을 반환합니다.
        """
        logger.warning("store_pdf_to_vector_db: document_chunks 테이블 제거로 비활성화됨")
        return 0
    
    def search_documents(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[tuple[Any, float]]:
        """문서 검색 (비활성화: document_chunks 제거로 빈 리스트 반환)"""
        return []

