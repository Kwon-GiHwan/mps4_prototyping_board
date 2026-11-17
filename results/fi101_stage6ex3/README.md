# Stage 6E-X3 결과 — 직렬화(KERNEL_WAIT n=0) + 그룹 PMU_MASK, kws·ad

**측정 조건**
- **TA profile 1**, EXT RLATENCY 500, placement 0, Pass A·B·C, boot당 3 set × 5 RUN(1 warm-up + 4).
- 이미지 f0baf8c: 14077be에 DRWL pmu_flags → PMCR.mask_en을 더한 것. bram `9b1844a3`.

**계약과 동결 커밋**

| 단계 | 계약 | preflight | 결과 |
|---|---|---|---|
| 본 계약 | `1d6e715` | — | — |
| Amendment A(mask_en) | 펌웨어 `f0baf8c` | `dc7709c` | `95a8de2`: boot 477 G1 FAIL |
| Amendment B(G1·결정적 카운터) | `6b292d8` | `0ce6071` | `9d59bf5`: boot 489 GS FAIL |
| Amendment C(그룹 창 안정성, 마지막) | `9081e77` | `532a9e3` | — |

**자료**
- 쓴 자료: 487·488(Amendment B, `raw_b/`)과 497–504(Amendment C, `raw_c/`). sha256는 일치한다.
- 판정 2회 실행 결과가 바이트 동일하다(`stage6ex3_summary.json`).
- 477과 489는 실패 기록으로만 남기고 다시 판정하지 않았다.
- X3 누적: 12 boot / 180 RUN. 모든 세션은 RESTORE VERIFIED, postflight 완료.

## 최종 판정

| 항목 | 판정 |
|---|---|
| Measurement | **VALID** (10/10 boot VALID, G1·GS·GM 통과) |
| Baseline Reproducibility | kws **REPRODUCED** (−0.41 %), ad **REPRODUCED** (+0.13 %, Δ 187 / 허용폭 3,613); 결정적 카운터 13개 정확 일치 |
| PMU_MASK Functionality | **FUNCTIONAL** |
| Group Partition Consistency | kws·ad **CONSISTENT** |
| Independent Reference Agreement | **AGREES** |
| Temporal Attribution Validity | **VALIDATED_FOR_KERNEL_UNITS**(MAC·DPU·AO·WD; mem2mem DMA의 AXI는 범위 밖) |
| Group Attribution | **VALIDATED** |
| Compute Explanation | **RESIDUAL_REDUCED** |
| Serialization | **SCHEDULE_EFFECT_OBSERVED** |
| Vela Fidelity | **INSUFFICIENT_EVIDENCE**(그룹 2개가 측정 변동 안에서 분류 경계에 걸림) |

## 그룹별 Unit 계측 (직렬 실행, pass A·B·C 측정 RUN 중앙값)

