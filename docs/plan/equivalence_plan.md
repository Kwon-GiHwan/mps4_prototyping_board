# Runner ↔ MLEK 실행 환경 동등성 (E1–E5) — 코드·기존 데이터 분석과 검증 계획 (2026-11-09)

브랜치 `refactor/firmware-modules`(현재 측정 이미지 `d0cd4775`와 기존 데이터가 있는 곳). **TA profile 1**, FI101
Ethos-U85 1024 MAC. Owner 2026-11-09: 동등성 검증을 최우선으로 하고, 이 문서는 코드·기존 데이터 분석과 계획까지만 다룬다.
보드 이미지 변경과 신규 측정은 계획 검토 뒤에 한다. 열린 항목의 원래 정의: `evidence/runner_gap/open_equivalence_items.md`.

**관리 분리:** 이 문서의 대상은 실행 환경 동등성이다. 다른 두 계획과의 관계는 아래와 같다.
- **Stage 2B-3(연산별 PMU 귀속, `stage2b3_plan.md`):** 그 데이터·판정·계약은 바꾸지 않는다.
- **Stage 2B-4(QREAD, 브랜치 `feat/stage2b4-qread`):** 이 결과로 일반화 범위(§6)만 정한다.
- **7개 모델 결과:** 2B-0b, 2B-2, 2B-3 pilot과 부록 1의 결과를 그대로 보존한다.

표기는 다음과 같다.
- [코드]: 소스에서 확인한 것.
- [데이터]: 기존 측정에서 확인한 것.
- [미확인]: 보드나 MLEK 실행이 있어야 확인되는 것.

## 1. 입력 쪽 동일성 — command stream, 입력, 메모리 배치, Vela, TA

| 항목 | MLEK (`b2c0bb2`, core driver) | runner | 판단 | 근거 |
| --- | --- | --- | --- | --- |
| Vela 버전·옵션 | 5.0.0, ethos-u85-1024, Performance, Dedicated_Sram, `Ethos_U85_SYS_DRAM_Mid_1024` | 같은 값(`config/fi101_s013.json`) | 같음 | [코드] |
| Vela 출력 → command stream·가중치 | MLEK 빌드 | 같은 Vela 출력에서 추출 | **같음 (kws·ad·mobilenet은 `vela_sha256` 일치를 기록)**; 나머지 4개는 "7개 모두 같은 바이트" 기록(`open_equivalence_items.md`) | [데이터] |
| blob 안 cms/const와 NPU가 받은 포인터 | — | blob cms/const sha256은 기록, BASEP·QBASE·QSIZE 판독값은 미기록 | **E3 미완** | [미확인] |
| 입력(IFM) | MLEK 내장 샘플 | kws·ad·rnnoise·vww4·yolo·w2l: seed-1 난수; mobilenet: MLEK 입력(amendment 1) | **다름(6개 모델)** — beat는 입력과 무관하게 같았다(§3) | [데이터] |
| cmd·const·arena | DDR(`nn_model` 0x70000000, arena 뒤), EXT 포트 | DDR `0x70100000`부터, EXT 포트 | 같은 메모리·포트, 오프셋만 다름 | [코드] |
| fast scratch | on-chip SRAM `0x31000000`, 0x60000 B, SRAM 포트 | on-chip SRAM `0x31100000`(knob), SRAM 포트 | 같은 메모리·포트, **base 다름** — runner 코드·데이터·스택이 0x31000000–0x31029FC0에 있어 같은 주소를 쓸 수 없음 | [코드] |
| TA | `ta_config_u85_sys_dram_mid` | profile 1(같은 값 표), RUN마다 되읽음 | 값은 같음; **EXT MAXR: MLEK 64 vs runner 0** — 6비트 필드면 같은 상태(가설, E2) | [코드]/[미확인] |

## 2. 실행 경로 차이 — NPU 실행 특성에 영향이 있을 수 있는가

분류: **(가) 작업 중 NPU에 작용할 수 있음** / **(나) 작업 밖 또는 계측 창에만 작용** / **(다) 이미 맞춤**.

