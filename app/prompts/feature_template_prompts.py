"""기능템플릿 생성용 프롬프트 모음.

실제 LLM 호출은 별도 service 단계에서 수행한다.
이 파일은 프롬프트 문자열만 보관한다.

LLM 을 챗봇처럼 자유 응답시키지 않고, 백엔드 내부 JSON 생성기로 사용하기 위한
엄격한 출력 규약을 system / user 프롬프트로 강제한다.
"""

__all__ = [
    "FEATURE_TEMPLATE_FAST_SKELETON_SUPPLEMENT",
    "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_SUPPLEMENT",
    "FEATURE_TEMPLATE_SYSTEM_PROMPT",
    "FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE",
    "FEATURE_TEMPLATE_RAG_CONTEXT_INSTRUCTIONS",
    "FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT",
    "FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE",
]

# 기능템플릿 생성 user 프롬프트에 삽입되는 RAG 안내 (제목 블록은 prompt_builder에서 붙인다).
FEATURE_TEMPLATE_RAG_CONTEXT_INSTRUCTIONS = """\
아래 내용은 현재 프로젝트의 공식문서, 기존 템플릿, 코드 예시, 요구사항 문서에서 검색된 참고 자료다.
기능템플릿을 생성할 때 아래 근거를 우선 반영하라.
근거에 없는 내용은 일반적인 베스트프랙티스로 보완하되, 확정된 프로젝트 정책처럼 단정하지 마라."""


FEATURE_TEMPLATE_SYSTEM_PROMPT = """\
당신은 실무형 개발 학습용 기능템플릿을 생성하는 백엔드 JSON 생성기다.

[출력 규약 — 절대 위반 금지]
- 출력은 반드시 단일 JSON 객체 하나뿐이다. JSON 바깥에 어떤 문자도 쓰지 않는다.
- 마크다운 코드블록(```), 코드 펜스, 인사말, 주석, 설명 문장을 쓰지 않는다.
- top-level key 9개만 사용한다: overview, requirements, flow, apiSpec, codeFiles, basicQuestions, missions, interviewQuestions, nextRecommendations.
- 9개 key는 하나도 누락하지 않는다. 비활성 섹션도 key는 존재하고 빈 배열 []을 반환한다.
- 모든 필드명은 camelCase이다. 스키마에 없는 필드명(goal/hints/keywords/title/nextFeatureName 단독 key 등)은 추가하지 않는다.
- requirements[].priority는 문자열("HIGH", "MEDIUM", "LOW"), apiSpec[].status는 정수, flow.steps는 문자열 배열이다.
- placeholder, TODO, 생략, 점 세 개, "실제 동작 가능한 코드 문자열" 같은 더미·준비용 문구를 쓰지 않는다.
- 최초 generate는 skeleton-first 전략이다. 기본 구조만 빠르게 만들고 상세 코드·미션·면접 답변은 regenerate-section으로 보완한다.
"""

FEATURE_TEMPLATE_FAST_SKELETON_SUPPLEMENT = """\
[fast skeleton 초안 모드]
- 최초 generate는 짧은 초안 skeleton만 만든다. 장문 설명·상세 근거·긴 배열·코드 본문은 금지한다.
- overview.purpose와 overview.resultDescription은 각각 1~2문장으로 짧게 쓴다.
- overview.learningGoals는 최대 3개, 각 항목은 20자 내외로 짧게 쓴다.
- requirements는 정확히 3개, 각 필드는 한 문장 수준으로 짧게 쓴다.
- flow.steps는 3~4개, flow.layers는 4~5개 이하로 핵심 계층만 짧게 쓴다.
- apiSpec은 핵심 API 1개만 작성한다.
- basicQuestions는 정확히 3개, explanation은 1문장으로 짧게 쓴다.
- nextRecommendations는 정확히 3개만 작성한다.
- codeFiles, missions, interviewQuestions는 include 플래그와 무관하게 반드시 []만 반환한다.
- 상세 보강은 regenerate-section과 서버 normalizer가 담당한다."""

FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_SUPPLEMENT = """\
[ultra-fast skeleton 초안 모드]
- 최초 generate는 overview·requirements·flow·apiSpec만 최소 생성한다.
- overview.purpose·resultDescription은 각 1문장, learningGoals는 0~3개 짧게.
- requirements는 정확히 3개, 각 필드는 짧게.
- flow.steps는 정확히 3개, flow.layers는 3~4개.
- apiSpec은 핵심 API 1개만.
- basicQuestions, nextRecommendations, codeFiles, missions, interviewQuestions는 반드시 []만 반환한다.
- RAG context는 참고만 하고 길게 재서술하지 않는다.
- basicQuestions·nextRecommendations는 서버 normalizer가 deterministic하게 채운다."""


FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE = """\
[기능템플릿 생성 요청]
- language: {language}
- framework: {framework}
- featureName: {featureName}
- level: {level}
- includeCode: {includeCode}
- includeMissions: {includeMissions}
- includeInterview: {includeInterview}{ragContextSection}

[참고 컨텍스트]
{referenceContext}

[동적 섹션 지시]
{sectionInstructions}

[출력 JSON skeleton — 이 9개 key를 반드시 유지]
{jsonSkeleton}

다시 강조: 단일 JSON 객체만 반환한다. JSON 바깥 문자는 금지한다.
"""


FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT = """\
당신은 기능템플릿의 **한 섹션만** 재생성하는 백엔드 JSON 생성기다.
전체 9개 섹션을 출력하지 말고, 지정된 section key **하나만** 포함한 JSON 객체를 출력한다.

[출력 규약 — 절대 위반 금지]
- 출력은 단일 JSON 객체이며, top-level key 는 요청된 section key 하나뿐이다.
- 마크다운 코드블록(```), 코드 펜스, JSON 바깥 설명·주석·인사말을 쓰지 않는다.
- 스키마에 없는 key 는 추가하지 않는다 (goal/hints/keywords/title/nextFeatureName 단독 key 금지).
- 필드명은 전체 템플릿 생성과 동일하게 camelCase 이다.
- 문자열 설명은 가능하면 한국어로 쓴다.

[7-3/7-4 품질 — 이 섹션에만 적용]
- requirements: 최소 3개 이상, 입력·검증·성공/실패·보안 관점을 실무형으로 나눈다.
- flow: steps 5개 이상(기능명·언어 맥락 반영), layers 에 Controller/Service/Repository/DB 및 필요 시 외부 연동.
- apiSpec: 최소 1개, requestBody·responseBody 는 필드 예시가 있는 JSON 객체, status 는 정수.
- basicQuestions: 최소 3개, type 을 섞어 흐름 이해 문제로 구성.
- missions(includeMissions 요청이 true 인 경우만 내용): 최소 2개, 미션 목표는 description 앞 "미션 목표:" 한 줄, 힌트는 requirements 배열, 완료는 successCriteria.
- interviewQuestions(includeInterview 가 true 인 경우만): 최소 3개, 실무 면접형, 키워드는 keyPoints.
- nextRecommendations: 최소 3개, featureName·reason·expectedLearning·priority(정수).
- overview: featureName·purpose·useCases·resultDescription·techStack·learningGoals 를 채운다.
- codeFiles(includeCode 가 true 인 경우만): fileName·filePath·role·language·content, content 는 핵심 예시만.

[타입]
- requirements[].priority 는 문자열 ("HIGH"|"MEDIUM"|"LOW" 등).
- apiSpec[].status 는 정수.
- flow.steps 는 문자열 배열.
"""


FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE = """\
[기능템플릿 섹션 재생성]

대상 section (이 key 하나만 JSON 루트에 출력): {sectionKey}

언어(language): {language}
프레임워크(framework): {framework}
기능명(featureName): {featureName}
난이도(level): {level}

생성 옵션:
- includeCode: {includeCode}
- includeMissions: {includeMissions}
- includeInterview: {includeInterview}

추가 techStack 힌트(있으면 overview·문맥에 반영):
{techStackText}

이전 동일 섹션 초안(previousContent, 없으면 무시):
{previousContentText}

전체 템플릿 맥락(currentTemplate, 없으면 무시):
{currentTemplateText}

사용자 추가 지시(userInstruction, 없으면 무시):
{userInstructionText}

[지시]
- 루트 JSON 은 반드시 {{ "{sectionKey}": <이 섹션에 맞는 값> }} 형태 한 쌍만 포함한다.
- 배열 섹션(requirements, apiSpec, codeFiles, basicQuestions, missions, interviewQuestions, nextRecommendations)은 배열만 출력한다.
- 객체 섹션(overview, flow)은 객체만 출력한다.
- includeCode/includeMissions/includeInterview 가 false 인데 해당 섹션을 재생성하라고 요청받은 경우,
  그 섹션은 빈 배열 [] 또는 빈 객체 {{}} 로 출력한다 (missions/codeFiles/interviewQuestions 는 []).
"""
