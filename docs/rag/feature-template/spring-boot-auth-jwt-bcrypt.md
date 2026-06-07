# Spring Boot 로그인 — JWT · BCrypt 보안 표준

COBIP 로그인 기능템플릿의 인증·토큰·비밀번호 처리 규칙이다.

## 비밀번호 저장

- 사용자 비밀번호는 **평문으로 절대 저장하지 않는다**
- 회원가입/비밀번호 변경 시 `PasswordEncoder.encode(rawPassword)`로 BCrypt 해시 저장
- 로그인 시 `PasswordEncoder.matches(rawPassword, storedHash)`로 비교
- Spring Boot에서는 `BCryptPasswordEncoder`를 `@Bean`으로 등록해 DI 주입

## JWT accessToken 발급

- 로그인 성공 시 **JWT accessToken**을 발급한다
- `tokenType`은 `"Bearer"`로 고정
- 응답 예시 필드: `accessToken`, `tokenType`, `expiresIn`(초), `user`
- `user` 객체에는 id, email, nickname 등 화면 표시용 최소 정보만 포함 (비밀번호·해시 제외)
- JWT secret/key는 환경변수로 관리하고 소스에 하드코딩하지 않는다

## 인증 실패 처리

- **400 validation error**와 **401 invalid credentials**를 분리한다
- `@Valid` / Bean Validation 위반 → 400, 필드별 오류 메시지
- 사용자 없음 또는 비밀번호 불일치 → 401, 동일한 오류 메시지 (계정 존재 여부 과도 노출 금지)
- 예: `"Invalid email or password"` — 이메일 존재 여부를 구분해 알리지 않는다

## Service 흐름 예

1. `LoginRequest`에서 username/email, password 추출
2. 사용자 조회 (Repository)
3. `PasswordEncoder.matches`로 BCrypt 검증
4. 성공 시 JWT 생성 → `LoginResponse` 반환
5. 실패 시 401에 해당하는 예외 처리

## 기능템플릿 반영 포인트

- requirements: 비밀번호 평문 저장 금지, BCrypt 검증, JWT 발급 요구사항 명시
- apiSpec: 200/400/401 statusCodes, errorResponses 분리
- codeFiles: LoginService에 `getUsername()`/`getPassword()` + PasswordEncoder 사용
- missions: BCrypt 적용, JWT 전환 실습 미션
- interviewQuestions: BCrypt salt, JWT Bearer 헤더, 400 vs 401 차이
