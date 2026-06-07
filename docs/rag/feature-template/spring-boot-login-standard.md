# Spring Boot 로그인 기능템플릿 표준

COBIP 기능템플릿에서 **featureName=로그인**, **framework=Spring Boot** 조합의 기본 구조를 정의한다.

## 기본 메타

| 항목 | 값 |
| --- | --- |
| featureName | 로그인 |
| framework | Spring Boot |
| language | Java |
| 기본 package | `com.example.auth` |
| 기본 endpoint | `POST /api/auth/login` |

## Controller

- 클래스명: `LoginController`
- 패키지: `com.example.auth`
- 경로: `@RequestMapping("/api/auth")` + `@PostMapping("/login")`
- 메서드 시그니처 예:

```java
@PostMapping("/login")
public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {
    return ResponseEntity.ok(loginService.login(request));
}
```

## Service

- 클래스명: `LoginService`
- 패키지: `com.example.auth`
- `LoginRequest`를 받아 자격증명 검증 후 `LoginResponse` 반환
- 비밀번호 검증은 `PasswordEncoder.matches` 사용 (평문 저장 금지)

## DTO

| 파일 | 역할 | 필드 예시 |
| --- | --- | --- |
| LoginRequest | 요청 DTO | username/password 또는 email/password |
| LoginResponse | 응답 DTO | accessToken, tokenType, user(id, email 등) |

초급자 템플릿에서는 **class DTO + getter/setter**를 권장한다. Service에서는 `request.getUsername()`, `request.getPassword()` 형태로 접근한다.

## codeFiles 규칙

동일 기능의 Java 파일은 **같은 package와 filePath**를 유지해야 한다.

```
src/main/java/com/example/auth/LoginController.java
src/main/java/com/example/auth/LoginService.java
src/main/java/com/example/auth/LoginRequest.java
src/main/java/com/example/auth/LoginResponse.java
```

각 파일 content의 `package` 선언도 `com.example.auth`로 통일한다.

## HTTP 응답

| 상황 | status | 설명 |
| --- | --- | --- |
| 로그인 성공 | 200 | accessToken, tokenType(Bearer), user 정보 |
| 입력 검증 실패 | 400 | Bean Validation 위반 |
| 자격증명 불일치 | 401 | 이메일/비밀번호 오류 (계정 존재 여부 과도 노출 금지) |

## 금지 endpoint

- `/api/feature`, `/api/example`, `/api/login`(단독) 사용 금지
- canonical endpoint는 반드시 `/api/auth/login`
