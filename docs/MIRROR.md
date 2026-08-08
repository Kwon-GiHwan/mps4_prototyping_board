# mps4_testing

MPS4 (Corstone SSE-320 / Cortex-M85 / Ethos-U85, FI101 이미지) 실보드 계측 작업물 모음.
ARM Ethos-U85 per-layer profiling 논문의 R4-C·R5-C 실험을 위한 펌웨어·호스트 툴링과
qualification 증거.

## 이 디렉터리의 위치

**여기는 사본이다. 실행 환경이 아니다.**

| 대상 | 권위 있는 위치 |
|---|---|
| 호스트 툴링 실행 | `gihwan:/home/gihwan/mps4/` |
| 펌웨어 빌드 | 컨테이너 `benchmark-runner:/work/selftest/` |
| 프로젝트 맥락·계약 | `~/Documents/Obsidian/wiki/projects/npu-benchmark.md` |
| 플랫폼 바이너리 (113M) | `~/Documents/Projects/personal/mps4_board_recovery/` |

**보드 복구 아카이브는 별도 디렉터리다.** `fi101_00.bit`(102M) 등 벤더 플랫폼 바이너리는
여기 없다 — 소스 트리에 넣기에 크고, Arm FI101 재배포 조건이 미확인이다. 해시와 포인터는
`board-config/RECOVERY_ARCHIVE.sha256`에 있고, 실물과 `FI101_BOARD_RECOVERY_MANIFEST.yaml`은
위 경로에 있다. **미러만 복원하면 보드를 재구성할 수 없다.**

작업을 이어갈 때는 **위키의 「▶ 다음 세션 시작점」 블록을 먼저 읽는다.** 현재 단계,
서버 경로, 배포본 해시, 착수 순서, 반복하면 안 되는 함정이 거기에 있다.

여기서 코드를 고쳐도 서버에 반영되지 않는다. 수정은 서버/컨테이너에서 하고 사본을
갱신하는 방향이 맞다 — 반대로 하면 두 개의 진실이 생긴다.

## 구성

