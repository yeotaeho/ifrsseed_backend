"""RAG Node (검색 및 추출)

데이터 추출가 페르소나로 동작하며, 외부/내부 데이터를 검색하고 DP 단위로 구조화합니다.
"""
import os
import tempfile
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger
from pathlib import Path

try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    logger.warning("langchain-groq가 설치되지 않았습니다.")
    ChatGroq = None

# LangChain Tools 제거됨 - FastMCP로 대체
# MCP Client import
try:
    from ifrs_agent.service.mcp_client import MCPClientManager
    MCP_AVAILABLE = True
except ImportError:
    logger.warning("MCP Client를 사용할 수 없습니다. pip install mcp 필요")
    MCPClientManager = None
    MCP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests가 설치되지 않았습니다. DART API 크롤링이 작동하지 않습니다.")

from ifrs_agent.agent.base import BaseNode
from ifrs_agent.orchestrator.state import IFRSAgentState
from backend.core.config.settings import get_settings
from ifrs_agent.repository.vector_store_repository import VectorStoreRepository
from ifrs_agent.service.embedding_service import EmbeddingService
from ifrs_agent.service.document_service import DocumentService
from ifrs_agent.database.base import get_session
from ifrs_agent.model.models import DataPoint


RAG_SYSTEM_PROMPT = """
당신은 IFRS 지속가능성 공시 데이터 추출 전문가입니다.

## 역할
1. 사용자 쿼리를 검색 쿼리로 최적화합니다.
2. 벡터 DB에서 관련 문서를 검색합니다.
3. 검색 결과에서 Data Point(DP) 값을 추출합니다.
4. 구조화된 팩트 시트를 생성합니다.

## 출력 형식
JSON 형식으로 응답하세요:
{
    "optimized_queries": ["쿼리1", "쿼리2"],
    "extracted_dps": [
        {
            "dp_id": "S2-15-a",
            "values": {"2022": 100, "2023": 95, "2024": 90},
            "unit": "tCO2e",
            "source": "DART",
            "confidence": 0.9
        }
    ]
}
"""


