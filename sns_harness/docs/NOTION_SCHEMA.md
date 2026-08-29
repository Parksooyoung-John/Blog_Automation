# Notion SNS 승인 큐 스키마

기존 블로그 발행 DB와 분리된 데이터베이스를 만들고 통합에 연결한 후 ID를
`NOTION_SNS_DATABASE_ID`에 저장합니다. 속성명과 유형은 정확히 일치해야 합니다.

| 속성 | Notion 유형 | 용도 |
|---|---|---|
| 이름 | Title | 블로그 제목 |
| 상태 | Select | 초안, 승인, 게시중, 게시완료, 보류, 오류 |
| 원문URL | URL | 숫자형 canonical URL |
| TistoryID | Text | 중복 방지 키 |
| 원문발행일 | Date | 신규 글 판정 |
| 원문해시 | Text | 수정 감지 |
| 형식 | Select | single, thread |
| 첫게시물 | Text | 루트 게시물 |
| 답글1~답글4 | Text | 연속 답글 |
| 주제태그 | Text | `#` 없는 Threads 주제 태그 |
| 예약시각 | Date | 비어 있으면 다음 기본 슬롯 배정 |
| 게시시각 | Date | 실제 완료 시각 |
| ThreadsIDs | Text | 순서가 보존된 JSON 배열 |
| 오류 | Text | 마지막 검수·게시 오류 |
| 재시도횟수 | Number | 실패 횟수 |

`예약시각`에는 시간과 시간대를 포함하도록 설정합니다. 운영자는 초안 필드를 직접 수정할 수
있지만 480자를 넘기면 Harness 검증에서 게시를 중단합니다.
