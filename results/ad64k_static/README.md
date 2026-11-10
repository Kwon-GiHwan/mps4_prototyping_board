# AD SRAM 예산 64 KiB — 정적 분석 (2026-11-11, 보드 측정 없음)

**질문.** 같은 AD 모델에서 예산 64 KiB의 실행 비용이 기준의 2.58배가 되고 예산 0보다도 커진 현상을 설명할
컴파일 구성상의 차이는 무엇인가 (owner 지시 2026-11-11).

**범위.**
- Stage 5-1의 AD 세 구성만 다룬다: Performance 384 KiB(기준), 64 KiB, 0.
- **TA profile 1**, 이미지 `83398c7`, Dedicated_Sram, Vela 5.0.0.
- 기존 측정값(boots 354–356)과 컴파일 산출물만 썼다. 새 보드 측정·예산·모델은 없다.
- 표시는 `POST_HOC_DESCRIPTIVE`다. 여기 어떤 값도 연산별 실측 시간이 아니다.
- Stage 2B H1/H2와 그룹별 카운터는 쓰지 않았다.

**재현.**
- 컨테이너: `python3 host/container/vela_op_map.py <out> [--vela-option=--arena-cache-size=N] ad_medium_int8.tflite` → `evidence/ad64k_static/vela_map/`
- 로컬: `python3 host/analysis/ad64k_static.py results/ad64k_static` → `per_kernel.csv`, `per_source_op.csv`

## 0. 측정 산출물과의 연결 (분석 도구가 매번 검사, 어긋나면 거부)

| 구성 | Vela 출력 (측정 DRWL 안 = op-map 재컴파일 = DRWL 기록) | command stream sha256 (= DRWL 기록 `cms_sha256`) | 측정 boot |
| --- | --- | --- | --- |
| 384 KiB | `b83f28f2…` | `093dcda9…` | 354 |
| 64 KiB | `22069237…` | `2afb5613…` | 355 |
| 0 | `638d2dba…` | `f83612be…` | 356 |

- 재컴파일 옵션은 측정 때와 같다(MLEK 옵션, 64 KiB·0은 `--arena-cache-size`만 추가). 여기에 `--enable-debug-db --verbose-high-level-command-stream`을 더했다.
- 디버그 옵션을 켜도 Vela 출력 파일이 바이트 단위로 같았다.
- kernel 대응은 다음 셋이 모두 맞을 때만 받아들였다:
  - debug-db `queue` offset = command stream kernel offset
  - Vela 고수준 명령의 연산 이름 = debug-db 최적화 연산
  - 레지스터 microblock(ACC_FORMAT) = Vela 로그 ublock
- 테스트 `host/tests/test_ad64k_static.py`(12개)가 있다. 변이 시험(`evidence/ad64k_static/mutate_ad64k.py`)은 **8/8 RED**이며, 해시로 원복했다.
- 대응을 확인하지 못한 kernel은 없다(`UNMAPPED` 0).
- 영역: region 0 = DRAM 상수, 1 = DRAM arena, 2 = SRAM fast scratch (Driver Runner의 Dedicated_Sram 구성).

## 1. 세 구성의 전체 비교표

**컴파일 구성 (정적).**

| 항목 | 384 KiB (기준) | 64 KiB | 0 |
| --- | ---: | ---: | ---: |
| 요청 예산 / Vela SRAM 사용 | 384 / 244.0 KiB | 64 / 59.8 KiB | 0 / 0 KiB |
| fast scratch / arena (B) | 249,856 / 1,024 | 61,280 / 147,456 | 0 / 245,760 |
| kernel 수 | 14 | **66** | 13 |
| command stream 길이 | 2,480 B | **13,512 B** | 2,264 B |
| cascade | 없음 | 연산 1–3 (16 stripe), 4–5·6–7 (각 3 stripe) | 없음 |

**정적 데이터 이동 (모두 int8 논리 크기, B).** Vela 고수준 명령의 IFM/OFM 영역과 레지스터의 가중치 길이·DMA 길이로
계산했다. 실제 버스 전송량이 아니다.

