# 전년도 SR 보고서 파싱 및 DP 매핑 가이드

## 📚 관련 문서

이 문서를 읽기 전/후에 다음 문서를 함께 참고하세요:
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 시스템 아키텍처 이해
- [NODES.md](./NODES.md) - RAG Node 및 Gen Node 상세
- [IMAGE_PARSING.md](./IMAGE_PARSING.md) - 이미지 파싱 상세 가이드
- [DATABASE_TABLES_STRUCTURE.md](./DATABASE_TABLES_STRUCTURE.md) - 데이터베이스 구조

---

## 1. 개요

### 1.1 목적

전년도 SR 보고서를 파싱하여 **Index 페이지와 본문을 분리 저장**하고, **DP(Data Point) → 페이지 매핑**을 추출하여 사용자가 선택한 DP에 해당하는 문단을 정확하게 찾을 수 있도록 합니다.

### 1.2 핵심 개념

1. **Index 페이지 분리**: GRI/SASB/IFRS Index 페이지를 자동 감지하여 별도 처리
2. **DP → 페이지 매핑**: Index 테이블에서 DP가 어느 페이지에 있는지 추출
3. **본문 분리 저장**: Index 페이지를 제외한 본문만 페이지 단위로 저장
4. **JOIN 기반 검색**: Index 테이블과 본문 테이블을 JOIN하여 정확한 문단 검색
5. **이미지 처리**: 차트, 그래프 등 이미지를 추출하고 캡셔닝하여 검색 가능하게 함

### 1.3 전체 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 전년도 보고서 수집 및 파싱 (초기 설정)                    │
└─────────────────────────────────────────────────────────────────┘

[1-1] DART API로 전년도 SR 보고서 수집
    ↓
[1-2] PDF 다운로드 및 저장
    ↓
[1-3] Docling으로 PDF 파싱
    ├─→ Index 페이지 감지 및 추출
    ├─→ 본문 페이지 추출 (Index 제외)
    └─→ 이미지 추출
    ↓
[1-4] Index 페이지 파싱
    ├─→ 테이블에서 DP → 페이지 매핑 추출
    │   예: GRI-305-1 → [131]
    └─→ Index 테이블에 저장
    ↓
[1-5] 본문 페이지 파싱
    ├─→ 페이지별 텍스트 추출
    ├─→ 문단 분할
    └─→ 본문 테이블에 저장
    ↓
[1-6] 이미지 처리
    ├─→ 이미지 추출 및 저장
    ├─→ 이미지 캡셔닝 (BLIP 또는 GPT-4o Vision)
    ├─→ 이미지 타입 분류 (차트/그래프/사진)
    └─→ 이미지 메타데이터 저장
    ↓
[1-7] 벡터 임베딩 생성 (선택적)
    └─→ 벡터 DB에 저장 (의미 기반 검색용)
    ↓
[1-8] DB 저장 완료
    ├─→ historical_sr_reports (메타데이터)
    ├─→ sr_report_index (DP → 페이지 매핑)
    ├─→ sr_report_body (본문 내용)
    └─→ sr_report_images (이미지 메타데이터)

┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: 사용자 DP 선택 및 문단 생성 (실시간 요청)                 │
└─────────────────────────────────────────────────────────────────┘

[2-1] 사용자가 플랫폼에서 DP 선택
    예: "GRI-305-1" 선택
    ↓
[2-2] "전년도 보고서에서 찾아서 생성" 버튼 클릭
    ↓
[2-3] Supervisor가 요청 수신
    ├─→ company_id, fiscal_year, dp_id 파라미터 추출
    └─→ RAG Node에 지시
    ↓
[2-4] RAG Node: Index와 본문 JOIN으로 문단 검색
    ├─→ SQL 쿼리 실행:
    │   SELECT b.content_text, b.paragraphs, i.dp_name
    │   FROM sr_report_index i
    │   JOIN sr_report_body b ON b.page_number = ANY(i.page_numbers)
    │   WHERE i.dp_id = 'GRI-305-1'
    │     AND hr.company_id = 'company-001'
    │     AND hr.report_year IN [2023, 2022]
    │
    └─→ 결과: 전년도 보고서 문단 리스트
    ↓
[2-5] RAG Node: 관련 이미지 검색 (선택적)
    ├─→ 같은 페이지의 이미지 검색
    └─→ 이미지 캡션을 FactSheet에 포함
    ↓
[2-6] RAG Node: 검색 결과를 FactSheet로 구성
    ↓
