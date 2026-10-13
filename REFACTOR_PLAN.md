# 소스·설정 리팩토링 작업 기록

작성일: 2026-09-11. 초기 브랜치: `refactor/source-config`.
현재 브랜치: `refactor/unified-mlek-campaigns` (기준 커밋 `b5e1f98`).
분기 기준: `paper/sigmetrics2027-submission`의
`1ceb5646971e5b2649c3370ae5e1890cd29491b1`.

## 목표와 진행 방식

소스·설정의 유지보수성을 개선하면서 기존 CLI, 프로토콜, 판정 규칙과
동결된 실험의 재현 경로를 보존한다. 독립적으로 검증 가능한 작업을 묶어 구현·검증한 뒤 이 기록을
갱신한다. 사용자 결정이 필요한 범위 변경에서만 진행 여부를 확인한다. 실패 또는 미검증 항목을 완료로 처리하지 않는다.

기존 `docs/`, `evidence/`, `provenance/`와 각 영역의 문서·복구 기록은
수정·이동하지 않는다. 이 파일은 사용자가 요청한 작업 순서·진행 기록이다.
테스트가 해당 경로의 자료를 읽는 의존성은 유지한다.

## 작업 순서와 완료 기준

| 단계 | 상태 | 작업 | 완료 검증 |
| --- | --- | --- | --- |
| 1 | 완료 | 범위, 동결 참조, 대표 오프라인 테스트 기준선 확정 | 아래 범위 및 제약 기록, 18개 테스트 실행 단위의 종료 코드·결과 확보 |
| 2 | 완료 | 테스트 실행 경로 정리 | 명시적 오프라인 목록, 테스트별 실행 방식 유지, 실패 종료 코드 전파, 기본 실행에 보드 접근 없음 |
| 3 | V9~V15 완료; 동결 영역 제외 | 실험별 구조화 및 호스트 import 통일 | 현재 CLI 경로, 모듈·예외 클래스 동일성 및 mock 적용 회귀 검증 |
| 4 | 완료: 통계·archive·V9~V13 통신 | 호스트 통신·공통 유틸 분리 | ACK 순서·중복·timeout·CRC 음성 테스트, 기존 입력의 결과와 거부 판정 동일 |
| 5 | 후속 구현·전체 로컬 재검증 완료 | 검증기 책임 분리 | 기존 동결 경로 보존, 후속 구현의 전체 의존성 identity 정의, fixture별 판정·rule ID 동일, mutation RED 검증 |
| 6 | 비동결 manifest 정리 완료; 실제 빌드 미검증 | 비동결 빌드·실행 설정 정리 | 생성 C 바이트·해시 동일, Makefile 테스트, 적격 컨테이너 clean build 두 번 비교 |

단계 2부터 작은 변경 단위로 진행한다. 기존 테스트의 실행 형태를 먼저
명시하고, 테스트 프레임워크 전체 전환이나 디렉터리 일괄 이동은 하지 않는다.
단계 5·6의 외부 빌드·보드 작업은 로컬 단위 검증과 구분한다.

## 변경 범위

| 영역 | 취급 |
| --- | --- |
| `host/` 실행 모듈과 오프라인 테스트 | 우선 리팩토링 후보. 파일별 동결·경로 참조를 변경 전에 재확인 |
| `host/bringup/`, `host/legacy/patches/` | 과거 보드 작업·일회성 패치 보존. import 또는 일괄 실행 금지 |
| `firmware/Selftest_pmu_diag/` Python 검증기 | 책임 분리 후보지만 아래 helper digest 계약 대상은 직접 변경 보류 |
| `firmware/patches/` 현재 생성기 | I/O·정확히 1회 치환 유틸 후보. 버전별 C template·측정 loop 보존 |
| `firmware/Makefile.*` | 비동결 파일부터 인라인 Python·실제 동일 규칙 추출 검토 |
| C, assembly, linker 입력 | 첫 작업 범위에서 보존. 바이너리 비교 가능한 별도 단계에서 검토 |
| `environment/board/` | 현재·과거 보드 스냅샷 및 복구 입력. current/history로 구분해 보존 |
| `environment/host/` | 환경 복구 기록으로 보존. 실행 설정처럼 수정하지 않음 |
| `environment/build/` | 복구 YAML과 archive 보존. 컨테이너 프로젝트 보관본은 archive/ 아래 유지 |
| `docs/`, `evidence/`, `provenance/` | 읽기 전용. 내부 `.py`, 생성 C도 일괄 리팩토링 대상에서 제외 |

## 확인한 동결·호환 제약

- V14/V15 Makefile 및 source patcher가
  `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c`와
  `firmware/Drivers/u85_driver/u85.c`의 SHA-256을 고정한다.
- `firmware/Selftest_pmu_diag/check_s5_only_boundary_image.py`의
  `HELPER_DEPENDENCIES`는 V12, V13, V14 검증기 세 파일의 digest를 고정한다.
  큰 V14 검증기를 단순 추출하는 것만으로도 이 계약이 깨진다.
- `firmware/Selftest_pmu_diag/PMU_QUAL_FROZEN_BASELINE.sha256`은
  `firmware/Selftest_pmu/runner_pmu_main.c`, `firmware/Makefile.pmu`,
  `firmware/LinkScripts/lnk.ld.S`, `firmware/LinkScripts/lnk.measure.overlay.ld`
  및 provenance tree를 기록한다.
- 2026-09-10 확인: 위 C 입력 2개, helper 3개, PMU runner·Makefile·overlay의
  현재 해시는 각 고정값과 일치했다. `lnk.ld.S`는 로컬에 없었다.
  provenance tree 전체와 원격 파일의 무결성은 이번에 검증하지 않았다.
- helper 분리 시 기대 해시만 바꿔 통과시키지 않는다. 기존 자격 경로와
  후속 개발 경로를 구분하고 새 의존성 전체에 대한 검증 기준을 마련한다.
- 펌웨어와 호스트의 wire 명세 선언은 독립적으로 유지한다. wire parser와
  manifest 기반 normalization의 경계, PASS/FAIL/UNPROVEN, rule ID를 보존한다.
- object/link 순서, `-O1 -g3`, BIN section 구성, variant별 생성·출력 경로를
  공통화 과정에서 바꾸지 않는다.
