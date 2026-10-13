# Arm Ethos-U NPU의 MAC 확장에 따른 성능 특성 분석

## 1. 실험 목적과 워크로드

본 실험의 목적은 Arm Ethos-U NPU에서 **MAC(Multiply-Accumulate) 연산 유닛의 수를 증가시켰을 때 실제 추론 성능이 얼마나 향상되는지**를 분석하는 것이다.

이론적으로는 MAC 수가 증가하면 동시에 처리할 수 있는 연산량도 증가하므로 성능 역시 향상될 것으로 기대할 수 있다. 그러나 실제 NPU의 성능은 연산 유닛의 수뿐 아니라 메모리 접근, 데이터 이동, 연산의 병렬화 가능성, 컴파일러의 연산 배치 방식 등 여러 요소의 영향을 받는다.

따라서 본 실험에서는 다양한 구조적 특성을 가진 TinyML 모델을 대상으로 여러 Ethos-U 구성에서 MAC 수를 변화시키며 실행 사이클을 측정한다.

평가 대상은 다음 7개 INT8 모델이다.


| 모델                | 태스크                  | 주요 특성                                       |
| ----------------- | -------------------- | ------------------------------------------- |
| RNNoise           | Noise Reduction      | 연산량이 작고 FC/GRU 계열 연산 비중이 큼                  |
| MicroNet KWS      | Keyword Spotting     | 비교적 작은 CNN                                  |
| AD Medium         | Anomaly Detection    | Conv2D 기반 CNN                               |
| Visual Wake Words | Image Classification | MobileNet 계열, Depthwise Convolution 비중이 높음  |
| YOLO-Fastest      | Object Detection     | 여러 해상도의 feature map을 사용하는 CNN               |
| MobileNetV2       | Image Classification | Conv2D와 Depthwise Convolution이 혼합된 비교적 큰 모델 |
| Wav2Letter        | Speech Recognition   | 연산량과 weight 크기가 매우 큰 모델                     |


모델별 계산량 차이가 매우 크기 때문에, 단순한 절대 실행시간 비교보다는 **각 모델이 MAC 증가에 따라 어떻게 scaling되는지**를 중심으로 분석한다.

---

## 2. 평가 환경

실험은 Arm의 Corstone 기반 Fixed Virtual Platform(FVP)과 실제 FPGA 플랫폼을 이용한다.

사용한 주요 NPU 구성은 다음과 같다.


| NPU       | 플랫폼                  | MAC 구성                    |
| --------- | -------------------- | ------------------------- |
| Ethos-U55 | Corstone-300/310     | 32, 64, 128, 256          |
| Ethos-U65 | Corstone-300/310/315 | 256, 512                  |
| Ethos-U85 | Corstone-320         | 128, 256, 512, 1024, 2048 |


Ethos-U 세대마다 Corstone subsystem, memory controller 및 FVP 구현이 다르기 때문에 **서로 다른 세대의 절대 cycle 수를 직접 비교하지 않는다.**

대신 동일한 플랫폼 내부에서 MAC 수를 증가시켰을 때 나타나는 speedup과 scaling efficiency를 분석한다.

실제 하드웨어 검증에는 MPS4 기반 Corstone-320 / Ethos-U85 FPGA 플랫폼을 사용하며, 해당 보드는 U85 1024-MAC 구성으로 고정되어 있다.

따라서 보드 실험은 MAC scaling 자체를 검증하는 용도가 아니라, **FVP에서 관찰된 workload별 상대적인 성능 특성과 실제 하드웨어에서의 경향이 일관적인지 확인하는 보조 실험**으로 사용한다.

---

## 3. 측정 과정

전체 실험 과정은 다음과 같다.

```text
TFLite INT8 model
      ↓
Arm Vela compiler
      ↓
Ethos-U command stream 생성
      ↓
MLEK inference runner 빌드
      ↓
FVP 또는 FPGA 실행
      ↓
PMU counter 수집

```

Vela는 TFLite 모델을 Ethos-U에서 실행할 수 있는 command stream으로 변환하며, 동시에 예상 실행 cycle과 메모리 사용량 등의 정보를 제공한다.

FVP 및 실제 보드에서는 Ethos-U의 PMU(Performance Monitoring Unit)를 이용하여 실행 중 발생한 cycle과 memory traffic 정보를 수집한다.

컴파일러의 예측값과 실제 실행에서 얻은 측정값은 서로 성격이 다르므로 별도의 지표로 구분한다.

---

## 4. 주요 측정 지표

### 4.1 Vela 성능 추정값

Vela compiler에서는 다음과 같은 성능 관련 정보를 얻는다.

