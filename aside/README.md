# aside/ — 어사이드 운전 도구

GW Agent(크롬 확장)의 운전 자리를 매장 PC 어사이드가 맡기 위한 코드입니다. 화면을 읽고 입력하는 코드는 label-list 것을 그대로 부릅니다.
설계 [`docs/aside/design-aside-ops.md`](../docs/aside/design-aside-ops.md) · 설치 순서 [`runbook-store-pc.md`](../docs/aside/runbook-store-pc.md) · 검증 결과 [`verify-report.md`](../docs/aside/verify-report.md)

| 파일 | 어디서 도나 | 무엇 |
|---|---|---|
| `desk.html` | 매장 PC 어사이드 탭 (항상 열어 둠) | 책상 화면: "지금 할 일" 한 가지를 보여 줌 |
| `desk-core.js` | 책상 화면 · 시험 | 책상 판단 (순수 함수) |
| `starter.js` | MIS 첫 화면 (어사이드가 실행) | 시작 코드: 읽기 코드·발주 대기 코드를 불러 옴. 섀도면 맞춰 보기까지 |
| `verify-core.js` | 시작 코드 · 도구 · 시험 | 맞춰 보기 · 모양 검사 · 도착 지연 (순수 함수) |
| `selftest.html` · `probe.js` | 매장 PC 어사이드 | 기능 시험 (스스로 채점) |
| `tools/check.mjs` | 클로드 코드 | 시트 사본·상태·기준선·비교·섀도 결과 (건수만 찍음) |
| `test/*.test.mjs` | — | 단위 시험 |
| `test/sim/*.mjs` | — | 가짜 MIS·가짜 시트로 끝까지 돌려 보기 |
| `test/bt/*.mjs` | — | 되돌려 보기: 진짜 자료 · 가상 30일 · AI 가 직접 읽을 때 |

## 지킬 것

- 발주 시트 주소·가게 키·시트 사본은 이 저장소에 두지 않습니다. `tools/check.mjs snap` 은 저장소 안에 저장하기를 거절합니다.
- `starter.js` 는 로그인된 MIS 화면 안에서 돕니다. 고칠 때는 시험(`test/sim/e2e-starter.mjs`)을 먼저 돌립니다.
- 언제 무엇을 받을지의 규칙은 여기 새로 쓰지 않습니다. label-list 의 `gw-agent/auto.js` · `periodic.js` · `gw-plan.json` 이 원본입니다.

## 시험

```
# label-list 사본이 있어야 함 (기본: ../mfgkorea/label-list · 아니면 LABEL_LIST=/경로)
node --test aside/test/*.test.mjs
node aside/test/sim/e2e-starter.mjs
node aside/test/sim/e2e-desk.mjs
node aside/test/sim/e2e-selftest.mjs
node aside/test/bt/schedule.mjs --days 30 --seed 1
```