| 항목 | MLEK | runner | 분류 | 상태 |
| --- | --- | --- | --- | --- |
| soft reset + PROT(보안·특권) | 작업마다 soft reset, CPL=privileged, CSL=secure | reset 없음(vendor `TEST_PROT=0`) | (가) 버스 전송 보안·특권 레벨, 이전 RUN의 내부 상태 | 미검증 (E5) |
| POWER_CTRL | 0 | knob 0(vendor 2를 hook으로 대체), CPM seam에서 되읽음 | (다) | 맞춤; 2 vs 0 A/B에서 차이 없음(boots 37–42) |
| CPU 대기 | `__WFE()`, CPU 쉼 | busy loop(`irq_triggered` 폴링) | (가) CPU 버스 트래픽 — 코드·데이터·스택이 fast scratch와 **같은 on-chip SRAM**에 있음 | 미검증 (E5) |
| D-cache | on | off | (가) 위와 같은 이유로 CPU의 SRAM 접근량이 달라짐 | 미검증 (E5) |
| CFG_SRAM_CAP / CFG_EXT_CAP | 쓰지 않음 | vendor가 0x21F3F 씀 | (가) 쓰기가 실제로 반영된다면; 공개 헤더상 읽기 전용 | 미검증 (E1) |
| REGIONCFG / QCONFIG / MEM_ATTR | 0/0/4/4, attr 3/1 선택 | 0/0/4/4, attr 2/0 선택 | (다) 선택된 값이 같음(MEM_ATTR0=1, 2=3인 동안) | 맞춤, RUN마다 되읽음 |
| AXI_SRAM / AXI_EXT | 0x20F0B / 0x21F3F | 같은 값(knob) | (다) | 맞춤, 되읽음 |
| NPU 시작 | `(CMD & PWR_CLK) | run` | `CMD | 1`(q 비트 0) | (다) 효과 같음 | 정적 |
| IRQ 후 | clear_irq, 전원 유지 → 해제 | CMD=2, 0, 0xC | (나) 작업 뒤 | — |
| PMU 창 | `ethosu_inference_begin/end` | 무장 → CPM seam 판독; PMCCNTR에 staging 포함 | (나) **IDLE·TOTAL은 비교 불가**(§3), ACTIVE·beat는 NPU가 셀 때만 증가 | E4 |
| 부팅당 추론 | 1회(B1–B3 = 3 boot) | 10 RUN(2 warm-up) | (나) 첫 추론 vs 반복 추론 상태 | 기술용 |
| 출력 검사 | 없음(profiler) | RUN마다 OFM 바이트 비교 | — | runner가 더 엄격 |

작업 중에 작용할 수 있는데 아직 검증하지 않은 것은 네 가지다: soft reset/PROT, CPU 대기 방식, D-cache, CAP 쓰기.
fast scratch base 차이는 SRAM0/SRAM1 hash 매핑이 다를 수 있다는 것만 남는다(E5, 포트별 beat로만 볼 수 있음).

## 3. 기존 데이터로 확인한 것 (`results/runner_mlek_equivalence/`, `host/analysis/equiv_existing.py`, POST_HOC_DESCRIPTIVE)

MLEK 보드 기준값은 **kws·ad·mobilenet 3개 모델**뿐이다(`docs/reference/mlek_board_reference.json`, B1–B3,
profiler 카운터 ACTIVE + beat 4종). runner 쪽은 이미지 4개다. 측정 RUN(warm-up 제외)과 유효 RUN만 썼다.