| 항목 | 384 KiB | 64 KiB | 0 |
| --- | ---: | ---: | ---: |
| 가중치 stream, DRAM에서 읽음 | 423,376 | **1,636,848** | 428,448 |
| 가중치 stream, SRAM에서 읽음 | 5,280 | 99,776 | 0 |
| 명시적 DMA (DRAM → SRAM, 레지스터 = Vela 고수준 DMA) | 9,440 | 20,880 | 0 |
| IFM 읽기: DRAM / SRAM (stripe 겹침 포함) | 2,048 / 643,476 | 267,424 / 615,828 | 644,500 / 0 |
| OFM 쓰기: DRAM / SRAM | 8 / 643,476 | 211,976 / 431,508 | 643,484 / 0 |
| **DRAM 읽기 합 (가중치 + IFM + DMA)** | 434,864 | **1,925,152** | 1,072,948 |
| **DRAM 쓰기 합 (OFM)** | 8 | 211,976 | 643,484 |

**측정값.** Stage 5-1, TA profile 1. NPU_ACTIVE는 Pass A/B 중앙값이고, 활동 카운터는 Pass A, 전송 카운터는 Pass B다. 괄호는 RUN 범위다.

| 카운터 | 384 KiB | 64 KiB | 0 |
| --- | ---: | ---: | ---: |
| NPU_ACTIVE A / B | 145,991 (1,584) / 145,916 | **376,999 (1,703) / 376,957** | 234,881 (2,456) / 234,100 |
| 기준 대비 (A / B) | — | +158.2 % / +158.3 % | +60.9 % / +60.4 % |
| MAC_ACTIVE / MAC_DPU_ACTIVE | 93,672 / 93,672 | 94,824 / 94,680 | 91,368 / 91,368 |
| AO_ACTIVE | 41,474 | 41,860 | 41,647 |
| WD_ACTIVE | 21,536 | **46,399** | 21,536 |
| WD_STALLED | 117,235 | 310,282 | 206,153 |
| SRAM 읽기 beat / transaction | 70,538 / 4,971 | 51,482 / 5,961 | 0 / 0 |
| SRAM 쓰기 beat / transaction | 41,888 / 2,972 | 28,779 / 2,154 | 0 / 0 |
| EXT 읽기 beat / transaction | 44,084 / 3,319 | **159,245** / 11,750 | 113,811 / 9,763 |
| EXT 쓰기 beat | 1 | 13,825 | 41,299 |
| (EXT beat × 16 B) 읽기 / 쓰기 | 705,344 / 16 | 2,547,920 / 221,200 | 1,820,976 / 660,784 |

- MAC·DPU의 RUN 범위는 0이다.
- stall은 서로 겹치므로 더하지 않는다.
- 정적 DRAM 크기와 EXT beat는 집계 대상이 같다고 가정하지 않는다. 두 표에 따로 둔다.

**Vela 추정** (summary, NPU 클럭 사이클, 네트워크 전체에 대한 Vela의 모델 값):

| 필드 | 384 KiB | 64 KiB | 0 |
| --- | ---: | ---: | ---: |
| `cycles_npu` (compute 추정) | 140,277 | 345,342 (×2.46) | 139,553 (×0.99) |
| `cycles_total` (전체 추정) | 148,328 | 443,065 (×2.99) | 269,222 (×1.82) |
| `dram_total_bytes` | 761,904 | 2,823,264 | 2,974,768 |

## 2. 변화가 집중된 원본 연산과 산출물 차이

원본 연산 번호는 TFLite 연산 순서다(debug-db `source`). 64 KiB의 kernel 66개는 모두 원본 연산 1–7에서 나왔다
(16 × 3 + 3 × 4 + 6). 원본 연산 8–13의 계산 설정·가중치는 기준과 같다. 단, 연산 8은 IFM을 DRAM에서 읽는다.