- `host.xxx`와 bare import가 혼재한다. 단순 re-export만으로 예외 클래스나
  monkeypatch 동일성이 보장된다고 가정하지 않는다.

이 목록은 확인한 주요 계약이다. 이후 각 변경 전에 해당 파일의 digest·경로
소비자를 추가 조사한다. 목록에 없다는 이유로 비동결 파일로 간주하지 않는다.

## 1단계 테스트 기준선

실행일: 2026-09-10. 로컬 Python 3.14.7,
`/opt/homebrew/opt/python@3.14/bin/python3.14`.
저장소 루트에서 실행했다. 기존 bytecode를 읽지 않도록 각 실행에
임시 `PYTHONPYCACHEPREFIX`를 지정했고 `PYTHONPATH`는 저장소의 `host/`였다.
임시 cache는 테스트 종료 후 제거했다.

다음 V15 모듈은 각각
`python3 -m unittest host.tests.test_<이름>_pmu_completion_s5_only_control`
명령으로 독립 프로세스에서 실행했다.

| 이름 | 테스트 수 | 결과 |
| --- | ---: | --- |
| analyze | 25 | OK, exit 0 |
| canonical_elf | 20 | OK, exit 0 |
| collect | 22 | OK, exit 0 |
| comparison_mode | 20 | OK, exit 0 |
| contract | 21 | OK, exit 0 |
| deployment | 42 | OK, exit 0 |
| inheritance | 20 | OK, exit 0 |
| normalize | 28 | OK, exit 0 |
| preflight | 29 | OK, exit 0 |
| runner_proto | 38 | OK, exit 0 |

V15 합계 265개. 추가로
`python3 -m unittest host.tests.test_pmu_completion_visibility_v14`를 실행해
60개 OK, exit 0. unittest 합계는 325개다.

구형 테스트는 각각 `python3 host/tests/<파일명>.py`로 실행했다.
아래 숫자는 unittest case 수가 아닌 스크립트 자체 보고 check 수다.

| 파일명 | passed | failed | 종료 코드 |
| --- | ---: | ---: | ---: |
| test_proto_unit | 9 | 0 | 0 |
| test_abi_unit | 18 | 0 | 0 |
| test_pmu_abi_unit | 16 | 0 | 0 |
| test_pmu_qual_unit | 281 | 0 | 0 |
| test_pmu_cfg_unit | 274 | 0 | 0 |
| test_pmu_diag_unit | 159 | 0 | 0 |
| test_harness_policy | 17 | 0 | 0 |

스크립트 합계 774 checks 통과. 총 18개 실행 단위 모두 exit 0.
재개 시 임시 JSON 실행 로그와 위 결과를 대조했다.

### 검증하지 않은 범위

- 전체 테스트, 나머지 V9~V14 host suite, firmware gate suite·mutation suite.
- Python 3.10/3.12에서의 호환성, ELF 변환의 실제 toolchain 통합 동작.
- 원격 컨테이너 빌드, FVP, 실제 보드 통신·배포·복구.
- 로컬 ARM GCC가 PATH에 없고 일부 vendor source/linker 입력도 없다.
  기존 Dockerfile만으로 적격 빌드 환경을 재현할 수 있다고 가정하지 않는다.

`test_runner_gate`, `test_measure_accept`, `test_pmu_board`, `test_stale_demo`,
`test_rawrx`, `test_harness_board`, `test_fixed_inference`는 보드 실행 경로로
기본 오프라인 목록에서 제외한다. `pytest` 전체 discovery는 사용하지 않는다.

## 2단계 실행 진입점 (2026-09-11)

`host/run_offline_tests.py`를 추가했다. 실행 명령:

```sh
python3 host/run_offline_tests.py
```

검토한 기준선 18개만 명시적으로 실행하며 discovery를 사용하지 않는다.
현재 Python 인터프리터로 각 테스트를 별도 프로세스에서 실행하고 원본 출력을
보존한다. 호출 위치와 관계없이 저장소 루트를 cwd로 사용하며, 임시 bytecode
cache와 host import 경로를 지정한다. 실행 단위마다 90초 timeout을 적용한다.
실패·timeout·프로세스 시작 오류가 발생해도 나머지를 실행하며 하나라도
실패하면 최종 exit 1이다. 요약의 개수는 test case가 아닌 실행 단위 수다.

검증 수준: 단위 및 로컬 프로세스 통합.

- `python3 -B -m unittest host.tests.test_run_offline_tests`: 2개 OK, exit 0.
  실제 실패하는 unittest 뒤에 standalone script가 실행되는지, cwd/import
  환경과 cache 제거를 검증했다. timeout·시작 오류 경로는 mock으로 검증했다.
  출력 중 intentional regression fixture의 FAILED는 예상된 자식 결과다.
- `/tmp`에서 `python3 /Users/gihwan/Documents/Projects/mps4_prototyping_board/host/run_offline_tests.py`:
  18개 실행 단위 PASS, exit 0. unittest 325개 및 스크립트 774 checks 유지.
- 새 파일의 구문·공백 검사와 `git diff --check` 수행.

진입점 회귀 테스트는 기준선 18개와 별도로 위 unittest 명령으로 실행한다.
전체 저장소 suite, 실제 timeout 대기, 펌웨어 빌드·보드 검증은 하지 않았다.
기존 테스트·동결 소스·설정·문서는 변경하지 않았다.

## 3단계 A: V15 내부 import 통일 (2026-09-11)

먼저 `host.normalize_pmu_completion_s5_only_control`의 `deployment`, `wire`
참조가 `from host import ...`로 가져온 모듈과 다른 객체임을 재현했다.
`host/tests/test_v15_imports.py`의 새 회귀 테스트가 변경 전 실패하는 것을
확인한 뒤 V15 실행 모듈 7개와 기존 테스트 9개의 import/경로 설정을 수정했다.

- V15 내부 의존성 및 테스트 fixture import를 `host.*`, `host.tests.*`로 통일.
- 패키지 import 때 host 디렉터리를 sys.path에 삽입하지 않음.
  직접 파일 실행 때는 저장소 루트를 추가해 동일한 host 의존성을 사용.
- wire 모듈의 광범위한 ModuleNotFoundError fallback을 제거하고 동일한
  `host.runner_proto.ProtocolError`를 사용.
