# E2E-D 보드 계약 초안 — B3 가중치·scale 배치(region 0 EXT 대 SRAM) × EXT 읽기 지연 (초안, 동결 전, 실행 미승인)

## 1. 질문

B3에 남은 EXT 지연 효과(12,206.5, TA profile 1)는 가중치·scale 공급(H-R1)과 함께 움직이는가, command fetch(H-R2)와 함께 움직이는가?

## 2. 구성

| 조건 | DRWL | graph IO | 가중치·scale (region 0) | command stream (QBASE) |
|---|---|---|---|---|
| B3 (대조) | `e2eb_b3` `7b2cedd5…` | SRAM | DDR/EXT | DDR/EXT |
| B3w | 같은 command stream, header word 7 = 2(새 placement 모드) | SRAM | **on-chip SRAM 사본**/SRAM 포트 | DDR/EXT |

- runner 변경(펌웨어):
  - `hooks.c ethosu_address_remap`: 모드 2이면 index 0을 SRAM 사본으로 돌린다(사본 = 0x31280000 + (base0 & 0xFFFF)). index −1(QBASE)과 나머지 base는 그대로다.
  - `placement_config_select`: 모드 2이면 region 0과 region 1을 SRAM 포트(0)로 둔다. QCONFIG는 3 그대로다.
  - 사본은 load 때 만들고, 패턴·보수 되읽기와 cache clean을 거친다. 측정 RUN 안에서는 복사하지 않는다.
  - RUN 기록에 BASEP0 실제값(remap 후)을 추가한다.
- 새 이미지 두 개: L500과 L1000. TA 설정 파일은 기존 이미지와 같다.
- 기대 REGIONCFG(n_base 6): B3 0x553, B3w 0x550.

## 3. 사전 예상 (동결 대상)

- MAC_ACTIVE 20,736.
- EXT read(16 B beat):
  - B3 11,322(E2E-B).
  - B3w = command stream 628 B → **39.25 beat**(±1 beat). EXT write는 0.
- SRAM read: B3w = B3 + 10,922 + 360(가중치·scale 이동), 합 보존.
- 대조: 새 이미지의 B3가 E2E-B B3(60,320 / 72,526.5)를 max(1 %, range 합) 안에서 재현해야 한다. 아니면 `IMAGE_NOT_EQUIVALENT`로 기록하고 판정은 `NOT_IDENTIFIABLE`이다.

## 4. 판정 (안)

LE(B3w) = B3w(1000) − B3w(500), LE(B3)는 같은 세션의 대조값을 쓴다.
- `WEIGHT_PATH_DOMINANT`(H-R1과 일관): LE(B3w) ≤ 0.25·LE(B3).
- `COMMAND_OR_OTHER_DOMINANT`(H-R2와 일관): LE(B3w) ≥ 0.75·LE(B3).
- `MIXED`: 그 사이.
- `NOT_IDENTIFIABLE`: 4개 B 구성 중 하나라도 VALID가 아니거나, B3w EXT read가 예상 밖이거나, 이미지가 동등하지 않음.
- 판정 이름은 원인 확정이 아니다. H-R3(중첩·의존성)는 어느 경우든 매개할 수 있다.

## 5. 순서·예산 (5 boot / 50 RUN, 이미지 교체 1회)

| boot | 조건 |
|---|---|
| 1 | REF (새 L500 이미지; boot 375 재현 게이트) |
| 2 | B3 L500 |
| 3 | B3w L500 |
| 4 | B3w L1000 |
| 5 | B3 L1000 |

pass A·B 각 5 RUN(1 + 4), TA profile 1. 중단·복원은 E2E-B와 같다.

## 6. 동결 전에 해야 할 것

- 펌웨어 변경과 테스트(host_sim placement 테스트 확장).
- 빌드 게이트 통과.
- 이미지 digest를 manifest에 넣는다.
- 판정 코드, mutation, preflight(사본 주소·REGIONCFG 0x550·EXT read 39 beat는 첫 boot-check로 확인).
