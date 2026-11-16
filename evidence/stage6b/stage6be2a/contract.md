# Stage 6B-E2A 계약 — Vela 5.0.0 비용 모델 정적 감사 (보드 없음)

지시: Stage 6B-E2A 공식 지시(2026-11-16). 이 계약은 Vela 요약·debug DB 추출, 민감도 재컴파일, 비교 계산보다 먼저 커밋한다.
분류: **`POSTHOC_DIAGNOSTIC`**. 보드 값(6B-B boot 410–420, E1-R boot 428–434)은 이미 알려진 자료다.
보드 측정, 새 형상 생성, E3, Stage 6C, KWS G23/G24 측정은 하지 않는다. 기존 파일은 수정하지 않는다.

## 0. 계약 전 노출 (정직하게 적는다)

계약을 쓰기 전에 아래를 이미 보았다.
- 6B-R의 `vela_fidelity_analysis.csv`(A군 7개의 Vela total·npu·sram_ac·dram_ac, 보드 NPU_ACTIVE, 바이트).
- 이 값으로 그래프 수준의 Σ(npu + sram_ac + dram_ac)를 암산했다. 보드 NPU_ACTIVE ÷ 이 합은 0.75–1.02였다.
  따라서 아래 F3 형식은 **A군에서는 사후 탐색으로 찾은 것**이다. A군 결과는 설명으로만 쓰고, 판정은 B군(E1-R)을 주로 쓴다.
- E1-R의 보드 NPU_ACTIVE·MAC_ACTIVE와 H1-UC 예측(이미 커밋됨). **E1-R 형상의 Vela 요약·debug DB 값은 아직 보지 않았다.**
- Vela 5.0.0 소스(PyPI sdist), MLEK TA 문서·헤더, U85 레지스터 정의, 보드 `capabilities.json`(사실 확인용).
- 추출 스크립트 smoke test로 **G12 기준 컴파일 하나**만 debug DB 열 이름을 확인했다(Vela·command stream digest가 기록과 같음).
  G12의 Vela 값은 6B-R에 이미 공개돼 있다. 민감도 변형과 B군 값은 보지 않았다.
- M1c 손계산 fixture로 G12 Conv의 `mac_cycles` 24,290(6B-R 기록값)을 소스식으로 맞춰 보았다(테스트 기대값).

## 1. 대상과 출처

| 군 | 대상 | 보드 원시 자료 | Vela 산출물 | 용도 |
|---|---|---|---|---|
| A | 6B-B VALID 7개: G09 G11 G12 G25 G40 G52 G57 (A2 그래프: ADD → Conv → ADD) | `evidence/stage6b/stage6bb/raw/evsweep_s6bb_run/conds/<cfg>/wfe/` | 컨테이너 `/work/s6b_ra_compile/s6b_<g>_f_ctx_self.tflite`, 기록 `revision_a/compiled/s6b_<g>.ra.json` | 주 비교(설명) |
| A′ | 6B-B UNSTABLE 3개: G28 G53 G56 | 같음 | 같음 | `NOT_COMPARABLE`, 목록만 |
| B | E1-R Primary Valid 6개: e1r_c200_h37w37_o96, e1r_c200_h33w33_o96, e1r_c200_h37w37_o176, e1r_c200_h29w29_o96, e1r_c100_h37w37_o96, e1r_c136_h37w37_o96 (Conv 단독, IFM/OFM Dram) | `evidence/stage6b/stage6be1r/raw/evsweep_s6be1r_run/conds/<cfg>/wfe/` | 커밋된 `evidence/stage6b/stage6be1r/workloads/<cfg>.tflite`, 기록 `<cfg>.drwl.json` | 주 비교(판정) |
| C1 | Stage 4K 독립 Conv `s4c2_conv_cin48` (E1-R boot 428) | E1-R raw `s4c2_conv_cin48` | 컨테이너 `/work/s4k_compile/s4c2_conv_cin48.tflite`, 기록 `s4c2_conv_cin48.compile.json` | 참고 |
| C2 | driver_m7 원본 7개 모델 | `results/fi101_stage6/whole_model_comparison.csv`(npu_active) | 컨테이너 MLEK 원본(`stage6b_models.SOURCES`) | 참고 |
| C3 | Stage 5 메모리 배치·SRAM 예산 | `results/fi101_stage5*` | — | 문헌 참고 |

