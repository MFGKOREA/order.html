# [Task] order.html 허브 연결 확인 (그록 봇)

받는 사람: 그록 봇 (집 PC 브라우저)
보낸 사람: 클로드 코드 (order.html 세션)
상태: 대기

```json
{
  "task_id": "T-20261128-001",
  "intent": "order.html 허브 README와 규칙 원본 링크 3개를 열어 보고, board.md 맨 아래에 '[그록 봇 → 클로드 코드] 허브 읽음' 한 줄을 push한다. 끝 기준: GitHub의 order.html board.md에 그 줄이 보이고 이 지시서 상태가 완료",
  "assigned_to": "remi",
  "verify_by": "claude-code",
  "sla_sec": 600,
  "retry_count": 0,
  "max_retries": 3,
  "status": "queued",
  "evidence": [],
  "created_at": "2026-11-28T01:00:00+09:00",
  "fallback": ["km"],
  "source": "11/28 KM: Aside-Grok bot-hub 만들기 (order.html 저장소)",
  "result_path": "docs/aside/board.md"
}
```

## 무엇을
- **할 일:** 새 허브(`MFGKOREA/order.html` 의 `docs/aside/`)를 받아 읽고, 이 지시서를 `완료` 로 바꾸고, board 에 한 줄 남겨 push 한다.
- **끝 기준:** GitHub 웹에서 order.html 의 `docs/aside/board.md` 맨 아래에 내 줄이 보인다.
- **보고 예시:** `- 11.28 09:10 [그록 봇 → 클로드 코드] 허브 읽음 · 규칙 링크 3개 열림`
- **보고 모양:** board 한 줄만. 이 일은 `reports/` 보고서를 쓰지 않는다.

## 대상 (헷갈리기 쉬우니 꼭 확인)
| 무엇 | 맞는 것 | ❌ 건드리지 않음 |
|---|---|---|
| 저장소 | `MFGKOREA/order.html` (https://github.com/MFGKOREA/order.html) | `MFGKOREA/label-list` 의 board.md (이번 줄은 거기 쓰지 않음) |
| 고칠 파일 | 이 지시서의 `상태:` 줄, `docs/aside/board.md` 맨 아래 | board.md 의 위 줄들, 다른 지시서, 어사이드 지시서(`task-20261128-hub-hello-aside.md`) |

## 순서
1. `git clone https://github.com/MFGKOREA/order.html` (이미 있으면 그 폴더에서 `git pull`).
   - 로그인 창이 나오면 KM 이 직접 로그인할 때까지 기다린다. 대신 로그인하지 않는다.
2. `docs/aside/README.md` 를 끝까지 읽는다.
3. README 의 "📏 규칙 원본" 표에 있는 링크 3개를 브라우저로 연다. 각 페이지에 파일 이름이 보일 때까지 기다린다.
   - 안 열리는 링크는 더 누르지 말고 파일 이름만 적어 둔다.
4. 이 파일의 `상태: 대기` 를 `상태: 완료` 로 고친다 (안 열린 링크가 있으면 `상태: 완료 (안 열림: 파일 이름)`).
5. `docs/aside/board.md` 맨 아래에 한 줄 덧붙인다 (위 "보고 예시" 모양, 지금 한국 시간).
6. 커밋 메시지 `[그록 봇] 허브 연결 확인` 으로 push 한다.
   - ⚠️ push 가 거절되면 `git pull` 뒤 다시 push. `--force` 는 쓰지 않는다 (다른 쪽이 쓴 줄이 지워짐).
   - ⚠️ "권한 없음(403)" 이 나오면 멈춘다. label-list 의 `docs/aside/board.md` 맨 아래에 `- 시:분 [그록 봇 → 클로드 코드] order.html push 권한 없음` 한 줄을 남기고 끝낸다.
   - 같은 단계에서 두 번 실패하면 더 해 보지 말고 멈춘다.

## 확인
| 확인 | 방법 | 정상 기준 |
|---|---|---|
| 줄이 올라갔는지 | GitHub 웹에서 order.html `docs/aside/board.md` | 맨 아래에 `[그록 봇 → 클로드 코드] 허브 읽음` |
| 이 파일만 바뀌었는지 | 이번 커밋의 바뀐 파일 | `board.md` 와 이 지시서, 2개 |
| 비밀이 없는지 | board 줄을 다시 읽음 | 이메일·계정·키 없음 |

## 끝나면
1. 이 파일 `상태:` 가 `완료` 인지 본다.
2. board 줄이 GitHub 에 보이는지 본다.
3. 클로드 코드가 다음에 줄을 확인하고 패킷 `T-20261128-001.json` 을 `done` 으로 바꾼다 (봇은 JSON 을 고치지 않아도 됨).
