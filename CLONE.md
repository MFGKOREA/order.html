# CLONE.md — Pickle (Louie), GPT, Grokbot (레미), Claude

How the system runs today. The design and the reason for each choice are in [DESIGN.md](DESIGN.md); the role prompts are in [`prompts/`](prompts/).

## 0. How the four work together

| Who | Does |
|---|---|
| 피클 (Pickle, Louie) | Entrance and exit only: copies one line from an answer file in the Drive folder, writes everything else into `요청.txt`, and passes on what comes back. Prompt: [`prompts/pickle.txt`](prompts/pickle.txt) |
| Hub (`tools/hub.py`, on the store PC, no AI) | Keeps the answer files fresh, answers data requests in milliseconds, queues actions, sends free questions to the right AI, filters personal information, logs everything |
| Claude | Code, automation, documents and analysis, as 결론 / 근거 / 확인 필요 (`prompts/claude.txt`) |
| GPT | Checks Claude's code, automation and documents; answers general questions (`prompts/gpt.txt`) |
| 레미 (Grokbot) | Browser and PC work: does the `접수` lines in `작업.txt` and answers browser questions through `요청.txt` (`prompts/remy.txt`) |

Start:

```
pip install -r requirements.txt
python3 tools/hub.py --drive "<Google Drive>/피클" --ai
```

- `--drive` must be a folder that Google Drive for desktop syncs. Name it `피클`, as the prompt does.
- Paste each file in `prompts/` into that AI's settings once. Pickle's is 7 lines, 186 tokens.
- `--ai` needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` on the PC. Without it, free questions answer `AI 연결 안 됨`.
- Requests can also be typed into the hub's window.
- `python3 tools/hub.py --weekly` prints this week's summary.

Files in the Drive folder:

| File | Written by | Holds |
|---|---|---|
| `재고.txt` `매출.txt` `입고.txt` `BOH.txt` `근무표.txt` `행사.txt` | hub | Every ready-made answer, one topic per file |
| `재고_ㄱ.txt` `재고_ㄴ.txt` … | hub | Inventory split by the item's first consonant (감자튀김 → `재고_ㄱ.txt`), so a one-item question reads one slice |
| `입고_오늘.txt` `입고_내일.txt` `입고_모레.txt` | hub | That day's deliveries |
| `작업.txt` | hub | Every pending action plus the 3 latest finished, e.g. `#3 접수 14:05 발주 브로콜리 2개` |
| `요청.txt` | Pickle, 레미, anyone | One request per line, appended |
| `답.txt` | hub | The latest answer only, under `> 요청` |
| `게시판.txt` | hub | The team's log: status tags, missing or late AIs, rejected answers, code, weekly summaries. Pickle never reads it |

Files in the hub's state folder (`downloads/.hub/`, never synced, never committed):

| File | Holds |
|---|---|
| `actions.jsonl` | Every queued action and its status |
| `inbox.json` | How far `요청.txt` has been read |
| `envelopes.jsonl` | Every request: status changes, who answered, missing or rejected AIs, seconds, cache use |
| `usage.jsonl` | Tokens and cost of each AI answer |
| `alerts.log` | Alerts for 신우님: personal information masked, OpenAI spend |
| `private_terms.txt` | Your own private words to mask, one per line (create it yourself) |

## 1. Messages to Pickle

- No greetings, pleasantries, acknowledgements or status reports. Never use the word `관제`.
- Data answers are one line in a fixed format, with no labels:
  - Inventory: `{품목명}: 예상 O.O개`. No timestamp, no `전산기준`. Estimate = on hand − reserved − (burn rate per hour × hours since snapshot), floored at 0, one decimal.
  - Sales: `{일자} 매장 당일 그로스 세일즈: O,OOO,OOO원 (목표 포캐스트 OOO만 원 대비 OO.O% 달성)`
  - Inbound: `{품목명}: 내일(11/14) 입고 6개`. 오늘, 내일 and 모레 are labelled; other days are just `M/D`; `입고 없음` when nothing is due.
  - Roster: `오늘(11/13) 출근: OP 김민수 09:00~15:00, CL 이지은 15:00~22:00`
  - Promotions: `행사: 런치 세트 20% 할인 (11/10~11/16, 평일 11~14시)`, one line each
  - BOH report:
    ```
    [BOH 리포트 (HH:MM)]
    - 신규 출근/퇴근: OP/CL 이름 (시각 태그)
    - 근무 중: O명
    - 퇴근 완료: O명
    - 특이사항: 없음
    ```
- Actions: `발주 접수 #3: 브로콜리 2개`, `HR 스케줄 확정 접수 #4`, `발주 보류: …`, `등록 안 된 작업: …`
- Analysis answers from Claude, GPT or 레미 are exactly three lines; these are the only answers that carry labels:
  ```
  결론: 다음 주 화요일 양파 20kg 추가 발주
  근거: 재고 13.0개, 모레 2.5kg 입고 (매장 11/13 09:00)
  확인 필요: 없음
  ```

Pickle never formats anything itself: the hub writes every line, and Pickle copies it.

