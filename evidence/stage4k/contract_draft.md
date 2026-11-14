# Stage 4K — Conv 1×1·3×3 MAC 하드웨어 특성: 보드 계약 초안 (2026-11-14, **동결 전, 실행 전**)

- 이 문서는 초안이다. 동결하지 않았고, 보드를 실행하지 않았다. 동결과 보드 실행은 owner의 별도 결정 뒤에 한다.
- 근거 문서는 다음과 같다.
  - 근거와 정적 분석: `docs/plan/stage4k_conv_kernel_plan.md`
  - 판정 코드: `host/analysis/stage4k.py`
  - 테스트: `host/tests/test_stage4k.py`
  - mutation 기록: `evidence/stage4k/mutation.txt`
- 동결할 때는 이 파일을 `contract.md`로 복사해 동결 커밋을 남긴다. 이 초안은 "대체됨"으로 표시만 하고 지우지 않는다.

## 1. 질문과 대상

**질문.** 같은 펌웨어·Runner·Vela 설정에서 일반 Conv의 커널 크기(1×1, 3×3)와 Cin(16, 32, 40, 48, 64)에 따라 다음이 어떻게 달라지는가.
- MAC 활성 사이클당 유효 처리율.
- 채널 단위의 계단.
- 전체 NPU 실행 비용.

**대상(최종 10개, 추가 없음).**

| 항목 | 값 |
| --- | --- |
| 연산 | Conv2D, 24×24 IFM, Cout 96, stride 1, SAME(1×1은 VALID, 명령 스트림이 SAME과 바이트 동일), RELU6, INT8, batch 1 |
| 1×1 | `s4_conv_base`(Cin 16), `s4c2_conv_cin32/40/48/64`. 기존 DRWL과 바이트 동일한 재빌드 |
| 3×3 | `s4k_conv3x3_cin16/32/40/48/64` |
| 선정 기준 | 지시서의 후보 10개를 그대로 쓴다. 15개 모두 컴파일 Gate B PASS(대조군 5 포함). 대조군 `s4k_conv1x1same_*`는 보드에 올리지 않는다 |
| 산출물 | `evidence/stage4k/workloads/`. DRWL sha256은 `results/fi101_stage4k/stage4k_static.csv`, 15개 모두 word 7 = 0 |
| 펌웨어 | Driver Runner `70090f1`(재빌드 없음): boot `718c4562…ef59`, bram `c80e77df…e99c`, ddr `374708ff…37bb`, images.txt `af688281…423f` |
| 고정 조건 | TA profile 1, Vela 5.0.0과 MLEK 옵션, Dedicated_Sram, WAIT_WFE, D-cache on, region 1 = DDR/EXT(REGIONCFG 0x15F) |

- placement(SRAM) 실험과 섞지 않는다.
- 다른 연산, 채널, 메모리 모드, Transformer, AO·WD 독립 실험으로 넓히지 않는다.

## 2. 프로토콜 (100 RUN, boot 10개)

- **Pass.** Stage 4와 같다(`board/ids.txt`).
  - pass A = 35, 48, 51, 53, 55, 64, 80, 81.
  - pass B = 35, 128, 130, 132, 135, 384, 386, 391.
- **RUN 수.** pass마다 warm-up 1 + 측정 4 = 5 RUN이다. 구성마다 10 RUN, 합계 100 RUN이다.
  - "5 RUN 추가" trigger는 두지 않는다.
- **조건.** `wfe 0 0 off 1,2`, `OUTPUTS=1`, `STOP_ON_INVALID=1`.
- **boot 순서**(`board/plan_b01–b10.txt`, 번호 369–378은 동결 때 확정):
  - 1×1 16 → 3×3 16 → 1×1 32 → 3×3 32 → 1×1 40 → 3×3 40 → 1×1 48 → 3×3 48 → 1×1 64 → 3×3 64.
  - 같은 Cin의 1×1과 3×3을 시간상 붙여 둔다.
  - 순서는 이것 하나로 고정하고, 반복이나 교차는 하지 않는다. 순서 효과는 통제하지 않았다고 보고한다.
