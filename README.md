# mps4_prototyping_board

Arm MPS4 FPGA prototyping board (HBI0376 Rev B Var A) 위에서 Corstone SSE-320 /
Cortex-M85 / **Ethos-U85 NPU**의 성능을 측정하기 위한 펌웨어·호스트 툴링과
qualification 증거. 실제 보드에서 실행·검증된 결과다. FVP 시뮬레이터 결과가 아니다.

프로젝트 전체(FVP 캠페인, MLEK 7개 모델, per-layer mechanism study)의 맥락은
`docs/presentation/`과 Obsidian vault `npu_benchmark/`에 있다.

---

## 사용 매뉴얼

### 0. 먼저 알아야 할 것 — 이 저장소는 미러다

**여기서 코드를 고쳐도 실행 환경에 반영되지 않는다.** 수정은 서버/컨테이너에서
하고 사본을 갱신하는 방향이 맞다. 반대로 하면 두 개의 진실이 생긴다.

| 대상 | 권위 있는 위치 |
|---|---|
| 호스트 툴링 실행 (보드 제어) | 서버 `gihwan:/home/gihwan/mps4/` |
| 펌웨어 빌드 | 컨테이너 `benchmark-runner:/work/selftest/` |
| Vela / MLEK / FVP | 컨테이너 `/opt/arm/`, `/usr/local/bin/vela` |
| 프로젝트 맥락·계약 | `~/Documents/Obsidian Vault/npu_benchmark/project-context.md` |
| 플랫폼 바이너리 (113 MB) | `~/Documents/Projects/personal/mps4_board_recovery/` |

브랜치 지도:

| 브랜치 | 내용 |
|---|---|
| `main` | 보드 커스텀 러너 (measure / PMU candidate / CFG A/B/C 준비). 2026-08-10 정지 |
| `pmu-completion-s5-only-control` | V13~V15 보드 캠페인 + `docs/paper/` (FVP 222 + 보드 21 샘플 논문 캠페인) |
| `u85-mechanism-p0` | `docs/paper/mechanism/` per-layer mechanism study (worktree `~/Documents/Projects/mps4_u85_mechanism`) |

### 1. 초기 환경 세팅

#### 1.1 로컬 Mac

```sh
git clone <repo> mps4_prototyping_board
cd mps4_prototyping_board
git worktree add ../mps4_u85_mechanism u85-mechanism-p0   # 논문/mechanism 문서를 보려면
brew install cloudflared                                   # 서버 SSH 터널
```

`~/.ssh/config`에 다음을 둔다. 키는 서버 `authorized_keys`에 등록돼 있어야 한다.

```
Host gihwan
    HostName ssh.gihwan.uk
    User gihwan
    IdentityFile ~/.ssh/<key>
    ProxyCommand /opt/homebrew/bin/cloudflared access ssh --hostname %h

Host gihwan-lan            # 같은 LAN에서만, 터널보다 빠름
    HostName 192.168.45.241
    Port 2222
    User gihwan
    IdentityFile ~/.ssh/<key>
```

확인:

```sh
ssh gihwan 'hostname; docker ps --format "{{.Names}} {{.Image}}"'
# benchmark-runner fpga-simulator:latest 가 떠 있어야 한다
```

`gihwan-local` / `gihwan-web`은 다른 머신이다.

#### 1.2 서버 (x86_64, 보드가 USB로 연결된 호스트)

| 항목 | 값 |
|---|---|
| 호스트 툴링 | `/home/gihwan/mps4/` (이 저장소 `host/`의 원본) |
| 파이썬 | **`/usr/bin/python3` (3.12.3, 시스템)** — 보드 스크립트는 여기서 돈다 |
| pyserial | 3.5, `apt install python3-serial` (pip 아님, requirements.txt 없음) |
| `mps4/venv/` | pyocd 전용. pyserial 없음. **활성화하면 보드 스크립트가 ModuleNotFoundError로 죽는다** |
| FVP (호스트측) | `/home/gihwan/fvp-corstone320-installed/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320` |

새 서버에 세팅할 때:

```sh
sudo apt install python3-serial
python3 -c "import serial; print(serial.__version__)"   # 3.5
```

#### 1.3 컨테이너 `benchmark-runner`

`docker commit` 스냅샷이라 Dockerfile로 재현되지 않는다 (SSE-320/310 FVP, fvp_avh가
Dockerfile에 없음). 컨테이너가 사라지면 FVP 환경은 복구 불가이므로 지우지 말 것.
펌웨어 툴체인(gcc, MLEK)은 이미지에 있어 펌웨어 빌드는 재현된다.

