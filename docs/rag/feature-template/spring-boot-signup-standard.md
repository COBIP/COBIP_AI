# Spring Boot 회원가입 기능템플릿 표준

COBIP 기능템플릿에서 **featureName=회원가입**, **framework=Spring Boot** 조합의 기본 구조를 정의한다.

## 기본 메타

| 항목 | 값 |
| --- | --- |
| featureName | 회원가입 |
| framework | Spring Boot |
| language | Java |
| 기본 package | `com.example.auth` 또는 `com.example.user` |
| 기본 endpoint | `POST /api/auth/signup` |

## 표준 codeFiles

```
SignupController.java
SignupService.java
SignupRequest.java
SignupResponse.java
User.java
UserRepository.java
```

## Controller · Service · Repository

- **SignupController**: HTTP 요청 수신, `@PostMapping("/signup")`, Service 위임
- **SignupService**: email 중복 검사, BCrypt 해시, User 저장, SignupResponse 변환
- **UserRepository**: `findByEmail`, `save` — Spring Data JPA

## SignupRequest / SignupResponse

- **SignupRequest**: email, password, nickname (Jakarta Validation: `@Email`, `@NotBlank`, `@Size`)
- **SignupResponse**: userId, email, nickname (비밀번호·해시 제외)
- DTO와 Entity(`User`)는 분리하고 Service에서 매핑

## 비밀번호 처리

- `PasswordEncoder.encode(rawPassword)`로 BCrypt 해시 후 DB 저장
- **평문 password 저장 금지**
- User Entity를 response로 그대로 반환 금지

## apiSpec

```
POST /api/auth/signup
Content-Type: application/json
authenticationRequired: false
requestBody: { email, password, nickname }
responseBody: { success, message, data: { userId, email, nickname } }
statusCodes: 201 (생성 성공), 400 (validation), 409 (duplicate email)
```

## HTTP 응답

| 상황 | status |
| --- | --- |
| 가입 성공 | 201 |
| 입력 검증 실패 | 400 |
| email 중복 | 409 |

## 금지 anti-pattern

- password를 그대로 DB에 저장
- User Entity를 API response에 그대로 노출
- `/api/feature`, `/api/example` placeholder endpoint
- LoginRequest/LoginResponse를 회원가입 기능에 잘못 사용
- Repository 로직을 Controller에 직접 작성
