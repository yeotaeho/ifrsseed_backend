"""ESG data agent router (Phase 3)."""

from __future__ import annotations

from typing import Literal

from backend.domain.v1.esg_data.models.langgraph import UCMWorkflowState

AgentName = Literal["creation_agent", "validation_agent"]


class AgentRouter:
    """?뚰겕?뚮줈???곹깭瑜?諛뷀깢?쇰줈 ?ㅼ쓬 ?먯씠?꾪듃瑜??좏깮."""

    def route(self, state: UCMWorkflowState) -> AgentName:
        if state.get("force_validate_only"):
            return "validation_agent"
        if state.get("route") == "validation_agent":
            return "validation_agent"
        return "creation_agent"

