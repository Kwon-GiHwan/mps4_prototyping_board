# A6 — 모델 구조 재수집: DWConv 비중과 feature map 크기 (POST_HOC_DESCRIPTIVE)

**2026-09-14.** REPORT §3.1의 `operator type · DWConv 수 · shape: NOT_COLLECTED`를 해소하고
§3.4 가설 4(DWConv/출력 채널 불일치, `NOT_ESTABLISHED`)와 가설 5(작은 feature map,
`CONSISTENT_WITH`)를 사전 등록한 규칙으로 평가한다. 동결 당시 없던 지표이므로
`POST_HOC_DESCRIPTIVE`. 계약: 계획서 §2 + `a6_model_structure.py` docstring, 계약 커밋
`50c61e3`(값 계산 전). 게이트 검사 11개, 돌연변이 3종 RED, digest 복원.

## 재수집

133개 구성의 동결 `vela_args`를 그대로 재실행하고 `--verbose-performance
--verbose-schedule --verbose-weights`만 추가했다 (`vela_verbose/run.py`, 서버 Vela 5.0.0).
**133/133 산출물의 SHA-256이 동결 `vela_sha256`과 일치**했다 (`vela_verbose/results.jsonl`).
verbose 옵션은 산출물을 바꾸지 않으며, 재수집한 구조 정보는 동결 산출물의 것이다.

수집 항목 (`a6_model_structure.csv`, 133행): NPU 연산 수, DepthwiseConv2D 연산 수,
총 MAC, DW MAC 비중, 스케줄 연산 수, ublock 집합. 연산별 OFM shape·블록·ublock은
`vela_verbose/cells/<cell>/vela_stdout.txt`에서 `schedule_ops()`로 읽는다.

## H4 — DWConv 비중과 확장 효율: `NO_ORDER_RELATION`

TA ON 20개 계열. x = 최소 MAC 구성의 DW MAC 비중, y = 계열의 인접 전이 효율 평균.
Spearman rho = **−0.075** (계약 임계 −0.7). `a6_h4_series.csv`.

| 계열 (대표) | DW MAC 비중 | 평균 효율 |
|---|---|---|
| YOLO-Fastest (U55/U65/U85) | 0.21 | 0.88 / 0.75 / 0.73 |
| VWW | 0.10 | 0.80 / 0.74 / 0.64 |
| MobileNetV2 | 0.07 | 0.81 / 0.77 / 0.74 |
| KWS | 0.05 | 0.90 / 0.83 / 0.78 |
| AD | 0.03 | 0.85 / 0.78 / 0.81 |
| RNNoise | 0.00 | 0.51 / 0.65 / 0.46 |
| Wav2Letter (U65/U85) | 0.00 | 0.83 / 0.91 |

효율이 가장 낮은 계열(RNNoise)은 DW가 없고, DW 비중이 가장 큰 YOLO-Fastest는 효율이
높은 쪽이다. 계약 지표로는 "DW 비중이 클수록 확장 효율이 낮다"는 순서가 나타나지 않는다.

보조값(계약 밖, 판정에 쓰지 않음): DW 연산이 MAC은 적고 사이클은 많으므로 Vela 추정
사이클 기준 DW 비중도 계산했다. YOLO 0.27–0.38, MobileNetV2 0.17–0.30, VWW 0.18–0.29,
AD·KWS 0.17–0.20. 이 지표로도 rho = +0.136으로 순서 관계가 없다.

**가설 4 제안 판정**: `NOT_ESTABLISHED` 유지, 근거 열에 "계열 수준 순서 관계 없음(rho −0.075)"을
추가한다. 매니저 검토(2026-09-14)대로 이 결과를 요인 4의 `RULED_OUT`으로 올리지 않는다. 계열
20개는 독립 모델 20개가 아니라 7개 모델 × 3 NPU의 조합이고, 세 NPU의 확장 범위를 하나의 평균
효율로 합쳤으며, MAC 비중은 사이클 비중과 다른 지표다. 연산 단위에서는 H5의 REGRESS/IMPROVE
양쪽에 DW가 같은 비율(≈40%)로 들어가 방향을 가르지 않는다.

**연산 단위 보조 검사 (2026-09-14 추가, 계약 밖 POST_HOC):** U85 256→512 분리 가능 연산(B-frozen)의
512/256 사이클 비를 연산 종류별로 보면 DepthwiseConv2D 47개 중앙값 0.667, Conv2D 63개 0.778 — DW 연산이
일반 Conv보다 덜 빨라지지 않는다(오히려 더 빨라짐). 사이클이 늘어난 비율도 0.36 vs 0.37로 같다. 모델별로는
VWW(DW 1.20 vs Conv 0.75)·AD(1.07 vs 0.57)에서 DW가 불리하고 YOLO(0.66 vs 1.17)에서 유리해 일관된
불이익이 없다. 모델 간(H4)과 연산 단위 모두에서 "DWConv가 확장 이득을 줄인다"는 가설은 지지되지 않는다.
발표에서는 요인 4를 "기각(제한 요인 아님)"으로 쓰되, 모델·층에 따라 방향이 다르다는 관측은 남긴다.

## H5 — 작은 feature map: `SMALL_FM_CONCENTRATED`

