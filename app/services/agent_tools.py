"""Agent tool 등록·intent별 후보 조회 (실행은 하지 않음; 7차 이후 확장)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AgentTool",
    "AgentToolRegistry",
]


@dataclass(frozen=True)
class AgentTool:
    """실행 메서드 없이 메타만 보유. 이후 단계에서 run/execute 연결."""

    name: str
    description: str
    intents: tuple[str, ...]


class AgentToolRegistry:
    """기본 tool 목록 및 intent별 후보 조회."""

    def __init__(self, tools: list[AgentTool] | None = None) -> None:
        self._tools: tuple[AgentTool, ...] = tuple(tools) if tools is not None else _default_tools()

    def get_tools_for_intent(self, intent: str) -> list[AgentTool]:
        return [t for t in self._tools if intent in t.intents]

    def get_tool_names_for_intent(self, intent: str) -> list[str]:
        return [t.name for t in self.get_tools_for_intent(intent)]


def _default_tools() -> list[AgentTool]:
    return [
        AgentTool(
            name="retriever_search",
            description="Qdrant 문서 검색용 tool",
            intents=("RAG_SEARCH",),
        ),
        AgentTool(
            name="feature_template_guide",
            description="기능템플릿 생성 API 사용 안내용 tool",
            intents=("FEATURE_TEMPLATE_HELP",),
        ),
        AgentTool(
            name="general_chat",
            description="일반 대화 처리용 tool",
            intents=("GENERAL_CHAT",),
        ),
    ]
