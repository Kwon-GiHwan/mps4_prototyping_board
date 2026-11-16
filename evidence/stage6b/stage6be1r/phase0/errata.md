# Stage 6B-E1 기록 정합성 감사와 errata (E1-R Phase 0)

- 근거: "Stage 6B-E1-R 공식 지시" §1.
- 대상: E1 결과 커밋 `5537c11`. 계약 `d39448c`, 동결 `3a83175`, Preflight `2c667b1`.
- **기존 파일은 하나도 고치지 않았다.** 이 문서와 `audit.py`·`audit.json`만 새로 썼다.
- 감사 스크립트 `audit.py`는 `host/analysis/stage6be1.py`를 import하지 않는다. 다음 자료에서 매핑을 다시 계산한다.
  - 원시 `runs.csv`
  - 보드 plan 파일
  - DRWL 파일 sha256
  - `predictions.json`, `stage6bb_manifest.json`, `stage6be1_summary.json`
- 측정 조건(원시 자료): TA profile 1, 이미지 `70090f1`, boot 421–427.

## 질문별 결과

| # | 질문 | 결과 | 근거 |
| --- | --- | --- | --- |
| 1 | 신규 형상은 정확히 6개인가 | **예** | `predictions.json` 6개. 이름 6개, DRWL sha256 6개, (Cin, H, W, Cout) 6개 모두 서로 다르다 |
| 2 | 보고서에 같은 형상이 중복 기재되었나 | **아니오(저장소 기록 기준)** | 아래 "7행·Cin136 두 번"의 원인 |
| 3 | 같은 Cin/Cout/공간인데 ublock·구성만 다른 형상이 있나 | **없다** | 6개는 (Cin, H, W, Cout)부터 다르다. 실행 구성 (커널 분할, ublock, OFM block)은 4종이다. Cin72/Cin80 13×13 o96은 `8x14x64`·16+80·2x2x32를, Cin136/Cin200 13×13 o96은 `6x14x96`·16+80·2x2x32를 공유한다. 짝 안에서는 Cin(Cin 조각)만 다르다 |
| 4 | 7 boot가 기준 1개 + 신규 6개에 정확히 대응하나 | **예** | plan b01–b07, manifest의 boot, 원시 `host_boot_index`가 모두 같다: 421 기준, 422–427 신규. 원시 `workload_sha256` = DRWL 파일 sha256 = manifest = predictions. 원시 `model_sha256` = 예측의 Vela 출력 sha256 |
| 5 | 사전 예측과 측정의 매핑이 정확한가 | **예** | 형상마다 예측 H1-UC = 원시 MAC_ACTIVE(측정 RUN 4회, 값 1개) = summary의 measured/predicted |
| 6 | MAC 6/6 일치와 경쟁 가설 비교가 원시 자료에서 재현되나 | **예** | 6/6 일치. 4개는 경쟁 가설 8개 중 어느 것과도 같지 않다. Cin72 7×7 o48은 H1-G·"전체 Cout"이 함께 일치한다. Cin72 7×7 o112는 "전체 Cout"이 함께 일치한다 |

해결되지 않은 형상-예측-측정 불일치는 **없다**. 따라서 E1-R로 진행한다.

## "7행, Cin136 13×13 Cout96 두 번"의 원인

ChatGPT에 전달된 표 원문은 저장소에 없다. 저장소 기록으로 확인한 사실은 다음과 같다.

1. **7행**: E1 README의 측정 결과 표는 신규 6행에 **기준 형상 1행**("기준 Cin48", boot 421, VALID)을 더해 7행이다. 신규 형상은 6개다.
2. **Cin136 두 번**: E1 README에는 형상 표가 두 개 있다. 하나는 선정·예측 표(boot 423, "Cin136 13×13 Cout96")이고, 다른 하나는 측정 결과 표("Cin136 13×13 o96")다. 각 표에 한 번씩 나온다. 두 표를 합치거나 옮기면 같은 형상이 두 번 보인다.
   - 측정 결과 표 안에는 중복이 없다(`audit.json`의 `readme_measured_table_rows`).
   - 터미널 최종 보고의 결과 표(6행)에도 중복이 없다.
3. 기준 행이 형상 열 대신 "기준 Cin48"로만 표시되어 신규 행과 구별이 약했던 점은 보고 형식의 결함이다. E1-R 보고서는 기준 행을 별도 표로 분리한다.

## Errata

| 위치 | 기록 | 정정 |
| --- | --- | --- |
| 커밋 `3a83175` 메시지 | "19 tests" | `host/tests/test_stage6be1.py`의 테스트는 **18개**다(`audit.json`의 `n_tests_test_stage6be1`). 보고서의 18개가 맞다. 커밋 메시지는 고치지 않는다 |
| `results/fi101_stage6b/stage6bb/README.md` | Spearman 0.30 | 0.32다. 6B-R README에서 이미 정정했다. 다시 적는다 |
| E1 README 측정 결과 표 | 기준 행이 신규 행과 같은 표에 있다 | 기준 형상은 신규 6개에 속하지 않는다(위 1) |

**기존 E1 판정 `INSUFFICIENT_EVIDENCE`(Primary Valid 0/6)는 바뀌지 않는다.**

## 감사 스크립트 검증

`audit.py`가 실제로 불일치를 잡는지 확인했다. 기존 자료의 임시 복사본을 하나씩 변조하고 실행했으며, 원본은 건드리지 않았다.

| 변조 | 결과 |
| --- | --- |
| 없음(기준) | issues 0 |
| M1 plan의 boot 번호 변경 | 검출 |
| M2 원시 `host_boot_index` 변경 | 검출 |
| M3 DRWL 파일 교체 | 검출 |
| M4 H1-UC 예측값 변경 | 검출 |
| M5 측정 RUN 하나의 MAC_ACTIVE 변경 | 검출 |
| M6 summary의 measured_mac 변경 | 검출 |

6/6 검출. 재현: `python3 evidence/stage6b/stage6be1r/phase0/audit.py . evidence/stage6b/stage6be1r/phase0/audit.json`
