# Stage 2B-3 — 명령 실행과 PMU 그룹 귀속 진단 (계획, 2026-11-08)

Owner 2026-11-08: "기록하고, 다음 세부 확인 단계로 넘어가자" + Stage 2B-3 지시문(사용자 제공) + "특정 모델에 대한
확인만 하지 말고, 전체 모델에 대해 균등하게 확인이 필요해". 이 문서는 계획이며 계약이 아니다. 보드 단계마다 데이터
전에 계약을 따로 고정한다. **TA profile 1**, Ethos-U85 1024 MAC, 7개 MLEK 모델 모두, 단계마다 같은 규칙.

## 출발점 (2B-2, `2efbd89`)

- 마스크는 실행을 바꾸지 않음(2B-0b, 7/7). 그룹 합계는 전체와 맞음(deficit ≤ 1.9 %).
- 그러나 그룹별 MAC 효율 = Vela MACs / (mac_active × 1024)가 ad CONV 2.85(> 1). kws CONV 0.93, rnnoise CONV(FC)
  0.96, wav2letter CONV 0.97도 모델 전체(0.27 / 0.16 / 0.97)와 비교해 의심 → **ad만의 문제로 보지 않는다.**
- H1/H2와 그룹별 비율은 다시 쓰지 않는다. Stage 1·2A·2B-0b 결과는 이 문제로 무효화하지 않는다(그룹 창을 쓰지 않음).
- 질문: 원래 연속 실행을 그대로 두고, 연산별(또는 어떤 단위로든) PMU 이벤트를 정확히 귀속할 수 있는가.

## 이미 확인한 정적 사실 (2026-11-08, 측정 blob의 명령 스트림, `ethosu85_interface.h`)

| model | kernel ops | DMA_START | DMA_WAIT (k=0) | KERNEL_WAIT (n=1) | BLOCKDEP 설정 횟수 |
| --- | --- | --- | --- | --- | --- |
| kws | 14 | 4 | 4 | 0 | 13 |
| ad | 14 | 3 | 3 | 0 | 9 |
| rnnoise | 48 | 11 | 11 | 0 | 17 |
| vww4 | 85 | 18 | 18 | 4 | 47 |
| yolo | 112 | 45 | 45 | 11 | 59 |
| mobilenet | 208 | 29 | 29 | 11 | 159 |
| wav2letter | 39 | 11 | 11 | 0 | 8 |

- kws·ad·rnnoise·wav2letter에는 KERNEL_WAIT가 없다. 연산 간 순서는 BLOCKDEP(다음 연산이 앞 연산의 블록을 몇 개
  기다리는지)와 DMA_WAIT(가중치 DMA 완료)만으로 정해진다 → 명령 해석 위치와 실행 완료 사이에 고정된 장벽이 없다.
- `cms.gate_ops`의 창 = [연산 i−1의 kernel 명령 직후, 연산 i의 kernel 명령 직후). 즉 "i−1 발행 ~ i 발행" 구간이며
  "i 실행" 구간이라는 보장이 없다(TRM에서 발행 조건 확인 필요, Phase 1).

## Phase 1 — 명령 스트림 정적 분석 (보드 없음, 7개 모델 전부)

1. Arm Ethos-U85 TRM의 command issue / completion, BLOCKDEP, KERNEL_WAIT(n), DMA_WAIT(k), PMU_MASK 정의를 원문으로
   확인하고 인용(문서 번호·절). 확인 못 한 항목은 "미확인"으로 남긴다. 특히: 명령 처리기가 kernel 명령에서 언제 다음
   명령으로 넘어가는가(대기열 깊이), PMU_MASK가 언제 적용되는가.
2. 도구 `host/analysis/cms_timeline.py`(신규, 단위 테스트): 연산마다 표 한 줄 —
   Op ID, 유형, Vela 연산(op_map), 명령 오프셋, BLOCKDEP 값, 직전 DMA_START/DMA_WAIT/KERNEL_WAIT, 2B-2 마스크
   enable/disable 위치, Vela MACs, 앞 연산과의 데이터 의존(IFM 주소 = 앞 OFM 주소; 레지스터 값으로 판단).
3. 각 줄을 "명령으로 확정되는 순서"(DMA_WAIT·KERNEL_WAIT·BLOCKDEP 0)와 "겹칠 수 있음(BLOCKDEP > 0, 장벽 없음)"으로
   분류하고, 실측으로만 확인 가능한 항목을 따로 적는다.

산출: `results/fi101_stage2b3/timeline/<model>.csv` + README(정적 사실 / 추정 / 실측 필요 구분).

## Phase 2 — 기존 데이터 재검토 (보드 없음, 7개 모델 전부, `POST_HOC_DESCRIPTIVE`)