```sh
ssh gihwan
docker exec -it benchmark-runner sh -lc 'cd /work/selftest && ls'
```

| 경로 | 내용 |
|---|---|
| `/work/selftest/` | 펌웨어 빌드 트리 (벤더 `Device_SSE-320`, `Drivers`, `Selftest_cli` 포함 — 미러에는 없음) |
| `/work/u85mech/` | mechanism study 작업 영역 |
| `/opt/arm/gcc-arm-none-eabi/` | Arm GNU Toolchain 15.2.Rel1 (`arm-none-eabi-gcc 15.2.1`) |
| `/opt/arm/ml-embedded-evaluation-kit/` | MLEK `26.03-8-gb2c0bb2`, core-driver 25.11 |
| `/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/` | FVP Corstone SSE-320 (Fast Models 11.27.25) |
| `/opt/arm/fvp_installed/`, `fvp_installed_310/`, `fvp_avh/` | SSE-300 / 310 / 315 FVP |
| `/usr/local/bin/vela` | Vela 5.0.0 |

#### 1.4 보드 시리얼

FTDI 4포트, 115200 8N1. 보드의 FTDI 시리얼 번호 `00FT46259002B`가 스크립트 29곳에
하드코딩돼 있다 (`host-environment/serial-bindings.yaml`). 다른 보드로 옮기면 전부
바꿔야 한다.

```
/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0   MCC 콘솔 (CR)
/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0   FPGA UART0 = 러너 프로토콜 / MLEK 출력 (LF)
if02, if03                                                                      FPGA UART1, UART2
```

SD 카드는 MCC의 `USB_ON`으로 `/dev/sdb1`에 노출되고 `/mnt`에 마운트한다 (sudo 필요).

#### 1.5 보드 복구 아카이브

`fi101_00.bit` 등 벤더 플랫폼 바이너리는 저장소에 없다. 해시는
`board-config/RECOVERY_ARCHIVE.sha256`, 실물은
`~/Documents/Projects/personal/mps4_board_recovery/`. **미러만으로는 보드를 재구성할 수
없다.** 복구는 "백업을 다시 쓰기"가 아니라, 카드에 원래 없던 `boot.bin`/`bram.bin`을
삭제하고 덮어쓴 것을 복원하는 것이다.

### 2. 펌웨어 빌드 (커스텀 러너, 컨테이너 안)

빌드 트리는 `/work/selftest/`. 로컬 재현이 필요하면 `build-env/selftest-worktree.tgz`를
빈 디렉터리에 풀어 쓴다 (벤더 원본 `fi101-selftest-src.tgz`는 빌드되지 않는다).

```sh
cd /work/selftest

# measurement-clean 러너 (MEASURE_SEQ 계열)
make -f Makefile.measure PROFILE=clean  bins check hashes     # build_measure_clean/{APP,VECTORS,DDR}.BIN
make -f Makefile.measure PROFILE=wrapped bins check hashes    # 진단용, 게이트는 advisory

# PMU candidate (OFF / END_ONLY 런타임 모드)
make -f Makefile.pmu PROFILE=clean bins check hashes

# PMU qualification schema v8 (H-PRINTF seam). QUAL을 비우면 Makefile이 멈춘다
make -f Makefile.pmu_qual QUAL=Q0 clean bins check manifest hashes   # hook 비활성 (등가성 대조)
make -f Makefile.pmu_qual QUAL=Q1 clean bins check manifest hashes   # hook 활성 (자격 후보)
```

- `check`는 denylist 콜그래프 검사(`check_measure_symbols.py`)와 정적 게이트를 돌리고
  위반 시 **빌드를 실패**시킨다. `manifest`는 ELF 게이트 본체(`check_pmu_qual.py`)를
  돌려 `pmu_qual_manifest.json`을 만든다. 호스트 스크립트는 이 manifest와 BIN 해시가
  일치해야 포트를 연다.
- `Selftest_pmu/npu_pmu_regs.h`는 생성물이다. 손으로 고치지 말고
  `python3 Selftest_pmu/gen_npu_pmu_regs.py --generate`, 드리프트는 `--check`로 잡는다.
  `nc_gen.py`가 변조 헤더 13종으로 생성기가 실패해야 할 때 실패하는지 검증한다.