[2-7] Gen Node: 전년도 보고서 문단 참고하여 문단 생성
    ↓
[2-8] Supervisor: 생성 결과 검증
    ↓
[2-9] 결과 반환 (문단 + 참고 이미지)
```

---

## 2. 데이터베이스 스키마

### 2.1 보고서 메타데이터 테이블

```sql
CREATE TABLE historical_sr_reports (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    report_year INTEGER NOT NULL,
    report_name TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'dart' | 'manual_upload'
    total_pages INTEGER,
    index_page_numbers INTEGER[],  -- Index 페이지 번호들 [146, 147]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(company_id, report_year),
    INDEX idx_historical_company_year (company_id, report_year)
);
```

### 2.2 Index 테이블 (DP → 페이지 매핑)

```sql
CREATE TABLE sr_report_index (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    -- ===== Index 정보 =====
    index_type TEXT NOT NULL,  -- 'gri' | 'sasb' | 'ifrs' | 'esrs'
    index_page_number INTEGER,  -- Index 페이지 번호
    
    -- ===== DP 매핑 =====
    dp_id TEXT NOT NULL,  -- 'GRI-305-1', 'S2-15-a' 등
    dp_name TEXT,  -- "직접 온실가스 배출량(Scope 1)"
    page_numbers INTEGER[] NOT NULL,  -- [131] 또는 [7, 8]
    section_title TEXT,  -- "GRI 305: 배출"
    remarks TEXT,  -- 비고
    
    -- ===== 메타데이터 =====
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsing_method TEXT DEFAULT 'docling',  -- 'docling' | 'llamaparse' | 'manual'
    confidence_score DECIMAL(5, 2),  -- 파싱 신뢰도 (0~100)
    
    INDEX idx_index_report (report_id),
    INDEX idx_index_dp (dp_id),
    INDEX idx_index_pages (page_numbers) USING GIN  -- 배열 검색 최적화
);
```

### 2.3 본문 테이블 (페이지별 본문 내용)

```sql
CREATE TABLE sr_report_body (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    -- ===== 페이지 정보 =====
    page_number INTEGER NOT NULL,
    is_index_page BOOLEAN DEFAULT FALSE,  -- Index 페이지 여부
    
    -- ===== 본문 내용 =====
    content_text TEXT NOT NULL,  -- 페이지 전체 텍스트
    content_type TEXT,  -- 'narrative' | 'quantitative' | 'table' | 'mixed'
    
    -- ===== 문단 분할 =====
    paragraphs JSONB,  -- [
    --   {
    --     "order": 1,
    --     "text": "문단 내용...",
    --     "start_char": 0,
    --     "end_char": 500
    --   }
    -- ]
    
    -- ===== 벡터 임베딩 =====
    embedding_id TEXT,  -- 벡터 DB 문서 ID
    embedding_status TEXT DEFAULT 'pending',
    
    -- ===== 메타데이터 =====
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(report_id, page_number),
    INDEX idx_body_report_page (report_id, page_number),
    INDEX idx_body_embedding (embedding_status)
);
```

### 2.4 이미지 테이블

```sql
CREATE TABLE sr_report_images (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    -- ===== 이미지 위치 정보 =====
    page_number INTEGER NOT NULL,
    image_index INTEGER,  -- 페이지 내 이미지 순서 (0-based)
    
    -- ===== 이미지 메타 (로컬 파일 경로 미저장) =====
    -- 바이트 크기는 extracted_data.size_bytes 또는 image_blob 길이로 표현 (image_file_size 컬럼 제거)
    image_width INTEGER,  -- 이미지 너비 (px)
    image_height INTEGER,  -- 이미지 높이 (px)
    
    -- ===== 이미지 타입 =====
    image_type TEXT,  -- 'chart' | 'graph' | 'photo' | 'diagram' | 'table' | 'unknown'
    
    -- ===== 이미지 캡션 =====
    caption_text TEXT,  -- 이미지 설명 (BLIP 또는 GPT-4o Vision)
    caption_confidence DECIMAL(5, 2),  -- 캡션 신뢰도 (0~100)
    
    -- ===== 이미지 내용 분석 =====
    extracted_data JSONB,  -- 차트/그래프에서 추출한 데이터
    -- 예: {
    --   "chart_type": "bar",
    --   "data_points": [
    --     {"label": "2022", "value": 1000},
    --     {"label": "2023", "value": 1200}
    --   ]
    -- }
    
    -- ===== 벡터 임베딩 =====
    caption_embedding_id TEXT,  -- 캡션 텍스트의 벡터 DB ID
    embedding_status TEXT DEFAULT 'pending',
    
    -- ===== 메타데이터 =====
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    INDEX idx_images_report_page (report_id, page_number),
    INDEX idx_images_type (image_type),
    INDEX idx_images_embedding (embedding_status)
);
```

---

## 3. Docling 기반 파서 구현

### 3.1 Docling 설정

```python
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption

