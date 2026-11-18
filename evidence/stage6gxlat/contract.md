# Stage 6G-X_LAT 계약 — 직렬 그룹별 EXT 읽기 지연 민감도와 Vela 비용 모델

지시: ChatGPT "Stage 6G-X_LAT 공식 지시"(사본 `docs/plan/stage6g_xlat_directive_chatgpt.txt`, 답변 전문 `docs/plan/stage6f0_reply_xlat_chatgpt.txt`). 6F-0 결과 `9a859c3`/`800cbb7`, X3 `65c9b0e`.
이 계약, 판정 코드 `host/analysis/stage6gxlat.py`, Vela 예상값 `predictions.json`, 테스트, mutation은 보드 실행 전에 커밋한다. 기존 결과는 바꾸지 않는다.

## 사전 노출과 설계의 성격

- 대상 그룹과 가설은 6F-0에서 기존 X3 L500 결과(그룹 NPU_ACTIVE·Vela 비율)를 본 뒤 정했다. 따라서 L500 값은 설계 근거다.
- 전향 검증은 L250·L1000 신규 측정과, 측정 전에 고정한 Vela 예상 변화량의 비교다.

## 1. 측정 조건 (TA 외 고정)

- 이미지: `f0baf8c` 소스를 `build_driver_runner.sh`로 빌드하고, `DRV_EXTRA_CMAKE=-DEXT_RLATENCY=L`만 바꾼다(E2B 방식, 새 펌웨어 기능 없음).
  - **L500 재빌드 = X3 이미지와 바이트 동일**(boot `3b4af743`, bram `9b1844a3`, images.txt `af688281`).
  - L250 bram `4f5f54aa…`, L1000 bram `7004c530…`.
  - L500 대비 **bram 2바이트(오프셋 638124–638125, `0x01F4` → `0x00FA` / `0x03E8`)만 다르다**. boot.bin과 images.txt는 같다.
  - ddr.bin은 X3와 같은 16 B 0(`374708ff`)이다.
- **TA**: profile 1(MLEK sys_dram_mid)에서 TA_EXT RLATENCY만 250 또는 1000으로 바꾼다. 나머지 TA 23개 레지스터는 X3 기준(`caps_14077be.json`)과 같아야 한다. boot마다 RUN 전 capabilities readback으로 확인한다.
- **같게 두는 것**: placement 0, X3 직렬 워크로드 B2/B3/B4(DRWL sha256 = X3 manifest), WAIT_WFE, pass A·B·C(X3 ids), boot당 3 pass × (1 warm-up + 4 측정).
- **L500**: X3 boot 497–499(kws), 502–504(ad) 자료를 재사용하고, X3 자신의 identity로 다시 판정한다.
- **MAC_STALLED_BY_IB(55)**: X3 pass A에 이미 들어 있다(driver event 55 `mac_stalled_by_ib`, X3에서 측정됨). 새 Pass는 만들지 않는다.

## 2. boot 계획 (505–516, 순서 고정, 12 boot / 180 RUN)

| boot | 모델 | 그룹(워크로드) | L |
|---|---|---|---|
| 505 | kws | G_V (x3_kws_B2) | 250 |
| 506 | kws | G_V | 1000 |
| 507 | kws | G_0 (x3_kws_B3) | 1000 |
| 508 | kws | G_0 | 250 |
| 509 | kws | G_R (x3_kws_B4) | 250 |
| 510 | kws | G_R | 1000 |
| 511 | ad | G_V (x3_ad_B2) | 1000 |
| 512 | ad | G_V | 250 |
| 513 | ad | G_0 (x3_ad_B3) | 250 |
| 514 | ad | G_0 | 1000 |
| 515 | ad | G_R (x3_ad_B4) | 1000 |
| 516 | ad | G_R | 250 |

- **세션 순서**: 지연이 바뀔 때마다 restore 후 deploy한다. deploy 순서는 L250(505) → L1000(506–507) → L250(508–509) → L1000(510–511) → L250(512–513) → L1000(514–515) → L250(516)이고, 그 뒤 restore와 postflight다.
- **run root**: 지연별로 둔다(`evsweep_xl250_run`, `evsweep_xl1000_run`).

## 3. boot 유효성과 중단 (`boot-check`, X3 `config_result` 그대로 + 조건별 identity)