- 음성 대조 빌드: `INJECT_VIOLATION=1 check`는 FAIL, `INJECT_SKIP_NPU=1`은
  `--expect-injected-skip` 모드에서만 PASS, `TEST_HOOKS=1`은 `--expect-test-hooks`
  모드에서만 PASS여야 한다.
- 두 번 빌드해 BIN이 바이트 동일한지 확인한다 (BUILD_ID는 고정 ASCII, 타임스탬프 없음).

### 3. 보드 배포와 부팅 (서버에서, `/usr/bin/python3`)

SD 카드 `\SOFTWARE\` 아래 세 파일이 `images.txt`로 로드된다
(`board-config/current/images.txt`):

```
IMAGE0  VECTORS.BIN  0x11000000  port 2  RAM
IMAGE1  APP.BIN      0x31000000  port 1  RAM
IMAGE2  DDR.BIN      0x90000000  port 1  RAM
```

배포 순서. 세 BIN은 카드의 `SOFTWARE/` 아래에 수동으로 복사한다
(`host/mcc_harness.py`의 `SdCard`는 `USB_ON → mount → … → umount → USB_OFF` 사이클과
MCC `WRITE_AXI`용 스테이징 파일을 카드 루트에 두는 용도이고, 이미지 파일 배치는 하지
않는다):

```
MCC USB_ON → sudo mount /dev/sdb1 /mnt → cp {VECTORS,APP,DDR}.BIN /mnt/SOFTWARE/
→ 되읽어 sha256 대조 (source == declared == destination) → sudo sync; umount /mnt → MCC USB_OFF
→ MCC REBOOT → "DDR memory test at 0x70000000: PASSED" + "Clearing SCC CPUWAIT" 대기
```

```sh
cd /home/gihwan/mps4
python3 host/do_reboot.py        # REBOOT + DDR self-test / CPUWAIT 확인
```

지켜야 할 순서 두 가지 (하네스 가드가 serial I/O 전에 raise한다):

1. **UART 캡처 listener를 먼저 열고 확인한 뒤 REBOOT.** 앱이 1초 안에 끝나는 경우
   listener를 나중에 열면 출력은 버려진다.
2. **postflight는 `REBOOT → 대기 → USB_OFF → /dev/sdb* 부재 확인`.** reboot가 debug
   USB 카드를 다시 노출하므로 USB_OFF를 먼저 하면 안 된다.

`reset_on()`은 DDR을 못 쓰게 만들어 full REBOOT 전까지 복구되지 않는다. 쓰지 말 것.

### 4. 측정 실행 (커스텀 러너)

러너는 UART0 위의 바이너리 프레임 프로토콜(magic `NUR1`, CRC32)로 제어한다.
NPU 워크로드는 벤더 Selftest의 고정 컨볼루션 `apU85Conv_TEST()`이며, 결과는 256바이트
golden window CRC `0x27084C4C`로 판정한다. Vela/MLEK 모델은 이 러너로 돌리지 않는다.

`RESULT_BASE`/`RESULT_LEN`은 **그 빌드의 .map에서** 읽어 환경변수로 넘긴다
(기본값 `0x90020cc0` / `0x100`은 특정 빌드 값이다).

```sh
cd /home/gihwan/mps4

# 기능 게이트 (functional / measure 이미지). 첫 실패에서 멈춤
RESULT_BASE=0x90020cc0 RESULT_LEN=0x100 python3 host/tests/test_runner_gate.py

# MEASURE 이미지 인수 (9 게이트 + 10회 연속 + RESET 후 재사용) → 16/16
python3 host/tests/test_measure_accept.py

# PMU candidate: OFF / END_ONLY 모드 게이트
python3 host/tests/test_pmu_board.py

# PMU qualification v8: 이미지 배포 + REBOOT 후, fresh boot 하나당 1회
python3 host/run_pmu_qual.py --mode Q1 --host-boot-index 2 \
    --bins-dir /path/to/build_pmu_qual_q1 \
    --manifest /path/to/build_pmu_qual_q1/pmu_qual_manifest.json \
    --out results/qual_q1_boot2.json

# CFG A/B/C 특성화: (case, round, position) 셀 하나 = fresh boot 하나 = 10회 연속
python3 host/run_pmu_cfg.py --case B --round 1 --position 2 --host-boot-index 5 \
    --bins-dir /path/to/build_pmu_cfg_b \
    --manifest /path/to/build_pmu_cfg_b/pmu_cfg_manifest.json \
    --out-dir results/cfg_r1_p2_B