U85 256→512, 동결 바인딩(B-frozen)의 분리 가능 연산 124개. 계약 지표의 OFM 크기는 **N×H×W×C
원소 수**(N=1)이며 자료형 바이트나 타일 수가 아니다. 중앙값:

| 방향 | n | OFM 중앙값 |
|---|---|---|
| IMPROVE | 65 | 18,432 |
| REGRESS | 43 | 8,064 |
| SAME | 16 | 5,312 |

REGRESS 중앙값이 IMPROVE의 0.44배로 계약 임계(0.5) 아래다. 사이클이 늘어난 연산은
출력 feature map이 작은 쪽에 몰려 있다.

모델별로 나누면 그림이 갈린다.

| 모델 | IMPROVE n / 중앙값 | REGRESS n / 중앙값 |
|---|---|---|
| YOLO-Fastest | 26 / 27,648 | 21 / 8,064 |
| VWW | 22 / 11,648 | 19 / 12,288 |
| AD | 6 / 70,656 | 2 / 26,784 |
| KWS | 10 / 17,500 | 0 |
| RNNoise | 1 / 24 | 1 / 1 |

합산 결과는 YOLO-Fastest가 만든다. VWW에서는 두 그룹의 크기가 같아(0.95배) 분리되지
않는다.

**매니저 검토(2026-09-14) 반영 — 공간 크기(H×W)와 채널(C)의 분리 (계약 밖 보조표, POST_HOC):**

| 범위 | IMPROVE n / REGRESS n | median H×W | median C | median H×W×C | H×W×C 판정 |
|---|---|---|---|---|---|
| 합산 | 65 / 43 | 256 / 36 | 96 / 136 | 18,432 / 8,064 | SMALL_FM_CONCENTRATED |
| YOLO 제외 | 39 / 22 | 256 / 64 | 96 / 134 | 17,500 / 11,648 | NOT_CONCENTRATED (0.67) |
| YOLO | 26 / 21 | 576 / 36 | 96 / 136 | 27,648 / 8,064 | – |
| VWW | 22 / 19 | 256 / 64 | 36 / 96 | 11,648 / 12,288 | – |
| AD | 6 / 2 | 256 / 136 | 276 / 234 | 70,656 / 26,784 | – |

원소 수(H×W×C)로는 YOLO를 빼면 계약 임계를 넘지 못한다. 그러나 **공간 크기 H×W로 보면 YOLO를
빼도 REGRESS 중앙값 64 vs IMPROVE 256(0.25배)이고, VWW도 64 vs 256으로 갈린다.** REGRESS 연산은
채널은 오히려 많고(136 vs 96) 공간 위치 수가 적다. 즉 원소 수가 아니라 공간 병렬성 부족이 신호이며,
VWW에서 원소 수가 분리되지 않았던 것은 채널 수가 그것을 상쇄했기 때문이다. 계약 지표는 원소 수였으므로
판정은 그대로 두고, H×W 결과는 "요인 5의 정의를 공간 크기로 좁히면 모델 간에 일관된다"는 보조
관측으로 적는다. 다음 계약에서는 H×W를 1차 지표로 등록할 것을 제안한다.

분리 불가 연산이 차지하는 512 MAC 사이클 비중: AD 0.10, KWS 0.03, VWW 0.02, YOLO 0.12, **RNNoise
0.84**. RNNoise는 사이클의 84%가 분리 불가 연산에 있어 연산 단위 H5 표로는 거의 다룰 수 없고,
18장의 그룹 단위 분석이 그 자리를 맡는다. RNNoise는 분리 가능 연산이 3개뿐이라 이 표로는 판단할 수 없고, 18장의 "작은
연산 그룹 10개"는 그룹 단위(분리 불가 연산 포함) 분석이라 이 표와 단위가 다르다.

REGRESS 연산 종류: Conv2D 23, DepthwiseConv2D 17, Pad 2, FC 1. IMPROVE: Conv2D 33,
DepthwiseConv2D 27. DW 연산은 양쪽에 같은 비율(≈40%)로 들어가 있어 방향을 가르지 않는다.
이는 H4의 결과와 같은 방향이다.

**가설 5 제안 판정**: `CONSISTENT_WITH` 유지. 근거가 그룹 단위 관측에서 연산 단위 OFM
크기로 한 단계 구체화됐다. 단, 모델 간 이질성(YOLO 주도, VWW 미분리)을 함께 적는다.

## 한계

- 두 판정 모두 사후 지표다. 결론 문장에는 쓰지 않고 §3.4 표의 근거 열에만 추가한다.
- H4의 "계열 평균 효율"은 계약에서 정한 요약이며, 전이별 효율의 분산을 숨긴다.
- H5의 OFM 크기는 Vela가 스케줄한 연산의 출력 크기이고, 원래 모델 층의 크기와는
  fusion·slicing만큼 다르다.
- U85 256→512 한 전이만 본 것이라 다른 NPU·전이로 일반화하지 않는다.

## 재현

```sh
python3 docs/paper/raw_data_report/amendments/a6_model_structure.py
python3 -m unittest docs.paper.raw_data_report.amendments.test_a6_model_structure
```
