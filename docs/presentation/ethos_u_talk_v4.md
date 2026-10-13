# 1. Ethos-U Architecture Overview

### 목적

Ethos-U 기반 시스템이 CPU, Memory, NPU로 어떻게 구성되고 각각 어떤 역할을 담당하는지 설명한다.

### 포함할 내용

- Ethos-U 계열의 간단한 위치
  - U55 / U65 / U85
  - 지원 MAC configuration
  - 최대 연산 성능 수준
- 발표의 주 대상은 **Corstone-320 + Ethos-U85**
- CPU / Memory / NPU 역할
  - CPU: TFLite Micro runtime 및 Ethos-U driver 실행
  - NPU: 양자화된 neural-network operator 실행
  - Memory: activation, weights 및 intermediate data 저장
- Ethos-U의 주요 데이터 형식
  - INT8 activation / weight 중심
  - 내부적으로 더 높은 precision의 accumulator 사용
- 대표 적용 분야
  - Vision
  - Audio / Speech
  - TinyML / Embedded AI
  - Edge inference

### 발표에서 제외

- 지원 CPU 모델 전체 목록
- 지원 OS 전체 목록
- 내부 SRAM의 세부 KB 범위
- 시장별 사용 사례 전체 나열
- Corestone security subsystem 상세

→ **1~2장**

---

# 2. Corstone-320 / Ethos-U85 Detailed Architecture

### 목적

이후의 memory configuration과 MAC scaling 결과를 이해하기 위한 하드웨어 구조를 설명한다.

### 포함할 내용

#### Corstone-320

- Cortex-M85
- Ethos-U85
- On-chip SRAM
- External memory
- Interconnect

간단한 block diagram으로 표현한다.

#### Memory Interface

- SRAM-side AXI interface
- External-memory-side AXI interface
- MAC configuration 증가에 따라 사용 가능한 memory port 수도 증가

예:

- 128 / 256 / 512 MAC
- 1024 MAC
- 2048 MAC

정도로만 단계적으로 보여준다.

#### Ethos-U85 내부 구조

핵심 블록만 표시:

- Central Control
- DMA
- Weight Decoder
- MAC / Compute Unit
- Activation Unit
- Input / Output Buffer

설명 포인트:

> NPU는 command stream에 따라 연산과 DMA transfer를 수행하며, compute resource뿐 아니라 memory access 구조가 전체 execution characteristics에 영향을 준다.

### 부록으로 이동

- DMA channel 세부 종류
- SWD/FWD decoder 상세
- NHWC/NHCWB16
- opcode bit field
- command 개수
- 모든 PMU port event

→ **2장**

---

# 3. Arm Simulation Environment and Measurement Interface

### 목적

실제 보드뿐 아니라 Arm이 제공하는 simulator를 이용해 hardware configuration을 변경하며 측정할 수 있음을 설명한다.

### Simulator

- Arm Fast Models / FVP
- Corstone-300 / 310 / 315 / 320
- 각 플랫폼에서 Ethos-U configuration 실행 가능
- Corstone-320 FVP에서 U85 MAC configuration 변경 가능

### 주요 측정 지표

#### Compiler-level estimate

Vela

- estimated cycles
- SRAM / DRAM access estimate
- memory usage
- encoded weight size

#### Runtime observation

FVP PMU

- Total cycles
- Active cycles
- SRAM read/write
- External-memory read/write

#### Physical observation

MPS4 FPGA

- 동일한 종류의 NPU PMU counter를 실제 hardware에서 관측

### 주요 실험 옵션

- NPU type
- MAC configuration
- system configuration
- memory mode
- memory timing configuration

### 발표에서 제외

- FVP parameter 1,870개
- diagnostics / extra_args
- TA register field 전체
- PMU event 170종
- Fast Models patch-version 전체 나열

→ **2장**

---

# 4. Experimental Environment

### 목적

TFLite model이 실제 Ethos-U에서 실행되기까지의 과정을 설명한다.

### 실행 Pipeline