class RAGNode(BaseNode):
    """RAG Node (검색 및 추출)
    
    하이브리드 검색, 크롤링, 멀티모달 처리를 담당합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """RAG Node 초기화"""
        super().__init__("rag_node", config)
        self.settings = get_settings()
        
        # LLM 클라이언트 초기화
        if ChatGroq is None:
            raise ImportError("langchain-groq가 설치되지 않았습니다. pip install langchain-groq 필요")
        
        self.llm = ChatGroq(
            model_name=self.config.get("model", self.settings.rag_model),
            groq_api_key=self.config.get("groq_api_key", self.settings.groq_api_key),
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 4096)
        )
        
        # DART API 설정
        self.dart_api_key = self.settings.dart_api_key
        self.dart_base_url = "https://opendart.fss.or.kr/api"
        
        # 벡터 검색 컴포넌트 초기화 (지연 로딩)
        self._embedding_service = None
        self._vector_repository = None
        self._document_service = None
        
        # FastMCP Client 초기화
        if MCP_AVAILABLE and MCPClientManager:
            self.mcp_manager = MCPClientManager()
            self._init_mcp_servers()
            # MCP Tools 바인딩은 비동기로 처리 (지연 로딩)
            self._mcp_tools_bound = False
        else:
            self.mcp_manager = None
            self._mcp_tools_bound = False
            logger.warning("⚠️ MCP를 사용할 수 없습니다. 외부 데이터 수집이 제한됩니다.")
        
        # TODO: 실제 구현 시 추가할 컴포넌트
        # self.table_extractor = TableExtractor()
        # self.image_processor = ImageProcessor()
        
        logger.info(f"RAG Node 초기화 완료 (모델: {self.llm.model_name})")
    
    async def process(self, state: IFRSAgentState) -> IFRSAgentState:
        """RAG 처리 메인 로직"""
        logger.info("RAG Node: 데이터 추출 시작")
        
        try:
            # 1. 쿼리 최적화
            optimized_queries = await self._optimize_query(
                state["query"],
                state["target_dps"]
            )
            
            # 2. 하이브리드 검색 (벡터 DB 검색)
            # 전략: company_id/fiscal_year가 있으면 먼저 해당 데이터 검색,
            #       결과가 없거나 부족하면 기준서 문서 검색
            search_results = []
            
            # 2-1. 회사별 데이터 검색 (있는 경우)
            company_results = []
            if state.get("company_id") and state.get("fiscal_year"):
                company_filters = {
                    "company_id": state["company_id"],
                    "fiscal_year": state["fiscal_year"]
                }
                if state.get("standard"):
                    company_filters["standard"] = state["standard"]
                
                company_results = await self._hybrid_search(
                    optimized_queries,
                    filters=company_filters,
                    top_k=5
                )
                search_results.extend(company_results)
                logger.info(f"✅ 회사별 데이터 검색: {len(company_results)}개 결과")
            
            # 2-2. 기준서 문서 검색 (항상 수행, 기준서는 company_id/fiscal_year 없음)
            standard_filters = {}
            if state.get("standard"):
                standard_filters["standard"] = state["standard"]
            standard_filters["document_type"] = "standard"  # 기준서만
            
            standard_results = await self._hybrid_search(
                optimized_queries,
                filters=standard_filters,
                top_k=5
            )
            search_results.extend(standard_results)
            logger.info(f"✅ 기준서 문서 검색: {len(standard_results)}개 결과")
            
            # 3. 외부 데이터 수집 (LLM이 자동으로 Tools 선택)
            # LLM이 필요에 따라 웹 검색, DART API, 뉴스 검색 등을 자동으로 선택
            if state.get("company_id") and state.get("fiscal_year"):
                # 회사별 벡터 DB 결과가 없거나 부족한 경우
                company_data_count = len([r for r in search_results 
                                         if r.get("metadata", {}).get("company_id") == state["company_id"]])
                
                if company_data_count == 0 or self._needs_external_data(search_results, state["target_dps"]):
                    logger.info(f"📥 회사별 데이터가 부족하여 외부 데이터 수집 시작 (벡터 DB: {company_data_count}개)")
                    
                    # LLM이 Tools를 사용하여 외부 데이터 수집
                    external_data = await self._collect_external_data_with_llm(
                        state["company_id"],
                        state["fiscal_year"],
                        state["query"],
                        state["target_dps"]
                    )
                    
                    if external_data:
                        search_results.extend(external_data)
                        logger.info(f"✅ 외부 데이터 수집 완료: {len(external_data)}개 문서")
                    
                    # 기존 DART API 크롤링도 유지 (LLM이 선택하지 않은 경우 대비)
                    if not external_data:
                        logger.info(f"📥 DART API로 직접 크롤링 시작")
                        crawled_data = await self._crawl_external_sources(
                            state["company_id"],
                            state["fiscal_year"]
                        )
                        if crawled_data:
                            search_results.extend(crawled_data)
                            logger.info(f"✅ DART API 크롤링 완료: {len(crawled_data)}개 문서")
            
            # 4. 멀티모달 콘텐츠 추출 (표·이미지) - 현재는 더미
            if state.get("documents"):
                multimodal_content = await self._extract_multimodal_content(
                    state["documents"],
                    state["target_dps"]
                )
                search_results.extend(multimodal_content)
            
            # 5. DP 추출 및 팩트 시트 생성
            fact_sheets = await self._extract_dps(
                search_results,
                state["target_dps"]
            )
            
            # 6. 상태 업데이트
            state["fact_sheets"] = fact_sheets
            state["yearly_data"] = self._organize_by_year(fact_sheets)
            state["current_node"] = "retrieving"
            state["status"] = "retrieving"
            
            # MCP Tool 결과를 State에 명시적으로 저장 (있는 경우)
            if "mcp_tool_results" not in state:
                state["mcp_tool_results"] = []
            if "external_data_sources" not in state:
                state["external_data_sources"] = []
            
            logger.info(f"RAG Node: {len(fact_sheets)}개 팩트 시트 생성 완료")
            
        except Exception as e:
            logger.error(f"RAG Node 처리 중 에러: {e}")
            state["errors"].append(f"RAG Node 실패: {str(e)}")
            state["status"] = "error"
        
        return state
    
    async def _optimize_query(
        self,
        query: str,
        target_dps: List[str]
    ) -> List[str]:
        """쿼리 최적화"""
        logger.debug(f"쿼리 최적화: {query}")
        
        # TODO: LLM을 사용한 쿼리 최적화
        # 현재는 간단히 분할
        optimized = [query]
        
        # DP별 쿼리 추가
        if target_dps:
            for dp in target_dps[:3]:  # 최대 3개만
                optimized.append(f"{query} {dp}")
        
        return optimized
    
    def _get_embedding_service(self) -> EmbeddingService:
        """임베딩 서비스 가져오기 (지연 로딩)"""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service
    
    def _get_vector_repository(self) -> VectorStoreRepository:
        """벡터 저장소 Repository 가져오기 (지연 로딩)"""
        if self._vector_repository is None:
            self._vector_repository = VectorStoreRepository()
        return self._vector_repository
    
    def _get_document_service(self) -> DocumentService:
        """문서 서비스 가져오기 (지연 로딩)"""
        if self._document_service is None:
            self._document_service = DocumentService()
        return self._document_service
    
    def _init_mcp_servers(self):
        """MCP 서버 등록"""
        if not self.mcp_manager:
            return
        
        mcp_configs = self.config.get("mcp_servers", {})
        
        # DART API Tool Server
        if mcp_configs.get("dart_enabled", True):
            self.mcp_manager.register_client("dart", {
                "name": "dart_tool_server",
                "command": "python",
                "args": ["-m", "tools.dart_server"],
                "env": {
                    "DART_API_KEY": self.settings.dart_api_key or ""
                }
            })
            logger.info("✅ DART MCP 서버 등록 완료")
        
        # Web Search Tool Server
        if mcp_configs.get("web_search_enabled", True):
            self.mcp_manager.register_client("web_search", {
                "name": "web_search_tool_server",
                "command": "python",
                "args": ["-m", "tools.web_search_server"],
                "env": {
                    "TAVILY_API_KEY": self.settings.tavily_api_key or ""
                }
            })
            logger.info("✅ Web Search MCP 서버 등록 완료")
        
        # News Search Tool Server
        if mcp_configs.get("news_enabled", True):
            self.mcp_manager.register_client("news", {
                "name": "news_tool_server",
                "command": "python",
                "args": ["-m", "tools.news_server"],
                "env": {}
            })
            logger.info("✅ News MCP 서버 등록 완료")
    
    async def _bind_mcp_tools(self):
        """MCP Tools를 LLM에 바인딩"""
        if not self.mcp_manager or self._mcp_tools_bound:
            return
        
        try:
            # 모든 MCP 서버에서 도구 목록 조회
            all_tools = []
            
            for server_name in ["dart", "web_search", "news"]:
                try:
                    client = await self.mcp_manager.get_client(server_name)
                    tools = await client.list_tools()
                    # MCP Tool을 LangChain Tool 형식으로 변환
                    langchain_tools = self._convert_mcp_to_langchain_tools(tools, server_name)
                    all_tools.extend(langchain_tools)
                except Exception as e:
                    logger.warning(f"MCP 서버 '{server_name}' 연결 실패: {e}")
            
            if all_tools and hasattr(self.llm, 'bind_tools'):
                self.llm = self.llm.bind_tools(all_tools)
                self._mcp_tools_bound = True
                logger.info(f"✅ MCP Tools 바인딩 완료: {len(all_tools)}개 도구")
        except Exception as e:
            logger.error(f"MCP Tools 바인딩 실패: {e}")
    
    def _convert_mcp_to_langchain_tools(
        self,
        mcp_tools: List[Dict[str, Any]],
        server_name: str
    ) -> List:
        """MCP Tool을 LangChain Tool 형식으로 변환"""
        from langchain.tools import Tool
        import asyncio
        
        langchain_tools = []
        for mcp_tool in mcp_tools:
            tool_name = mcp_tool.get("name", "")
            tool_description = mcp_tool.get("description", "")
            
            # MCP Tool 호출 래퍼 생성
            def create_tool_wrapper(name: str, server: str):
                async def async_wrapper(*args, **kwargs):
                    client = await self.mcp_manager.get_client(server)
                    result = await client.call_tool(name, kwargs)
                    return result.get("content", "")
                
                # 동기 함수로 변환 (LangChain Tool은 동기 함수 기대)
                def sync_wrapper(*args, **kwargs):
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
                
                return sync_wrapper
            
            tool = Tool(
                name=tool_name,
                func=create_tool_wrapper(tool_name, server_name),
                description=tool_description
            )
            langchain_tools.append(tool)
        
        return langchain_tools
    
    async def _hybrid_search(
        self,
        queries: List[str],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """하이브리드 검색 (Dense + Sparse)
        
        현재는 Dense 검색(벡터 검색)만 구현되어 있습니다.
        향후 Sparse 검색(BM25) 및 RRF 점수 융합 추가 예정.
        
        Args:
            queries: 검색 쿼리 리스트
            filters: 필터 조건 (standard, document_type, company_id, fiscal_year 등)
            top_k: 쿼리당 반환할 최대 결과 수
        
        Returns:
            검색 결과 리스트
        """
        logger.debug(f"🔍 하이브리드 검색 시작: {len(queries)}개 쿼리")
        
        # 서비스 초기화
        embedding_service = self._get_embedding_service()
        vector_repo = self._get_vector_repository()
        
        all_results = []
        seen_chunks = set()  # 중복 제거용
        
        for query in queries:
            try:
                # 1. 쿼리 임베딩 생성
                logger.debug(f"📝 쿼리 임베딩 생성: {query[:50]}...")
                query_embedding = embedding_service.generate_embedding(query, normalize=True)
                query_embedding_list = query_embedding.tolist()
                
                # 2. 벡터 검색
                logger.debug(f"🔎 벡터 DB 검색 중...")
                chunks_with_scores = vector_repo.search_by_vector(
                    query_embedding_list,
                    top_k=top_k,
                    filters=filters,
                    similarity_threshold=0.3  # 최소 유사도 임계값
                )
                
                # 3. 검색 결과 변환
                for chunk, similarity_score in chunks_with_scores:
                    # 중복 제거 (같은 chunk_id는 한 번만)
                    chunk_key = (chunk.chunk_id, query)
                    if chunk_key in seen_chunks:
                        continue
                    seen_chunks.add(chunk_key)
                    
                    result = {
                        "query": query,
                        "content": chunk.chunk_text,
                        "source": chunk.document_path,
                        "score": float(similarity_score),
                        "metadata": {
                            "chunk_id": chunk.chunk_id,
                            "page": chunk.page_number,
                            "standard": chunk.standard,
                            "document_type": chunk.document_type,
                            "company_id": chunk.company_id,
                            "fiscal_year": chunk.fiscal_year,
                            "chunk_index": chunk.chunk_index,
                            **chunk.chunk_metadata
                        }
                    }
                    all_results.append(result)
                
                logger.debug(f"✅ 쿼리 '{query[:30]}...' 검색 완료: {len(chunks_with_scores)}개 결과")
                
            except Exception as e:
                logger.error(f"❌ 쿼리 검색 실패: {query[:50]}... - {e}")
                # 에러 발생 시 더미 결과 추가 (안정성)
                all_results.append({
                    "query": query,
                    "content": f"검색 실패: {str(e)}",
                    "source": "error",
                    "score": 0.0,
                    "metadata": {"error": str(e)}
                })
        
        # 유사도 점수로 정렬
        all_results.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"✅ 하이브리드 검색 완료: 총 {len(all_results)}개 결과 (중복 제거 후)")
        return all_results
    
    def _needs_external_data(
        self,
        search_results: List[Dict],
        target_dps: List[str]
    ) -> bool:
        """외부 데이터 필요 여부 판단"""
        # 간단한 휴리스틱: 검색 결과가 적으면 외부 크롤링 필요
        return len(search_results) < len(target_dps) * 2
    
    async def _collect_external_data_with_llm(
        self,
        company_id: str,
        fiscal_year: int,
        query: str,
        target_dps: List[str]
    ) -> List[Dict[str, Any]]:
        """LLM이 MCP Tools를 사용하여 외부 데이터 수집
        
        LLM이 자동으로 적절한 MCP 도구(웹 검색, DART API, 뉴스 검색)를 선택하여
        외부 데이터를 수집합니다.
        
        Args:
            company_id: 회사 ID
            fiscal_year: 회계연도
            query: 사용자 쿼리
            target_dps: 대상 Data Point 목록
        
        Returns:
            수집된 문서 리스트
        """
        # MCP Tools 바인딩 확인 및 수행
        if not self._mcp_tools_bound:
            await self._bind_mcp_tools()
        
        if not self.mcp_manager or not hasattr(self.llm, 'bind_tools'):
            logger.debug("⚠️ MCP Tools를 사용할 수 없어 직접 크롤링으로 대체합니다.")
            return []
        
        try:
            # LLM에게 외부 데이터 수집 요청
            prompt = f"""
