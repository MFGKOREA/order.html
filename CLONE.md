# CLONE.md — Relay rules for Pickle (Louie), GPT, Grokbot, Claude

The formatter and checker live in `tools/pickle_relay.py`. Run `python3 tools/pickle_relay.py --help`.

## 1. Messages to the boss's Pickle

- No greetings, pleasantries or filler. Never use the word `관제`.
- No labels or headers such as `결론`, `근거`, `확인필요`.
- Inventory answer: `{품목명}: 예상 O.O개`
  - No timestamp, no `전산기준`.
  - Estimate = on hand − reserved − (burn rate per hour × hours since snapshot), floored at 0, one decimal.
- Sales / forecast:
  `{일자} 매장 당일 그로스 세일즈: O,OOO,OOO원 (목표 포캐스트 OOO만 원 대비 OO.O% 달성)`
- BOH report:
  ```
  [BOH 리포트 (HH:MM)]
  - 신규 출근/퇴근: OP/CL 이름 (시각 태그)
  - 근무 중: O명
  - 퇴근 완료: O명
  - 특이사항: 없음
  ```

## 2. Shared AI board (Google Docs)

- Doc ID: `123Xl37_ffN18WCPpWas_cn94G4ibAtfeHtWn8IgkiQo`
- Question post:
  ```
  ## 질문: [YYYY-MM-DD HH:MM] {질문 내용}
  - 대상: Claude, 그록봇, GPT, 피클(루이)
  - 속도 기준: 단일 3초 내, 2중 전달 10초 안쪽 완료
  ```
- Collect each AI's answer, strip filler and labels, and send only the core data to Pickle.

## 3. Local cache index (1-second answers)

| Data | File | Required fields |
|---|---|---|
| Recipes | `downloads/line_recipes.json` | (free form) |
| Promotions | `downloads/store_promotions.json` | (free form) |
| Inventory | `downloads/live_inventory_cache.json` | `items[]`: `name`, `on_hand`, `reserved`, `burn_per_hour`, `snapshot_at` (ISO 8601) |
| Staffing | `downloads/live_boh_status.json` | `as_of` (HH:MM), `events[]`: `shift` (OP/CL), `name`, `type` (출근/퇴근), `time`; `on_duty`, `off_duty`, `notes` |
| Today's sales | `downloads/live_sales.json` | `date`, `gross_sales` (원), `forecast_manwon` (만 원) |

Sample files in this format are in `tests/fixtures/`.