## 2. Requests answered without any AI (~1 ms)

| Request | Answer |
|---|---|
| 매장에 감자튀김 재고 몇개야 | `감자튀김: 예상 20.0개` |
| 지금 현재 그로스세일즈 얼마야 | `2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (…)` |
| 내일 피자치즈 입고 몇개야 | `피자치즈: 내일(11/14) 입고 6개` |
| 오늘 출근 누구? | `오늘(11/13) 출근: OP 김민수 09:00~15:00, CL 이지은 15:00~22:00` |
| 이번 주 행사? | the promotions running this week, one line each |
| 지금 근무 몇명이야 | the BOH report |
| 피클에게 브로컬리 발주 2개 넣어줘 | `발주 접수 #1: 브로콜리 2개`, queued for 레미 |
| HR 스케쥴 확정 눌러줘 | `HR 스케줄 확정 접수 #2`, queued for 레미 |
| 작업 확인 / 발주 몇개 했어 / HR 스케줄 확정됐어? | the task list |
| #1 완료 / #2 실패 로그인 만료 | updates the action (shown in `작업.txt`, not in `답.txt`) |

Also handled: several items or topics in one request ("양파랑 감자튀김 재고"), quantities like `3박스`, `두 박스`, `2.5kg`, dates like `11/20`, "다음 주 행사", "내일 출근 누구".

Rules that keep actions safe:
- **Only listed actions are queued** (발주, HR 스케줄 확정). Other change-making commands answer `등록 안 된 작업: …` and nothing runs. New actions are added in `tools/router.py`.
- **Unclear orders are held, never guessed.** Typos and spacing are matched to the cache's item names (브로컬리 → 브로콜리, 피자 치즈 → 피자치즈); more nicknames go in `ALIASES`.
- **No duplicates.** The same pending action again within 60 s is not queued twice.
- **Questions are never actions.** "발주량?" and "몇 개 발주해야 해?" go to the AIs; "확정됐어?" shows the task list.
- **Each request runs once**, also across restarts; a rewritten `요청.txt` never re-runs old lines.
- **Who can order:** anyone who can edit the Drive folder can queue an order, so share it only with the people and AIs that should.

Try one request without the hub: `python3 tools/router.py "내일 피자치즈 입고 몇개야"`

## 3. Free questions (the AIs)

| Kind | Recognised by | Asked |
|---|---|---|
| Code, automation, documents | 코드, 스크립트, 자동화, 엑셀, 수식, 작성, 초안, 공지문, … | Claude writes, then GPT checks (status [검증중]) |
| Analysis | 분석, 예측, 추천, 발주량, 얼마나, 원인, 비교, … | Claude |
| Checking | 검증, 검토, 맞아, 맞는지, … | GPT |
| Browser work | 세콤, HR, 사이트, 로그인, 화면, … | 레미, by hand |
| Everything else | — | GPT |
| Starts with `[중요]` | — | Claude and GPT at once |

- **Envelope:** each AI gets one JSON envelope (`id`, `날짜`, `요청자`, `대상`, `질문`, `원하는형식`, `출처`, `시각`, `상태`, `자료`, `검토할답`). `자료` holds the cache lines the question touches, each tagged `(출처 시각)`.
- **Format and sources:** an answer must be 결론 / 근거 / 확인 필요. If it states a number or a staff name, 근거 needs `(출처 시각)`, with the source one of HR, 세콤, 웹, POS or 매장. An answer that breaks this is sent back once; if it still breaks it, it is dropped and noted on the board.
- **Deadline:** 10 seconds. A missing AI is noted on the board as `[이름] 응답 없음` and the others carry on. A late answer goes to the board, and Pickle's answer is redone only if the late one disagrees.
- **Disagreement:** when two answers state different numbers or names, both go under 확인 필요 with their sources.
- **Cache:** the same question on the same day reuses the earlier answer, as long as the data it used is unchanged. `[중요]` questions and `모름` answers skip it.
- **레미's answers:** `게시판.txt` shows `→ 레미` questions. 레미 answers with one line in `요청.txt`, e.g. `Q-20261113-004 답: 결론: … / 근거: … (세콤 11/13 14:30) / 확인 필요: …`. Until then Pickle says `접수`.
- **Status tags** on the board: `[대기]` → `[처리중]` → `[검증중]` → `[완료]`.

Settings (environment variables on the PC):