- source 판정, wire 상수, 동결 firmware, 기존 docs/evidence는 변경하지 않음.

검증 수준: 단위 및 로컬 프로세스 통합.

- `python3 host/run_offline_tests.py`: 18개 실행 단위 PASS, exit 0.
  기존 unittest 325개와 standalone 774 checks 유지.
- `python3 -B -m unittest host.tests.test_v15_imports`: 2개 OK.
  새 프로세스의 모듈·예외 클래스 동일성, mock 공유, V15 bare 모듈의 내부
  중복 로드 부재, PYTHONPATH 없는 외부 cwd에서 V15 파일 10개 직접 실행 확인.
- `host.run_offline_tests.UNITTEST_MODULES`의 11개 모듈과
  `host.tests.test_v15_imports`를 하나의 `python3 -m unittest` 프로세스에서
  함께 실행: 327개 OK, exit 0. 별도 임시 bytecode cache 사용.
- 독립 code-review: 관련 테스트 72개와 직접 실행 경로 확인, 구체 결함 없음.
- 변경 파일 Python 3.10 문법 parse 및 `git diff --check` 확인.

한계: V8~V14의 bare import 경로는 아직 통일하지 않았다. 외부 호출자가
V15 모듈 자체를 bare 이름과 `host.*` 양쪽으로 직접 import하는 경우까지
동일 객체로 만드는 alias 장치는 도입하지 않았다. V15 호출자는 `host.*`를
사용한다. 기존 CLAUDE.md의 V15 bare import 안내는 동결 경로의 이전 관례이며,
이 브랜치의 V15 변경 범위에서는 이 기록의 패키지 import 방식을 적용한다.
전체 suite·실제 ELF 도구·펌웨어 빌드·보드 동작은 이번에도 검증하지 않았다.

## 3단계 B: 실제 패키지 구조 및 legacy 분리 (2026-09-11)

사용자가 평면 구조 개선과 불필요 파일 정리·legacy 이동을 요청했다.
이에 import 치환만 이어가기보다 실험별 구현·테스트를 실제로 묶는 작업을
먼저 수행했다. 아래가 현재 구조이며, 앞선 단계의 옛 경로는 작업 이력이다.

```text
host/
  experiments/
    s5_only/
      protocol.py          # wire decoding
      contract.py          # experiment vocabulary and invariants
      collector.py         # cell/campaign collection
      normalize.py         # wire + verified context
      analysis.py          # outcome classification
      canonical_elf.py      # analysis artifact identity
      comparison_mode.py   # equivalence mode qualification
      deployment.py        # deployed artifact/context binding
      preflight.py         # pre-board checks
      inheritance.py       # inherited qualification inventory
  tests/
    s5_only/test_*.py       # matching ten test modules
    test_v15_imports.py     # package/process and vocabulary-scope regression
  legacy/
    patches/               # six historical one-off patch scripts
  bringup/                 # frozen board scripts, original paths retained
  run_offline_tests.py
```

기존 `host/<prefix>_pmu_completion_s5_only_control.py`를 다음 이름으로 이동했다.

| 이전 prefix | `host/experiments/s5_only/`의 현재 모듈 |
| --- | --- |
| analyze | analysis.py |
| canonical_elf | canonical_elf.py |
| collect | collector.py |
| comparison_mode | comparison_mode.py |
| contract | contract.py |
| deployment | deployment.py |
| inheritance | inheritance.py |
| normalize | normalize.py |
| preflight | preflight.py |
| runner_proto | protocol.py |

테스트도 같은 이름으로 `host/tests/s5_only/test_<모듈>.py`에 이동했다.
기존 소스·테스트 경로 20개는 제거했으며 wrapper를 남기지 않았다.
실행 코드에서 발견한 소비자를 모두 새 경로로 갱신했다. 보존 문서 안의 옛
명령은 역사적 경로다. 외부 호출자는 새 package/file 경로로 변경해야 한다.

```sh
python3 host/run_offline_tests.py
python3 -B -m unittest host.tests.s5_only.test_protocol
python3 -m host.experiments.s5_only.inheritance
```

직접 파일 실행도 새 위치에서 지원한다. 예:
`python3 host/experiments/s5_only/inheritance.py`.

`host/patches/`의 6개 스크립트는 저장소 실행 코드에서 호출 참조를 찾지
못했고 이미 적용된 문자열 치환을 담고 있어 `host/legacy/patches/`로 이동했다.
삭제하지 않았으며 이동 전후 6개 파일 SHA-256 동일성을 확인했다.
`host/bringup/`은 serial-bindings 복구 기록에 경로가 고정되어 그대로 두었다.
빈 추상화 디렉터리나 모든 버전을 한데 넣는 generic framework는 만들지 않았다.

검증 수준: 단위 및 로컬 프로세스 통합.

- `python3 host/run_offline_tests.py`: 새 경로의 18개 실행 단위 모두 PASS.
  원래 unittest 325개, standalone 774 checks 유지.
- `python3 -B -m unittest host.tests.test_v15_imports host.tests.test_run_offline_tests`:
  5개 OK. 현재 source 모듈 10개의 외부 cwd 직접 실행 포함.
- 이동 전 snapshot과 AST 비교: 10개 소스의 import/bootstrap 이외 로직 동일.
- 어휘 guard는 구현뿐 아니라 이동한 테스트까지 재귀 검색하도록 유지했다.
  양쪽 파일에 금지어를 주입하는 read_text mock 음성 회귀가 거부를 확인한다.
- 독립 리뷰에서 guard 범위 축소와 기존 suite 명령 경로 소멸을 발견해 수정했다.
  수정 후 리뷰에서 추가 결함 없음, 관련 unittest 24개 통과.
- `.claude/commands/suite.md`는 실행용 명령 설정이므로 새 runner 명령으로 갱신.
- 새 파일 Python 3.10 문법 parse 및 공백 검사, `git diff --check` 수행.

이번에도 firmware, docs, evidence, provenance, 복구 설정은 변경하지 않았고
보드 접근 및 펌웨어 빌드를 실행하지 않았다. 전체 host 구조 전환은 아직 남았다.

## 3단계 C: V14 completion visibility 패키지화 (2026-09-11)

