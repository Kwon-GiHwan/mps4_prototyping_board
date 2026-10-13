# MPS4 / Ethos-U85 PMU measurement

PMU measurements of an Arm Ethos-U85 (1024 MAC) on the MPS4 FI101 FPGA board, driven by a custom runner
(vendor selftest `test_u85` + PMWL workload blobs), compared against stock MLEK on the same board.
Bare-metal Cortex-M85, `arm-none-eabi-gcc 15.2.1`, `-O1 -g3`.

History before the cleanup (V13–V15, paper campaign, Tier A/B/C, screenings 1/2, earlier A/Bs) lives on branch
`refactor/unified-mlek-campaigns` (last commit `fe7541b`). Paths quoted inside `docs/specs/` and `evidence/` are
from that layout.

## Layout

| dir | what |
| --- | --- |
| `host/` | packer, workload metadata, board driver, parser, metrics, A/B outcome; `host/tests/` |
| `firmware/` | the subset of the build tree this repo owns — **mirrors `/work/selftest` in the container path-for-path** (patchers, gate, base runner source, vendor `u85.c`, `Makefile.pmu_events`). Do not restructure it. |
| `board/` | board-host scripts (copied to `~/evsweep` on `ssh gihwan`): deploy/restore/postflight/inspect, MCC helpers, `run_campaign.sh` |
| `config/` | workload metadata (`workloads/*.meta.json`), PMU event set (`screening_ids.txt`) |
| `docs/reference/` | PMU event lists (TRM 110, driver 171), PMU reference, MLEK board reference values |
| `docs/specs/` | frozen contracts still in force: metric definitions, timing-adapter A/B |
| `evidence/` | `ta_ab/` (the TA finding, incl. the MLEK-TA baseline arm), `runner_gap/` (static diff, hypothesis table) |
| `environment/` | board card config, build environment, host Python/serial setup |

## NPU timing adapters — CRITICAL measurement condition

FI101 has an NPU timing adapter in front of each NPU AXI port (`TA_SRAM` at `0x51102000`, `TA_EXT` at
`0x51102400`, TA_VERSION `0x1117`). Their state alone changed NPU-active cycles 3.7–7× on the same command stream
(`evidence/ta_ab/`). The vendor `test_u85` path never touches them; MLEK programs them at boot
(`ta_config_u85_sys_dram_mid`).

- **Every board measurement fixes the TA state explicitly** and records it with the data: the profile (blob header
  word 27 / packer `--ta-profile`: 1 = MLEK sys_dram_mid, 2 = pass-through) or the exact register values.
  "Untouched / reset state" is not a fixed condition — the reset values have never been read — and is not a baseline.
- **Every contract names the TA state** in its protocol, and every report and results table states it next to the
  numbers. A number without its TA state is not reported.
- **Changing the TA state is a change of measurement condition**, like changing the image or the Vela options:
  never mixed within one comparison, and stated wherever results from two TA states appear together.
- Comparing with MLEK requires TA profile 1. MLEK's board numbers are "FI101 + emulated SYS_DRAM_Mid".
- All runner results before boot 49 (on the old branch) were taken with the TAs untouched.

## Pipeline

1. **Blob** (container, `ssh gihwan` → `docker exec benchmark-runner`): `host/pack_vela_workload.py --vela-profile mlek`
   plus the knobs (`--ports`, `--axi-limit`, `--ta-profile`, `--fast-base`, `--power-ctrl`), and
   `host/screening_workload_meta.py <model> <out> mlek` for N_MAC and Vela's prediction.
2. **Image**: `make -f Makefile.pmu_events MODEL=1 all` in `/work/selftest` (gate `check_pmu_events.py` runs in
   `all`). Copy `firmware/` changes into the container first; back up `build_pmu_events_model` before rebuilding.
3. **Deploy** (owner runs sudo): `sudo sh ~/evsweep/deploy.sh <staging> ~/evsweep/evidence_<new>` — always a new
   evidence root. Restore reference for the original board image: `~/evsweep/evidence_m6`.
4. **Measure**: `sh ~/evsweep/run_campaign.sh <staging> <out> <ids> <plan>` (one boot per plan line, 35 RUNs).
5. **Analyse**: `host/screening_metrics.py <root>` (needs `<root>/workloads/*.meta.json`), then
   `host/ab_outcome.py <ctrl> <treat>` for a one-variable A/B against MLEK.
6. **Restore**: owner runs `sudo sh ~/evsweep/restore.sh ~/evsweep/evidence_m6`, then `sh ~/evsweep/postflight.sh`.

Board-host copies: `board/*` → `~/evsweep/`, `host/*.py` → `~/evsweep/host/`. Keep them in sync before a campaign.

## The one thing this project is about

**A check that cannot fail is worse than no check.** Every gate and every outcome rule gets mutation-tested:
neuter the check, run the suite, require RED; restore by digest (`shasum -a 256`), not by eye. A surviving
mutation means a missing fixture — add the fixture, do not delete the mutation.

- Tri-state, always: PASS / FAIL / **UNPROVEN**. Unproven is not "probably fine".
- Outcomes are preregistered values from a closed set. Contracts are frozen before the data exists; a superseded
  contract is recorded as an amendment, never edited away. A metric not preregistered is only reported later,
  labelled `POST_HOC_DESCRIPTIVE`.
- One variable per A/B. The control blob must be byte-identical to the previous baseline blob; the treatment
  differs in one header word. Knobs are read back on the board; a mismatch invalidates the RUN.

## Running the tests

`sh test.sh` from the repo root runs every module (unittest per module; `test_proto_unit.py` is a script).
`pytest` is not used. Clear `__pycache__` before trusting a result after editing or restoring a file.

## Traps already paid for

- A build that compiles is not an image that runs; record `NOT_EXECUTABLE` rather than dropping a cell.
- `model` validity mode does not use `run_rc`; a knob read-back failure (`PMWL_KNOB_NOT_HONOURED`, 0x7D) is visible
  only in `run_rc`. Check it until the validity rule covers it.
- Board restore is not "write the backups back": discover the destination set and abort if ambiguous.
- Hardware order: the UART listener must be alive before `REBOOT`; `USB_OFF` only after the reboot and never while
  the card is mounted. Enforced by the scripts' guards.
- PMU event names are generation-conditional (U85 emits `SRAM_*`/`EXT_*`); never hardcode by number across tools.
- The PMCCNTR window of this runner includes CPU staging copies; latency is `npu_active` cycles, never PMCCNTR.
- Fast scratch placement (DDR via SRAM port, DDR via EXT, on-chip SRAM) and POWER_CTRL do **not** move NPU cycles
  (A/Bs on the old branch); the TA state does.

## Standing constraints

- Pushing to `origin/main` — **HOLD**. Feature branches may be pushed.
- Never patch MLEK's `inference_runner` to obtain a metric. MLEK runs need a fresh authorization.
- Board access is granted per named step. The owner runs every `sudo` (deploy/restore) via
  `! ssh -t gihwan 'sudo …'`; credentials are never written to documents, evidence, commits, env vars or files.
- Never issue `USB_OFF` while the card is mounted.

## Reporting

```
검증 수준: [구문 | 단위 | 통합 | E2E]
실제 실행한 것: ...
실행하지 않은 것: ...
```

Every board number is reported with its TA state. "Syntax-checked" and "works" are different claims.
