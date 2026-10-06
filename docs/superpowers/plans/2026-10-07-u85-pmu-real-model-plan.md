# U85 PMU 이벤트 — 실모델·EXT 경로 확장 계획 (Tier C)

작성 2026-10-07. 근거: 2026-09-23 Tier A/B 캠페인(`docs/ETHOS_U85_PMU_REFERENCE.md` 8절,
`docs/ETHOS_U85_PMU_TRM110_MEASURED.md`) + 2026-10-07 재검토(컨테이너 소스·FI101 문서·Vela 실제 컴파일).
**이 문서는 계획이다. 각 단계의 측정 계약은 데이터 전에 별도로 동결한다.**

## 진행 상태

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 0 | `USE_AXI_EXT` 1×1 실험 — EXT 포트 도달성 + `ext_*` 30개 | 진행 중 (2026-10-07, 소유자 "진행" 지시) |
| 1 | 작은 Vela 모델(kws/h3r급) Tier C — 실모델 경로 검증 | 대기 (0 결과에 의존) |
| 2 | mobilenet급 — stall/limit·`axi_latency_128+` | 대기 |

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