`host/experiments/completion_visibility/`로 구현 6개를 이동했다.
이전 `*_pmu_completion_visibility_v14.py` 파일의 대응은 다음과 같다.

| 이전 prefix | 현재 모듈 |
| --- | --- |
| runner_proto | protocol.py |
| collect | collector.py |
| analyze | analysis.py |
| preflight | preflight.py |
| requirements | requirements.py |
| run | runner.py |

기존 테스트 5개도 `host/tests/completion_visibility/test_<모듈>.py`로
이동했다. protocol 테스트의 이전 이름은 `test_pmu_completion_visibility_v14.py`다.
새 `test_runner.py`는 timeout 예외, ACK/완료/별도 재조회 순서, 새 CLI의
도움말 경로를 보드 없이 검증한다. 기존 소스·테스트 경로 11개는 제거했다.

- requirements의 함수·테스트 경로 문자열과 AST resolver를 함께 갱신했다.
  firmware의 기존 bare 참조는 유지한다. 누락된 참조를 건너뛰지 않는다.
- parser 독립성 검사는 새 테스트 이름·패키지 경로도 거부한다.
- V15 contract 테스트가 새 V14 protocol을 참조하도록 갱신했다.
- `host/run_pmu_qual.py`는 provenance의 SOURCE_ANCHOR 해시에 포함되어 있어
  내용 변경 없이 보존했다. V14 runner는 이 동결된 V8 transport와 동일한
  bare runner_proto를 사용한다. V14의 순수 protocol/collector는 package
  import를 사용한다. 이 경계는 구형 transport 후속 구현 전까지 명시적으로 유지한다.
  사용되지 않던 runner의 V14 protocol import는 제거했다.

현재 명령:

```sh
python3 host/run_offline_tests.py
python3 -B -m unittest host.tests.completion_visibility.test_requirements
python3 -m host.experiments.completion_visibility.runner --help
python3 -m host.experiments.completion_visibility.protocol --help
```

runner의 실제 실행은 보드 작업이므로 이번에 실행하지 않았다. 직접 파일
경로 실행도 새 위치에서 지원하며, runner/protocol의 `--help`는 PYTHONPATH 없는
외부 디렉터리에서 확인했다. preflight 입력 파일 처리는 기존 CLI 회귀 테스트로 확인했다.

검증 수준: 단위 및 로컬 프로세스 통합.

- 이동 전 V14 기존 테스트 5개 모듈: 189개 OK.
- 이동 후 V14 테스트 6개 모듈: 192개 OK(새 runner 테스트 3개 포함).
- `python3 host/run_offline_tests.py`: 23개 실행 단위 모두 PASS, exit 0.
  V15 265 + V14 192 = unittest 457개, 기존 standalone 774 checks 통과.
- 실행 목록의 unittest 모듈 전부와 `host.tests.test_v15_imports`,
  `host.tests.test_run_offline_tests`를 단일 unittest 프로세스로 실행:
  462개 OK. 기존처럼 실행기 테스트의 의도적인 자식 실패는 외부 테스트가 검증한다.
- 이동 전 snapshot과 AST 비교: 6개 소스의 import/bootstrap 및 참조 경로·usage
  문자열을 제외한 로직 동일. 동결 transport는 snapshot 및 git 원본과 동일.
- 독립 리뷰: 전체 이동 diff 및 requirements 의미 필드·참조 symbol 순서·요약
  동일 확인, 구체 결함 없음. 리뷰어도 V14 192개를 직접 실행했다.
- Python 3.10 문법 parse 및 `git diff --check` 수행.

전체 저장소 테스트, 구형 Python 런타임, 펌웨어 빌드, 보드 통신은 검증하지 않았다.
`.claude` suite 안내를 확장된 실행 목록에 맞췄으며 보존 문서는 수정하지 않았다.

## 3단계 D: V9~V13 버전별 패키지화 (2026-09-11)

구현 15개와 standalone 테스트 5개를 이동했다. 버전별 상수, wire layout,
manifest identity, 분류·통계 로직은 합치지 않았다.

```text
host/experiments/
  interval/
    v9/{protocol,runner,analysis}.py
    v10/{protocol,runner,analysis}.py
    v11a/{protocol,runner,analysis}.py
  completion_poll/
    v12/{protocol,runner,analysis}.py
    v13/{protocol,runner,analysis}.py
host/tests/
  interval/{test_v9,test_v10,test_v11a}.py
  completion_poll/{test_v12,test_v13}.py
  test_versioned_experiments.py
```

이전 `runner_proto_pmu_<버전>.py`, `run_pmu_<버전>.py`,
`analyze_pmu_<버전>.py`는 각각 `protocol.py`, `runner.py`, `analysis.py`로 이동했다.
버전은 `interval_v9`, `interval_v10`, `interval_v11a`, `completion_poll_v12`,
`completion_poll_count_v13`이며 마지막 버전의 새 폴더는 `completion_poll/v13`이다.
기존 경로 20개는 제거했다. 테스트는 import 시 실행하는 기존 형식을 유지하므로
unittest discovery 대신 개별 script로 실행한다.

- V13→V12 및 V11A/V13 테스트의 구버전 교차 참조를 새 package 경로로 연결.
- V11A firmware checker 경로를 새 위치 기준으로 계산.
- V12 fixture는 중앙 `host/tests/fixtures/`에 유지하고 읽기 경로만 갱신.
- V13 analyzer subprocess를 새 `completion_poll/v13/analysis.py`로 연결.
- V9~V13 protocol/runner는 동결된 V8 bare `runner_proto` 및 `run_pmu_qual`과
  동일한 예외 클래스를 사용한다. V14/V15의 package protocol 클래스로
  임의 전환하지 않으며, 두 동결 파일 자체는 수정하지 않았다.
- 중복 try/import fallback을 제거하고 직접 실행 시 repo/host 경로를 명시.
  새 회귀 테스트가 새 프로세스에서 예외 동일성과 timeout 거부를 확인한다.

현재 실행 예:

```sh
python3 host/run_offline_tests.py
python3 host/tests/interval/test_v11a.py
python3 host/tests/completion_poll/test_v13.py
python3 -m host.experiments.interval.v9.runner --help
python3 -m host.experiments.completion_poll.v13.analysis --help
```

