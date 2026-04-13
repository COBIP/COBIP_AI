"""
In-memory 문제 데이터 저장소.
프로토타입 단계에서 DB 대신 사용한다.
향후 DB 연동 시 이 모듈만 교체하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WrongPattern:
    error_type: str          # type_mismatch, missing_semicolon, ...
    pattern: str             # 오답 코드 패턴
    feedback: str            # 한 줄 피드백 메시지


@dataclass
class Problem:
    id: int
    title: str
    description: str
    answer_code: str
    concept: str
    hint: str
    wrong_patterns: list[WrongPattern] = field(default_factory=list)
    explanation_chunks: list[str] = field(default_factory=list)


# ── 문제 데이터 3개 ──────────────────────────────────────────────

PROBLEMS: dict[int, Problem] = {}


def _init_problems() -> None:
    """문제 데이터를 초기화한다."""

    # 문제 1: 문자열 변수 선언
    PROBLEMS[1] = Problem(
        id=1,
        title="문자열 변수 선언",
        description='문자열 "안녕"을 저장하는 변수 a를 선언하세요.',
        answer_code='String a = "안녕";',
        concept="String은 문자열을 저장하는 자료형이다.",
        hint="문자열을 저장할 수 있는 자료형을 떠올려보세요.",
        wrong_patterns=[
            WrongPattern(
                error_type="type_mismatch",
                pattern='int a = "안녕";',
                feedback="타입이 잘못되었습니다. 문자열은 String으로 선언해야 합니다.",
            ),
            WrongPattern(
                error_type="missing_semicolon",
                pattern='String a = "안녕"',
                feedback='세미콜론(;)이 필요합니다. 자바 문장은 세미콜론으로 끝나야 합니다.',
            ),
            WrongPattern(
                error_type="variable_declaration_error",
                pattern='string a = "안녕";',
                feedback="자바에서 문자열 타입은 대문자 S로 시작하는 String입니다.",
            ),
        ],
        explanation_chunks=[
            "String은 문자열을 저장하는 자료형이다.",
            "int는 정수를 저장하는 자료형이다.",
            "문자열은 int 변수에 저장할 수 없다.",
            "세미콜론(;)은 자바 문장의 끝을 나타낸다.",
            "자바에서 String은 대문자 S로 시작한다.",
        ],
    )

    # 문제 2: 정수 변수 선언과 출력
    PROBLEMS[2] = Problem(
        id=2,
        title="정수 변수 선언과 출력",
        description="정수 10을 저장하는 변수 num을 선언하고, 출력하세요.",
        answer_code='int num = 10;\nSystem.out.println(num);',
        concept="int는 정수를 저장하는 자료형이며, System.out.println()으로 값을 출력한다.",
        hint="정수를 저장할 수 있는 자료형과 출력 함수를 생각해보세요.",
        wrong_patterns=[
            WrongPattern(
                error_type="type_mismatch",
                pattern='String num = 10;',
                feedback="타입이 잘못되었습니다. 정수는 int로 선언해야 합니다.",
            ),
            WrongPattern(
                error_type="wrong_output",
                pattern='int num = 10;\nSystem.out.print(num);',
                feedback="println을 사용해야 줄바꿈이 포함된 출력이 됩니다.",
            ),
            WrongPattern(
                error_type="missing_semicolon",
                pattern='int num = 10\nSystem.out.println(num);',
                feedback="첫 번째 줄에 세미콜론(;)이 빠져 있습니다.",
            ),
        ],
        explanation_chunks=[
            "int는 정수를 저장하는 자료형이다.",
            "String은 문자열 전용이므로 정수를 직접 저장하면 타입 오류가 발생한다.",
            "System.out.println()은 값을 출력하고 줄바꿈한다.",
            "System.out.print()는 줄바꿈 없이 출력한다.",
            "변수 선언과 출력은 각각 세미콜론으로 끝나야 한다.",
        ],
    )

    # 문제 3: 두 수의 합 계산
    PROBLEMS[3] = Problem(
        id=3,
        title="두 수의 합 계산",
        description="변수 a에 3, 변수 b에 5를 저장하고, 두 수의 합을 변수 sum에 저장하세요.",
        answer_code='int a = 3;\nint b = 5;\nint sum = a + b;',
        concept="변수에 값을 저장하고, 산술 연산자 +를 이용해 두 값을 더할 수 있다.",
        hint="두 변수를 더할 때 어떤 연산자를 쓰는지 생각해보세요.",
        wrong_patterns=[
            WrongPattern(
                error_type="concept_mismatch",
                pattern='int a = 3;\nint b = 5;\nint sum = a * b;',
                feedback="덧셈에는 + 연산자를 사용해야 합니다. *는 곱셈입니다.",
            ),
            WrongPattern(
                error_type="variable_declaration_error",
                pattern='int a = 3;\nint b = 5;\nsum = a + b;',
                feedback="sum 변수의 타입(int)을 선언해야 합니다.",
            ),
            WrongPattern(
                error_type="type_mismatch",
                pattern='int a = 3;\nint b = 5;\nString sum = a + b;',
                feedback="두 정수의 합은 int 타입이어야 합니다. String이 아닙니다.",
            ),
        ],
        explanation_chunks=[
            "변수에 값을 저장하려면 자료형과 변수명을 선언해야 한다.",
            "int는 정수를 저장하는 자료형이다.",
            "+ 연산자는 두 수를 더한다.",
            "* 연산자는 두 수를 곱한다.",
            "변수를 처음 사용할 때는 반드시 타입을 선언해야 한다.",
            "int sum = a + b; 형태로 연산 결과를 저장할 수 있다.",
        ],
    )


_init_problems()


def get_problem(problem_id: int) -> Problem | None:
    return PROBLEMS.get(problem_id)


def get_all_problems() -> list[Problem]:
    return list(PROBLEMS.values())