| 원본 연산 (형상, 유효 MAC) | 384 KiB | 64 KiB | 0 |
| --- | --- | --- | --- |
| **1** Conv 3×3 1→192 @32×32 (1,769,472) | 2 kernel (OFM 채널 16 + 176, 가중치 이중 버퍼); block 8×32×32; ublock 2×2×32 (1,792개) | **16 kernel** (2행 stripe, cascade); block 2×32×96; ublock 1,536개; 가중치 SRAM (DMA 4,816 B, stream 합 46,336 B) | 1 kernel; ublock 1,536개; 가중치 DRAM |
| **2** DW 3×3 s2 192 @16×16 (442,368) | 1 kernel; block 20×8×16; ublock 2×4×16 (384개); IFM SRAM 196,608 | **16 kernel** (1행 stripe); block 2×8×64; **ublock 768개**; IFM SRAM 380,928 (stripe 겹침으로 ×1.94) | 기준과 같은 구성, 모든 데이터 DRAM |
| **3** Conv 1×1 192→276 @16×16 (13,565,952) | 1 kernel; block 8×16×64; ublock 2×2×32; **가중치 DRAM 58,016 B 1회**; OFM SRAM | **16 kernel** (1행 stripe); block 1×16×288; ublock **1×4×32** (개수 576, 같음); **가중치 DRAM stream 928,256 B = 58,016 × 16**; **OFM → DRAM** 70,656 B | 1 kernel, 가중치 DRAM 1회 |
| **4·6** DW 3×3 276 @16×16 (각 635,904) | 1 kernel; block 16×16×32; IFM SRAM; 가중치 DRAM 3,104 B | 3 kernel (6행 stripe); block 6×16×64; **IFM DRAM** 97,152 (겹침 ×1.375); 가중치 DMA → SRAM 5,984 B | 1 kernel, DRAM |
| **5·7** Conv 1×1 276→276 @16×16 (각 19,501,056) | 1 kernel; block 8×16×64; 가중치 DRAM 87,376 / 87,344 B 1회 | 3 kernel; block 6×8×160; **가중치 DRAM ×3** (262,128 / 262,032 B); **OFM → DRAM** | 1 kernel, DRAM |
| 8 DW 3×3 s2 276 | SRAM | 같은 구성, **IFM을 DRAM에서** (70,656) | DRAM |
| 9–13 | SRAM | 같음 | DRAM |

- 64 KiB에서 가중치를 DRAM에서 다시 읽는 양은 기준 대비 +1,213,472 B다. 연산 3이 +870,240, 연산 5·7이 +349,440이고, 연산 4·6은 가중치가 SRAM으로 옮겨 가 −6,208이다.
- 연산 1·2의 가중치는 SRAM으로 한 번 DMA한 뒤 stripe마다 SRAM에서 다시 읽는다.
- 0은 연산 1이 1 kernel로 합쳐진 것 말고는 기준과 kernel 구성이 같다. 가중치 stream도 기준과 같고(428,448 B), feature map만 전부 DRAM에 있다.
- `acc_input`은 모든 kernel에서 0이다(입력 채널 방향의 kernel 간 누적 없음).

**MAC 활동과의 부합 (사후 산술, 원인 아님).** OFM ublock 수(Σ ⌈H/ub_h⌉·⌈W/ub_w⌉·⌈C/ub_c⌉)를 기준과 비교했다.
- 64 KiB: 연산 1이 −256, 연산 2가 +384, 연산 3–7은 0이다.
- 0: 연산 1만 −256이다.
- ublock당 9 사이클을 가정하면 64 KiB는 −2,304 + 3,456 = **+1,152**, 0은 **−2,304**다. 측정한 MAC_ACTIVE 변화(+1,152, −2,304)와 정확히 같다.
- 가정의 근거와 한계: "ublock당 9"는 Stage 4C-1의 DW 3×3(stride 1)에서 읽은 값이다. 여기서는 Conv 3×3(Cin 1)과 DW 3×3 stride 2에도 적용했으므로, 이 일치는 사후 기술이다.
- 연산 3의 ublock 모양 변경(2×2×32 → 1×4×32)은 개수가 같아서 MAC 변화에 기여하지 않는 것으로 계산된다.
- MAC_DPU_ACTIVE의 64 KiB 값(94,680, MAC보다 144 적음)은 이 계산으로 설명되지 않는다.

## 3. 확인된 사실, 가장 유력한 설명, 아직 필요한 증거

