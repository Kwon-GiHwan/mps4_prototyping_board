# RUNNER_V1_PMU_DIAG — 실보드 실행 절차

> schema v8 H-PRINTF 자격심사(Q0/Q1)는 **별도 빌드 그래프**이며 절차도 분리되어
> 있다 — `PMU_QUAL_PROCEDURE.md`를 볼 것. 이 문서는 v7 diag 매트릭스
> (S1/S2/S3, A/B/C, NC) 전용이고, v8은 이 문서의 어떤 산출물도 무효화하지 않는다.

## v7 최소 seam 실험 (S1/S2/S3) — 현재 단계

v6는 세 가지 개입(① 프로그래밍 전 `CMD=0` pre-hold, ② `u85_diag.c`의
`TEST_CPM=0`로 드라이버의 terminal `CMD=0xC` 제거, ③ post snapshot 뒤 runner의
명시 release)을 **한꺼번에** 넣어 성공했다. 따라서 v6는 "power lifecycle이
관여한다"까지만 보이고 **최소 충분 seam을 분리하지 못한다.** production
END_ONLY가 벤더 드라이버를 그대로 쓸 수 있는지가 이 실험의 질문이다.

세 빌드는 **PMCCNTR_CFG를 case B(생성된 CYCLE config)로 고정**하고
`power_seam_id`만 다르다. A/B/C 이름은 CFG 실험 전용이므로 재사용하지 않는다.

| seam | 드라이버 | 반환 후 재hold | terminal release 복원 |
|---|---|---|---|
| **S1** | reference `Drivers/u85_driver/u85.c` (byte-identical) | 없음 | 드라이버(`test_u85()` 내부). runner는 **read만** |
| **S2** | reference `u85.c` (byte-identical) | **있음** — 반환 후 첫 동작이 `CMD=0` | runner (재hold로 취소했으므로 증거 확보 후 복원) |
| **S3** | diag 전용 `u85_diag.c` (`TEST_CPM=0`) | 없음 | runner (드라이버가 발행하지 않으므로) |

세 seam 모두 **동일한 terminal state로 보드를 되돌린다** —
`npu_cmd_after_power_release`는 세 경우 모두 `0xC`를 기록한다. 누가 그 write를
소유하는지는 record가 아니라 정적 게이트가 판정한다
(`npu_write(CMD, 0xC)` 카운트 S1 0 / S2 1 / S3 1).

**관측 비간섭 계약**: S2에서 `run_fixed_inference()` 반환 뒤 **첫 동작은 반드시
`CMD=0` 재hold**다. NPU/PMU read는 물론 `t_call_return` DWT read도 그 뒤로
옮겼다 — 반환 직후를 샘플링하면 측정하려는 race 자체가 바뀐다.
`npu_cmd_after_seam`/`npu_status_after_seam`은 seam **이후**에만 기록한다.
S2의 `t_call_return - t_call_enter`에는 `rehold_guard_cycles`가 포함되므로
그 값을 함께 보고한다.

```sh
make -f Makefile.pmu_diag SEAM=S1 bins check hashes   # build_pmu_diag_s1, "PDS1"
make -f Makefile.pmu_diag SEAM=S2 bins check hashes   # build_pmu_diag_s2, "PDS2"
make -f Makefile.pmu_diag SEAM=S3 bins check hashes   # build_pmu_diag_s3, "PDS3"
```

`SEAM`은 `DIAG_CASE=B`를 강제하고 `NC`와 조합할 수 없다. `check`가 추가로
증명하는 것: seam별 `npu_write(CMD, …)` 카운트(`0`/`0xC` 기준 S1 1/0,
S2 2/1, S3 1/1),
**반환~재hold 구간에 NPU/PMU/timestamp 접근 0건**(전처리 소스 스캔이 순서의
권위 — `-O1`에서 accessor가 인라인되므로 objdump는 보조), objdump상
`run_fixed_inference` 직후 첫 `bl`이 `pmu_diag_rehold_power`인지(S2),
S1/S3 ELF에 재hold 심볼 부재, 그리고 링크된 u85 드라이버가 seam과 일치하는지.
S1/S2는 private copy를 **컴파일조차 하지 않는다.**

