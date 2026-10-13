# RQ 구성과 분석 자료 정리

작성: 2026-09-15  
진행 현황 확인 기준: 저장소 `5491b4c`  
목적: 논문의 질문, 분석 순서, 실험 자료의 역할을 RQ1과 RQ2로 정리한다. 기존 실험 계획과 판정 기준은 유지한다.

## 1. 최종 RQ

### RQ1 — Performance and MAC Scaling

**성능과 MAC 확장 특성**

> How do inference execution cost and MAC-scaling behavior vary across workloads and NPU configurations?
>
> 모델과 NPU 구성에 따라 추론 실행 비용과 MAC scaling은 어떻게 달라지는가?

모델별 실행 비용의 분포를 먼저 제시하고, 같은 모델에서 MAC 구성을 변경했을 때의 비용과 확장 이득을 분석한다.

### RQ2 — Effects of Memory and Execution Conditions

**메모리·실행 조건의 영향**

> How do memory-service conditions and execution configurations affect inference execution cost?
>
> 메모리 서비스 조건과 실행 구성은 추론 실행 비용에 어떤 영향을 주는가?

각 비교에서 MAC을 고정하고 관심 조건을 변경한다. 기본 분석은 실행 비용, 기준 대비 증감률, 조건별 민감도다. 여러 MAC에서 대응하는 비교가 있을 때 MAC별 반응 차이와 scaling 변화를 추가 분석한다.

## 2. 두 RQ의 관계

| 구분 | RQ1 | RQ2 |
|---|---|---|
| 역할 | 성능과 MAC scaling 현상 관측 | 메모리·실행 조건의 영향 분석 |
| 기본 비교 | 모델별 비용 및 동일 모델의 MAC 구성별 비용 | 동일 MAC에서 조건 변경 전후 비용 |
| 주요 변경 변수 | MAC 구성 | Latency, MAXR, BWCAP, 형상, 연산 종류, 데이터 배치 |
| 기본 지표 | NPU cycles, speedup, scaling efficiency | NPU cycles, 비용 증감률, 조건별 민감도 |
| 연결 분석 | 설명할 비용·확장 현상 제시 | 조건 변경 효과가 MAC에 따라 다르면 RQ1과 연결 |

```text
Corstone Family 성능 분석
|
+-- RQ1: 성능과 MAC 확장 특성
|   |
|   +-- 실행 비용의 분포
|   |   +-- 모델별 NPU cycles
|   |   +-- ACTIVE 및 메모리 접근 특성
|   |   `-- 대표 사례의 연산 그룹별 비용
|   |
|   `-- MAC 확장 결과
|       +-- MAC별 실행 비용과 speedup
|       +-- 인접 전이의 scaling efficiency
|       `-- 개선 / 동일 / 증가 구간
|
`-- RQ2: 메모리·실행 조건의 영향
    |
    +-- 기본 분석: 각 비교에서 MAC 고정
    |   |
    |   +-- 지연·동시성
    |   |   `-- Read/write latency, MAXR
    |   +-- 대역폭
    |   |   `-- SRAM BWCAP, EXT BWCAP
    |   +-- 형상·실행 구조
    |   |   `-- H x W, 연산 종류, block, schedule
    |   `-- 데이터 배치
    |       `-- SRAM / 외부 메모리 배치
    |   
    |   결과: cycles / 기준 대비 증감률 / 조건별 민감도
    |
    `-- 확장 분석: 여러 MAC의 대응 비교가 있을 때
        +-- 조건 변경 효과가 MAC별로 다른가?
        `-- 그 차이가 MAC scaling에 어떻게 반영되는가?
            `-- RQ1에서 관측한 현상과 연결
```

## 3. 논문의 설명 순서

```text
실행 비용의 분포                  MAC 확장 결과
모델별 비용과 접근 특성    --->    MAC 증가에 따른 비용 변화
          [ RQ1 ]                         [ RQ1 ]
                                             |
                                             v
                                  메모리·실행 조건의 영향
                                  같은 MAC에서 조건 변경
                                           [ RQ2 ]
                                             |
                                             v
                                  MAC별 반응 차이 분석
                                  대응 비교가 있을 때 추가
                                       [ RQ1과 연결 ]
```

