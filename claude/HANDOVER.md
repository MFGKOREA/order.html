# Astro Friends (@thewhatif_labs) — Claude Code 이사 안내서

작성 2026-11-03. 채팅(claude.ai 프로젝트 "INSTAGRAM Viral")에서 Claude Code로 옮기면서 만든 인수인계 문서.
새 세션은 이 파일부터 읽고, 자세한 내용은 아래 프로젝트 문서를 읽을 것.

## 0. 이사 직후 할 일 (한 번만)
1. Claude Code에서 프로젝트 "INSTAGRAM Viral"을 붙여서 열기 → 프로젝트 문서 11개가 그대로 보임
2. `/mcp` → `kling-ai` 서버 로그인(OAuth). 성공하면 Kling 도구(who_am_i, query_membership_and_credits 등)가 생김
3. 연결 확인: Kling 크레딧 조회 + 힉스필드 `balance` 조회
4. 재료 생성 담당을 정함: 지금처럼 어사이드가 Kling으로 만들지, Claude가 Kling MCP로 직접 만들지

### 이사 점검 기록 (2026-11-03, 클라우드 세션)
- 힉스필드: 연결됨. pro 플랜, 잔액 91.36크레딧 (문서 기록과 일치)
- Kling(`plugin:kling-ai`): 설치돼 있으나 OAuth 미인증 → 도구 안 보임. 사용자가 로그인해야 함
- Manifold: 연결됨
- 재료 생성 담당 결정(2026-11-03): **Claude가 Kling MCP로 직접 생성**. Kling 로그인 전까진 힉스필드 `kling3_0`으로 대체 가능 (5초 9:16 = 10크레딧, 힉스필드 차감)
- 클라우드 세션에서는 kling-ai OAuth를 못 띄움 → claude.ai 커넥터(https://claude.ai/customize/connectors)에 `https://kling.ai/mcp/plugin` 추가 후 새 세션, 또는 로컬 Claude Code에서 `/mcp` 로그인
- 이 저장소(`mfgkorea/order.html`)에는 프로젝트 문서 11개(`claude/series-bible.md` 등)가 아직 없음 → 문서를 이 `claude/` 폴더로 옮겨 넣으면 이후 세션이 바로 읽을 수 있음

## 1. 응답 규칙
- 반말, '~함' 어미
- 영어 대본·캡션·프롬프트를 줄 땐 한글 번역을 같이
- 단위는 미터법(km, m, ℃)
- 순수 정보 위주, 불필요한 인터랙티브 기능 빼기
- 매 편 크레딧 사용량/잔액 보고

## 2. 계정·시리즈 핵심
- 인스타 @thewhatif_labs, 유튜브 'Astro Friends'. 영어권 타깃, 9:16 릴스 약 36~37초
- 컨셉: 우주복 입은 동물(Astro ○○)이 지구 같은 '미지의 행성(an unknown planet)'에 착륙 → 한 가지 조건만 다른 상황
- 스토리 고정: 만약에? → 문제 발생(과학 팩트 1개) → 위기(경고 HUD) → 해결(그 동물의 실제 특성) → 탈출(발사 + 펀치라인 + 다음 방문자 예고)
- 내레이터: 우주선 AI "NOVA", 보이스는 힉스필드 ElevenLabs v4 Orion(ed69c516-92d2-4b30-a967-617737a342e5), stability 0.45
- 첫 0~2초 콜드 오픈: 위기 장면 + WHAT IF 질문 자막(y 1330, 얼굴 안 가리게)
- 엔딩 카드: NEXT VISITOR / WHAT IF? / FOLLOW @thewhatif_labs / YOUTUBE: ASTRO FRIENDS
- 캡션: 한 단어로 답하는 댓글 질문 + 'Also on YouTube: Astro Friends' + 해시태그 5~9개
- 퀄리티 기준: Ep12 같은 AI 영상 퀄리티. Claude가 Blender로 직접 만든 3D(Ep13 첫 버전)는 거절됨 → 다시 쓰지 말 것

## 3. 현재 진행 상황 (2026-11-03 기준)
- 게시: Ep1~11 공개, Ep12~23 예약(11/7까지)
- Ep24 낙타, Ep25 기린 READY / Ep26 오리너구리 패키지 완성
- Ep27~37 대본·프롬프트 완성 → `claude/episodes/ep27-37-packages.md`
- 다음 신규: Ep38 안경원숭이(빨간 태양)
- 시즌편(날짜 고정): 11/24 비버(슈퍼문), 11/25 다람쥐, 12/12 잠자리, 12/23 순록, 12/31 수탉

## 4. 제작 흐름 (Ep24~)
1. 재료: 키프레임 k0~k7·동물 REF·커버는 Kling Image 3.0(2K, 9:16), 음성은 힉스필드 Orion. Ep27부터 훅 영상 5초도 Kling(image-to-video, 시작 이미지 k7)
2. Claude가 재료를 받아 힉스필드 샌드박스에서 2.5D 애니메이션 → 자막·HUD·엔딩 합성 → 8M 렌더 → 커버
3. 업로드 대기열 페이지에 READY 패키지 추가 (VIDEO_URL / COVER_URL / COVER_FRAME / CAPTION)
4. 예약은 Meta Business Suite에서 하루 1편, 밤 11:50(KST). 상태 READY → SCHEDULED → POSTED, 보류는 HOLD
5. 완성본은 힉스필드 `register_what_if_result(episode=NN)`로도 등록

## 5. 파이프라인 코드 (힉스필드 샌드박스용)
샌드박스는 24시간 미사용 시 파일이 사라짐 → 프로젝트에 백업된 걸로 복구:
- `claude/pipeline/scripts.md` (voice.sh, mkedit.py, render_edit.sh, cover.sh, epbuild.sh + 모델 다운로드 명령)
- `claude/pipeline/prep.py`, `anim.py` → /home/user/anim/
- `claude/pipeline/edit-template.jsx`, `ui.jsx`, `cover-template.jsx` → /home/user/anim/
순서: voice.sh → kf/k0~k6.png 다운로드 → shots.py·ep.json → epbuild.sh NN → cover.sh → 업로드

## 6. 링크
- 업로드 대기열: https://claude.ai/artifact/NfbkKWkL7kh5hMzhNYGPMY
- Ep24~ 어사이드 프롬프트 문서: https://claude.ai/artifact/VV4ZcjBjEtdDbtn6KLeMuG
- Ep27~37 어사이드 프롬프트 문서: https://claude.ai/artifact/Vo3B4wG7DCWuEq2zaeMH1S
- 다음 30편 콘텐츠 플랜: https://claude.ai/artifact/5UGP3V6r7QCgr8C1RwJV9H

## 7. 도구
- 힉스필드: pro 플랜, 2026-11-03 잔액 91.36크레딧 (Kling 3.0 영상·Motion Control도 여기서 가능, 대신 힉스필드 크레딧 차감)
- Kling 플러그인(kling-ai 스킬 3개): Claude Code에서 `/mcp` 로그인 후 사용. Ep24부터 Kling 크레딧 충전해 둠
- Manifold: 인스타·틱톡·유튜브 데이터(조회수 분석)
- 전용 스킬: astro-friends-episode(한 편 제작), whatif-topic-scout(주제 순위), reel-hook-lab(훅 8개 + A/B), reel-performance-audit(조회수 편차 분석)
- 업로드 보조: 어사이드(Aside, 별도 AI 브라우저). 어사이드용 프롬프트는 영어로

## 8. 프로젝트 문서 목록
- `claude/series-bible.md` — 시리즈 규칙·에피소드 전체 기록 (가장 먼저 읽을 것)
- `claude/episodes/ep14-20-packages.md`, `ep21-23-packages.md`, `ep27-37-packages.md` — 대본·프롬프트·캡션 원본
- `claude/characters/cartoon-character-plan.md` — 굿즈·게임용 카툰 캐릭터 15마리 계획 (2차 카툰풍 생성 보류 중, Kling 연결되면 진행)
- `claude/pipeline/*` — 위 5번 코드