```

한 표본은 두 번의 독립 읽기(비요청 `COMPLETE` 프레임 + `GET` 재독출)로 구성되며 두
원시 페이로드가 바이트 동일해야 채택된다. 유효성 term(v8은 38개)이 하나라도 실패하면
`npu_pmu_window_cycles`는 `None`이다. 0으로 바꾸지 않는다.

### 5. 분석과 증거 동결

```sh
python3 host/analyze_pmu_qual.py --q0 results/qual_q0_boot1.json --q1 results/qual_q1_boot2.json
python3 host/analyze_pmu_cfg.py  ...      # PMU_CFG_FROZEN 상수로 manifest/BIN 불일치 표본 거부
```

분석기는 JSON의 파싱 결과를 믿지 않고 아카이브된 원시 바이트를 다시 파싱·CRC 검증한다.
출력 마지막 줄 `QUALIFICATION ONLY -- no production go, no performance baseline.`이
없으면 그 출력은 절차의 산출물이 아니다.

동결 증거는 `provenance/<IMAGE>/`에 `MANIFEST.yaml`, `SHA256SUMS`, raw log로 둔다.
검증은 두 단계 다 돌린다:

```sh
cd provenance/FI101_RUNNER_V1_MEASURE_SEQ
sha256sum -c SHA256SUMS        # 바이트 동일성. clone에서는 제외된 .BIN 때문에 실패가 정상
python3 verify_manifest.py     # 필드·null·해시 대상·교차 일관성
```

`provenance/` 아래는 동결 증거다. 수정하면 해당 이미지의 qualification이 무효가 된다.

### 6. MLEK 모델 캠페인 (Vela → FVP / FPGA, 브랜치 `pmu-completion-s5-only-control`)

논문 데이터(FVP 222 + 보드 21 샘플)는 커스텀 러너가 아니라 **stock MLEK
`inference_runner`**로 수집했다. 계약과 스크립트는 `docs/paper/`에 있다. 실행은 전부
컨테이너 안이며 `SOURCE_DATE_EPOCH=1776763519`를 반드시 건다 (없으면 AXF가 초 단위로
달라진다).

```sh
docker exec -it benchmark-runner sh -lc '
export SOURCE_DATE_EPOCH=1776763519
KIT=/opt/arm/ml-embedded-evaluation-kit

# 1) Vela 컴파일 (예: U85 512, frozen 관례는 MAC별 system-config가 다름)
vela --accelerator-config ethos-u85-512 --config $KIT/scripts/vela/default_vela.ini \
     --system-config Ethos_U85_SYS_DRAM_Mid_512 --memory-mode Dedicated_Sram \
     --optimise Performance --output-dir /tmp/v \
     $KIT/resources_downloaded/kws/kws_micronet_m.tflite

# 2) MLEK 빌드 — FVP용 (FPGA용은 -DFPGA_PLATFORM_SSE_320=ON, 두 바이너리는 호환되지 않는다)
cmake -B /tmp/b -S $KIT -DCMAKE_TOOLCHAIN_FILE=$KIT/scripts/cmake/toolchains/bare-metal-gcc.cmake \
  -DTARGET_PLATFORM=mps4 -DTARGET_SUBSYSTEM=sse-320 -DETHOS_U_NPU_ID=U85 \
  -DETHOS_U_NPU_CONFIG_ID=Z512 -DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram \
  -DETHOS_U_NPU_ENABLED=ON -DUSE_CASE_BUILD=inference_runner \
  -Dinference_runner_ACTIVATION_BUF_SZ=0x00200000 \
  -Dinference_runner_MODEL_PATH=/tmp/v/kws_micronet_m_vela.tflite
cmake --build /tmp/b -j$(nproc)

# 3) FVP 실행, UART0을 파일로. --fast 금지, extra_args 빈값
/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320 \
  -a /tmp/b/bin/mlek_inference_runner.axf \
  -C mps4_board.subsystem.ethosu.num_macs=512 \
  -C mps4_board.visualisation.disable-visualisation=1 \
  -C mps4_board.telnetterminal0.start_telnet=0 \
  -C mps4_board.uart0.out_file=/tmp/run.uart.log -C mps4_board.uart0.unbuffered_output=1