| 본문 | 주요 내용 | 대응 RQ |
|---|---|---|
| Where Does Inference Time Go? | 모델별 실행 비용, ACTIVE·메모리 접근 특성, 대표 그룹 비용 | RQ1 |
| How Does Performance Scale? | 전체 MAC 확장 곡선, speedup, 인접 전이 효율 | RQ1 |
| How Do Memory and Execution Conditions Affect Inference Cost? | 고정 MAC에서 지연·동시성·대역폭·형상·배치 변경 효과 | RQ2 |
| Connection to MAC Scaling | 조건 변경 효과의 MAC별 차이와 확장 결과의 관계 | RQ2의 확장 분석 |

RQ2의 전체 제목은 실행 비용을 중심으로 쓴다. `What Limits Performance Scaling?`은 MAC scaling과 연결하는 분석의 질문으로 사용할 수 있다.

각 분석 주제는 다음 순서로 설명한다.

```text
질문 --> 비교 조건 --> 주요 결과 --> 결과를 설명하는 관측
```

예: “동시 읽기 요청 수가 read-latency 민감도에 영향을 주는가?”라는 질문을 제시하고, 고정 MAC과 변경 MAXR을 표시한 뒤 cycles·민감도 곡선으로 답한다. H1-B 같은 내부 실험명과 판정 코드는 출처 및 방법 설명에 둔다.

## 4. RQ2의 기본 분석과 확장 분석

### 4.1 MAC 고정의 의미

MAC 한 종류에서만 실험한다는 뜻이 아니다. 각 조건 변경 비교 안에서 MAC을 고정한다.

```text
                    조건 변경 전         조건 변경 후
                    ------------         ------------
256 MAC 고정        C(256, base)  ------> C(256, changed)
                                  비용 변화 계산

512 MAC 고정        C(512, base)  ------> C(512, changed)
                                  비용 변화 계산

기본 분석: 각 행에서 조건 변경 효과 계산
확장 분석: 두 행의 효과를 비교하고 MAC scaling과 연결
```

### 4.2 기본 지표

- 실행 비용: 해당 비교의 NPU cycles.
- 비용 증감률: `(C_changed - C_base) / C_base x 100`.
- 음수는 비용 감소, 양수는 비용 증가를 뜻한다.
- 조건별 민감도: 변경한 파라미터의 단위 변화에 대한 cycles 변화. 예를 들어 latency 민감도는 `Delta cycles / Delta configured latency`로 표시한다. 비교 구간과 고정 조건을 함께 기록한다.

메모리 서비스 조건 비교는 같은 MAC과 Vela 산출물을 유지하고 TA 조건을 변경한다. 실행 구성 비교는 같은 MAC에서 형상·연산 종류·데이터 배치 등을 변경하며, 이에 따른 컴파일 결과와 실행 비용을 함께 수집한다.

### 4.3 비용 개선과 MAC scaling 개선은 별개

다음은 설명을 위한 가상 값이다.

| MAC | 기본 조건 cycles | 변경 조건 cycles | 비용 증감률 |
|---|---:|---:|---:|
| 256 | 100 | 80 | -20% |
| 512 | 50 | 40 | -20% |

```text
조건 변경 효과: 256 MAC에서 -20%, 512 MAC에서도 -20%

기본 조건 MAC speedup: 100 / 50 = 2.0
변경 조건 MAC speedup:  80 / 40 = 2.0

=> 실행 비용은 감소했다.
=> MAC scaling은 그대로다.
=> RQ2의 의미 있는 결과이며, scaling 변화가 필수는 아니다.
```

두 MAC에서 비용 감소율이 다르면 조건 변경 전후의 MAC speedup과 scaling efficiency를 비교한다.

## 5. RQ2의 분석 주제와 현재 자료