| 지표 | 결과 |
| --- | --- |
| SRAM_RD / SRAM_WR / EXT_RD / EXT_WR beat | 3개 모델 × 이미지 2개(`2c2fa435`, `2bb04bfa`)에서 **MLEK B1–B3와 정확히 같은 값**(RUN 사이 변화 없음). 입력이 다른 kws·ad에서도 같음. `d0cd4775`는 2B-0b·2B-3에서 beat 세트를 재지 않음 |
| NPU_ACTIVE | runner 중앙값 − MLEK 중앙값: kws −0.51 … −0.79 %, ad −0.10 … +0.30 %, mobilenet −0.04 … +0.04 %. 11개 비교 중 9개가 MLEK B1–B3 범위 안. 범위 밖 2개: kws `d0cd4775`(−0.79 %), ad `d0cd4775` 2B-0b(−0.10 %, MLEK 최소값보다 109 사이클 아래). runner의 RUN 범위는 모두 MLEK 값과 겹침. **kws는 이미지 셋 모두 MLEK보다 낮은 쪽**(−0.5 … −0.8 %) |
| MAC_ACTIVE 등 다른 이벤트 | **MLEK 쪽 값이 없음.** MLEK profiler는 이벤트 목록이 소스에 고정(`ethosu_profiler.c`: ACTIVE, SRAM/EXT beat)이라, 얻으려면 MLEK HAL 소스를 바꿔야 함 → owner 결정 사항(§5 C3) |
| IDLE / TOTAL | 비교 불가: MLEK IDLE ≈ 5.9 k, runner IDLE은 staging이 포함된 창이라 수백만(E4) |
| 출력 | **mobilenet만 MLEK FI101 출력과 같은 입력에서 바이트 일치**(amendment 1 golden). kws·ad·rnnoise는 tflite_runtime golden과 바이트 일치(MLEK 출력과는 비교 안 됨). vww4·yolo·w2l은 tflite와 1 / 955 / 2 바이트 다름, MLEK golden 없음 |
| vww4·rnnoise·yolo·w2l의 카운터 | MLEK 쪽 값 없음 → 이 4개 모델은 현재 어떤 지표도 MLEK와 비교되지 않음 |

이미지 사이 재현: x1 control(boots 80–82)과 Stage 0 S0-4는 `2c2fa435`·`38ce118c`·`2bb04bfa` 사이에서 mac_active와
beat 4종이 같음을 보였다. `d0cd4775`는 2B-0b에서 `npu_active`만 이전 이미지 범위와 비교했다.

**정정(이 분석 중 발견):** 2B-3 pilot 계약과 보고에서 "ad, mobilenet, rnnoise golden = MLEK FI101"이라고 썼다.
실제로 MLEK FI101 golden은 **mobilenet만**이고, ad·rnnoise는 tflite_runtime(seed-1 입력) golden이다. pilot의
OFM 일치 결과 자체는 맞다. 근거는 `evidence/stage1/contract.md` 39–41행과 `evidence/x1_mlek_models/manifest.x1.json`.
정정은 pilot 계약 끝에 덧붙인다(원문은 고치지 않음).

## 4. 동등성 판정 기준 (제안 — 보드 전에 계약으로 고정)

판정은 세 가지다: `EQUIVALENT` / `NOT_EQUIVALENT` / `UNPROVEN`. 판정 단위는 (모델, 지표)이다.

| 지표 | 기준 | 데이터가 없을 때 |
| --- | --- | --- |
| 정적 항목(§1·§2의 (다)) | 값·해시가 같고, 양쪽에서 되읽은 값이 같음 | 되읽지 못한 쪽이 있으면 `UNPROVEN` |
| beat 카운터 | 정확히 같음 (결정적인 값) | MLEK 쪽 값이 없으면 `UNPROVEN` |
| NPU_ACTIVE | \|runner 중앙값 − MLEK 중앙값\| ≤ max(MLEK B1–B3 범위, runner 측정 RUN 범위). 2B-0b와 같은 방식이고, 양쪽 지터를 모두 허용함 | 같음 |
| 다른 PMU 이벤트 | MLEK 쪽 값이 있을 때만 위와 같은 규칙 | `UNPROVEN` (C3을 정하기 전까지 MAC_ACTIVE 포함) |
| 출력 | MLEK FI101 출력과 **같은 입력에서** 바이트 일치 | tflite와만 일치하면 MLEK 동등성은 `UNPROVEN` |
| E5 차이 하나 | 변형 vs 같은 이미지의 기준 arm이 2B-0b 허용오차(결정적 0.1 %, 지터 max(1 %, RUN 폭)) 안이면 그 지표에 대해 `INERT`, 밖이면 `EFFECTIVE`(효과를 기록) | — |

**동등 주장의 범위:** "모델 Y, 지표 X에서 runner = MLEK"는 다음 세 조건이 모두 성립할 때만 쓴다.
1. (Y, X)가 `EQUIVALENT`이다.
2. Y의 출력이 `EQUIVALENT`이다.
3. (가)로 분류한 차이 네 가지가 X에 대해 모두 `INERT`이다.

이 가운데 하나라도 빠지면 지금과 같이 "측정한 모델·조건에서 재현"으로만 쓴다.

