"""OpenAI VLM으로 단일 이미지에 대해 image_type / caption / confidence(JSON) 추출.

환경 변수: OPENAI_API_KEY (필수)
모델명: SR_IMAGE_VLM_MODEL 환경변수 없이 코드 상수 `DEFAULT_VLM_MODEL` 사용.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.config.settings import get_settings

DEFAULT_VLM_MODEL = "gpt-5-mini"

ALLOWED_IMAGE_TYPES = frozenset(
    {"chart", "graph", "photo", "diagram", "table", "logo", "unknown"}
)

SYSTEM_PROMPT = """You are an assistant that analyzes a single image from a sustainability (SR) report PDF.
Respond with ONE JSON object only, no markdown, no code fences.
Keys:
- "image_type": one of: chart, graph, photo, diagram, table, logo, unknown
- "caption": short description in Korean (1-3 sentences)
- "confidence": a number between 0 and 1 for your confidence in image_type and caption combined
"""


def normalize_image_type(raw: Optional[str]) -> str:
    if not raw or not isinstance(raw, str):
        return "unknown"
    s = raw.strip().lower()
    if s in ALLOWED_IMAGE_TYPES:
        return s
    return "unknown"


def _parse_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    # Strip ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _confidence_to_decimal(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        f = float(v)
        if f < 0 or f > 1:
            return None
        return Decimal(str(round(f, 2)))
    except (TypeError, ValueError):
        return None


def vlm_describe_image(
    image_bytes: bytes,
    mime_type: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    이미지 바이트 + MIME → {image_type, caption_text, caption_confidence}.

    caption_confidence는 NUMERIC(5,2)에 맞게 0~1 소수 둘째 자리까지.
    """
    if not image_bytes:
        raise ValueError("image_bytes is empty")
    key = (api_key or get_settings().openai_api_key).strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not set")

    mdl = (model or DEFAULT_VLM_MODEL).strip()
    mime = (mime_type or "application/octet-stream").strip()
    if not mime.startswith("image/"):
        mime = "image/png"

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai 패키지가 필요합니다: pip install openai") from e

    import base64

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    client = OpenAI(api_key=key)
    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": "Analyze this image and output the JSON as specified.",
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

    # vision + response_format=json_object 는 모델/SDK 조합에서 400(invalid JSON body)이 나는 경우가 있어 사용하지 않음.
    # 시스템 프롬프트로 JSON만 출력 유도 후 _parse_json_object 로 파싱.
    resp = client.chat.completions.create(
        model=mdl,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    choice = resp.choices[0] if resp.choices else None
    raw_text = (choice.message.content or "").strip() if choice and choice.message else ""
    try:
        data = _parse_json_object(raw_text)
    except json.JSONDecodeError:
        logger.warning("[VLM] JSON 파싱 실패, raw 앞 200자: {}", raw_text[:200])
        data = {}

    it = normalize_image_type(data.get("image_type") or data.get("type"))
    cap = data.get("caption") or data.get("caption_text")
    if cap is not None and not isinstance(cap, str):
        cap = str(cap)
    conf = _confidence_to_decimal(data.get("confidence"))

    return {
        "image_type": it,
        "caption_text": (cap.strip() if isinstance(cap, str) and cap.strip() else None),
        "caption_confidence": conf,
    }