1. **계산 자체 배제:** Vela MACs 출처와 그룹 매핑(op_map으로 연산별 재합산), 1024 MAC/사이클 상한이 int8 conv에 맞는지
   (TRM), mac_active의 정의(드라이버·TRM 설명). 모델 전체 효율(0.16–0.97)이 1 이하인지 다시 확인.
2. 모든 모델·그룹의 효율과 이상값 목록(1 초과 및 모델 전체 대비 과대).
3. **지연(lag) 가설을 모든 모델에 같은 방식으로 시험:** 창이 실제로는 연산 i−d를 센다고 가정하고(d = 0, 1, 2) 그룹의
   Vela MACs를 다시 배정 → 모든 그룹에서 효율 ≤ 1이 되는 d가 있는가. 모델별로 다르면 그 차이가 BLOCKDEP/장벽 구조와
   맞는가.
4. 경계 패턴: set A·C·D의 이벤트(MAC/AO/WD/DMA 계열)가 같은 경계에서 같은 방향으로 어긋나는가. 2B-0b의 절반 분할
   (m_a/m_b, 7개 모델)도 같은 방식으로 본다.
5. "합계 보존"이 창이 스트림을 빈틈없이 나누는 것만으로 설명되는지(창 연속성은 정적 사실) 정리. 합계 보존 ≠ 귀속 정확.

산출: `results/fi101_stage2b3/existing_data/` (이상값 목록, lag 시험표, 경계 패턴, 설명 가능/추가 계측 필요 구분).

## Phase 3 — 마스크 창 정렬 진단 (보드, 7개 모델 균등)

계약을 데이터 전에 고정(판정 코드 + 변이 테스트). 이미지 `d0cd4775`(현재 카드에 있음) 그대로, 원래 스트림에
PMU_MASK만 넣음(2B-0b에서 교란 없음 확인). set A, 10 RUN(2 warm-up).

**연산 선택 규칙 (모든 모델 동일, 정적으로 결정) — 2026-11-08 owner 수정으로 대체됨, 아래 "Phase 3a 설계" 참조:** 기준 연산(anchor) = Vela 연산 1개가 stream 연산 1개로만
나오고(스트라이프·분할·체이닝 아님) Vela MACs가 앞뒤 2개 연산 각각의 4배 이상인 연산 중 MACs가 가장 큰 것.
- A1: CONV 유형 anchor
- A2: CONV가 아닌 유형 anchor (DEPTHWISE가 있으면 DEPTHWISE, 없으면 MACs가 가장 큰 비-CONV 연산; rnnoise·
  wav2letter는 MAC 신호가 약하므로 npu_active로만 보고)
- 규칙을 만족하는 연산이 없는 모델·유형은 `NOT_APPLICABLE`로 기록(빠뜨리지 않음).

**3a (1차, 모델당 4 boot):** 각 anchor i에 대해
- 기존 위치 창 [i−1 발행 후, i 발행 후)
- +1 이동 창 [i 발행 후, i+1 발행 후)

판정 질문: anchor의 큰 MAC 신호(앞뒤의 4배 이상)가 어느 창에 나타나는가 → 연산별 지연 d의 직접 관측. 효율 ≤ 1만으로
정확하다고 인정하지 않음: (a) anchor 신호가 한 창에 모이는지, (b) 반복 안정성(RUN 폭), (c) 같은 d가 7개 모델·두 유형에서
성립하는지를 같이 본다.

**3b (3a 결과에 따라, 별도 승인):** 경계 쌍 창(CONV→비CONV, 비CONV→CONV), KERNEL_WAIT 전후 위치(vww4·yolo·mobilenet만
해당 — 이 3개 모델에만 KERNEL_WAIT가 있음, 이유 기록), 그리고 **독립 기준**: 스트림을 연산 k 뒤에서 잘라 STOP을 붙인
접두 스트림 P(k)의 mac_active 차이 P(i+1) − P(i) = 연산 i의 MAC 활동(끝까지 완료되므로 겹침과 무관). 접두 스트림은 꼬리의
실행을 바꾸므로(STOP 삽입) 기준값으로만 쓰고 연산 비용으로 보고하지 않는다. → 지시문의 "STOP 실행 변경" 해당, 승인 후.

## Phase 4 — KERNEL_WAIT 장벽 비교 (Phase 3에서 경계를 못 찾을 때만, 별도 승인)

Baseline / Mask-only / Barrier / Barrier+Mask, 7개 모델 같은 규칙의 경계. 전체 사이클·이벤트·출력·순서 비교. 증가한
사이클을 겹침 시간으로 읽지 않고, 장벽 환경의 연산 비용을 원래 실행의 지연으로 쓰지 않는다.

## Phase 5 — 판정

