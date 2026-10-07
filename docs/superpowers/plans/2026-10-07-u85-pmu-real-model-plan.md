# U85 PMU 이벤트 — 실모델·EXT 경로 확장 계획 (Tier C)

작성 2026-10-07. 근거: 2026-09-23 Tier A/B 캠페인(`docs/ETHOS_U85_PMU_REFERENCE.md` 8절,
`docs/ETHOS_U85_PMU_TRM110_MEASURED.md`) + 2026-10-07 재검토(컨테이너 소스·FI101 문서·Vela 실제 컴파일).
**이 문서는 계획이다. 각 단계의 측정 계약은 데이터 전에 별도로 동결한다.**

## 진행 상태

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 0 | `USE_AXI_EXT` 1×1 실험 — EXT 포트 도달성 + `ext_*` 30개 | **완료: EXT_UNREACHABLE** (부팅 11, `evidence/pmu_events_c/VERDICT.md`). 0x9000_0000(IDAU 9, Dev Access)은 EXT 포트로 못 감 — EXT 요청 4건 후 stall |
| 0b | 텐서를 DRAM 별칭(0x7010_0000, IDAU 7 S)에 두고 EXT 재시험 | **완료: EXT_DRAM_REACHABLE** (부팅 12, 66/66 VALID, golden 일치, ±1 % 검사 PASS). `ext_*` 16개 NONZERO — `evidence/pmu_events_c/VERDICT_0b.md` |
| 1 | 작은 Vela 모델(kws_micronet_m) — 실모델 경로 | **완료: MODEL_RUNS_CORRECT** (부팅 13, 66/66, 보드 OFM = tflite_runtime 레퍼런스 바이트 일치). TRM 38 / Reserved 46 NONZERO — `evidence/pmu_events_c/VERDICT_1.md` |
| 2 | mobilenet, 표적 48개(포트 분리·PMCAXI_CHAN=EXT) | **완료** (부팅 18, 18/18 VALID under amendment 2). 36 NONZERO — `sram*` 24·`axi_latency` 7 전부 셈; `*_stall_limit` 12만 0. 부팅 14 실패→진단 15–17: 원인은 모델의 미세 수치 차이(5/1001 B, ≤4), 포트 분리 아님 — `evidence/pmu_events_c/VERDICT_2*.md` |
| 3a | 전수형 171개 — mobilenet, 포트 분리·PMCAXI_CHAN, AXI 한도 OFF | **완료** (부팅 19, 66/66, 업로드 1회). TRM 57 / Reserved 47 NONZERO; 단계 2와 48/48 동일 |
| 3b | `*_stall_limit` — AXI 한도 1건 | **완료** (부팅 20, 9/9). 12개 중 9개 셈; EXT **쓰기** 한도 3개는 이 라우팅에 EXT 쓰기가 없어 0 |
| 합계 | 전 유효 캠페인 합집합 | **TRM-110 중 78개 실측 NONZERO**, 미관측 32 (sram2/3 22·ecc 6·no_event 1·ext 쓰기 한도 3). Reserved-61 중 53개 NONZERO — `evidence/pmu_events_c/VERDICT_3.md` |

## 재검토에서 확립된 사실

1. **`ext_*` 0의 원인 정정.** test3 데이터는 SRAM이 아니라 **DDR `0x9000_0000`**(DDR.BIN, 링크맵 `.ddr`)에 있다.
   벤더 `test_commands()`가 `MEM_ATTR0..3 = 0`(SRAM AXI 포트), `REGIONCFG = 0` 을 쓰므로 DDR 주소인데도
   전 트래픽이 SRAM 포트로 나간다. `USE_AXI_EXT` 컴파일 스위치(같은 파일)가 MEM_ATTR에 EXT 비트(0x4)를 세운다.
