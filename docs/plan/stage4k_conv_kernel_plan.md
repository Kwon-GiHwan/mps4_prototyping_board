# Stage 4K — Conv 1×1·3×3 MAC 하드웨어 특성: 기존 증거 확인과 정적 분석 (2026-11-14, 보드 실행 없음)

> **상태(2026-11-15):** 보드 측정 완료(boot 369–378, TA profile 1), 결과 `results/fi101_stage4k/README.md`, 계약 `evidence/stage4k/contract.md`.

- **범위:** owner 지시 "Ethos-U85 Stage 4 확장 — Conv 1×1·3×3 MAC Hardware Characterization"의 Phase 1–4.
  보드 배포·RUN·계약 동결은 하지 않았다.
- **보드 계약 초안:** `evidence/stage4k/contract_draft.md` (동결 전).
- **분석 도구:** `host/analysis/stage4k.py`. 산출물은 `results/fi101_stage4k/`에 있다.
- **측정 조건(기존 값의 출처):** FI101 Ethos-U85 1024 MAC, **TA profile 1**(MLEK sys_dram_mid), Driver Runner. 이미지는 아래에 따로 적는다.

## 1. Phase 1 — 기존 결과 재확인 (원시 RUN에서 다시 계산, `stage4k.py prior` → `prior.json`)

| 1×1 Cin | 출처 (이미지, boot) | MAC_ACTIVE | MAC_DPU | 유효 MAC / MAC_ACTIVE | DPU / MAC | NPU_ACTIVE pass A (range) | MAC_ACTIVE / NPU_ACTIVE |
| ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 16 | Stage 4, `83398c7`, 330 | 2,304 | 1,152 | 384 | 0.5 | 21,207 (367) | 0.109 |
| 16 | 4C-2, `83398c7`, 344 | 2,304 | 1,152 | 384 | 0.5 | 21,479.5 (1,299) | 0.107 |
| 16 | placement A, **`70090f1`**, 367 | 2,304 | 1,152 | 384 | 0.5 | 21,086.5 (617) | 0.109 |
| 32 | 4C-2, `83398c7`, 345 | 4,608 | 2,304 | 384 | 0.5 | 25,622.5 (407) | 0.180 |
| 40 | 4C-2b, `83398c7`, 348 | 3,456 | 3,456 | 640 | 1.0 | 22,454.5 (101) | 0.154 |
| 48 | 4C-2b, `83398c7`, 349 | 3,456 | 3,456 | 768 | 1.0 | 22,331 (887) | 0.155 |
| 64 | 4C-2 346 / 4C-2b 350, `83398c7` | 4,608 | 4,608 | 768 | 1.0 | 24,182.5 (997) / 24,554 (449) | 0.19 |

모두 TA profile 1이다. 측정 RUN 4회 모두에서 MAC_ACTIVE·MAC_DPU_ACTIVE의 range는 0이다.

**지시서의 대표값 표는 원시 데이터와 정확히 일치한다.**
- 테스트 `test_stage4k.Prior`는 기대값을 모듈에서 읽지 않고 테스트에 직접 적은 값과 비교한다.
- 근거 범위: 1×1, 24×24, Cout 96이고, Cin마다 boot 1회다(Cin 64만 2회).

**관측과 해석을 나눈다.**
- **관측:**
  - PartKernel(Cin 16, 32)에서는 MAC 활성 사이클당 유효 MAC이 384, DepthFirst(Cin 40, 48, 64)에서는 640/768/768이다.
  - Cin 40과 48의 MAC_ACTIVE는 같다.
  - Stage 4의 cin15(PartKernel, 다른 OFM block)도 2,304로 Cin 16과 같다.
- **해석의 한계:**
  - 이 값들은 "Cin을 16의 배수로 올린 양"과 부합한다.
  - 그러나 하드웨어가 padding 채널을 실제로 계산한다는 증거는 아니다.
  - Vela 전략 전환(Cin 32→40)이 하드웨어 고정 전환점이라는 증거도 아니다.
  - Cin, traversal, IFM block 깊이, weight order는 함께 바뀌었고 분리되지 않았다.