EXACT_ATTRIBUTION / COARSE_ATTRIBUTION / ISOLATED_ONLY / NOT_IDENTIFIABLE (지시문 표 그대로). 판정 조건: 출력 일치,
교란 없음, 합계 정합, 물리적 타당성(효율 ≤ 1), 독립 기준과의 일치, **7개 모델·여러 유형에서 같은 규칙**. 겹친 실행에서
"연산의 활동 사이클"과 "모델 지연 기여분"은 다른 양으로 보고.

## 보드 비용 (2B-2 기록 기준: 재부팅 153 s + blob 전송·RUN)

| model | 부팅 1회 | 3a (4 boot) |
| --- | --- | --- |
| kws | 3.0분 | 12분 |
| ad | 3.8분 | 15분 |
| rnnoise | 2.9분 | 12분 |
| vww4 | 3.5분 | 14분 |
| yolo | 3.8분 | 15분 |
| mobilenet | 11.7분 | 47분 |
| wav2letter | 38분 (blob 전송이 대부분) | 152분 |
| 합 | 66.7분 | **약 4.5시간** |

wav2letter가 절반 이상. 줄이는 방법은 펌웨어에 "한 부팅에서 명령 스트림만 바꿔 여러 번 실행" 기능을 넣는 것(이미지 변경,
별도 승인) — 지금은 제안만.

## 순서와 승인

1. Phase 1 → Phase 2 (보드 없음, 바로 진행).
2. Phase 2 결과로 3a의 연산 선택·판정 규칙을 계약으로 고정 → 3a 진행(이미지 그대로, 약 4.5 h).
3. 3b·Phase 4·이미지 변경·STOP 접두 스트림은 진단 계획과 예상 영향을 보고하고 승인 후.
4. 단계마다 결과 폴더, 이 문서, `stage2_plan.md`, Obsidian에 기록. 정적/기존 데이터로 확인한 사실과 새 보드 실험의
   사실을 구분해 쓴다.

## Phase 1·2 결과 (2026-11-08, `results/fi101_stage2b3/README.md`)

- 정적: 커널 명령은 비차단(남은 커널 최대 2개), PMU_MASK는 차단 명령이고 앞 연산의 완료를 기다리지 않음, 연속 커널 사이
  장벽 없음(BLOCKDEP 겹침) → 창 경계는 "앞 연산들의 완료"에 묶이고 연산 i 자신의 실행과 무관(TRM 원문 + 추론).
- 기존 데이터: 연산별 최대 처리량(TRM Table 7: conv 1024, sparsity 2048, depthwise 128)으로 다시 보면 d=0은 ad·yolo에서
  불가능하고, 7개 모델에 공통인 정수 지연은 없다. ad는 d=0–3 모두 불가능. MAC 0인 ELEMENTWISE·RESIZE 창에도 mac_active가
  있다(원인 미구분).

## Phase 3a 설계 (Phase 1·2 결과 반영, **owner 확인 전 — 보드 측정 안 함**)

Owner 2026-11-08 수정: 선정 규칙은 연산 종류와 무관한 공통 기준. A = 인접 연산보다 MACs가 4배 이상 큰 연산 중 대비가 가장
뚜렷한 것, B = A와 인접하고 MACs가 작거나 0인 연산. Vela 연산량·명령 스트림만 쓰고 2B-2 PMU 결과는 쓰지 않는다. 조건 불충족
모델은 `NOT_AVAILABLE`(완화 없음). 선정·계측·사후 검증 규칙은 7개 모델 동일.

구현 `host/analysis/s2b3_select.py`(변이 9개 RED): A = 양쪽 이웃이 있고 MACs > 0, MACs ≥ 4 × 각 이웃; 대비 = MACs /
max(이웃 MACs, 1024)(1024 = MAC 배열 1사이클, 이웃이 0일 때 대비가 무한대가 되지 않게); 동점이면 MACs 큰 쪽, 그다음 앞
연산. B = A 다음 연산(늦은 창이 A의 일을 담을 위치).

| model | A (유형·Vela 연산) | A MACs | 앞 이웃 MACs | B (유형·Vela 연산) | B MACs | MAC 대비 | 최소 사이클 대비 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| kws | 11 CONV Conv2D | 2,744,000 | 126,000 | 12 POOL AvgPool | 24,500 | 21.8 | 2.7 |
| ad | 5 CONV Conv2D | 19,501,056 | 635,904 | 6 DEPTHWISE | 635,904 | 30.7 | 3.8 |
| rnnoise | 37 CONV FullyConnected | 32,832 | 24 | 38 ELEMENTWISE Add | 0 | 32.1 | 32.1 |
| vww4 | 66 CONV Conv2D | 1,253,376 | 0 | 67 DEPTHWISE | 41,472 | 30.2 | 3.8 |
| yolo | 99 CONV Conv2D | 663,552 | 1,728 | 100 RESIZE | 0 | 384 | 648 |
| mobilenet | 164 CONV Conv2D | 10,838,016 | 0 | 165 DEPTHWISE | 254,016 | 42.7 | 5.3 |
| wav2letter | 8 CONV Conv2D | 2,368,000,000 | 64,750,000 | 9 CONV Conv2D | 592,000,000 | 4.0 | 4.0 |

