"""SR 보고서 파싱 상태/DTO - PDF bytes 기반 4개 테이블 추출 플로우용

Agent와 Orchestrator 간 상태 전달에 사용합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PDFBytesState:
    """PDF를 bytes로 받아서 메모리에서 처리하기 위한 상태"""
    company: str
    year: int
    pdf_bytes: Optional[bytes] = None
    pdf_url: Optional[str] = None
    company_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.pdf_bytes is not None and len(self.pdf_bytes) > 0


@dataclass
class HistoricalSRReportsRow:
    """historical_sr_reports 테이블 행 DTO"""
    id: str
    company_id: Optional[str]
    report_year: int
    report_name: str
    source: str
    total_pages: int
    index_page_numbers: List[int]
    created_at: str


@dataclass
class SrReportIndexRow:
    """sr_report_index 테이블 행 DTO"""
    id: str
    report_id: str
    index_type: str
    index_page_number: int
    dp_id: str
    dp_name: Optional[str]
    page_numbers: List[int]
    section_title: Optional[str]
    remarks: Optional[str]
    parsed_at: str
    parsing_method: str
    confidence_score: Optional[float]


@dataclass
class SrReportBodyRow:
    """sr_report_body 테이블 행 DTO"""
    id: str
    report_id: str
    page_number: int
    is_index_page: bool
    content_text: str
    content_type: Optional[str]
    paragraphs: List[Dict[str, Any]]
    embedding_id: Optional[str]
    embedding_status: str
    parsed_at: str
    toc_path: Optional[List[str]] = None


@dataclass
class SrReportImagesRow:
    """sr_report_images 테이블 행 DTO"""
    id: str
    report_id: str
    page_number: int
    image_index: int
    image_width: Optional[int]
    image_height: Optional[int]
    image_type: Optional[str]
    caption_text: Optional[str]
    caption_confidence: Optional[float]
    extracted_data: Optional[Dict[str, Any]]
    caption_embedding_id: Optional[str]
    embedding_status: str
    extracted_at: str


@dataclass
class SRParsingResult:
    """4개 테이블 파싱 결과를 담는 통합 DTO"""
    historical_sr_reports: Optional[Dict[str, Any]] = None
    sr_report_index: List[Dict[str, Any]] = field(default_factory=list)
    sr_report_body: List[Dict[str, Any]] = field(default_factory=list)
    sr_report_images: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 가능한 dict로 변환"""
        return {
            "historical_sr_reports": self.historical_sr_reports,
            "sr_report_index": self.sr_report_index,
            "sr_report_body": self.sr_report_body,
            "sr_report_images": self.sr_report_images,
            "error": self.error,
        }

    @property
    def is_success(self) -> bool:
        return self.error is None and self.historical_sr_reports is not None