## 5. 최소 보드 실험 설계 (미승인 — 비용은 2B-3 실측 부팅 시간 기준)

부팅당 시간 실측(TA profile 1): rnnoise 3.0분, yolo 3.8분, ad 3.9분, mobilenet 11.9분, wav2letter 약 17분(2B-3 부록 1).
kws·vww4는 3–5분이다. 7개 모델을 한 번씩 돌리는 데 약 50분이 든다.

### A. runner만으로 닫을 수 있는 항목 — 진단 이미지 1개, 부팅 1–2번(약 10분)

| # | 대상 | 방법 | 닫히는 조건 |
| --- | --- | --- | --- |
| A1 | E1 CAP | 부팅 뒤 첫 RUN에서 vendor가 쓰기 **전**·쓴 **후**·CPM seam에서 `CFG_SRAM_CAP`/`CFG_EXT_CAP`를 읽어 기록. 첫 RUN에서 쓰기 전에 읽은 값이 reset 값이고, MLEK는 이 값을 그대로 쓴다 | 쓰기 전 값 = 쓴 뒤 값이면 쓰기가 효과 없음(`INERT`). 다르면 A/B 대상(B4) |
| A2 | E2 TA EXT MAXR | TA profile 1과 같고 EXT MAXR만 64인 profile을 추가해 쓰고 되읽음 | 64를 썼는데 0이 읽히면 MLEK 상태 = runner 상태 |

firmware 변경이 필요하다: 판독 지점 추가, TA 표 한 줄. 이미지가 바뀐다. 부팅 1번을 기준 비교에 쓴다(새 이미지의 mac_active·beat가 `d0cd4775`과 같은지, S0-4 방식).

### B. E5 차이를 하나씩 검증 — 새 이미지 하나에 knob 4개, 기준은 같은 이미지에서 knob OFF

| # | 변수 (knob 하나) | 효과가 예상되는 이유 |
| --- | --- | --- |
| B1 | CPU 대기: busy loop → WFI(vendor `BUSY_SLEEP` 경로 대신 `__wfi`) | CPU가 on-chip SRAM을 계속 읽음 |
| B2 | D-cache on(출력 영역은 기존 poison clean/invalidate 경로로 정리) | 같은 이유 |
| B3 | 작업 전 soft reset + PROT(driver와 같은 순서·값) | 보안·특권 레벨, 내부 상태 |
| B4 | CAP 쓰기 생략 | A1에서 쓰기가 효과 있다고 나올 때만 |

- 한 변형에 7개 모델을 1번씩 돈다. 세트는 A(npu_active, mac_active, beat 4종 + 2B 기본 이벤트), 10 RUN이다. 약 50분.
- 기준 arm(knob OFF)도 7개 모델에 같은 시간이 든다. B1–B3과 기준을 합쳐 약 3.3시간이다.
- **최소안:** B1·B2만, MLEK 기준값이 있는 3개 모델(kws·ad·mobilenet)에서 돌린다. 기준 + 2 변형 = 9번, 약 1시간.
- fast scratch base(0x31000000)는 runner 이미지가 그 주소에 있어 실행할 수 없다. `NOT_EXECUTABLE`로 기록하고, 포트별 beat로 간접 비교만 한다.

### C. MLEK 쪽 — MLEK 실행을 새로 승인받아야 함(CLAUDE.md), `inference_runner`는 수정하지 않음

| # | 내용 | 비용 |
| --- | --- | --- |
| C1 | vww4·rnnoise·yolo·w2l을 MLEK on FI101로, **blob과 같은 IFM**으로 실행: OFM dump(golden, `mlek_golden.py` G1–G5) + profiler 카운터 | `open_equivalence_items.md` 추정 2–3시간 |
| C2 | kws·ad도 같은 방식으로 실행 → 같은 입력에서 MLEK 출력과 비교(지금은 tflite만) | 약 40분 |
| C3 | **결정 필요:** MLEK에서 MAC_ACTIVE 등을 얻으려면 `ethosu_profiler.c`(MLEK HAL)의 이벤트 목록을 바꿔야 함. 바꾸지 않으면 MAC_ACTIVE 동등성은 `UNPROVEN`으로 두고, B 결과(runner의 MAC_ACTIVE가 E5 차이에 불변인지)로 간접적으로만 말함 | 결정 |