V12 analysis는 기존과 동일하게 library이며 CLI를 새로 만들지 않았다.
runner 실제 실행은 보드 작업이므로 이번 검증에서 실행하지 않았다.

검증 수준: 단위 및 로컬 프로세스 통합.

- 이동 전·후 standalone checks: V9 49, V10 52, V11A 53, V12 62, V13 62,
  합계 278개 모두 PASS. V12는 summary 대신 PASS 행을 집계했다.
- `python3 -B -m unittest host.tests.test_versioned_experiments`: 2개 OK.
  5개 버전의 frozen 예외 동일성·fake timeout, V13→V12 동일 모듈,
  serial 미로드, CLI 9개의 직접/모듈 `--help` 실행 확인.
- `python3 host/run_offline_tests.py`: 29개 실행 단위 PASS, exit 0.
  unittest 459개, standalone 1,052 checks(기존 774 + 이번 278) 통과.
- 실행 목록의 unittest 및 기존 실행기/import 회귀를 한 프로세스에서 실행:
  464개 OK. standalone 스크립트는 합동 unittest 프로세스에 import하지 않음.
- snapshot AST 비교: 15개 소스의 import/bootstrap 이외 함수·상수 동일.
- 독립 리뷰: 전체 이동 diff 확인 및 /tmp에서 5개 script 직접 실행 성공,
  새 회귀 2개도 통과. 구체 결함 없음.
- Python 3.10 문법 parse, `git diff --check`, 동결 base/transport 원본 비교 확인.

firmware/docs/evidence/provenance/복구 설정은 변경하지 않았다.
펌웨어 빌드, 구형 Python 런타임 및 보드 통신은 검증하지 않았다.
V13 테스트의 선택적인 `/tmp/pmu_completion_poll_count_v13_manifest.json` 입력
검사 조건도 그대로 유지했다. 없는 입력의 검증까지 수행했다고 해석하지 않는다.

## 4단계 A: interval 공통 통계 추출 (2026-09-11)

V9/V10/V11A analysis에서 AST가 동일한 통계 함수 5개를 확인하고
`host/experiments/interval/stats.py`로 옮겼다. 각 analysis는 공개 함수
`series_stats()`를 사용하며 기존 `_median`, `_inclusive_quartiles`, `_mad`,
`_cv`, `_series_stats` 복사본과 사용되지 않게 된 statistics import를 제거했다.
구현 3개와 새 공통 모듈을 합친 줄 수는 1,104→1,015로 89줄 감소했다.

홀수 표본의 median-inclusive quartile, sample standard deviation 기반 CV,
평균 0일 때 None, 빈 입력 거부, 출력 key와 수치형은 기존 구현 그대로다.
manifest/variant/wire 검증과 campaign 분류·보고서 구성은 변경하지 않았다.
동일한 `_decode_hex` 함수도 발견했지만 입력 검증 경계 정리는 다음 변경으로 남겼다.

검증 수준: 단위 및 오프라인 분석 결과 회귀.

- `python3 -B -m unittest host.tests.interval.test_stats`: 6개 OK.
  홀수·짝수 표본, 단일 값/평균 0, 상수 표본, 빈 입력, 입력 불변성 확인.
  손으로 계산한 CV 기대값은 부동소수점 반올림 차이를 고려해 근사 비교한다.
- 기존 interval 테스트가 생성하는 성공 campaign 보고서 6개(버전별 2개)를
  변경 전후 각각 캡처했다. 정렬된 JSON bytes가 모두 동일하다.
  이는 fixture 보고서 비교이며 실제 보드 캠페인을 다시 분석한 것은 아니다.
- 통계 함수 제외 나머지 AST는 호출 이름 변경을 정규화하면 동일하다.
- 독립 리뷰: 전체 diff와 추출 함수 AST 동일성, 보고서 byte 동일성 확인.
  리뷰어도 통계 테스트 6개를 실행했고 구체 결함을 발견하지 못했다.
- `python3 host/run_offline_tests.py`: 30개 실행 단위 모두 PASS, exit 0.
  unittest 465개와 standalone 1,052 checks 통과. 새 통계 테스트도 기본 목록에 포함했다.
- Python 3.10 문법 parse, 공백 검사와 `git diff --check` 수행.

펌웨어 빌드·실보드·다른 Python 런타임은 실행하지 않았다.

## 4단계 B/C 및 6단계 A: 공통 처리·빌드 묶음 (2026-09-11)

사용자 요청에 따라 작업 단위를 묶어 진행했다.

- [4B] interval archive 검증 공통화 → verify: 기존 load 결과·예외 및 보고서 동일.
  `host/experiments/interval/archive.py`가 variant, hex, payload/reread 해시,
  reread 증명, manifest bytes/hash/object 검증을 담당한다. 버전별 의미 검증,
  artifact와 wire 검증은 각 analysis에 남겼다. 중복 구현은 제거했다.
- [4C] V9~V13 통신 공통화 → verify: ACK/COMPLETE 순서, timeout, NACK,
  stale frame, drain, raw 상태 갱신 시점 동일.
  `host/experiments/exchange.py`로 실제 같은 RUN/GET 교환만 추출했다.
  버전별 parser·campaign 정책은 각 runner에 유지했다. 구현 292줄 감소.
- [6A] V14/V15 manifest 생성 공통화 → verify: 실제 Makefile manifest recipe의
  synthetic artifact 출력이 기존과 동일하고 helper 변경 시 재생성.
  `firmware/build_tools/write_completion_manifest.py`로 인라인 Python을 옮겼다.
  helper를 Makefile prerequisite에 추가했다. 컴파일·링크 순서와 gate는 그대로다.
  추출 도중 발견한 shell quoting 회귀는 backtick BUILD 경로로 재현하고 수정했다.

검증 수준: 단위, 오프라인 결과 비교, synthetic artifact 기반 Make recipe 통합.

- archive 단위 12개 통과. 기존 fixture를 이용한 load 560회(거부 13회 포함)의
  반환/예외와 성공 보고서 6개가 변경 전후 byte 동일.
  검증 guard 9개를 각각 비활성화한 in-memory mutation은 모두 테스트가 거부했다.
- exchange 단위 7개 통과. 독립 작업자의 기존/현재 코드 재생 150회에서
  반환·예외·송신 순서·timeout·late count·raw state 동일. 부모가 새 코드와 테스트를
  읽고 통합 실행을 다시 수행했다. archive 독립 리뷰에서도 구체 결함 없음.