**확인된 사실** (정적 산출물과 측정값):
1. 64 KiB의 kernel 증가(14 → 66)는 전부 원본 연산 1–7의 cascade stripe 분할에서 나왔다. 연산 8–13은 기준과 같다.
2. 64 KiB에서는 연산 3의 가중치 전체(58,016 B)가 16개 stripe kernel마다 DRAM에서 다시 stream된다. 연산 5·7은 3번씩이다.
   - DRAM 가중치 stream 합: 423 KB → 1,637 KB (×3.87).
   - 0과 기준은 각 가중치를 한 번만 stream한다(423–428 KB).
3. **WD_ACTIVE는 64 KiB에서만 2.15배(46,399)였고, 0에서는 기준과 정확히 같았다(21,536).** 가중치 stream이 늘어난 구성에서만 WD 활동이 늘었다(함께 관측됨).
4. 0은 feature map을 모두 DRAM에 둔다. 정적 DRAM 쓰기(643 KB)와 EXT 쓰기(661 KB)는 64 KiB(212 KB / 221 KB)보다 많다.
   하지만 정적 DRAM 읽기 합(1.07 MB vs 1.93 MB)과 EXT 읽기(1.82 MB vs 2.55 MB)는 64 KiB가 더 많다.
5. MAC_ACTIVE 변화(+1.2 % / −2.5 %)는 작고, 연산 1·2의 ublock 수 변화와 산술적으로 맞는다(사후). 시간 증가(+158 %)와는 크기가 다르다.
6. Vela도 64 KiB > 0 > 기준 순으로 추정했다(`cycles_total`). `cycles_npu`도 64 KiB에서만 ×2.46 올랐다.
   Vela의 `dram_total_bytes`는 0이 64 KiB보다 크다. 측정한 EXT 읽기+쓰기 합은 64 KiB가 더 크다(2.77 MB vs 2.48 MB).

**가장 유력한 설명** (가설):
> 64 KiB 구성에서는 원본 연산 1–3이 16개의 1–2행 stripe cascade로 분할되었다. 그 결과 원본 연산 3의 가중치 전체가
> stripe마다 DRAM에서 다시 stream되었고(16회), 연산 5·7도 3회씩 다시 stream되었다. 연산 3·5·7의 출력과 4·6·8의
> 입력도 SRAM 대신 DRAM을 거친다. 이 반복 가중치 이동은 0 구성에는 없는 차이이며, 64 KiB가 0보다 느린 것의 원인
> 후보다. 다만 연산별 시간과 인과적 기여는 측정하지 않았다.

함께 바뀐 것이 있어 분리되지 않는다.
- kernel 수와 명령 길이(×5.4)가 늘었다.
- block이 작아졌다(1–2행).
- DW 연산 2의 IFM stripe 겹침 읽기(×1.94)와 ublock 증가가 있다.
- 연산 3–8 사이 feature map이 DRAM을 오간다.

**아직 필요한 증거.**
- 원본 연산별 시간: 얻지 못했다(Stage 2B 방법의 한계).
- 64 KiB의 +231k 사이클 가운데 반복 가중치 stream, 작은 block과 kernel 수, DRAM feature map이 각각 차지하는 몫은 이 자료로 나눌 수 없다.
- 측정 EXT 읽기는 정적 DRAM 읽기 합보다 270–750 KB 많다(세 구성 모두). 그 차이(halo 재읽기, 전송 단위, 다른 접근 등)는 설명하지 않았다.
- MAC_DPU_ACTIVE −144(64 KiB)는 설명되지 않았다.

**가장 중요한 비교 한 가지 (제안만, 실행은 별도 결정).**
- 먼저 보드 없이 64 KiB 주변 예산을 컴파일만 해서 쌍을 찾는다. 조건은 원본 연산 1–3의 cascade 분할은 64 KiB와 같고, 연산 3의 가중치 반복 stream만 다른 것이다(예: 가중치가 SRAM에 버퍼되는 예산).
- 그런 쌍이 있으면 그 두 구성만 측정한다(2 구성 × Pass A·B × 5 RUN = 20 RUN, TA profile 1).
- 그런 쌍이 없으면, 예산만으로는 두 요인을 분리할 수 없다고 보고한다.
