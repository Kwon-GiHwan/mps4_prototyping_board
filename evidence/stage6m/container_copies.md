# 컨테이너 사본 불일치 22개 — 사용 여부와 원본 (Stage 6-M Phase 0, 읽기만 함)

- 조사일 2026-11-16. `sync.sh check`와 같은 목록(`/work/mps4_host` 호스트 파일, `/work/selftest` 펌웨어 파일)을 컨테이너에서 sha256으로 다시 읽었다.
- 결과: 불일치 22개 = **누락 12개** + **저장소의 예전 버전과 정확히 같은 낡은 사본 10개**. 저장소 어느 버전과도 다른 파일은 없다.
- Stage 6-M 사용 여부: **사용하지 않는다.** 컨테이너 작업은 `/work/s6b_host`(쓰는 6개 파일을 저장소와 sha256 대조: 모두 같음)와 `/work/s6m`에서만 한다.
- 지시에 따라 고치거나 동기화하지 않았다. `/work/selftest`는 펌웨어 빌드 트리이며, 이번 분석은 펌웨어를 빌드하지 않는다.

| 컨테이너 경로 | 상태 | 일치하는 저장소 버전 | 저장소 최신 변경 |
|---|---|---|---|
| `/work/mps4_host/host/container/stage4ao_models.py` | 누락 | — | 58165d6 2026-11-15 |
| `/work/mps4_host/host/container/stage4aoe_models.py` | 누락 | — | eab77da 2026-11-15 |
| `/work/mps4_host/host/container/stage4c_models.py` | 낡은 사본 | 93b356b 2026-11-11 | d29ed54 2026-11-14 |
| `/work/mps4_host/host/container/stage4wd_models.py` | 누락 | — | 6a7045b 2026-11-15 |
| `/work/mps4_host/host/container/stage6b_amendment_b.py` | 누락 | — | 22a89cf 2026-11-15 |
| `/work/mps4_host/host/container/stage6b_models.py` | 누락 | — | 0c4bf4c 2026-11-15 |
| `/work/mps4_host/host/container/stage6b_revision_a_models.py` | 누락 | — | 37b6268 2026-11-15 |
| `/work/mps4_host/host/container/stage6be1_models.py` | 누락 | — | 3a83175 2026-11-15 |
| `/work/mps4_host/host/container/stage6be1r_models.py` | 누락 | — | 5094e74 2026-11-16 |
| `/work/mps4_host/host/container/stage6br_vela.py` | 누락 | — | 5c801f7 2026-11-15 |
| `/work/selftest/driver_runner/tests/host_sim.c` | 낡은 사본 | 717ba5b 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/tests/placement_probe.c` | 누락 | — | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/include/placement.h` | 누락 | — | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/include/probe.h` | 낡은 사본 | c1b9b79 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/include/record.h` | 낡은 사본 | 717ba5b 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/include/runner.h` | 낡은 사본 | 83398c7 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/include/workload.h` | 낡은 사본 | 65cf963 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/src/hooks.c` | 낡은 사본 | 717ba5b 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/src/placement.c` | 누락 | — | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/src/platform.cc` | 낡은 사본 | c1b9b79 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/src/runner.c` | 낡은 사본 | 83398c7 2026-11-10 | 70090f1 2026-11-14 |
| `/work/selftest/driver_runner/use_case/pmu_runner/src/workload.c` | 낡은 사본 | 65cf963 2026-11-10 | 70090f1 2026-11-14 |

- 호스트 쪽(`/work/mps4_host`): 누락 9개(Stage 4AO 이후 컨테이너 스크립트), 낡은 사본 1개(`stage4c_models.py`). 해당 스크립트들은 단계마다 `/work/s6b_host` 같은 별도 경로에 복사해 썼다(E1-R preflight에서 그 경로를 대조함).
- 펌웨어 쪽(`/work/selftest`): 누락 3개, 낡은 사본 9개, 모두 driver runner 소스다. 보드 이미지 `70090f1`이 이 트리에서 빌드됐는지는 이번에 확인하지 않았다.