- **CONFIG_MISMATCH**: 다음 중 하나라도 맞지 않을 때.
  - workload sha256, 조건별 이미지 digest, boot 번호(위 표), condition.
  - TA 레지스터 전체: 기준과 같고 ext rlatency만 L이어야 한다.
  - NPU MAC 수, record schema 5, placement 0, pmu_flags, PMCR.mask_en, IRQ.
- **INVALID_OUTPUT**: 다음 중 하나라도 맞지 않을 때.
  - golden(OUTPUT_MATCH, mismatch 0).
  - output CRC가 X3 원본 B0(kws 487, ad 500)의 CRC와 같을 것.
- **INVALID_PMU / UNSTABLE**: X3 Amendment C 그대로다.
  - MAC·DPU는 RUN마다 같아야 한다.
  - pass A 대 B/C NPU_ACTIVE.
  - pass A range ≤ max(5 %, cap). cap은 kws 2,423, ad 2,596이다.
- **중단**: boot-check가 VALID가 아니면 세션을 멈춘다(rc 1 → RESTORE). 추가 boot나 재측정은 없다.

## 4. Vela 예상값 (측정 전 고정 → `predictions.json`, `vela/xlat_vela.json`)

- **컴파일**: Vela 5.0.0, MLEK 옵션, `Ethos_U85_SYS_DRAM_Mid_1024` 사본에서 `Dram_read_latency`만 250 / 500 / 1000으로 바꾼다. 기본 컴파일도 함께 남긴다(`host/container/xlat_vela.py`).
- **L500**: per-layer CSV가 X3 `evidence/stage6ex3/vela`와 바이트 동일하다(kws·ad).
- **명령 스트림 비교 가능성**:
  - ad: L250·L500·L1000 모두 Vela 출력이 같다(`b83f28f2`, cms `093dcda9`).
  - kws: L250·L500은 같다(`f9575c36`, cms `21564a54`).
  - **kws L1000은 Vela가 다른 스트림을 만든다**(cms `af4a80d3`). 측정 스트림의 L1000 비용 추정이 아니므로, 지시 §4에 따라 kws의 L1000 Vela 비교는 인정하지 않는다(`vela_comparable` false).
- **그룹 예상값**:
  - V_group(L) = Σ per-layer Op Cycles(= max(NPU, SRAM AC, DRAM AC))이다. 그룹의 TFLite 연산은 X3 `tflite_groups`로 정한다.
  - 지배 항은 지연마다 따로 기록한다.

| 그룹 | V(250) | V(500) | V(1000) | ΔV 250→500 | ΔV 500→1000 | ΔV 250→1000 | L500 DRAM 지배 비중 |
|---|---|---|---|---|---|---|---|
| kws G_V | 16,851 | 23,436 | (46,872, 비교 불가) | 6,585 | — | — | 1.00 |
| kws G_0 | 22,056 | 23,261 | (25,753, 비교 불가) | 1,205 | — | — | 0.00 |
| kws G_R | 43,983 | 55,551 | (103,911, 비교 불가) | 11,568 | — | — | 0.82 |
| ad G_V | 69,165 | 71,857 | 110,154 | 2,692 | 38,297 | 40,989 | 0.11 |
| ad G_0 | 19,605 | 21,874 | 43,749 | 2,269 | 21,875 | 24,144 | 1.00 |
| ad G_R | 45,443 | 54,597 | 94,489 | 9,154 | 39,892 | 49,046 | 0.26 |

- **지배 항(연산 순서, N/S/D)**:
  - kws G_V: NNN → DDD(500) → DDD(1000).
  - ad G_V: NNNN → NNND → DDDD.
  - ad G_0: N → D → D.
  - ad G_R: SNNNNNNN → SNNDDNNN → DDDDDNND.

## 5. 판정 규칙 (그룹별, 그 다음 전체)

**기호**: B_L = pass A NPU_ACTIVE 측정 RUN 중앙값, r_L = range. L500 값은 X3다.

**허용폭**: tol(a, b) = max(cap_model, r_a + r_b, 0.01·max(B_a, B_b)).