- 전체 예상 cycle
- NPU 연산 예상 cycle
- SRAM 접근 예상 cost
- 외부 메모리 접근 예상 cost
- SRAM 및 외부 메모리 사용량
- encoded weight 크기

이 값들은 **실제 하드웨어에서 측정된 값이 아니라 compiler cost model의 예측값**이다.

따라서 실제 FVP 또는 FPGA cycle과 동일한 물리량으로 취급하지 않고, 주로 configuration 간 예상 성능 변화와 compiler prediction의 경향을 분석하는 데 사용한다.

---

### 4.2 FVP PMU 측정값

FVP에서는 NPU PMU를 이용해 다음 값을 측정한다.

- Total cycle
- Active cycle
- Idle cycle
- 메모리 read/write transaction 수

세대에 따라 memory-interface counter의 이름과 의미가 다르다.

U55/U65에서는 주로 AXI0/AXI1 traffic을 측정하고, U85에서는 SRAM 및 external-memory traffic을 구분한다.

본 연구에서는 전체 추론 실행 비용을 나타내는 **NPU Total cycle을 MAC scaling 분석의 기본 지표**로 사용한다.

---

### 4.3 실제 FPGA 측정값

Corstone-320 FPGA에서도 동일한 Ethos-U PMU 인터페이스를 이용해 Total/Active/Idle cycle과 SRAM 및 external-memory traffic을 확인한다.

다만 FPGA에서 측정되는 cycle과 FVP의 simulated cycle은 동일한 timing model에서 만들어진 값이 아니다.

따라서 FVP와 실제 보드 사이에서는 절대 cycle 오차를 계산하지 않고,

- workload 성능 순위
- 상대적 execution cost
- 반복 실행의 안정성
- 전체적인 성능 경향

등을 중심으로 비교한다.

---

## 5. MAC Scaling 지표

MAC 증가에 따른 성능 향상을 평가하기 위해 다음 지표를 사용한다.

### Speedup

기준 MAC 구성과 비교하여 실행 cycle이 얼마나 감소했는지를 나타낸다.

Speedup(Mi)=Cycle(M0)Cycle(Mi)Speedup(M_i)=\frac{Cycle(M_0)}{Cycle(M_i)}

예를 들어 MAC이 2배 증가했을 때 cycle이 절반으로 감소하면 speedup은 2배이다.

### Cumulative Scaling Efficiency

실제 speedup을 이론적으로 가능한 MAC 증가 배수와 비교한다.

Efficiency=SpeedupMAC increase ratioEfficiency=\frac{Speedup}{MAC\ increase\ ratio}

예를 들어 MAC을 4배 늘렸는데 실제 성능이 2배 향상되었다면 scaling efficiency는 50%이다.

### Incremental Scaling Efficiency

연속된 두 MAC 구성 사이에서 추가된 MAC이 얼마나 효과적으로 사용되었는지를 나타낸다.

이 지표를 이용하면 특정 MAC 규모부터 성능 향상이 둔화되거나 정체되는 지점을 찾을 수 있다.

---

## 6. FVP에서 관찰된 MAC Scaling 특성

전체 FVP 실험에서 대부분의 MAC 증가 구간에서는 성능이 향상되었지만, **향상 폭은 workload와 MAC 규모에 따라 크게 달랐다.**

전체 53개의 인접 MAC scaling 구간 중

- 높은 scaling efficiency를 보인 구간: 28개
- 중간 수준의 scaling을 보인 구간: 23개
- 낮은 scaling 또는 saturation이 나타난 구간: 2개

로 나타났다.

즉 대부분의 workload에서는 MAC 증가가 성능 향상으로 이어지지만, 추가 MAC이 항상 이론적인 비율만큼 성능을 증가시키지는 않는다.

특히 MAC 규모가 커질수록 workload 구조에 따라 scaling efficiency 차이가 커지는 경향을 확인할 수 있었다.

---

## 7. U85에서 관찰된 비정상적 Scaling

가장 주목할 만한 결과는 Ethos-U85에서 관찰된 RNNoise의 256→512 MAC 구간이다.


| MAC  | NPU Total Cycle |
| ----: | ---------------: |
| 256  | 36,086          |
| 512  | 55,086          |
| 1024 | 49,086          |


MAC을 256에서 512로 두 배 증가시켰음에도 실행 cycle이 감소하지 않고 오히려 증가했다.

반면 KWS, AD, VWW, YOLO, MobileNetV2 및 Wav2Letter에서는 같은 구간에서 실행 cycle이 감소했다.

따라서 이 현상은 단순히 “U85-512가 느리다”는 플랫폼 전체의 특성이라기보다 **특정 workload의 연산 구조와 MAC configuration 사이의 상호작용에 의해 발생하는 현상일 가능성**이 있다.

