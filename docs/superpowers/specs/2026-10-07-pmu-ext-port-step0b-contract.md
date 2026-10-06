# Tier C step 0b — EXT AXI port with tensors at a DRAM alias (contract)

Frozen 2026-10-07, **before any data exists**, after step 0 = EXT_UNREACHABLE
(`evidence/pmu_events_c/VERDICT.md`). Authorization: owner, 2026-10-07.

## Question

Step 0 showed the EXT port cannot serve the 0x9000_0000 "DDR4 Dev Access" alias (IDAU 9). The FI101 map
puts the EXT managers' targets (DRAM0/1) at IDAU 6 (NS) / 7 (S). (Q1) With the same 1×1 job's tensors
copied to S DRAM `0x7010_0000` and MEM_ATTR on the EXT port, does the job complete correctly?
(Q2) Which `ext_*` counters count?

## The change (build `EXT=1 DRAM=1`, build id "PMXD" 0x504D5844)

Vendor files unedited; u85.o built with `-DUSE_AXI_EXT=1` as in step 0. The linker wraps `test_u85`
(`--wrap=test_u85`). `__wrap_test_u85` (generated runner, only under `PMU_EVENTS_EXT_DRAM`):
1. copies cmd (qsize B), weights (0x600), in (0x400), scratch (0x300) from the vendor's own pointers to
   `0x7010_0000 + {0x0000, 0x1000, 0x2000, 0x3000}`;
2. fills the DRAM output (`+0x4000`, out_size B) with 0xA5 — stale DRAM must never pass as output;
3. calls `__real_test_u85` with a copy of the vendor's struct whose cmd/weights/in/scratch/out point at
   DRAM (out_ver unchanged → the vendor's own memcmp judges the DRAM output);
4. copies the DRAM output back to the vendor's `out_data_0` (0x90020CC0) and returns the vendor's rc.
Runner entry (`apU85Conv_TEST`), poison/CRC, golden window, EVENTS mode, CPM seam: unchanged.
Gate: in this build `__wrap_test_u85` linked and the three copied sizes equal the linked `nm -S` sizes of
`test3_weights`/`test3_in_data_0`/`test3_scratch_buffer`; in every other build `__wrap_test_u85` absent.

## Procedure, validity, event verdicts

Identical to step 0 (22 sets × 3, golden check per RUN, ten validity terms, closed event verdicts).

## Reachability verdict (Q1) — closed set

| verdict | condition |
| --- | --- |
| `EXT_DRAM_REACHABLE` | ≥ 1 valid run |
| `EXT_DRAM_WRONG_OUTPUT` | every run rc 0 or rc returned, but no run has golden_ok |
| `EXT_DRAM_UNREACHABLE` | rc ≠ 0 on every run with no golden_ok |
| `DRAM_ALIAS_INACCESSIBLE` | set 1 rep 1 refused by `RULE_RUN_TRANSPORT` (hang/fault; CPU-side and NPU-side not distinguished) |

The preregistered comparison with Tier B (same/different verdict per id) applies only if REACHABLE.
