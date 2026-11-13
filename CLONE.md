# CLONE.md — Pickle (Louie), GPT, Grokbot (레미), Claude

## 0. How the four work together

| Who | Does |
|---|---|
| 피클 (Pickle, Louie) | Talks to the boss. Answers by copying one line from a file in the Drive folder; passes everything else on through `요청.txt`. Instructions: [`PICKLE_PROMPT.txt`](PICKLE_PROMPT.txt) |
| Hub (`tools/hub.py`, runs on the store PC, no AI) | Keeps the answer files fresh, answers requests in milliseconds, queues actions, asks Claude/GPT the rest |
| Claude, GPT | Free-form questions (hub `--ai`, needs API keys) |
| 레미 (Grokbot) | PC and browser work: does the `접수` lines in `작업.txt`, then writes `#번호 완료` (or `#번호 실패 사유`) into `요청.txt` |

Start:

```
pip install -r requirements.txt
python3 tools/hub.py --drive "<Google Drive>/피클" --ai
```

- `--drive` must be a folder that Google Drive for desktop syncs; name it `피클`, as the prompt does.
- Paste `PICKLE_PROMPT.txt` into Pickle's instructions.
- Drop `--ai` to run without API keys; free questions then answer `AI 연결 안 됨`.
- Requests can also be typed straight into the hub's window.

Files in the Drive folder:

| File | Written by | Holds |
|---|---|---|
| `재고.txt` `매출.txt` `입고.txt` `BOH.txt` | hub | Every ready-made answer, one topic per file |
| `재고_ㄱ.txt` `재고_ㄴ.txt` … | hub | Inventory split by the item's first consonant (감자튀김 → `재고_ㄱ.txt`), so a one-item question reads one slice |
| `입고_오늘.txt` `입고_내일.txt` `입고_모레.txt` | hub | That day's deliveries |
| `작업.txt` | hub | Every pending action plus the 3 latest finished, e.g. `#3 접수 14:05 발주 브로콜리 2개` |
| `요청.txt` | Pickle, 레미, anyone | One request per line, appended |
| `답.txt` | hub | The latest answer only, under `> 요청`. 레미's `#3 완료` updates show in `작업.txt` and never replace it |

## 1. Messages to Pickle

- No greetings, pleasantries or filler. Never use the word `관제`.
- No labels or headers such as `결론`, `근거`, `확인필요`.
- Inventory: `{품목명}: 예상 O.O개`
  - No timestamp, no `전산기준`.
  - Estimate = on hand − reserved − (burn rate per hour × hours since snapshot), floored at 0, one decimal.
- Sales / forecast:
  `{일자} 매장 당일 그로스 세일즈: O,OOO,OOO원 (목표 포캐스트 OOO만 원 대비 OO.O% 달성)`
- Inbound: `{품목명}: 내일(11/14) 입고 6개`
  - Today, tomorrow and the day after are labelled 오늘, 내일, 모레; other days are just `M/D`.
  - `입고 없음` when nothing is due.
- BOH report:
  ```
  [BOH 리포트 (HH:MM)]
  - 신규 출근/퇴근: OP/CL 이름 (시각 태그)
  - 근무 중: O명
  - 퇴근 완료: O명
  - 특이사항: 없음
  ```
- Actions: `발주 접수 #3: 브로콜리 2개`, `HR 스케줄 확정 접수 #4`, `발주 보류: …`, `등록 안 된 작업: …`

Pickle never formats anything itself: the hub writes every line in these formats, and Pickle copies it.

## 2. Requests the hub understands (no AI, ~1 ms)

| Request | Answer |
|---|---|
| 매장에 감자튀김 재고 몇개야 | `감자튀김: 예상 20.0개` |
| 지금 현재 그로스세일즈 얼마야 | `2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (…)` |
| 내일 피자치즈 입고 몇개야 | `피자치즈: 내일(11/14) 입고 6개` |
| 지금 근무 몇명이야 | the BOH report |
| 피클에게 브로컬리 발주 2개 넣어줘 | `발주 접수 #1: 브로콜리 2개`, queued for 레미 |
| HR 스케쥴 확정 눌러줘 | `HR 스케줄 확정 접수 #2`, queued for 레미 |
| 작업 확인 | the latest actions |
| #1 완료 / #2 실패 로그인 만료 | updates the action |
| anything else | the fastest AI's first useful line (`--ai`) |

Also handled: several items or topics in one request ("양파랑 감자튀김 재고", "감자튀김 재고랑 내일 입고"), quantities like `3박스`, `두 박스`, `2.5kg`, and dates like `11/20`.

Rules that keep actions safe:
- **Only listed actions are queued** (발주, HR 스케줄 확정). Any other command answers `등록 안 된 작업: …` and nothing runs. New actions are added in `tools/router.py`.
- **Unclear orders are held, never guessed.** An order whose item or quantity is unclear answers `발주 보류: …`. Typos and spacing are matched to the cache's item names: 브로컬리 → 브로콜리, 피자 치즈 → 피자치즈. More nicknames go in `ALIASES`.
- **No duplicates.** The same pending action again within 60 s is not queued twice.
- **Questions are never actions** ("발주 몇개 했어", "확정됐어?").
- **Each request runs once.** Every line of `요청.txt` is handled once, also across restarts, and a rewritten file never re-runs old lines. Lines already there when the hub first starts are treated as history.
- **Who can order:** anyone who can edit the Drive folder can queue an order, so share it only with the people and AIs that should.

Try one request without the hub: `python3 tools/router.py "내일 피자치즈 입고 몇개야"`

## 3. Shared AI board (Google Docs)

