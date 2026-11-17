# Stage 6B-E2E-D 계약 — Weight/Scale 배치(B3 대 B3w) × EXT 읽기 지연

지시: Stage 6B-E2E-D 공식 지시(2026-11-18). 이 계약, 판정 코드, manifest, 실행 순서, 테스트, 세션 파일은 **보드 측정 전에** 커밋한다.
기존 데이터와 판정(E2E-C까지)은 바꾸지 않는다. 승인 상한은 5 boot / 50 RUN이다. Pass C, E3, Stage 6C, 다른 보드 측정은 하지 않는다.
결과는 NPU 내부 실행시간(NPU_ACTIVE)이다. CPU staging과 가중치 복사를 포함한 시스템 latency가 아니다.

## 0. 선행 커밋과 Phase 0 확인

**`14077be` — runner placement 2(`PLACEMENT_SRAM_W`)**
- QBASE 호출(index −1) 때 PMU를 arm하기 전에, region 0(가중치·scale)을 SRAM 사본으로 한 번 복사하고 D-cache를 clean한 뒤 바이트 비교한다.
- 이후 index 0만 사본 주소로 remap하고, region 0을 SRAM 포트로 보낸다. QBASE와 QCONFIG는 바꾸지 않는다.
- 사본이 없으면 placement 1로 동작한다. 이때 REGIONCFG는 0x553이 되고 REGIONCFG_MATCH 플래그가 꺼진다.
- `probe.base[0]`은 BASEP0에 실제로 쓴 주소다. 기록 schema(4)는 바뀌지 않는다.
- 공유 REGIONCFG 표는 placement 2를 0x150(n_base 5) / 0x550(n_base 6)으로 안다.
- 회귀: identity 판정 9개 출력이 바이트 동일, 함수 단위 회귀가 `6614ce8` 결과와 동일, E2E-B 판정 불변. 관련 mutation 하네스 모두 KILLED.

**재현 기준(E2E-B, TA profile 1)**
- B3 = `e2eb_b3` `7b2cedd5…`, NPU_ACTIVE 60,320(range 1,197) / 72,526.5(1,189), LE 12,206.5.
- EXT read 11,322 beat / 793 트랜잭션, MAC 20,736.
- 출력 golden `b9341e6f…`. 안정성 기준은 기존과 같다(pass A range ≤ 5 %, pass A 대 B).

**region 0의 내용(정적)**
- 모델 offset `0x420`에서 시작하는 flatbuffer 벡터 하나(90,256 B, sha256 `c2fe2704…`)다. Vela flash 텐서이며, E2E-A region 표상 WEIGHT·SCALE만 region 0을 쓴다.
- command stream(628 B)은 모델 offset `0x164f0`으로 region 0(`0x420–0x164b0`) 밖이다. 따라서 가중치·scale 외의 데이터는 함께 옮겨지지 않는다.

## 1. 이미지 (`image_l500/`, `image_l1000/`, 컨테이너 빌드 `14077be`)

| | boot.bin | bram.bin | ddr.bin | images.txt |
|---|---|---|---|---|
| L500 | `751a1bf2…` | `ec0e8c3b…` | `374708ff…`(16 B 0, 기존과 같음) | `af688281…` |
| L1000 | `751a1bf2…` | `ca7d2e49…` | 같음 | 같음 |

- L500은 두 번 빌드했고 바이트 단위로 같다. L1000은 L500과 bram offset 637989–637990 두 바이트(`0x1F4→0x3E8`, EXT RLATENCY)만 다르다.
- 기존 이미지(`70090f1`)와의 ELF 심볼 비교(`image_l500/old_70090f1.nm`, `new.nm`; 심볼 1,711 → 1,722) 결과:
  - 바뀐 것: `ethosu_address_remap`, `placement_config_select`, `placement_regioncfg`, `runner_poll`(load 경로).
  - 새로 생긴 것: `placement_weights*`, `placement_effective`, `weights_sync`, 정적 변수 6개.
  - 나머지 심볼(PMU 세션, TA 설정, 측정창, 드라이버)은 이름과 크기가 같다.
