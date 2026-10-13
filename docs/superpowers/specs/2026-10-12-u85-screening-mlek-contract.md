# Ethos-U85 screening 2 — MLEK-Vela-aligned (contract)

Frozen 2026-10-12, **before any board data of this run exists**. Authorization: owner, 2026-10-12 ("진행해보자"),
on step 1 of the proposal "align with MLEK where host-only changes allow". Same image, same events, same analysis
as screening 1 (`2026-10-12-u85-screening-contract.md`); this contract states only what differs.

## Why

Screening 1 compiled with the packer's Vela options, not MLEK's. A source comparison
(MLEK `b2c0bb2`, core-driver, vendor `u85.c`, runner patch) found these differences from an MLEK
`ethos-u85-1024` build on the same board:

| # | item | screening 1 | MLEK | this run |
| --- | --- | --- | --- | --- |
| 1 | Vela options | `Ethos_U85_SYS_DRAM_Low`, Vela's own ini, no arena cache limit | `resources.py run_vela()`: `--optimise Performance --config default_vela.ini --memory-mode=Dedicated_Sram --system-config=Ethos_U85_SYS_DRAM_Mid_1024` (ini: `arena_cache_size=393216`) | **MLEK's** (`--vela-profile mlek`) |
| 4 | AXI limits | vendor `0x21F3F` on both ports | driver: `AXI_SRAM = 0x20F0B` (12 rd / 16 wr / 256 B), `AXI_EXT = 0x21F3F` | **MLEK's** (`--axi-limit sram=0x20F0B,ext=0x21F3F`) |
| 2 | fast scratch memory | staging DDR (`0x9012_xxxx`) through the SRAM port | on-chip SRAM `0x3100_0000` (`.bss.NoInit.ethos_u_cache`) | unchanged — firmware change |
| 3 | timing adapter | not programmed | sse-320 default ON, `ta_config_u85_sys_dram_mid` | unchanged — firmware change |
| 5 | PMU window | runner arm → CPM seam (incl. staging) | `ethosu_inference_begin/end` around the job | unchanged (M1 is `npu_active`, unaffected) |
| 7 | CPU side | no TFLM, D-cache off | TFLM, D-cache on | unchanged |

Region→port mapping (cmd/const/arena EXT, fast SRAM port) and MEM_ATTR values already match MLEK's
`Dedicated_Sram` driver defines; unchanged.

So this run is **"MLEK-Vela-aligned"**, not "MLEK": the command stream and AXI limits are MLEK's; the memory
behind the SRAM port, the timing adapter and the CPU side are not. Results are never labelled as MLEK results.

## Pre-data facts (static, already established)

- Reproduction check: the `mlek` option list with `ethos-u85-256` / `Ethos_U85_SYS_DRAM_Low` reproduces MLEK's
  shipped `*_vela_Z256.tflite` **byte for byte** for kws_micronet_m, mobilenet_v2, ad_medium_int8. MLEK ships no
  Z1024 file, so the 1024 output itself has no MLEK reference; only the option list is verified.
- Default packer profile regression: kws blob unchanged (`ebd54a85…`).
- Vela output differs from screening 1 for 4 of 5 workloads; matmul's is identical (only the AXI_SRAM knob
  differs). mobilenet fast scratch 1,510,336 → 385,968 B (≤ 393,216). Metadata: `evidence/u85_screening_mlek/workloads/`.

## Protocol

As screening 1: MODEL image APP `0f215ef5…` (on the card), one boot per workload, `--keep-model --validity model
--repeats 35`, the same 8 ids, RUNs 1–5 warm-up. Boots **29–33** in the order kws, mobilenet, ad_medium,
conv3x3, matmul. Ports `cmd=ext,const=ext,arena=ext,fast=sram`. Fallback as screening 1 (all-EXT once,
not pooled).

## Analysis (committed with this contract, unchanged after data)

- `host/screening_metrics.py evidence/u85_screening_mlek` — unchanged code; per-workload outcome from the same
  closed set (`SCREENED` / `UNPROVEN` / `NOT_EXECUTABLE`). M7 uses this run's Vela prediction
  (Mid_1024, `core_clock` 1 GHz); it is still prediction vs observation, with the clock caveat.
- `host/screening_compare.py evidence/u85_screening evidence/u85_screening_mlek` — per workload: cms changed
  (Vela output digest) and the ratio of medians (run 2 / run 1) for npu_active, M3, M4, M5 and the three stall
  ratios. Ratios only where both runs are SCREENED. Descriptive; no threshold, no "better/worse".

## What this run does not claim

- Not an MLEK measurement (differences 2, 3, 5, 7 remain).
- A ratio ≠ 1 is not attributed to a single cause: Vela options and AXI_SRAM change together in this run
  (except matmul, where only AXI_SRAM changes).
- No bytes, no ms (as screening 1).