- manifest 단위 3개: Q/QS/SQ/S5 출력·자체 해시·dependency,
  누락 artifact 거부, backtick 경로 literal 처리를 확인.
  부모도 이전 Make recipe와 현재 recipe를 실행해 Q 2,907 bytes,
  S5 2,919 bytes의 manifest가 각각 동일함을 확인했다.
- `python3 host/run_offline_tests.py`: **34 실행 단위 모두 PASS**, exit 0.
  unittest **487개**, standalone 기존 1,052 + Makefile 116 checks 통과.
  실행 목록은 전체 module 이름/상대 script 경로를 사용하여 host와 build 검증을 포함한다.
- `python3 -B -m unittest host.tests.test_run_offline_tests host.tests.test_v15_imports`:
  **5개 OK**. 실패 전파 fixture의 자식 실패는 의도된 것이며 외부 unittest가 성공했다.
- Python 3.10 syntax parse와 `git diff --check` 통과.
  V12/V13/V14 helper 3개 digest가 고정값과 일치한다.
  frozen transport, C 입력 및 boundary checker가 HEAD와 byte 동일하다.

로컬 vendor tree/toolchain이 없어 전체 firmware clean build 2회·생성 C 및 바이너리
재현성은 확인하지 않았다. 보드, FVP, 원격 실행도 하지 않았다. 6단계의 이 검증은
미완료이며 synthetic manifest 검증으로 대체됐다고 간주하지 않는다.

## 5단계 착수 결정과 범위

구조 변경의 마지막 묶음인 **5단계 검증기 분리와 로컬 재검증**을 완료했다.
별도로 6단계의 실제 빌드 환경 검증이 남아 있다. V9~V15 구조화와 공통화는 완료했지만 동결·역사 영역을
일괄 이동하거나 저장소 전체를 동일한 구조로 전환한 것은 아니다.

5단계는 기존 동결 경로를 보존하고 **별도 후속 검증기 버전 및 재자격 경로**를
추가하기로 사용자가 승인했다. 별도 브랜치에서 진행한다. 분리 근거는
`firmware/Selftest_pmu_diag/check_s5_only_boundary_image.py`의
`HELPER_DEPENDENCIES`/`verify_helper_identity`: V12/V13/V14 파일 바이트가
고정되어 있어 단순 분리도 V15 identity 거부를 유발한다.
기대 해시만 바꾸어 통과시키는 방식은 사용하지 않는다.

승인된 작업 묶음:

1. 후속 checker 의존성 identity와 기존 자격 경로 분리
   → verify: 기존 helper 해시와 기존 실행 결과 유지.
2. lexical/address/source contract/ELF/image contract/CLI 책임별 추출
   → verify: 기존 fixture 판정·rule ID 동일.
3. 전체 모듈 대상 trace/mutation 검증 및 V15 의존성 재검증
   → verify: mutation RED와 downstream 테스트 통과.

기존 efficacy suite는 `gate.__file__` 한 파일의 AST·trace에 의존한다.
파일만 분리하면 검사 범위를 누락할 수 있으므로 3번을 함께 수행해야 한다.

분기 당시부터 존재한 미추적 사용자 파일은 변경하지 않았다:
`docs/paper/context/EXTERNAL_REVIEW_20260909_COVERAGE.md`, `docs/presentation/`.
기존 docs/evidence/provenance/board-config의 tracked diff는 없다.
`codex-mark-used`는 PATH에서 찾지 못했으며 별도 설치하지 않았다.
기존 소스·설정 변경은 `refactor/source-config`의 `10dd809`에 커밋했다.
사용자 문서는 해당 커밋에서 제외했다. 후속 작업은 이 커밋에서 분기했다.


## 5단계 구현: 별도 후속 검증기 (2026-09-11)

`refactor/gate-successor`는 완료된 소스·설정 정리 커밋 `10dd809`에서 분기했다.
기존 frozen 검증기/테스트/Makefile 실행 경로는 유지했다.

구현 구조:

- `firmware/gates/completion_visibility/`: constants/errors, c_lexical/c_addresses,
  source_loops/source_storage/source_cleanup/source_confinement/source_contracts,
  elf_analysis/image_contracts/cli의 12개 구현 모듈. 공개 package API는 검증
  진입점만 제공한다. 내부 586개 정의는 테스트 전용 GateView로 접근한다.
- `firmware/gates/identity.py`: 후속 버전과 전체 코드 바이트 identity.
  12개 모듈, package/CLI 진입점, identity/S5 detector, frozen V12/V13 및
  transitive `check_pmu_qual.py`를 포함한 20개 파일을 기록한다.
  보관한 caller snapshot과 다른 파일·필드·digest는 거부한다.
  후속 상태는 `UNQUALIFIED_SUCCESSOR`이며 snapshot 생성 자체가 자격 부여는 아니다.
- `firmware/gates/s5_boundary.py`: 기존 S5 판정을 새 모듈에 연결한 별도 경로.
  `expected_identity`를 명시적으로 받아 이미지 해석 전에 대조한다.
- `firmware/gates/tests/`: 기존 fixture 호출 순서·개수 재사용, 다중 파일
  AST/source/trace 검사, 실제 owner의 alias 계측, identity·S5 비교와 code mutation.

현재 실행 경로:

```sh
python3 -m firmware.gates.completion_visibility --help
python3 firmware/gates/completion_visibility/__main__.py --help
python3 -B -m unittest firmware.gates.tests.test_structure firmware.gates.tests.test_identity firmware.gates.tests.test_s5_boundary firmware.gates.tests.test_mutations
python3 -B -m unittest firmware.gates.tests.test_completion_visibility
```

CLI의 기존 variant/fixture/ELF 옵션과 판정 내용은 유지하며, 출력 JSON에는
`checker_identity`를 추가한다. 기존 qualified evidence와 동일한 결과로
오인하지 않도록 새 식별 정보와 `UNQUALIFIED_SUCCESSOR`를 기록한다.

검증 수준: Python 단위·프로세스 통합, 기존 fixture 회귀, 코드 mutation 및
실제 저장된 disassembly fixture의 downstream 비교. 전체 firmware 빌드/보드 검증은 아니다.