```
host/            호스트 툴링 (Python, pyserial)
  runner_proto.py    프레임 인코더/디코더, CRC32, serial transport, 측정 ABI 파서
  mcc_harness.py     MCC 콘솔 트랜스포트 (LAR 주소, SD, REBOOT)
  do_reboot.py       MCC REBOOT + DDR self-test / CPUWAIT 확인
  capture_mcc.py     MCC 콘솔 캡처
  capture_all_uart.py  4포트 동시 캡처 (bring-up 증거 생성기)
  tests/             단위 시험(보드 불필요) + 보드 게이트 11종
  bringup/           2026-08-03 하드웨어 bring-up 진단 25종 (역할 종료, 이력용)
  patches/           호스트 툴 파생 이력 (일회성, 이미 적용됨)

evidence/        실험 원시 증거
  boot-capture-logs/   4포트 UART 원시 캡처 18세트 — SODIMM 접촉 불량 원인 규명의
                       근거 (실험 A/B/C, 재장착 전후, memtest7, official-ti3-final).
                       .raw = 바이트 그대로, .timeline = 타임스탬프 부착
  early-boot-logs/     초기 부팅·전원 사이클 로그 10건 (캡처 체계 정립 이전)

board-config/    실험 시점의 MPS4 SD 설정 스냅샷
  config.txt.backup-uartmode0 / config.txt.pre-verbose
  images.txt.operating-ti2 / images.txt.pre-verbose

firmware/        펌웨어 소스. 마일스톤 순서:
  Makefile.gcc           GCC golden baseline (armclang 스캐터 → GNU 링커 포팅)
  Makefile.rawrx         raw UART RX 시험
  Makefile.runner        functional runner v1
  Makefile.measure       measurement-clean 러너 (MEASURE_SEQ 이미지)
  Makefile.pmu           PMU candidate (PROFILE=clean/wrapped)
  Selftest/
    raw_rx_main.c        raw RX 시험 러너
    runner_v1_main.c     functional runner v1
  Selftest_measure/      ← 보드 인수를 통과한 MEASURE_SEQ의 소스
    runner_measure_main.c     측정 경계·상태기계·측정 ABI·stale-output 차단
    check_measure_symbols.py  denylist 콜그래프 검사 (위반 시 빌드 실패)
  Selftest_pmu/          ← 현재 작업 중인 PMU candidate
    runner_pmu_main.c    런타임 instrumentation_mode (OFF / END_ONLY)
    gen_npu_pmu_regs.py  벤더 헤더에서 레지스터 기하 추출 (--generate / --check)
    npu_pmu_regs.h       생성물. 직접 편집 금지
    nc_gen.py            생성기 음성 게이트 13종 + 양성 대조 1종.
                         변조 헤더를 생성만 하는 게 아니라 실제로 컴파일해
                         _Static_assert 백스톱까지 실증한다
  LinkScripts/
    lnk.measure.overlay.ld   내가 추가한 오버레이 (동결 lnk.ld.S를 안 건드리려고)
    lnk.ld.S                 벤더 원본, FROZEN — 수정 금지
    lnk.sct                  armlink 스캐터 원본. lnk.ld.S 포팅의 기준
    region_defs.h / region_limits.h    벤더 원본
  patches/               펌웨어 파생 이력 (일회성, 이미 적용됨).
                         PMU 트리가 MEASURE 사본에서 어떻게 만들어졌는지의 기록

build-env/       빌드 환경 재현
  BUILD_ENVIRONMENT.yaml   툴체인·컨테이너 digest·MLEK 커밋·기대 출력 해시.
                           restore drill 결과와 컨테이너 재현 불가 사실도 여기
  selftest-worktree.tgz    실제 빌드 트리. **복구는 이걸로 한다** (두 이미지 비트 재현)
  fi101-selftest-src.tgz   벤더 배포본. UPSTREAM REFERENCE ONLY — 빌드 안 됨
  container-build-context/ Dockerfile 등. 단 현재 이미지를 재현하지는 못함

HANDOFF-snapshot.md  위키 프로젝트 페이지 사본. 최상단 「다음 세션 시작점」 블록이
                     작업 재개의 1차 아티팩트인데 Obsidian 에만 있었다. 스냅샷이며
                     원본이 권위 — 둘이 다르면 Obsidian 쪽이 맞다
session-memory/      세션 메모리 파일 사본 (프로젝트 단계·보고 규율)

host-environment/  호스트 실행 환경 (코드 수정 없이 기록만)
  HOST_RESTORE.md      인터프리터 분리, pyserial 출처(apt python3-serial), 미포함 항목
  host-python.txt      원시 조사 결과
  serial-bindings.yaml FTDI 시리얼 하드코딩 29곳 위치

provenance/      이미지별 증거 (BIN 포함)
  FI101_RUNNER_V1_MEASURE_SEQ/     Measurement Candidate. MANIFEST/SHA256SUMS/
                                   qualification 스크립트·raw log/build_closure
  FI101_MEASURE_TESTHOOKS/         stale-path 검증 전용. 성능 데이터 부적격
  FI101_RUNNER_V1_PMU_CANDIDATE/   현재 SD 배포본. clean/ + hooks/
  FI101_RUNNER_V1_MEASURE_ABI/     중간 이미지 (MEASURE_SEQ의 전신). clean/ + wrapped/
  FI101_RUNNER_V1_MEASURE_PRE_ABI/ 중간 이미지 (ABI 도입 전). clean/ + wrapped/
  MEASURE_PROVENANCE.txt           MEASURE 계열 초기 빌드 provenance
  earlier-images/                  이전 이미지들의 PROVENANCE.txt·부속물
```

## 의도적으로 넣지 않은 것

서버·컨테이너 전수 대조 결과, 미러에 없는 것은 아래가 전부이며 모두 의도적 제외다.

| 대상 | 이유 |
|---|---|
| `fi101-selftest-src.tgz` | 벤더 FI101 Selftest 배포본. 내 산출물이 아니고 상류 원본 |
| `selftest_user_guide.md` | 벤더 문서 |
| `boot-capture-logs-20260803.tar.gz` | `evidence/boot-capture-logs/`를 압축한 중복본 |
| `runner/selftest/` (9.8M) | 벤더 Selftest 소스를 서버에 풀어둔 사본. `fi101-selftest-src.tgz`와 동일 내용 |
| `sd-backup/` (103M) | SD 카드 전체 백업. 복구 기준점이지 구현물이 아니다 |
| `venv/` · `__pycache__/` | 실행 환경 부산물 |
| `FI101_GCC` · `FI101_OFFICIAL` · `FI101_RAWRX` · `FI101_RUNNER_V1`의 BIN | GCC/RAWRX/RUNNER_V1은 여기 소스+Makefile로 재생성 가능, OFFICIAL은 벤더 배포본. 부속물(`lnk.ld`, `Makefile.gcc`, `runner_v1.map`)은 `earlier-images/`에 넣었다 |