### 빌드 산출물 (schema v7 seam 이미지, 2026-08-08 컨테이너 clean build)

동결 provenance가 아니라 **재현 기대값**이다. 배포 전 컨테이너에서 재빌드해
일치를 확인하고, 결과 JSON에는 실제 배포한 BIN 해시를 host가 붙인다.
이미지 식별은 APP.BIN 해시로 한다. S2는 clean rebuild 비트 동일을 확인했다.

| 빌드 | APP.BIN SHA-256 | VECTORS.BIN SHA-256 |
|---|---|---|
| S1 (`PDS1`) | `7570133e68c803b3268c9a9bf75ace8996f3ba26ede3713362226bb8bbe84375` | `83eb2eb167a5aa82477545650e37c51e55e14d9ebfd92fe6b306e3709f97ea9f` |
| S2 (`PDS2`) | `880080bab94aed99dd494c4659c5c2a8bc3543f800cab7b85974c333541c368f` | `5f15c108b580b8aa6e93f88669a5f618418c623c0668451c966dce0b8044598c` |
| S3 (`PDS3`) | `b04ef92151efa50ff9fe062d07ce33b214342439da7f2c9713b0348827d65a1d` | `8c6fe7d00be152964c518731c3ed425f0ebf53b7059432c67445da9c7b0afb26` |

DDR.BIN은 세 빌드 공통 `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`
(공식 해시) — NPU command stream은 seam과 무관하게 불변이다.

### 보드 실행 순서 (케이스당 독립 full REBOOT, 다음 dispatch)

```
S1 → boot N   : build_pmu_diag_s1 배포 → REBOOT → run_pmu_diag.py --seam S1
S2 → boot N+1 : build_pmu_diag_s2 배포 → REBOOT → run_pmu_diag.py --seam S2
S3 → boot N+2 : build_pmu_diag_s3 배포 → REBOOT → run_pmu_diag.py --seam S3
```

```sh
python3 run_pmu_diag.py --seam S1 --host-boot-index N \
    --bins-dir <배포 build dir> --out results/pmu_diag_S1_boot<N>.json
python3 analyze_pmu_diag.py --s1 ... --s2 ... --s3 ...
```

collector는 요청 seam과 target의 `power_seam_id`·`build_id`·`diag_case`가
어긋나면 **JSON을 쓰기 전에 실패**한다.

### row validity 게이트 (`pmu_diag_seam_row_ok`)

각 row는 **post 상태를 보기 전에** 아래를 전부 통과해야 한다. post 유지 여부는
row validity에서 의도적으로 제외하고 `pmu_diag_seam_post_held`가 단독 판정한다
— 그래야 "유효한 측정인데 손실이 관측됐다"와 "측정 자체가 무효다"가 섞이지 않는다.

**identity**: `seam_id` · `build_id`(PDS1/2/3) · `case_is_b` · `is_normal_build`(nc=0)
· `seam_rehold_consistent` · `rehold_guard_ok`

**pre-inference 실제 상태** (pre snapshot에서 직접 읽음): `pre_armed` ·
`pre_global_enable` · `cfg_programmed_pre`(`pre.pmccntr_cfg == cfg_write_value`).
`*_after_program`과 `program_stable`은 **다른 시점의 사실**이라 이를 대체하지
못한다 — 프로그래밍 직후와 stability 루프 이후 사이에 상태가 무너지면 오직 이
세 항목만 잡아낸다. 이 게이트가 없으면 **추론 이전에 일어난 소실을 terminal
release 탓으로 오인**한다.

**runtime seam telemetry** (seam이 주장한 대로 실제 동작했는지):
`seam_runtime_cmd_ok` — S1은 `npu_cmd_after_seam & 0xC == 0xC`(벤더 terminal
release가 이미 관측돼야 함), S2·S3는 `== 0`(전력 보유/재보유 중).
`seam_runtime_status_ok` — S2·S3만 `npu_status_after_seam & 0x8 == 0`.
**S1의 status는 shutdown transition 중이라 값의 의미가 불명확하므로 게이트하지
않는다.**