- 조건: TA profile 1. A·B·C1은 이미지 `70090f1`, C2는 `65cf963`.
- **A와 B는 통제군이 아니다.** 그래프(3연산 vs 1연산), 메모리 배치(Conv IFM/OFM Sram vs Dram), 가중치 경로가 함께 다르다.
- **C2는 동등 조건이 아니다.** 두 이미지 사이에 펌웨어 16개 파일이 바뀌었고(`git diff 65cf963 70090f1 -- firmware`), 같은 workload를 두 이미지에서 잰 교차 검증이 없다. 따라서 C2와 A·B의 오차 차이를 같은 조건의 차이로 해석하지 않는다(`REFERENCE_NOT_EQUIVALENT`).

### 1.1 비교 가능 조건 (형상마다, 하나라도 거짓이면 `NOT_COMPARABLE`)
- I1: 재컴파일한 Vela 출력 sha256 = 측정 blob 기록의 `vela_sha256`.
- I2: 출력의 command stream sha256 = 기록의 `cms_sha256`.
- I3: 원본 tflite sha256 = 기록의 `model_sha256`(A는 `ra.json`의 A2 `model_sha256`).
- I4: 보드 상태가 원 단계에서 VALID(A: 6B-B `shapes.csv`, B: E1-R `PRIMARY_VALID`).
- 범위: Vela `cycles_total`은 그래프 전체 연산의 합, 보드 NPU_ACTIVE는 같은 command stream 전체의 NPU 실행 구간이다. 두 범위가 같은 command stream을 덮는 것을 I1–I2로 확인한다.

### 1.2 보드 값 (재계산, 원 단계와 일치 확인)
- `stage4k.summary_of(folder, n_mac)`의 pass A·B 중앙값(warm-up 제외). 이벤트: 35 NPU_ACTIVE, 48 MAC_ACTIVE, 64 AO_ACTIVE, 80 WD_ACTIVE, 81 WD_STALLED, 128/130 SRAM read 트랜잭션/beat, 132/135 SRAM write 트랜잭션/beat, 384/386 EXT read 트랜잭션/beat, 391 EXT write beat.
- 바이트 = beat × 16(U85 AXI 128-bit, MLEK 문서 D). 평균 burst(바이트) = beat ÷ 트랜잭션 × 16.
- I5(무결성): A의 NPU_ACTIVE·MAC_ACTIVE가 6B-B `shapes.csv`와 같고, B의 NPU_ACTIVE가 E1-R 요약 `npu.a_median`과 같다. 다르면 분석을 멈추고 보고한다.
- I6(재현): A의 오차가 6B-R `vela_fidelity_analysis.csv`의 `error_pct`와 1e-9 안에서 같다.

## 2. Vela 값의 정의 (소스 기준; Vela 5.0.0, regor .so = PyPI cp310 wheel과 바이트 동일)

- 연산별(debug DB `perf_debug`): `npu_cycles`(MeasureCycleCost.opCycles, 가중치 버퍼링·LUT 전송 반영), 메모리별 `<mem>_ac`(MeasureAccessCycles의 totalAccessCycles), `total_cycles` = max(npu, 메모리별 ac의 최대).
- `perf_debug_main`: `mac_cycles`, `ao_cycles`, `cmd_cycles`, traversal, 블록.
- 그래프: 요약 CSV `cycles_total` = Σ 연산 `total_cycles`, `cycles_npu` = Σ npu, `cycles_sram_access`·`cycles_dram_access` = Σ 메모리별 ac.
- **Vela compute** = `cycles_npu`. **Vela SRAM/DRAM access** = `cycles_sram_access`/`cycles_dram_access`. **Vela total** = `cycles_total`.
- Vela 연산별 값은 보드의 연산별 실행시간이 아니다. 연산별 PMU 실측과 대응시키지 않는다.

## 3. Phase 2 — 소스 재현 검사 M1 (판정 입력)

