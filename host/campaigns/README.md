# 공통 MLEK 캠페인

`host.campaigns`는 모델 × 대상 × 옵션 variant × MAC 후보를 먼저 전개하고,
각 조합의 실행 결과를 빠짐없이 기록하는 유지보수 경로다. 과거의 동결된 실험
스크립트나 V15 보드 대조 실험을 범용 모델 실행기로 사용하지 않는다.

## 측정·판정 계약

- 각 반복은 새 FVP 프로세스 또는 새 보드 부팅에서 시작한다. 보드는 UART
  수신 준비를 확인한 뒤 재부팅한다. warmup은 없고 반복당 추론은 한 번이다.
- 선택한 모델의 SHA-256을 확인하고 Vela 출력 모델을 stock MLEK
  `inference_runner_MODEL_PATH`에 주입한다. 모델을 기본 예제 모델로 대체하지 않는다.
- 소스는 수정되지 않은 Git checkout이어야 한다. revision, 도구 identity,
  Vela 설정, toolchain, 모델과 빌드 산출물의 identity를 기록한다.
- 완료 문구 하나, 추론 횟수 1, 완전한 NPU profile 하나와
  `TOTAL = ACTIVE + IDLE`가 성립해야 성공이다. 누락되거나 잘못된 측정은 실패다.
- CPU fallback은 허용한다. Vela 로그와 CPU 관련 출력 행을 보존하며, 해당 행이
  없는 것은 CPU 연산이 없다는 증명이 아니다.
- 측정값은 NPU profile counter다. 호스트 wall-clock 경과 시간은 추론 latency가
  아니다. AXI 계열과 SRAM/EXT 계열 event는 원래 이름·단위와 함께 보존한다.

같은 실행·판정 절차를 적용해도 NPU, 메모리 구성, FVP 버전, timing adapter가
다르면 절대 cycle 비교가 자동으로 성립하지 않는다. `repeat_policy: "record"`는
반복값을 그대로 기록한다. `"exact"`는 각 반복의 event vector가 같아야 하므로
실보드 기본값으로 사용하지 않는다.

**현재 stock runner의 입력 생성 정책을 사용한다. 모든 플랫폼에서 실제로 같은
입력 tensor byte가 생성되는지는 아직 검증하지 않았다.** 고정 입력 데이터 주입과
실행 시 tensor hash 확인은 별도 계약 확장이 필요하다. 이 코드의 회귀 검증은
가짜 실행파일과 보드 I/O fixture를 이용했으며, 새 실행기로 실제 MLEK 빌드,
FVP 6종, 실보드 전체 실험을 완료한 상태는 아니다.

## 설정과 실행

설정 예시는 [mlek.example.json](../../environment/campaigns/mlek.example.json)이다.
`/path/to/...`를 설치된 MLEK·FVP 경로로, `/dev/REPLACE_...`를 확인한 보드 장치로
교체한 별도 설정 파일을 사용한다. 예시는 설치를 자동 수행하지 않는다.

```sh
python3 -m host.campaigns plan /path/to/campaign.json --output /tmp/mlek-plan.json
python3 -m host.campaigns run /path/to/campaign.json --output /path/to/new-results
python3 -m host.campaigns run /path/to/campaign.json --output /path/to/new-results --resume
```

`plan`은 모델 발견과 해시 계산만 하며 도구·보드를 실행하지 않는다. `--output`을
생략하면 JSON을 stdout으로 출력한다. 기존 출력 파일은 덮어쓰지 않는다.
`run`도 새 출력 디렉터리를 요구한다. 종료 코드는 전체 성공 0, 하나라도 성공 외
상태가 있으면 1, 설정·재개 조건 오류 2, 사용자 중단 130이다.

`discover_models`는 지정한 MLEK resources 디렉터리에서 모든 `.tflite`를 찾고
기존 `_vela.tflite` 출력은 제외한다. MLEK 모델 다운로드를 끝낸 뒤 사용해야 한다.
이 목록은 **실제로 발견한 파일** 전체이며 설치하지 않은 모델의 존재까지 확인하는
원격 카탈로그는 아니다. 명시적인 모델 목록을 원하면 `discover_models` 대신
`models: [{"id": "...", "path": "...", "sha256": "..."}]`를 사용한다.