**나머지**: `start_sequence_ok` · `power_hold_ok` ·
`power_release_restored`(세 seam 모두 `npu_cmd_after_power_release == 0xC`) ·
`reset_guard_complete` · `global_after_program` · `armed_after_program` ·
`program_stable` · `cfg_write_path_ok` · `cycle_read_stable` · `no_overflow` ·
`run_rc_ok` · `inference_valid_flags` · `golden_window_crc`

### 판정 (보수적)

세 row가 개별 valid한 뒤, **cross-seam corroboration**으로
`output_crc`가 S1·S2·S3에서 동일한지 확인한다. 불일치하면 `invalid-sample`로
중단하고 seam 결론을 내지 않는다 — 같은 고정 추론이 세 이미지에서 같은 출력
바이트를 남겼어야 비교가 성립한다. 이는 각 row의 exact 256B golden 게이트를
**대체하지 않는 추가 조건**이다(전체 region CRC는 잔존 scratch로 boot마다
달라지므로 비교하지 않는다).

| 관측 | 판정 |
|---|---|
| row 하나라도 invalid | `invalid-sample` — 실패한 check 이름과 함께 중단 |
| `output_crc` seam 간 불일치 | `invalid-sample` — 비교 불가, 재실행 |
| S3가 post state 유지 실패 | `control-failed` — 통제군부터 복구, S1/S2 해석 금지 |
| S1·S2 모두 유지 | `terminal-release-harmless` — pre-hold만으로 충분한 후보(반복 필요) |
| S1 상실, S2 회복 | `rehold workaround viable-for-repeat` — **production GO 아님.** 1회 PASS는 안정성 증거가 아니고 END_ONLY는 또 다른 이미지다 |
| S1·S2 모두 상실 | `internal-pre-release-seam-required` — 반환 후 재hold는 이미 늦음. seam이 추론 경로 **안쪽**, 드라이버의 terminal release 이전에 있어야 함 |

진단 delta는 어떤 경우에도 성능 metric이 아니다(측정 window 안에 추가 MMIO가
설계상 포함된다).

---

# 부록 — A/B/C (PMCCNTR_CFG) 실험 절차

> **2026-08-08 boot1/2 (A/B) 실패 기록 — root cause 실험이 아님.**
> `PMU_DIAG_20260808-093848/results/pmu_diag_{A_boot1,B_boot2}.json`은
> schema v1의 **invalid evidence**로 보존한다(재사용 금지 — v3 파서가 거부).
> 실패 원인 2건: ① reset-settle **ordering hazard** — reset 직후의 좁은
> 구간에서 PMU를 프로그래밍하면 전체(CFG·PMCNTEN·CNT_EN)가 wipe된다.
> B의 CFG readback 0x11 성공 직후 pre snapshot부터 전부 0이 그 증거.
> 메커니즘은 미확정: enable RMW가 self-clear 전 reset bits를 재기록(M1)했을
> 수도, 비동기 reset 완료가 mid-reset write를 소거(M2)했을 수도 있으며 두
> 가설 모두 데이터와 부합했다.
> ② whole-.sec_noinit CRC를 golden 게이트로 쓴 계약 결함 — coordinator가
> 회수한 exact 256B window는 CRC 0x27084C4C로 golden 일치(semantic drift
> 없음), region CRC는 잔존 scratch로 boot마다 달랐다.

> **2026-08-08 boot3 (A, schema v2)도 invalid evidence다.**
> `PMU_DIAG_V2_20260808-101656/results/pmu_diag_A_boot3.json`에서 reset bit는
> 첫 read에 clear(`PMCR=0x4000`)였고 arm readback도 1이었지만, 바로 뒤 pre
> snapshot부터 arm과 CNT_EN이 모두 0이었다. 따라서 reset-bit clear readback은
> 비동기 reset 완료 증거가 아니며 v2 settle poll 계약은 폐기한다.

