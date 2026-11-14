# Stage 4 보완 — F1–F7 구현과 보드 없는 검증 (2026-11-14)

Owner 지시 "Stage 4 보완 — DRAM/SRAM 배치 비교를 위한 Runner 구현 및 사전 검증"에 따른 기록이다.
- **허용 범위:** 소스 수정, 로컬 빌드, 정적 검증, 테스트.
- **하지 않은 것:** 보드 배포, 보드 실행, PMU 측정, 계약 동결.
- **측정 조건 표기:** 보드 수치는 이 문서에 새로 없다. 인용한 기존 값은 모두 TA profile 1, 이미지 `83398c7`, Stage 4 conv_base(boot 330)의 값이다.

**최종 판정: `READY_FOR_BOARD_VALIDATION`**
- 구현과 로컬 검증을 통과했다.
- 보드에서만 확인할 수 있는 항목은 §6에 정의했다.
- 이 판정은 보드 SRAM 접근이나 B의 출력 정합성을 확인했다는 뜻이 아니다.

## 1. F1–F7 구현 내역

모든 변경은 `firmware/driver_runner`와 `host/` 안에 있다. 다음은 수정하지 않았다: MLEK 트리, Ethos-U core driver, Vela 설정, 명령 스트림, TA profile, PMU 이벤트.

| # | 내용 | 파일 |
| --- | --- | --- |
| F1 | DRWL 헤더 word 7 `placement`: 0 = DDR(기본), 1 = SRAM. 그 밖의 값은 거부한다(펌웨어 load 코드 0x107, host `ValueError`). DRWL version 1은 유지한다. 이전 blob은 모두 word 7 = 0이다 | `workload.h/.c`, `host/lib/drwl.py`(`with_placement`) |
| F2 | B의 arena = (fast memory 끝을 64 KiB로 올림) + (DDR arena − model_base). conv_base에서는 `0x310615C0`이고 하위 16 bit가 A와 같다. 2 MiB가 `0x31400000` 안에 들어가지 않으면 `LOAD_SRAM_NO_ROOM`(0x600)으로 거부한다. fast memory 끝은 런타임에 `ethosu_drv`에서 읽고, fast memory가 SRAM 밖이면 빈 창으로 처리한다 | `placement.h/.c`, `runner.c`(`arena_of`), `platform.cc`(`sram_window`) |
| F3 | strong `ethosu_config_select`: MLEK Dedicated_Sram 표(QCONFIG 3, region 0·1 = 3, 2–7 = 1, 범위 밖은 region 0 값)를 그대로 쓴다. placement 1일 때만 index 1 → 0(SRAM 포트)이다. placement는 load가 성공할 때만 설정하고, load를 시작할 때 DDR로 되돌린다 | `hooks.c`, `placement.c` |
| F4 | 완료 IRQ에서 PMU snapshot을 먼저 읽은 뒤 REGIONCFG(0x3C)와 QCONFIG(0x1C)를 읽는다. record schema 4는 끝에 `regioncfg_irq`, `qconfig_irq`, `placement`를 추가하고 flag `REC_REGIONCFG_MATCH`(bit 6)를 둔다. host는 schema 3(기존 기록 95 words)과 4(98 words)를 모두 읽는다. schema 4의 validity에는 `regioncfg_match`가 추가된다 | `record.h`, `probe.h`, `hooks.c`, `runner.c`, `host/lib/record_v2.py` |
| F5 | 다음은 LOAD_MODEL_END 때 두 조건 모두에 적용한다. RUN 때는 하지 않는다. (1) arena 전체에 주소 기반 패턴과 그 보수를 각각 쓰고, D-cache clean+invalidate 뒤 되읽는다. 실패하면 0x701/0x702다. (2) 모델 init 뒤 OFM 텐서를 0x5A로 오염시킨다. (3) IFM을 입력 텐서에 복사하고 sync 뒤 되읽는다. 실패하면 0x800이다 | `runner.c`(`prepare_io`), `placement.c`(`placement_mem_check`), `platform.cc`(`dcache_sync`) |
| F6 | 빌드 gate를 추가했다. (a) `ethosu_config_select`가 runner의 strong 정의(T)이고 `ethosu_dev_run_command_stream`이 호출한다. (b) SRAM 범위의 심볼은 `cache_arena 0x31000000 0x60000` 하나뿐이고, 섹션은 `.sram` 하나뿐이다 | `host/container/build_driver_runner.sh` |
| F7 | host 측: B blob 생성(`stage4p.py make-b`), Gate B(`gate-b`), 분석(`analyse`)을 만들었다. 보드 스크립트는 RUN마다 placement와 REGIONCFG_MATCH를 확인하고, 불일치하면 boot를 중단한다. schema 3 이미지에 SRAM workload를 쓰면 거부한다. 테스트와 mutation을 추가했다 | `host/analysis/stage4p.py`, `host/board/run_driver_events.py`, `host/tests/test_{placement,stage4p,drwl,record_v2,driver_runner_sim,driver_runner_contract}.py`, `firmware/driver_runner/tests/{host_sim.c,placement_probe.c}`, `test.sh` |

