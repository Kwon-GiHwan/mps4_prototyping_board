# MPS4 / Ethos-U85 PMU measurement

PMU measurements of an Arm Ethos-U85 (1024 MAC) on the MPS4 FI101 FPGA board, driven by a custom runner
(vendor selftest `test_u85` + PMWL workload blobs), compared against stock MLEK on the same board.
Bare-metal Cortex-M85, `arm-none-eabi-gcc 15.2.1`, `-O1 -g3`.

History before the cleanup (V13–V15, paper campaign, Tier A/B/C, screenings 1/2, earlier A/Bs) lives on branch
`refactor/unified-mlek-campaigns` (last commit `fe7541b`). Paths quoted inside frozen `docs/specs/` and `evidence/`
are as they were when written: flat `host/*.py` until the split into `host/{lib,container,board,analysis}` after
`570c4a0` (e.g. `host/baseline_gate.py` = `host/analysis/baseline_gate.py`).

**History rewritten 2026-10-27** to remove a file that held a credential: every commit from 2026-09-08 on has a
new hash. Hashes quoted in `docs/specs/`, `evidence/` and older commit messages are the old ones; look them up in
`environment/history_rewrite_20261027.tsv` (old → new).

## Layout

| dir | what |
| --- | --- |
| `host/` | split by where code runs: `lib/` (shared modules), `container/`, `board/` (board host), `analysis/` (Mac); `tests/` |
| `firmware/` | our sources on top of Arm's FI101 selftest tree, **copied to `/work/selftest` in the container path-for-path**: `common/` (NPU registers, PMU, timing adapters, timestamps; shared), `runner/` (measurement runner: protocol, measured RUN, PMWL blob, printf seams), `study/conv1x1/` (register-level study image), `gate/` (build gates), `vendor/` (generated copy of Arm's `u85.c` with the raised timeout and the POWER_CTRL hook; Arm's file is never edited), `LinkScripts/` overlay, `Makefile.npu_runner`, `Makefile.study`. Arm's vendor tree itself stays in the container. |
| `board/` | board-host scripts (synced to `~/evsweep` on `ssh gihwan`): deploy/restore/postflight/inspect, MCC helpers, `run_campaign.sh`; MLEK image set (boot/bram/ddr.bin + images.txt): `deploy_mlek.sh`/`restore_mlek.sh`, app-UART capture `mlek_app_capture.py` |
| `config/` | **stage-0 profile** `mlek_baseline.json` (35 RUNs, 5 warm-up); `mlek_r10.json` = the same conditions with 10 RUNs (2 warm-up) on the restructured runner image `38ce118c`, for new measurements from 2026-10-27; PMU sets `baseline_ids.txt` (stage 0) / `stage1_ids.txt` / `stage2a_ids.txt`, blob manifests `mlek_baseline.manifest.json` (kws, ad) and `.a1.json` (mobilenet, amendment 1) |
| `docs/reference/` | PMU event lists (TRM 110, driver 171), PMU reference, MLEK board reference values |
| `docs/specs/` | frozen contract in force: `mlek-baseline.md` (profile, per-run gate, outcome, amendment 1); Stage 1 contract: `evidence/stage1/contract.md` |
| `evidence/` | `stage2a/` (boots 75–77, component attribution; event audit, dw3x3 MLEK golden), `stage1/` (boots 65–71 = dataset s1; boots 72–74 = dataset a2 under amendment 2, MLEK goldens in `stage1/a2/mlek_golden/`), `mlek_baseline/` (boots 59–61), `mlek_baseline_a1/` (boot 64, amendment 1), `mobilenet_ofm/` (three-way OFM comparison), `runner_gap/` (static diff, `mlek_diff_audit.md`); summaries only: `ta_ab/` (the TA finding), `tools_check/` (refactor verification) — raw data at `2ce4512` |
| `environment/` | board card config, build environment, host Python/serial setup |
| `results/` | reading copies grouped for a question; originals stay in `evidence/`: `npu_utilization_mps4/` (MLEK models kws, ad, mobilenet from Stage 1: raw per workload, `summary.csv`, `npu_utilization.csv`); `npu_utilization_fvp/` (same layout, all seven MLEK models on FVP U85-1024 from the old branch; no MAC_ACTIVE) |

### host modules

| module | owns | used by |
| --- | --- | --- |
| `lib/pmwl.py` | PMWL blob format: header/knob word layout, knob encoding, TA profile tables, pack, parse_header | packer, driver |
| `lib/reference.py` | event lists (TRM 110 / driver 171), MLEK board NPU ACTIVE and B1 counters | parser, driver, gate |
| `lib/results.py` | runs.csv loading, warm-up/measured window, event names | gate |
| `lib/runner_proto.py` | UART protocol to the runner firmware | driver, board/postflight.sh |
| `lib/pmu_events_parse.py` | event sets, per-RUN validity, verdicts, refusals | driver |
| `lib/mlek_profile.py` | frozen profile → `pmwl.knobs()` arguments | packer, gate |
| `analysis/ofm_compare.py` | MLEK VERIFY_TEST_OUTPUT dump parsing, byte-by-byte OFM comparison (int8) | output verification |
| `analysis/mlek_golden.py` | amendment-2 golden validity G1–G5 (MLEK FI101 dump vs blob meta) → manifest entry with the TFLite diagnostic | before every amendment-2 boot |
| `analysis/baseline_gate.py` | stage-0 per-run gate (B1–B3, R1–R6) and the MLEK-equivalence outcome | Mac, after every baseline campaign |
| CLI | `container/pack_vela_workload.py`, `container/make_op_model.py` (single-op INT8 tflite as flatbuffers), `container/workload_meta.py` (N_MAC, Vela prediction); `board/run_pmu_events.py`; `analysis/baseline_gate.py`, `analysis/ofm_compare.py`, `analysis/stage1.py` (Stage 1 gate, metrics, fingerprint), `analysis/stage2a.py` (Stage 2A metrics, reproduction, hypothesis status, routing) | |

