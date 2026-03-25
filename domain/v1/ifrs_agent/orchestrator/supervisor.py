"""Supervisor Agent (감사관)

전체 워크플로우를 제어하는 중앙 오케스트레이터입니다.
감사관(Auditor) 페르소나로 동작하며, 모든 의사결정과 품질 검수를 담당합니다.

하이브리드 접근: Validation Node의 기능을 Supervisor에 통합하여
Star Topology를 완성하면서도 코드 레벨에서 책임 분리를 유지합니다.

모델 통일: Llama 3.3 70B 하나로 감사와 검증을 모두 수행합니다.
정확도 향상을 위해 별도의 validation 모델을 사용하지 않습니다.
"""
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    logger.warning("langchain_groq가 설치되지 않았습니다. pip install langchain-groq 필요")
    ChatGroq = None

from ifrs_agent.orchestrator.state import IFRSAgentState
from backend.core.config.settings import get_settings


# IFRS Rulebook (기준서별 필수 DP 및 검증 규칙)
IFRS_RULEBOOK = {
    "IFRS_S1": {
        "governance": {
            "required_dps": ["S1-GOV-1", "S1-GOV-2", "S1-GOV-3"],
            "validation_rules": [
                "이사회 역할 명시 필수",
                "경영진 책임 범위 정의 필수",
                "보고 주기 명시 필수"
            ]
        },
        "strategy": {
            "required_dps": ["S1-STR-1", "S1-STR-2"],
            "validation_rules": [
                "단기/중기/장기 구분 필수",
                "재무적 영향 정량화 권장"
            ]
        }
    },
    "IFRS_S2": {
        "governance": {
            "required_dps": ["S2-GOV-1", "S2-GOV-2"],
            "validation_rules": [
                "기후 관련 위험과 기회에 대한 지배기구 감독 명시 필수"
            ]
        },
        "strategy": {
            "required_dps": ["S2-10-a", "S2-15-a", "S2-15-b", "S2-15-c"],
            "validation_rules": [
                "물리적/전환 리스크 구분 필수",
                "시나리오 분석 포함 필수",
                "재무제표 연결 명시 필수"
            ]
        },
        "metrics": {
            "required_dps": ["S2-29-a", "S2-29-b", "S2-29-c"],
            "validation_rules": [
                "Scope 1/2/3 배출량 구분 필수",
                "단위 명시 필수 (tCO2e)",
                "기준연도 명시 필수"
            ]
        }
    }
}


SUPERVISOR_SYSTEM_PROMPT = """
당신은 IFRS S1/S2 지속가능성 공시 전문 감사관입니다.

## 역할
1. 사용자의 보고서 작성 요청을 분석합니다.
2. 필요한 Data Point(DP)를 식별합니다.
3. 적절한 노드에 작업을 지시합니다.
4. 결과물의 IFRS 준수 여부를 검증합니다.

## 지표 메타화 규칙
- 모든 지표는 DP 단위로 분해합니다.
- 예: "임직원 수" → 남성/여성/장애인 비율로 세분화
- 중복 지표는 IFRS 기준으로 통합합니다.

## 검증 규칙
- 재무적 연결성(Financial Linkage)이 명시되어야 합니다.
- 정량 데이터는 출처와 기준연도가 있어야 합니다.
- 그린워싱 표현(과장, 모호한 약속)을 감지하면 경고합니다.

## 출력 형식
JSON 형식으로 응답하세요:
{
    "action": "instruct_node | review | approve | reject",
    "target_node": "rag | gen | validation",
    "instruction": "구체적인 지시사항",
    "required_dps": ["DP-001", "DP-002"],
    "validation_rules": ["rule1", "rule2"],
    "rationale": "결정 근거"
}
"""

VALIDATION_SYSTEM_PROMPT = """
당신은 IFRS 지속가능성 공시 검증 전문가입니다.

## 역할
1. 입력 데이터의 범위와 합리성을 검증합니다.
2. 생성된 문단에서 그린워싱 표현을 탐지합니다.
3. IFRS 준수 여부를 확인합니다.

## 그린워싱 패턴
- 과장된 표현: "세계 최고", "100% 친환경", "완벽한"
- 모호한 약속: "노력할 예정" (구체적 계획 없음)
- 근거 없는 친환경 주장: "친환경" (인증/기준 없음)

## 출력 형식
JSON 형식으로 응답하세요:
{
    "greenwashing_risk": 0.0-1.0,
    "greenwashing_issues": [
        {"text": "표현", "risk": "high|medium|low", "description": "설명"}
    ],
    "compliance_score": 0.0-1.0,
    "compliance_issues": ["이슈1", "이슈2"]
}
"""

# 범위 검증 규칙 (Validation Node에서 이동)
VALIDATION_RULES = {
    "percentage": {
        "min": 0,
        "max": 100,
        "error_message": "백분율은 0-100 범위여야 합니다."
    },
    "employee_count": {
        "min": 1,
        "max": 10000000,
        "error_message": "임직원 수가 비정상적입니다."
    },
    "emission_intensity": {
        "min": 0,
        "max": 1000,
        "unit": "tCO2e/억원",
        "error_message": "배출 집약도가 비정상적입니다."
    },
    "gender_ratio": {
        "sum_check": True,
        "expected_sum": 100,
        "error_message": "성별 비율 합계가 100%가 아닙니다."
    }
}

