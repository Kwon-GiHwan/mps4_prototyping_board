# mps4_prototyping_board

Arm MPS4 FPGA prototyping board (HBI0376 Rev B Var A) 위에서 Corstone SSE-320 /
Cortex-M85 / **Ethos-U85 NPU**의 per-layer 성능을 측정하기 위한 펌웨어·호스트 툴링과
qualification 증거.

실제 보드에서 실행·검증된 결과다. FVP 시뮬레이터 결과가 아니다.

## 지금 어디까지 왔나

| 단계 | 상태 |
|---|---|
| 하드웨어 bring-up (SODIMM 접촉 불량 원인 규명) | 완료 |
| GCC golden baseline (armclang scatter → GNU ld 이식) | 완료 |
| Functional runner v1 (프레임 프로토콜 + 상태기계) | 완료 |
| Measurement-clean runner (측정 경계 · stale-output 차단) | **보드 인수 통과** |
| NPU PMU 계측 (cycle counter) | 진행 중 — 원인 규명 단계 |
| A/B/C 오염 게이트 | 미착수 |

측정 이미지 `FI101_RUNNER_V1_MEASURE_SEQ`는 실보드에서 **16/16 + 15/15** 게이트를 통과했고,
그 증거(스크립트·raw log·해시)가 `provenance/`에 동결돼 있다.

현재 PMU candidate의 **cycle counter 수치는 사용 금지**다. `PMCCNTR_CFG`가 배선되지 않은
것이 정적 분석으로 확인됐고, 그것이 원인이라는 것은 아직 **가설**이다. 실보드 A/B/C 실험으로
증명하기 전까지 확정하지 않는다.

## 구성

```
firmware/          펌웨어 소스 (마일스톤별 Makefile + 러너)
  Selftest_measure/  보드 인수를 통과한 measurement-clean 러너
  Selftest_pmu/      NPU PMU candidate + 레지스터 생성기 + 음성 게이트
host/              호스트 툴링 (프로토콜 클라이언트 · MCC 트랜스포트 · 시험)
provenance/        이미지별 동결 증거 (MANIFEST · SHA256SUMS · raw log)
evidence/          bring-up 원시 UART 캡처
board-config/      보드 설정 스냅샷 (현재 + 역사적)
build-env/         빌드 환경 provenance
host-environment/  호스트 실행 환경 (인터프리터 · 의존성 · 시리얼 바인딩)
docs/MIRROR.md     이 트리의 상세 구조와 무결성 확인 절차
```

## 설계 원칙

계측 코드보다 **증거의 등급을 구분하는 방식**이 이 저장소의 핵심이다.

**하드웨어 상수는 유도하지 않고 추출한다.** `Selftest_pmu/gen_npu_pmu_regs.py`가 Arm 벤더
헤더에서 레지스터 오프셋과 비트 위치를 기계적으로 뽑아 헤더를 생성하고 `--check`가 드리프트를
잡는다. 사람이 카운터 개수에서 비트 위치를 계산해 넣었다가 overflow 비트를 reserved 영역에서
읽는 결함이 실제로 났기 때문이다 — 그 상태에서는 wrap된 샘플이 "overflow 없음"으로 통과한다.
`nc_gen.py`가 벤더 헤더를 13종으로 변조해 생성기가 **실패해야 할 때 실패하는지** 검증하고,
생성된 헤더를 실제로 컴파일해 `_Static_assert` 백스톱까지 실증한다.

**"검사하지 못한 것"은 통과가 아니라 실패다.** 정규식이 키를 놓쳐 동결 대상을 검사하지 않고
exit 0을 낸 적이 있어, 검증기가 조용히 통과하는 경로를 전부 실패로 바꿨다.

**동결 증거와 작업 도구를 분리한다.** `MANIFEST.yaml`의 qualification 항목은 100% 일치를
요구하고, 계속 개발되는 호스트 도구는 별도 스냅샷으로 둔다. 둘을 한 계약에 넣었더니 평범한
스크립트 수정이 아카이브 손상처럼 보였다.

**측정값의 유효성을 분해한다.** "레지스터를 읽었다" · "카운터가 무장됐다" · "실제로 카운팅했다"는
서로 다른 사실이고 각각 별도 플래그로 보고된다. 값이 0인 것과 측정하지 않은 것도 구분된다 —
호스트 파서는 후자를 `None`으로 반환한다.

## 재현

빌드는 `build-env/`의 작업 트리 아카이브에서 재현된다. Clean 추출 후 두 이미지가 비트 단위로
일치하는 것을 확인했다.

다만 **Arm 벤더 소스와 컴파일된 `.BIN`은 재배포 조건이 확인되지 않아 이 저장소에 포함하지
않았다**(`.gitignore` 참조). 해시는 `build-env/BUILD_ENVIRONMENT.yaml`에 기록돼 있어 동일성
확인은 가능하다. 보드 플랫폼 바이너리(FPGA 비트스트림 등 113 MB)도 별도 아카이브에 있다.
**이 저장소만으로는 보드를 재구성할 수 없다.**

그래서 `provenance/*/SHA256SUMS`는 **clone 에서 검증되지 않는다** — 제외된 `.BIN`이
목록에 들어 있기 때문이다. 이는 손상이 아니라 의도된 제외이며, 완전한 검증은 벤더
아티팩트를 갖춘 원본 아카이브에서만 가능하다.

## 하드웨어

```
보드    Arm MPS4 (HBI0376 Rev B Var A)
SoC     Corstone SSE-320 / Cortex-M85
NPU     Ethos-U85 — 이벤트 카운터 8개, 48비트 cycle counter
호스트  FTDI 4포트 — if00 MCC 콘솔(CR), if01 FPGA UART0(LF)
```

## 라이선스

직접 작성한 코드(러너 · 호스트 툴링 · 생성기 · 시험)의 라이선스는 별도 명시 전까지 미정이다.
Arm 벤더 소스·바이너리는 포함돼 있지 않으며 각각의 원 배포 조건을 따른다.