다음 정보를 수집하기 위해 적절한 도구를 사용하세요:

- 회사: {company_id}
- 연도: {fiscal_year}
- 쿼리: {query}
- 대상 Data Points: {', '.join(target_dps[:5])}

필요한 정보:
1. {company_id}의 {fiscal_year}년 지속가능경영보고서 (get_sustainability_report 도구 사용)
2. {company_id}의 ESG 관련 최신 뉴스 (search_news 도구 사용)
3. IFRS S1/S2 관련 최신 정보 (duckduckgo_search 또는 tavily_search 도구 사용)

각 도구를 사용하여 정보를 수집하세요.
"""
            
            messages = [
                SystemMessage(content="당신은 외부 데이터 수집 전문가입니다. 적절한 도구를 선택하여 정보를 수집하세요."),
                HumanMessage(content=prompt)
            ]
            
            # LLM 호출 (Tool Calling 자동 처리)
            response = await self.llm.ainvoke(messages)
            
            # Tool 호출 결과 처리
            collected_data = []
            
            # Tool 호출이 있는 경우 처리
            tool_calls = getattr(response, 'tool_calls', []) or []
            
            if tool_calls:
                logger.info(f"🔧 LLM이 {len(tool_calls)}개 MCP 도구를 선택했습니다.")
                
                for tool_call in tool_calls:
                    # tool_call은 dict 또는 객체일 수 있음
                    if isinstance(tool_call, dict):
                        tool_name = tool_call.get('name', '')
                        tool_input = tool_call.get('args', {})
                    else:
                        tool_name = getattr(tool_call, 'name', '')
                        tool_input = getattr(tool_call, 'args', {}) or {}
                    
                    logger.debug(f"🔧 MCP 도구 호출: {tool_name} - {tool_input}")
                    
                    # MCP Tool 실행
                    tool_result = None
                    try:
                        # Tool 이름으로 서버 식별
                        server_name = self._get_server_for_tool(tool_name)
                        
                        # MCP Tool 호출
                        result = await self.mcp_manager.call_tool(
                            server_name,
                            tool_name,
                            tool_input if isinstance(tool_input, dict) else {}
                        )
                        
                        if result and not result.get("is_error", False):
                            tool_result = result.get("content", "")
                        else:
                            error_msg = result.get("content", "알 수 없는 오류") if result else "도구 호출 실패"
                            logger.error(f"❌ MCP 도구 실행 실패 ({tool_name}): {error_msg}")
                            tool_result = f"도구 실행 실패: {error_msg}"
                    except Exception as e:
                        logger.error(f"❌ MCP 도구 실행 실패 ({tool_name}): {e}")
                        tool_result = f"도구 실행 실패: {str(e)}"
                    
                    if tool_result:
                        # 검색 결과를 문서 형식으로 변환
                        collected_data.append({
                            "content": str(tool_result),
                            "source": f"mcp-tool-{tool_name}",
                            "metadata": {
                                "tool": tool_name,
                                "company_id": company_id,
                                "fiscal_year": fiscal_year,
                                "query": query
                            }
                        })
            
            # Tool 호출이 없으면 직접 DART API 사용
            if not collected_data:
                logger.debug("⚠️ LLM이 도구를 선택하지 않아 직접 DART API를 사용합니다.")
                return []
            
            logger.info(f"✅ MCP 기반 외부 데이터 수집 완료: {len(collected_data)}개 결과")
            return collected_data
            
        except Exception as e:
            logger.error(f"❌ MCP 기반 외부 데이터 수집 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _get_server_for_tool(self, tool_name: str) -> str:
        """Tool 이름으로 서버 식별"""
        tool_server_map = {
            "get_sustainability_report": "dart",
            "search_disclosure": "dart",
            "duckduckgo_search": "web_search",
            "tavily_search": "web_search",
            "search_news": "news"
        }
        return tool_server_map.get(tool_name, "dart")  # 기본값: dart
    
    async def _crawl_external_sources(
        self,
        company_id: str,
        fiscal_year: int
    ) -> List[Dict[str, Any]]:
        """외부 소스 크롤링
        
        DART API를 사용하여 기업 공시 데이터를 크롤링합니다.
        """
        logger.info(f"🔍 외부 소스 크롤링 시작: {company_id}, {fiscal_year}")
        
        if not REQUESTS_AVAILABLE:
            logger.warning("⚠️ requests가 설치되지 않았습니다. pip install requests 필요")
            return []
        
        if not self.dart_api_key:
            logger.warning("⚠️ DART_API_KEY가 설정되지 않았습니다.")
            return []
        
        try:
            # 1. 기업 코드 조회
            corp_code = self._get_company_code(company_id)
            if not corp_code:
                logger.warning(f"⚠️ 기업 코드를 찾을 수 없습니다: {company_id}")
                return []
            
            # 2. 지속가능경영보고서 목록 조회
            reports = self._get_sustainability_reports(corp_code, fiscal_year)
            
            if not reports:
                logger.warning(f"⚠️ {fiscal_year}년 지속가능경영보고서를 찾을 수 없습니다.")
                return []
            
            # 3. 보고서 다운로드, 벡터 DB 저장 및 파싱
            documents = []
            document_service = self._get_document_service()
            
            for report in reports[:3]:  # 최대 3개만 처리
                rcept_no = report.get("rcept_no")
                report_nm = report.get("report_nm", "Unknown")
                
                logger.info(f"📥 보고서 다운로드 중: {report_nm} ({rcept_no})")
                
                # 임시 파일로 다운로드
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                    pdf_path = tmp_file.name
                
                pdf_data = self._download_report(rcept_no, pdf_path)
                
                if pdf_data:
                    try:
                        # 3-1. 벡터 DB에 저장 (청크 분할, 임베딩 생성 포함)
                        logger.info(f"💾 벡터 DB에 저장 중: {report_nm}")
                        saved_count = document_service.store_pdf_to_vector_db(
                            pdf_path=pdf_path,
                            document_type="report",
                            standard="IFRS_S2",  # 기본값, 필요시 동적으로 설정
                            company_id=company_id,
                            fiscal_year=fiscal_year,
                            parser_type="auto"
                        )
                        logger.info(f"✅ 벡터 DB 저장 완료: {saved_count}개 청크")
                        
                        # 3-2. 검색을 위한 간단한 텍스트 추출 (기존 로직 유지)
                        import fitz  # PyMuPDF
                        doc = fitz.open(pdf_path)
                        text_content = "\n\n".join([page.get_text() for page in doc])
                        doc.close()
                        
                        documents.append({
                            "content": text_content,
                            "source": f"DART-{rcept_no}",
                            "metadata": {
                                **report,
                                "company_id": company_id,
                                "fiscal_year": fiscal_year,
                                "chunks_saved": saved_count
                            }
                        })
                        logger.info(f"✅ 보고서 처리 완료: {report_nm} ({saved_count}개 청크)")
                    except Exception as e:
                        logger.error(f"❌ PDF 처리 실패: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                    finally:
                        # 임시 파일 삭제
                        try:
                            os.unlink(pdf_path)
                        except:
                            pass
                else:
                    logger.warning(f"⚠️ 보고서 다운로드 실패: {report_nm}")
            
            logger.info(f"✅ 외부 소스 크롤링 완료: {len(documents)}개 문서")
            return documents
            
        except Exception as e:
            logger.error(f"❌ 외부 소스 크롤링 실패: {e}")
            return []
    
    def _get_company_code(self, company_name: str) -> Optional[str]:
        """회사명으로 기업 코드 조회 (DART API)
        
        DART API의 corpCode.json 엔드포인트를 사용하여 회사명으로 기업 코드를 조회합니다.
        여러 방법을 시도합니다:
        1. 회사명 매핑 테이블 사용
        2. corpCode.json API로 회사명 검색
        3. 종목코드가 있는 경우 종목코드로 조회
        
        Args:
            company_name: 회사명 또는 회사 ID (예: "삼성전자", "삼성SDS", "samsung-sds")
        
        Returns:
            기업 코드 (corp_code) 또는 None
        """
        if not REQUESTS_AVAILABLE or not self.dart_api_key:
            return None
        
        # 회사 ID -> 실제 회사명 매핑
        company_name_map = {
            # 삼성 계열
            "samsung-sds": "삼성에스디에스",
            "samsung-electronics": "삼성전자",
            "samsung-sdi": "삼성SDI",
            "samsung-electro-mechanics": "삼성전기",
            "samsung-life": "삼성생명보험",
            "samsung-fire": "삼성화재해상보험",
            "samsung-securities": "삼성증권",
            "samsung-engineering": "삼성엔지니어링",
            "samsung-heavy": "삼성중공업",
            "samsung-biologics": "삼성바이오로직스",
            # SK 계열
            "sk-hynix": "SK하이닉스",
            "sk-telecom": "SK텔레콤",
            "sk-innovation": "SK이노베이션",
            "sk-energy": "SK에너지",
            "sk-chemicals": "SK케미칼",
            # 현대 계열
            "hyundai-motor": "현대자동차",
            "hyundai-mobis": "현대모비스",
            "hyundai-steel": "현대제철",
            "hyundai-engineering": "현대건설",
            "kia": "기아",
            # LG 계열
            "lg-electronics": "LG전자",
            "lg-chem": "LG화학",
            "lg-display": "LG디스플레이",
            "lg-energy": "LG에너지솔루션",
            # 기타 대기업
            "posco": "포스코홀딩스",
            "naver": "네이버",
            "kakao": "카카오",
            "celltrion": "셀트리온",
            "kb-financial": "KB금융지주",
            "shinhan-financial": "신한지주",
            "hana-financial": "하나금융지주",
            "woori-financial": "우리금융지주",
        }
        
        # 매핑된 회사명으로 변환
        actual_company_name = company_name_map.get(company_name.lower(), company_name)
        
        # 하이픈/언더스코어를 공백으로 변환 (예: samsung-sds -> samsung sds)
        if "-" in actual_company_name or "_" in actual_company_name:
            actual_company_name = actual_company_name.replace("-", " ").replace("_", " ")
        
        logger.debug(f"🔍 회사명 변환: {company_name} -> {actual_company_name}")
        
        # 방법 1: corpCode.json API 사용 (회사명으로 검색)
        # 참고: DART API는 corpCode.json이 아니라 전체 회사코드 파일을 다운로드하는 방식
        # 하지만 회사명으로 검색하려면 전체 파일을 다운로드하거나 다른 방법 사용 필요
        
        # 방법 2: 전체 회사코드 파일 다운로드 후 검색 (캐싱 고려)
        try:
            # 전체 회사코드 파일 다운로드 (ZIP 압축된 XML 형식)
            url = f"{self.dart_base_url}/corpCode.xml"
            params = {
                "crtfc_key": self.dart_api_key
            }
            
            logger.debug(f"📥 DART API 요청: {url}")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '').lower()
            logger.debug(f"📦 응답 Content-Type: {content_type}")
            
            # ZIP 파일 처리 (DART API는 ZIP으로 압축된 XML을 제공)
            xml_content = None
            import zipfile
            import io
            
            # ZIP 파일 시그니처 확인 (PK = ZIP 파일)
            if response.content[:2] == b'PK' or 'zip' in content_type:
                logger.debug("📦 ZIP 파일로 감지, 압축 해제 중...")
                try:
                    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                        # ZIP 파일 내 XML 파일 찾기
                        xml_files = [f for f in zip_file.namelist() if f.endswith('.xml')]
                        if xml_files:
                            xml_file_name = xml_files[0]
                            logger.debug(f"📄 ZIP 내 XML 파일 발견: {xml_file_name}")
                            
                            # XML 파일 읽기 및 인코딩 처리
                            xml_bytes = zip_file.read(xml_file_name)
                            try:
                                xml_content = xml_bytes.decode('utf-8')
                            except UnicodeDecodeError:
                                # UTF-8 실패 시 EUC-KR 시도 (한글 인코딩)
                                try:
                                    xml_content = xml_bytes.decode('euc-kr')
                                except UnicodeDecodeError:
                                    # CP949 시도
                                    xml_content = xml_bytes.decode('cp949')
                            
                            logger.debug(f"✅ ZIP 압축 해제 완료: {len(xml_content)} bytes")
                        else:
                            logger.error("❌ ZIP 파일 내 XML 파일을 찾을 수 없습니다")
                            return None
                except zipfile.BadZipFile as e:
                    logger.warning(f"⚠️ ZIP 파일이 아닙니다: {e}")
                    # ZIP이 아니면 일반 XML로 처리
                    try:
                        xml_content = response.text
                    except:
                        xml_content = response.content.decode('utf-8')
            else:
                # 일반 XML 응답
                logger.debug("📄 일반 XML 응답으로 처리")
                try:
                    xml_content = response.text
                except:
                    xml_content = response.content.decode('utf-8')
            
            if not xml_content:
                logger.error("❌ XML 내용을 추출할 수 없습니다")
                return None
            
            # XML 파싱 (xml.etree.ElementTree 사용)
            try:
                import xml.etree.ElementTree as ET
                # XML 문자열을 바이트로 변환하여 파싱
                root = ET.fromstring(xml_content.encode('utf-8') if isinstance(xml_content, str) else xml_content)
                
                # 정확한 매칭 우선
                logger.debug(f"🔎 정확한 매칭 검색 중: '{actual_company_name}'")
                for item in root.findall('.//list'):
                    corp_code_elem = item.find('corp_code')
                    corp_name_elem = item.find('corp_name')
                    
                    if corp_code_elem is not None and corp_name_elem is not None:
                        corp_code_val = corp_code_elem.text
                        corp_name_val = corp_name_elem.text
                        
                        if corp_name_val == actual_company_name:
                            logger.info(f"✅ 기업 코드 조회 성공 (정확한 매칭): {company_name} -> {corp_code_val}")
                            return corp_code_val
                
                # 부분 매칭 시도 (회사명이 포함된 경우)
                logger.debug(f"🔎 부분 매칭 검색 중: '{actual_company_name}'")
                matches = []
                for item in root.findall('.//list'):
                    corp_code_elem = item.find('corp_code')
                    corp_name_elem = item.find('corp_name')
                    
                    if corp_code_elem is not None and corp_name_elem is not None:
                        corp_code_val = corp_code_elem.text
                        corp_name_val = corp_name_elem.text
                        
                        if actual_company_name in corp_name_val:
                            matches.append((corp_code_val, corp_name_val))
                
                if matches:
                    # 첫 번째 매칭 결과 반환
                    corp_code_val, corp_name_val = matches[0]
                    logger.info(f"✅ 기업 코드 조회 성공 (부분 매칭): {company_name} -> {corp_code_val} ({corp_name_val})")
                    if len(matches) > 1:
                        logger.debug(f"   💡 총 {len(matches)}개 매칭 발견, 첫 번째 결과 사용")
                    return corp_code_val
                
            except ET.ParseError as e:
                logger.warning(f"⚠️ XML 파싱 실패, 정규식으로 재시도: {e}")
                # XML 파싱 실패 시 정규식으로 재시도
                import re
                
                # 정확한 매칭
                pattern = rf'<corp_code>([^<]+)</corp_code>\s*<corp_name>{re.escape(actual_company_name)}</corp_name>'
                match = re.search(pattern, xml_content)
                
                if match:
                    corp_code = match.group(1)
                    logger.info(f"✅ 기업 코드 조회 성공 (정규식): {company_name} -> {corp_code}")
                    return corp_code
                
                # 부분 매칭
                pattern_partial = rf'<corp_code>([^<]+)</corp_code>\s*<corp_name>[^<]*{re.escape(actual_company_name)}[^<]*</corp_name>'
                match_partial = re.search(pattern_partial, xml_content)
                
                if match_partial:
                    corp_code = match_partial.group(1)
                    logger.info(f"✅ 기업 코드 조회 성공 (정규식 부분 매칭): {company_name} -> {corp_code}")
                    return corp_code
            
            logger.warning(f"⚠️ 기업을 찾을 수 없습니다: {company_name}")
            return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ DART API 요청 실패: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 회사코드 파싱 실패: {e}")
            return None
    
    def _get_report_list(
        self,
        corp_code: str,
        bgn_de: str,  # "20240101"
        end_de: str,  # "20241231"
        pblntf_ty: str = "A"  # A: 정기공시, B: 주요사항보고
    ) -> List[Dict]:
        """보고서 목록 조회 (DART API)
        
        Args:
            corp_code: 기업 코드
            bgn_de: 시작일 (YYYYMMDD)
            end_de: 종료일 (YYYYMMDD)
            pblntf_ty: 공시 유형 (A: 정기공시, B: 주요사항보고)
        
        Returns:
            보고서 목록
        """
        if not REQUESTS_AVAILABLE or not self.dart_api_key:
            return []
        
        url = f"{self.dart_base_url}/list.json"
        params = {
            "crtfc_key": self.dart_api_key,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_ty": pblntf_ty
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "000":
                reports = data.get("list", [])
                logger.info(f"✅ 보고서 목록 조회 성공: {len(reports)}개")
                return reports
            else:
                error_msg = data.get("message", "알 수 없는 오류")
                logger.error(f"❌ DART API 오류: {error_msg}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ DART API 요청 실패: {e}")
            return []
    
    def _get_sustainability_reports(
        self,
        corp_code: str,
        year: int
    ) -> List[Dict]:
        """지속가능경영보고서 목록 조회 (DART API)
        
        Args:
            corp_code: 기업 코드
            year: 연도
        
        Returns:
            지속가능경영보고서 목록
        """
        bgn_de = f"{year}0101"
        end_de = f"{year}1231"
        
        reports = self._get_report_list(corp_code, bgn_de, end_de)
        
        # 지속가능경영보고서 필터링
        sustainability_reports = [
            r for r in reports
            if any(keyword in r.get("report_nm", "") for keyword in [
                "지속가능", "ESG", "sustainability", "Sustainability",
                "ESG보고서", "지속가능경영", "지속가능성"
            ])
        ]
        
        logger.info(f"✅ 지속가능경영보고서 {len(sustainability_reports)}개 발견")
        return sustainability_reports
    
    def _download_report(
        self,
        rcept_no: str,
        save_path: Optional[str] = None
    ) -> Optional[bytes]:
        """보고서 원문 다운로드 (PDF) - DART API
        
        Args:
            rcept_no: 접수번호
            save_path: 저장 경로 (선택)
        
        Returns:
            PDF 바이너리 데이터 또는 None
        """
        if not REQUESTS_AVAILABLE:
            return None
        
        # DART 보고서 다운로드 URL
        download_url = f"https://dart.fss.or.kr/pdf/download/pdf.do?rcp_no={rcept_no}&dcm_no="
        
        try:
            response = requests.get(download_url, timeout=30)
            response.raise_for_status()
            
            # PDF인지 확인
            if response.headers.get("content-type") == "application/pdf":
                pdf_data = response.content
                
                if save_path:
                    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(pdf_data)
                    logger.info(f"✅ 보고서 다운로드 완료: {save_path}")
                
                return pdf_data
            else:
                logger.warning(f"⚠️ PDF가 아닌 파일입니다: {rcept_no}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 보고서 다운로드 실패: {e}")
            return None
    
    def _get_financial_statements(
        self,
        corp_code: str,
        bsns_year: str,  # "2024"
        reprt_code: str = "11011"  # 11011: 사업보고서, 11012: 반기보고서
    ) -> Optional[Dict]:
        """재무제표 데이터 조회 (DART API)
        
        Args:
            corp_code: 기업 코드
            bsns_year: 사업연도
            reprt_code: 보고서 코드 (11011: 사업보고서)
        
        Returns:
            재무제표 데이터 또는 None
        """
        if not REQUESTS_AVAILABLE or not self.dart_api_key:
            return None
        
        url = f"{self.dart_base_url}/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": self.dart_api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "000":
                logger.info("✅ 재무제표 데이터 조회 성공")
                return data
            else:
                error_msg = data.get("message", "알 수 없는 오류")
                logger.error(f"❌ DART API 오류: {error_msg}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ DART API 요청 실패: {e}")
            return None
    
    async def _extract_multimodal_content(
        self,
        pdf_paths: List[str],
        target_dps: List[str]
    ) -> List[Dict[str, Any]]:
        """멀티모달 콘텐츠 추출 (표·이미지)
        
        TODO: 실제 구현 시
        - LlamaParse로 표 추출
        - 이미지 캡셔닝 (GPT-4o-mini Vision 또는 Donut)
        """
        logger.debug(f"멀티모달 추출: {len(pdf_paths)}개 PDF")
        
        # 더미 멀티모달 결과
        return []
    
    async def _extract_dps(
        self,
        search_results: List[Dict[str, Any]],
        target_dps: List[str]
    ) -> List[Dict[str, Any]]:
        """DP 추출 및 팩트 시트 생성
        
        DataPoint 메타데이터를 DB에서 조회하여 팩트 시트에 포함합니다.
        DP ID가 정확히 일치하지 않으면 유사한 DP를 검색합니다.
        """
        logger.debug(f"📊 DP 추출 시작: {len(target_dps)}개 DP")
        
        # DB 세션 생성
        db = get_session()
        fact_sheets = []
        
        try:
            # LLM을 사용한 DP 추출
            for dp_id in target_dps:
                try:
                    # 1. DataPoint 메타데이터 조회 (정확히 일치)
                    dp = db.query(DataPoint).filter(
                        DataPoint.dp_id == dp_id,
                        DataPoint.is_active == True
                    ).first()
                    
                    # 2. 정확히 일치하지 않으면 유사한 DP 검색
                    if not dp:
                        dp = self._find_similar_dp(db, dp_id)
                    
                    if not dp:
                        logger.warning(f"⚠️ DP를 찾을 수 없습니다: {dp_id}")
                        fact_sheets.append(self._create_dummy_fact_sheet(dp_id))
                        continue
                    
                    # 2. 관련 검색 결과 필터링 (DP 이름도 포함하여 검색)
                    search_keywords = [
                        dp_id.lower(),
                        dp.name_ko.lower() if dp.name_ko else "",
                        dp.name_en.lower() if dp.name_en else ""
                    ]
                    
                    relevant_results = [
                        r for r in search_results
                        if any(
                            keyword in r.get("content", "").lower()
                            for keyword in search_keywords
                            if keyword
                        )
                    ]
                    
                    if not relevant_results:
                        logger.warning(f"⚠️ DP {dp_id}에 대한 검색 결과가 없습니다.")
                        # 메타데이터만 포함한 더미 팩트 시트 생성
                        fact_sheet = self._create_dummy_fact_sheet(dp_id)
                        fact_sheet.update(self._get_dp_metadata(dp))
                    else:
                        # 3. LLM으로 값 추출 (DP 메타데이터 포함)
                        fact_sheet = await self._extract_with_llm(
                            relevant_results,
                            dp_id,
                            dp_metadata=dp
                        )
                    
                    fact_sheets.append(fact_sheet)
                    
                except Exception as e:
                    logger.error(f"❌ DP {dp_id} 추출 실패: {e}")
                    # 실패 시 더미 데이터
                    fact_sheets.append(self._create_dummy_fact_sheet(dp_id))
        
        finally:
            db.close()
        
        logger.info(f"✅ DP 추출 완료: {len(fact_sheets)}개 팩트 시트 생성")
        return fact_sheets
    
    def _find_similar_dp(self, db, dp_id: str) -> Optional[DataPoint]:
        """유사한 DP 검색
        
        DP ID가 정확히 일치하지 않을 때 유사한 DP를 찾습니다.
        child_dps 관계를 활용하여 더 정확한 매칭을 수행합니다.
        
        검색 우선순위:
        1. 직접 검색 (S2-xx 형식)
        2. Parent-Child 관계 활용 (child_dps 컬럼 사용)
        3. 키워드 기반 검색
        4. 숫자 기반 검색 (최소한의 범위로 제한)
        
        예: S2-15-a -> S2-15의 child_dps에서 S2-15-a 찾기
            S2-GOV-1 -> 거버넌스 관련 DP
        """
        from sqlalchemy import or_, func
        import re
        
        # 1. 직접 검색 시도 (올바른 형식: S2-xx)
        dp = db.query(DataPoint).filter(
            DataPoint.dp_id == dp_id,
            DataPoint.is_active == True
        ).first()
        if dp:
            return dp
        
        # 2. 부모 DP 찾기 (S2-15-a -> S2-15)
        if dp_id.startswith("S1-") or dp_id.startswith("S2-"):
            match = re.match(r'S[12]-(\d+)', dp_id)
            if match:
                num_part = match.group(1)
                parent_id = f"{dp_id[:2]}-{num_part}"
                
                # 부모 DP 찾기
                parent_dp = db.query(DataPoint).filter(
                    DataPoint.dp_id == parent_id,
                    DataPoint.is_active == True
                ).first()
                
                if parent_dp:
                    # child_dps가 있으면 그 안에서 정확히 일치하는 것 찾기
                    if parent_dp.child_dps and len(parent_dp.child_dps) > 0:
                        # child_dps는 ARRAY 타입이므로 직접 비교
                        for child_id in parent_dp.child_dps:
                            if child_id == dp_id:
                                child_dp = db.query(DataPoint).filter(
                                    DataPoint.dp_id == child_id,
                                    DataPoint.is_active == True
                                ).first()
                                if child_dp:
                                    logger.info(f"✅ DP Parent-Child 관계 검색 성공: {dp_id} -> {child_dp.dp_id} (부모: {parent_id})")
                                    return child_dp
                    
                    # child_dps가 없거나 매칭 실패 시, 부모 DP 반환
                    logger.info(f"✅ DP 부모 검색 성공: {dp_id} -> {parent_dp.dp_id}")
                    return parent_dp
                
                # 부모가 없으면 S2-{num}-로 시작하는 DP 검색 (더 정확한 범위)
                dp = db.query(DataPoint).filter(
                    DataPoint.dp_id.like(f"{dp_id[:2]}-{num_part}-%"),  # S2-15-로 시작하는 것만
                    DataPoint.is_active == True
                ).first()
                if dp:
                    logger.info(f"✅ DP ID 유사 검색 성공: {dp_id} -> {dp.dp_id}")
                    return dp
        
        # 2. 키워드 기반 검색 (GOV -> 거버넌스, STR -> 전략 등)
        keyword_map = {
            "GOV": ["거버넌스", "governance", "지배구조", "이사회"],
            "STR": ["전략", "strategy", "시나리오"],
            "RISK": ["위험", "risk", "리스크"],
            "METRIC": ["지표", "metric", "배출량", "목표"]
        }
        
        for key, keywords in keyword_map.items():
            if key in dp_id.upper():
                for keyword in keywords:
                    dp = db.query(DataPoint).filter(
                        or_(
                            DataPoint.name_ko.ilike(f"%{keyword}%"),
                            DataPoint.topic.ilike(f"%{keyword}%")
                        ),
                        DataPoint.is_active == True
                    ).first()
                    if dp:
                        logger.info(f"✅ DP 키워드 검색 성공: {dp_id} -> {dp.dp_id} ({keyword})")
                        return dp
        
        # 3. 숫자 기반 유사 검색 (마지막 수단, 더 정확한 범위로 제한)
        # 전체 숫자가 아닌 주요 숫자만 사용 (예: S2-15-a -> "15"만 사용)
        numbers = re.findall(r'\d+', dp_id)
        if numbers:
            # 가장 큰 숫자만 사용 (일반적으로 DP 번호)
            main_number = max(numbers, key=len) if numbers else None
            if main_number and len(main_number) >= 2:  # 최소 2자리 숫자만
                # S2-{number} 또는 S1-{number} 형식으로 정확히 매칭
                prefix = dp_id[:2] if dp_id.startswith("S1") or dp_id.startswith("S2") else "S2"
                dp = db.query(DataPoint).filter(
                    DataPoint.dp_id.like(f"{prefix}-{main_number}%"),  # S2-15로 시작하는 것만
                    DataPoint.is_active == True
                ).first()
                if dp:
                    logger.info(f"✅ DP 숫자 기반 검색 성공: {dp_id} -> {dp.dp_id} (숫자: {main_number})")
                    return dp
        
        return None
    
    def _get_dp_metadata(self, dp: DataPoint) -> Dict[str, Any]:
        """DataPoint 메타데이터를 딕셔너리로 변환"""
        # Enum 값 안전하게 추출 (문자열인 경우도 처리)
        def safe_enum_value(val):
            if val is None:
                return None
            if hasattr(val, 'value'):
                return val.value
            return str(val)
        
        return {
            "dp_name": dp.name_ko,
            "dp_name_en": dp.name_en,
            "description": dp.description or "",
            "topic": dp.topic,
            "subtopic": dp.subtopic,
            "unit": safe_enum_value(dp.unit),
            "dp_type": safe_enum_value(dp.dp_type),
            "financial_impact_type": dp.financial_impact_type,
            "validation_rules": dp.validation_rules if dp.validation_rules else {},
            "value_range": dp.value_range if dp.value_range else None,
            "disclosure_requirement": safe_enum_value(dp.disclosure_requirement),
            "reporting_frequency": dp.reporting_frequency,
            "category": dp.category,
            "standard": dp.standard
        }
    
    async def _extract_with_llm(
        self,
        search_results: List[Dict],
        dp_id: str,
        dp_metadata: Optional[DataPoint] = None
    ) -> Dict[str, Any]:
        """LLM을 사용한 DP 값 추출 (메타데이터 활용)
        
        Args:
            search_results: 벡터 검색 결과
            dp_id: Data Point ID
            dp_metadata: DataPoint 메타데이터 (선택)
        """
        # 검색 결과 요약 (더 많은 컨텍스트 포함)
        content_summary = "\n\n".join([
            f"[출처: {r.get('source', 'unknown')}, 점수: {r.get('score', 0):.2f}]\n{r.get('content', '')[:500]}"
            for r in search_results[:5]
        ])
        
        # DP 메타데이터 정보 구성
        # Enum 값 안전하게 추출 (문자열인 경우도 처리)
        def safe_enum_value(val):
            if val is None:
                return None
            if hasattr(val, 'value'):
                return val.value
            return str(val)
        
        metadata_info = ""
        if dp_metadata:
            unit_info = safe_enum_value(dp_metadata.unit) or "자동 감지"
            dp_type_info = safe_enum_value(dp_metadata.dp_type) or "N/A"
            value_range_info = ""
            if dp_metadata.value_range:
                if isinstance(dp_metadata.value_range, dict):
                    min_val = dp_metadata.value_range.get("min")
                    max_val = dp_metadata.value_range.get("max")
                    if min_val is not None or max_val is not None:
                        value_range_info = f"값 범위: {min_val if min_val is not None else 'N/A'} ~ {max_val if max_val is not None else 'N/A'}"
            
            metadata_info = f"""