**권장 순서:** A(10분) → C1·C2(승인 필요, 3–4시간) → B 최소안(1시간) → 필요하면 B 전체. A와 B는 같은 진단·변형
이미지 하나로 묶을 수 있다(knob 방식). 모든 실험은 데이터를 얻기 전에 계약으로 고정하고, TA profile 1을 유지한다.

## 6. QREAD(2B-4) 결과를 어디까지 일반화할 수 있는가

- QREAD 계측은 CPU가 실행 중에 폴링해야 하므로 **busy-poll 경로에서만** 할 수 있다. WFE 경로(MLEK)에서는 원리적으로 같은 계측을 할 수 없다.
- 따라서 QREAD 결과는 기본적으로 **runner 실행 환경**의 결과다.
- MLEK과 같은 실행으로 일반화하려면 B1(CPU 대기)과 B2(D-cache)가 해당 지표에 대해 `INERT`여야 한다. 그리고 (모델, 지표)가 §4 기준으로 `EQUIVALENT`여야 한다.
- B1이 `EFFECTIVE`면 QREAD 결과는 "busy-poll 환경"으로만 쓴다.
- 2B-4 브랜치는 이 결과가 나온 뒤 이 브랜치 위로 rebase한다.

## 7. 지금 할 수 있는 것과 결정할 것

- 보드 없이 끝낸 것:
  - §1–§3 정적·기존 데이터 분석.
  - 비교 스크립트와 테스트(`equiv_existing.py`, `test_equiv_existing.py`).
  - pilot golden 표기 정정.
- 결정 요청:
  1. A 진단 이미지(firmware 변경) 승인 여부.
  2. C1·C2 MLEK 실행 승인 여부.
  3. C3, 즉 MLEK profiler 이벤트 변경 허용 여부.
  4. B를 최소안으로 할지 전체로 할지.

## 8. Owner 결정 (2026-11-09 2차)과 수정된 판정 기준 — §4를 대체한다(§4는 기록으로 남김)

Owner 결정:
- 자체 runner를 폐기하거나 Ethos-U 드라이버로 바꾸지 않는다.
- runner의 계측 유효성과 MLEK 실행 동등성을 따로 검증한다.

승인 범위:
1. 2B-3 측정을 먼저 끝내고 원시 데이터와 보드 이미지를 보존한다.
2. 실험 A(CAP, TA EXT MAXR 되읽기).
3. C1·C2. MLEK 기준값이 없는 4개 모델(vww4·rnnoise·yolo·w2l)과 kws·ad를 같은 입력, 같은 Vela 산출물, TA profile 1로 돌려 출력과 PMU 값을 비교한다.
4. MLEK 계측 빌드. 원본 MLEK 실행은 그대로 두고 MAC_ACTIVE 등을 세는 빌드를 추가하며, 그 빌드가 실행을 교란하는지 확인한다.
5. 실험 B는 A와 기존 데이터의 결과를 보고 필요한 설정부터 하나씩 한다. D-cache를 바꾸면 캐시 일관성과 출력을 확인하고, WFI와 WFE는 구분한다.

2B-4(QREAD)는 기존 runner의 레지스터 직접 접근 방식으로 계속 검토하며, 드라이버 전환은 필수 조건이 아니다.
Stage 1·2A·3 측정값은 보존하고, 이번 검증에서 실제로 영향을 받는 항목만 따로 재평가한다.

### 8.1 판정을 둘로 나눈다

**(R) runner 계측 유효성** — runner가 자기 실행을 올바르게 재는가. MLEK와는 무관하다.

| 항목 | 기준 | 판정 |
| --- | --- | --- |
| R1 실행 정확성 | 각 blob 자신의 golden과 OFM 바이트 일치, RUN 유효(model 모드) | `VALID` / `INVALID` |
| R2 설정 적용 | knob·TA·AXI·MEM_ATTR·POWER_CTRL 되읽기 일치, CAP·TA EXT MAXR의 실제 적용값 기록(실험 A) | `APPLIED` / `NOT_APPLIED` / `UNPROVEN` |
| R3 계측 창 | seam이 RUN마다 정확히 1번 발생, 카운터 overflow 없음, 측정 창 정의(E4) 기록 | `VALID` / `INVALID` |
| R4 재현 | 같은 blob이 이미지 사이에서 mac_active·beat가 같고 npu_active가 범위 안(S0-4 방식) | `REPRODUCED` / `NOT_REPRODUCED` |