7/7 선정, `NOT_AVAILABLE` 없음. 규칙이 유형을 제한하지 않았지만 7개 모두 A가 CONV(FC 포함)로 나왔다.
"최소 사이클 대비" = A의 최소 MAC 사이클 / 이웃의 최소 MAC 사이클(TRM 최대 처리량). depthwise는 128 MACs/cycle이라
MAC 대비가 커도 사이클 대비는 작다(ad·vww4 3.8, kws 2.7). 실제 depthwise 사이클은 이 최소보다 클 수 있어, 이웃의
mac_active가 A의 최소 사이클을 넘을 수 있다 → 이 모델들에서는 "A의 일이 어느 창에 있나"가 덜 선명하다. 규칙은 owner가 정한
MAC 기준 그대로 두고 위험만 기록한다(사이클 기준으로 바꿀지는 owner 결정).

**마스크 이동 방법.** 경계 b[k] = 연산 k−1의 kernel 명령 바로 뒤(연산 k의 레지스터 설정 앞). 단일 창 W(k) = b[k]에
PMU_MASK(1), b[k+1]에 PMU_MASK(0). 원래 스트림에 이 두 명령만 넣는다(`cms.gate(stream, k, k+1)`). 이동 = 창을 kernel 경계
하나씩 옮김.
- 모든 모델: W(A−1), W(A), W(A+1) = W(B), W(A+2). +2까지 두는 이유: TRM "남은 커널 최대 2개"로는 경계가 2 연산까지 늦을 수 있음.
- 차단 명령 변형(같은 규칙, 해당 모델만): A나 B의 설정에 DMA_WAIT/KERNEL_WAIT가 있으면, 처음 해당하는 창의 여는 위치를
  그 차단 명령 바로 뒤로 옮긴 창 하나 추가 — mobilenet W(A)(KERNEL_WAIT n=1, DMA_WAIT), rnnoise W(B)(DMA_WAIT),
  wav2letter W(A)(DMA_WAIT). 나머지 4개는 해당 없음(`NOT_APPLICABLE`).
- 대조: 같은 캠페인에서 마스크 없는 `ctl` 1회(교란 확인: CPU 추론 사이클 `infer_cpu`가 ctl의 RUN 폭 안).

**판정 기준(계약으로 고정할 안).** set A, 측정 RUN 중앙값. S_A = A의 최소 MAC 사이클(TRM 최대 처리량), M_k = W(k)의 mac_active.
1. 유효성: 모든 RUN 유효(model 모드), 교란 없음(위 대조). 아니면 `UNPROVEN`.
2. 위치: M_k ≥ S_A인 창이 정확히 하나 → `LOCATED(k−A)`(0 = 정렬, +1 = 한 칸 늦음 …); 없는데 ΣM ≥ S_A → `SPLIT`(A의 일이
   여러 창에 나뉨); 둘 이상 → `AMBIGUOUS`. RUN별 값으로 다시 판정해 모든 RUN이 같아야 함(아니면 `UNSTABLE`).
3. B(MAC 0 또는 작음): M_B > B의 최소 사이클이면 "B 창에 B 외의 MAC 활동" 기록(rnnoise·yolo: MAC 0인 연산의 mac_active 질문).
4. 모델 간: 7개 모델이 같은 `LOCATED(d)`면 `COMMON_SHIFT_CANDIDATE`, 아니면 `NO_COMMON_SHIFT`.
5. **3a만으로는 `EXACT_ATTRIBUTION`을 판정하지 않는다.** 위 판정은 필요조건이다. 정확성은 독립 기준(3b: 스트림을 연산 k 뒤에서
   끊고 STOP을 붙인 접두 스트림 P(k)의 mac_active 차이 = 연산별 MAC 활동)과의 일치로만 인정한다.

**예상 보드 비용 (2B-2 기록: 재부팅 153 s + 전송·RUN, set A만)**

| model | 부팅 1회 | 창 4 + ctl 1 | 차단 변형 | 합 |
| --- | --- | --- | --- | --- |
| kws | 3.0분 | 15분 | — | 15분 |
| ad | 3.8분 | 19분 | — | 19분 |
| rnnoise | 2.9분 | 15분 | 3분 | 17분 |
| vww4 | 3.5분 | 18분 | — | 18분 |
| yolo | 3.8분 | 19분 | — | 19분 |
| mobilenet | 11.7분 | 59분 | 12분 | 70분 |
| wav2letter | 38분 | 190분 | 38분 | 228분 |
| 합 | | | | **약 6.4시간** (wav2letter 3.8 h) |