- **세션.** owner 승인 sudo 세션 하나로 진행한다(`board/session_draft.txt`, `sudo_session.sh --check` OK).
  - boot마다 한 단계를 두고, 그 뒤 `stage4k.py boot-check`를 실행한다.
  - boot 1 뒤에는 `repro-gate`도 실행한다.
  - 실패한 단계가 있으면 세션이 멈추고 카드를 복원한다.
- **배포 전(보드 밖).**
  - `sh test.sh` ALL PASS.
  - `mutate.py` 전부 KILLED, sha256 복원.
  - `sync.sh board`.
  - staging `~/evsweep_s4k` 구성:
    - 이미지: `~/evsweep_s4p`에서 복사하고 sha256을 확인한다.
    - DRWL 10개와 각 `compile.json`, `tflite_ofm.bin`.
    - `conditions.txt`, `ids.txt`, plan 10개.
    - `ref/wfe`: placement A boot 367 원시 데이터.
    - 보드 `~/evsweep/host/analysis`에 `stage4k.py`, `stage4.py`, `stage4c1.py`, `stage4c2.py`를 둔다.
- **보드 시간 추정.**
  - boot 10 × (reboot + 최대 160 KB 업로드 + 10 RUN + 출력 조회) ≈ 40–60분.
  - 배포·복원 ≈ 5분.
- **종료.**
  - `restore_mlek` → `postflight.sh`(m6 이미지, PING, USB_OFF, 카드 분리 확인).
  - 카드가 마운트된 상태에서 `USB_OFF`는 하지 않는다(스크립트 guard).

## 3. Gate와 중단 조건

| Gate | 내용 | 실패 시 |
| --- | --- | --- |
| G0 배포 | deploy 검증(digest), 재부팅 마커, PING | 세션 중단, 복원. RUN 없음 |
| G1 재현 (`repro-gate`, boot 1) | 1×1 Cin 16을 placement A(같은 이미지·같은 blob, boot 367)와 비교한다. 아래가 모두 맞아야 한다: 측정 RUN마다 MAC_ACTIVE 2,304와 MAC_DPU 1,152; 출력 sha256 같음, PASS_EXACT; 양쪽에서 상수인 카운터가 모두 같음(pass B beat 포함); NPU_ACTIVE pass A 중앙값 차이 ≤ max(1 % × 21,086.5, 두 range) | **3×3을 하나도 실행하지 않는다.** 세션 중단, 복원, `NOT_INTERPRETED (REPRO_GATE)` |
| G2 boot마다 (`boot-check`) | Gate C: 두 pass 모두 측정 RUN 4회, 모든 RUN 유효(`record_v2.validity`: job OK, IRQ 1회, REGIONCFG_MATCH 등), 출력 PASS_EXACT 또는 PASS_TOLERANCE, RUN 간 CRC 하나 | 세션 중단, 복원. 이후 구성은 `NOT_MEASURED`, 재측정 없음 |
| boot 안 | `--stop-on-invalid`: 무효 RUN이나 출력 불일치가 나오면 즉시 boot 종료. NPU fault, timeout, refusal, 응답 없음도 같다 | G2 FAIL로 처리 |
| 보조 재현 (분석 때) | 1×1 Cin 32/40/48/64를 기존 `83398c7` 측정과 같은 규칙으로 비교한다. Cin 64는 boot 346·350 두 기준 모두와 비교 | `REPRO_MISMATCH`면 그 Cin의 이미지 간 비교는 하지 않는다. 세션 내 값은 그대로 쓰고 표시한다. 중단 조건은 아니다 |

- 어느 경우에도 형상·주소·RUN 수·순서를 바꿔 다시 시도하지 않는다. 바꾸려면 Amendment와 승인이 필요하다.

## 4. 판정 규칙 (`stage4k.py judge`, 데이터 전에 고정)