| 검사 | 내용 | 통과 |
|---|---|---|
| M1a | 모든 NPU 연산에서 `total_cycles` = max(`npu_cycles`, 메모리별 ac 최대) | 비교 가능 컴파일 전부에서 100 % |
| M1b | 모든 그래프에서 `cycles_total` = Σ 연산 `total_cycles` | 100 % |
| M1c | 모든 1×1 DepthFirst Conv 연산에서 `mac_cycles`를 소스식으로 재계산(아래)해 ±1 사이클 안 | ≥ 90 % |
| M1d | 메모리 access cycles를 ChannelBW식으로 재계산(아래) | 기술만(판정 입력 아님) |

M1c 식(`EstimateMacCyclesPerBlock`, `EstimateMacOpCycles`, int8, Acc32, dense):
- ofmBlk = min(OFM, OFM block), ifmBlk = min(IFM, IFM block), nU = ⌈ofmBlk/ublock⌉(h,w,c별).
- 블록당 MAC = max(4·ublock_c/8, ifmBlk_c/8 · nU_h·nU_w) · nU_c · ⌈Cin/ifmBlk_c⌉ (1×1이라 kernel step 1). delay: nU_h·nU_w = 1이고 nU_c = 1이면 +2.
- 블록 수 n = (⌈OFM/ublock⌉의 원소 수) ÷ (nU의 원소 수) (실수).
- AO 블록 = max(⌈0.0625 · ofmBlk 원소⌉, 10 · ofmBlk_c · const_read_latency / 256), const 메모리 = Dram(지연 500).
- `mac_cycles` = ⌊블록당 MAC · n + AO 블록⌋.

M1d 식(`ChannelBW`): BW_ch = min(Bandwidth, burst · min(RB_ch/(burst/16), max_out · ports · 0.8) / latency · 0.8),
Bandwidth = clock_scale · 16 · ports_used, U85-1024 RB = {Mem2Mem 256, IFMStream 256, Weight 416, FastWeight 208, IFM 256, Scale 16}, Write는 RB 제한 없음.

## 4. Phase 3 — 형상별 표 (`vela_board_table.csv`)

열: shape, group, status, vela_compute, vela_sram_ac, vela_dram_ac, vela_total, board_npu_active, board_mac_active, board_ao_active,
board_wd_active, board_wd_stalled, vela_sram_read/write_bytes, vela_dram_read/write_bytes, board_sram_read/write_bytes,
board_ext_read/write_bytes, error_total = (NPU − Vela_total)/Vela_total, **diag_vela_compute_over_mac_active**(진단 지표, 예측 오차 아님),
vela_conv_mac_cycles, h1uc_mac_active(A: `stage6br.h1_uc`, B: `predictions.json` H1-UC), diag_vela_conv_mac_over_h1uc, 평균 burst 3종.
H1-UC는 MAC_ACTIVE 예측식이다. Vela compute나 NPU_ACTIVE의 예측으로 쓰지 않는다.

## 5. Phase 5 — 메커니즘 형식 (매개변수 없음, Vela 자신의 연산별 성분만 사용)

| 형식 | 식 (연산별 값을 그래프에서 합) | 해당 메커니즘 |
|---|---|---|
| F0 | Σ max(npu, sram, dram) | Vela 그대로(검산) |
| F1 | Σ (npu + max(sram, dram)) | 계산과 메모리가 겹치지 않음 |
| F2 | Σ max(npu, sram + dram) | 두 메모리 포트가 겹치지 않음 |
| F3 | Σ (npu + sram + dram) | 아무것도 겹치지 않음 |
| F4 | Σ max(npu, sram·r_S, dram·r_D), r_S = 보드 SRAM 바이트 ÷ Vela SRAM 바이트, r_D = 보드 EXT 바이트 ÷ Vela DRAM 바이트(그래프 수준, 읽기+쓰기) | Vela 바이트 추정 대신 실측 바이트 |

F4는 보드 바이트를 쓰는 대입이며 연산별 바이트 실측이 없어서 그래프 수준 비율을 모든 연산에 똑같이 적용한 근사다.

**M2(메커니즘과 관측 차이의 관계):** F1–F4 중 한 형식이 다음을 모두 만족한다.
- B군 비교 가능 형상 ≥ 5개, 그 전부에서 |오차| ≤ 15 %.
- A군 비교 가능 형상의 |오차| 중앙값 ≤ 15 %.
만족하는 형식이 여럿이면 모두 기록한다. M2는 "관계"이며 인과의 입증이 아니다.