> **2026-08-08 boot4 (A, schema v3)도 invalid evidence다.**
> `PMU_DIAG_V3_20260808-103124/results/pmu_diag_A_boot4.json`은 초기 CNT_EN,
> reset 직전 arm, 마지막 reset 직후 CNT_EN이 모두 1이지만 reset 직후 arm만
> 0임을 보였다. 즉 U85의 final counter-reset pulse는 global enable은 보존하고
> PMCNTENSET.CYCLE은 clear한다. schema v4는 Arm Linux 순서 뒤 cycle counter를
> 다시 arm하고 즉시 readback한 뒤 pre snapshot을 얻는다.

> **boot5 (A, schema v4)도 invalid evidence다.** 즉시 re-arm readback은 1이었지만
> pre snapshot 전에 CNT_EN과 arm이 다시 0이 됐다. 즉 immediate readback은 비동기
> 상태 경계의 완료 증거가 아니었다.

> **boot6 (A, schema v5)도 invalid evidence다.** reset 뒤 65,536 cycle을 기다린 뒤
> programming readback은 성공했으나, 첫 1,024-cycle spaced observation에서 CNT_EN과
> arm이 사라졌다. 이때 NPU CMD는 `0xC`(clock/power Q shutdown request)였다. 벤더
> core-driver의 PMU enable이 먼저 `ethosu_request_power()`를 호출한다는 사실과 결합해
> schema v6는 PMU 접근 전 `CMD=0`으로 power hold를 건다. v1~v5 payload는 v6 parser가
> 모두 거부한다.

> **boot7/8/9 (A/B/C, schema v6)은 유효한 최종 증거다.** 증거 루트는
> `/home/gihwan/mps4/PMU_DIAG_V6_20260808-105919/`. A/B/C 모두 power hold와 8/8
> persistence를 통과하고 cycle progress를 보였다. 따라서 CFG 누락은 원인이 아니다.

> 이 이미지는 **배포 금지 진단 자산**이다. 어떤 수치도 성능 데이터가 아니다.
> DIAG delta에는 추가 MMIO read가 들어가며, 결과 JSON에도 metric이라는 이름의
> 키가 존재하지 않는다 (`usable_diagnostic_delta`).

## 빌드 (benchmark-runner 컨테이너, /work/selftest)

```sh
make -f Makefile.pmu_diag DIAG_CASE=A bins check hashes   # build_pmu_diag_a, BUILD_ID "PDGA"
make -f Makefile.pmu_diag DIAG_CASE=B bins check hashes   # build_pmu_diag_b, BUILD_ID "PDGB"
make -f Makefile.pmu_diag DIAG_CASE=C bins check hashes   # build_pmu_diag_c, BUILD_ID "PDGC"
```

`check`는 다음 게이트를 돌린다:
- `check_diag_case.py` — 전처리된 diag TU에서 레지스터별 `pmu_reg_write` 호출 수를
  센다. **case A는 PMCCNTR_CFG write 0건**이 소스 수준 사실로 강제된다.
- `check_measure_symbols.py --profile clean` — 기존 denylist 콜그래프 게이트.
- diag-private `u85_diag.c`가 원본 `Drivers/u85_driver/u85.c` 대비 오직
  `TEST_CPM=1 → 0` 한 줄만 다른지 byte-level 정규화 비교. 이 seam은 terminal
  `CMD=0xC`를 제거하지 않고 POST snapshot 뒤로 미룬다.

음성 게이트 빌드 (case B 전용, 각각 독립 build dir + 고유 BUILD_ID "PDN1"~"PDN4"):

```sh
make -f Makefile.pmu_diag DIAG_CASE=B NC=skipcfg  bins check   # CFG write 생략
make -f Makefile.pmu_diag DIAG_CASE=B NC=noevent  bins check   # START=NO_EVENT
make -f Makefile.pmu_diag DIAG_CASE=B NC=skiparm  bins check   # PMCNTENSET 생략
make -f Makefile.pmu_diag DIAG_CASE=B NC=forceovf bins check   # PMOVSSET로 overflow 주입
```

NC 이미지의 record는 `nc_control_id` 1~4를 반환하며, `run_pmu_diag.py`와
`pmu_diag_verdict`는 이런 record를 **A/B/C 데이터셋에 넣기를 거부**한다.

## 빌드 산출물 (schema v6 — power hold + reset guard + persistence)