| 주제 | 기본 질문 | 주요 자료 | 결과에서 강조할 내용 |
|---|---|---|---|
| 지연·동시성 | Read/write latency와 MAXR에 비용이 어떻게 반응하는가? | X4, H13 H1-A/B/C, latency 0/0 대조 | 읽기·쓰기 영향의 차이, MAXR에 따른 latency 민감도 |
| 대역폭 | SRAM·EXT BWCAP 변경이 비용에 어떤 영향을 주는가? | A5, H13 SRAM cap·H2-A | 상한을 낮췄을 때의 비용 증가와 완화했을 때의 이득 |
| 형상·실행 구조 | 같은 MAC에서 형상과 연산 종류에 따라 비용이 어떻게 달라지는가? | A6, H3, H3-R, Vela block·schedule 자료 | 형상별 비용 차이와 메모리 조건에 따른 변화 |
| 데이터 배치 | 데이터의 SRAM·외부 메모리 배치가 비용을 어떻게 바꾸는가? | H2-B-X, 배치·스케줄 자료 | 배치 구성별 cycles와 메모리 접근 변화 |

현재 결과에서 본문으로 연결할 수 있는 예:

- SRAM BWCAP을 절반으로 낮췄을 때 평가한 4개 구성의 cycles는 약 35–64% 증가했다. 기본값을 완화했을 때는 약 0.8–5.3% 감소했다.
- RNNoise의 read-latency 반응은 write-latency 반응보다 컸으며, MAXR 변경에 따라 read-latency 민감도가 달라졌다.
- Wav2Letter의 외부 BWCAP 변경과 대표 레이어의 데이터 배치 변경은 서로 다른 비교다. 각각 전체 모델과 대표 레이어 결과로 제시한다.
- H3의 형상·연산 자료는 고정 MAC 비용 비교와 MAC 전이 비교 양쪽에 사용할 수 있다. 기존 사전 판정은 유지하고, RQ2의 고정 MAC 비교를 별도로 정리한다.

진행 현황은 작성 시점의 로컬 기록 기준이다. H13 S1–S5는 완료되어 결과와 전달 자료 생성 코드가 있다. H3-R은 비형상 INT8 요소와 적용 TA 조건을 맞추는 보강 실험으로, 확인 기준 커밋에서는 모델·조건 생성 및 검증까지 완료됐으며 측정 결과는 아직 기록되지 않았다.

초기의 가설 7종 표는 실험의 배경과 결과 대응을 설명하는 자료로 유지한다. 본문 순서는 가설의 과거 상태보다 위 네 가지 분석 주제를 따른다.

## 6. 보강 분석의 위치

```text
주 분석                                  보강 자료
-------                                  ---------
RQ1 실행 비용·MAC scaling  <------------  플랫폼 비교, Vela 추정 비교
RQ1 대표 사례의 비용 분포  <------------  연산 그룹 프로파일
RQ2 형상·실행 구조         <------------  Vela block·ublock·schedule
RQ2 데이터 배치            <------------  텐서 배치·인코딩·메모리 카운터
관련 결과의 검증            <------------  FPGA 비교 자료
```

Vela 추정·플랫폼·FPGA 비교는 관련 결과를 보강하는 위치에 배치한다. 연산 그룹 자료는 해당 계측 경로의 비용 분포로 표시한다. 자료별 측정 경로와 비교 조건은 방법·그림 설명·근거표에서 확인할 수 있게 한다.

## 7. 자료 정리: 실행표 → 비교표 → 결과–근거 대응표

```text
원시 실행
results.jsonl / UART / 모델·산출물 / 적용 설정
    |
    v
[1] 실행표                 한 행 = 하나의 실행
    |
    | baseline / changed 실행 묶음 연결
    v
[2] 비교표                 한 행 = 하나의 비교
    |
    +------------------> 그림·표
    |                       |
    v                       v
[3] 결과–근거 대응표        한 행 = 하나의 핵심 결과
    |
    v
논문의 결과 문장
```

### 7.1 실행표

측정값과 실행 정보를 정리한다.

