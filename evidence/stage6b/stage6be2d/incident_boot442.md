# Stage 6B-E2D 세션 중단 기록 — boot 442 (W0-P1) 판정 코드 오탐 (2026-11-17)

## 일어난 일

- 세션(`3ca60a7` 동결, preflight `1c7a108`)은 boot 440(REF), 441(W0-P0 L500), 442(W0-P1 L500)를 실행했다.
- 442 뒤 `boot-check`가 **CONFIG_MISMATCH**(이유: `identity placement`)를 냈다. 계약 §6에 따라 세션이 멈췄고 카드는 자동 복원됐다(RESTORE VERIFIED).
- 보드 정상화를 위해 postflight를 따로 실행했다(sudo 없음): POSTFLIGHT DONE, 카드 분리, 마운트 0.
- 443–448(W1 4구성, L1000 전체)은 **측정하지 않았다.** 사용 boot는 3/9, RUN은 30/90이다.

## 원인 (판정 코드 결함, 보드 측정은 정상)

- E2D 판정은 `stage6bb.identity_of` → `stage4aoe.identity_a1` → `stage4k.identity`를 그대로 쓴다.
- `stage4k.identity`에는 `placement=all(r.get("placement") == 0 …)` 항이 고정돼 있다(Stage 4K는 DDR만 썼다).
- `identity_a1`은 REGIONCFG 항만 빼고 이 항을 그대로 두고, 대신 DRWL의 placement와 비교하는 `drwl_placement` 항을 더한다.
- 그래서 placement 1인 W0-P1은 기대값이 맞아도 항상 실패한다.
- dry run은 기존(placement 0) 자료로만 해서 이 경로를 확인하지 못했다. preflight 표 #9·#11이 이 경로를 확인한 것처럼 읽히는 것은 잘못이다.

boot 442의 실제 기록(원시 자료 `raw/evsweep_s6be2d_run_l500/conds/e2d_w0p1/`):
- 10 RUN 모두 placement 1, n_base 5, REGIONCFG 0x153(기대 339 = 0x153), valid_flags 127(REGIONCFG_MATCH 포함).
- arena = base1 = `0x310765F0`(on-chip SRAM). base0(가중치) `0x700003B0` DDR, base2 `0x31000000` fast.
- 출력은 golden과 같다. identity의 다른 항은 모두 통과했다(`drwl_placement` 포함).

## 현재 상태

- 계약 규칙상 판정은 **MEASUREMENT_INVALID**다(CONFIG_MISMATCH와 미측정 구성).
- 측정된 값(기술, 판정 입력 아님. TA profile 1, EXT RLATENCY 500, 이미지 `70090f1`):

| 구성 | boot | 상태(현 판정 코드) | NPU_ACTIVE (range) | MAC_ACTIVE | Vela |
|---|---|---|---|---|---|
| REF | 440 | VALID, 재현 게이트 PASS | 22,307 | 3,456 | — |
| W0-P0 | 441 | VALID | 55,487.5 | 20,736 | 107,812 |
| W0-P1 | 442 | CONFIG_MISMATCH(오탐) | 27,182.5 (386) | 20,736 | 없음 |

## 승인이 필요한 결정 (에이전트는 진행하지 않음)

- 판정 코드 정정(안): E2D에서 identity의 `placement` 항을 DRWL 기대 placement와 비교하도록 바꾼다(공유 모듈은 고치지 않음). 테스트와 mutation을 추가한다.
- 측정 계속(안):
  - (가) 정정 후 9 boot 전체를 새 boot 번호로 다시 측정한다. 순서·균형이 원래 설계대로 유지된다.
  - (나) 남은 6 boot(443–448 상당)만 측정한다. 순서가 끊기고 시간 간격이 생긴다.
- 어느 쪽이든 승인 예산 9 boot를 넘는다(이미 3 boot 사용).