class SRReportDoclingParser:
    """Docling 기반 SR 보고서 파서 (Index와 본문 분리)"""
    
    def __init__(self):
        # Docling 설정
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # 네이티브 PDF 우선
        pipeline_options.do_table_structure = True  # 표 구조 인식
        pipeline_options.table_structure_options.do_cell_matching = True
        pipeline_options.do_image_extraction = True  # 이미지 추출 활성화
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
```

### 3.2 Index 페이지 감지 및 파싱

```python
async def parse_and_separate(
    self,
    pdf_path: str,
    company_id: str,
    report_year: int
) -> Dict[str, Any]:
    """
    PDF 파싱 및 Index/본문 분리
    
    Returns:
        {
            "index_data": {
                "index_pages": [146, 147],
                "dp_mappings": [...]
            },
            "body_data": {
                "total_pages": 157,
                "pages": [...]
            },
            "image_data": {
                "total_images": 45,
                "images": [...]
            }
        }
    """
    # 1. Docling으로 PDF 변환
    doc = self.converter.convert(pdf_path)
    
    # 2. Index 페이지 감지 및 추출
    index_data = await self._extract_index(doc)
    
    # 3. 본문 데이터 추출 (Index 페이지 제외)
    body_data = await self._extract_body(doc, index_data["index_pages"])
    
    # 4. 이미지 추출 및 처리
    image_data = await self._extract_images(doc, index_data["index_pages"])
    
    return {
        "index_data": index_data,
        "body_data": body_data,
        "image_data": image_data
    }

async def _extract_index(self, doc) -> Dict[str, Any]:
    """Index 페이지 감지 및 DP 매핑 추출"""
    index_pages = []
    dp_mappings = []
    
    # 1. Index 페이지 감지 (키워드 기반)
    for page_num, page in enumerate(doc.pages, start=1):
        page_text = self._extract_page_text(page)
        
        # Index 키워드 확인
        if self._is_index_page(page_text):
            index_pages.append(page_num)
            
            # 2. Index 테이블 파싱
            tables = self._extract_tables_from_page(page)
            
            for table in tables:
                # 테이블에서 DP → 페이지 매핑 추출
                mappings = self._parse_dp_mappings_from_table(table)
                dp_mappings.extend(mappings)
    
    return {
        "index_pages": index_pages,
        "dp_mappings": dp_mappings
    }

def _is_index_page(self, page_text: str) -> bool:
    """Index 페이지 여부 판단"""
    index_keywords = [
        "gri standards index",
        "gri index",
        "sasb index",
        "ifrs index",
        "esrs index",
        "standards index",
        "index"
    ]
    
    page_lower = page_text.lower()
    return any(keyword in page_lower for keyword in index_keywords)

def _extract_tables_from_page(self, page) -> List[Dict]:
    """페이지에서 테이블 추출 (Docling의 구조 인식 활용)"""
    tables = []
    
    # Docling이 이미 구조화된 테이블 정보 제공
    for item in page.items:
        if hasattr(item, 'table') and item.table:
            table_data = {
                "headers": self._extract_table_headers(item.table),
                "rows": self._extract_table_rows(item.table)
            }
            tables.append(table_data)
    
    return tables

def _parse_dp_mappings_from_table(self, table: Dict) -> List[Dict]:
    """테이블에서 DP → 페이지 매핑 추출"""
    mappings = []
    
    headers = table["headers"]
    rows = table["rows"]
    
    # 컬럼 인덱스 찾기
    dp_col_idx = self._find_column_index(headers, ["gri", "disclosure", "indicator"])
    page_col_idx = self._find_column_index(headers, ["page"])
    name_col_idx = self._find_column_index(headers, ["disclosure", "indicator", "name"])
    
    for row in rows:
        if len(row) <= max(dp_col_idx, page_col_idx, name_col_idx, default=0):
            continue
        
        # DP ID 추출
        dp_text = row[dp_col_idx] if dp_col_idx is not None else ""
        dp_id = self._extract_dp_id(dp_text)
        
        if not dp_id:
            continue
        
        # 페이지 번호 추출
        page_text = row[page_col_idx] if page_col_idx is not None else ""
        page_numbers = self._extract_page_numbers(page_text)
        
        mappings.append({
            "dp_id": dp_id,
            "dp_name": row[name_col_idx] if name_col_idx is not None else "",
            "page_numbers": page_numbers,
            "section_title": self._extract_section_title(row, headers)
        })
    
    return mappings

