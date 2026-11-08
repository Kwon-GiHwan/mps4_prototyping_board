# Stage 2B-3 Phase 1·2 — 명령 실행 정적 분석과 기존 데이터 재검토 (2026-11-08)

계획 `docs/plan/stage2b3_plan.md`. **새 보드 측정 없음.** 정적 분석(명령 스트림·TRM·Vela 소스)과 기존 데이터
(2B-2 boots 212–243, 2B-0b boots 177–211, 모두 **TA profile 1**, 이미지 `d0cd4775`)만 사용. `POST_HOC_DESCRIPTIVE`.
Ethos-U85 1024 MAC. 7개 모델 모두 같은 도구·같은 규칙.

## 재현

```
python3 host/analysis/cms_timeline.py results/fi101_stage2b3/timeline results/fi101_stage2_groups/vela_op_map <m_all blobs of 2B-2>
python3 host/analysis/s2b3_existing.py evidence/s2_groups/raw evidence/s2_mask/raw results/fi101_stage2b3/timeline results/fi101_stage2b3/existing_data
python3 host/analysis/s2b3_select.py results/fi101_stage2b3/timeline
```

m_all blob(2B-2, 계약 `evidence/s2_groups/contract.md`의 digest)의 명령 스트림 = 측정한 스트림. 테스트
`test_cms_timeline`(변이 15개 RED), `test_s2b3_existing`(10개 RED), `test_s2b3_select`(9개 RED).

## 출처 (TRM은 원문 인용, 문서 102685 r0p0 rev 0000-05)

본문은 `https://documentation-service.arm.com/documentation/102685/0000/<slug>` (`Accept: application/hal+json`,
`content` = base64 HTML; `docs/reference/ETHOS_U85_PMU_REFERENCE.md` 7절과 같은 방법). Vela 5.0.0 C++ 코어(Regor)
소스는 `gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-vela` commit `1626366f`, `ethosu/regor/architecture/ethosu85/`.

| 항목 | 원문 | slug |
| --- | --- | --- |
| 발행/차단 | "A command is blocking if following commands cannot be issued until the command is completed." 표: `NPU_OP_<KERNEL>` Blocking **No**, 완료 = "NPU has calculated the result and the memory system has accepted all result writes." `NPU_OP_PMU_MASK` Blocking **Yes**, 완료 = "NPU has updated the PMU mask." | `Programmers-model/Command-stream-architecture/Command-types/Command-issue-and-completion` |
| 남은 커널 수 | "In this version of the architecture, when a command starts there are at most two kernel operations remaining." "Thus a chain counts as a single outstanding operation." | `Programmers-model/Instruction-index-for-cmd0-stream/NPU-OP-KERNEL-WAIT-instruction` |
| KERNEL_WAIT | "Wait for n or fewer kernel operations to be remaining before starting the next command. A kernel operation is remaining if it has been issued but is not yet complete." | 같은 곳 |
| BLOCKDEP | "Block dependency offset for kernel operations." 3비트(0–7). **값의 의미는 TRM에 서술 없음.** Regor `CheckOverlap`: 이전 연산의 마지막 job들과 현재 연산의 처음 job들이 겹치지 않는 최대 오프셋, 최대 7(`MaxBlockdep`) | `.../NPU-SET-BLOCKDEP-instruction` |
| PMU_MASK | "Enable or disable PMU counting (debug feature only)." 적용 시점·진행 중 연산의 계수 방식은 **TRM에 없음** | `.../NPU-OP-PMU-MASK-instruction` |
| mac_active | "MAC is doing block traversal. Valid blk_cmd and not stalled" | PMEVTYPER 표 |
| MAC 최대 처리량 (1024, 8-bit) | Table 7: CONV2D 1024 MACs/cycle(2:4 sparsity면 2배), Fully connected "WB"(weight-bound), **DepthwiseConv2D 128** | `Operators-and-performance/...` "Convolution performance of the Ethos-U85 1024" |