기존 Ethos-U 분석에서도 MAC scaling은 단순히 연산량만으로 결정되지 않고, memory service와 workload가 제공할 수 있는 병렬성에 영향을 받을 수 있다고 설명된다.

특히 Ethos-U의 MAC array는 output-channel 방향의 병렬 연산을 활용하기 때문에, 작은 spatial dimension 또는 낮은 연산량을 가진 workload에서는 MAC array가 커지더라도 추가 연산 유닛을 충분히 활용하지 못할 가능성이 있다.

또한 U85에서는 MAC configuration이 변경될 때 내부 output-block(ublock)의 구조도 변경될 수 있기 때문에, 특정 tensor shape에서는 block 크기와 workload 구조 사이의 mismatch가 추가적인 비효율을 만들 가능성도 존재한다.

다만 현재 실험에서는 이러한 원인을 직접 입증할 수 있는 operator-level stall 또는 utilization 정보가 충분하지 않으므로, **ublock 변화나 memory-system 특성이 직접적인 원인이라고 단정하지 않는다.**

현재 단계에서 확실하게 말할 수 있는 것은 다음과 같다.

> U85의 특정 workload에서는 MAC 수 증가가 항상 실행 cycle 감소로 이어지지 않으며, RNNoise의 256→512 구간에서 명확한 non-monotonic scaling이 관찰되었다.

---

## 8. Memory System과 Scaling의 관계

MAC을 증가시키면 NPU의 이론적인 연산 처리 능력은 증가하지만, 메모리 시스템의 처리 능력이 같은 비율로 증가하는 것은 아니다.

따라서 MAC 규모가 커질수록 다음과 같은 상황이 발생할 수 있다.

```text
MAC 처리 능력 증가
        ↓
연산 자체는 더 빠르게 처리 가능
        ↓
메모리에서 데이터를 공급하는 시간이 상대적으로 중요해짐
        ↓
추가 MAC의 성능 기여 감소

```

Vela의 성능 모델에서도 여러 workload에서 MAC 증가에 따라 전체 예상 cost 중 DRAM 접근 관련 비용의 비중이 증가하는 경향이 나타난다.

예를 들어 KWS와 AD에서는 U85의 MAC 규모가 증가하면서 Vela가 예측하는 external-memory 관련 cost 비중이 크게 증가한다.

이는 MAC을 확장했을 때 **compute 성능보다 data movement가 상대적으로 중요한 요소가 될 가능성**과 일치한다.

하지만 이 결과는 어디까지나 compiler model의 예측이며, 실제 runtime memory stall을 직접 측정한 것은 아니다.

따라서 현재 결과는

> “성능 scaling이 memory-system의 영향을 받는 정황이 존재한다.”

정도로 해석하는 것이 적절하며,

> “해당 workload가 memory-bound이기 때문에 scaling이 제한된다.”

라고 직접 결론 내리기에는 아직 근거가 부족하다.

---

## 9. Active Cycle의 해석

U85 FVP 실험에서는 대부분의 workload에서

Active/Total≥0.98Active / Total \geq 0.98

수준으로 나타났다.

이는 NPU가 실행 시간 대부분 동안 active 상태였음을 의미한다.

그러나 **Active 상태와 compute-bound 상태는 동일한 의미가 아니다.**

NPU가 active 상태더라도 내부에서는

- 연산 수행
- 데이터 이동
- 메모리 응답 대기
- pipeline 내부 dependency 대기

등이 발생할 수 있다.

따라서 높은 Active 비율만으로 “MAC이 계속 계산을 수행하고 있었다”거나 “compute-bound workload이다”라고 판단할 수 없다.

병목을 구체적으로 규명하려면 더 세분화된 operator-level counter가 필요하다.

---

## 10. Vela 예측과 FVP 관측 비교

Vela의 성능 추정은 전체적인 configuration 선택과 workload ranking에서는 비교적 높은 일관성을 보였다.

대부분의 MAC scaling ladder에서 Vela가 예상한 성능 방향과 FVP에서 관찰된 방향이 일치했다.

그러나 모든 configuration transition을 정확히 예측하지는 못했다.

대표적으로 U85 RNNoise의 256→512 구간에서는 FVP에서 실행 cycle이 증가했지만, Vela는 이러한 성능 역전을 정확히 예측하지 못했다.

이는 compiler cost model이 전체적인 성능 경향을 추정하는 데는 유용하지만, 특정 hardware configuration boundary에서 발생하는 세부적인 runtime behavior까지 항상 표현하지는 못한다는 것을 보여준다.

따라서 Vela는 후보 configuration을 빠르게 비교하는 데 사용할 수 있지만, 최종 configuration 선택에는 FVP 또는 실제 하드웨어를 통한 검증이 필요하다.