def _extract_dp_id(self, text: str) -> Optional[str]:
    """텍스트에서 DP ID 추출"""
    import re
    
    # GRI 형식: GRI-2-1, GRI 2-1, 2-1 등
    patterns = [
        r'GRI\s*[-:]?\s*(\d+)\s*[-:]?\s*(\d+)',  # GRI 2-1
        r'(\d+)\s*[-:]?\s*(\d+)',  # 2-1
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"GRI-{match.group(1)}-{match.group(2)}"
    
    # IFRS 형식: S2-15-a, IFRS S2-15-a 등
    patterns = [
        r'(S\d+)\s*[-:]?\s*(\d+)\s*[-:]?\s*([a-z])',  # S2-15-a
        r'IFRS\s+(S\d+)\s*[-:]?\s*(\d+)\s*[-:]?\s*([a-z])',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3).lower()}"
    
    return None

def _extract_page_numbers(self, page_text: str) -> List[int]:
    """페이지 번호 추출 (예: "7,8", "131", "38~39")"""
    import re
    
    page_numbers = []
    
    # 쉼표로 구분된 페이지
    if ',' in page_text:
        parts = page_text.split(',')
        for part in parts:
            nums = re.findall(r'\d+', part)
            page_numbers.extend([int(n) for n in nums])
    
    # 범위 표시 (예: 38~39)
    elif '~' in page_text:
        match = re.search(r'(\d+)\s*~\s*(\d+)', page_text)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            page_numbers.extend(range(start, end + 1))
    
    # 단일 페이지
    else:
        nums = re.findall(r'\d+', page_text)
        page_numbers.extend([int(n) for n in nums])
    
    return sorted(set(page_numbers))  # 중복 제거 및 정렬
```

### 3.3 본문 페이지 추출

```python
async def _extract_body(
    self,
    doc,
    index_pages: List[int]
) -> Dict[str, Any]:
    """본문 데이터 추출 (Index 페이지 제외)"""
    pages = []
    
    for page_num, page in enumerate(doc.pages, start=1):
        # Index 페이지는 제외
        if page_num in index_pages:
            continue
        
        # 페이지 텍스트 추출
        page_text = self._extract_page_text(page)
        
        # 문단 분할
        paragraphs = self._split_into_paragraphs(page_text)
        
        pages.append({
            "page_number": page_num,
            "content_text": page_text,
            "paragraphs": paragraphs,
            "is_index_page": False
        })
    
    return {
        "total_pages": len(doc.pages),
        "pages": pages
    }

def _extract_page_text(self, page) -> str:
    """페이지 텍스트 추출"""
    text_parts = []
    
    for item in page.items:
        if hasattr(item, 'text'):
            text_parts.append(item.text)
        elif hasattr(item, 'content'):
            # 표나 이미지의 캡션 등
            text_parts.append(str(item.content))
    
    return "\n\n".join(text_parts)

def _split_into_paragraphs(self, text: str) -> List[Dict]:
    """텍스트를 문단으로 분할"""
    paragraphs = []
    
    # 빈 줄로 문단 구분
    para_texts = text.split('\n\n')
    
    char_offset = 0
    for idx, para_text in enumerate(para_texts):
        para_text = para_text.strip()
        if len(para_text) > 50:  # 최소 길이 필터
            paragraphs.append({
                "order": idx + 1,
                "text": para_text,
                "start_char": char_offset,
                "end_char": char_offset + len(para_text)
            })
            char_offset += len(para_text) + 2  # '\n\n' 길이
    
    return paragraphs
```

---

## 4. 이미지 처리

### 4.1 이미지 추출 (Docling)

```python
async def _extract_images(
    self,
    doc,
    index_pages: List[int]
) -> Dict[str, Any]:
    """이미지 추출 및 처리"""
    images = []
    image_counter = 0
    
    for page_num, page in enumerate(doc.pages, start=1):
        # Index 페이지는 제외 (선택적)
        if page_num in index_pages:
            continue
        
        # 페이지에서 이미지 추출
        page_images = self._extract_images_from_page(page, page_num, image_counter)
        images.extend(page_images)
        image_counter += len(page_images)
    
    return {
        "total_images": len(images),
        "images": images
    }

