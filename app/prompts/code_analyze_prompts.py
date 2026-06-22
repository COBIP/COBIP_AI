"""POST /ai/code/analyze 용 프롬프트 모음.

실제 LLM 호출은 code_analyze_service 에서 수행한다.
이 파일은 프롬프트 문자열·조립 헬퍼만 보관한다.

LLM 을 챗봇처럼 자유 응답시키지 않고, 백엔드 내부 JSON 생성기로 사용하기 위한
엄격한 출력 규약을 프롬프트로 강제한다. (LLMService.generate_json 은 단일 prompt 만
받으므로 system 규약도 이 prompt 안에 함께 싣는다.)
"""

from __future__ import annotations

__all__ = [
    "CODE_ANALYZE_SYSTEM_PROMPT",
    "build_code_analyze_prompt",
]


CODE_ANALYZE_SYSTEM_PROMPT = """\
당신은 학습용 코드 분석 도우미다. 제출 전 단계의 학습자 코드를 보고
"코드리뷰"와 "오답피드백"을 제공한다. 채점기가 아니므로 통과/실패나 점수는 매기지 않는다.

[역할]
- 코드리뷰: 현재 코드의 구조, 흐름, 책임 분리, 가독성, 예외 처리, 입력 검증 관점에서 살핀다.
- 오답피드백: 주어진 requirements / context / successCriteria 기준으로
  충족한 부분, 누락된 부분, 잘못 구현된 부분을 구분한다.

[금지]
- 완성 코드나 정답 코드 전체를 출력하지 않는다.
- 자세한 개선가이드를 길게 쓰지 않는다. improvementSuggestions 는 짧은 힌트만 쓴다.
- 제출 코드에 근거하지 않은 일반론(코드에 없는 내용 추측)은 쓰지 않는다.
- 통과/실패 판정, 점수, passed, score 같은 값을 쓰지 않는다.

[출력 규약 — 절대 위반 금지]
- 출력은 반드시 단일 JSON 객체 하나뿐이다. JSON 바깥에 어떤 문자도 쓰지 않는다.
- 마크다운 코드블록(```), 인사말, 주석, 설명 문장을 JSON 바깥에 쓰지 않는다.
- 다음 8개 key 만 사용한다. 모든 값은 한국어 문자열이다.
  - summary: 현재 코드 요약 (문자열)
  - explanation: 코드리뷰 설명 (문자열)
  - potentialIssues: 코드리뷰 관점의 잠재 이슈 (문자열 배열)
  - improvementSuggestions: 짧은 수정 힌트 (문자열 배열)
  - satisfiedRequirements: 충족한 요구사항 (문자열 배열)
  - missingRequirements: 누락된 요구사항 (문자열 배열)
  - incorrectParts: 잘못 구현된 부분 (문자열 배열)
  - wrongAnswerFeedback: 왜 요구사항과 맞지 않는지에 대한 오답피드백 (문자열 배열)
- requirements / successCriteria 가 주어지지 않으면 오답피드백 4개 배열은 빈 배열 [] 로 둔다.
- 배열 각 항목은 1~2문장으로 짧게 쓴다.
"""


def _format_list_block(title: str, items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return f"[{title}] (제공되지 않음)"
    lines = "\n".join(f"- {item}" for item in cleaned)
    return f"[{title}]\n{lines}"


def build_code_analyze_prompt(
    *,
    code: str,
    language: str,
    context: str | None,
    mission_title: str | None,
    mission_description: str | None,
    requirements: list[str],
    success_criteria: list[str],
) -> str:
    """system 규약 + 분석 대상 컨텍스트를 단일 prompt 문자열로 조립한다."""

    context_text = (context or "").strip() or "(제공되지 않음)"
    mission_title_text = (mission_title or "").strip() or "(제공되지 않음)"
    mission_desc_text = (mission_description or "").strip() or "(제공되지 않음)"

    sections = [
        CODE_ANALYZE_SYSTEM_PROMPT,
        "[분석 대상 정보]",
        f"- 언어(language): {language}",
        f"- 기능/문맥(context): {context_text}",
        f"- 미션 제목(missionTitle): {mission_title_text}",
        f"- 미션 설명(missionDescription): {mission_desc_text}",
        _format_list_block("요구사항(requirements)", requirements),
        _format_list_block("완료 기준(successCriteria)", success_criteria),
        "[현재 코드]",
        "```",
        code if code.strip() else "(빈 코드)",
        "```",
        "위 코드와 정보를 바탕으로 규약에 맞는 단일 JSON 객체만 출력하라.",
    ]
    return "\n".join(sections)