**출력.** Stage 4 규칙을 따른다.
- CPU reference(tflite_runtime) 대비 PASS_EXACT / PASS_TOLERANCE(≤ 1 LSB) / FAIL / INVALID.
- 펌웨어 자체 비교값(ofm_mismatch, ofm_max_diff)이 호스트 비교와 같아야 한다.
- RELU6 포화 수는 기록만 한다.
  - 10개 모두 OFM scale이 base(0.0501)와 같아서 cap은 120이다.
  - CPU reference 기준 포화 수는 1×1이 1–637, 3×3이 3,271–12,046(55,296개 중)이다.

**측정값과 허용폭.**

| 측정값 | 사용 | 허용폭 |
| --- | --- | --- |
| MAC_ACTIVE(48), MAC_DPU_ACTIVE(51) | 판정 | 정확값. 측정 RUN 4회가 모두 같아야 한다. 다르면 `MEASUREMENT_UNSTABLE`이고 판정하지 않는다 |
| NPU_ACTIVE(35) | 판정 (pair) | tol = max(기준 중앙값의 1 %, 두 RUN range). Stage 4 pair 규칙, pass B로 방향 확인 |
| AO_ACTIVE(64), WD_ACTIVE(80), WD_STALLED(81), pass B beat·transaction | 보조, 기록 | pair 안에서 같은 tol로 changed / not을 기록하고 원인은 배정하지 않는다 |
| 53, 55 | 보고만 | TRM 110 목록 밖. 결론에 쓰지 않는다 |

**RQ별 판정(닫힌 결과 집합).**
- **구성별 MAC_ACTIVE** (4C-2b 규칙): `INVALID` > `MEASUREMENT_UNSTABLE` > `MATCH:<§5 가설 중 모든 RUN과 같은 것>` > `NONE_MATCHED`. 측정 뒤 계수를 맞추거나 가설을 추가하지 않는다.
- **RQ1 커널 크기** (Cin마다): 유효 MAC/MAC_ACTIVE(nominal)를 1×1과 3×3에서 비교한다.
  - 결과: `SAME_RATE` / `RATE_3X3_HIGHER` / `RATE_3X3_LOWER` / `NOT_JUDGED`.
  - 비교 가능성 표시를 함께 단다:
    - Cin 16, 32: `SAME_TRAVERSAL_BLOCKS_DIFFER`.
    - Cin 40, 48, 64: `TRAVERSAL_DIFFERS`.
  - 두 표시 모두에서 커널 크기만의 효과라고 쓰지 않는다.
- **RQ2 채널 단위** (커널마다, MAC_ACTIVE 정확값):
  - `PROPORTIONAL_TO_CIN`: MAC_ACTIVE × 16 = MAC_ACTIVE(16) × Cin.
  - `CONSISTENT_WITH_CEIL16`: MAC_ACTIVE × 16 = MAC_ACTIVE(16) × ⌈Cin/16⌉·16.
  - `BOTH` / `NEITHER` / `NOT_JUDGED`. 이와 함께 Cin 40 = 48 여부를 적는다.
  - 1×1 다섯 점은 두 전략에 걸쳐 있으므로, 결과가 `NEITHER`여도 전략 그룹별로 따로 기술한다.
- **RQ3 컴파일러 전략:** 판정 없이 기술만 한다. (traversal, OFM/IFM block, ublock) 그룹별 처리율과 정적 표를 함께 놓는다. Vela가 고른 전략의 최적성은 주장하지 않는다.
- **RQ4 계산 vs 실행:** 같은 커널 안의 인접 Cin과, 같은 Cin의 1×1→3×3에 Stage 4 pair 규칙을 적용한다.
  - 결과: `CONSISTENT_WITH_MAC_CHANGE` / `NOT_PROPORTIONAL_TO_MAC` / `UNRESOLVED`.
  - pass A와 pass B의 방향이 반대면 `UNRESOLVED`다.
  - MAC 비율, MAC_ACTIVE 비율, NPU_ACTIVE 비율, MAC_ACTIVE/NPU_ACTIVE, 보조 지표를 함께 표로 낸다.