TRM에 없는 것: BLOCKDEP 값의 서술 정의, 마스크 적용 시점, DMA·커널 동시 실행과 연속 커널 중첩의 명시 문장.

## Phase 1 — 명령 실행 정적 분석 (`timeline/<model>.csv`, 연산마다 한 줄)

열: 위치, 유형, BLOCKDEP, 앞 kernel 이후 동기화 명령, OFM·커널·IFM 깊이, MACs(레지스터로 계산), 2:4 sparsity,
입력을 마지막으로 쓴 연산(`ifm_src`, `ifm2_src`), Vela 연산.

- **MACs 검증:** 레지스터로 계산한 연산별 MACs의 Vela 연산 이름별 합이 Vela 값(`results/fi101_stage1/vela_block_fill_per_op.csv`)과
  7개 모델 모두 정확히 같음. 예외는 Softmax 분해의 ReduceSum(wav2letter 148 vs 4,292, mobilenet 1 vs 1,001) 하나.
- **2:4 sparsity:** ad·kws의 첫 conv 2개, vww4·yolo의 첫 conv 1개만 켜져 있다(MAC 비중 1.6–17.6 %). 나머지는 꺼짐.

| model | kernel ops | DMA_WAIT | KERNEL_WAIT (n=1) | BLOCKDEP 0인 경계 | BLOCKDEP > 0인 경계 |
| --- | --- | --- | --- | --- | --- |
| kws | 14 | 3 | 0 | 1 | 12 |
| ad | 14 | 2 | 0 | 1 | 12 |
| rnnoise | 48 | 11 | 0 | 35 | 12 |
| vww4 | 85 | 17 | 4 | 50 | 34 |
| yolo | 112 | 44 | 11 | 70 | 41 |
| mobilenet | 208 | 28 | 11 | 47 | 160 |
| wav2letter | 39 | 10 | 0 | 26 | 12 |

(경계 = 연산 i−1 → i, i ≥ 1. DMA_WAIT·KERNEL_WAIT는 그 경계의 설정 부분에 있는 수.)

**정적으로 확정되는 것:**
1. 커널 명령은 비차단이다. 명령 처리기는 연산 i를 발행하고 완료를 기다리지 않고 다음 명령을 읽는다. 남은(발행됐지만
   완료 안 된) 커널 연산은 명령 시작 시점에 최대 2개다.
2. PMU_MASK는 차단 명령이고 "마스크를 바꿨을 때" 완료된다. 앞선 커널 연산의 완료는 기다리지 않는다(이 경우 TRM은
   KERNEL_WAIT를 따로 둔다).
3. 2B-2의 연산 i 창 = [연산 i−1 발행 뒤의 PMU_MASK(1), 연산 i 발행 뒤의 PMU_MASK(0)]. 두 시점 모두 "명령 처리기가 그
   위치에 도착한 때"이고, 그 도착은 남은 커널이 2개 이하가 될 때까지 늦어진다. 즉 **창의 경계는 앞선 연산들의 완료
   시점에 묶이고, 연산 i 자신의 실행 시작·끝과는 무관하다.**
4. 연속한 두 커널 연산 사이에는 장벽이 없다(Regor는 KERNEL_WAIT를 DMA 앞에서만 낸다: vww4 4, yolo 11, mobilenet 11,
   나머지 0). 순서는 BLOCKDEP만으로 정해지고, BLOCKDEP > 0이면 다음 연산이 앞 연산의 마지막 블록들이 끝나기 전에 시작할
   수 있다(Regor 정의). BLOCKDEP > 0인 경계가 kws·ad 12/13, mobilenet 160/207.
5. 그룹 창들은 스트림을 빈틈없이 이어서 덮는다(모든 연산이 정확히 한 그룹). 그래서 **그룹 합 = 전체는 귀속이 맞든 틀리든
   성립한다.** 합계 보존은 귀속 정확성의 증거가 아니다.