**Compute Invariance**(그룹): MAC(48)·DPU(51) 중앙값이 L250·L1000에서 L500 대비 1 % 안이다.
- 깨지면 그 그룹은 `CONFOUNDED`이고 비교에서 뺀다.
- 전체: 모두 성립하면 SUPPORTED, 하나라도 깨지면 REFUTED, 판정할 그룹이 없으면 INSUFFICIENT_EVIDENCE.
- 전송량(130, 135, 386, 391)의 1 % 일치(`traffic_comparable`)는 기술한다.

**Latency Response**(그룹):
- ΔB = B1000 − B250.
- |ΔB| > tol(250, 1000)이면 `SENSITIVE`, 아니면 `NOT_DETECTABLY_SENSITIVE`.
- 그룹 boot가 하나라도 VALID가 아니면 `INSUFFICIENT_EVIDENCE`.
- 전체: 하나라도 SENSITIVE이면 SENSITIVE.
- L500으로 기울기 (B500 − B250)/250과 (B1000 − B500)/500을 기술한다(비선형성).

**Vela Term Fidelity**(그룹):
- **비교 구간**: Vela L250·L1000이 모두 비교 가능하면 250→1000, kws처럼 L250만 가능하면 250→500(L500 = X3 보드)이다.
- ΔB_seg, ΔV_seg, tol_seg = tol(구간 양끝).
- 판정(위에서부터):
  1. `INSUFFICIENT_EVIDENCE`: tol_seg > 0.5·max(|ΔV_seg|, |ΔB_seg|)(E2B 식별력 규칙).
  2. `DIRECTION_AND_MAGNITUDE_CONSISTENT`: |ΔB_seg − ΔV_seg| ≤ 0.15·|ΔV_seg| + tol_seg(E2B Primary).
  3. `DIRECTION_ONLY_CONSISTENT`: |ΔB_seg|, |ΔV_seg| 모두 > tol_seg이고 부호가 같다.
  4. `INCONSISTENT`: 그 밖.
- Prediction_Error_Delta = ΔB_seg − ΔV_seg.
- **전체**: 판정 가능한 그룹 중 하나라도 INCONSISTENT이면 INCONSISTENT. 모두 D&M이면 D&M. 그 밖은 DIRECTION_ONLY_CONSISTENT. 판정 가능한 그룹이 없으면 INSUFFICIENT_EVIDENCE.
- 지배 항 분류 일치만으로는 Fidelity를 주지 않는다.

**H-L2 Term Dominance**:
- L500 Vela DRAM 지배 비중이 ≥ 0.5인 그룹(kws G_V·G_R, ad G_0)의 상대 반응 ΔB/B250이 다른 그룹(kws G_0, ad G_V·G_R)보다 모두 크면 SUPPORTED, 아니면 REFUTED다.
- 한쪽이 비면 INSUFFICIENT_EVIDENCE다.
- NPU 지배 그룹의 반응을 0으로 가정하지 않는다.

**Pipeline Mechanism**:
- SENSITIVE 그룹마다 WD_STALLED(81)·MAC_STALLED_BY_IB(55)·EXT 읽기 주소 핸드셰이크 정체(387) 중 하나 이상의 L250→L1000 변화가 ΔB와 같은 부호이고 |ΔB|의 0.5 이상이면 `PARTIALLY_SUPPORTED`, 아니면 `MECHANISM_UNRESOLVED`다.
- 관측적 관계일 뿐, 대기시간 분해가 아니다(387은 서비스 대기시간이 아니다).

**Measurement**: 12 boot 모두 VALID이면 VALID, STOP 상태가 있거나 VALID가 없으면 MEASUREMENT_INVALID, 그 밖은 PARTIAL_VALID.

## 6. 해석 한계

- 직렬 그룹 비용을 원본 비직렬 실행의 연산별 시간으로 옮기지 않는다.
- TA 지연 민감도를 실제 DRAM 대기시간으로 환산하지 않는다.
- 인위적인 지연 에뮬레이션에 대한 Vela 비용 모델 검증이다.
- 결과와 무관하게 Amendment를 자동으로 추가하지 않고, 종료 후 7개 모델 연구로 돌아간다.

## 7. 검증

- 테스트 `test_stage6gxlat`(손으로 쓴 fixture), mutation 전부 KILLED, `test.sh` ALL PASS.
- Preflight(이미지·DRWL·caps digest, 보드 staging, boot 505–516 미사용, 세션 검사).
- 판정 2회 바이트 동일, 기존 결과 불변. 로컬 커밋만 한다.