> **이 표는 schema v6 시점 해시다 (SUPERSEDED).** 현재 트리는 schema v7이라
> record가 5워드 늘었고, `SEAM` 없이 빌드하는 A/B/C·NC4도 이제 v7 payload를
> 내며 `power_seam_id=3`(= S3 seam)으로 보고한다. 아래 해시로 재현되지
> 않는다 — CFG 실험을 다시 돌릴 때는 재빌드해 표를 갱신할 것. 배포 가능한
> 현재 이미지는 위 v7 seam 표다.

아래 해시는 동결 provenance가 아니라 **재현 기대값**이다 — 배포 전
컨테이너에서 재빌드해 일치를 확인하고, 결과 JSON에는 실제 배포한 BIN의
해시를 host가 붙인다. DDR.BIN은 7개 빌드 전부 공식 해시(`81d37a21…4ade98`)와
동일 — NPU command stream 불변. **이미지 식별은 APP.BIN 해시로 한다**
(VECTORS는 케이스 간 겹칠 수 있고, DDR 하나로 판단 금지는 기존 교훈 그대로).
v1~v5 해시는 폐기한다. 아래는 최종 schema v6 clean rebuild 해시다.

| 빌드 | APP.BIN SHA-256 | VECTORS.BIN SHA-256 |
|---|---|---|
| A (`PDGA`) | `7acbe376fa24daec3acc3ed806b1d6829663143c8d4a41a6633b178bfe01271d` | `44fecbda3935b8ecc5b0db5b71376f76933d061fafe12008d726ae14a6ec713a` |
| B (`PDGB`) | `fd53d584498e8167aed2538650e0ac9e45648c1cfdcc26a8f65a54aa69452ebd` | `9417ce84e10cc4e65b784be7e6ff93a10e6dc866b03b14b1fc5262658651d458` |
| C (`PDGC`) | `1976d9008c78e104bbe4cc43292ff5f3be14cafea1983fae39828859d45dbd76` | `9417ce84e10cc4e65b784be7e6ff93a10e6dc866b03b14b1fc5262658651d458` |
| B NC=skipcfg (`PDN1`) | `3966c8fac3f5eb87b36e7ad6b77db0e283d7ea1bed855d152e5a9f1a81df289a` | `287f21d3fb38835d7f7c734002191443c857e028291872ff1a2feb6db324b15e` |
| B NC=noevent (`PDN2`) | `a4c306ca1c384e923f1598fa2b4073f2cbf726e0ab41b2d3dc4b8a433e0aebf3` | `9417ce84e10cc4e65b784be7e6ff93a10e6dc866b03b14b1fc5262658651d458` |
| B NC=skiparm (`PDN3`) | `93afc5046489f7f0d48a0c5c4746b3007a60808f078c65cb2f83e82aec486dd0` | `a1120c4353b2c4ab641233e4130a8f06e1a17a88574bf909af51510b5c22cb5b` |
| B NC=forceovf (`PDN4`) | `fc91fd0c97ab4d41d806cb6e3f5cdc17a9b22d261e1cc91ebe0e7c80defb5193` | `1abb9f2c770a9f339562654e5830f2029947d5ed2b039864acbd44f43d8b078d` |

DDR.BIN은 전 빌드 공통 `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`이다.

## 케이스당 실행 (반드시 독립 full REBOOT)

A를 B·C 뒤에 같은 세션에서 돌리면 CFG가 남아 있을 수 있어 무의미하다.
케이스 순서는 자유지만, 각 케이스는 아래 전체 사이클을 처음부터 밟는다.

```
1. SD 마운트   USB_ON → sudo mount /dev/sdb1 /mnt
2. 배포        build_pmu_diag_<x>/{APP,VECTORS,DDR}.BIN → /mnt/SOFTWARE/
               (배포 직후 sha256sum으로 세 파일 재확인 — host가 결과 파일에
                이 해시를 붙인다)
3. sync → umount → USB_OFF
4. MCC REBOOT  (do_reboot.py 경로. DDR self-test PASS · CPUWAIT 해제 확인)
5. 실행        python3 run_pmu_diag.py --case <A|B|C> \
                   --host-boot-index <N> \
                   --bins-dir <배포에 쓴 build dir> \
                   --out results/pmu_diag_<case>_boot<N>.json
6. host_boot_index를 1 올린다 (REBOOT마다, 케이스와 무관하게 단조 증가)
```