**실측으로만 확인할 것:** 창 경계가 실제로 어느 연산의 완료에 묶이는가(TRM의 "최대 2개"를 경계에 적용하면 지연은 1–2
연산), 겹친 구간의 MAC 활동이 어느 창에 들어가는가, PMU_MASK가 시작될 때 이미 진행 중인 활동이 어떻게 세어지는가.

데이터 의존(`ifm_src`)은 근사다: OFM 바이트 범위 = base + stride_y × 높이로 잡았다. BLOCKDEP 7 ↔ 의존 없음 대응이
kws·ad·vww4에서는 거의 정확하지만, 스트라이프·체인·브로드캐스트가 있는 모델(mobilenet, yolo, rnnoise, wav2letter)에서는
어긋남 → 의존 판단에 쓰지 않고 참고로만 둔다.

## Phase 2 — 기존 데이터 재검토 (`existing_data/`)

### 1. 계산 자체 점검

- Vela MACs와 그룹 매핑: 레지스터 MACs = Vela MACs(위). 2B-2의 그룹 MACs를 연산별로 다시 합쳐도 같은 값.
- 2B-2 효율 = MACs / (1024 × mac_active). 상한 1은 conv에만 맞고, **sparsity 연산은 2048, depthwise는 128**이 상한이다
  (TRM Table 7). 그래서 연산별 최대 처리량으로 "최소 필요 MAC 사이클"을 계산해 창의 mac_active와 비교하는 **bound**를
  쓴다: bound = Σ(연산 MACs / 그 연산의 최대 처리량) / mac_active, 1을 넘으면 불가능. POOL·ELEMENTWISE·RESIZE는 TRM 표에
  처리량이 없어 0으로 둔다(제약하지 않음).
- 모델 전체(m_all) bound: 0.15(rnnoise)–0.97(wav2letter), 모두 ≤ 1.

### 2. 지연 가설 (창 i가 연산 i−d의 MAC 일을 담는다, d = 0–3), `efficiency_lag.csv`

| model | d = 0 | d = 1 | d = 2 | d = 3 | 남는 d |
| --- | --- | --- | --- | --- | --- |
| ad | CONV 2.80 | POOL 1.31 | CONV 2.80, m_b 1.48 | POOL 5.22 | **없음** |
| yolo | **DEPTHWISE 1.24** | 가능 | ELEMENTWISE 1.36 | 가능 | 1, 3 |
| mobilenet | 가능 | ELEMENTWISE 6.18 | 6.07 | 5.66 | 0 |
| vww4 | 가능 | 가능 | POOL 1.14 | 3.30 | 0, 1 |
| wav2letter | 가능 | 가능 | POOL 60.3 | 297 | 0, 1 |
| kws | 가능 | 가능 | 가능 | 가능 | 0–3 (판별 불가) |
| rnnoise | 가능 | 가능 | 가능 | 가능 | 0–3 (판별 불가) |

- **7개 모델 모두에 맞는 고정 지연은 없다.** d=0은 ad·yolo가, d=1은 ad·mobilenet이 배제한다.
- ad는 0–3 어느 값도 안 맞는다 → 창 하나가 여러 연산의 일을 조금씩 담는(겹침) 양상과 맞고, "정수 칸만큼 밀림"으로는
  설명되지 않는다.
- yolo는 2B-2에서 이상값으로 보이지 않았지만(효율 기준 1 이하), depthwise 상한 128을 쓰면 d=0에서 불가능하다
  (DEPTHWISE 창은 최소 65,063 사이클이 필요한데 mac_active는 52,438). ad 다음으로 두 번째 모델.
- kws·rnnoise는 이 검사로는 아무것도 배제되지 않는다(필요조건 검사의 한계).

### 3. MAC이 0인 창의 mac_active