## 2. A/B 워크로드 차이 검증 (Gate B, `gate_b.json`)

| 항목 | 결과 |
| --- | --- |
| A blob | `2681c566…f267`. Stage 4 conv_base blob과 같다 |
| B blob | `83034eb1…1de9` (`workloads/s4p_conv_base_sram.drwl`) |
| 다른 바이트 | offset 28 하나(word 7: 0 → 1) |
| 모델(Vela tflite: 명령 스트림, 가중치·bias·scale, 텐서 정의) | 동일. `fadf33d7…` = Stage 4 `vela_sha256` |
| 명령 스트림 | `596fe964…`(520 B)가 두 모델의 같은 offset에 한 번씩 있다 |
| IFM·golden 구간, 헤더(word 7 제외), IO 표 | 동일 |
| kernel 수, block·ublock, 처리 순서, 가중치 DMA | 명령 스트림 안의 정보다. 명령 스트림이 바이트 단위로 같으므로 이 항목들도 같다(재컴파일 없음) |
| 판정 | **PASS** (8개 검사 전부) |

## 3. 메모리 주소·영역·포트 검증표

상태 표기:
- `STATIC`: 이미지·소스·링커에서 확인.
- `SIM`: host 시뮬레이터에서 실행으로 확인.
- `UNVERIFIED`: 보드에서만 확인할 수 있음.

| 항목 | A | B | 상태 |
| --- | --- | --- | --- |
| region 1 base(arena) | `0x700015C0` | `0x310615C0` | 계산은 STATIC(`test_placement`의 conv_base 값), 동작은 SIM. 보드 기록은 UNVERIFIED |
| region 1 범위 | `0x700015C0–0x700111C0` | `0x310615C0–0x310711C0`(ISRAM0 안) | STATIC |
| arena 전체(2 MiB, CPU 전용 꼬리 포함) | `…–0x702015C0` | `…–0x312615C0`(ISRAM1에 걸침, `0x31400000` 이하) | STATIC |
| 하위 16 bit 정렬 | `0x15C0` | `0x15C0` | STATIC + SIM |
| 384 KiB fast scratch와의 충돌 | 없음 | 없음. 시작이 fast memory 끝(`0x31060000`) 이후 | STATIC(새 이미지 nm: SRAM 심볼은 `cache_arena` 하나) |
| 코드·데이터·.bss·heap(BRAM `0x12000000`), stack(DTCM `0x30000000`), UART staging(DDR `0x90000000`), 모델(DDR `0x70000000`)과의 충돌 | 기존과 같음 | 없음 | STATIC(새 이미지 `size -A`, `nm -S`, 링커 MEMORY) |
| SRAM에 다른 로드 이미지 | — | 없음(images.txt: boot `0x11000000`, bram `0x12000000`, ddr `0x70000000`) | STATIC |
| REGIONCFG(base 5개) / QCONFIG | 0x15F / 3 | 0x153 / 3(region 1 필드만 다름) | 표는 STATIC(`test_placement`, 디스어셈블), 동작은 SIM. 보드 값은 UNVERIFIED(F4로 RUN마다 기록) |
| region 0·2·3–7의 포트 | 3·1·1 | 같음 | STATIC(`test_placement`: A와 B의 XOR = 0xC뿐) |
| TA 설정 | profile 1 | 같은 레지스터 값. 바뀌는 것은 region 1이 거치는 TA뿐 | 이미지는 TA를 쓰지 않는다(`git diff`: TA 코드 변경 없음). 보드 값은 capabilities로 비교하며 UNVERIFIED |
| CPU/NPU 주소 대응 | identity(`ethosu_address_remap` 변경 없음) | 같음. secure alias `0x31…` | STATIC. NPU의 `0x3106…` 접근은 UNVERIFIED |
| 캐시 일관성 | 드라이버가 job 전에 clean, 뒤에 invalidate(주소 무관). 적재 때 검사·오염 뒤 clean+invalidate | 같음 | STATIC. `0x31…`의 cacheability는 UNVERIFIED |
| SRAM 접근 권한(MPC) | — | MLEK 소스에 MPC 설정 코드가 없다. 보드의 MPC 상태는 모른다 | UNVERIFIED(P2 메모리 검사가 CPU 접근을 확인한다) |
| 잘못된 placement 값, SRAM 범위 초과, 메모리 불량, IFM 불일치 | — | 거부(0x107 / 0x600 / 0x701·0x702 / 0x800)하고 IDLE로 돌아간다. 다음 RUN은 거부된다 | SIM |
| 포트 설정 불일치(REGIONCFG/QCONFIG) | — | REGIONCFG_MATCH가 해제되고 validity가 실패하며 보드 스크립트가 boot를 중단한다 | SIM |
| 이전 이미지(schema 3)에 B workload | — | `RULE_RECORD_SCHEMA`로 거부한다(이전 이미지는 word 7을 무시하기 때문) | 단위 시험 |

