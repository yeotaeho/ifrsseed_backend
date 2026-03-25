"""SR 보고서 파싱 - historical_sr_reports (메타데이터·인덱스 페이지 감지).

§10: 메타는 에이전트·parsing·매핑·저장 흐름에서 parsing 담당.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from .common import PYMUPDF_AVAILABLE, open_pdf


class PDFParser:
    """PDF 파싱 및 메타데이터 추출."""

    INDEX_SEARCH_TAIL_PAGES = 30
    # 필수: 둘 다 있어야 인덱스 페이지 후보 (영문 단어 경계로 매칭)
    INDEX_REQUIRED_PATTERNS = (r"\bindex\b", r"\bpage\b")
    # 하나라도 있으면 인덱스 페이지로 판단 (영문 단어 경계 또는 한글 문자열)
    INDEX_ANY_OF_PATTERNS = (r"\bcode\b", r"\bdisclosure\b", r"항목", r"구분")

    def parse(
        self,
        pdf_path_or_bytes: Union[str, bytes],
        company: str,
        year: int,
    ) -> Dict[str, Any]:
        """
        PDF를 파싱하고 historical_sr_reports 테이블용 데이터를 생성합니다.
        """
        if not PYMUPDF_AVAILABLE:
            return {"error": "PyMuPDF(pymupdf) 패키지가 설치되지 않았습니다."}

        try:
            doc = open_pdf(pdf_path_or_bytes)
            total_pages = len(doc)
            index_page_numbers = self._find_index_pages(doc, total_pages)
            doc.close()

            report_id = str(uuid.uuid4())
            report_name = f"{company} 지속가능경영보고서 {year}"
            historical_sr_reports = {
                "id": report_id,
                "company_id": None,
                "report_year": year,
                "report_name": report_name,
                "source": "sr_agent",
                "total_pages": total_pages,
                "index_page_numbers": index_page_numbers,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return {"historical_sr_reports": historical_sr_reports}
        except Exception as e:
            logger.error(f"PyMuPDF 파싱 오류: {e}")
            return {"error": str(e)}

    def _find_index_pages(self, doc: Any, total_pages: int) -> List[int]:
        index_page_numbers: List[int] = []
        start = max(1, total_pages - self.INDEX_SEARCH_TAIL_PAGES + 1)
        index_candidate_pages = list(range(start, total_pages + 1))

        for api_page in index_candidate_pages:
            page_text = self._get_page_text(doc, api_page)
            if self._is_index_page(page_text):
                index_page_numbers.append(api_page)

        index_page_numbers = self._expand_continuous_pages(
            doc, index_page_numbers, index_candidate_pages
        )
        if index_page_numbers:
            index_page_numbers = self._keep_last_run(index_page_numbers)
        return index_page_numbers

    def _get_page_text(self, doc: Any, page_no_1based: int) -> str:
        try:
            page = doc[page_no_1based - 1]
            return page.get_text() or ""
        except Exception:
            return ""

    def _is_index_page(self, page_text: str) -> bool:
        """정규표현식으로 필수 키워드(index, page) 및 선택 키워드(code, disclosure, 항목, 구분) 매칭."""
        if not page_text or not page_text.strip():
            return False
        page_lower = page_text.lower()
        # 필수: index, page 둘 다 존재 (단어 경계)
        for pattern in self.INDEX_REQUIRED_PATTERNS:
            if not re.search(pattern, page_lower, re.IGNORECASE):
                return False
        # 선택: 하나라도 있으면 인덱스 페이지로 판단
        for pattern in self.INDEX_ANY_OF_PATTERNS:
            if re.search(pattern, page_text, re.IGNORECASE if pattern.isascii() else 0):
                return True
        return False

    def _expand_continuous_pages(
        self, doc: Any, pages: List[int], candidates: List[int]
    ) -> List[int]:
        expanded = set(pages)
        for api_page in candidates:
            if api_page in expanded:
                continue
            prev = api_page - 1
            if prev not in expanded:
                continue
            run_min = prev
            while run_min - 1 in expanded:
                run_min -= 1
            if api_page > run_min + 5:
                continue
            page_text = self._get_page_text(doc, api_page)
            if self._is_index_page(page_text) and len(page_text.strip()) > 100:
                expanded.add(api_page)
                pages.append(api_page)
        pages.sort()
        return pages

    def _keep_last_run(self, pages: List[int]) -> List[int]:
        if not pages:
            return []
        runs: List[List[int]] = []
        cur: List[int] = [pages[0]]
        for p in pages[1:]:
            if p == cur[-1] + 1:
                cur.append(p)
            else:
                runs.append(cur)
                cur = [p]
        runs.append(cur)
        return max(runs, key=lambda r: r[-1])


def parse_sr_report_metadata(
    pdf_path_or_bytes: Union[str, bytes],
    company: str,
    year: int,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    PDF에서 보고서 메타데이터를 추출하여 historical_sr_reports 1건 분량을 반환합니다.

    Returns:
        {"historical_sr_reports": {...}} 또는 {"error": "..."}
    """
    parser = PDFParser()
    result = parser.parse(pdf_path_or_bytes, company, year)
    if "error" in result:
        return result
    row = result["historical_sr_reports"]
    if company_id is not None:
        row["company_id"] = company_id
    return {"historical_sr_reports": row}