- `python3 -B -m unittest firmware.gates.tests.test_structure firmware.gates.tests.test_identity firmware.gates.tests.test_s5_boundary firmware.gates.tests.test_mutations`:
  **13 tests OK** (6.7초). 전체 586개 정의 집합과 AST 동일 확인
  (의존성 로더·출력 provenance 2개 함수만 의도 변경), acyclic imports,
  repo 밖 direct CLI와 module CLI, 실제 CLI JSON의 identity/원래 판정 동일성 확인.
- identity의 20개 파일 각각 누락/byte 변조 거부, frozen dependency는 재캡처 시에도
  변조 거부. caller identity 필드 삭제와 qualified 승격 거부.
- S5 정상 fixture 판정은 기존과 identity 필드 제외 동일.
  mask/QREAD/QSIZE/심볼 누락/STATUS 재읽기의 5개 입력 변이 오류 메시지도 동일.
  S5.nm은 심볼 존재만 확인하며, 원래 boundary API에 없는 nm 분석을 주장하지 않는다.
- **36개 규칙의 코드 mutation**: 각 규칙의 raise를 메모리에서 비활성화하고
  실제 owner 및 import alias를 함께 교체했을 때 기존 targeted fixture가 모두 RED.
  소스 파일은 수정하지 않았다. 정상 상태의 각 negative가 정확한 rule에 도달함도 확인.
- `python3 -B -m unittest firmware.gates.tests.test_completion_visibility`:
  **1 outer test OK** (151초), 내부 **1,241 checks PASS** count guard 확인.
- `python3 -B -u firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`:
  기존 frozen suite도 **1,241 checks PASS**, exit 0.
- 초기 전체 실행은 다중 파일 trace가 0을 기록해 실패했다. fixture의 sys.path가
  `Selftest_pmu_diag/..` 경로를 추가하여 code.co_filename이 정규화 경로와 달랐다.
  원인을 직접 재현하고 실제 module.__file__ 별칭을 trace map에 등록했다.
  수정 후 efficacy 7개 모두 통과: 실행 위치 3,313개, 선언된 vacuity 18개 유지.
  전체 suite도 위와 같이 다시 통과했다. 실패를 제외한 일부 결과만 완료로 보고하지 않았다.
- 독립 리뷰: import/global 참조, identity 오류의 GateError 변환,
  전체 module inventory/trace, 실제 owner alias 계측 확인. 구체 결함 없음.
  리뷰어도 structure 4개(당시), identity/S5 7개, mutation 36개, efficacy 7개를 실행했다.
- `git diff --cached --check` 통과. 추출된 기존 공백 36줄을 정리했고
  정리 전후 AST 동일성을 별도 확인했다. 기존 frozen 파일·문서의 diff는 없다.

남은 작업은 적격 빌드 환경의 clean build 및 생성 C/바이너리 재현성 검증이다.
현재 로컬에는 필요한 vendor tree/toolchain이 없어 실행하지 않았다.
따라서 production Makefile 연결이나 기존 qualified evidence 교체는 하지 않았고,
후속 identity의 `UNQUALIFIED_SUCCESSOR` 상태를 유지한다.
이번 브랜치는 원격에 push하지 않았다.


## 환경 디렉터리 통합 (2026-09-11)

사용자가 승인한 목표 구조에 따라 `refactor/environment-layout`를
검증기 완료 커밋 `bc126a1`에서 분기했다. 이 변경은 환경 파일 배치와
경로 안내 정리이며 host/firmware 코드 및 동결 provenance 변경이 아니다.

1. 보드 current/history, 빌드 archive, 호스트 환경으로 27개 파일 이동
   → verify: 이동 전후 파일 수와 SHA-256 비교, 옛 디렉터리 제거 확인.
2. 복구 manifest·ignore 규칙·README 및 MIRROR의 경로 안내 갱신
   → verify: 새 상대 경로, 아카이브 ignore, 현재 안내의 옛 경로 잔존 검사.
3. 동결 영역·사용자 파일 보존과 결과 기록
   → verify: 기준 커밋 대비 보호 영역 diff 없음, 최종 diff 공백 검사.

보드 과거 설정의 동일한 바이트 파일도 서로 다른 사건 이름을 유지한다.
불완전한 devcontainer 설정을 포함한 과거 컨테이너 프로젝트는 실행 설정으로
승격하거나 수정하지 않고 `archive/` 아래에 원문 그대로 보관한다.


환경 통합 결과: **완료**.

```text
environment/
  README.md
  board/
    RECOVERY_ARCHIVE.sha256
    current/                    5개 설정
    history/                    4개 과거 설정
  build/
    BUILD_ENVIRONMENT.yaml
    archive/
      container-build-context/  13개 보관 파일
  host/
    HOST_RESTORE.md
    host-python.txt
    serial-bindings.yaml
```

- 기존 tracked 파일 27개를 모두 이동했다. 기존 세 디렉터리는 제거했다.
  같은 이름의 호환용 디렉터리·symlink는 새로 만들지 않았다.
- 이동한 26개 파일의 SHA-256은 이동 전과 동일하다. 빌드 YAML만 경로 5곳
  (작업 트리 아카이브, 복구 명령, 벤더 배포본, 컨테이너 보관본, firmware overlay 안내)을
  바꿨다. 기존 원문에 이 5개 치환만 적용한 결과와 전체 문자열이 같음을 확인했다.
  기록된 hash·version·복구 실험 결과는 바뀌지 않았다.
- `.gitignore`의 외부 아카이브 경로, README 및 `docs/MIRROR.md`의 경로 안내를 갱신했다.
  문서 수정은 이 이동에 필요한 안내에 한정했다. 대화 원문·논문·evidence·provenance는
  수정하지 않았다. 동결 기록의 옛 경로 대응은 `environment/README.md`에 정리했다.
- Git에 없던 두 `.tgz` 아카이브는 새로 확보하거나 생성하지 않았다.
  향후 배치 위치는 `environment/build/archive/`이며 기존 제외 규칙을 이 위치로 옮겼다.

검증 수준: 파일 무결성, 정적 경로/ignore/셸 문법 검사.