INT8 TFLite model  
↓  
Vela compilation  
↓  
Ethos-U optimized TFLite  
↓  
MLEK firmware build  
↓  
FVP / MPS4 execution  
↓  
PMU counter collection  
↓  
Result analysis

### Vela에서 결정하는 것

- accelerator configuration
- system configuration
- memory mode
- operator scheduling
- memory allocation

명령어 전체를 보여주기보다는 **각 단계에서 무엇이 결정되는지**를 보여주는 것이 중요하다.

---

## Appendix: Layer-wise Profiling

Whole-model PMU measurement만으로는 특정 scaling anomaly가 어느 연산에서 발생하는지 알기 어렵다.

따라서:

1. Vela가 생성한 NPU command stream을 분석
2. 각 NPU operator 실행 경계에 interrupt 삽입
3. interrupt 발생 시 PMU counter snapshot
4. operator 또는 operator group별 cycle / memory access를 복원

### Instrumentation 검증

발표에서는 다음 세 가지만 제시:

- Model output이 instrumentation 전후 동일
- 원래 command sequence는 유지되고 profiling command만 추가
- profiling overhead가 전체 실행 대비 매우 작고 반복 측정에서 일정함

세부 구현은 부록:

- FlatBuffer 변경 위치
- IRQ handler 코드
- opcode parsing
- CRC 값
- 정확한 cycle overhead

→ 본문 **1장**, 부록 **2장**

---

# 5. Workload Selection

### 목적

특정 모델 하나의 특성이 아니라 여러 형태의 TinyML workload에서 scaling 특성을 관찰한다.

### MLEK 모델을 사용한 이유

- Arm에서 Ethos-U 실행을 위해 제공하는 검증된 example workload
- Vela + MLEK inference runner와 바로 통합 가능
- 모두 INT8 기반
- 다양한 operator composition과 model size를 포함

### Workload 예

- RNNoise — Noise Reduction
- KWS — Keyword Spotting
- Anomaly Detection
- Visual Wake Words
- YOLO — Object Detection
- MobileNetV2 — Image Classification
- Wav2Letter — Speech Recognition

표에는:  
**Model / Task / Main operator characteristic**  
정도만 둔다.

### MLPerf Tiny와의 관계

MLPerf Tiny benchmark 자체를 실행했다고 표현하지 않는다.

대신:

> MLPerf Tiny가 다루는 대표 TinyML task와 유사한 workload category를 포함하도록 모델을 구성하였다.

또는

> MLEK workload를 사용하되 MLPerf Tiny의 대표 task 구성을 참고하여 workload diversity를 확보하였다.

→ **1장**

---

# 6. Experimental Sweep Design

### 목적

어떤 configuration을 조합하여 실험했는지 한눈에 보여준다.

### 실험 축


| Dimension            | Configuration                            |
| -------------------- | ---------------------------------------- |
| Corstone             | SSE-300 / 310 / 315 / 320                |
| NPU                  | U55 / U65 / U85                          |
| MAC scale            | NPU별 지원 configuration                    |
| Memory mode          | Sram Only / Shared SRAM / Dedicated SRAM |
| System configuration | configuration별 Arm 기본 설정                 |
| Workload             | 7 models                                 |


### 핵심 U85 sweep

128  
→ 256  
→ 512  
→ 1024  
→ 2048 MAC

동일 workload에서 MAC resource가 증가했을 때 NPU execution characteristics가 어떻게 변화하는지 관찰한다.

### 실험 규모

발표에서는 복잡한 tree 대신:

- 133 candidate configurations
- 실행 가능한 main evaluation set: 74 configurations
- 각 configuration 반복 측정
- 추가 platform / board / layer-wise experiments

정도로 단순화한다.

세부 sample count는 appendix.

→ **1~2장**

---

# 7. Results

여기는 실험 종류가 아니라 **발견한 현상 중심**으로 구성한다.

## Result 1 — MAC Scaling is Workload-dependent

MAC 수가 증가하면 대부분 execution cost가 감소하지만 감소 폭은 workload마다 다르다.

