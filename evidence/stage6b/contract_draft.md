# Stage 6B — 1×1 DepthFirst 대표 형상 MAC 측정 계약 **초안** (동결하지 않음)

상태: 초안이다. 동결하지 않았고 보드 RUN도 하지 않았다. 대상 표 (§1)는 사전 고정 규칙 (`rules.md`, `b9f3824`)의 선정 결과다.
개정 A (README §4)가 승인되면 §1을 그 선정 결과로 바꾼다. 나머지 절은 그대로 쓴다.

측정 조건 (모든 숫자):
- FI101 Ethos-U85 1024 MAC, **TA profile 1**, Driver Runner 이미지 `70090f1`
- DDR/EXT 배치 (DRWL word 7 = 0), Vela 5.0.0 (MLEK 옵션)
- pass A (set 2) / pass B (set 3), 각 warm-up 1 + 측정 4 RUN
- 출력 PASS_EXACT (golden = BUILTIN_REF)

## 1. 대상 (고정 순서, 원래 규칙의 선정)

| 순서 | config | 역할 | 원본 | DRWL sha256 | n_base / REGIONCFG |
|---:|---|---|---|---|---|
| 1 | `s4c2_conv_cin48` | 기준 재현 (Stage 4K boot 375) | — | `6eb390be…` (4K 원시 데이터와 같음) | 5 / 0x15F |
| 2 | `s6b_g14_f_ctx` | G14 대표 (F_CTX) | wav2letter #220 (TFLite 연산 번호는 `candidates.json`) | `9af29638…` | 7 / 0x155F |

- 2 boot / 20 RUN이다. 개정 A가 승인되면 최대 11 boot / 110 RUN이 된다.
- A1 manifest: `workloads/expected_identity.json`. REGIONCFG는 `stage4aoe.placement_regioncfg(n_base, placement)`로 계산한다.
- 실행 가능 확인 (`compiled/*.s6b.json` `feasible`): fast scratch ≤ 0x60000, arena ≤ 0x200000, 모델 + arena ≤ 32 MiB,
  scheduled Conv 하나, CPU 연산 없음, 반복 컴파일 sha256 같음. 이미지의 capabilities (fast_size 0x60000, arena_len 0x200000)는
  boot마다 기존 값과 같아야 한다.

## 2. 기준 재현 Gate (boot 1)

- 기준: Stage 4K boot 375 `s4c2_conv_cin48` (MAC_ACTIVE 3,456, MAC_DPU_ACTIVE 3,456, NPU_ACTIVE 22,251, range 154).
- 검사는 `stage4aoe.repro_gate`와 같은 방식 (K.reproduce)이다.
  - MAC·DPU 정확히 같음
  - 출력 sha256 같음
  - 상수 카운터 같음
  - NPU 허용폭 안
- FAIL이면 중단하고 해석하지 않는다.

## 3. 지표 (데이터 전 고정)

- 주 지표 (MAC 축):
  - MAC_ACTIVE, MAC_DPU_ACTIVE, MAC_DPU_ACTIVE / MAC_ACTIVE
  - Nominal MAC / MAC_ACTIVE: Nominal = Vela mac_count
  - Valid MAC / MAC_ACTIVE: Valid = H·W·Cin·Cout, 1×1이므로 Nominal과 같음
  - 1024 MAC/cycle 대비 비율
- F_CTX 계열의 해석 제한:
  - ADD 두 개는 MAC_ACTIVE 0, WD 0이다 (Stage 4AO-E). 그래서 MAC·WD 지표는 Conv만의 값이다.
  - AO_ACTIVE, NPU_ACTIVE, MAC_ACTIVE/NPU_ACTIVE, Nominal MAC/NPU_ACTIVE, beat 수에는 ADD가 포함된다.
    이 값들은 "래퍼 포함"으로 표시하고 Conv 단독 값으로 해석하지 않는다.
- 보조 (기술 통계만): AO_ACTIVE, WD_ACTIVE, WD_STALLED, NPU_ACTIVE, EXT/SRAM rd·wr beat, Vela 추정 사이클.
  WD_STALLED를 병목 시간으로 환산하지 않는다.

## 4. 판정 (데이터 전 고정, 구현은 동결 때 `stage6b.py judge`로 추가)

- 안정성: pass A MAC_ACTIVE range ≤ max(1 %, 25 cycle). 넘으면 MEASUREMENT_UNSTABLE (판정 제외, 추가 RUN은 승인 사항).
- 형상별 처리율 범주 (Nominal MAC / MAC_ACTIVE = r):
  - R768: |r − 768| ≤ 1 %
  - R640: |r − 640| ≤ 1 %
  - R1024: |r − 1024| ≤ 1 %
  - OTHER: 그 밖 (값을 그대로 보고)
- 기존 640·768은 정확히 같은 형상에만 정량 기준으로 쓴다. 이번 대상에는 같은 형상이 없으므로 모두 **새 관측**이다.
- 가설 H1–H4 (지시 §6)은 조사 방향이다. 이번 측정으로 인과를 확정한다고 쓰지 않는다.
  - H2 (채널 단위)는 Cin을 16 단위로 올린 Valid′로도 r을 함께 보고하는 방식으로만 다룬다 (POST_HOC 표시).

## 5. 실행·Gate·fail-fast·복원

Stage 4AO-E A1 계약 (`evidence/stage4aoe/contract_a1.md`), Stage 4WD 계약과 같다.
- 실행 전 G0: sha256 대조, 정적 정체성, 보드 dry run (이번에는 n_base 5와 7을 모두 dry run).
- boot마다 boot-check (A1). boot 1 뒤 repro-gate.
- 실패하면 즉시 중단하고 복원한다. 실패 경로에서는 postflight를 따로 실행한다.
- 원시 데이터와 sha256을 보존한다. `--outputs`로 불일치 출력을 보존한다.
- m6 복원 → PING state 1 → 카드 분리. push는 하지 않는다.

## 6. 승인 필요

1. 개정 A (F_CTX_SELF 형태 추가) 적용 여부. 적용하면 §1을 다시 선정한다.
2. 보드 측정: 원래 규칙이면 2 boot / 20 RUN, 개정 A면 최대 11 boot / 110 RUN.
3. 판정 구현 (`judge`)과 mutation test를 동결 전에 추가하는 것.