- Python 검증: 목적지 27개 존재, 옛 파일·디렉터리 부재, SHA-256 및 YAML 5개 치환 비교 PASS.
- `rg` 및 Python 검증: 현재 README/MIRROR/ignore/YAML에 옛 경로 없음,
  새 환경 README의 상대 링크 모두 존재. 역사 기록과 이전 경로 대응표의 옛 이름은 의도적으로 유지.
- `git check-ignore -q --no-index`: 외부 아카이브 2개·보관본 .env·build 산출물은 제외,
  .env.example·run_sim.sh는 추적 가능 — 6개 확인 PASS.
- `bash -n`: 보관된 shell script 3개 PASS. 스크립트 자체를 실행하지 않았다.
- 기준 커밋 대비 firmware/host/provenance/evidence/docs/paper/docs/presentation diff 없음.
- `git diff --cached --check` PASS.

소스와 실행 동작이 바뀌지 않아 전체 펌웨어/호스트 회귀 테스트는 반복하지 않았다.
빌드·컨테이너·보드 실행도 하지 않았다. 실제 빌드 환경의 자격 검증은 앞 단계와 같이 남아 있다.

## 공통 MLEK 캠페인 실행기 (2026-09-11)

사용자 목적을 명확히 반영: 설치된 모든 MLEK 모델 × 설정된 모든 보드/FVP ×
요청 옵션 조합을 같은 측정·판정 계약으로 처리한다. 메모리 제약은 조합별 결과이며
조합을 사전에 누락하거나 전체 캠페인을 성공으로 위장하지 않는다.
`refactor/unified-mlek-campaigns`를 환경 통합 완료 커밋에서 분기했다.

1. 기존 실행조건 audit 및 공통 계약/전체 matrix 정의
   → verify: 모델·target·옵션별 모든 요청 조합에 안정적인 ID와 상태가 존재.
2. Vela/MLEK 빌드, FVP, MPS4 adapter 연결
   → verify: fake executable/serial 환경에서 실제 모델 전달, 종료코드, timeout,
   원본 로그 보존, capture-before-reset 및 finally 복원 검증.
3. 공통 결과 판정과 재개·오류 분리
   → verify: 메모리 오류 뒤 다음 조합 실행, 실패 은폐 없음, stale 결과 재사용 거부,
   실행 중단 후 남은 조합 상태 보존, 복원 실패 target 격리.
4. 사용 경로/역사 경로 분류 및 미사용 코드 정리
   → verify: 동결 해시·문서/evidence 원본 보존, 현재 실행기로부터 legacy 의존 없음.

기존 조건은 통합돼 있지 않다: stage1/2/3은 anchored74개 조합·고정arena/옵션,
보드는MPS4/U85 한 기종이며 formal probe 수정본이 현재 저장소에 없고,
archive simulator는 입력모델 미주입 및 build/FVP 실패 은폐가 있다.
원본 캠페인 증거는 그대로 보존하고 후속 유지보수 코드를 host/campaigns에 둔다.

### 로컬 구현·검증 결과

- 단계 1~3의 로컬 구현 완료: `host/campaigns`의 plan/run/resume와
  `environment/campaigns/mlek.example.json`. 모델 발견은 설치된 resources의
  전체 `.tflite`(기존 Vela 출력 제외)이며, 원격 미다운로드 모델까지 포함했다고
  간주하지 않는다. FVP 6종과 현재 MPS4/U85-1024 adapter를 연결했다.
- 최초 계획에 모든 모델×target×variant×MAC을 기록한다. 미지원 MAC, 메모리
  부족, 빌드/실행 실패, 측정 오류는 각각 terminal 상태이며 다음 cell로 진행한다.
  보드 복구 실패 시 동일 장치의 다른 target 별칭까지 격리한다.
- 선택 모델→Vela→CMake MODEL_PATH→AXF/배포파일 hash를 연결한다. 공통 Git
  source revision, Vela/CMake/실제 C/C++ compiler identity, 설정·toolchain identity를
  기록·비교한다. CMake의 실제 cache와 요청 조건도 비교하며 override 우회를 거부한다.
- raw UART·명령·로그 보존, 재개 시 계획/성공 증거 검증, lock 이후 상태 읽기,
  예외·중단 attempt 상태 확정, serial by-id 원래 경로 보존을 구현했다.
- 단계 4 완료: 미사용 `host/bringup/*.py` 25개를 `host/legacy/bringup/`으로
  바이트 동일하게 이동했다. 동결 serial-bindings의 원래 경로는 수정하지 않고
  legacy README에 대응을 기록했다. V9~V15·root PMU 도구는 현재 consumer와
  동결 qualification 의존성 때문에 reference 경로로 유지한다.

실행한 검증:

- `python3 host/run_offline_tests.py`: **39 실행 단위 PASS, 0 FAIL**.
- 최종 campaign 5개 unittest module 및 `host.tests.test_run_offline_tests`:
  **50 tests PASS** (runner 검증의 의도적인 child failure를 정상 검출).
- 실제 CLI plan: 임시 모델 8개×7 targets×2 variants×7 MACs = **784 cells**.
  실제 CLI run: 미지원 MAC cell 보존 및 exit **1**, 도구/보드 접근 없음.
- 기존 FVP UART 2개를 새 parser로 읽어 TOTAL 4,115,068 / 49,086 확인.
  보드 역사 로그의 문자 그대로 `^M` 표기는 raw UART와 달라 새 parser가 거부한다.
- compileall PASS, bringup 25개 HEAD 대비 byte 동일; 동결 firmware/docs/evidence/
  provenance 파일 변경 없음. 독립 검토 후 발견된 회귀를 수정했다.

남은 실환경 검증(완료 아님): 이 Mac의 PATH에 Vela/FVP가 없고 `/opt/arm` SDK가
없다. 새 실행기를 실제 MLEK checkout·FVP 6종·MPS4에 적용한 전체 matrix 결과는
아직 없다. stock runner 입력 정책을 유지하지만 플랫폼 간 실제 입력 tensor bytes의
동일성은 검증하지 않았다. 따라서 **완전히 같은 입력을 사용한 전체 실험이 이미
수행·보장됐다고 주장하지 않는다**. 실제 설치의 source/compiler/config identity,
FVP capability/TA, MPS4 이미지 layout을 확인하고 matrix 실행과 입력 동일성 검증을
마쳐야 실환경 qualification을 완료할 수 있다.