## 4. 기존 DRAM 실행 경로 회귀 (Gate C)

| 항목 | 결과 |
| --- | --- |
| `run()` 본문 | `19adf32`와 바이트 동일 |
| PMU arm hook(`ethosu_address_remap`), `pmu_session.c`, `probe.c`, `trace.c`, `frame.c`, `record.c` | 바이트 동일 |
| RUN 중 추가된 CPU 작업 | PMU 창 전: `fill_config`에 store 1개(`r->placement`). PMU 창 뒤: `fill_from_probe`에 store 2개, `flags_of`에 비교 1개, IRQ handler에서 PMU snapshot 뒤 MMIO read 2개. 복사·검증·로깅은 추가하지 않았다(계약 테스트 `test_run_path_unchanged`) |
| 기존 헤더 처리 | word 7 = 0 blob은 그대로 받는다. Stage 4 blob은 `with_placement(…, 0)` 뒤에도 바이트가 같다 |
| 실행 명령·출력 조회, 카운터 초기화·시작·종료 | 기존 시뮬레이터 테스트(full run, 4in/5out, GET_OUTPUT, trace 모드, checked trace, 실패 flag, refusal, board script)가 전부 통과한다 |
| 기존 기록 | schema 3 record를 그대로 읽는다(`test_schema_3_records_still_parse`). schema 3의 validity 규칙은 바뀌지 않았다 |
| 적재 시간 변화(A 포함) | load마다 arena 2 MiB 검사, OFM 오염, IFM 되읽기가 추가된다. RUN 밖이고 PMU 창 밖이다. A가 Stage 4를 재현하는지는 보드 P1로 확인한다 |

## 5. 로컬 빌드·자동 테스트 (Gate D)