## 6. Phase 4 — 설정 감사 (`config_audit.csv`, 항목별 closed set: `MATCH` / `MISMATCH_VERIFIED` / `UNKNOWN` / `NOT_APPLICABLE`)

| 항목 | 비교 | 규칙 |
|---|---|---|
| C1 지연 | TA rlatency/wlatency 대 Vela read/write latency, 단위 | 값이 같고 S0-3 c2(TA root clock = CPU clock, MCLK_ON = NPU cycles)로 단위가 NPU 사이클이면 MATCH |
| C2 outstanding | 유효 한도 = min(TA 값(0 = 무한, 문서 S·D), NPU AXI `max_outstanding_*_m1`+1) 대 Vela max_reads/writes | 같으면 MATCH, 다르면 MISMATCH_VERIFIED |
| C3 포트 수 | NPU CONFIG `num_axi_sram`/`num_axi_ext` 대 Vela ports_used | 필드를 log2로 읽고(Vela 자체 U85-1024 표와 같은 해석) 같으면 MATCH |
| C4 대역폭 | TA cap = bwcap · word / (pulse_on + pulse_off) B/cycle, word ∈ {8, 16}(문서 S와 C·D가 다름), TA가 덮는 포트 수 ∈ {1, 2} 대 Vela Bandwidth = clock_scale·16·ports_used | 네 조합이 모두 Vela보다 작으면 MISMATCH_VERIFIED, 모두 같거나 크면 MATCH, 그 밖에는 UNKNOWN |
| C5 burst | 실측 평균 burst(바이트) 대 Vela burst_length(Sram 64, Dram 128); NPU AXI `max_beats` 필드 | 한 포트·방향에서 A∪B 비교 가능 형상 **전부**의 평균 burst가 Vela burst_length보다 10 % 넘게 크면 MISMATCH_VERIFIED. 전부 Vela 이하(+10 % 안)이면 MATCH(평균 burst는 최대값의 하한 증거일 뿐임을 함께 적음). 그 밖에는 UNKNOWN |
| C6 메모리 배치 | Vela 텐서 메모리(Sram/Dram) 대 보드 영역(fast_base는 SRAM 포트, DDR은 EXT 포트) | 6B-R 정적 대응 그대로: MATCH |
| C7 SRAM 크기 | arena_cache_size 대 capabilities `fast_size` | 같으면 MATCH |
| C8 클럭 | Vela core_clock 1 GHz | 사이클 단위 비교라 NOT_APPLICABLE |
| C9 TA MODE bit 0 | 동적 클럭(언더런 때 NPU 클럭 정지) | Vela에 대응 개념 없음: NOT_APPLICABLE, 의미를 기록 |

추정값으로 하드웨어 값을 채우지 않는다. 확인할 수 없으면 UNKNOWN이다.

## 7. Phase 5 — 원인 가설 (closed set: `SUPPORTED_PATTERN` / `CONTRADICTED` / `NOT_DISTINGUISHABLE`)

오차 초과분 excess = NPU_ACTIVE − Vela_total.
- **H-E2-1 메모리 서비스 비용 과소추정.** (a) 바이트량: F4의 A∪B |오차| 중앙값 ≤ 15 %이면 SUPPORTED_PATTERN. 모든 형상에서 보드 총 바이트 ≤ Vela 총 바이트이고 F4와 F0의 |오차| 중앙값 차이가 10 %p 이하이면 CONTRADICTED. 그 밖에는 NOT_DISTINGUISHABLE. (b) 바이트당 서비스 비용(지연·대역폭): 정적 자료로는 **항상 NOT_DISTINGUISHABLE**(TA 조건 A/B가 필요). Phase 6 민감도는 크기만 보여 준다.
- **H-E2-2 실행 중첩 가정.** F1–F3 중 하나가 M2를 만족하면 SUPPORTED_PATTERN. F1–F3이 모두 A·B 각각에서 형상의 절반 이상을 15 % 넘게 **과대** 예측하면(보드 < 형식) CONTRADICTED. 그 밖에는 NOT_DISTINGUISHABLE.
- **H-E2-3 작은 그래프의 고정 비용.** 군별로 Spearman(excess, Vela_total) ≥ 0.8이면 그 군에서 CONTRADICTED(초과분이 크기와 함께 커짐), Spearman ≤ 0.2이고 excess의 CV ≤ 0.25이면 SUPPORTED_PATTERN, 그 밖에는 NOT_DISTINGUISHABLE. A·B가 같으면 그 값, 다르면 NOT_DISTINGUISHABLE. 소스에 연산·그래프 고정 비용 항이 있는지를 함께 적는다.
- **H-E2-4 컴파일 구성·배치 차이.** A와 B는 래퍼·배치·그래프 크기가 함께 바뀌므로 원인 분리는 **항상 NOT_DISTINGUISHABLE**. 다만 A·B 오차 중앙값 차이가 25 %p를 넘으면 "양상 차이 있음"으로 기록한다. C2는 참고로만 적는다.