**(M) MLEK 실행 동등성** — 같은 입력·같은 Vela 산출물·TA profile 1에서 runner의 값이 MLEK와 같은가.

| 항목 | 기준 | 데이터가 없거나 조건이 다를 때 |
| --- | --- | --- |
| M1 출력 | 같은 IFM에서 runner OFM = MLEK FI101 OFM (바이트) | `UNPROVEN`. 다른 입력이나 tflite 일치는 근거로 쓰지 않는다 |
| M2 beat | MLEK와 정확히 같음 | MLEK 값이 없으면 `UNPROVEN` |
| M3 NPU_ACTIVE | \|runner 중앙값 − MLEK 중앙값\| ≤ max(MLEK 반복 범위, runner 측정 RUN 범위) | 같음 |
| M4 처리부 이벤트(MAC_ACTIVE 등) | MLEK 계측 빌드 값과 M3과 같은 규칙. 단, 계측 빌드가 원본 MLEK를 교란하지 않을 때만(원본과 같은 입력에서 ACTIVE와 beat가 M2·M3 기준으로 같음) | 계측 빌드가 없거나 교란이 있으면 `UNPROVEN` |

**입력 조건:** M 판정에는 같은 입력의 실행만 쓴다. 기존 MLEK B1–B3(MLEK 내장 샘플 입력)과 runner(seed-1 입력)의 비교(§3)는 **기술용**이며 M 판정의 근거가 아니다. mobilenet만 같은 입력이다.

### 8.2 실행 환경 차이(E5, 실험 B)의 처리

- 모든 차이가 `INERT`여야 연구를 진행할 수 있다고 가정하지 않는다.
- 차이 하나에 대해 변형 arm과 기준 arm(같은 이미지)을 비교한다. 2B-0b 허용오차 안이면 `INERT`, 밖이면 `EFFECTIVE`다.
- `EFFECTIVE`가 나오면:
  1. 원인을 구분한다. 어떤 지표가 바뀌었는지(npu_active만인지, mac_active·beat까지인지), 어느 모델에서인지 본다.
  2. 그 지표를 쓰는 결과에 **적용할 수 있는 실행 조건**을 명시한다. 예: "busy-poll·D-cache off 실행 기준", "WFE 실행에서는 X % 다름".
  3. 결과를 폐기하지 않는다.
- WFI(`__WFI`)와 WFE(`__WFE`, MLEK)는 다른 변형으로 둔다. D-cache 변형은 출력 영역의 clean/invalidate와 OFM 일치를 함께 확인한다.

### 8.3 기존 결과의 재평가 범위

- Stage 1·2A·3과 2B 결과는 그대로 둔다.
- 재평가하는 것은 이번 검증에서 바뀐 판정이 걸린 항목뿐이다. 예: M1이 `UNPROVEN`에서 `EQUIVALENT`로 바뀐 모델의 "MLEK와 같은 출력" 문구, `EFFECTIVE` 차이가 걸린 지표의 적용 조건 표기.
- 재평가는 원 결과 옆에 덧붙이는 표로 남긴다.

## 9. C1·C2와 MLEK 계측 빌드 실행 설계 (2026-11-09, 계약은 MLEK 첫 실행 전에 고정)

### 9.1 "같은 입력"을 만드는 방법 (기존 절차, `evidence/mobilenet_ofm/REPORT.md`)

- MLEK에는 seed-1 입력을 넣을 수 없다. 넣으려면 DYNAMIC_MEM_LOAD를 써야 하는데, 그러면 모델 배치가 0x90000000으로 바뀐다.
- 그래서 같은 입력은 **MLEK의 자체 입력(`std::rand`, 기본 seed — Obsidian A7: 결정적)**으로 만든다.
  1. VERIFY_TEST_OUTPUT 빌드로 그 입력과 출력을 보드에서 덤프한다.
  2. 덤프한 입력으로 runner blob을 다시 만든다(`pack_vela_workload.py --ifm/--golden`).