예시는 기존 기록에서 확인한 FVP 6종과 MPS4 SSE-320/U85-1024 보드를 포함한다.
Performance/Size 두 variant, 일곱 MAC 후보를 사용하므로 모델당 98개 조합을
계획한다. 지원하지 않는 MAC도 삭제하지 않고 `UNSUPPORTED_CONFIGURATION`으로
기록한다. 실제 보드 adapter는 현재 이 MPS4 구성만 지원하며, 다른 물리 보드는
배포·부팅·복원 adapter와 검증을 추가해야 한다.

| 대상 | 선언된 지원 MAC | TA | Vela system config / memory mode |
| --- | --- | --- | --- |
| SSE-300 U55 | 32, 64, 128, 256 | ON | U55 High End Embedded / Shared_Sram |
| SSE-300 U65 | 256, 512 | ON | U65 High End / Dedicated_Sram |
| SSE-310 U55 | 32, 64, 128, 256 | OFF | U55 High End Embedded / Shared_Sram |
| SSE-310 U65 | 256, 512 | OFF | U65 High End / Dedicated_Sram |
| SSE-315 U65 | 256, 512 | OFF | U65 High End / Dedicated_Sram |
| SSE-320 U85 FVP | 128, 256, 512, 1024, 2048 | ON | U85 DRAM Mid_1024 / Dedicated_Sram |
| MPS4 SSE-320 U85 board | 1024 | ON | U85 DRAM Mid_1024 / Dedicated_Sram |

FVP 지원값·TA·parameter namespace는
[기존 capability 조사](../../docs/paper/platform_sensitivity/FVP_CAPABILITY_MATRIX.csv),
Vela config 이름은 [기존 옵션 조사](../../docs/paper/platform_sensitivity/probe_raw/vela_options.json),
보드 빌드 조건은 [과거 FPGA 빌드 코드](../../docs/paper/evidence/fpga-builds-20260825/fpga_build.py)를
참고했다. 현재 설치의 지원 여부를 대신하지 않는다. 실행 때 도구 version/help와
FVP parameter 출력을 별도로 남긴다.

예시의 U85 FVP와 보드는 동일한 `Ethos_U85_SYS_DRAM_Mid_1024`를 적용한다.
FVP의 모든 MAC에 같은 값을 요청하며 지원하지 않는 조합은 실패 상태로 남긴다.
과거 캠페인은 MAC에 따라 Low/Mid/High를 변경했으므로 이 예시가 과거 결과를
그대로 재현한다는 뜻은 아니다. system config, memory mode, activation arena는
variant에서 변경할 수 있으며 바뀐 조건은 별도 cell identity를 가진다.

추가 Vela 옵션은 `options.py`의 정확한 허용 이름·값만 가능하다. CMake 추가값은
`CMAKE_BUILD_TYPE`만 허용한다. 모델·NPU·MAC·arena·TA·플랫폼·runner·FPGA flag는
관리되는 설정이므로 추가 옵션으로 덮어쓸 수 없다. FVP 추가 parameter는 literal
키만 사용하며 MAC/UART/capture 관련 키를 덮어쓸 수 없다.

## 결과와 실패 처리

출력의 `plan.json`은 최초 전체 계획, `results.json`은 진행·최종 상태 원장이다.
각 cell 하위에 빌드 명령·로그, 산출물, 반복별 FVP/UART 원본과 검증 결과를 남긴다.
보드는 원래 카드 파일의 backup과 복원 확인도 기록한다.

메모리 부족은 `MEMORY_ERROR`, 설치 누락은 `ENVIRONMENT_UNAVAILABLE`, 빌드 실패는
`BUILD_ERROR`, 실행 실패는 `EXECUTION_ERROR`, 측정 오류는 `INVALID_MEASUREMENT`
등으로 구분한다. 실패한 cell을 삭제하거나 성공 표본으로 대체하지 않고 다음
조합으로 진행한다. 보드 복원 실패는 해당 장치를 격리해 후속 접근을 막는다.

`--resume`는 같은 계약·설정·모델 및 저장된 원장의 무결성을 요구한다. 종료 상태의
cell은 재시도하지 않는다. 중간에 끊긴 시도도 새 표본으로 몰래 대체하지 않는다.
강제 종료 후 `.running`이 남았다면 실제 프로세스·보드 복구 상태를 확인한 뒤
재개해야 한다. 출력 디렉터리와 raw log는 분석·재개가 끝날 때까지 보존한다.
