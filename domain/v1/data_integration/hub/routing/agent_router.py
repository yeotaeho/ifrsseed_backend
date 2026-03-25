"""Hub Routing - Agent/Service 호출 중재자

Orchestrator의 명령을 받아 적절한 Agent나 Service로 라우팅합니다.
"""
from typing import Any, Dict, Optional
from loguru import logger

from ...spokes.agents.sr_agent import SRAgent
from ...spokes.agents.sr_save_agent import SRSaveAgent
from ...spokes.agents.sr_index_agent import SRIndexAgent
from ...spokes.agents.sr_body_agent import SRBodyAgent
from ...spokes.agents.sr_images_agent import SRImagesAgent


class AgentRouter:
    """
    Agent 라우터 - Agent 선택 및 호출 중재
    
    Orchestrator가 "어떤 작업"을 해야 할지 판단하면,
    Router가 "어떤 Agent"를 호출할지 결정합니다.
    """
    
    def __init__(self):
        # Agent 레지스트리
        self._agents: Dict[str, Any] = {}
        self._initialized = False
    
    def _initialize_agents(self):
        """Agent 인스턴스 생성 (Lazy Initialization)"""
        if self._initialized:
            return
        
        try:
            self._agents["sr_agent"] = SRAgent()
            logger.info("SR Agent 초기화 완료")
        except Exception as e:
            logger.error(f"SR Agent 초기화 실패: {e}")
        
        try:
            self._agents["sr_save_agent"] = SRSaveAgent()
            logger.info("SR Save Agent 초기화 완료")
        except Exception as e:
            logger.error(f"SR Save Agent 초기화 실패: {e}")

        try:
            self._agents["sr_index_agent"] = SRIndexAgent()
            logger.info("SR Index Agent 초기화 완료")
        except Exception as e:
            logger.error(f"SR Index Agent 초기화 실패: {e}")

        try:
            self._agents["sr_body_agent"] = SRBodyAgent()
            logger.info("SR Body Agent 초기화 완료")
        except Exception as e:
            logger.error(f"SR Body Agent 초기화 실패: {e}")

        try:
            self._agents["sr_images_agent"] = SRImagesAgent()
            logger.info("SR Images Agent 초기화 완료")
        except Exception as e:
            logger.error(f"SR Images Agent 초기화 실패: {e}")

        self._initialized = True
    
    async def route_to(self, agent_name: str, **kwargs) -> Dict[str, Any]:
        """
        지정된 Agent로 요청을 라우팅합니다.
        
        Args:
            agent_name: 호출할 Agent 이름 ("sr_agent", "sr_save_agent", ...)
            **kwargs: Agent에 전달할 파라미터
        
        Returns:
            Agent 실행 결과
        """
        self._initialize_agents()
        
        agent = self._agents.get(agent_name)
        if not agent:
            logger.error(f"알 수 없는 Agent: {agent_name}")
            return {
                "success": False,
                "message": f"Agent '{agent_name}'을 찾을 수 없습니다.",
            }
        
        logger.info(f"[Routing] {agent_name}로 라우팅: {list(kwargs.keys())}")
        
        try:
            # Agent 실행
            if agent_name == "sr_agent":
                company = kwargs.get("company")
                year = kwargs.get("year")
                company_id = kwargs.get("company_id")
                use_bytes_mode = kwargs.get("use_bytes_mode", True)
                if not company or not year:
                    return {
                        "success": False,
                        "message": "company와 year 파라미터가 필요합니다.",
                    }
                result = await agent.execute(company=company, year=year, company_id=company_id)
            
            elif agent_name == "sr_save_agent":
                pdf_bytes = kwargs.get("pdf_bytes")
                company = kwargs.get("company")
                year = kwargs.get("year")
                company_id = kwargs.get("company_id")
                if not pdf_bytes:
                    return {
                        "success": False,
                        "message": "pdf_bytes 파라미터가 필요합니다.",
                    }
                result = await agent.execute(pdf_bytes, company, year, company_id)

            elif agent_name == "sr_index_agent":
                pdf_bytes = kwargs.get("pdf_bytes")
                company = kwargs.get("company", "")
                year = kwargs.get("year", 0)
                report_id = kwargs.get("report_id")
                if not pdf_bytes:
                    return {
                        "success": False,
                        "message": "pdf_bytes 파라미터가 필요합니다.",
                    }
                if not report_id:
                    return {
                        "success": False,
                        "message": "report_id 파라미터가 필요합니다.",
                    }
                result = await agent.execute(
                    pdf_bytes=pdf_bytes,
                    company=company,
                    year=year,
                    report_id=report_id,
                )

            elif agent_name == "sr_body_agent":
                pdf_bytes = kwargs.get("pdf_bytes")
                report_id = kwargs.get("report_id")
                index_page_numbers = kwargs.get("index_page_numbers")
                if not pdf_bytes or not report_id:
                    return {
                        "success": False,
                        "message": "pdf_bytes와 report_id가 필요합니다.",
                    }
                result = await agent.execute(
                    pdf_bytes=pdf_bytes,
                    report_id=report_id,
                    index_page_numbers=index_page_numbers,
                )

            elif agent_name == "sr_images_agent":
                pdf_bytes = kwargs.get("pdf_bytes")
                report_id = kwargs.get("report_id")
                index_page_numbers = kwargs.get("index_page_numbers")
                image_output_dir = kwargs.get("image_output_dir")
                base_name = kwargs.get("base_name")
                if not pdf_bytes or not report_id:
                    return {
                        "success": False,
                        "message": "pdf_bytes와 report_id가 필요합니다.",
                    }
                result = await agent.execute(
                    pdf_bytes=pdf_bytes,
                    report_id=report_id,
                    index_page_numbers=index_page_numbers,
                    image_output_dir=image_output_dir,
                    base_name=base_name,
                )

            else:
                result = {"success": False, "message": f"Agent '{agent_name}'은 아직 구현되지 않았습니다."}
            
            logger.info(f"[Routing] {agent_name} 실행 완료: success={result.get('success')}")
            if not result.get("success"):
                logger.warning(
                    "[Routing] {} 실패 상세: message={} errors={}",
                    agent_name,
                    result.get("message"),
                    result.get("errors"),
                )
            return result
            
        except Exception as e:
            logger.error(f"[Routing] {agent_name} 실행 실패: {e}")
            return {
                "success": False,
                "message": f"Agent 실행 중 오류 발생: {str(e)}",
            }
    
    def get_available_agents(self) -> list[str]:
        """사용 가능한 Agent 목록 반환"""
        self._initialize_agents()
        return list(self._agents.keys())