| 항목 | 결과 |
| --- | --- |
| `sh test.sh` | **ALL PASS**, 52 모듈(신규 `test_placement`, `test_stage4p` 포함) |
| 신규·변경 테스트 | `test_placement` 4, `test_stage4p` 11, `test_drwl` 7, `test_record_v2` 5, 시뮬레이터 `Placement` 7 + `PlacementBoardScript` 3, 계약 `Placement` 3 |
| mutation | `mutate.py` → `mutation.txt`: **34/34 KILLED**. 모든 파일을 sha256으로 복원했고(전체 digest 비교 동일), 복원 뒤 GREEN |
| 펌웨어 빌드 | 원격 컨테이너 `benchmark-runner`(보드 host의 docker)에서 실행했다. 소스는 커밋 `70090f1`의 `git archive`, 출력은 `/work/driver_s4p_img`, rc 0이다. 펌웨어 소스는 이후 커밋에서도 바뀌지 않았다 |
| 빌드 gate | `GATE OK: driver hooks are the runner's, MLEK profiler hooks are MLEK's, SRAM holds only cache_arena` |
| 이미지 | boot.bin `718c4562…ef59`, bram.bin `c80e77df…e99c`, ddr.bin `e3b0c442…b855`(빈 파일, 기존과 같음), images.txt `af688281…423f`(기존과 같음), axf `13244fce…6b52`(`build_facts.txt`) |
| 디스어셈블 | `placement_config_select`: index 1이면 placement == 1일 때 0, 아니면 3. index 2–7이면 1. 나머지(−1 포함)는 3. `ethosu_config_select`는 index(r2)를 넘겨 이 함수로 tail call한다. 기존 이미지의 `ethosu_config_select`는 드라이버의 weak(`W`)이고 새 gate는 이를 거부한다 |
| 경고 | `LOAD segment with RWX permissions` 1건. 기존 Stage 4 빌드에도 같은 경고가 있다 |
| MLEK 트리 | tracked 파일 변경 없음(빌드 스크립트가 전후로 검사). untracked `.bak` 파일이 이전 작업부터 있었고, 이번에 만든 것이 아니며 빌드 입력도 아니다 |

로컬 빌드 성공은 보드에서 SRAM 접근이 동작한다는 증거가 아니다.

## 6. 보드에서만 확인할 수 있는 항목 (UNVERIFIED)

| # | 항목 | 확인 방법(계약 초안) |
| --- | --- | --- |
| U1 | FI101에 `0x31060000–0x312615C0` SRAM이 실제로 있고, CPU가 secure alias로 읽고 쓸 수 있다(ISRAM1 구간 포함). MPC가 막지 않는다 | P2: B load의 arena 검사가 ACK, load_status 0 |
| U2 | NPU가 SRAM AXI 포트로 `0x310615C0–0x310711C0`을 읽고 쓴다 | B의 오염 RUN(set 1 rep 1)이 golden과 일치하고, 출력 `PASS_EXACT`, pass B SRAM wr beat +3,456, EXT wr −3,456 |
| U3 | REGIONCFG 0x153 / QCONFIG 3이 실제로 적용된다 | 모든 RUN의 `regioncfg_irq`/`qconfig_irq`, REGIONCFG_MATCH |
| U4 | 새 이미지의 A가 Stage 4를 재현한다(load 시 검사·오염 추가, record 확장의 영향 없음) | P1 |
| U5 | B load 때 CPU fault나 hang이 없다 | P2(응답 없음이면 중단, 복원) |
| U6 | `0x31…`와 `0x70…`의 CPU 캐시 속성(아키텍처 기본 맵상 둘 다 cacheable로 판단) | 측정하지 않는다. 캐시 처리가 주소와 무관하므로 A/B에서 같은 코드가 돈다는 정적 근거만 있다 |
| U7 | B에서 IFM·OFM과 가중치 staging이 SRAM 포트·TA_SRAM을 함께 쓰는 영향 | 분리하지 않는다. B 구성의 일부로 보고한다 |

## 7. 재현 절차

```sh
# 저장소 (worktree mps4_prototyping_board-driver, branch feat/driver-runner)
sh test.sh                                               # ALL PASS
python3 evidence/stage4_placement/mutate.py              # 34/34 KILLED, sha256 복원
W=evidence/stage4/workloads
python3 host/analysis/stage4p.py make-b $W/s4_conv_base.drwl evidence/stage4_placement/workloads/s4p_conv_base_sram.drwl
python3 host/analysis/stage4p.py gate-b $W/s4_conv_base.drwl evidence/stage4_placement/workloads/s4p_conv_base_sram.drwl \
    $W/s4_conv_base.drwl.json $W/s4_conv_base.drwl.cms.bin  # PASS
python3 evidence/stage4_placement/static_facts.py         # 17/17 (설계 단계의 사실 재계산)
# 이미지 (원격 컨테이너, 보드 접근 없음)
git archive <commit> firmware/driver_runner firmware/common host | ssh gihwan 'docker exec -i benchmark-runner sh -c \
    "mkdir /work/<new src> && tar -x -C /work/<new src>"'
ssh gihwan 'docker exec benchmark-runner sh /work/<new src>/host/container/build_driver_runner.sh /work/<new src> /work/<new out>'
```
