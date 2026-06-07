# COBIP 기능템플릿 9개 섹션 작성 규칙

COBIP `/ai/feature-template/generate` 응답은 아래 9개 top-level 섹션을 **schema 키 이름 그대로** 포함해야 한다.

## 1. overview

- **담을 정보**: featureName, purpose, useCases, resultDescription, techStack, learningGoals
- **형식**: purpose/resultDescription은 1~3문장, useCases·learningGoals는 짧은 문자열 배열
- **로그인 예시**: "이메일·비밀번호로 인증하고 JWT accessToken을 발급한다", techStack에 Java·Spring Boot·JWT·BCrypt

## 2. requirements

- **담을 정보**: requirementId, name, description, inputValue, processCondition, successResult, failureResult, priority, relatedScreenOrApi
- **형식**: 최소 3개, HIGH/MEDIUM/LOW priority 문자열
- **로그인 예시**: 입력 검증(R-001), BCrypt 검증(R-002), JWT 발급(R-003); relatedScreenOrApi는 `POST /api/auth/login`

## 3. flow

- **담을 정보**: steps(문자열 배열), layers(layer+role 객체 배열)
- **형식**: steps 5개 이상, layers에 Controller/Service/Repository/DB
- **로그인 예시**: "1) 클라이언트 POST /api/auth/login" → "5) LoginResponse 반환"

## 4. apiSpec

- **담을 정보**: apiName, method, endpoint, description, requestBody, responseBody, status 및 확장 필드
- **형식**: method는 POST/GET 등, status는 정수, requestBody/responseBody는 JSON 객체
- **로그인 예시**: POST /api/auth/login, email/password 요청, accessToken/tokenType/user 응답

## 5. codeFiles

- **담을 정보**: fileName, filePath, role, language, content
- **형식**: includeCode=true일 때 최소 4개, role은 "REST API 컨트롤러", "비즈니스 로직 서비스", "요청 DTO", "응답 DTO" 등
- **로그인 예시**: LoginController, LoginService, LoginRequest, LoginResponse — package `com.example.auth` 통일

## 6. basicQuestions

- **담을 정보**: questionId, type, question, choices, answer, explanation, relatedSection, difficulty
- **형식**: 최소 3개, type은 short_answer/multiple_choice 등 허용 enum
- **로그인 예시**: "Controller와 Service 역할 차이?", "BCrypt를 쓰는 이유?"

## 7. missions

- **담을 정보**: missionId, title, description, missionType, requirements, successCriteria, relatedRequirements, difficulty
- **형식**: description 첫 줄에 "미션 목표:" 포함, 최소 2개
- **로그인 예시**: JWT 적용 미션, Bean Validation 추가 미션

## 8. interviewQuestions

- **담을 정보**: questionId, question, keyPoints, sampleAnswer, relatedSection
- **형식**: 최소 3개, keyPoints는 문자열 배열
- **로그인 예시**: "로그인 흐름 설명", "400과 401 차이", "비밀번호 저장 방식"

## 9. nextRecommendations

- **담을 정보**: featureName, reason, expectedLearning, priority
- **형식**: 최소 3개, priority는 1부터 정수
- **로그인 예시**: 회원가입, JWT 갱신, 권한/인가 기능 추천

## 공통 규칙

- placeholder endpoint(`/api/feature`) 사용 금지
- RAG context가 있으면 requirements·apiSpec·flow·codeFiles에 우선 반영
- enum·타입은 schema 정의를 따른다 (priority 문자열, apiSpec.status 정수)