→ MAC scale vs normalized cycles 그래프

---

## Result 2 — Scaling is Mostly Sub-linear

MAC resource가 2배 증가한다고 execution cost가 항상 1/2이 되지는 않는다.

Compute resource 외에도:

- memory access
- operator structure
- scheduling
- system configuration

등의 영향을 받는다.

→ Scaling efficiency graph

---

## Result 3 — Compiler Estimate Captures Trend but not Every Anomaly

Vela estimate와 FVP observation은 전체적인 scaling trend에서는 높은 일관성을 보였다.

하지만 일부 configuration에서는 실제 observation과 다른 결과가 나타났다.

대표 사례:  
**U85 256 → 512 MAC에서 RNNoise cycle 증가**

→ predicted vs observed graph

---

## Result 4 — RNNoise 256→512 Anomaly is Distributed Across Small Operators

Layer-wise profiling 결과:

- 특정 하나의 operator가 원인은 아님
- 여러 small / elementwise operator group에서 증가가 누적
- 큰 convolution / matrix operation 하나로 설명되지 않음

→ operator group delta graph

---

## Result 5 — Memory Configuration Changes Magnitude, but the Main Trend Remains

여러 memory mode에서 재측정했을 때:

- cycle 변화의 크기는 달라짐
- RNNoise의 256→512 증가 현상 자체는 유지

따라서:

> 해당 현상은 특정 memory mode 하나에만 의존하는 현상으로 보이지 않는다.

단, compiler scheduling과 memory configuration의 효과가 동시에 변하므로 직접적인 memory bottleneck으로 단정하지 않는다.

---

## Result 6 — Simulation and FPGA Preserve Workload Ordering

U85@1024에서 FVP와 MPS4 FPGA의 workload별 상대적인 execution ordering이 동일하게 나타났다.

여기서는:

- 절대 cycle 값 비교보다
- workload ranking / normalized trend

위주로 설명한다.

→ **4~5장**

---

# 8. Limitations and Improvements

내부 코드명 F1/F2/A1/X4 등은 발표에서 제거한다.

### 현재 한계

#### Simulator version consistency

플랫폼별 Fast Models version이 완전히 동일하지 않음.

→ 동일 simulator version으로 재측정 필요

#### Memory counter coverage

일부 configuration에서 memory PMU counter가 충분히 수집되지 않음.

→ SRAM / external-memory counter 추가 측정

#### Memory effect isolation

memory mode 변경 시 compiler-generated program도 함께 변경될 수 있음.

→ 동일 artifact를 유지한 memory-service sensitivity experiment 필요

#### Stall information

현재 cycle / memory traffic만으로 정확한 bottleneck을 확정하기 어려움.

→ stall-related PMU event 추가 필요

#### FPGA coverage

현재 MPS4는 U85 1024 MAC configuration만 제공.

→ physical board에서 전체 MAC scaling을 직접 검증할 수 없음

→ **1~2장**

---

# 9. Ongoing Work — MPS4 FPGA Layer-wise Measurement

### 목적

FVP에서 개발한 layer-wise profiling 방법을 실제 MPS4 FPGA로 확장한다.

### 현재 구성

TFLite  
↓  
Vela  
↓  
Layer-wise profiling instrumentation  
↓  
FPGA firmware build  
↓  
MPS4 deployment  
↓  
PMU collection  
↓  
Operator-level analysis

### 확인하려는 것

- FVP에서 관찰한 operator-level behavior가 실제 FPGA에서도 나타나는가
- simulation에서 나타난 workload별 상대적 특성이 hardware에서도 유지되는가
- FVP에서 발생하는 profiling overhead와 실제 hardware의 profiling overhead 차이

### 중요 제한

MPS4 FPGA의 U85는 1024 MAC으로 고정되어 있으므로

**256→512 scaling anomaly 자체를 FPGA에서 직접 재현하는 것이 목적은 아니다.**

대신:

> FVP에서 관찰된 operator-level execution characteristics가 실제 hardware에서도 일관된지 검증한다.

→ **1장**