def _extract_images_from_page(
    self,
    page,
    page_number: int,
    start_index: int
) -> List[Dict]:
    """페이지에서 이미지 추출"""
    images = []
    
    # Docling이 이미지 정보를 제공
    for item_idx, item in enumerate(page.items):
        if hasattr(item, 'image') and item.image:
            # 이미지 바이너리 추출
            image_bytes = item.image.get_bytes()
            
            # 이미지 저장
            image_filename = f"report_{page_number}_img_{item_idx}.png"
            image_path = self._save_image(image_bytes, image_filename)
            
            # 이미지 메타데이터
            image_info = {
                "page_number": page_number,
                "image_index": start_index + len(images),
                "image_width": item.image.width if hasattr(item.image, 'width') else None,
                "image_height": item.image.height if hasattr(item.image, 'height') else None,
                "image_bytes": image_bytes  # 캡셔닝용
            }
            
            images.append(image_info)
    
    return images

def _save_image(self, image_bytes: bytes, filename: str) -> str:
    """이미지를 파일로 저장"""
    import os
    from pathlib import Path
    
    # 이미지 저장 디렉토리
    image_dir = Path("data/images/sr_reports")
    image_dir.mkdir(parents=True, exist_ok=True)
    
    # 파일 저장
    image_path = image_dir / filename
    with open(image_path, 'wb') as f:
        f.write(image_bytes)
    
    return str(image_path)
```

### 4.2 이미지 캡셔닝

```python
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import io

