# order.html

## BOH 출퇴근 대시보드 위젯 (iOS Scriptable)

매드포갈릭 수원컨벤션센터점 BOH(주방) 직원 + KM의 세콤 지문 출퇴근 현황을
아이폰 홈 화면에 띄우는 Stageshow 벤토 스타일 위젯입니다.

| 파일 | 설명 |
| --- | --- |
| `boh-attendance-widget.js` | Scriptable 위젯 스크립트 (단일 파일) |
| `boh-attendance.json` | 위젯이 불러오는 당일 출퇴근 데이터 (GitHub raw) |
| `boh-attendance.sample.json` | JSON 스키마 예시 |

### 설치
1. Scriptable 앱 → 새 스크립트 → `boh-attendance-widget.js` 내용 붙여넣기 → 저장
2. 앱에서 ▶ 실행하면 Large 미리보기가 바로 열립니다
3. 홈 화면 → 위젯 추가 → Scriptable(Large 권장 / Medium 지원) → Script 선택
4. (선택) 위젯 Parameter: `cream`(발주앱 크림테마) · `medium` · JSON URL 을 공백으로 구분해 입력

### 데이터 갱신
`boh-attendance.json` 을 수정해 커밋하면 위젯이 30분 주기로 자동 반영합니다.
네트워크 실패 시 마지막 성공 캐시 → 내장 Fallback 순으로 안전하게 렌더링됩니다.
`status` 를 비우면 지문/스케줄 시간으로 상태를 자동 판정합니다
(퇴근완료 / 근무중 / 출근미태그 / 퇴근미태그 / 출근예정 / 휴무).
