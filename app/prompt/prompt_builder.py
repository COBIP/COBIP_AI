"""
프롬프트 빌더.
RAG로 검색된 context + 사용자 정보를 조합해 LLM 프롬프트를 구성한다.
"""

from __future__ import annotations


def build_prompt(
    retrieved_context: list[str],
    user_code: str,
    question: str,
    problem_title: str,
    problem_description: str,
) -> tuple[str, str]:
    """
    시스템 프롬프트와 유저 프롬프트를 생성한다.

    Returns:
        (system_prompt, user_prompt) 튜플
    """

    context_block = "\n".join(f"- {c}" for c in retrieved_context)

    system_prompt = (
        "너는 자바 프로그래밍을 가르치는 친절한 튜터야.\n"
        "아래 [참고 자료]를 근거로 학생의 질문에 답변해.\n"
        "참고 자료에 없는 내용은 추측하지 말고, 모르면 모른다고 답해.\n"
        "답변은 한국어로, 초보자가 이해할 수 있게 짧고 명확하게 해.\n"
        "코드 예시가 필요하면 간단하게 포함해.\n"
    )

    user_prompt = (
        f"[문제] {problem_title}\n"
        f"{problem_description}\n\n"
        f"[학생이 제출한 코드]\n{user_code}\n\n"
        f"[참고 자료]\n{context_block}\n\n"
        f"[학생 질문]\n{question}\n\n"
        "위 참고 자료를 바탕으로 학생의 질문에 답변해주세요."
    )

    return system_prompt, user_prompt