'
```

UART 프로파일 블록(`NPU TOTAL/ACTIVE/IDLE`, U85는 `SRAM_*`/`EXT_*` beats)은
`docs/paper/analysis/pmuparse.py`로 파싱한다 (이벤트 이름을 하드코딩하지 않고
discovery로 찾는다). 정식 수집은 `docs/paper/evidence/stage{1,2,3}-*/stage*.py`
(3회 exact-equality), 분석은 `analysis/analyzer.py`(정확히 1회 적용).

보드(FPGA, U85@1024 고정)는 `evidence/fpga-builds-*/fpga_build.py`로 7종 빌드 →
`evidence/board-qualification-*/board_probe.py`로 배포·1회 실행·복원. 이 경로의 SD 이미지
이름은 `boot.bin`/`bram.bin`/`ddr.bin`이며 커스텀 러너의 세 BIN과 다르다. stock 러너는
boot당 정확히 1 inference라 표본은 fresh boot 단위(3×1=21)다. 러너를 패치해 숫자를
얻는 것은 계약 위반이다.

### 7. per-layer mechanism 도구 (브랜치 `u85-mechanism-p0`, FVP 전용)

U85는 Vela의 Python code generator를 거치지 않으므로(regor C++ 경로) 컴파일된
command stream을 후처리한다. 증거 루트는 서버
`/home/gihwan/mps4/U85_MECH_P0C_20260902T015728Z/`에 도구와 로그가 있다.

```sh
# 컨테이너 안. 모든 non-DMA launch 직후에 NPU_OP_IRQ(param=순번) 삽입. 선언한 곳 외 무변경을 스스로 검증
python3 insert_irq.py in_vela.tflite out_full.tflite --all
python3 insert_irq.py in_vela.tflite out_ctrl.tflite --control     # 무수정 복사본 (대조)

# 드라이버 패치는 빌드마다 적용 → 빌드 → revert, revert 후 백업과 바이트 동일 확인
python3 patch_driver_u85_v2.py         # IRQ 핸들러: snapshot → reset → clear, 종료 후 PLPROF printf
cmake ... -Dinference_runner_MODEL_PATH=out_full.tflite && cmake --build ...
python3 patch_driver_u85_v2.py --revert
```

출력은 `PLPROF,<idx>,<ccnt>,<active>,<sram_rd>,<sram_wr>,<ext_rd>,<ext_wr>` 행이며,
IRQ 경계당 약 23.5 cycles의 skid가 붙는다. 자격 절차와 매핑 규칙은
`docs/paper/mechanism/U85_PROFILING_QUALIFICATION.md`. 실보드에서는 아직 실행하지 않았다.

### 8. 테스트 실행 (보드 불필요, 로컬 Mac에서도 가능)

호스트 단위 시험은 self-reporting 스크립트다 (`PASS/FAIL` 행과 `passed: N failed: M`
요약을 찍고 `sys.exit`). `pytest`로 수집하면 import 시점의 `sys.exit()` 때문에 죽으므로
쓰지 않는다. 필요 조건 두 가지: **Python 3.10 이상**(`X | None` 타입 문법 사용, 서버는
3.12)과 **`PYTHONPATH=host`**(테스트가 `runner_proto`를 bare import 한다). pyserial은
단위 시험에 필요 없다. 파일을 고치거나 복원한 뒤에는 `__pycache__`를 지운다.

```sh
cd <repo root>
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
for t in test_proto_unit test_abi_unit test_pmu_abi_unit test_pmu_qual_unit \
         test_pmu_cfg_unit test_pmu_diag_unit test_harness_policy; do
  PYTHONPATH=host python3 host/tests/$t.py | tail -1