- build_id(0x44525652)와 기록 schema는 같다. 따라서 capabilities 기준(`caps_l500/l1000.json`)도 같다.
- 빌드 게이트는 OK다: 훅이 runner 것이고, SRAM 심볼은 `cache_arena`뿐이다.

## 2. 구성 (`workloads/`)

| 조건 | DRWL | placement | graph IO | 중간 텐서 | 가중치·scale (region 0) | command stream |
|---|---|---|---|---|---|---|
| REF | `s4c2_conv_cin48` `6eb390be…` | 0 | — | — | — | — |
| B3 | `e2eb_b3` `7b2cedd5…` | 1 | SRAM `0x31076770` | SRAM fast | DDR/EXT `0x70000420` | DDR/EXT |
| B3w | `e2ed_b3w` `51ff7a4a…` | 2 | SRAM | SRAM fast | **SRAM 사본 `0x31280420`** | DDR/EXT |

- B3w DRWL은 B3와 offset 28(word 7) 한 바이트(1→2)만 다르다. 따라서 command stream, kernel 3개, block·ublock·traversal, 양자화·activation, 입력, golden이 모두 같다.
- 기대 REGIONCFG(n_base 6): B3 0x553, B3w 0x550. QCONFIG는 3.
- SRAM 사본 `0x31280420–0x312964B0`:
  - 창 끝 `0x31400000` 안이다.
  - arena(`0x31076770–0x31276770`), driver fast memory(`0x31000000–0x31060000`)와 겹치지 않는다.
  - staging(`0x90000000`)은 DDR이다.

## 3. 판정 (`host/analysis/stage6be2ed.py`)

**유효성**: E2E-B와 같다(공유 identity, 이미지, TA readback, 출력, PMU, 안정성).

추가 layout 검사(RUN마다):
- placement 2:
  - `weights_where`: BASEP0 = manifest `weights_at`.
  - `weights_inside`: SRAM 창 안.
  - `weights_disjoint`: arena·fast memory와 겹치지 않음.
- placement 0/1: `weights_ddr`(DDR 모델 안).

**Measurement Validity**: VALID / PARTIAL_VALID / MEASUREMENT_INVALID(E2E-B 규칙, MAC = 20,736).

**B3 동등성(새 이미지, 지연별)**
- |B3(L) − E2E-B(L)| ≤ max(1 %, range_E2E-B + range_now)이고, 전송량(SRAM/EXT read·write beat·트랜잭션)이 E2E-B와 정확히 같아야 한다.
- 두 지연 모두 맞으면 `B3_REPRODUCED`, 하나만 맞으면 `B3_PARTIAL`, 둘 다 아니면 `B3_NOT_REPRODUCED`.
- 세션: boot 464 뒤 `b3-gate` L500이 FAIL이면 세션을 멈춘다.

**Remap Validity**(B3w, VALID이고 MAC이 일치하는 지연별)
- EXT read beat ∈ [39, 64](command stream 628 B = 39.25 beat, fetch 반올림으로 1 KiB까지).
- EXT write = 0.
- SRAM read 증가 = 11,282 beat(가중치 174,752 + scale 5,760 B) ±1 %. 기준은 같은 지연의 B3, 없으면 E2E-B B3.
- read 합(SRAM + EXT)은 B3 ±1 %.
- 두 지연 모두 통과하면 `WEIGHT_SCALE_REMAP_CONFIRMED`, 하나만이면 `REMAP_PARTIAL`, 없으면 `REMAP_INVALID`.
- remap이 실패해도 지연 민감도만으로 가중치 경로 효과라고 주장하지 않는다.

