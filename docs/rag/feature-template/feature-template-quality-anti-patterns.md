# COBIP 기능템플릿 품질 Anti-Pattern (금지 규칙)

LLM 생성 결과와 normalizer 보정 후에도 아래 패턴이 남으면 **품질 결함**으로 간주한다.

## Endpoint 금지

| 금지 | 대체 |
| --- | --- |
| `/api/feature` | `/api/auth/login` |
| `/api/example` | `/api/auth/login` |
| `/api/login` (단독, auth prefix 없음) | `/api/auth/login` |
| `POST /api/feature` | `POST /api/auth/login` |

requirements, flow.steps, apiSpec, basicQuestions, missions, interviewQuestions 문자열 전체에 적용한다.

## Package / Path 금지

- `com.example.login`과 `com.example.auth` **혼용 금지**
- canonical package: `com.example.auth`
- filePath와 content의 `package` 선언 불일치 금지
- LoginResponse.java에 package 선언 누락 금지

## DTO 접근 방식 금지

- LoginRequest가 **class DTO**인데 Service에서 `request.username()` (record 접근자) 사용 금지
- class DTO → `request.getUsername()`, `request.getPassword()` 사용
- record DTO → `request.username()`, `request.password()` 사용
- **한 기능 내에서 class/record 혼용 금지** (COBIP 초급 템플릿은 class + getter 권장)

## codeFiles role 금지

| 파일 | 금지 role | 올바른 role |
| --- | --- | --- |
| LoginRequest.java | 데이터 접근 | 요청 DTO |
| LoginResponse.java | 데이터 접근 | 응답 DTO |
| LoginController.java | (모호) | REST API 컨트롤러 |
| LoginService.java | (모호) | 비즈니스 로직 서비스 |

## 코드 placeholder 금지

- `TODO`, `생략`, `...`, `placeholder`, `실제 동작 가능한 코드 문자열` 같은 stub 문구 금지
- import·핵심 메서드·검증 로직이 없는 빈 클래스만 나열 금지

## 섹션 간 불일치 금지

- apiSpec endpoint와 requirements.relatedScreenOrApi 불일치
- flow.steps의 endpoint와 apiSpec.endpoint 불일치
- codeFiles LoginController의 `@PostMapping` 경로와 apiSpec endpoint 불일치

## LLM full-first 최소 codeFiles (Spring Boot 로그인)

includeCode=true일 때 아래 4개 파일이 같은 package로 존재해야 한다.

- LoginController.java
- LoginService.java
- LoginRequest.java
- LoginResponse.java

Controller → Service → DTO 호출 흐름이 컴파일 가능해야 한다.