3b 독립 기준(접두 스트림 P(A−1)…P(A+2), 모델당 4 boot)은 약 +4.5시간이고 STOP 실행 변경이라 별도 승인. wav2letter를 줄이는
유일한 방법은 펌웨어에 "한 부팅에서 스트림만 바꿔 여러 번 실행"을 넣는 것(이미지 변경, 별도 승인).

## Phase 3a pilot (owner 2026-11-09)

Owner: 6.4 h 전체 대신 pilot 먼저 — ad, yolo, mobilenet, rnnoise. 선정은 유지(사후 변경 금지, 식별력 부족은 결과에 명시).
판정은 진단 라벨만(`WINDOW_LOCALIZED` / `WINDOW_SPLIT` / `WINDOW_AMBIGUOUS` / `UNSTABLE` / `NOT_IDENTIFIABLE`); 귀속은 별도
검증. MAC 0 연산 창의 mac_active를 귀속 오류의 확정 증거로 쓰지 않는다. 계약 `evidence/s2b3_pilot/contract.md`
(`dc9b795`, boots 244–273, 약 2.8 h). ad는 A+2(op 7)가 A와 같은 conv라 정적으로 `NOT_IDENTIFIABLE`(데이터 전 기록).

**결과 (boots 244–273, 30/30 exit=0, TA profile 1, `results/fi101_stage2b3/pilot/README.md`)**: ad `NOT_IDENTIFIABLE`(정적),
mobilenet `WINDOW_AMBIGUOUS`(W(A)=W(B)=10,584 = A의 최소 사이클), rnnoise `WINDOW_LOCALIZED(+2)`(W(A+2) 144 ≥ 32),
yolo `WINDOW_AMBIGUOUS`(W(A−1) 1,512, W(B) 648 = A의 최소). 전제 조건 4/4 충족, RUN별 안정, 공통 오프셋 없음.
mobilenet `w_A_wait`: W(A)의 mac_active 중 7,335가 op 164 발행 전(대기 완료 전)에 있음. 사후 기술: mobilenet A−2(op 162)는
A와 MACs가 같은 conv — 고정 규칙은 A−1·A+1·A+2만 비교했다. 나머지 3개 모델·3b는 owner 결정 대기.

## Phase 3b 설계안 (owner 2026-11-09: 별도 설계, **보드 실험 미승인**)

Owner: STOP으로 나눈 prefix 실행은 원래 연속 실행과 스케줄이 다를 수 있어 곧바로 ground truth로 쓰지 않는다. 원래 실행을
유지한 계측과 실행을 분리한 계측이 각각 무엇을 검증할 수 있는지 구분한다.

| 계측 | 실행 | 검증할 수 있는 것 | 검증할 수 없는 것 |
| --- | --- | --- | --- |
| 마스크 창 (3a) | 원래 그대로(교란 검사 포함) | 마스크가 실행·출력을 바꾸는가; 카운트가 명령 위치 대비 어디에 모이는가; 창 합 = 합집합 창; 이벤트마다 같은 곳에 모이는가; RUN 간 안정성 | 창의 카운트가 어느 연산 것인가(기준 없음); 연산별 비용 |
| prefix P(k) = 연산 0..k + STOP | 꼬리가 바뀜(연산 k 뒤에 겹칠 연산이 없음, 다음 연산의 DMA 선반입 없음) | P(n) = 원래 스트림(항등 검사); 연산을 하나 더할 때 늘어나는 양 Δ_k = P(k) − P(k−1) — "그 prefix 스케줄에서의 한계 증가분" | Δ_k = 원래 실행에서 연산 k의 활동이라는 것(스케줄이 다름) |
| 장벽 KERNEL_WAIT n=0 (연산 k+1 앞) | 그 경계 하나만 직렬화, 나머지 그대로, 출력 동일해야 함 | 그 경계의 겹침이 전체 사이클에 주는 영향(직렬화 비용); 장벽 + 마스크 창이 그 경계에서 정확히 나뉘는가 | 원래 실행의 연산별 지연(장벽 비용을 원래 지연으로 쓰지 않음) |

**핵심 질문:** 어떤 이벤트가 "스케줄에 따라 변하지 않는 연산별 양"인가. 예: mac_active는 TRM상 "block traversal, not stalled"
사이클이라 겹침·대기와 무관하게 연산의 일만 셀 가능성이 있다(가설). stall·npu_active는 스케줄에 따라 바뀐다.