필요하면 `gihwan:/home/gihwan/mps4/` 또는 컨테이너에서 가져온다.

## 소스 무결성 (교차 검증 완료)

`firmware/` 아래 MEASURE 계열 5개 파일이 MEASURE_SEQ manifest의 동결 해시와 **5/5 일치**함을
확인했다 — `runner_measure_main.c` · `check_measure_symbols.py` · `lnk.ld.S` ·
`lnk.measure.overlay.ld` · `Makefile.measure`. 즉 여기 있는 소스가 보드 인수(16/16, 15/15)를
통과한 그 이미지를 만든 소스다.

## 숫자들이 각각 무엇을 세는가

서로 다른 것을 세므로 분모가 다르다. 숫자 자체보다 무엇을 세는지가 중요하다.

| 숫자 | 대상 |
|---|---|
| 미러 파일 수 | 이 디렉터리의 전체 파일. 작업하면 계속 변한다 |
| `SHA256SUMS` | **한 이미지 디렉터리 안**의 무결성 루트. 미러 전체가 아니다 |
| qualification 항목 | `MANIFEST.yaml`이 선언한 동결 증거 해시. 100% 일치 필수 |
| working snapshot | 동결 시점 호스트 도구 사본. 작업 사본과의 차이는 정보성 |
| board recovery | 별도 아카이브의 플랫폼 바이너리·설정 (`board-config/RECOVERY_ARCHIVE.sha256`) |

## 무결성 확인

```sh
cd provenance/FI101_RUNNER_V1_MEASURE_SEQ
shasum -a 256 -c SHA256SUMS        # 33/33 OK (2026-08-08 확인)
```

`verify_manifest.py`는 서버·컨테이너 경로를 참조하므로 **서버에서 실행해야 한다**
(`gihwan:/home/gihwan/mps4/FI101_RUNNER_V1_MEASURE_SEQ/`).

현재 상태 (2026-08-08 서버 재실행 확인): **QUALIFICATION 68/68 passed ·
WORKING SNAPSHOT 10/10 intact**. 이전에 기록했던 74/75 드리프트는 manifest를
2-class(동결 qualification / working tooling snapshot)로 분리해 해소됐다 — 계속 변하는
작업 파일은 snapshot class로 옮겨 정보성으로만 비교한다.

**주의**: working snapshot의 `10/10 intact`는 동결 시점 호스트 도구 사본의 무결성
수치다. `FI101_MEASURE_TESTHOOKS`의 "10/10" (보드 실험 결과 주장)과는 다른 것을
센다 — 후자는 raw artifact 부재로 재현 증거가 불완전하다 (아래 이미지 자격 표 참조).

## 이미지 자격 (중요)

| 이미지 | 상태 |
|---|---|
| `FI101_RUNNER_V1_MEASURE_SEQ` | Functionally Qualified / Measurement **Candidate**. A/B/C 오염 게이트 전까지 성능 데이터 **보류** |
| `FI101_MEASURE_TESTHOOKS` | stale-path 검증 아티팩트. 성능 데이터·A/B/C 어느 쪽에도 **부적격**. "10/10"은 previously reported이며 **raw artifact 부재 — 재현 증거 불완전** |
| `FI101_RUNNER_V1_PMU_CANDIDATE` | 현재 SD 배포본. **PMU 수치 폐기**, 비-PMU 회귀 증거만 유효 |
| `FI101_RUNNER_V1_MEASURE_ABI` | MEASURE_SEQ에 의해 **대체된 중간 이미지**. 실험에 사용 금지 |
| `FI101_RUNNER_V1_MEASURE_PRE_ABI` | ABI 도입 전 중간 이미지. 실험에 사용 금지 |

이미지 식별은 세 BIN의 조합으로 한다. TESTHOOKS와 MEASURE_SEQ는 `DDR.BIN`이 바이트
동일하므로 **DDR 해시 하나로 성능 적격성을 판단하면 안 된다.**

## 주의

- `Selftest_pmu/npu_pmu_regs.h`는 생성물이다. 값을 손으로 고치면 `--check`가 실패한다.
  레지스터 비트 위치를 유도하지 말고 생성기가 추출하게 둘 것 — 유도한 비트 하나가
  wrap된 샘플을 유효로 통과시킬 뻔했다.
- `provenance/` 아래 파일은 동결 증거다. 수정하면 해당 이미지의 qualification이 무효다.
- `bringup/`은 SODIMM 접촉 불량 진단 시절 스크립트다. 현재 워크플로에서는 쓰지 않는다.