2. **EXT 도달성 미검증.** FI101 표: M0/M1 → VM0–3·XMSTEXPDEV, M2/M3 → XMSTEPDRAM0/1. 현재 `0x9000_0000`
   접근은 SRAM 포트(=XMSTEXPDEV 경로)로 성공한다. EXT 포트로 같은 주소가 닿는지는 모른다 → 단계 0의 핵심 질문.
3. **벤더 제출 경로는 매개변수화돼 있다.** `test_u85(eTest, irq_mask, out_size, qsize, &u85_warp_data_t)` →
   `BASEP0=weights, BASEP1=scratch, BASEP2=in, BASEP3=out, QBASE=cmd_st, QSIZE`. TFLM `ethosu.cc` 규약
   (base0=상수, base1=arena, base2=fast scratch)과 일치. `"Testing CPM signals"` seam은 `test_commands()` 안 →
   어떤 스트림이든 그대로 발화.
4. **Vela 1024 산출물에서 필요한 것 전부 추출 가능** (vela 5.0.0, `ethos-u85-1024` 실제 컴파일 확인):
   `ethos-u` op 입력 = command_stream / read_only(상수) / scratch(arena 크기) / scratch_fast(크기) / IFM;
   `OfflineMemoryAllocation` 메타데이터 = arena 안 IFM/OFM 오프셋.
5. **필수 수정: IRQ 대기 타임아웃.** `BUSY_SLEEP` + `BUSY_SLEEP_TIMEOUT 10000` 루프(50 MHz에서 수 ms).
   초과 시 `irq_never_triggered`로 빠져나와 실행 중인 NPU에 `CMD=0xC`(clock/power 해제)를 쓴다.
6. D-cache 꺼짐(러너 주석·소스 확인) → 캐시 유지보수 불필요. VM0–3 각 2 MB, 러너 VM 사용 ~160 KB.
   DDR 스테이징 `0x9012_0000` 16 MiB. 보드 CPU 50 MHz.
7. 기존 Vela 산출물은 전부 256/512용(`/work/u85mech`, `/work/u85e2`, `~/mps4/U85_MECH_P1A_*`) → 1024 재컴파일 필요.
   메모리 모드 기본 `Dedicated_Sram`(상수·arena→Axi1, fast→Axi0). `tflite_runtime` 컨테이너에 있음(레퍼런스 출력용).

## 변경 지점과 규모

| 위치 | 변경 | 규모 |
| --- | --- | --- |
| 벤더 `u85.c` 생성 사본(패처, 원본 무수정) | 단계 0: `USE_AXI_EXT=1`. 단계 1+: 타임아웃 상향, 영역별 REGIONCFG/MEM_ATTR | 앵커 1–4개 |
| 러너 패처 확장 | `SET_WORKLOAD` 명령, 스테이징 포인터로 `test_u85`, OFM 기준 poison/CRC, IFM 배치, fast scratch VM 배열 | 생성 ~150–200줄 |
| 호스트 도구(신규) | 1024 Vela 컴파일 → 추출 → `tflite_runtime` 레퍼런스 → 패커 | ~200줄 + 테스트 |
| 호스트 드라이버 | `set_workload()`, 업로드 후 기존 22세트 루프, 출력 일치 항 | ~100줄 |
| 게이트 | 생성 벤더 사본, 러너 | 규칙 4–6개 |
| 무변경 재사용 | EVENTS 모드(power hold), CPM seam, 판정/파서/조인, deploy/restore/postflight | — |

## 운영

UART 115200 ≈ 11 KB/s: kws 140 KB ≈ 13 s, mobilenet 4 MB ≈ 6 min, wav2letter 14.6 MB ≈ 22 min(16 MiB 스테이징 빠듯).
배포(sudo, 소유자 실행)는 펌웨어당 1회. 원본 복구 기준값 `~/evsweep/evidence/board-backup/current`
(`ffa3e5bd…`/`45e943c5…`/`81d37a21…`) — 매 단계 끝에 restore + postflight.

## 함정 (이전 캠페인에서 실측)