**설계(연산 A−1 … A+2, 3a와 같은 연산; 모델 범위는 3a 결과 뒤 결정):**
1. 서로 독립된 두 분리 방식으로 연산별 양을 구한다: (i) prefix 차이 Δ_k, (ii) 장벽 실행에서 장벽 + 마스크 창.
2. 이벤트별로 (i)과 (ii)가 일치하고, 둘의 합이 원래 실행의 합집합 창(3a의 `u`)과 일치하면 그 이벤트만
   "스케줄 불변 후보"로 둔다. 일치하지 않는 이벤트는 연산별 기준이 없다고 기록한다.
3. 스케줄 불변 후보가 생긴 이벤트에 한해, 3a 마스크 창 값과 비교해 원래 실행에서 창이 어느 연산의 일을 담는지 추정한다.
   이것도 "추정"이며, 정확한 그룹 귀속(EXACT)은 (i)·(ii)·원래 실행 세 가지가 같은 규칙으로 맞을 때만 주장한다.
4. 사전 확인(보드 1회, 승인 후): prefix 스트림이 runner에서 유효 RUN으로 끝나는지(model 모드: `stream_completed`는
   잘린 스트림 길이 기준, OFM은 판정하지 않음), 장벽 스트림의 출력이 ctl과 같은지.

비용(3a pilot 4개 모델 기준): prefix 4 + 장벽 3(경계 A−1|A, A|B, B|A+2) + 장벽+마스크 4 ≈ 모델당 11 boot → 약 4.6 h
(mobilenet 2.1 h). 펌웨어·이미지 변경 없음(blob만). 3a 결과를 본 뒤 범위를 줄여 다시 제안한다.

## Phase 3b 검토 (owner 2026-11-09 2차: 3b 보드 실험 **미승인**, 검토와 pilot 설계만)

Owner: STOP prefix와 KERNEL_WAIT는 원본 실행을 바꾼다. 각 방식의 완료 조건, 겹침·데이터 의존성에 미치는 영향, 원본과 비교해
검증할 수 있는 것, 둘이 일치해도 정확한 귀속을 보장하지 못하는 조건, 최소 3b pilot을 검토. mobilenet 대기 명령 전후 차이와
rnnoise `WINDOW_LOCALIZED(+2)`를 써서 **명령 창과 실제 처리부 활동의 시간 관계**를 검증할 방법. 해석 기준 유지:
LOCALIZED ≠ 귀속, 공통 오프셋 가정 금지, 모델별 결과를 하나의 정렬 규칙으로 보정하지 않음, STOP·장벽 결과는 원본의 ground
truth가 아님, yolo는 대조와 출력이 같을 뿐 독립 정답 검증은 미완.

### 1. 각 방식이 보장하는 완료 조건 (TRM 102685 r0p0 인용, 그 밖은 추론으로 표시)

| 명령 | 차단 | TRM이 보장하는 것 | 보장하지 않는 것 |
| --- | --- | --- | --- |
| `NPU_OP_STOP` | 예 | "Complete any outstanding operations and then transition to STOPPED state"; "The stop transition is complete only when all commands in the stream before the stop point are complete". 커널 완료 = "all result data has been written to memory" | STOP 뒤 명령은 실행되지 않으므로 원래 꼬리(다음 연산과의 겹침, 다음 연산 setup의 DMA)는 존재하지 않음 |
| `NPU_OP_KERNEL_WAIT n=0` | 예 | "waits for all previous kernel operations be complete" — 그때까지 다음 명령이 시작하지 않음 | mem2mem DMA(DMA_START로 큐에 들어간 것)는 기다리지 않음(TRM: DMA_WAIT가 별도). 장벽 앞 연산들끼리의 겹침은 원래대로 |
| `NPU_OP_KERNEL_WAIT n=1` (원본 mobilenet op 164 setup) | 예 | 직전 커널 연산(체인 포함) 하나만 남기고 완료 | 직전 연산은 계속 실행 중일 수 있음 |
| `NPU_OP_PMU_MASK` | 예 | "NPU has updated the PMU mask" | 커널 완료를 기다린다는 서술 없음; 마스크가 언제 이벤트에 적용되는지 문서 없음("debug feature only") |

추론(문서 아님): 커널 연산은 비차단이고 남은 커널은 최대 2개이므로, 마스크 명령이 파싱 시점에 적용된다면 창은 "명령이 지나간
시간"이고 연산 실행은 그보다 늦게 끝난다. 3a에서 rnnoise W(A+2), mobilenet `w_A_wait`가 이 추론과 모순되지 않는다(증명 아님).

### 2. 겹침과 데이터 의존성에 미치는 영향