class ImageCaptionService:
    """이미지 캡셔닝 서비스"""
    
    def __init__(self, model_type: str = "blip"):
        """
        Args:
            model_type: 'blip' | 'gpt4o' | 'blip2'
        """
        self.model_type = model_type
        
        if model_type == "blip":
            self.processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base"
            )
            self.model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base"
            )
        elif model_type == "blip2":
            # BLIP-2는 더 정확하지만 더 무거움
            from transformers import Blip2Processor, Blip2ForConditionalGeneration
            self.processor = Blip2Processor.from_pretrained(
                "Salesforce/blip2-opt-2.7b"
            )
            self.model = Blip2ForConditionalGeneration.from_pretrained(
                "Salesforce/blip2-opt-2.7b"
            )
    
    async def generate_caption(
        self,
        image_bytes: bytes,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        이미지 캡션 생성
        
        Args:
            image_bytes: 이미지 바이너리
            context: 컨텍스트 (예: "SR 보고서의 온실가스 배출량 차트")
        
        Returns:
            {
                "caption": "막대 그래프: 2022-2024년 Scope 1 배출량 추이",
                "confidence": 0.92,
                "image_type": "chart"
            }
        """
        # 이미지 로드
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # 캡션 생성
        if self.model_type in ["blip", "blip2"]:
            caption = await self._generate_caption_blip(image, context)
        elif self.model_type == "gpt4o":
            caption = await self._generate_caption_gpt4o(image_bytes, context)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        # 이미지 타입 분류
        image_type = self._classify_image_type(image_bytes, caption["caption"])
        
        return {
            "caption": caption["caption"],
            "confidence": caption.get("confidence", 0.9),
            "image_type": image_type
        }
    
    async def _generate_caption_blip(
        self,
        image: Image.Image,
        context: Optional[str]
    ) -> Dict[str, Any]:
        """BLIP 모델로 캡션 생성"""
        import torch
        
        # 프롬프트 구성
        if context:
            prompt = f"a chart showing {context}"
        else:
            prompt = "a detailed description of this image"
        
        # 이미지 처리
        inputs = self.processor(image, prompt, return_tensors="pt")
        
        # 생성
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(device)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        out = self.model.generate(**inputs, max_length=200)
        caption = self.processor.decode(out[0], skip_special_tokens=True)
        
        return {
            "caption": caption,
            "confidence": 0.9  # BLIP은 confidence 제공 안 함
        }
    
    async def _generate_caption_gpt4o(
        self,
        image_bytes: bytes,
        context: Optional[str]
    ) -> Dict[str, Any]:
        """GPT-4o Vision으로 캡션 생성 (더 정확하지만 비용 높음)"""
        from openai import OpenAI
        
        client = OpenAI()
        
        # 프롬프트 구성
        prompt = f"""
        Describe this image in detail. 
        If it's a chart or graph, extract the data points and trends.
        {f"Context: {context}" if context else ""}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        caption = response.choices[0].message.content
        
        return {
            "caption": caption,
            "confidence": 0.95  # GPT-4o는 더 정확
        }
    
    def _classify_image_type(
        self,
        image_bytes: bytes,
        caption: str
    ) -> str:
        """이미지 타입 분류"""
        caption_lower = caption.lower()
        
        # 차트/그래프 키워드
        chart_keywords = ["chart", "graph", "bar", "line", "pie", "scatter", "plot"]
        if any(kw in caption_lower for kw in chart_keywords):
            return "chart"
        
        # 표 키워드
        table_keywords = ["table", "grid", "matrix"]
        if any(kw in caption_lower for kw in table_keywords):
            return "table"
        
        # 다이어그램 키워드
        diagram_keywords = ["diagram", "flowchart", "process"]
        if any(kw in caption_lower for kw in diagram_keywords):
            return "diagram"
        
        # 사진 키워드
        photo_keywords = ["photo", "image", "picture", "photograph"]
        if any(kw in caption_lower for kw in photo_keywords):
            return "photo"
        
        return "unknown"
```

### 4.3 이미지 데이터 추출 (차트/그래프)

```python
class ChartDataExtractor:
    """차트/그래프에서 데이터 추출"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def extract_chart_data(
        self,
        image_bytes: bytes,
        caption: str,
        image_type: str
    ) -> Dict[str, Any]:
        """
        차트/그래프에서 데이터 포인트 추출
        
        Returns:
            {
                "chart_type": "bar",
                "data_points": [
                    {"label": "2022", "value": 1000},
                    {"label": "2023", "value": 1200}
                ],
                "trend": "increasing"
            }
        """
        if image_type not in ["chart", "graph"]:
            return None
        
        # GPT-4o Vision으로 데이터 추출
        from openai import OpenAI
        import base64
        
        client = OpenAI()
        
        prompt = f"""
        Extract all data points from this chart/graph.
        Return the data in JSON format:
        {{
            "chart_type": "bar|line|pie|scatter",
            "data_points": [
                {{"label": "x-axis label", "value": number}},
                ...
            ],
            "trend": "increasing|decreasing|stable",
            "unit": "unit if available"
        }}
        
        Caption: {caption}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        import json
        chart_data = json.loads(response.choices[0].message.content)
        
        return chart_data
```

### 4.4 이미지 처리 통합

```python
async def process_images(
    self,
    images: List[Dict],
    report_id: str
) -> List[Dict]:
    """이미지 처리 통합 파이프라인"""
    processed_images = []
    
    caption_service = ImageCaptionService(model_type="blip")
    chart_extractor = ChartDataExtractor(llm_client=self.llm)
    
    for img_info in images:
        # 1. 이미지 캡셔닝
        caption_result = await caption_service.generate_caption(
            image_bytes=img_info["image_bytes"],
            context=f"SR 보고서 {img_info['page_number']}페이지"
        )
        
        # 2. 차트/그래프인 경우 데이터 추출
        extracted_data = None
        if caption_result["image_type"] in ["chart", "graph"]:
            extracted_data = await chart_extractor.extract_chart_data(
                image_bytes=img_info["image_bytes"],
                caption=caption_result["caption"],
                image_type=caption_result["image_type"]
            )
        
        # 3. DB 저장용 데이터 구성
        processed_images.append({
            "report_id": report_id,
            "page_number": img_info["page_number"],
            "image_index": img_info["image_index"],
            "image_width": img_info.get("image_width"),
            "image_height": img_info.get("image_height"),
            "image_type": caption_result["image_type"],
            "caption_text": caption_result["caption"],
            "caption_confidence": caption_result["confidence"],
            "extracted_data": extracted_data
        })
    
    return processed_images
```

---

## 5. DB 저장 및 JOIN 쿼리

### 5.1 데이터 저장

```python
class HistoricalReportService:
    """전년도 보고서 저장 서비스"""
    
    async def save_parsed_report(
        self,
        company_id: str,
        report_year: int,
        parsed_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """파싱된 데이터를 DB에 저장"""
        
        # 1. 보고서 메타데이터 저장
        report_id = await self.db.execute(
            """
            INSERT INTO historical_sr_reports
            (company_id, report_year, report_name, total_pages, index_page_numbers)
            VALUES (:company_id, :report_year, :report_name, :total_pages, :index_pages)
            RETURNING id
            """,
            {
                "company_id": company_id,
                "report_year": report_year,
                "report_name": "지속가능경영보고서",
                "total_pages": parsed_data["body_data"]["total_pages"],
                "index_pages": parsed_data["index_data"]["index_pages"]
            }
        )
        
        # 2. Index 데이터 저장
        for mapping in parsed_data["index_data"]["dp_mappings"]:
            await self.db.execute(
                """
                INSERT INTO sr_report_index
                (report_id, index_type, dp_id, dp_name, page_numbers, section_title)
                VALUES (:report_id, :index_type, :dp_id, :dp_name, :page_numbers, :section_title)
                """,
                {
                    "report_id": report_id,
                    "index_type": self._detect_index_type(mapping["dp_id"]),
                    "dp_id": mapping["dp_id"],
                    "dp_name": mapping["dp_name"],
                    "page_numbers": mapping["page_numbers"],
                    "section_title": mapping.get("section_title")
                }
            )
        
        # 3. 본문 데이터 저장
        for page_data in parsed_data["body_data"]["pages"]:
            await self.db.execute(
                """
                INSERT INTO sr_report_body
                (report_id, page_number, content_text, paragraphs, is_index_page)
                VALUES (:report_id, :page_number, :content, :paragraphs, :is_index)
                """,
                {
                    "report_id": report_id,
                    "page_number": page_data["page_number"],
                    "content": page_data["content_text"],
                    "paragraphs": json.dumps(page_data["paragraphs"]),
                    "is_index": False
                }
            )
        
        # 4. 이미지 데이터 저장
        processed_images = await self.process_images(
            parsed_data["image_data"]["images"],
            report_id
        )
        
        for img_data in processed_images:
            await self.db.execute(
                """
                INSERT INTO sr_report_images
                (report_id, page_number, image_index,
                 image_width, image_height, image_type, caption_text,
                 caption_confidence, extracted_data)
                VALUES (:report_id, :page_number, :image_index,
                        :width, :height, :image_type, :caption,
                        :confidence, :extracted_data)
                """,
                {
                    "report_id": img_data["report_id"],
                    "page_number": img_data["page_number"],
                    "image_index": img_data["image_index"],
                    "width": img_data.get("image_width"),
                    "height": img_data.get("image_height"),
                    "image_type": img_data["image_type"],
                    "caption": img_data["caption_text"],
                    "confidence": img_data["caption_confidence"],
                    "extracted_data": json.dumps(img_data.get("extracted_data"))
                }
            )
        
        return {"report_id": report_id, "status": "completed"}
```

### 5.2 JOIN 기반 검색

```python
async def find_paragraphs_by_dp(
    self,
    dp_id: str,
    company_id: str,
    reference_years: List[int]
) -> List[Dict]:
    """
    DP로 문단 검색 (Index와 본문 JOIN)
    
    이 쿼리가 핵심! Index 테이블과 본문 테이블을 JOIN하여
    정확한 페이지의 문단을 찾습니다.
    """
    query = """
        SELECT 
            b.page_number,
            b.content_text,
            b.paragraphs,
            i.dp_name,
            i.section_title,
            i.confidence_score,
            hr.report_year
        FROM sr_report_index i
        INNER JOIN historical_sr_reports hr 
            ON i.report_id = hr.id
        INNER JOIN sr_report_body b 
            ON b.report_id = hr.id 
            AND b.page_number = ANY(i.page_numbers)
        WHERE 
            hr.company_id = :company_id
            AND hr.report_year IN :reference_years
            AND i.dp_id = :dp_id
            AND i.confidence_score >= 70
        ORDER BY 
            hr.report_year DESC,
            i.confidence_score DESC,
            b.page_number
    """
    
    results = await self.db.fetch_all(query, {
        "company_id": company_id,
        "reference_years": tuple(reference_years),
        "dp_id": dp_id
    })
    
    return results

async def find_images_by_dp(
    self,
    dp_id: str,
    company_id: str,
    reference_years: List[int]
) -> List[Dict]:
    """
    DP와 관련된 이미지 검색
    같은 페이지에 있는 이미지를 찾습니다.
    """
    query = """
        SELECT 
            img.page_number,
            img.caption_text,
            img.image_type,
            img.extracted_data,
            i.dp_name,
            hr.report_year
        FROM sr_report_index i
        INNER JOIN historical_sr_reports hr 
            ON i.report_id = hr.id
        INNER JOIN sr_report_images img 
            ON img.report_id = hr.id 
            AND img.page_number = ANY(i.page_numbers)
        WHERE 
            hr.company_id = :company_id
            AND hr.report_year IN :reference_years
            AND i.dp_id = :dp_id
            AND img.image_type IN ('chart', 'graph')
        ORDER BY 
            hr.report_year DESC,
            img.page_number
    """
    
    results = await self.db.fetch_all(query, {
        "company_id": company_id,
        "reference_years": tuple(reference_years),
        "dp_id": dp_id
    })
    
    return results
```

---

## 6. 사용 예시

### 6.1 전년도 보고서 파싱

```python
from ifrs_agent.service.historical_report_parser import SRReportDoclingParser
from ifrs_agent.service.historical_report_service import HistoricalReportService

# 1. PDF 파싱
parser = SRReportDoclingParser()
parsed_data = await parser.parse_and_separate(
    pdf_path="samsung_sds_sr_2024.pdf",
    company_id="company-001",
    report_year=2024
)

# 2. DB 저장
service = HistoricalReportService(db_session)
result = await service.save_parsed_report(
    company_id="company-001",
    report_year=2024,
    parsed_data=parsed_data
)

print(f"✅ 보고서 파싱 완료: {result['report_id']}")
print(f"   - Index 페이지: {len(parsed_data['index_data']['index_pages'])}개")
print(f"   - DP 매핑: {len(parsed_data['index_data']['dp_mappings'])}개")
print(f"   - 본문 페이지: {len(parsed_data['body_data']['pages'])}개")
print(f"   - 이미지: {len(parsed_data['image_data']['images'])}개")
```

### 6.2 DP 기반 문단 검색

```python
# 사용자가 "GRI-305-1" 선택
paragraphs = await service.find_paragraphs_by_dp(
    dp_id="GRI-305-1",
    company_id="company-001",
    reference_years=[2023, 2022]
)

# 결과:
# [
#     {
#         "report_year": 2023,
#         "page_number": 131,
#         "content_text": "본사는 2023년 기준 Scope 1 배출량...",
#         "dp_name": "직접 온실가스 배출량(Scope 1)",
#         "section_title": "GRI 305: 배출"
#     }
# ]

# 관련 이미지도 검색
images = await service.find_images_by_dp(
    dp_id="GRI-305-1",
    company_id="company-001",
    reference_years=[2023, 2022]
)

# 결과:
# [
#     {
#         "report_year": 2023,
#         "page_number": 131,
#         (로컬 image_file_path 컬럼 없음 — 캡션·extracted_data 등으로 식별)
#         "caption_text": "막대 그래프: 2022-2024년 Scope 1 배출량 추이",
#         "image_type": "chart",
#         "extracted_data": {
#             "chart_type": "bar",
#             "data_points": [
#                 {"label": "2022", "value": 1000},
#                 {"label": "2023", "value": 1100}
#             ]
#         }
#     }
# ]
```

---

## 7. 이미지 처리 전략 요약

### 7.1 이미지 추출 방법

1. **Docling**: PDF에서 이미지 자동 추출
2. **파일 저장**: PNG 형식으로 저장
3. **메타데이터 기록**: 페이지 번호, 이미지 인덱스 등

### 7.2 이미지 캡셔닝 방법

| 방법 | 정확도 | 속도 | 비용 | 권장 사용 |
|------|--------|------|------|----------|
| **BLIP** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 무료 | 기본 (대부분의 경우) |
| **BLIP-2** | ⭐⭐⭐⭐ | ⭐⭐⭐ | 무료 | 더 정확한 캡션 필요 시 |
| **GPT-4o Vision** | ⭐⭐⭐⭐⭐ | ⭐⭐ | 유료 | 차트 데이터 추출 시 |

### 7.3 이미지 타입별 처리

- **차트/그래프**: 데이터 포인트 추출 (GPT-4o Vision)
- **표**: OCR 또는 GPT-4o Vision으로 데이터 추출
- **사진**: 캡셔닝만 수행
- **다이어그램**: 캡셔닝 및 구조 설명

---

## 8. 참고사항

### 8.1 Docling 설치

```bash
pip install docling
```

### 8.2 이미지 캡셔닝 모델 설치

```bash
# BLIP
pip install transformers torch pillow

# BLIP-2 (선택적)
pip install transformers[torch] accelerate
```

### 8.3 성능 최적화

- **이미지 캡셔닝**: 배치 처리로 속도 향상
- **차트 데이터 추출**: 차트/그래프만 GPT-4o Vision 사용
- **이미지 저장**: 압축된 형식 사용 (PNG → WebP)

---

## 9. 다음 단계

1. **벡터 임베딩 생성**: 이미지 캡션도 벡터 DB에 저장하여 검색 가능하게
2. **이미지 검색 통합**: RAG Node에서 이미지도 함께 검색
3. **Gen Node 연동**: 생성된 문단에 관련 이미지 자동 포함