- Doc ID: `123Xl37_ffN18WCPpWas_cn94G4ibAtfeHtWn8IgkiQo`
- Question post:
  ```
  ## 질문: [YYYY-MM-DD HH:MM] {질문 내용}
  - 대상: Claude, 그록봇, GPT, 피클(루이)
  - 속도 기준: 단일 3초 내, 2중 전달 10초 안쪽 완료
  ```
- Each question gets one answer slot per AI, directly below the header:
  ```
  [Claude] 답변:
  [GPT] 답변:
  [레미] 답변:
  ```
  - `Claude` and `GPT` are filled automatically (`tools/ai_board.py`).
  - `레미` (Grokbot) runs inside the Grok Bot app and needs no xAI API key. It does PC and browser work, and fills its own slot when 신우님 says "게시판 확인". The script never calls xAI and leaves this slot blank.
  - An answer may run over several lines; it ends at the next slot or the next `## 질문:`.
- Collect each AI's answer, strip filler and labels, drop duplicate lines, skip empty slots, and send only the core data to Pickle.

```
python3 tools/ai_board.py post "질문"      # question post with empty slots
python3 tools/ai_board.py answer board.txt  # fill empty Claude/GPT slots of the latest question
python3 tools/ai_board.py relay board.txt   # Pickle message for the latest question
python3 tools/ai_board.py ask "질문"        # answer one question now; lines stream as they arrive
python3 tools/ai_board.py serve             # stays running, one question per line
```

- Keys: `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` on the machine that runs the script. In a Claude cloud session, a network secret for `api.openai.com` works for GPT; Anthropic keys cannot be saved there.
- Models: `CLAUDE_MODEL` (default `claude-opus-5-5`, low effort), `GPT_MODEL` (default `gpt-5-mini`, minimal reasoning).
- Speed check is printed to stderr: each AI's first useful line ≤ 3 s, all AIs done ≤ 10 s.

## 4. Local cache index

| Data | File | Required fields |
|---|---|---|
| Recipes | `downloads/line_recipes.json` | (free form) |
| Promotions | `downloads/store_promotions.json` | (free form) |
| Inventory | `downloads/live_inventory_cache.json` | `items[]`: `name`, `on_hand`, `reserved`, `burn_per_hour`, `snapshot_at` (ISO 8601) |
| Staffing | `downloads/live_boh_status.json` | `as_of` (HH:MM), `events[]`: `shift` (OP/CL), `name`, `type` (출근/퇴근), `time`; `on_duty`, `off_duty`, `notes` |
| Today's sales | `downloads/live_sales.json` | `date`, `gross_sales` (원), `forecast_manwon` (만 원) |
| Inbound | `downloads/live_inbound.json` | `deliveries[]`: `date` (YYYY-MM-DD), `name`, `qty`, optional `unit` (default 개) |

Sample files in this format are in `tests/fixtures/`. Without the hub, `python3 tools/pickle_relay.py feed --out-dir <folder> [--watch]` writes the four answer files alone.

## 5. Speed

Measured on the cloud machine with the sample data:

| Step | Time |
|---|---|
| Data question: Pickle reads a topic file | nothing to wait for at question time; a cache change reaches the file in 64 ms median, 101 ms worst |
| Request line in `요청.txt` → answer in `답.txt` (hub running) | 26 ms median, 54 ms worst |
| The router alone | 0.3–1.6 ms per request |
| Free question with `--ai` | 3–5 ms of script time, then the fastest AI's time to its first line |
| Hub when idle | 0.15 ms per check, every 0.05 s |

Token cost for Pickle, per question:
- The cost is prompt + the one file Pickle reads + its one-line answer.
- Measured with GPT's tokenizer as an estimate, on a store with 67 items and 29 deliveries in the week.
- The platform's own tool-call overhead is not included.

| Request | Before | Now |
|---|---|---|
| 피클에게 브로컬리 발주 2개 넣어줘 | 380 | 236 |
| 매장에 감자튀김 재고 몇개야 | 967 | 259 |
| 지금 현재 그로스세일즈 얼마야 | 307 | 257 |
| 내일 피자치즈 입고 몇개야 | 676 | 276 |
| HR 스케쥴 확정 눌러줘 | 370 | 222 |
| All five | 2,700 | 1,250 (54% less) |

Where the savings come from:
- **Prompt:** 210 → 160 tokens. All formatting rules live in the hub, so Pickle only picks a file and copies.
- **Inventory:** the whole list is 734 tokens; one first-consonant slice is 46 on average (86 at most).
- **Deliveries:** the week is 438 tokens; `입고_내일.txt` is 88.
- **답.txt:** holds one answer instead of five.

The rest is on Pickle's side: every earlier turn of a chat is sent again with each new question, so a fresh chat each day keeps that from piling up.

What makes it fast:
- **Data questions never touch an AI.** Every answer is pre-written, rebuilt every 0.05–0.1 s, and written atomically, only when it changes. A cache file caught mid-write keeps its last good answers.
- **The AI path is kept warm.** It loads both SDKs once, builds their response models offline, and opens both connections before the first question. The fastest AI's first useful line goes out the moment it arrives.
- **The AIs are set for speed.** Claude runs at low effort, GPT at minimal reasoning, and both are asked for one line.
- **Paid speed options, off by default:**
  - `CLAUDE_FAST=1`: Claude fast mode, up to 2.5x output speed at 2x price ($8 / $40 per MTok on Opus 5.5). It retries once at standard speed if the fast pool is busy.
  - `GPT_PRIORITY=1`: OpenAI priority processing, at a higher price.

Not measured yet:
- Google Drive sync time in both directions, and how often Pickle reads the folder.
- The AIs' real latency (needs keys).
- How long 레미 takes to carry out an action.