---

## 11. 실제 FPGA 검증

Corstone-320 / Ethos-U85 1024-MAC FPGA 환경에서 동일한 7개 workload를 실행하였다.

FVP와 실제 FPGA의 절대 cycle 값은 직접 비교하지 않았지만, workload별 상대적인 성능 순위는 완전히 동일하게 나타났다.

7개 workload에 대해 FVP와 FPGA의 workload ranking은

Spearman ρ=1.0Spearman\ \rho = 1.0

이었으며 순위 inversion은 발생하지 않았다.

이는 FVP의 cycle 값을 실제 하드웨어 cycle과 동일시할 수 있다는 의미는 아니다.

다만 **어떤 workload가 상대적으로 실행 비용이 높은지에 대한 workload-level ordering이 실제 FPGA에서도 유지되었음**을 보여준다.

---

## 12. 현재 실험으로 판단할 수 있는 것과 없는 것

### 현재 데이터로 확인할 수 있는 것

본 실험에서는 다음 결과를 직접 관찰하였다.

1. MAC 수 증가가 항상 이론적인 비율의 성능 향상으로 이어지지는 않는다.
2. Scaling efficiency는 workload 구조에 따라 크게 달라진다.
3. U85 RNNoise의 256→512 구간에서는 MAC 증가에도 실행 cycle이 증가하는 non-monotonic scaling이 발생한다.
4. Vela는 전체적인 성능 경향과 configuration ranking에는 유용하지만 일부 configuration transition을 정확히 예측하지 못한다.
5. FVP와 실제 U85 FPGA에서 workload별 상대적인 성능 순위는 일관되게 나타났다.

### 현재 데이터만으로 확정할 수 없는 것

현재 whole-model FVP 실험만으로는 다음을 직접 확정할 수 없다.

- 특정 workload가 compute-bound인지 memory-bound인지
- 특정 layer에서 어떤 hardware resource가 bottleneck인지
- RNNoise 256→512 역전의 직접적인 원인이 ublock 변화인지
- memory bandwidth 또는 latency가 scaling saturation의 직접 원인인지
- 개별 MAC processing element의 실제 utilization이 얼마인지

이러한 분석에는 layer/operator 수준의 측정이 필요하다.

---

## 13. Operator-Level Mechanism Analysis

Whole-model cycle만으로는 특정 MAC configuration에서 성능이 변하는 원인을 분리하기 어렵다.

따라서 후속 분석에서는 U85 256-MAC과 512-MAC을 중심으로 **연산 단위의 실행 특성**을 비교한다.

분석 대상 정보는 다음과 같다.

- operator별 cycle
- Active cycle
- SRAM read/write traffic
- external-memory read/write traffic
- tensor shape
- operator type
- Vela block/ublock configuration
- tile 및 stripe configuration

각 operator를 동일한 identity로 연결하면 다음과 같은 질문을 분석할 수 있다.

- 어느 연산에서 256→512 성능이 악화되는가?
- 성능 악화와 memory traffic 변화가 함께 나타나는가?
- 작은 feature map이나 tensor shape에서 문제가 집중되는가?
- ublock 또는 tiling strategy 변화와 실행 cost 증가가 같은 configuration boundary에서 발생하는가?

이 분석을 통해 현재 whole-model 수준에서 관찰된 non-monotonic scaling의 원인을 보다 구체적으로 설명할 수 있다.

---

## 14. 요약

본 연구는 Arm Ethos-U55, U65, U85에서 다양한 TinyML workload의 MAC scaling 특성을 분석한다.

실험 결과, 대부분의 configuration에서 MAC 증가에 따라 성능이 향상되었지만 그 효율은 workload에 따라 크게 달랐다. 특히 U85의 RNNoise에서는 MAC을 256에서 512로 증가시켰을 때 오히려 실행 cycle이 증가하는 non-monotonic scaling이 관찰되었다.

이 결과는 **MAC 수 자체만으로 실제 NPU 성능을 예측하기 어렵다는 것**을 보여준다.

NPU의 실제 성능은 연산량뿐 아니라 workload가 제공할 수 있는 병렬성, tensor shape, memory-system behavior, compiler가 생성하는 tiling 및 scheduling 등의 영향을 함께 받는다.

현재 whole-model 측정에서는 이러한 요소 중 어느 하나를 직접적인 병목 원인으로 확정할 수 없으므로, memory-system 및 workload structure와의 연관성 수준으로 해석한다.

후속 operator-level 분석에서는 U85의 256→512 configuration transition을 중심으로 실행 cycle, memory traffic 및 compiler scheduling 정보를 함께 분석하여 non-monotonic scaling의 mechanism을 규명한다.