- mobilenet과 Stage 1 a2 연산자들이 이미 이 방식으로 만들어졌다.
- 이 입력은 stock MLEK B1–B3이 쓴 입력과 같은 코드 경로의 같은 `std::rand` 값이다. **가정**: VERIFY 빌드와 stock 빌드의 입력이 같다. 근거는 같은 소스, 같은 seed라는 것이다. G5(덤프 해시)로 VERIFY 쪽만 확인된다.

### 9.2 단계 (모두 TA profile 1, 같은 Vela 산출물 — G2로 확인)

| 단계 | 내용 | 보드 | 대상 |
| --- | --- | --- | --- |
| C-a | VERIFY 빌드: 입력·출력 덤프, `mlek_golden.py` G1–G5 → manifest | MLEK 배포 1번 + 부팅 1번 / 모델 | vww4, rnnoise, yolo, w2l(C1), kws, ad(C2) |
| C-b | stock MLEK: profiler 카운터(ACTIVE, beat 4종), B1–B3처럼 3번 부팅(배포 1번에 reboot 3번) | 같음 | vww4, rnnoise, yolo, w2l(kws·ad·mobilenet은 기존 B1–B3이 같은 입력이라 재사용) |
| C-c | MLEK 계측 빌드: `ethosu_profiler.c`의 이벤트 목록에 MAC_ACTIVE(48), MAC_DPU_ACTIVE(51), AO_ACTIVE(64)를 더함(8 카운터 이내). 임시로 수정해 빌드하고 소스는 digest로 복원(a2 `build.sh` 방식). 3번 부팅 | 같음 | 7개 모델 |
| C-d | runner: MLEK 입력과 정답으로 다시 만든 blob(kws, ad, vww4, rnnoise, yolo, w2l; mobilenet은 기존 `0d51cf9e`), 이미지 `d0cd4775`, 세트 A·C·D, 10 RUN | runner 캠페인 | 6개 모델 |

- **계측 빌드의 교란 확인(M4 전제):** 같은 입력에서 계측 빌드의 ACTIVE·beat가 stock MLEK와 같아야 한다. 기준은 §8.1 M2(beat 정확히 같음), M3(ACTIVE)다. 다르면 그 모델의 M4는 `UNPROVEN`이다.
- **runner 쪽 판정:** C-d의 RUN이 R1(자기 정답과 OFM 일치)을 만족하면, 그 정답은 MLEK 출력이므로 M1(같은 입력에서 MLEK와 출력 일치)도 함께 판정된다.

### 9.3 도구 변경 (보드 없이, MLEK 실행 전에)

- **`pack_vela_workload.py`:** `--ifm`/`--golden`이 지금은 한 텐서만 받는다. rnnoise(입력 여러 개)와 yolo(출력 2개)용으로 텐서 목록을 받게 확장한다. IO 표 순서를 따른다.
- **`ofm_compare.section`:** 여러 텐서의 덤프를 이어 붙여 돌려준다. 텐서 크기로 나누는 함수를 추가한다.
- **`mlek_golden.py`:** G1(길이)을 텐서별로 확인한다.
- **MLEK profiler 카운터 파서:** 기존 B1–B3 형식을 재사용한다.

### 9.4 자원과 비용

- **board host 디스크:** 여유 345 MB(2026-11-09). MLEK 빌드 하나가 약 60 MB다. 그래서 빌드는 한 번에 하나씩 하고, 이미지(boot/bram/ddr.bin, images.txt)와 로그만 남긴 뒤 내가 만든 빌드 디렉터리를 지운다. 2B-3 측정 중에는 빌드하지 않는다.
- **보드 시간(추정):** MLEK 배포·부팅·캡처가 모델당 약 10분(w2l은 더 김)이다.
  - C-a: 6개 모델, 약 1.2 h.
  - C-b: 4개 모델 × 3번 부팅, 약 1 h.
  - C-c: 7개 모델 × 3번, 약 1.8 h.
  - C-d: runner 6번 부팅, 약 1 h. w2l 업로드에 약 17분이 든다.
  - 합계 약 5 h. 원래 추정이었던 3–4 h는 C-c를 넣기 전 값이다.
- **sudo:** MLEK 배포(`deploy_mlek.sh` / `restore_mlek.sh`)와 runner 이미지 배포(`deploy.sh`)는 sudo가 필요하다. 비밀번호는 실행할 때 받아 stdin으로만 쓴다.