## Data Point 정보
- 이름: {dp_metadata.name_ko} ({dp_metadata.name_en if dp_metadata.name_en else "N/A"})
- 설명: {dp_metadata.description[:300] if dp_metadata.description else "N/A"}
- 단위: {unit_info}
- 타입: {dp_type_info}
- 주제: {dp_metadata.topic or "N/A"}{f" > {dp_metadata.subtopic}" if dp_metadata.subtopic else ""}
{value_range_info}
- 재무 영향: {dp_metadata.financial_impact_type or "N/A"}
"""
        
        prompt = f"""
다음 검색 결과에서 Data Point {dp_id}의 값을 추출하세요.
{metadata_info}
## 검색 결과
{content_summary}

## 요구사항
1. {dp_metadata.name_ko if dp_metadata else dp_id}의 2022, 2023, 2024년 값 추출
2. 단위 확인 ({dp_metadata.unit.value if dp_metadata and dp_metadata.unit else "자동 감지"})
3. 값이 없으면 null로 표시
4. 값 범위 검증 ({dp_metadata.value_range if dp_metadata and dp_metadata.value_range else "범위 없음"})
5. 출처 명시 (검색 결과의 source 필드 사용)
6. 신뢰도 점수 (0-1, 값이 명확하면 높게, 불확실하면 낮게)

