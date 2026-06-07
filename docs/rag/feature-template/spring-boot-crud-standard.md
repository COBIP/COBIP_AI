# Spring Boot CRUD 기능템플릿 표준 (게시글 예시)

COBIP 기능템플릿에서 **범용 CRUD** 패턴을 정의한다. 기본 예시 도메인은 **게시글 CRUD**이다.

## 기본 메타

| 항목 | 값 |
| --- | --- |
| featureName | 게시글 CRUD |
| framework | Spring Boot |
| language | Java |
| 기본 package | `com.example.post` |

## REST endpoint 패턴

```
POST   /api/posts           — 생성(Create)
GET    /api/posts           — 목록 조회(Read List)
GET    /api/posts/{postId}  — 단건 조회(Read Detail)
PUT    /api/posts/{postId}  — 수정(Update)
DELETE /api/posts/{postId}  — 삭제(Delete)
```

## 표준 codeFiles

```
PostController.java
PostService.java
PostRepository.java
Post.java
PostCreateRequest.java
PostUpdateRequest.java
PostResponse.java
```

## 계층 역할

| 계층 | 역할 |
| --- | --- |
| PostController | HTTP 요청/응답, status code 반환 |
| PostService | 비즈니스 로직, Entity ↔ DTO 변환 |
| PostRepository | DB 접근 (JpaRepository) |
| Post | JPA Entity |
| PostCreateRequest / PostUpdateRequest | 요청 DTO |
| PostResponse | 응답 DTO |

## CRUD 동작 규칙

- **Create**: PostCreateRequest → Entity 저장 → PostResponse 반환 (201)
- **Read List**: 전체 또는 페이징 목록 → PostResponse 배열 (200)
- **Read Detail**: postId 조회, 없으면 404 NOT_FOUND
- **Update**: postId 조회 후 제목/내용 수정 (200)
- **Delete**: postId 조회 후 삭제 (204 또는 200)

## apiSpec 확장 필드

- `authenticationRequired`: 기능에 따라 true/false
- `requestHeaders`: Content-Type: application/json
- `statusCodes`: 200, 201, 400, 404
- `errorResponses`: NOT_FOUND `{ "message": "Post not found", "postId": ... }`
- `frontendNotes`: 목록/상세/수정/삭제 후 화면 갱신 전략 (refetch, optimistic update 등)

## 금지 anti-pattern

- 모든 CRUD를 하나의 메서드로 처리
- DTO 없이 Entity를 request/response에 직접 노출
- `/api/feature` placeholder endpoint
- postId 없이 수정/삭제 처리
- Repository 로직을 Controller에 직접 작성