| Variable | Default | What it does |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5-5` | Claude model (runs at low effort) |
| `GPT_MODEL`, `GPT_REASONING_EFFORT` | `gpt-5-mini`, `minimal` | GPT model and reasoning level |
| `OPENAI_MONTHLY_BUDGET` | `5` | USD per month. The daily cap is this ÷ the days in the month. At 80% of the day or the month 신우님 gets an alert; at 100% of the day GPT stops and its work goes to Claude |
| `GPT_PRICE_IN`, `GPT_PRICE_OUT` | `0.25`, `2.00` | USD per million tokens. gpt-5-mini's launch price; set the current one |
| `CLAUDE_PRICE_IN`, `CLAUDE_PRICE_OUT` | `4`, `20` | USD per million tokens. Fast mode is counted double |
| `CLAUDE_FAST`, `GPT_PRIORITY` | off | Paid speed tiers (Claude fast mode: 2x price; OpenAI priority: set its price above) |

The weekly summary (counts, average answer time, failures, spend) is posted on `게시판.txt` on the first check of each new week.

## 4. Personal information filter

Everything written to the Drive folder passes `tools/privacy.py` first: answer files, `답.txt`, `작업.txt` and `게시판.txt`.

- **Masked automatically:** phone numbers, e-mail addresses, resident registration numbers, card and bank account numbers, and apartment units (101동 1203호). They become `[가림]`.
- **Your own words:** list them in `downloads/.hub/private_terms.txt`, one per line, for example a home address or family names. The file is re-read whenever it changes.
- **Alerts:** each hit is shown in the hub's window and logged in `alerts.log`.

Store data such as dates, order numbers, sales and stock passes untouched.

## 5. Shared AI board (Google Docs)

- Doc ID: `123Xl37_ffN18WCPpWas_cn94G4ibAtfeHtWn8IgkiQo`
- Until the hub can write to Google Docs, `게시판.txt` in the Drive folder is the board: status tags, missing AIs and weekly summaries go there.
- The original question-post format is still supported for posts made by hand:
  ```
  ## 질문: [YYYY-MM-DD HH:MM] {질문 내용}
  - 대상: Claude, 그록봇, GPT, 피클(루이)
  - 속도 기준: 단일 3초 내, 2중 전달 10초 안쪽 완료
  [Claude] 답변:
  [GPT] 답변:
  [레미] 답변:
  ```
  ```
  python3 tools/ai_board.py post "질문"      # question post with empty slots
  python3 tools/ai_board.py answer board.txt  # fill empty Claude/GPT slots of the latest question
  python3 tools/ai_board.py relay board.txt   # Pickle message for the latest question
  ```
- 레미 runs inside the Grok Bot app and needs no xAI API key. Nothing here calls xAI.

## 6. Local cache index

| Data | File | Required fields |
|---|---|---|
| Inventory | `downloads/live_inventory_cache.json` | `items[]`: `name`, `on_hand`, `reserved`, `burn_per_hour`, `snapshot_at` (ISO 8601) |
| Staffing (BOH) | `downloads/live_boh_status.json` | `as_of` (HH:MM), `events[]`: `shift` (OP/CL), `name`, `type` (출근/퇴근), `time`; `on_duty`, `off_duty`, `notes` |
| Today's sales | `downloads/live_sales.json` | `date`, `gross_sales` (원), `forecast_manwon` (만 원) |
| Inbound | `downloads/live_inbound.json` | `deliveries[]`: `date` (YYYY-MM-DD), `name`, `qty`, optional `unit` (default 개) |
| Roster | `downloads/live_roster.json` | `shifts[]`: `date` (YYYY-MM-DD), `shift` (OP/CL), `name`, `start`, `end` (HH:MM) |
| Promotions | `downloads/store_promotions.json` | `promotions[]`: `name`, `start`, `end` (YYYY-MM-DD), optional `detail` |
| Recipes | `downloads/line_recipes.json` | (free form) |

Sample files in this format are in `tests/fixtures/`. Without the hub, `python3 tools/pickle_relay.py feed --out-dir <folder> [--watch]` writes the answer files alone.

## 7. Speed and tokens

Measured on the cloud machine with the sample data:

| Step | Time |
|---|---|
| Data question: Pickle reads an answer file | nothing to wait for; a cache change reaches the file in 64 ms median, 101 ms worst |
| Request line in `요청.txt` → answer in `답.txt` | about 50 ms (hub checking every 0.05 s) |
| The router alone | 0.3–1.6 ms per request |
| Free question | the AI's own time, at most 10 s; script overhead 3–5 ms |
| Hub when idle | 0.15 ms per check |

Pickle's tokens per question:
- Counted as prompt + the one file Pickle reads + its answer.
- Measured with GPT's tokenizer as an estimate, on a store with 67 items and 29 deliveries in the week.
- The platform's tool-call overhead is not included.

| Request | Before | Now |
|---|---|---|
| 피클에게 브로컬리 발주 2개 넣어줘 | 380 | 262 |
| 매장에 감자튀김 재고 몇개야 | 967 | 285 |
| 지금 현재 그로스세일즈 얼마야 | 307 | 283 |
| 내일 피자치즈 입고 몇개야 | 676 | 302 |
| HR 스케쥴 확정 눌러줘 | 370 | 248 |
| All five | 2,700 | 1,380 (49% less) |

- The whole inventory list is 734 tokens; one first-consonant slice is 46 on average.
- `입고_내일.txt` is 88 tokens against 438 for the week.
- Every earlier turn of a chat is sent again with each new question, so a fresh Pickle chat each day keeps that from piling up.

Not measured yet:
- Google Drive sync time in both directions, and how often Pickle reads the folder.
- The AIs' real latency and cost (needs keys).
- How long 레미 takes.