done
(cd firmware && python3 Selftest_pmu_diag/test_check_pmu_qual.py | tail -1)   # ELF 게이트 mutation test
```

2026-09-02 로컬 실행 결과: proto 9 · abi 18 · pmu_abi 16 · pmu_qual 281 · pmu_cfg 274 ·
pmu_diag 159 · harness_policy 17 · check_pmu_qual 123, 전부 failed 0.
`firmware/Selftest_pmu_diag/test_check_pmu_cfg.py`만 pytest를 요구한다
(`pip install pytest` 후 `cd firmware && python3 -m pytest Selftest_pmu_diag/test_check_pmu_cfg.py`).

보드가 필요한 스크립트(`test_runner_gate.py`, `test_measure_accept.py`,
`test_pmu_board.py`, `test_stale_demo.py`, `test_rawrx.py`)는 서버에서 배포·부팅 후
`/usr/bin/python3`로 직접 실행한다. 논문 브랜치의 V14/V15 시험은 `python3 -m unittest
host.tests.<module>` 형식이며 `.claude/commands/suite.md`가 전체를 돌린다.

### 9. 반복하면 안 되는 함정

- stock MLEK 러너는 boot당 정확히 1 inference. 루프 없음.
- 캡처 listener는 REBOOT 이전에 살아 있어야 한다.
- postflight는 REBOOT → 대기 → USB_OFF → `/dev/sdb*` 부재 확인 순서.
- PMU 이벤트를 번호로 비교하지 않는다. U55/U65↔U85 공유 이름 22개 중 18개가 ordinal이 다르다.
- "FVP가 `num_macs`를 받아줬다"는 유효성 증거가 아니다 (SSE-300 FVP는 100도 받는다). Vela enum이 권위.
- FVP와 FPGA 바이너리는 target-specific. "같은 바이너리를 양쪽에서 실행"이라는 표현 자체가 금지.
- 금지 어휘: latency, T_npu, faster/slower, internal completion, execution time. FVP↔보드 절대 사이클 비교 금지.
- `npu_pmu_regs.h`는 생성물, `provenance/`는 동결 증거, `LinkScripts/lnk.ld.S`는 벤더 원본 FROZEN.
- `venv/`를 활성화하고 보드 스크립트를 돌리지 않는다.
- 컨테이너 `benchmark-runner`를 지우면 FVP 환경은 복구되지 않는다.

---

## 지금 어디까지 왔나

| 단계 | 상태 |
|---|---|
| 하드웨어 bring-up (SODIMM 접촉 불량 원인 규명) | 완료 |
| GCC golden baseline (armclang scatter → GNU ld 이식) | 완료 |
| Functional runner v1 (프레임 프로토콜 + 상태기계) | 완료 |
| Measurement-clean runner (측정 경계 · stale-output 차단) | **보드 인수 통과** (16/16 + 15/15) |
| NPU PMU 계측 — H-PRINTF seam v8, Gate 1 | 완료 (30/30 유효, 불안정 특성화) |
| 완료 관측 경계 특성화 V13~V15 (브랜치) | 완료 — 관측 경계까지 특성화, 추가 보드 실험 비권장 |
| 논문 캠페인 FVP 222 + 보드 21 (stock MLEK) | 완료, RQ3 rho=1.0 |
| U85 256→512 per-layer mechanism study | P0-C QUALIFIED, P0-D 측정 대기 |

## 구성

```
firmware/          펌웨어 소스 (마일스톤별 Makefile + 러너)
  Selftest_measure/  보드 인수를 통과한 measurement-clean 러너
  Selftest_pmu/      NPU PMU candidate + 레지스터 생성기 + 음성 게이트
  Selftest_pmu_diag/ PMU 진단·자격(v7/v8) 러너, 정적 게이트, 절차 문서
  LinkScripts/       오버레이 링커 스크립트 (벤더 lnk.ld.S는 FROZEN)
host/              호스트 툴링 (프로토콜 클라이언트 · MCC 트랜스포트 · 수집·분석 · 시험)
provenance/        이미지별 동결 증거 (MANIFEST · SHA256SUMS · raw log)
evidence/          bring-up 원시 UART 캡처
board-config/      보드 설정 스냅샷 (현재 + 역사적)
build-env/         빌드 환경 provenance (툴체인 · 컨테이너 digest · 작업 트리 아카이브)
host-environment/  호스트 실행 환경 (인터프리터 · 의존성 · 시리얼 바인딩)
docs/MIRROR.md     이 트리의 상세 구조와 무결성 확인 절차
docs/presentation/ 프로젝트 설명 발표자료 (md)
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

**계약은 데이터 전에 동결한다.** 계획·임계값·분석 규칙은 첫 표본 전에 git tag와 `.sha256`
앵커로 고정하고, 수정은 편집이 아니라 supersession으로 기록한다.

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
보드    Arm MPS4 (HBI0376 Rev B Var A), FI101 이미지
SoC     Corstone SSE-320 / Cortex-M85
NPU     Ethos-U85 — 1024 MACs 고정, 이벤트 카운터 8개, 48비트 cycle counter
호스트  FTDI 4포트 — if00 MCC 콘솔(CR), if01 FPGA UART0(LF)
```

## 라이선스

직접 작성한 코드(러너 · 호스트 툴링 · 생성기 · 시험)의 라이선스는 별도 명시 전까지 미정이다.
Arm 벤더 소스·바이너리는 포함돼 있지 않으며 각각의 원 배포 조건을 따른다.
