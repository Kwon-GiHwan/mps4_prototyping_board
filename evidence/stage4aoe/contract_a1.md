# Stage 4AO-E — 계약 개정 A1: 정체성 REGIONCFG 규칙 수정과 전체 재측정 (**동결 2026-11-15, boot 394 전**)

원 계약 `contract.md` (동결 `7cedd8e`)와 세션 1 데이터 (`f97eb2a`, boot 386–387)는 바꾸지 않는다. 이 개정은 정체성 Gate의
REGIONCFG 조건만 바꾸고, 그 밖의 모든 조항 (대상 8개, 순서, 측정 조건, 출력 검증, PMU, 판정 규칙과 구간, fail-fast, 복원)은
`contract.md` §0–§10을 그대로 따른다.
결정: owner 지시 (ChatGPT 경유) "Stage 4AO-E — 계약 A1 개정 승인 및 전체 재측정": A1 승인, 선택지 (a) 전체 재실행.

## 1. 세션 1의 판정 (그대로 둔다)

- boot 386: 재현 PASS. boot 387 (ADD H24): 원 계약 기준 boot-check FAIL (INVALID). boot 388–393: NOT_MEASURED.
- boot 387의 AO_ACTIVE 3,456은 POST_HOC_DESCRIPTIVE로만 보존한다. 새 규칙으로 소급 재판정하지 않고, 새 공식 데이터에도 넣지 않는다.

## 2. A1 — 바뀐 조건 (`stage4aoe.identity_a1`)

`K.identity`의 고정값 `regioncfg_irq == 0x15F`를 빼고, 모든 RUN (warm-up 포함)에 대해 아래를 모두 요구한다.

| 검사 | 내용 |
|---|---|
| expected_agree | 기대 n_base를 RUN과 무관한 두 가지 정적 방법으로 구해 일치해야 한다: (1) manifest `expected_identity.json` (컨테이너에서 DRWL 안의 Vela 모델의 ethos-u custom op: 입력 − 1 + 출력, TFLM `ethos_u/ethosu.cc`의 num_base_addr, 최대 8), (2) DRWL 헤더: 3 + IFM 수 + OFM 수. placement도 manifest와 DRWL word 7이 같아야 한다 |
| n_base | RUN 기록의 n_base = 기대 n_base |
| regioncfg | regioncfg_irq = placement_regioncfg(기대 n_base, DRWL placement). 2 bit/region, REGION0 3, REGION1_DDR 3 (SRAM 0), REGION2–7 1 (펌웨어 `placement.h`/`placement.c`) |
| qconfig | qconfig_irq = 3 |
| drwl_placement | RUN 기록의 placement = DRWL placement (0) |
| regioncfg_match_flag | 펌웨어의 REC_REGIONCFG_MATCH (valid_flags bit 6) 설정 |

K.identity의 나머지 (RUN 10개, model 길이, schema 4, placement 0, IRQ 1, CRC 1, 출력 길이, capabilities)와 workload sha256,
PASS_EXACT, RUN validity는 그대로다. Stage 4K 코드 (`stage4k.py`)는 바꾸지 않는다.
재현 Gate (boot 1)는 원 계약대로 `stage4ao.config_result` (Conv, n_base 5 → 0x15F)와 `K.reproduce`, AO 허용폭 35.34를 쓴다.
boot-check (boot 1 포함)는 `identity_a1`을 쓴다.

기대값 (정적, 두 방법 일치; `board_a1/g0.txt`):

| config | n_base | REGIONCFG | IFM (B) | OFM (B) | DRWL sha256 앞 12자리 |
|---|---:|---|---|---:|---|
| s4ao_conv1x1_h24 | 5 | 0x15F | 9,216 | 55,296 | bee0fbcb34fe |
| s4aoe_add_h24 | 6 | 0x55F | 55,296 ×2 | 55,296 | dfbe74f3d5c5 |
| s4aoe_mul_h24 | 6 | 0x55F | 55,296 ×2 | 55,296 | 3a96dd083afe |
| s4aoe_abs_h24 | 5 | 0x15F | 55,296 | 55,296 | 66e138cc0cbb |
| s4aoe_add_mul_h24 | 7 | 0x155F | 55,296 ×3 | 55,296 | c3eab559eaf1 |
| s4aoe_add_h72 | 6 | 0x55F | 165,888 ×2 | 165,888 | be981ef6916f |
| s4aoe_mul_h72 | 6 | 0x55F | 165,888 ×2 | 165,888 | 16c238a2178a |
| s4aoe_abs_h72 | 5 | 0x15F | 165,888 | 165,888 | e5d5ed2051ce |

## 3. 사전 검증 (데이터 전)

- 오류 주입 테스트 (`test_stage4aoe.A1Identity`, 세션 1 RUN 사본으로; 공식 판정은 바꾸지 않음):
  - 올바른 n_base + 틀린 REGIONCFG
  - 틀린 n_base + 그에 맞는 REGIONCFG
  - 틀린 placement
  - QCONFIG 불일치
  - REGIONCFG_MATCH 플래그 없음 (값은 맞음)
  - manifest와 헤더 불일치
  - 출력 불일치
  - 다른 workload (같은 n_base)
  - → 모두 FAIL. 깨끗한 사본은 PASS.
- 회귀: 보관된 schema-4 RUN 전부 (4K, 4AO, placement, 세션 1)에서 REGIONCFG = 규칙(n_base, placement)이고, DRWL이 있는
  구성에서는 헤더 n_base = RUN n_base.
- 정상 Conv 재현 판정 유지: 재현 Gate 테스트 (4AO boot 380 사본) PASS.
- test_stage4aoe 27개, 시뮬레이터 34개, mutation 57/57 KILLED, test.sh ALL PASS.
- G0 dry run: 데이터가 있는 구성 (h24 4AO·세션 1, add_h24 세션 1)은 boot-check PASS, 나머지는 NOT_MEASURED → FAIL rc 1이다.
  8개 모두 보드에서 정적 기대값을 계산해 표와 대조한다.

## 4. 실행

- boot **394–401** (확인: 마지막 사용 번호 387). 순서는 원 계약과 같다: h24 → add_h24 → mul_h24 → abs_h24 → add_mul_h24 → add_h72 → mul_h72 → abs_h72.
- 새 스테이징 `~/evsweep_s4aoe2`, 실행 `~/evsweep_s4aoe2_run`, 배포 evidence `~/evsweep/evidence_s4aoe2`.
- 세션 파일: `board_a1/session.txt`. 실패 경로로 끝나면 postflight를 user 단계로 따로 실행한다.