**Residual Latency**
- 정의: LE(B) = B(1000) − B(500). tol_LE(B) = max(0.01·B(500), r(500) + r(1000)). Residual_Ratio R = LE_B3w / LE_B3. Weight_Path_Removal_Effect = LE_B3 − LE_B3w.
- 사용 조건: 4개 B 구성 모두 VALID이고 MAC이 일치하며, `B3_REPRODUCED`, `WEIGHT_SCALE_REMAP_CONFIRMED`, LE_B3 > tol_B3. 아니면 `INSUFFICIENT_EVIDENCE`.
- 판정:
  - `WEIGHT_PATH_DOMINANT_RESPONSE`: R ≤ 0.25이고 감소량 LE_B3 − LE_B3w > tol_B3 + tol_B3w.
  - `RESIDUAL_NON_WEIGHT_RESPONSE`: R ≥ 0.75이고 LE_B3w > tol_B3w.
  - `MIXED_RESPONSE`: 0.25 < R < 0.75이고, 감소량과 남은 반응이 둘 다 위 기준을 넘음.
  - `INSUFFICIENT_EVIDENCE`: 그 밖.
- R의 잡음 구간 [(LE_w − t_w)/(LE_3 + t_3), (LE_w + t_w)/(LE_3 − t_3)]은 보고만 한다.
- 이 규칙은 보드 실행 전 테스트에서 바꿨다. 처음 쓴 규칙은 "구간 전체가 한 범주 안"이었는데, E2E-B 수준의 잡음(tol ≈ LE의 20 %)에서는 R = 1.0도 [0.67, 1.49]가 되어 NON_WEIGHT에 도달할 수 없었다. 그래서 동결 전에 위처럼 고쳤다.
- R은 지연 민감도 변화의 비이며, WD 대기의 기여율이 아니다. R이 커도 command fetch 지배라고 확정하지 않는다(다른 경로와 의존성을 배제하지 못함).

**기술 보고**:
- Weight placement effect B3(L) − B3w(L)와 tol.
- B3w의 남은 반응(command 경로와 관련된 반응, 원인 배정 없음).
- MAC, DPU, AO, WD, WD_STALLED, 전송량, 트랜잭션 변화.

**Pipeline Mechanism**: `MECHANISM_UNRESOLVED`로 고정한다. 처리부별 지연 기여를 식별하는 계측이 없으므로 `MECHANISM_PARTIALLY_SUPPORTED`에 도달할 수 없다.

**Vela**: B3w는 `NO_COMPARABLE_VELA_ESTIMATE`이다. 다른 구성의 Vela 값을 대입하지 않는다. 기존 B0 과소예측과 E2D 배치 효과에 연결해 기술만 한다.

**금지 해석**:
- WD_STALLED 감소를 가중치 대기시간으로 치환하지 않는다.
- 카운터를 합산해 NPU_ACTIVE를 배분하지 않는다.
- R을 WD stall 비율로 읽지 않는다.

## 4. 측정 (5 boot / 50 RUN, warm-up 10, 측정 40, TA profile 1)

| 순서 | boot | 조건 | 이미지 |
|---|---|---|---|
| 1 | 463 | REF | 새 L500 |
| 2 | 464 | B3 | 새 L500 (+ b3-gate) |
| 3 | 465 | B3w | 새 L500 |
| 4 | 466 | B3w | 새 L1000 |
| 5 | 467 | B3 | 새 L1000 |

- boot마다 pass A·B 각 5 RUN(1 + 4), `OUTPUTS=1 STOP_ON_INVALID=1`, ids·conditions는 E2E-B와 같다.
- 이미지 교체는 한 번이다. boot 번호는 preflight에서 보드 최대 host_boot_index(462)로 확인한다.

## 5. 중단·복원

- REF 게이트 FAIL, boot-check rc 1(CONFIG_MISMATCH/UNMEASURED), b3-gate FAIL이면 세션이 멈추고 카드를 복원한다.
- 재측정·대체·추가 boot는 없다.
- 종료 때 RESTORE VERIFIED와 postflight를 기록한다.

## 6. 검증

- 테스트 `test_stage6be2ed`(37개)와 펌웨어 테스트(placement probe, sim, contract).
- mutation `mutate.py` 58/58 KILLED(판정 45개 + 펌웨어 13개).
- `test.sh` ALL PASS. 로컬 커밋만 한다.