상관으로 원인을 확정하지 않는다.

## 8. Phase 6 — Vela 단독 민감도 (사전 고정)

- 방법: MLEK ini를 복사하고 `[System_Config.E2A_<항목>_<값>]` 절을 붙인다. 이 절은 `Ethos_U85_SYS_DRAM_Mid_1024`의 17줄을 그대로 복사하고 한 줄만 바꾼다. `--system-config`만 바꾸고 나머지 옵션은 같다.
- 변수(한 번에 하나, 기준값의 ×0.5와 ×2; 정수형은 반올림):
  Dram_clock_scale, Dram_read_latency, Dram_write_latency, Dram_max_reads, Dram_max_writes, Dram_burst_length, Dram_ports_used(1만),
  Sram_clock_scale, Sram_read_latency, Sram_write_latency, Sram_max_reads, Sram_max_writes, Sram_burst_length, Sram_ports_used(1만).
  총 26개 변형 × (A 7 + B 6 + C1 1) 컴파일.
- 분류: command stream sha256, const sha256, arena·fast 크기, IO 오프셋이 기준과 모두 같으면 `ESTIMATOR_ONLY_COMPARABLE`; 하나라도 다르면 `COMPILE_CHANGED`; 컴파일 실패·추출 실패면 `NOT_COMPARABLE`.
- ESTIMATOR_ONLY_COMPARABLE에서만: Vela_total 변화, 탄력도 ln(total_v/total_0)/ln(p_v/p_0), 보드 대비 오차(라벨 `POSTHOC_SENSITIVITY`).
  COMPILE_CHANGED는 다른 컴파일에 대한 새 예측이라 보드와 비교하지 않는다. 최적 설정 탐색은 하지 않는다.
- 민감도 결과는 판정 입력이 아니다.

## 9. 최종 판정 (closed set, 위에서부터 처음 성립하는 것)

1. **`COST_MODEL_MECHANISM_IDENTIFIED`**: M1a, M1b, M1c가 통과하고 M2가 성립.
2. **`CONFIGURATION_DISCREPANCY_IDENTIFIED`**: §6에 MISMATCH_VERIFIED가 하나 이상.
3. **`CAUSE_UNRESOLVED`**: 그 밖.

- 1이 성립해도 §6 결과를 함께 보고한다(반대도 같다).
- 어떤 판정이든 "실제 실행시간 오차의 원인"은 입증하지 않은 것으로 남긴다(지시 §10).
- I5 실패 시 판정하지 않고 멈춘다.

## 10. Phase 7 — 후속 보드 실험 초안

결과에 따라 초안만 쓴다(`e2b_contract_draft.md`). 최대 5 boot 예산부터 검토하고, 한 번에 한 변수, command stream 동일성, TA 조건, 사전 예상, PMU 이벤트, 중단 기준을 포함한다. 래퍼와 메모리 경로가 동시에 바뀌는 비교로 몫을 단정하지 않는다.

## 11. 검증

- 판정 코드 `host/analysis/stage6be2a.py`, 테스트 `host/tests/test_stage6be2a.py`(손으로 쓴 기대값), mutation(`evidence/stage6b/stage6be2a/mutate.py`) 전부 KILLED.
- Vela 추출을 2회 해서 facts 파일 sha256이 같아야 한다. 분석을 2회 해서 산출물이 바이트 단위로 같아야 한다.
- `test.sh` ALL PASS, 기존 파일 불변(git), credential 검사.
- 로컬 커밋만 한다. push하지 않는다. 컨테이너는 원격 `benchmark-runner`만 쓴다(로컬 colima 사용 안 함).