**기준 환경.**
- 이미지 `70090f1`은 Stage 4 placement 실험의 이미지다.
  - boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`(16 B 0).
  - 보드 staging `~/evsweep_s4p`와 컨테이너 `/work/driver_s4p_img/image`의 sha256이 같다.
- 이 이미지에서 DRWL word 7 = 0(DDR/EXT)인 실행은 Stage 4 conv_base를 재현했다 (placement P1 PASS).
  - MAC·DPU·pass B beat 7종·출력 CRC가 같았다.
  - NPU_ACTIVE 차이는 −120.5로 허용폭 617 안이었다.
- 같은 판정 함수(`stage4k.reproduce`)로 4C-2 boot 344(`83398c7`)와 placement A(`70090f1`)를 비교했다 (보드 없이 실데이터 dry run).
  - 비교 항목: MAC·DPU 동일, 출력 sha256 동일, 공통 상수 카운터 10개 동일, NPU_ACTIVE 차이 393 ≤ tol 1,299.
  - 결과: PASS.
- **판정:**
  - 기존 1×1 결과는 새 실험의 **재현 기준**으로 쓸 수 있다.
  - 그러나 3×3과 직접 비교하는 1×1 값은 같은 이미지·같은 세션에서 다시 측정한다(계약 초안 §2).
  - 재빌드 없이 `70090f1`을 그대로 쓴다.

**재사용 자산.**
- 생성기: `stage4c_models.py`(4C-2 채널 규칙), `stage4_compile.py`(Gate B, DRWL `--ifm`), `pack_vela_workload.py`.
- 분석: `stage4.py`(output check, Gate C, pair 규칙), `stage4c1/4c2.py`(CMS 레지스터, ublock·IFM step), `stage4c2b.py`의 가설 판정 방식.
- 보드: `run_driver_campaign.sh`(`STOP_ON_INVALID`), `sudo_session.sh`.

## 2. MAC 정의 (`stage4k.macs`)

| 이름 | 정의 | 1×1 | 3×3 (24×24, SAME) |
| --- | --- | --- | --- |
| nominal (= tflite N_MAC = Vela MAC 수) | H·W·Cout·k²·Cin, padding 위치 탭 포함 | 24·24·96·Cin | 24·24·96·9·Cin |
| valid (논리적으로 유효한 탭) | (kH − t)(kW − t)·Cin·Cout, t = ⌊k/2⌋(⌊k/2⌋+1) | = nominal | 70·70·96·Cin = nominal × 0.9452 |
| c16 | nominal에서 Cin을 16의 배수로 올림 | 4C-2b의 관측에서 온 정규화일 뿐, 하드웨어 단위가 아님 | |

- "유효 MAC / MAC_ACTIVE"는 별도 표시가 없으면 **nominal** 기준이다(기존 384/768과 같은 정의). valid 기준 값도 함께 적는다.
- SAME padding의 0 탭을 하드웨어가 계산하는지는 모른다. nominal과 valid 중 어느 쪽과 맞는지는 측정이 가려야 할 가설(아래 §5)이다.

**이론 최대 처리율.**
- Arm *Ethos-U85 NPU Technical Overview* 102684 Issue 03의 표 "NPU Configuration (MACs/CC)"에 1024가 있다.
- 보드 CONFIG 레지스터의 `macs_per_cc` = 10(2¹⁰)으로 1024 MAC 구성임을 확인했다.
- 이 문서는 8×8 INT8 MAC 수만 준다. Conv, DWConv 같은 **연산별 최대 처리율 표는 공개 문서에서 확인하지 못했다.**
  - TRM 102685는 입수하지 못했다.
- 따라서 "상대 효율" = MAC / (1024 × cycles)로 정의한다. 이 값은 구성 MAC 수 대비 비율이고, Conv 전용 공식 peak 대비가 아니다.
- DWConv에 대해 문서들에 적힌 128 MAC/cycle(`stage2b3_plan.md`)은 이번 연산과 무관하므로 쓰지 않는다.

## 3. Phase 2 — 10개 후보 컴파일과 정적 분석

**생성 규칙(`stage4c_models.py k3`).**
- IFM은 커널과 무관하게 Cin별로 같다. 4C-2 규칙인 128채널 확장의 앞 Cin이며, 1×1과 3×3의 IFM sha256이 5/5 같다.
- 3×3 weight (96,3,3,Cin)의 구성:
  - 중앙 탭 = 같은 Cin의 1×1 weight.
  - 나머지 8탭 = `K3_SEED` 20261114에서 Cin 128로 한 번 뽑아 앞 Cin만 자른 값.
- bias와 OFM scale은 base(`s4_conv_base`)의 값이며, 10개 모두 같은 양자화다.
- RELU6, stride 1, SAME이다.
  - 1×1은 기존 산출물 그대로 VALID다.
  - 1×1을 SAME으로 다시 써도 명령 스트림과 CPU reference가 5/5 바이트 동일했다 (대조군 `s4k_conv1x1same_*`).
- 결정성: 1×1 다섯 개는 기존 DRWL·tflite·CMS·reference와 바이트 동일하게 다시 만들어졌다. 3×3은 두 번 빌드해 바이트 동일했다.

**결과.** Gate B 15/15 PASS(NPU 단일 op, CPU fallback 없음, Conv 커널만, MAC 수 = 정의, 같은 Vela 출력). Vela 5.0.0, MLEK 옵션(`--accelerator-config ethos-u85-1024 --optimise Performance --memory-mode Dedicated_Sram --system-config Ethos_U85_SYS_DRAM_Mid_1024`).

| Kernel | Cin | Vela 전략 | OFM / IFM block | Ublock | IFM step (커널별) | IFM-block 깊이 채움 | OFM block 채움 | Ublock 채움 | MAC 수 nominal (valid) | weight B | Vela NPU / MAC / AO cycles | 예상 비교 목적 |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1×1 | 16 | PartKernel | 6×12×96 / 6×12×16 | 2×2×32 | 1 | 1.0 | 1.0 | 0.75 | 884,736 | 2,752 | 16,660 / 8,019 / 4,224 | 재현 gate(같은 이미지 boot 367), 기준 |
| 1×1 | 32 | PartKernel | 6×12×96 / 6×12×16 | 2×2×32 | 2 | 1.0 | 1.0 | 0.75 | 1,769,472 | 4,928 | 17,231 / 14,163 / 4,992 | 재현, PartKernel 비례 |
| 1×1 | 40 | **DepthFirst** | 6×12×96 / 6×12×64 | 2×2×32 | 1 | 0.625 | 1.0 | 0.75 | 2,211,840 | 4,992 | 16,651 / 4,947 / 3,840 | 재현, 16채널 올림 기준 |
| 1×1 | 48 | DepthFirst | 6×12×96 / 6×12×64 | 2×2×32 | 1 | 0.75 | 1.0 | 0.75 | 2,654,208 | 5,760 | 16,682 / 4,947 / 3,840 | 재현 |
| 1×1 | 64 | DepthFirst | 6×12×96 / 6×12×64 | 2×2×32 | 1 | 1.0 | 1.0 | 0.75 | 3,538,944 | 7,296 | 16,709 / 5,331 / 3,888 | 재현 |
| 3×3 | 16 | PartKernel | 24×10×32 / 26×12×16 | 2×2×32 | 1 | 1.0 | 0.8 | 0.75 | 7,962,624 (7,526,400) | 16,432 | 14,487 / 10,993 / 4,896 | 같은 traversal·IFM block 깊이에서 커널 크기 |
| 3×3 | 32 | PartKernel | 같음 | 2×2×32 | 2 | 1.0 | 0.8 | 0.75 | 15,925,248 (15,052,800) | 32,800 | 27,944 / 21,361 / 6,336 | PartKernel 내 Cin 비례 |
| 3×3 | 40 | PartKernel | 같음 | 2×2×32 | 3 | 0.833 | 0.8 | 0.75 | 19,906,560 (18,816,000) | 42,240 | 40,020 / 31,729 / 7,776 | 채널 단위(가설 8개를 모두 가름) |
| 3×3 | 48 | PartKernel | 같음 | 2×2×32 | 3 | 1.0 | 0.8 | 0.75 | 23,887,872 (22,579,200) | 49,104 | 41,069 / 31,729 / 7,776 | 40과 짝(계단 확인) |
| 3×3 | 64 | PartKernel | 같음 | 2×2×32 | 4 | 1.0 | 0.8 | 0.75 | 31,850,496 (30,105,600) | 65,424 | 54,195 / 42,097 / 9,216 | 범위 끝, 1×1 64와 비교(traversal 다름) |

- 10개 모두 커널 2개(OFM slice 16 + 80, IFM depth = Cin, ACC_INPUT_RESET 같음)이다.
- OFM ublock은 144 + 432 = 576개이다.
- CMS 길이는 모두 520 B이다.
- weight stream은 커널당 4개(WD 4)이다.
- 그 밖의 차이는 kernel 크기 레지스터, block 레지스터, weight·DMA 길이뿐이다.
- 출처: `results/fi101_stage4k/static.json`, `stage4k_static.csv`.

**1×1과 3×3의 전략 차이.**
- 1×1은 Cin 32→40에서 PartKernel→DepthFirst로 바뀌고, IFM block 깊이도 16→64, weight order도 함께 바뀐다(4C-2와 같음).
- **3×3은 Cin 16–64 전 구간에서 PartKernel이고 IFM block 깊이 16이다.** 전환 경계가 없다.
  - 그 결과 3×3에서는 Cin이 바뀌어도 traversal과 block 구성이 고정된다.
  - 이 덕분에 3×3 다섯 점은 **"같은 실행 구성에서 Cin만 바뀐 비교"**가 된다(1×1에서는 할 수 없던 비교).
- 3×3 OFM block(24×10×32)은 W 방향 채움이 0.8이다. 1×1의 6×12×96은 1.0이다.
  - 같은 PartKernel이라도 1×1과 3×3은 OFM block이 다르다.
  - 따라서 Cin 16/32의 커널 비교도 "traversal 같음, block 다름"이다.

**Vela 추정치(관측 아님).**
- MAC 사이클 추정은 3×3 Cin 40과 48에서 31,729로 같다. Vela의 성능 모델이 Cin을 16 단위로 올려 계산한다는 뜻이다(컴파일러 모델에 대한 사실).
- Vela의 MAC 사이클당 MAC은 3×3 PartKernel에서 약 724–757, 1×1 PartKernel에서 110–125이다.
- 1×1의 실측 MAC_ACTIVE(2,304)는 Vela MAC cycles(8,019)와 크게 다르다. 그래서 Vela 추정치는 예측 근거로 쓰지 않고 보고만 한다.

## 4. 보드 측정이 필요한 연구 질문 (기존 결과만으로 답할 수 없는 것)

| RQ | 기존 결과로 말할 수 있는 것 | 측정이 필요한 것 |
| --- | --- | --- |
| RQ1 커널 크기 | 1×1의 384(PartKernel)/768(DepthFirst) | 3×3의 MAC 활성 사이클당 처리율. 같은 이미지·세션의 1×1과 비교 |
| RQ2 채널 단위 | 1×1 DepthFirst에서 Cin 40 = 48 (16 올림과 부합) | 3×3 PartKernel에서 Cin 40과 48이 같은지, 16→32→48→64가 Cin에 비례하는지 |
| RQ3 컴파일러 전략 | 1×1 전환 경계 32→40(컴파일), 3×3 경계 없음(컴파일, 이 문서) | 고정된 PartKernel 3×3에서의 처리율과, 전략이 바뀌는 1×1의 처리율 관계 |
| RQ4 계산 vs 실행 | 1×1: MAC_ACTIVE ×2에서 NPU_ACTIVE +19–27 % | 3×3에서 MAC 수가 9배일 때 NPU_ACTIVE 변화, AO·WD·WD_STALLED·beat의 동반 변화 |
| RQ5 하드웨어 한계 | 1×1: MAC_ACTIVE 기준 37.5 % / 75 %, NPU_ACTIVE 기준 4–19 % (1024 MAC/CC 대비) | 3×3이 어느 조건에서 1024에 가까워지는지 |

## 5. 사전 등록 가설 (MAC_ACTIVE 값, `stage4k.py predict` → `predictions.json`)

- 처리율 r ∈ {384, 768}과 양 a ∈ {nominal, valid, c16, valid_c16}을 조합한 8개 값이다. 1×1에서 본 두 처리율을 3×3에 대입한 것이다.
- 메커니즘이 아니라 값의 닫힌 집합이다. 3×3 Cin 40에서는 8개가 모두 다르다.

| 3×3 Cin | R384_nominal | R384_valid | R384_c16 | R384_valid_c16 | R768_nominal | R768_valid | R768_c16 | R768_valid_c16 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 20,736 | 19,600 | 20,736 | 19,600 | 10,368 | 9,800 | 10,368 | 9,800 |
| 32 | 41,472 | 39,200 | 41,472 | 39,200 | 20,736 | 19,600 | 20,736 | 19,600 |
| 40 | 51,840 | 49,000 | 62,208 | 58,800 | 25,920 | 24,500 | 31,104 | 29,400 |
| 48 | 62,208 | 58,800 | 62,208 | 58,800 | 31,104 | 29,400 | 31,104 | 29,400 |
| 64 | 82,944 | 78,400 | 82,944 | 78,400 | 41,472 | 39,200 | 41,472 | 39,200 |

- 어느 것과도 맞지 않으면 `NONE_MATCHED`이다. 이것도 정상적인 결과이고, 측정 뒤 계수를 맞추지 않는다.
- R384_c16은 "4 사이클 × OFM ublock × IFM step × 9 탭"과 같은 값이다. 이 일치는 정의상 같다는 뜻이고, 독립 근거가 아니다.

## 6. 연산량이 비슷한 보조 비교군 (제안만, 보드 계획에 넣지 않음)

- 3×3 Cin 16(7.96 M MAC)과 연산량이 비슷한 1×1은 Cin 144(7.96 M)이다. 3×3 Cin 32(15.9 M)에는 1×1 Cin 288이 해당한다.
- 이 짝은 MAC 수를 맞추지만 IFM 크기·weight 크기·Vela 전략이 달라진다. 인과 분리를 해 주지 않는다.
- 필요하면 별도 승인 뒤 컴파일만 먼저 한다.