## 출력 형식
JSON 형식으로 응답하세요:
{{
    "dp_id": "{dp_id}",
    "values": {{"2022": value_or_null, "2023": value_or_null, "2024": value_or_null}},
    "unit": "단위",
    "source": "출처",
    "page_reference": "페이지 참조 (있는 경우)",
    "confidence": 0.9
}}
"""
        
        try:
            messages = [
                SystemMessage(content=RAG_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            result = self._parse_llm_response(response.content, dp_id, dp_metadata)
            
            # DP 메타데이터 병합
            if dp_metadata:
                result.update(self._get_dp_metadata(dp_metadata))
            
            return result
            
        except Exception as e:
            logger.error(f"LLM 추출 실패: {e}")
            fact_sheet = self._create_dummy_fact_sheet(dp_id)
            if dp_metadata:
                fact_sheet.update(self._get_dp_metadata(dp_metadata))
            return fact_sheet
    
    def _parse_llm_response(
        self,
        response_text: str,
        dp_id: str,
        dp_metadata: Optional[DataPoint] = None
    ) -> Dict[str, Any]:
        """LLM 응답 파싱
        
        Args:
            response_text: LLM 응답 텍스트
            dp_id: Data Point ID
            dp_metadata: DataPoint 메타데이터 (선택, 향후 검증에 사용 가능)
        """
        import json
        import re
        
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
            
            # 기본값 보완
            if "values" not in result:
                result["values"] = {}
            if "unit" not in result:
                result["unit"] = "N/A"
            if "source" not in result:
                result["source"] = "internal"
            if "confidence" not in result:
                result["confidence"] = 0.5
            
            result["dp_id"] = dp_id
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return self._create_dummy_fact_sheet(dp_id)
    
    def _create_dummy_fact_sheet(self, dp_id: str) -> Dict[str, Any]:
        """더미 팩트 시트 생성 (테스트용)"""
        return {
            "dp_id": dp_id,
            "dp_name": f"Data Point {dp_id}",
            "values": {
                2022: 100,
                2023: 95,
                2024: 90
            },
            "unit": "N/A",
            "source": "dummy",
            "page_reference": "",
            "confidence": 0.3  # 낮은 신뢰도 표시
        }
    
    def _organize_by_year(
        self,
        fact_sheets: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """연도별 데이터 정리"""
        yearly_data = {}
        
        for fact_sheet in fact_sheets:
            for year, value in fact_sheet.get("values", {}).items():
                if year not in yearly_data:
                    yearly_data[year] = {}
                
                yearly_data[year][fact_sheet["dp_id"]] = {
                    "value": value,
                    "unit": fact_sheet.get("unit", "N/A"),
                    "source": fact_sheet.get("source", "unknown")
                }
        
        return yearly_data


# ============================================
# MCP Server 기능 (통합)
# ============================================

try:
    from mcp.server.fastmcp import FastMCP
    MCP_SERVER_AVAILABLE = True
except ImportError:
    MCP_SERVER_AVAILABLE = False

# MCP 서버 인스턴스 (선택적)
_mcp_server: Optional[FastMCP] = None
_rag_node_instance: Optional[RAGNode] = None


def get_rag_node_instance() -> RAGNode:
    """RAG Node 인스턴스 가져오기 (싱글톤, MCP 서버용)"""
    global _rag_node_instance
    if _rag_node_instance is None:
        try:
            _rag_node_instance = RAGNode()
            logger.info("RAG Node 인스턴스 생성 완료 (MCP 서버용)")
        except Exception as e:
            logger.error(f"RAG Node 초기화 실패: {e}")
            raise
    return _rag_node_instance


def get_mcp_server() -> Optional[FastMCP]:
    """MCP 서버 인스턴스 가져오기"""
    global _mcp_server
    if not MCP_SERVER_AVAILABLE:
        return None
    
    if _mcp_server is None:
        _mcp_server = FastMCP("RAG Node Server")
        
        @_mcp_server.tool()
        async def process(
            state: Dict[str, Any],
            instruction: Optional[str] = None
        ) -> Dict[str, Any]:
            """RAG Node 처리 (MCP Tool)
            
            Supervisor로부터 받은 State를 처리하고 수정된 State를 반환합니다.
            
            Args:
                state: IFRSAgentState 딕셔너리
                instruction: Supervisor의 지시사항 (선택적)
            
            Returns:
                수정된 IFRSAgentState 딕셔너리
            """
            try:
                node = get_rag_node_instance()
                
                # instruction이 있으면 state에 추가
                if instruction:
                    state["instruction"] = instruction
                
                # RAG Node 처리
                result_state = await node.process(state)
                
                # Dict로 변환하여 반환
                return {
                    "state": result_state,
                    "success": True,
                    "fact_sheets_count": len(result_state.get("fact_sheets", [])),
                    "status": result_state.get("status", "unknown")
                }
                
            except Exception as e:
                logger.error(f"RAG Node 처리 실패: {e}")
                import traceback
                traceback.print_exc()
                
                # 에러 발생 시 원본 state에 에러 추가
                state["errors"] = state.get("errors", [])
                state["errors"].append(f"RAG Node 처리 실패: {str(e)}")
                state["status"] = "error"
                
                return {
                    "state": state,
                    "success": False,
                    "error": str(e)
                }
        
        @_mcp_server.tool()
        async def get_status() -> Dict[str, Any]:
            """RAG Node 상태 조회 (MCP Tool)
            
            Returns:
                RAG Node의 현재 상태 정보
            """
            try:
                node = get_rag_node_instance()
                return {
                    "status": "ready",
                    "model": node.llm.model_name if hasattr(node, 'llm') else "unknown",
                    "mcp_available": node.mcp_manager is not None if hasattr(node, 'mcp_manager') else False
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e)
                }
        
        logger.info("RAG Node MCP 서버 초기화 완료")
    
    return _mcp_server


# MCP 서버 실행 진입점
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        # MCP 서버 모드로 실행
        server = get_mcp_server()
        if server:
            logger.info("RAG Node MCP 서버 시작...")
            server.run()
        else:
            print("⚠️ MCP가 설치되지 않았습니다. pip install mcp 필요")
            sys.exit(1)
    else:
        # 일반 모듈로 실행 (테스트 등)
        print("RAG Node 모듈입니다.")
        print("MCP 서버로 실행하려면: python -m ifrs_agent.agent.rag_node --mcp")
