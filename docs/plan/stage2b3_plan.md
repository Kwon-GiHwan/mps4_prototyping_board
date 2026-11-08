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

**연산 선택 규칙 (모든 모델 동일, 정적으로 결정):** 기준 연산(anchor) = Vela 연산 1개가 stream 연산 1개로만
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