A constant or layout lives in exactly one host module; scripts import it. **Host ↔ firmware is the exception, on
purpose:** the runner firmware declares the PMWL layout and TA tables independently (`firmware/runner/pmwl.c`,
`firmware/common/ta.c`), and `host/tests/test_pmwl_firmware_contract.py` requires the C to agree with `pmwl.py`. Never make one side
import the other — a copy agrees with itself and proves nothing. Tests must not read their expected values back
from the module under test.

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

1. **Blob** (container, `ssh gihwan` → `docker exec benchmark-runner`): `python3 /work/mps4_host/host/container/pack_vela_workload.py` (Vela options fixed to MLEK's)
   with `--profile /work/mps4_host/config/mlek_baseline.json` (the default condition: every knob, seed and the Vela version
   come from the profile) — or, for a one-variable A/B arm only, explicit knobs (`--ports`, `--axi-limit`,
   `--ta-profile`, `--fast-base`, `--power-ctrl`). A new profile blob gets its digests into the manifest.
2. **Image**: `make -f Makefile.npu_runner all` in `/work/selftest` (gates `gate/check_measure_symbols.py` and
   `gate/check_runner.py` run in `all`). `sh sync.sh container` first; back up `build_npu_runner` before rebuilding.
3. **Deploy** (owner runs sudo): `sudo sh ~/evsweep/deploy.sh <staging> ~/evsweep/evidence_<new>` — always a new
   evidence root. Restore reference for the original board image: `~/evsweep/evidence_m6`.
4. **Measure**: `sh ~/evsweep/run_campaign.sh <staging> <out> <ids> <plan> [repeats]` (one boot per plan line;
   repeats = the profile's: 35 for `mlek_baseline`, the default; 10 for `mlek_r10`). Analyse with the same profile
   (`host/analysis/stage1.py … --profile config/mlek_r10.json`); the gate refuses a RUN count or image the profile
   does not name.
5. **Analyse**: baseline-profile data is used only after `host/analysis/baseline_gate.py <root>/base` gives `BASELINE_PASS` for the workload (`docs/specs/mlek-baseline.md`).
   Mobilenet uses amendment 1: blob golden = MLEK FI101 OFM on MLEK's input, gate with
   `--manifest config/mlek_baseline.manifest.a1.json`. The TFLite difference is a diagnostic, never pass/fail.
   **Amendment 2** makes this the general rule for every run after Stage 1 boots 65–71: golden = MLEK FI101 OFM on
   MLEK's input, accepted only through `host/analysis/mlek_golden.py` (G1–G5), hashes fixed in the manifest first.
6. **Restore**: owner runs `sudo sh ~/evsweep/restore.sh ~/evsweep/evidence_m6`, then `sh ~/evsweep/postflight.sh`.

Before every campaign: `sh sync.sh board` and `sh sync.sh container` (copy with repo-relative paths, then verify by
sha256; `sh sync.sh check` only verifies). Every copy keeps the repo layout (`host/lib`, `host/board`, `docs/reference`, `config`); `lib/reference.py` finds the event lists at
`host/lib/../../docs/reference`, so `docs/reference/` must sit beside `host/` there too — never copy modules alone.

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
- `model` validity mode does not require `run_rc == 0` (vendor rc is judged instead). A knob read-back failure
  (`PMWL_KNOB_NOT_HONOURED`, 0x7D) is caught by the `knobs_honoured` term since `f39eca8`; RUNs archived before
  that commit were not checked by it. `baseline_gate.py` additionally requires `run_rc == 0` and an exact OFM.
- Board restore is not "write the backups back": discover the destination set and abort if ambiguous.
- Hardware order: the UART listener must be alive before `REBOOT`; `USB_OFF` only after the reboot and never while
  the card is mounted. Enforced by the scripts' guards.
- PMU event names are generation-conditional (U85 emits `SRAM_*`/`EXT_*`); never hardcode by number across tools.
- The PMCCNTR window of this runner includes CPU staging copies; latency is `npu_active` cycles, never PMCCNTR.
- Fast scratch placement (DDR via SRAM port, DDR via EXT, on-chip SRAM) and POWER_CTRL did **not** move NPU cycles
  in A/Bs on the old branch — all taken with the TAs untouched; the TA state does.
- Still different from MLEK and untested (`evidence/runner_gap/mlek_diff_audit.md`): no soft reset/PROT, vendor
  CFG_*_CAP writes, CPU busy-polling from on-chip SRAM with caches off (MLEK: WFE, caches on).

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
