"""IFRS Agent Workflow (LangGraph)

LangGraph 기반 워크플로우 정의 및 실행 관리
"""
from typing import Dict, List, Any, Optional
from loguru import logger

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    logger.error("langgraph가 설치되지 않았습니다. pip install langgraph 필요")
    StateGraph = None
    END = None

# SqliteSaver는 선택적 기능이므로 별도로 import
SqliteSaver = None
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    logger.warning("SqliteSaver를 사용할 수 없습니다. 체크포인팅 기능이 비활성화됩니다.")
    SqliteSaver = None

from ifrs_agent.orchestrator.state import IFRSAgentState
from ifrs_agent.orchestrator.supervisor import SupervisorAgent
from backend.core.config.settings import get_settings
# 노드는 MCP 서버로 실행되므로 import 불필요


class IFRSAgentWorkflow:
    """IFRS 에이전트 워크플로우
    
    LangGraph를 사용하여 노드들을 연결하고 실행 흐름을 관리합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """워크플로우 초기화"""
        if StateGraph is None:
            raise ImportError("langgraph가 설치되지 않았습니다. pip install langgraph 필요")
        
        self.config = config or {}
        self.settings = get_settings()
        
        # 노드 인스턴스 생성
        self.supervisor = SupervisorAgent(
            self.config.get("supervisor", {})
        )
        
        # 노드 인스턴스는 더 이상 필요하지 않음
        # Supervisor가 MCP를 통해 노드를 호출하므로
        # 노드 서버는 별도 프로세스로 실행됨
        
        logger.info("노드는 MCP 서버로 실행됩니다 (별도 프로세스)")
        
        # 그래프 빌드
        self.graph = self._build_graph()
        
        logger.info("IFRSAgentWorkflow 초기화 완료")
    
    def _build_graph(self) -> Any:
        """워크플로우 그래프 구성
        
        Supervisor가 노드를 직접 호출하는 구조로 단순화되었습니다.
        LangGraph는 State 관리와 체크포인팅만 담당합니다.
        """
        workflow = StateGraph(IFRSAgentState)
        
        # Supervisor의 orchestrate 메서드를 메인 노드로 설정
        # Supervisor가 내부적으로 모든 노드를 직접 호출하고 제어합니다
        workflow.add_node(
            "supervisor_orchestrate",
            self._wrap_async(self.supervisor.orchestrate)
        )
        
        # 엣지 설정: Supervisor가 모든 것을 제어하므로 단순한 흐름
        workflow.set_entry_point("supervisor_orchestrate")
        workflow.add_edge("supervisor_orchestrate", END)
        
        # 체크포인트 설정 (선택적)
        checkpointer = None
        if self.config.get("enable_checkpointing", False) and SqliteSaver is not None:
            try:
                checkpointer = SqliteSaver.from_conn_string(":memory:")
            except Exception as e:
                logger.warning(f"체크포인터 초기화 실패: {e}")
                checkpointer = None
        
        if checkpointer:
            return workflow.compile(checkpointer=checkpointer)
        else:
            return workflow.compile()
    
    # 참고: _check_data_sufficiency, _check_quality 메서드는 제거됨
    # Supervisor의 orchestrate 메서드가 내부적으로 모든 결정을 수행합니다.
    
    
    def _wrap_async(self, async_func):
        """비동기 함수를 동기 함수로 래핑 (LangGraph 호환)"""
        import asyncio
        
        def sync_wrapper(state: IFRSAgentState) -> IFRSAgentState:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(async_func(state))
        
        return sync_wrapper
    
    def set_nodes(
        self,
        rag_node: Optional[Any] = None,
        gen_node: Optional[Any] = None
    ):
        """노드 인스턴스 설정 (나중에 노드 구현 후 호출)
        
        Note: Validation Node는 Supervisor에 통합되었으므로 제거됨
        """
        if rag_node:
            self.rag_node = rag_node
        if gen_node:
            self.gen_node = gen_node
        
        # 그래프 재빌드
        self.graph = self._build_graph()
        logger.info("노드 설정 완료 - 그래프 재빌드됨")
    
    async def run(
        self,
        query: str,
        documents: Optional[List[str]] = None,
        target_standards: Optional[List[str]] = None,
        fiscal_year: Optional[int] = None,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """워크플로우 실행
        
        Args:
            query: 사용자 쿼리
            documents: 업로드된 문서 경로 목록
            target_standards: 대상 기준서 목록
            fiscal_year: 회계연도
            company_id: 기업 식별자
        
        Returns:
            최종 상태 딕셔너리
        """
        logger.info(f"워크플로우 실행 시작: {query[:50]}...")
        
        # 초기 상태 생성
        initial_state: IFRSAgentState = {
            "query": query,
            "documents": documents or [],
            "target_standards": target_standards or ["IFRS_S2"],
            "fiscal_year": fiscal_year or 2024,
            "company_id": company_id or "unknown",
            "current_node": "entry",
            "iteration_count": 0,
            "status": "initialized",
            "target_dps": [],
            "fact_sheets": [],
            "yearly_data": {},
            "generated_sections": [],
            "validation_results": [],
            "corporate_identity": {},
            "reference_sources": [],
            "audit_log": [],
            "errors": [],
            "instruction": None,
            "mcp_tool_results": [],
            "external_data_sources": []
        }
        
        try:
            # 워크플로우 실행
            result = await self.graph.ainvoke(
                initial_state,
                {"configurable": {"thread_id": str(company_id or "default")}}
            )
            
            logger.info(f"워크플로우 실행 완료: 상태={result.get('status')}")
            return result
            
        except Exception as e:
            logger.error(f"워크플로우 실행 중 에러: {e}")
            initial_state["errors"].append(str(e))
            initial_state["status"] = "error"
            return initial_state
    
    def run_sync(
        self,
        query: str,
        documents: Optional[List[str]] = None,
        target_standards: Optional[List[str]] = None,
        fiscal_year: Optional[int] = None,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """워크플로우 동기 실행 (테스트용)"""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.run(query, documents, target_standards, fiscal_year, company_id)
        )

