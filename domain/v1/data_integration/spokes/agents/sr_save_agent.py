"""LLM 기반 SR 파싱 및 저장 에이전트

- 오케스트레이션: OpenAI GPT(ChatOpenAI)가 순서에 따라 parse_* / save_* 도구를 호출합니다.
- 실제 파싱: parse_metadata_tool, parse_index_tool(Docling + LlamaParse), parse_body_tool 등이 수행합니다.
- 인덱스 저장: parse_index_tool 반환값(sr_report_index 리스트)을 받은 뒤, 각 행이 삽입에 적합한 컬럼(dp_id, index_type, dp_name, page_numbers, section_title)에 맞는지 검토하고, 잘못 매핑된 값은 올바른 컬럼으로 선정·보정한 뒤 save_sr_report_index로 저장합니다.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from backend.core.config.settings import get_settings
from backend.domain.shared.tool.sr_report_tools import SR_PARSE_TOOLS
from backend.domain.shared.tool.sr_report.save.sr_save_tools import SR_SAVE_TOOLS


class SRSaveAgent:
    """
    LLM/도구 기반 SR 파싱 및 저장 에이전트.
    
    pdf_bytes를 받아 LLM이 판단하여 parse_* 도구로 파싱하고,
    그 결과를 save_* 도구로 4개 테이블에 저장합니다.
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model_name: str = "gpt-5-mini",
        max_iterations: int = 100,
    ):
        self.api_key = openai_api_key or get_settings().openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        
        self.model_name = model_name
        self.max_iterations = max_iterations
        
        # 파싱 + 저장 도구 바인딩 (오케스트레이션용 LLM = OpenAI GPT)
        all_tools = SR_PARSE_TOOLS + SR_SAVE_TOOLS
        self.llm = ChatOpenAI(
            model=model_name,
            api_key=self.api_key,
            temperature=0,
        ).bind_tools(all_tools)
    
    def build_system_prompt(self) -> str:
        """파싱 및 저장 에이전트 시스템 프롬프트"""
        return """당신은 SR(지속가능경영) 보고서 PDF를 파싱하고 DB 4개 테이블에 저장하는 에이전트입니다.

목표: 제공된 PDF bytes(base64)를 파싱한 뒤, 그 결과를 DB에 저장합니다.

규칙:
1. 한 번에 하나의 도구만 호출합니다.
2. 반드시 아래 순서를 지킵니다.

--- 1단계: 메타데이터 파싱 (필수) ---
parse_metadata_tool(pdf_bytes_b64, company, year, company_id)를 호출합니다.
- 반환된 historical_sr_reports에서 report_id와 index_page_numbers를 추출하고 기억합니다.

--- 2단계: 메타데이터 저장 (필수) ---
save_historical_sr_report(...)를 호출하여 메타데이터를 저장합니다.
- 반환된 report_id를 기억하고, 이후 모든 도구 호출에 이 report_id를 사용합니다.

--- 3단계: 인덱스 파싱 (index_page_numbers가 있으면) ---
parse_index_tool(pdf_bytes_b64, report_id, index_page_numbers)를 호출합니다.

--- 4단계: 인덱스 검토 후 배치 저장 (파싱 결과가 있으면) ---
parse_index_tool이 반환한 sr_report_index 리스트의 각 행을 검토하세요.
- 스키마: dp_id(공시 식별자, 예 GRI-2-1/S1-2-d/TC-SI-130a.1), index_type(gri|ifrs|sasb), dp_name(지표명), page_numbers(페이지 번호 배열), section_title(섹션 제목).
- 값이 잘못된 컬럼에 들어갔으면(예: dp_id에 "ESRS2"만 있음, section_title에 지표명이 있음) 올바른 컬럼으로 재배치합니다.
- 원문에 없는 값을 만들지 말고, 보정 불가 시 해당 필드는 null 또는 기존 값 유지.
- **중요: 모든 행을 검토하고 보정한 뒤, save_sr_report_index_batch(report_id, indices=[...])를 한 번만 호출하여 모든 인덱스를 한 번에 저장하세요.**

--- 5단계: 종료 ---
메타·인덱스 저장까지 완료했으면 "파싱 및 저장 완료"라고 보고합니다.
(본문·이미지는 sr_body_agent, sr_images_agent 경로로 별도 실행)

최대 {max_iterations}번 도구 호출. 반드시 1→2→3→4→5 순서를 지킵니다.
"""
    
    async def execute(
        self,
        pdf_bytes: bytes,
        company: str,
        year: int,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        pdf_bytes를 파싱하고 LLM/도구로 4개 테이블에 저장합니다.
        
        Returns:
            {"success": bool, "message": str, "report_id": str}
        """
        import base64
        
        # pdf_bytes를 base64로 인코딩
        pdf_bytes_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        system_prompt = self.build_system_prompt().replace("{max_iterations}", str(self.max_iterations))
        user_prompt = f"""아래는 {company}의 {year}년 SR 보고서 PDF bytes(base64)입니다.

company: {company}
year: {year}
company_id: {company_id or "null"}
pdf_bytes_b64: {pdf_bytes_b64[:100]}... (총 {len(pdf_bytes_b64)} 문자)

위 PDF를 파싱하고 4개 테이블에 저장하세요.
1단계부터 순서대로 진행하고, 모든 데이터를 빠짐없이 처리하세요."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        report_id = None
        result = {"success": False, "message": "", "report_id": None}
        
        for i in range(self.max_iterations):
            logger.info(f"[SRSaveAgent] 반복 {i+1}/{self.max_iterations}")
            
            try:
                response = await self.llm.ainvoke(messages)
            except Exception as e:
                logger.error(f"[SRSaveAgent] LLM 호출 오류: {e}")
                result["message"] = f"LLM 오류: {e}"
                break
            
            messages.append(response)
            
            # 도구 호출 없으면 종료
            if not response.tool_calls:
                result["message"] = response.content or "저장 완료"
                result["success"] = True
                break
            
            # 도구 실행 (한 번에 하나만)
            for idx, tc in enumerate(response.tool_calls):
                if idx > 0:
                    # 한 번에 하나만
                    continue
                
                tool_name = tc["name"]
                tool_args = tc["args"]
                
                logger.info(f"[SRSaveAgent] 도구 호출: {tool_name}({list(tool_args.keys()) if isinstance(tool_args, dict) else tool_args})")
                
                try:
                    # 파싱 도구 실행 (pdf_bytes_b64는 LLM이 넘기지 못하므로 에이전트가 보유한 값으로 주입)
                    parse_tool_names = ["parse_metadata_tool", "parse_index_tool"]
                    if tool_name in parse_tool_names:
                        tool_fn = next((t for t in SR_PARSE_TOOLS if t.name == tool_name), None)
                        if not tool_fn:
                            tool_result = {"error": f"알 수 없는 파싱 도구: {tool_name}"}
                        else:
                            args_with_pdf = dict(tool_args) if isinstance(tool_args, dict) else {}
                            args_with_pdf["pdf_bytes_b64"] = pdf_bytes_b64
                            tool_result = tool_fn.invoke(args_with_pdf)
                    
                    # 저장 도구 실행
                    else:
                        tool_fn = next((t for t in SR_SAVE_TOOLS if t.name == tool_name), None)
                        if not tool_fn:
                            tool_result = {"error": f"알 수 없는 저장 도구: {tool_name}"}
                        else:
                            tool_result = tool_fn.invoke(tool_args)
                            
                            # save_historical_sr_report 반환값은 report_id
                            if tool_name == "save_historical_sr_report" and isinstance(tool_result, str):
                                report_id = tool_result
                                result["report_id"] = report_id
                                logger.info(f"[SRSaveAgent] report_id 획득: {report_id}")
                
                except Exception as e:
                    logger.error(f"[SRSaveAgent] 도구 실행 오류: {e}")
                    tool_result = {"error": str(e)}
                
                # ToolMessage 추가
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc["id"]))
        else:
            result["message"] = "최대 반복 횟수 초과"
        
        return result