```text
run_id
experiment_id
platform / npu / mac / model
memory_profile / execution_config
requested_settings / applied_settings
repeat
total_cycles / active_cycles / memory_counters
status
artifact_id / raw_log_path
```

요청 설정과 실제 적용 설정을 함께 기록한다. 현재 MAXR 자료처럼 두 값이 다른 경우도 이 표에서 확인할 수 있게 한다.

### 7.2 비교표

```text
comparison_id
rq / analysis_topic / comparison_type
baseline_run_ids / comparison_run_ids
changed_variables / fixed_conditions
metric_name
baseline_cost / comparison_cost
cost_change_pct
condition_sensitivity
mac_speedup / scaling_efficiency
transition_direction
```

| 비교 유형 | 주로 계산하는 값 |
|---|---|
| RQ1 모델별 비용 | cycles, 구성 내 정규화 비용 |
| RQ1 MAC 전이 | MAC speedup, scaling efficiency, 전이 방향 |
| RQ2 고정 MAC 조건 변경 | cycles, 비용 증감률, 조건별 민감도 |
| RQ2 확장 분석 | MAC별 조건 변경 효과, 조건별 MAC speedup·효율 |

해당 비교에 필요한 지표만 계산한다. RQ2 기본 비교에 MAC scaling 지표를 필수로 요구하지 않는다. TOTAL과 ACTIVE는 지표명을 명시해 각각 연결한다.

### 7.3 결과–근거 대응표

| 항목 | 내용 |
|---|---|
| 소속 RQ | RQ1 또는 RQ2 |
| 분석 주제 | 비용 분포, MAC scaling, 지연·동시성, 대역폭, 형상·실행 구조, 배치 |
| 핵심 결과 | 본문에 넣을 결과 문장 |
| 비교 근거 | comparison ID, experiment ID |
| 그림·표 | 본문 또는 부록 위치 |
| 분석 메모 | 결과를 설명하는 관측과 해석 |

사전 판정·탐색·사후 분석 구분은 기존 실험 메타데이터에서 유지한다. 발표와 논문 본문에서는 질문과 주요 결과를 먼저 제시하고 근거를 연결한다.

## 8. 자료 준비 순서

1. **RQ1 전체 결과를 먼저 정리한다.** 모델별 비용 분포, MAC 확장 곡선, 인접 전이 지표를 만든다. 대표 사례에는 연산 그룹 자료를 연결한다.
2. **RQ2를 고정 MAC 비교로 정리한다.** 기준 조건, 변경 변수, cycles, 증감률, 민감도를 지연·동시성 → 대역폭 → 형상·실행 구조 → 배치 순서로 묶는다.
3. **대응하는 여러 MAC 비교에서 확장 분석을 수행한다.** 조건 변경 효과의 MAC별 차이를 계산하고 RQ1의 확장 결과와 연결한다.
4. **핵심 결과와 근거를 연결한다.** 비교표에서 그림·표를 생성하고, 결과 문장에서 원시 실행까지 추적할 수 있도록 정리한다. 대표 사례 외 전체 결과는 부록·전체 결과표에 둔다.

## 9. 근거 문서

이 문서의 RQ 명칭과 구성은 사용자가 확정한 방향을 반영한다. 아래 문서는 기존 측정 및 진행 상태를 확인한 자료다.

- [논문 원고](../MANUSCRIPT.md)
- [감사 보고서](../raw_data_report/REPORT.md)
- [추가 분석·캠페인 목록](../raw_data_report/amendments/README.md)
- [A5 대역폭 분석](../raw_data_report/amendments/A5_effective_bandwidth.md)
- [A6 모델 구조 분석](../raw_data_report/amendments/A6_model_structure.md)
- [X4 TA 조건 변경 결과](../raw_data_report/amendments/A8_x4_timing_adapter_sweep.md)
- [H13 결과](../raw_data_report/amendments/h13/H13_RESULTS.md)
- [H13 전달 자료 생성 코드](../raw_data_report/amendments/h13/make_handoff.py)
- [H3-R 보강 실험 계획](../../superpowers/plans/2026-09-15-h3r-verification-GO.md)