- **STOP prefix P(k)** (연산 0..k + STOP): 연산 k 뒤의 겹침이 사라진다(k+1의 BLOCKDEP 겹침, k+1 setup의 DMA_START 선반입,
  메모리 경쟁). 0..k 사이 겹침은 원래대로. 데이터는 k까지의 결과만 메모리에 남는다. Δ_k = P(k) − P(k−1)은 "그 prefix 스케줄에서
  연산 k를 더할 때의 증가분"이며, P(k−1)의 꼬리(k−1이 혼자 끝남)와 P(k)의 k−1 구간(k와 겹침)이 서로 달라 k의 몫과 k−1의 겹침
  변화가 섞인다.
- **장벽 KERNEL_WAIT n=0** (한 경계에만): 그 경계의 겹침 하나만 없앤다. 출력은 같아야 한다(대기만 추가). 장벽 뒤 연산의 시작이
  늦어져 DMA·메모리 경쟁의 시점도 바뀐다. 장벽 앞에 큐된 mem2mem DMA는 계속 돌 수 있다.
- 공통: 둘 다 연산을 "앞뒤가 비워진 상태"로 만든다. 원본에서 겹쳐 실행될 때의 stall·대기·메모리 경쟁은 재현하지 않는다.

### 3. 원본 연속 실행과 비교해 검증할 수 있는 것

| 항목 | STOP prefix | 장벽 |
| --- | --- | --- |
| 출력 | P(n) = 원본만(항등 검사). 중간 P(k)는 정답이 없어 판정 불가(같은 P(k)끼리 RUN 간 재현만) | 전체 OFM = ctl (필수 전제) |
| 실행 교란 크기 | 마지막 연산 꼬리만 다름 — 크기는 측정 불가(원본에 대응 구간 없음) | 장벽만 넣은 실행 vs ctl: NPU·CPU 사이클과 이벤트별 합의 차이 = 그 경계 직렬화 비용 |
| 이벤트별 스케줄 민감도 | Σ_k Δ_k = P(n) = 원본 합 (항등식이라 증거 아님) | 장벽 유무로 합이 안 변하는 이벤트 = "그 경계에서 스케줄 불변 후보"(예: mac_active 가설) |
| 창과 실행의 시간 관계 | 없음(창을 쓰지 않음) | 장벽 + 마스크: 창을 열기 전/닫기 전에 비우면 창 값이 어떻게 바뀌는지 → 마스크 적용 시점과 in-flight 활동의 양 |
| RUN 유효성 | **현재 규칙으로는 무효 예상**: runner가 출력 영역을 RUN마다 독(poison) 값으로 채우고 `OUTPUT_CHANGED`(output_crc ≠ poison_crc)를 요구하는데, 모델 출력은 마지막 연산이 쓴다. prefix를 쓰려면 사전 등록한 별도 유효성(`OUTPUT_CHANGED` 제외, `stream_completed`는 잘린 길이 기준)이 필요 — **분석 규칙 변경이라 owner 승인 사항** | 현재 model 모드 그대로 |

### 4. 두 방식이 일치해도 정확한 귀속을 보장하지 못하는 조건

1. **같은 방향의 편향**: 두 방식 모두 경계를 비워 연산을 고립시킨다. 둘이 같은 값을 주면 "고립된 연산의 양"이 일관된다는
   뜻일 뿐, 원본에서 겹쳐 실행될 때 같은 양이라는 뜻이 아니다.
2. **스케줄 민감 이벤트**: stall, `npu_active`, 메모리 대기(`*_stalled`), 일부 AO 이벤트는 겹침·경쟁에 따라 바뀐다. 이런
   이벤트는 고립 값과 원본 값이 원리적으로 다를 수 있다.
3. **mac_active 불변은 가설**: TRM 정의("block traversal, not stalled")에서 나온 가설일 뿐이다. 블록 크기·job 분할이 문맥에
   따라 달라지면 깨진다.
4. **마스크 적용 시점 미문서**: 장벽 + 마스크 창이 경계에서 정확히 나뉜다는 것도 마스크가 파싱 시점에 적용된다는 가정에 기댄다.
   이 가정 자체를 아래 pilot에서 관찰한다.
5. **KERNEL_WAIT 밖의 활동**: mem2mem DMA, 체인(한 연산으로 셈), 가중치 디코더 선반입처럼 커널 완료와 묶이지 않은 활동은
   장벽으로 나뉘지 않는다.
6. **합 보존은 증거가 아님**: Σ Δ = P(n), 창 합 = u는 항등식 성격이라 어느 쪽 배분이 맞는지 말하지 않는다.
7. **작은 값**: rnnoise A의 최소 32사이클처럼 수십 사이클 규모는 마스크 전환 자체의 잔여 활동과 구분이 어렵다.