ELEMENTWISE·RESIZE 연산은 MACs가 0인데, 그 창의 mac_active가 0이 아니다: yolo ELEMENTWISE 31,805(모델의 18.5 %),
mobilenet 11,321, vww4 1,564, wav2letter 626, rnnoise 216, yolo RESIZE 648. 원인은 둘 중 하나이고 기존 데이터로는 구분할 수 없다:
(a) 이 연산들도 MAC 블록 순회를 한다(TRM 정의 "MAC is doing block traversal"만으로는 판단 불가), (b) 앞 연산의 일이 넘어왔다.
→ 3a의 B 연산(MAC 0: rnnoise Add, yolo Resize)이 이것을 직접 가른다.

### 4. 이벤트별 어긋남 (`event_share.csv`, 그룹 중앙값 / m_all 중앙값)

같은 그룹 안에서도 이벤트마다 몫이 다르다. 예: ad CONV는 npu_active 0.32, mac_active 0.22, ao_active 0.36, wd_active 0.11.
kws CONV는 sram_rd_tran_req_stalled 0.999. 즉 모든 이벤트가 한 덩어리로 밀리는 것이 아니다. 처리부(WD → MAC → AO)마다
같은 연산을 처리하는 시점이 달라서, 창 경계에서 처리부별로 다른 연산의 일이 잡히는 것과 맞다(추정). `cc_stalled_on_blockdep`(33),
`mac_stalled_*`(52–55), `wd_stalled_by_wd_buf`(83)는 TRM이 Reserved로 둔 이벤트라 의미를 해석하지 않는다.

### 5. 마스크 명령이 실행을 바꾸는가 (`infer_cpu`, CPU 쪽 추론 사이클, set A)

마스크 arm에서는 NPU 사이클 카운터도 마스크되므로 CPU DWT 사이클로 비교한다(2B-0b 대조 `ctl` 대비).

| model | ctl RUN 폭 | ctl2 | m_all | g_CONV | 다른 그룹 |
| --- | --- | --- | --- | --- | --- |
| kws | 2.42 % | +0.04 % | +0.12 % | +0.80 % | +0.68 – +0.93 % |
| ad | 1.74 % | +0.13 % | −0.09 % | +0.44 % | −0.01 – +0.06 % |
| rnnoise | 2.78 % | −0.37 % | −0.52 % | +2.56 % | −1.34 – −0.55 % |
| vww4 | 1.09 % | −0.01 % | −0.22 % | +0.96 % | −0.15 – +0.34 % |
| yolo | 0.26 % | −0.19 % | +0.02 % | +0.18 % | −0.03 – +0.13 % |
| mobilenet | 0.29 % | −0.01 % | −0.04 % | +0.23 % | −0.01 – +0.09 % |
| wav2letter | 0.11 % | +0.01 % | −0.02 % | 0.00 % | −0.01 – 0.00 % |

모두 대조의 RUN 폭 안이다. 다만 창이 가장 많은 g_CONV가 7개 모델 모두에서 0 이상이라, 마스크 명령이 아주 작게 실행을
늦출 가능성은 배제하지 못한다. 서로 다른 부팅(2B-0b와 2B-2)끼리 비교한 것이므로, 3a에서는 같은 캠페인 안에 대조를 둔다.

## 결론 (정적 + 기존 데이터)

- 2B-2의 귀속 오류는 ad만의 문제가 아니다. 연산별 최대 처리량을 쓰면 yolo도 d=0에서 불가능하다. 7개 모델에 공통인
  정수 지연은 없다.
- 원인으로 정적 분석이 가리키는 것: 창 경계는 명령 처리기가 그 위치에 도착한 시점이고, 커널 연산은 비차단(최대 2개
  남음)이며 연속 커널 사이에 장벽이 없다(BLOCKDEP 겹침) → 창은 연산 i의 실행 구간이 아니라 "앞 연산들의 완료 사이"를
  잰다. 이것은 TRM 문장에서 나온 추론이고, 실측 확인은 3a의 몫이다.
- 기존 데이터로는 정확한 귀속 규칙을 찾을 수 없다. 합계 보존과 효율 ≤ 1은 필요조건일 뿐이다(owner 지시와 같음).