- `cnt_en=0`에서 쓴 PMU 설정은 카운팅에 반영 안 됨 / `cnt_en=1`에서 power hold 없이 PMCR 리셋 쓰기 → cnt_en 0
- 호출 후 판독은 항상 0 (벤더 `CMD=0xC`) — 판독은 CPM seam에서
- 프로그래밍 전 `CMD=0` hold + guard 필수 (2026-08 진단 캠페인이 명명한 원인)
- 배포 증거 루트는 배포마다 새로(`evidence_bN`) — 원본 백업 슬롯 덮어쓰기 방지

## 열린 질문 (UNPROVEN)

EXT 포트 DDR 도달성 / Vela 출력의 `tflite_runtime` 비트 일치 / `SYS_DRAM_Low` 설정과 FPGA 실제의 차이(정확성 무관).

## 단계 1 축소안 (2026-10-07, 0b 결과 반영)

계획서 "변경 지점과 규모"의 큰 항목 대부분이 불필요해졌다:

| 원래 계획 | 실제 |
| --- | --- |
| 러너 새 명령 `SET_WORKLOAD` + 호스트 프로토콜 확장 | **불필요.** 기존 `LOAD_MODEL`로 워크로드 블롭(헤더 `PMWL` + cms + 상수 + IFM + 레퍼런스 OFM)을 스테이징(0x9012_0000)에 올림 |
| 스테이징 포인터로 `test_u85` 호출하는 러너 경로 | 0b의 `__wrap_test_u85`에 블롭 분기 추가 — 진입점·seam·EVENTS 그대로 |
| OFM 기준 poison/CRC 재설계 | 벤더 `VERIFY_OUTPUT` memcmp에 `out_ver`=레퍼런스 OFM을 넘김 → rc가 정답 판정 |
| 영역별 REGIONCFG/MEM_ATTR | 단계 1은 전 영역 EXT(`USE_AXI_EXT`) — 0b에서 검증된 경로 |
| 벤더 타임아웃 | 유일한 벤더 변경: 생성 사본에서 `BUSY_SLEEP_TIMEOUT` 상향 (`#define`이 무조건이라 `-D`로 불가) |

추가로 확인한 사실: Vela cms 앞에는 `COP1` 드라이버 페이로드가 붙는다(core-driver `ethosu_driver.c`:
`COMMAND_STREAM`=2 액션의 `(reserved<<16)|length` 워드 뒤가 순수 스트림). 끝 워드 `0xffff0000` = `NPU_OP_STOP`
mask 0xFFFF. 논문 모델 중 dnn_s 외 전부 `ethos-u` op 하나로 컴파일됨. 원본:
`/opt/arm/ml-embedded-evaluation-kit/resources_downloaded/*/`. 단계 1 모델: `kws_micronet_m`.

## 단계 3 결정 (2026-10-07, 소유자: "둘 다 진행하자")

1. **업로드 부팅당 1회.** 구현은 "RESET 후 스테이징 블롭 재사용"이 아니라, MODEL 빌드에서만 상태표가
   `INPUT_READY`/`RESULT_READY`에서도 `SET_INSTRUMENTATION_MODE`를 받게 하는 것. RESET 의미는 그대로이고
   모델은 CRC 검증된 LOAD_MODEL 1회로 유지된다. 이전 세트의 PMU 상태는 매 RUN의 power-hold 시퀀스가
   지우고 리셋한다(OVS/CNTEN/INT clear, PMCR 리셋). 호스트 `--keep-model`.
2. **AXI 한도 노브.** 헤더 v3(32워드): [23] AXI_SRAM, [24] AXI_EXT. 적용은 POWER_CTRL seam(벤더가
   0x00021F3F를 쓴 뒤), 되읽기 검증. TRM: max_outstanding_read_m1[5:0], write_m1[12:8], max_beats[17:16].
   기본 OFF — 3a 전수형은 OFF, 3b만 ON.