| 모델·그룹 | NPU_ACTIVE (range, 상대) | MAC | DPU | AO | WD | WD_STALLED | SRAM rd/wr beat | EXT rd beat | 387 |
|---|---|---|---|---|---|---|---|---|---|
| kws 원본 B0 | 91,444.5 (1,593) | 56,450 | 49,495 | 17,825 | 11,383.5 | 64,319 | 22,664 / 17,760 | 15,815 | 19,304.5 |
| kws 직렬 B1 | 105,074.5 (2,169) | 56,450 | 49,495 | 17,780.5 | 11,125.5 | 62,956.5 | 22,664 / 17,760 | 15,814 | 19,977.5 |
| kws G_V (op 2·4·6) | 26,117 (871, 3.3 %) | **11,700** | 10,530 | 4,031.5 | 3,881 | 13,012 | 3,375 / 3,375 | 8,898 | 7,982.5 |
| kws G_0 (op0, Cin 1) | 31,070 (479, 1.5 %) | **26,090** | 22,515 | 4,440 | 3,057 | 25,114 | 2,121 / 5,117 | 1,217 | 2,300.5 |
| kws G_R (나머지) | 47,805 (550, 1.2 %) | 18,660 | 16,450 | 9,303.5 | 4,167.5 | 24,463.5 | 17,168 / 9,268 | 5,699 | 7,852 |
| ad 원본 B0 | 146,136.5 (1,839) | 93,672 | 93,672 | 41,481 | 21,537.5 | 117,283.5 | 70,538 / 41,888 | 44,084 | 40,902 |
| ad 직렬 B1 | 164,292.5 (2,393) | 93,672 | 93,672 | 41,479 | 20,614 | 119,186.5 | 70,538 / 41,888 | 44,083 | 44,343.5 |
| ad G_V (op 2·4·6·8) | 79,780 (350, 0.4 %) | **60,480** | 60,480 | 15,001 | 16,839 | 60,581 | 40,448 / 14,976 | 35,856 | 27,640 |
| ad G_0 (op0, Cin 1 3×3) | 20,753 (1,359, 6.5 %; GS는 cap으로 통과) | **16,128** | 16,128 | 12,288 | 1,140 | 15,060 | 1,336 / 12,622 | 525 | 2,150.5 |
| ad G_R (DW·op10·12) | 64,766.5 (973, 1.5 %) | 17,064 | 17,064 | 14,193.5 | 2,469.5 | 43,175.5 | 28,754 / 14,290 | 7,702 | 13,738.5 |

- 그룹 AXI 값은 창 값이다. KERNEL_WAIT는 mem2mem DMA를 기다리지 않으므로 그룹 귀속 판정에 쓰지 않는다.
- **H-P 분할**: MAC·DPU는 그룹 합 = 직렬 전체(정확)다. AO·WD·NPU_ACTIVE도 허용폭 안이다(kws NPU 104,992 대 105,074.5; ad 165,299.5 대 164,292.5).
- **H-S**: 직렬화는 MAC·DPU를 바꾸지 않았다(SUPPORTED, 두 모델). 전송 beat도 같다.

## 핵심 결과

1. **독립 기준 일치**: 모델 안 연산의 MAC_ACTIVE가 단독·예측값과 정확히 같다.
   - kws G_0 = 26,090 = 6C F5 단독 측정.
   - kws G_V = 11,700 = h1uc 예측.
   - ad G_V = 60,480 = h1uc 예측.
2. **ad 잔차 33,192의 위치(H-A1 SUPPORTED)**:
   - G_0(op0) 16,128과 G_R 17,064의 합 = **33,192**로 정확히 같다. 잔차는 전부 검증 밖 연산(첫 Conv, DW 등)에 있다.
   - 6D가 R_PK3 연장(Cin 1→16 패딩)으로 낸 op0 외삽값 36,864는 실측 16,128의 2.3배 과대다. Cin 1 PartKernel은 단순 16 패딩이 아니다(kws F5와 같은 방향).
3. **직렬화 효과**(관측일 뿐, 순수 중첩 이득으로 단정하지 않음):
   - kws +13,630(+14.9 %, 허용폭 3,762), ad +18,156(+12.4 %, 허용폭 4,232).
   - 계산·전송량은 같고 실행시간만 늘었다. 장벽·명령 처리 비용은 분리하지 못했다.
4. **그룹 창 NPU 합 대 모델 원본**: 원본 NPU_ACTIVE는 그룹 비용 합보다 kws 12.9 %, ad 11.6 % 작다(겹침과 장벽 비용이 섞인 값).

## Vela 비교 (공식 분모 cycles_total = per-layer Op Cycles 합)

| 모델 | 원본 / cycles_total | 직렬 / cycles_total | 원본 / cycles_npu | 직렬 / cycles_npu |
|---|---|---|---|---|
| kws | 0.894 | 1.028 | 1.059 | 1.217 |
| ad | 0.985 | 1.108 | 1.042 | 1.171 |