- **RQ5 하드웨어 한계:** 판정 없이 기술만 한다.
  - nominal/(1024·MAC_ACTIVE), valid/(1024·MAC_ACTIVE), nominal/(1024·NPU_ACTIVE)를 보고한다.
  - 1024 = 구성 MAC/CC다. Conv 전용 TRM peak를 확보하지 못했으므로 "공식 Conv peak 대비"라고 쓰지 않는다.

## 5. 사전 등록 가설 (`results/fi101_stage4k/predictions.json`)

- r ∈ {384, 768} × a ∈ {nominal, valid, c16, valid_c16}의 8개 MAC_ACTIVE 값이다(표는 계획 문서 §5).
- 3×3 Cin 40은 8개를 모두 가른다. Cin 16·32·48·64에서는 c16과 nominal이 겹친다.
- 해석 한계:
  - `R*_valid*`와 맞으면 "padding 탭 수를 뺀 양과 부합"으로만 쓴다. 0 탭을 건너뛰는 회로가 있다고 쓰지 않는다.
  - `R*_c16`과 맞으면 "16채널 올림과 부합"으로만 쓴다. 16채널 처리 단위라고 쓰지 않는다.
  - r = 384와 768은 1×1에서 본 값일 뿐 하드웨어 상수가 아니다.

## 6. 해석 범위와 금지

- 커널 크기, 채널 수, 컴파일러 전략, OFM block, weight 크기가 함께 바뀌는 비교에서는 인과를 주장하지 않는다.
  - 1×1 대 3×3은 언제나 OFM block과 weight 크기가 다르다.
  - Cin ≥ 40에서는 traversal도 다르다.
- NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다. WD_STALLED를 병목 시간으로 환산하지 않는다.
- 3×3의 전체 사이클을 1×1과 직접 비교해 커널 효과라고 쓰지 않는다. MAC 수(×9)로 정규화한 값만 쓴다.
- 7개 모델이나 다른 형상으로 일반화하지 않는다. 한 boot 안의 4 RUN이므로 boot 간 재현성은 1×1 기준 비교로만 말한다.

## 7. 실패·불확실 결과의 후속 조치 (사전 정의)

| 결과 | 조치 |
| --- | --- |
| G1 FAIL | 3×3 미실행. 원시 데이터 보존, 원인 조사 계획만 보고. 재측정은 새 승인 |
| G2 FAIL (boot k) | 1..k−1 보존·판정, k 이후 `NOT_MEASURED`. 재시도 없음 |
| `MEASUREMENT_UNSTABLE` | 그 구성은 RQ1/RQ2 `NOT_JUDGED`. 추가 RUN 없음 |
| `NONE_MATCHED` | 관측값과 처리율을 기술. 새 가설은 다음 계약에서만 |
| `REPRO_MISMATCH` (1×1 Cin ≥ 32) | 세션 내 값으로만 비교, 이미지 간 비교 제외, 표시 |
| NPU_ACTIVE `UNRESOLVED` | "이번 조건에서 차이를 판정하지 못함"으로 보고. 영향 없음이 아님 |
| 메모리 stall 이벤트가 필요해 보임 | 이번 계약에 넣지 않는다. pass C 추가는 별도 계약 |

## 8. 원시 데이터 보존과 장비 복원

- 세션 뒤 다음을 `evidence/stage4k/raw/`로 복사한다.
  - 대상: `~/evsweep_s4k_run`, 세션 로그, staging의 plan/ids/conditions.
  - 대상 아님: m6 이미지 바이너리.
- 복사 뒤 sha256 목록을 남긴다.
- 복원은 `restore_mlek`(m6 digest와 같음을 확인) → `postflight.sh`(PING state 1, USB_OFF, 카드 분리 확인) 순이다.
- 세션이 실패로 끝나면 `postflight.sh`를 따로 실행한다.
- 분석은 `stage4k.py judge`로 하고, 결과는 `results/fi101_stage4k/`에 둔다.
