# 🔌 Aside-Grok Bot Connection (어사이드 · 그록 봇 연결 진행)

order.html 허브(`docs/aside/`)에 어사이드·그록 봇·피클을 붙이는 일입니다.
이 표는 **클로드 코드가 확인하고 고칩니다.** 봇은 이 파일을 고치지 않습니다(board 한 줄만).

## 진행 상황

| # | 단계 | 누가 | 상태 | 끝 기준 |
|---|---|---|---|---|
| 1 | 허브를 main 에 올림 | 클로드 코드 | 완료 (11.28) | GitHub main 에 `docs/aside/README.md` 가 보임 |
| 2 | 그록 봇 연결 확인 (`T-20261128-001`) | 그록 봇 | 대기 | board 맨 아래에 `[그록 봇 → 클로드 코드] 허브 읽음` |
| 3 | 어사이드 연결 확인 (`T-20261128-002`) | 어사이드 | 대기 | board 맨 아래에 `[어사이드 → 클로드 코드] 허브 읽음` |
| 4 | 2·3 확인, 패킷 `done` 으로 | 클로드 코드 | 대기 | `T-20261128-001.json`·`002.json` 의 `status` 가 `done` |
| 5 | 피클이 order.html `reports/` 도 감지 | 피클 | 대기 | order.html 에 보고서가 올라오면 KM 폰에 알림 |
| 6 | 첫 실제 일 맡기기 | 클로드 코드 → 봇 | 대기 | 지시서 1개 `완료` + 보고서 1개 |

## KM 이 할 일 (집 PC · 폰)

**그록 봇에게** (2단계)
> "`MFGKOREA/order.html` 저장소를 pull 하고 `docs/aside/README.md` 를 읽은 뒤, `docs/aside/tasks/task-20261128-hub-hello-grok.md` 를 해줘."

**어사이드에게** (3단계)
> "`MFGKOREA/order.html` 저장소를 pull 하고 `docs/aside/README.md` 를 읽은 뒤, `docs/aside/tasks/task-20261128-hub-hello-aside.md` 를 해줘."

**피클에게** (5단계)
> "label-list 말고 `MFGKOREA/order.html` 저장소의 `docs/aside/reports/` 와 `board.md` 도 새 글이 올라오면 알려줘."

봇이 board 에 줄을 남기면 클로드 코드에게 "연결 확인해" 라고 말해 주세요. 4단계를 하고 이 표를 고칩니다.

## 막히면

| 막힘 | 할 일 |
|---|---|
| 봇이 push 권한 없음(403) | 봇은 label-list board 에 한 줄 남기고 멈춤 → KM 이 order.html 저장소 설정에서 봇 계정에 쓰기 권한을 줌 |
| 로그인 창 | KM 이 직접 로그인. 봇은 기다림 |
| 같은 단계 두 번 실패 | 봇은 멈추고 `상태: 막힘: 이유` → 클로드 코드가 지시서를 고침 |