### 5. 수정된 3b pilot 설계 안 (보드 미승인; 모델 2개·연산 1–2개)

**목적: 명령 창과 실제 처리부 활동의 시간 관계를 관찰**한다. 연산별 귀속은 판정하지 않는다. 결과 라벨은 계약에서 사전 등록한다.

- **모델과 연산** (3a와 같은 A, 선정 변경 없음):
  - rnnoise A = 37: 3a 결과는 W(A)=8, W(A+2)=144. 작은 A가 두 창 뒤에 모이는 사례다.
  - mobilenet A = 164: `w_A_wait`에서 W(A)의 7,335가 A 발행 전에 있었다. 원본 setup에 KERNEL_WAIT n=1이 있다.
- **arm** (각각 3a `w_A` 또는 `ctl`에서 명령 하나만 다름):

  | arm | 내용 | 무엇을 관찰 |
  | --- | --- | --- |
  | `ctl`, `ctl2` | 원본 (A/A) | 기준·드리프트 |
  | `w_A` | 3a와 같은 창 (재현 확인) | 다른 날 같은 값인가 |
  | `w_A_dopen` | W(A)를 여는 PMU_MASK(1) 바로 앞에 KERNEL_WAIT n=0 | 열 때 in-flight 활동 제거 → `w_A − w_A_dopen` = 열기 시점에 남아 있던 앞 연산들의 몫(이 스케줄 기준) |
  | `w_A_dclose` | W(A)를 닫는 PMU_MASK(0) 바로 앞에 KERNEL_WAIT n=0 | 닫기 전에 A까지 완료 → `w_A_dclose − w_A` = 원래 창이 닫힌 뒤에 일어나던 활동 |
  | `w_A_dboth` | 둘 다 | 앞뒤가 비워진 A 하나의 활동(고립 값) |
  | `bar_open`, `bar_close` | 같은 위치 장벽만, 마스크 없음 | 출력 = ctl, 직렬화 비용, 장벽 arm의 교란 기준 |
  | rnnoise만 `w_next`, `w_next_dopen` | W(A+2)와, 그 창을 열기 전에 비운 것 | 144가 열기 전에 발행된 작업의 in-flight 활동인가 |
  | rnnoise만 `bar_next_open` | `w_next_dopen` 위치 장벽만, 마스크 없음 | 그 arm의 교란 기준 |

- **시간 관계 판독** (사전 등록할 값; 어느 것도 "A의 것"이라는 판정 아님):
  - 마스크가 파싱 시점에 적용된다면 다음이 함께 나와야 한다:
    - `w_A_dopen`이 작다(A가 막 시작한 부분만).
    - `w_A_dclose` ≥ S.
    - `w_A_dboth` ≥ S.
    - rnnoise `w_next_dopen` ≈ 0.
  - 마스크 명령이 앞선 작업의 완료를 기다린다면 `w_A ≈ w_A_dclose`이고, `w_A_dopen`은 `w_A`에서 크게 줄지 않는다.
  - 어느 쪽에도 맞지 않으면 `TIMING_UNRESOLVED`로 기록한다.
  - mobilenet: `w_A_dopen` ≤ `w_A_wait`(3,249)여야 한다(원본 n=1 대기보다 더 비우므로). 아니면 그 자체를 보고한다.
- **전제** (위반 시 `UNPROVEN`):
  - 모든 RUN 유효, ctl2 = ctl.
  - 장벽 arm의 출력 = ctl.
  - 장벽 + 마스크 arm의 CPU 사이클 = 같은 위치 장벽만 arm의 CPU 사이클(교란 기준을 ctl이 아니라 짝 장벽 arm으로).
- **STOP prefix**: 위 장벽 pilot과 분리한다. rnnoise P(A−1), P(A) 2 boot(약 6분)로 실행·유효성만 확인하며, `OUTPUT_CHANGED` 제외 유효성은 별도 승인을 받는다. 승인이 없으면 prefix는 3b pilot에서 뺀다.
- **필요한 구현** (보드 없이, 승인 후):
  - `cms`에 KERNEL_WAIT·STOP 삽입 helper를 추가하고 테스트와 변이 검사를 한다.
  - blob 검증: 삽입 명령을 빼면 원본과 바이트가 같아야 한다.
  - 판정 스크립트를 쓰고 변이 검사를 한다.
  - 펌웨어·이미지 변경은 없다.
- **비용** (파일럿 실측: rnnoise 3.0분/boot, mobilenet 11.9분/boot):
  - rnnoise 11 boot ≈ 35분.
  - mobilenet 8 boot ≈ 1.6 h.
  - 합 ≈ 2.1 h. prefix 확인을 넣으면 +6분.
  - 최소안은 rnnoise만 ≈ 35분.
