# COBIP apiSpec 확장 필드 작성 규칙

COBIP 기능템플릿 `apiSpec[]` 항목은 기본 필드 외 아래 **확장 필드**를 포함하면 품질이 안정적이다.

## 확장 필드 목록

| 필드 | 설명 |
| --- | --- |
| authenticationRequired | 이 API 호출 전 인증 필요 여부 (로그인 API는 false) |
| requestHeaders | Content-Type 등 필요 헤더 |
| requestFields | 요청 본문 필드 설명 배열 |
| responseFields | 응답 본문 필드 설명 배열 |
| statusCodes | 가능한 HTTP 상태 코드와 의미 |
| errorResponses | 오류별 응답 예시 |
| frontendNotes | 프론트엔드 연동 시 주의사항 |

## Spring Boot 로그인 API 기준 예

```json
{
  "apiName": "로그인",
  "method": "POST",
  "endpoint": "/api/auth/login",
  "description": "이메일(또는 username)과 비밀번호로 인증 후 JWT accessToken을 발급한다.",
  "authenticationRequired": false,
  "requestHeaders": {
    "Content-Type": "application/json"
  },
  "requestBody": {
    "email": "user@example.com",
    "password": "secret123"
  },
  "requestFields": [
    {"name": "email", "type": "string", "required": true, "description": "로그인 이메일"},
    {"name": "password", "type": "string", "required": true, "description": "비밀번호"}
  ],
  "responseBody": {
    "accessToken": "eyJhbG...",
    "tokenType": "Bearer",
    "user": {"id": 1, "email": "user@example.com"}
  },
  "responseFields": [
    {"name": "accessToken", "type": "string", "description": "JWT access token"},
    {"name": "tokenType", "type": "string", "description": "Bearer 고정"},
    {"name": "user", "type": "object", "description": "로그인 사용자 요약 정보"}
  ],
  "status": 200,
  "statusCodes": [
    {"code": 200, "description": "로그인 성공"},
    {"code": 400, "description": "입력 검증 실패"},
    {"code": 401, "description": "자격증명 불일치"}
  ],
  "errorResponses": [
    {"status": 400, "body": {"message": "Validation failed", "fieldErrors": []}},
    {"status": 401, "body": {"message": "Invalid email or password"}}
  ],
  "frontendNotes": "성공 시 accessToken을 localStorage 또는 secure storage에 저장하고 Authorization: Bearer 헤더로 후속 API에 전달한다."
}
```

## username/password 변형

email 대신 username을 쓰는 템플릿에서는 requestFields·requestBody의 필드명만 username으로 바꾸고 endpoint·status 구조는 동일하게 유지한다.

## 금지 사항

- endpoint에 `/api/feature`, `/api/example` 사용 금지
- statusCodes에 200만 넣고 400/401 누락 금지
- authenticationRequired를 로그인 API에 true로 설정 금지