| 그룹 | Vela Op Cycles(지배 항) | 직렬 NPU | ratio | 분류 |
|---|---|---|---|---|
| kws G_0 | 23,261 (NPU) | 31,070 | 1.336 | UNDER |
| kws G_V | 23,436 (DRAM ×3) | 26,117 | 1.114 | INSUFFICIENT(경계 1.1이 range 안) |
| kws G_R | 55,551 (DRAM 7, NPU 2) | 47,805 | 0.861 | OVER |
| ad G_0 | 21,874 (DRAM) | 20,753 | 0.949 | INSUFFICIENT(경계 0.9가 range 안) |
| ad G_V | 71,857 (NPU 3, DRAM 1) | 79,780 | 1.110 | UNDER |
| ad G_R | 54,597 (NPU 5, DRAM 2, SRAM 1) | 64,766.5 | 1.186 | UNDER |

- **직렬화와 Vela 합 사이의 거리**: kws는 직렬화가 Vela 합에 가까워졌다(|ln| 0.112 → 0.027). ad는 멀어졌다(0.015 → 0.102). 따라서 "직렬화가 Vela 오차를 줄인다"는 일반화는 성립하지 않는다.
- **그룹 오차의 방향**:
  - Cin 1 첫 Conv(kws G_0)는 1.34배 과소예측이다(NPU 항 지배).
  - DRAM 항이 지배하는 kws G_R는 과대예측이다.
  - ad G_V(NPU 항 지배)와 G_R는 과소예측이다.
  - 한 방향이 아니며, 원본 모델 비율의 일치(ad 0.985)는 그룹 오차의 상쇄로도 생길 수 있다.
- **cycles_npu 기준 비율**: 6-M·6D·6E-0 값과 같은 정의다. cycles_total 기준과 섞지 않는다(정오표 `evidence/stage6e0/erratum_vela_terms.md`).

## 모델 수준 설명력 (6D 대비)

**kws·ad의 MAC_ACTIVE**
- 그룹 실측으로 전량 분해되며, 검증 연산은 예측과 정확히 일치한다.
- 6D의 ad 판정 NOT_EXPLAINED(P/M 0.646)는 "검증 연산 예측은 맞고, 잔차는 검증 밖 연산 실측"으로 바뀌었다.
- 다만 이 실측은 직렬 조건의 값이다. MAC_ACTIVE는 스케줄 불변(H-S)이므로 원본 실행에도 같다고 볼 수 있다. 다만 이는 MAC·DPU에 한한다.

**NPU_ACTIVE**
- 그룹 비용(직렬) 합은 원본보다 12–13 % 크다.
- 원본의 그룹별 시간은 얻지 못했다. 그래서 실행시간 설명력은 여전히 미해결이다.

**7개 모델로의 적용 범위**
- 방법은 그대로 적용할 수 있다(펌웨어 플래그 + 직렬 스트림).
- 그룹 창 NPU_ACTIVE의 절대 변동(약 0.4–2.2k 사이클)보다 작은 그룹은 정량 판정이 어렵다.

## 미해결

- 직렬화 증가분의 내부 구성(장벽, 명령 처리, DMA 재배치)
- 원본 실행에서의 그룹별 시간
- Cin 1 PartKernel의 실제 처리 규칙
- DW stride 2 / C 276의 비용 규칙
- Vela 그룹 오차의 원인(NPU 항 과소, DRAM 항 과대)
- AXI 그룹 귀속(DMA)

## 테스트·불변성

- 테스트: `test_stage6ex3` 34, `test_cms_serial` 10, 펌웨어 관련(sim·contract·drwl·record).
- mutation: 판정·스트림 98/98, 펌웨어 14/14. test.sh ALL PASS.
- 기존 결과 파일 불변(477·489 자료와 판정 포함). 로컬 커밋만 했다.