`run_pmu_diag.py`가 하는 일: ping → reset → dummy model/input으로 상태기계
진입 → `CMD_RUN_PMU_DIAG` → 언솔리시티드 `CMD_PMU_DIAG_COMPLETE` 수신 →
`GET_PMU_DIAG_RESULT` 재독으로 latch 일치 확인 → **케이스/NC identity 불일치
시 결과 파일을 쓰지 않고 실패** → JSON 기록.

## 판정

세 JSON을 모은 뒤 (각각 독립 REBOOT에서 수집된 것):

```sh
python3 analyze_pmu_diag.py \
    --a results/pmu_diag_A_boot7.json \
    --b results/pmu_diag_B_boot8.json \
    --c results/pmu_diag_C_boot9.json
```

analyzer는 각 JSON의 **원본 wire payload를 재파싱해 CRC부터 재검증**하고
(parsed 사본은 신뢰하지 않는다), case identity·nc=0·서로 다른
host_boot_index·BIN 해시 존재를 확인한 뒤에만 표를 적용한다. root-cause를
주장할 때는 full B proof 체크리스트를 함께 출력한다.

- 게이트: 세 케이스 모두 normal build(nc=0)·기대 case id·rc 0·필수 flag·
  exact 256B golden window `[0x90020CC0, 0x90020DC0)`의
  `golden_window_crc == 0x27084C4C`·stable·overflow 없음이어야 표를
  적용한다. 전체 `result_region_crc`는 참고값일 뿐 게이트가 아니다.
  하나라도 깨지면 `invalid-sample` — 재실행 대상이다.
- A/C 무진행 + full B proof이면 CFG root-cause, A/B/C 모두 진행이면
  `cfg-not-required`다. B가 진행을 보였어도 full proof가 깨지면 `inconclusive`.
- 보고는 구현 설명이 아니라 **A/B/C raw snapshot 표와 판정부터** 올린다
  (위키 계약).

NC 이미지의 실보드 분류 검증은 A/B/C의 정상 결과가 먼저 확보된 뒤 별도
boot index에서 수행한다.

## 최종 실보드 결과와 판정

| case | boot | CFG | pre→post cycle | arm/global 유지 | persistence | golden |
|---|---:|---:|---:|---|---|---|
| A (CFG write 없음) | 7 | `0x00` | `10466→23895` (`+13429`) | yes | 8/8 | PASS |
| B (START=CYCLE) | 8 | `0x11` | `10554→20665` (`+10111`) | yes | 8/8 | PASS |
| C (explicit zero) | 9 | `0x00` | `10473→20564` (`+10091`) | yes | 8/8 | PASS |

세 boot 모두 `CMD 0xC→0x0` power hold, status reset-clear, 종료 후 `CMD=0xC`
복원을 확인했다. 모든 delta는 **진단값**이며 성능 수치로 사용하지 않는다.

판정: **PMCCNTR_CFG 누락은 root cause가 아니다.** v5 A는 `CMD=0xC`에서 첫
persistence read에 PMU state를 잃었고, v6 A는 추론 전 `CMD=0` power hold만으로
CFG write 없이 state를 8/8 유지하고 progress를 보였다. 진단 전용 드라이버의 한 줄
seam은 종료 power release를 POST 뒤로 미뤄 counter state를 관찰 가능하게 했다.
따라서 기존 zero의 root cause는 **PMU programming/readback window가 NPU clock/power
request lifetime 밖에 있었던 power-lifecycle integration 결함**이다.

Production END_ONLY의 다음 수정은 PMU enable/program을 NPU power request 이후에 두고,
cycle POST snapshot·disable을 power release 이전에 두는 전용 seam을 설계하는 것이다.
frozen `Selftest_pmu/runner_pmu_main.c`와 `Makefile.pmu`는 이 진단에서 수정하지 않았다.
