# Spring Boot JWT 인증 기능템플릿 표준

COBIP 기능템플릿에서 **featureName=JWT 인증** — 로그인 이후 **보호된 API 접근**을 위한 인증/인가 구조를 정의한다.

## 기본 메타

| 항목 | 값 |
| --- | --- |
| featureName | JWT 인증 |
| framework | Spring Boot |
| language | Java |
| package | `com.example.auth`, `com.example.security` |

## 표준 codeFiles

```
JwtTokenProvider.java
JwtAuthenticationFilter.java
SecurityConfig.java
CustomUserDetailsService.java
AuthController.java
LoginRequest.java
LoginResponse.java
```

## JWT 발급 (로그인)

- 로그인 성공 시 **accessToken** 발급
- `tokenType`은 `"Bearer"`
- 클라이언트는 `Authorization: Bearer {accessToken}` 헤더 사용

## 필터 · Provider 흐름

1. **JwtAuthenticationFilter**: 요청 헤더에서 Bearer 토큰 추출
2. **JwtTokenProvider**: 토큰 서명 검증, subject/claims에서 사용자 식별
3. **SecurityContext**에 Authentication 객체 저장
4. **SecurityConfig**: 필터 체인 등록, 공개/보호 URL 구분

## apiSpec 예시

### 로그인 (공개)

```
POST /api/auth/login
authenticationRequired: false
requestBody: { email, password }
responseBody: { accessToken, tokenType, user }
statusCodes: 200, 400, 401
```

### 내 정보 조회 (보호)

```
GET /api/users/me
authenticationRequired: true
requestHeaders: Authorization: Bearer {accessToken}
statusCodes: 200, 401
errorResponses: 401 { "message": "Unauthorized" } — 토큰 만료/위조/누락
```

## 오류 처리

| 상황 | status |
| --- | --- |
| 토큰 유효 | 200 |
| 토큰 만료/위조/누락 | 401 |
| 검증 실패를 200으로 반환 | **금지** |

## 금지 anti-pattern

- accessToken을 평문 로그에 출력
- JWT secret을 코드에 하드코딩 (환경변수 사용)
- Authorization 헤더 없이 보호 API 호출 가능하게 작성
- `/api/feature` placeholder endpoint
- SecurityConfig 없이 Filter만 단독 사용