# 그린워싱 패턴 (Validation Node에서 이동)
GREENWASHING_PATTERNS = [
    {
        "pattern": r"(세계 최고|업계 최초|완벽한|100% 친환경)",
        "risk": "high",
        "description": "과장된 표현"
    },
    {
        "pattern": r"(노력할 예정|추진 중|검토 중)(?!.*구체적)",
        "risk": "medium",
        "description": "모호한 약속"
    },
    {
        "pattern": r"(친환경|그린|에코)(?!.*인증|.*기준)",
        "risk": "medium",
        "description": "근거 없는 친환경 주장"
    }
]


class SupervisorAgent:
    """Supervisor Agent (오케스트레이터)
    
    전체 워크플로우를 제어하는 중앙 오케스트레이터입니다.
    노드를 직접 호출하고 제어하는 진정한 오케스트레이터 역할을 수행합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Supervisor 초기화"""
        self.config = config or {}
        self.settings = get_settings()
        
        # LLM 클라이언트 초기화
        if ChatGroq is None:
            raise ImportError("langchain-groq가 설치되지 않았습니다. pip install langchain-groq 필요")
        
        # 메인 LLM (감사 및 검증 통합 - Llama 3.3 70B)
        self.llm = ChatGroq(
            model_name=self.config.get("model", self.settings.supervisor_model),
            groq_api_key=self.config.get("groq_api_key", self.settings.groq_api_key),
            temperature=self.config.get("temperature", self.settings.groq_temperature),
            max_tokens=self.config.get("max_tokens", self.settings.groq_max_tokens)
        )
        
        # 검증도 메인 LLM 사용 (정확도 향상을 위해 통일)
        self.validation_llm = self.llm
        
        # Validation 설정 (Validation Node에서 이동)
        self.validation_rules = VALIDATION_RULES
        self.greenwashing_patterns = GREENWASHING_PATTERNS
        
        self.rulebook = IFRS_RULEBOOK
        self.max_retries = self.config.get("max_retries", self.settings.max_retries)
        
        # MCP Client Manager 초기화 (노드 호출용)
        try:
            from ifrs_agent.service.mcp_client import MCPClientManager
            self.mcp_manager = MCPClientManager()
            self._init_node_servers()
            logger.info("Supervisor: MCP Client Manager 초기화 완료")
        except ImportError:
            logger.warning("MCP Client Manager를 사용할 수 없습니다. pip install mcp 필요")
            self.mcp_manager = None
        
        logger.info(f"SupervisorAgent 초기화 완료 (모델: {self.llm.model_name} - 감사 및 검증 통합)")
    
    def _init_node_servers(self):
        """노드 MCP 서버 등록 (노드 파일에 통합된 MCP 서버 사용)"""
        if not self.mcp_manager:
            return
        
        # RAG Node 서버 등록 (노드 파일에서 직접 실행)
        self.mcp_manager.register_client("rag_node", {
            "name": "rag_node_server",
            "command": "python",
            "args": ["-m", "ifrs_agent.agent.rag_node", "--mcp"],
            "env": {}
        })
        logger.info("Supervisor: RAG Node MCP 서버 등록 완료")
        
        # Gen Node 서버 등록 (노드 파일에서 직접 실행)
        self.mcp_manager.register_client("gen_node", {
            "name": "gen_node_server",
            "command": "python",
            "args": ["-m", "ifrs_agent.agent.gen_node", "--mcp"],
            "env": {}
        })
        logger.info("Supervisor: Gen Node MCP 서버 등록 완료")
        
        # Design Node 서버 등록 (노드 파일에서 직접 실행)
        self.mcp_manager.register_client("design_node", {
            "name": "design_node_server",
            "command": "python",
            "args": ["-m", "ifrs_agent.agent.design_node", "--mcp"],
            "env": {}
        })
        logger.info("Supervisor: Design Node MCP 서버 등록 완료")
    
    async def orchestrate(self, state: IFRSAgentState) -> IFRSAgentState:
        """메인 오케스트레이션 메서드
        
        Supervisor가 노드를 직접 호출하고 전체 워크플로우를 제어합니다.
        LangGraph 노드로 사용됩니다.
        
        Args:
            state: IFRSAgentState
            
        Returns:
            수정된 IFRSAgentState
        """
        logger.info("Supervisor: 오케스트레이션 시작")
        
        try:
            # 1단계: 요청 분석
            state = await self.analyze(state)
            
            # 2단계: 노드 선택 및 실행 (반복)
            iteration_count = 0
            max_iterations = self.max_retries * 3  # 최대 반복 횟수
            
            while iteration_count < max_iterations:
                # 다음 액션 결정
                decision = await self._decide_next_action(state)
                
                if decision["action"] == "complete":
                    logger.info("Supervisor: 모든 작업 완료")
                    break
                
                # 노드 호출
                if decision["action"] == "call_rag_node":
                    state = await self._call_rag_node(state, decision)
                    
                elif decision["action"] == "call_gen_node":
                    state = await self._call_gen_node(state, decision)
                    
                elif decision["action"] == "call_design_node":
                    state = await self._call_design_node(state, decision)
                
                else:
                    logger.warning(f"Supervisor: 알 수 없는 액션: {decision['action']}")
                    break
                
                iteration_count += 1
                
                # 에러 발생 시 중단
                if state.get("status") == "error":
                    logger.error("Supervisor: 에러 발생으로 오케스트레이션 중단")
                    break
            
            # 최종 검증 및 감사
            state = await self.validate_and_audit(state)
            
            # 상태 업데이트
            state["current_node"] = "supervisor"
            state["status"] = "completed" if state.get("status") != "error" else "error"
            
            logger.info(f"Supervisor: 오케스트레이션 완료 (반복 횟수: {iteration_count})")
            
        except Exception as e:
            logger.error(f"Supervisor 오케스트레이션 실패: {e}")
            state["errors"].append(f"오케스트레이션 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def _decide_next_action(self, state: IFRSAgentState) -> Dict[str, Any]:
        """다음 액션 결정 (LLM 기반)
        
        현재 상태를 분석하고 다음에 수행할 액션을 결정합니다.
        
        Args:
            state: 현재 상태
            
        Returns:
            결정 딕셔너리
        """
        required_dps = set(state.get("target_dps", []))
        extracted_dps = set(
            fs.get("dp_id") for fs in state.get("fact_sheets", [])
            if fs.get("dp_id")
        )
        missing_dps = required_dps - extracted_dps
        
        prompt = f"""
        현재 상태를 분석하고 다음 액션을 결정하세요.
        
        ## 현재 상태
        - 상태: {state.get('status')}
        - 현재 노드: {state.get('current_node')}
        - 필요한 DP: {len(required_dps)}개
        - 추출된 DP: {len(extracted_dps)}개
        - 누락된 DP: {len(missing_dps)}개 {list(missing_dps)[:5] if missing_dps else []}
        - 생성된 섹션: {len(state.get('generated_sections', []))}개
        - 반복 횟수: {state.get('iteration_count', 0)}
        
        ## 결정 옵션
        1. call_rag_node: 데이터 추출이 필요하거나 부족한 경우
        2. call_gen_node: 데이터가 충분하여 문단 생성이 필요한 경우
        3. call_design_node: 디자인 추천이 필요한 경우
        4. complete: 모든 작업이 완료된 경우
        
        ## 판단 기준
        - 누락된 DP가 있으면 call_rag_node
        - 모든 DP가 추출되었고 섹션이 없으면 call_gen_node
        - 섹션이 생성되었고 검증이 필요하면 complete
        
        JSON 형식으로 응답:
        {{
            "action": "call_rag_node | call_gen_node | call_design_node | complete",
            "target_node": "rag | gen | design",
            "instruction": "구체적인 지시사항",
            "rationale": "결정 근거"
        }}
        """
        
        messages = [
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            decision = self._parse_decision(response.content)
            
            # State에 결정 기록
            state["audit_log"].append({
                "action": "decide_next_action",
                "decision": decision,
                "timestamp": datetime.now().isoformat(),
                "iteration": state.get("iteration_count", 0)
            })
            
            logger.info(f"Supervisor: 다음 액션 결정 - {decision.get('action')} ({decision.get('rationale', '')[:50]})")
            
            return decision
            
        except Exception as e:
            logger.error(f"Supervisor 액션 결정 실패: {e}")
            # 기본값: 데이터가 부족하면 RAG, 충분하면 Gen
            if missing_dps:
                return {
                    "action": "call_rag_node",
                    "target_node": "rag",
                    "instruction": f"누락된 {len(missing_dps)}개 DP를 추출하세요",
                    "rationale": "누락된 DP가 있어 RAG Node 호출"
                }
            elif not state.get("generated_sections"):
                return {
                    "action": "call_gen_node",
                    "target_node": "gen",
                    "instruction": "추출된 데이터로 문단을 생성하세요",
                    "rationale": "데이터가 충분하여 Gen Node 호출"
                }
            else:
                return {
                    "action": "complete",
                    "target_node": None,
                    "instruction": "모든 작업 완료",
                    "rationale": "모든 작업이 완료됨"
                }
    
    async def _call_rag_node(
        self,
        state: IFRSAgentState,
        decision: Dict[str, Any]
    ) -> IFRSAgentState:
        """RAG Node MCP 호출
        
        Args:
            state: 현재 상태
            decision: 호출 결정 정보
            
        Returns:
            수정된 상태
        """
        if not self.mcp_manager:
            logger.error("Supervisor: MCP Manager가 초기화되지 않았습니다")
            state["errors"].append("MCP Manager가 초기화되지 않았습니다")
            state["status"] = "error"
            return state
        
        logger.info(f"Supervisor: RAG Node MCP 호출 - {decision.get('instruction')}")
        
        # State에 지시사항 저장
        state["instruction"] = decision.get("instruction", "")
        state["current_node"] = "rag_node"
        state["status"] = "retrieving"
        
        # RAG Node MCP 호출
        try:
            result = await self.mcp_manager.call_tool(
                server_name="rag_node",
                tool_name="process",
                params={
                    "state": state,
                    "instruction": decision.get("instruction", "")
                }
            )
            
            if result.get("success", False):
                state = result.get("state", state)
                logger.info(f"Supervisor: RAG Node 호출 완료 - {result.get('fact_sheets_count', 0)}개 팩트 시트")
            else:
                error_msg = result.get("error", "알 수 없는 오류")
                logger.error(f"Supervisor: RAG Node 호출 실패 - {error_msg}")
                state["errors"].append(f"RAG Node 호출 실패: {error_msg}")
                state["status"] = "error"
                return state
            
            # 결과 검토
            state = await self.review(state)
            
        except Exception as e:
            logger.error(f"Supervisor: RAG Node MCP 호출 실패: {e}")
            import traceback
            traceback.print_exc()
            state["errors"].append(f"RAG Node MCP 호출 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def _call_gen_node(
        self,
        state: IFRSAgentState,
        decision: Dict[str, Any]
    ) -> IFRSAgentState:
        """Gen Node MCP 호출
        
        Args:
            state: 현재 상태
            decision: 호출 결정 정보
            
        Returns:
            수정된 상태
        """
        if not self.mcp_manager:
            logger.error("Supervisor: MCP Manager가 초기화되지 않았습니다")
            state["errors"].append("MCP Manager가 초기화되지 않았습니다")
            state["status"] = "error"
            return state
        
        logger.info(f"Supervisor: Gen Node MCP 호출 - {decision.get('instruction')}")
        
        # State에 지시사항 저장
        state["instruction"] = decision.get("instruction", "")
        state["current_node"] = "gen_node"
        state["status"] = "generating"
        
        # Gen Node MCP 호출
        try:
            result = await self.mcp_manager.call_tool(
                server_name="gen_node",
                tool_name="process",
                params={
                    "state": state,
                    "instruction": decision.get("instruction", "")
                }
            )
            
            if result.get("success", False):
                state = result.get("state", state)
                logger.info(f"Supervisor: Gen Node 호출 완료 - {result.get('sections_count', 0)}개 섹션 생성")
            else:
                error_msg = result.get("error", "알 수 없는 오류")
                logger.error(f"Supervisor: Gen Node 호출 실패 - {error_msg}")
                state["errors"].append(f"Gen Node 호출 실패: {error_msg}")
                state["status"] = "error"
            
        except Exception as e:
            logger.error(f"Supervisor: Gen Node MCP 호출 실패: {e}")
            import traceback
            traceback.print_exc()
            state["errors"].append(f"Gen Node MCP 호출 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def _call_design_node(
        self,
        state: IFRSAgentState,
        decision: Dict[str, Any]
    ) -> IFRSAgentState:
        """Design Node MCP 호출
        
        Args:
            state: 현재 상태
            decision: 호출 결정 정보
            
        Returns:
            수정된 상태
        """
        if not self.mcp_manager:
            logger.warning("Supervisor: MCP Manager가 초기화되지 않았습니다 - Design Node 스킵")
            return state
        
        logger.info(f"Supervisor: Design Node MCP 호출 - {decision.get('instruction')}")
        
        # State에 지시사항 저장
        state["instruction"] = decision.get("instruction", "")
        state["current_node"] = "design_node"
        state["status"] = "designing"
        
        # Design Node MCP 호출
        try:
            result = await self.mcp_manager.call_tool(
                server_name="design_node",
                tool_name="process",
                params={
                    "state": state,
                    "instruction": decision.get("instruction", "")
                }
            )
            
            if result.get("success", False):
                state = result.get("state", state)
                logger.info("Supervisor: Design Node 호출 완료")
            else:
                error_msg = result.get("error", "알 수 없는 오류")
                logger.warning(f"Supervisor: Design Node 호출 실패 - {error_msg} (치명적이지 않음)")
                # Design Node 실패는 치명적이지 않으므로 계속 진행
            
        except Exception as e:
            logger.warning(f"Supervisor: Design Node MCP 호출 실패: {e} (치명적이지 않음)")
            # Design Node 실패는 치명적이지 않으므로 계속 진행
        
        return state
    
    async def analyze(self, state: IFRSAgentState) -> IFRSAgentState:
        """1단계: 사용자 요청 분석 및 필요 DP 식별
        
        LangGraph 노드로 사용됩니다.
        """
        logger.info("Supervisor: 요청 분석 시작")
        
        try:
            # 프롬프트 구성
            prompt = self._build_analysis_prompt(
                state["query"],
                state["target_standards"]
            )
            
            # LLM 호출 (비동기)
            messages = [
                SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            decision = self._parse_decision(response.content)
            
            # 상태 업데이트
            state["target_dps"] = decision.get("required_dps", [])
            state["current_node"] = "analyzing"
            state["status"] = "analyzing"
            state["audit_log"].append({
                "action": "analyze",
                "decision": decision,
                "timestamp": datetime.now().isoformat(),
                "rationale": decision.get("rationale", "")
            })
            
            logger.info(f"Supervisor: {len(state['target_dps'])}개 DP 식별 완료")
            
        except Exception as e:
            logger.error(f"Supervisor 분석 중 에러: {e}")
            state["errors"].append(f"Supervisor 분석 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def review(self, state: IFRSAgentState) -> IFRSAgentState:
        """2단계: RAG 추출 결과 검토
        
        LangGraph 노드로 사용됩니다.
        """
        logger.info("Supervisor: 추출 결과 검토 시작")
        
        try:
            required_dps = set(state["target_dps"])
            extracted_dps = set(fs.get("dp_id") for fs in state["fact_sheets"] if fs.get("dp_id"))
            missing_dps = required_dps - extracted_dps
            
            # 상태 업데이트
            state["current_node"] = "reviewing"
            state["status"] = "reviewing"
            state["audit_log"].append({
                "action": "review",
                "required_dps": list(required_dps),
                "extracted_dps": list(extracted_dps),
                "missing_dps": list(missing_dps),
                "timestamp": datetime.now().isoformat()
            })
            
            if missing_dps:
                logger.warning(f"Supervisor: {len(missing_dps)}개 DP 누락 - {list(missing_dps)[:5]}")
            else:
                logger.info("Supervisor: 모든 필수 DP 추출 완료")
            
        except Exception as e:
            logger.error(f"Supervisor 검토 중 에러: {e}")
            state["errors"].append(f"Supervisor 검토 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def validate_and_audit(self, state: IFRSAgentState) -> IFRSAgentState:
        """검증 + 감사 통합 메서드 (하이브리드 접근)
        
        워크플로우 레벨에서는 하나의 노드이지만,
        내부적으로는 검증과 감사를 분리하여 처리합니다.
        
        LangGraph 노드로 사용됩니다.
        """
        logger.info("Supervisor: 검증 및 감사 시작")
        
        try:
            # 1단계: 검증 수행 (Validation 로직)
            validation_result = await self._perform_validation(state)
            state["validation_results"].append(validation_result)
            
            # 2단계: 감사 수행 (Audit 로직)
            audit_result = self._perform_audit(state, validation_result)
            state["audit_log"].append(audit_result)
            
            # 상태 업데이트
            state["current_node"] = "validating_and_auditing"
            state["status"] = audit_result.get("status", "auditing")
            
            logger.info(
                f"Supervisor: 검증 및 감사 완료 - "
                f"그린워싱 위험도: {validation_result.get('greenwashing_risk', 0.0):.2f}, "
                f"IFRS 준수도: {validation_result.get('compliance_score', 1.0):.2f}, "
                f"결정: {audit_result.get('action', 'unknown')}"
            )
            
        except Exception as e:
            logger.error(f"Supervisor 검증 및 감사 중 에러: {e}")
            state["errors"].append(f"Supervisor 검증 및 감사 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    def audit(self, state: IFRSAgentState) -> IFRSAgentState:
        """3단계: 생성 결과 최종 감사 (하위 호환성 유지)
        
        기존 코드와의 호환성을 위해 유지하지만,
        새로운 코드는 validate_and_audit을 사용해야 합니다.
        
        LangGraph 노드로 사용됩니다.
        """
        logger.info("Supervisor: 최종 감사 시작 (레거시 메서드)")
        
        try:
            # 검증 결과 확인
            if not state["validation_results"]:
                logger.warning("Supervisor: 검증 결과가 없습니다")
                state["audit_log"].append({
                    "action": "audit",
                    "status": "no_validation",
                    "timestamp": datetime.now().isoformat()
                })
                state["current_node"] = "auditing"
                state["status"] = "auditing"
                return state
            
            latest_validation = state["validation_results"][-1]
            
            # 그린워싱 체크
            greenwashing_risk = latest_validation.get("greenwashing_risk", 0.0)
            if greenwashing_risk > 0.7:
                logger.error(f"Supervisor: 그린워싱 위험 감지 (위험도: {greenwashing_risk})")
                state["audit_log"].append({
                    "action": "reject",
                    "reason": "greenwashing_risk",
                    "risk_score": greenwashing_risk,
                    "issues": latest_validation.get("greenwashing_issues", []),
                    "timestamp": datetime.now().isoformat()
                })
                state["status"] = "rejected"
                return state
            
            # IFRS 준수 체크
            compliance_score = latest_validation.get("compliance_score", 1.0)
            if compliance_score < 0.8:
                # 누락된 DP 식별
                missing_dps = self._identify_missing_dps(
                    state["generated_sections"],
                    state["target_dps"]
                )
                
                # 재무 연결성 부족 확인
                missing_financial_linkage = self._check_financial_linkage(
                    state["generated_sections"]
                )
                
                logger.warning(
                    f"Supervisor: IFRS 준수 점수 미달 ({compliance_score:.2f}) - "
                    f"누락 DP: {len(missing_dps)}, 재무 연결성 부족: {len(missing_financial_linkage)}"
                )
                
                state["audit_log"].append({
                    "action": "request_revision",
                    "compliance_score": compliance_score,
                    "missing_dps": missing_dps,
                    "missing_financial_linkage": missing_financial_linkage,
                    "timestamp": datetime.now().isoformat()
                })
            else:
                logger.info(f"Supervisor: IFRS 준수 점수 통과 ({compliance_score:.2f})")
                state["audit_log"].append({
                    "action": "approve",
                    "compliance_score": compliance_score,
                    "timestamp": datetime.now().isoformat()
                })
            
            state["current_node"] = "auditing"
            state["status"] = "auditing"
            
        except Exception as e:
            logger.error(f"Supervisor 감사 중 에러: {e}")
            state["errors"].append(f"Supervisor 감사 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    def _build_analysis_prompt(self, query: str, target_standards: List[str]) -> str:
        """분석 프롬프트 구성"""
        # Rulebook에서 기준서별 필수 DP 추출
        required_dps = []
        validation_rules = []
        
        for standard in target_standards:
            if standard in self.rulebook:
                for section_name, section_config in self.rulebook[standard].items():
                    required_dps.extend(section_config.get("required_dps", []))
                    validation_rules.extend(section_config.get("validation_rules", []))
        
        prompt = f"""
사용자 요청을 분석하고 필요한 Data Point(DP)를 식별하세요.

## 사용자 요청
{query}

## 대상 기준서
{', '.join(target_standards)}

## 기준서별 필수 DP (참고)
{json.dumps(required_dps, ensure_ascii=False, indent=2) if required_dps else "없음"}

## 검증 규칙 (참고)
{chr(10).join(f"- {rule}" for rule in validation_rules) if validation_rules else "없음"}

## 분석 요구사항
1. 사용자 요청에서 언급된 ESG 주제를 식별하세요.
2. 해당 주제와 관련된 IFRS DP를 식별하세요.
3. 기준서별 필수 DP를 확인하고 포함하세요.
4. DP는 가능한 한 세분화하세요 (예: "임직원 수" → 남성/여성/장애인 비율)

## 출력 형식
JSON 형식으로 응답하세요:
{{
    "action": "instruct_node",
    "target_node": "rag",
    "instruction": "RAG Node에 다음 DP를 검색하도록 지시",
    "required_dps": ["S2-15-a", "S2-15-b", ...],
    "validation_rules": ["규칙1", "규칙2", ...],
    "rationale": "분석 근거"
}}
"""
        return prompt
    
    def _parse_decision(self, response_text: str) -> Dict[str, Any]:
        """LLM 응답을 파싱하여 결정 추출"""
        try:
            # JSON 추출 (코드 블록 제거)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            decision = json.loads(response_text)
            return decision
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}, 응답: {response_text[:200]}")
            # 기본값 반환
            return {
                "action": "instruct_node",
                "target_node": "rag",
                "instruction": "사용자 요청에 따라 관련 DP를 검색하세요",
                "required_dps": [],
                "validation_rules": [],
                "rationale": "JSON 파싱 실패로 기본값 사용"
            }
    
    def _identify_missing_dps(
        self,
        generated_sections: List[Dict[str, Any]],
        target_dps: List[str]
    ) -> List[str]:
        """생성된 섹션에서 누락된 DP 식별"""
        referenced_dps = set()
        for section in generated_sections:
            referenced_dps.update(section.get("referenced_dps", []))
        
        return list(set(target_dps) - referenced_dps)
    
    def _check_financial_linkage(
        self,
        generated_sections: List[Dict[str, Any]]
    ) -> List[str]:
        """재무 연결성 부족 섹션 식별"""
        missing = []
        for section in generated_sections:
            financial_linkage = section.get("financial_linkage", "")
            if not financial_linkage or len(str(financial_linkage)) < 50:
                missing.append(section.get("section_id", "unknown"))
        return missing
    
    def _get_dp_description(self, dp_id: str) -> str:
        """DP 설명 조회 (온톨로지에서)
        
        TODO: 실제 구현 시 온톨로지 저장소에서 조회
        """
        # 임시 구현
        return f"Data Point {dp_id}"
    
    # ============================================
    # 내부 메서드: 검증 로직 (Validation Node에서 이동)
    # ============================================
    
    async def _perform_validation(self, state: IFRSAgentState) -> Dict[str, Any]:
        """검증 수행 (Validation Node의 process 메서드 로직)
        
        Validation Node의 기능을 그대로 Supervisor로 이동
        책임은 분리되어 있지만, 같은 클래스 내부에 존재
        """
        logger.info("Supervisor: 검증 단계 시작")
        
        validation_results = []
        
        # 1. 입력 데이터 검증
        data_validation = self._validate_input_data(
            state.get("fact_sheets", [])
        )
        
        # 2. 생성 결과 검증
        for section in state.get("generated_sections", []):
            section_validation = await self._validate_section(section)
            validation_results.append(section_validation)
        
        # 3. 그린워싱 검사
        greenwashing_check = await self._check_greenwashing(
            state.get("generated_sections", [])
        )
        
        # 4. IFRS 준수 검사
        compliance_check = self._check_ifrs_compliance(
            state.get("generated_sections", []),
            state.get("target_standards", [])
        )
        
        # 검증 결과 반환
        return {
            "data_validation": data_validation,
            "section_validations": validation_results,
            "greenwashing_risk": greenwashing_check["risk_score"],
            "greenwashing_issues": greenwashing_check["issues"],
            "compliance_score": compliance_check["score"],
            "compliance_issues": compliance_check["issues"],
            "is_valid": (
                data_validation["is_valid"] and
                greenwashing_check["risk_score"] < 0.7 and
                compliance_check["score"] >= 0.8
            )
        }
    
    def _validate_input_data(
        self,
        fact_sheets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """입력 데이터 검증 (Validation Node에서 이동)"""
        errors = []
        warnings = []
        
        for fact_sheet in fact_sheets:
            dp_id = fact_sheet.get("dp_id", "")
            values = fact_sheet.get("values", {})
            
            dp_type = self._get_dp_type(dp_id)
            rule = self.validation_rules.get(dp_type)
            
            if not rule:
                continue
            
            # 범위 검사
            if "min" in rule or "max" in rule:
                for year, value in values.items():
                    if not isinstance(value, (int, float)):
                        continue
                    
                    if "min" in rule and value < rule["min"]:
                        errors.append(
                            f"{dp_id} {year}년 값({value})이 최소값({rule['min']}) 미만입니다."
                        )
                    if "max" in rule and value > rule["max"]:
                        errors.append(
                            f"{dp_id} {year}년 값({value})이 최대값({rule['max']}) 초과입니다."
                        )
            
            # 합계 검사
            if rule.get("sum_check"):
                total = sum(values.values())
                expected = rule.get("expected_sum", 100)
                if abs(total - expected) > 0.01:
                    errors.append(
                        f"{dp_id} 합계({total})가 예상값({expected})과 다릅니다."
                    )
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def _validate_section(
        self,
        section: Dict[str, Any]
    ) -> Dict[str, Any]:
        """섹션별 검증 (Validation Node에서 이동)"""
        errors = []
        warnings = []
        
        # 재무 연결성 확인
        if not section.get("financial_linkage") or len(str(section.get("financial_linkage", ""))) < 50:
            warnings.append("재무 연결성 설명이 부족합니다.")
        
        # 출처 확인
        if not section.get("sources"):
            warnings.append("참조 출처가 없습니다.")
        
        return {
            "section_id": section.get("section_id", "unknown"),
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def _check_greenwashing(
        self,
        generated_sections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """그린워싱 탐지 (Validation Node에서 이동)"""
        issues = []
        all_content = " ".join([
            s.get("content", "") for s in generated_sections
        ])
        
        # 1. 패턴 기반 탐지
        for pattern_config in self.greenwashing_patterns:
            matches = re.finditer(
                pattern_config["pattern"],
                all_content,
                re.IGNORECASE
            )
            for match in matches:
                issues.append({
                    "text": match.group(0),
                    "risk": pattern_config["risk"],
                    "description": pattern_config["description"]
                })
        
        # 2. LLM 기반 심층 분석 (비동기)
        if all_content:
            try:
                llm_analysis = await self._llm_analyze_greenwashing(all_content)
                issues.extend(llm_analysis.get("issues", []))
            except Exception as e:
                logger.warning(f"LLM 그린워싱 분석 실패: {e}")
        
        # 3. 위험 점수 계산
        risk_score = self._calculate_risk_score(issues)
        
        return {
            "risk_score": risk_score,
            "issues": issues,
            "recommendation": self._get_recommendation(issues)
        }
    
    async def _llm_analyze_greenwashing(
        self,
        content: str
    ) -> Dict[str, Any]:
        """LLM 기반 그린워싱 분석 (Validation Node에서 이동)"""
        prompt = f"""
다음 텍스트에서 그린워싱 표현을 찾아주세요.

## 텍스트
{content[:2000]}  # 최대 2000자

## 검색 항목
1. 과장된 표현 (예: "세계 최고", "100% 친환경")
2. 모호한 약속 (예: "노력할 예정" - 구체적 계획 없음)
3. 근거 없는 친환경 주장 (인증/기준 없이 "친환경" 사용)

## 출력 형식
JSON 형식으로 응답하세요:
{{
    "issues": [
        {{
            "text": "발견된 표현",
            "risk": "high|medium|low",
            "description": "문제 설명"
        }}
    ]
}}
"""
        
        try:
            messages = [
                SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            
            response = await self.validation_llm.ainvoke(messages)
            result = self._parse_llm_response(response.content)
            return result
            
        except Exception as e:
            logger.error(f"LLM 그린워싱 분석 실패: {e}")
            return {"issues": []}
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """LLM 응답 파싱 (Validation Node에서 이동)"""
        try:
            # JSON 추출
            if "```json" in response_text:
                json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            elif "```" in response_text:
                json_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            
            result = json.loads(response_text)
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {"issues": []}
    
    def _calculate_risk_score(self, issues: List[Dict]) -> float:
        """위험 점수 계산 (Validation Node에서 이동)"""
        if not issues:
            return 0.0
        
        risk_weights = {
            "high": 0.5,
            "medium": 0.3,
            "low": 0.1
        }
        
        total_score = sum(
            risk_weights.get(issue.get("risk", "low"), 0.1)
            for issue in issues
        )
        
        # 정규화 (0-1)
        return min(total_score / len(issues), 1.0)
    
    def _get_recommendation(self, issues: List[Dict]) -> str:
        """추천 사항 생성 (Validation Node에서 이동)"""
        if not issues:
            return "그린워싱 위험이 없습니다."
        
        high_risk_count = sum(1 for i in issues if i.get("risk") == "high")
        
        if high_risk_count > 0:
            return f"고위험 그린워싱 표현 {high_risk_count}개 발견. 즉시 수정이 필요합니다."
        else:
            return f"중/저위험 표현 {len(issues)}개 발견. 검토 후 수정 권장."
    
    def _check_ifrs_compliance(
        self,
        generated_sections: List[Dict[str, Any]],
        target_standards: List[str]
    ) -> Dict[str, Any]:
        """IFRS 준수 검사 (Validation Node에서 이동)"""
        issues = []
        score = 1.0
        
        # 기본 검증 항목
        for section in generated_sections:
            # 재무 연결성 확인
            if not section.get("financial_linkage"):
                issues.append(f"{section.get('section_id', 'unknown')}: 재무 연결성 부족")
                score -= 0.2
            
            # 출처 확인
            if not section.get("sources"):
                issues.append(f"{section.get('section_id', 'unknown')}: 참조 출처 부족")
                score -= 0.1
            
            # 내용 길이 확인
            content = section.get("content", "")
            if len(content) < 100:
                issues.append(f"{section.get('section_id', 'unknown')}: 내용이 너무 짧음")
                score -= 0.1
        
        # 점수 정규화 (0-1)
        score = max(0.0, min(1.0, score))
        
        return {
            "score": score,
            "issues": issues
        }
    
    def _get_dp_type(self, dp_id: str) -> str:
        """DP 타입 추정 (Validation Node에서 이동)"""
        if "ratio" in dp_id.lower() or "percent" in dp_id.lower():
            return "percentage"
        elif "employee" in dp_id.lower() or "staff" in dp_id.lower():
            return "employee_count"
        elif "emission" in dp_id.lower() or "ghg" in dp_id.lower():
            return "emission_intensity"
        elif "gender" in dp_id.lower():
            return "gender_ratio"
        return "unknown"
    
    # ============================================
    # 내부 메서드: 감사 로직 (기존 audit 메서드 분리)
    # ============================================
    
    def _perform_audit(
        self,
        state: IFRSAgentState,
        validation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """감사 수행 (기존 audit 메서드 로직)
        
        검증 결과를 바탕으로 최종 결정을 내림
        """
        logger.info("Supervisor: 감사 단계 시작")
        
        # 그린워싱 체크
        greenwashing_risk = validation_result.get("greenwashing_risk", 0.0)
        if greenwashing_risk > 0.7:
            logger.error(f"Supervisor: 그린워싱 위험 감지 (위험도: {greenwashing_risk})")
            return {
                "action": "reject",
                "reason": "greenwashing_risk",
                "risk_score": greenwashing_risk,
                "issues": validation_result.get("greenwashing_issues", []),
                "status": "rejected",
                "timestamp": datetime.now().isoformat()
            }
        
        # IFRS 준수 체크
        compliance_score = validation_result.get("compliance_score", 1.0)
        if compliance_score < 0.8:
            missing_dps = self._identify_missing_dps(
                state["generated_sections"],
                state["target_dps"]
            )
            
            missing_financial_linkage = self._check_financial_linkage(
                state["generated_sections"]
            )
            
            logger.warning(
                f"Supervisor: IFRS 준수 점수 미달 ({compliance_score:.2f}) - "
                f"누락 DP: {len(missing_dps)}, 재무 연결성 부족: {len(missing_financial_linkage)}"
            )
            
            return {
                "action": "request_revision",
                "compliance_score": compliance_score,
                "missing_dps": missing_dps,
                "missing_financial_linkage": missing_financial_linkage,
                "status": "needs_revision",
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.info(f"Supervisor: IFRS 준수 점수 통과 ({compliance_score:.2f})")
            return {
                "action": "approve",
                "compliance_score": compliance_score,
                "status": "approved",
                "timestamp": datetime.now().isoformat()
            }

