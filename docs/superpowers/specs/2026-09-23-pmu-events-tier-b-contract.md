# PMU event counting (Tier B) — measurement contract

Frozen 2026-09-23, **before any data exists**. Amend by a new file; never edit.
Depends on: Tier A contract + amendment 1 (every EV_TYPE encoding reads back;
acceptance therefore proves nothing about counting — that is what this asks).

## Question

For each of the 171 EV_TYPE ids the Arm driver names (110 of which the public
TRM documents), does the counter **count** during the fixed U85 Convolution
inference on FI101? "Count" is a closed verdict, below. No interpretation of
the values is preregistered beyond two consistency checks.

## Authorization

Board access for Tier B approved verbally by the project owner on 2026-09-23
(same grant as Tier A, extended to Tier B by explicit answer). Only the fact
is recorded. SD-card mount and card restore are performed by the operator.

## Firmware: `Makefile.pmu_events` — a generated copy of the base runner

`patches/patch_pmu_events_source.py` applies exact-once anchored replacements
to `Selftest_pmu/runner_pmu_main.c` (sha256 pinned:
`b95b11b0cbddceefa8940515b8965be0d1132ea209ba32e12dbf4fefa95e41a2`) and
emits the generated main under the build directory. The base file is not
edited. Production `END_ONLY` behaviour is unchanged: mode 1 still refuses
`count != 0`, still arms only the cycle counter.

New mode `INSTRUMENTATION_EVENTS = 2`:
- `SET_INSTRUMENTATION_MODE(mode=2, set_id, count 1..8, codes[8])` accepted.
- Run path = END_ONLY's bracket **plus**: before enable, `PMEVTYPER[i] =
  codes[i]` for `i < count` and `PMCNTENSET |= (1<<count)-1`; after disable,
  `event_values[i] = PMEVCNTR[i]`, `event_overflow_mask = PMOVSSET[7:0]`,
  `applied_event_count = count`, `event_valid_mask = ((1<<count)-1) & ~overflow`.
- Capabilities advertise bit 2. Build id ASCII "PMEV" = 0x504D4556.
- Everything else (poison, golden window, cycle counter, provenance) as base.

Gates: existing measured-path denylist gate (clean profile) **and**
`check_pmu_events.py` on the linked ELF: `apU85Conv_TEST` IS linked (this
image must run inference — the inverse of Tier A's rule), PMEVTYPER0 literal
present, build id present, generated source carries mode 2. Every rule has a
fixture; tripped set == RULES.

## Procedure — ONE deploy, ONE boot, 66 RUNs

Event sets: the 171 driver ids sorted ascending, chunked into **22 sets of 8**
(set 21 has 3 ids; `count=3`, no padding — `event_valid_mask` is the authority,
never code 0). `set_id` = 1..22.

For `set in 1..22`, for `rep in 1..3`:
```
SET_INSTRUMENTATION_MODE(EVENTS, set_id, count, codes)   -> must ACK, applied==2
RUN                                                       -> ACK, RUN_COMPLETE(record)
```
66 runs total on one boot, host-boot-index recorded. The stock runner supports
repeated RUNs on one boot (run_pmu_cfg.py: "ten consecutive runs on that boot").
If any run NACKs or times out, the campaign **stops** and is reported partial;
no set is re-run to fill a hole.

## Per-run validity (preregistered, all required, else the run is INVALID)

```
rc == 0
required_flags_ok()                       (record's valid_flags, as host defines)
npu_pmu_cycle_valid == 1
instrumentation_mode_applied == 2
applied_event_count == count
event_valid_mask == (1<<count)-1          (no overflow in any armed slot)
event_codes[i] == codes[i] for i < count
```
An INVALID run is archived, never dropped, never re-run.

## Verdict per event id — closed set, from its 3 repeats

| verdict | condition |
| --- | --- |
| `COUNTED_NONZERO` | all 3 runs valid, all 3 values > 0 |
| `COUNTED_ZERO` | all 3 runs valid, all 3 values == 0 |
| `INCONSISTENT` | all 3 runs valid, values mix zero and nonzero |
| `NOT_OBSERVED` | fewer than 3 valid runs for this id |

Zero is a result, not an absence: `ecc_*` at zero cannot distinguish "no ECC
error occurred" from "ECC not configured"; `sram2_*`/`sram3_*` at zero cannot
distinguish "port absent" from "port idle". The verdict records the number;
the document that reads it must not upgrade it.

## Two preregistered consistency checks (P1, PASS/FAIL/UNPROVEN)

1. `CYCLE_EVENT_VS_PMCCNTR`: for id 17 (`cycle`), each valid run:
   `|event_value - window_cycles| / window_cycles <= 0.01` → PASS; else FAIL.
   (window_cycles = PMCCNTR lo|hi<<32; if window overflowed → UNPROVEN.)
2. `NPU_ACTIVE_LE_CYCLE`: for id 35, each valid run: `event_value <= window_cycles`
   → PASS; else FAIL.

Nothing else is computed from this data. Anything further is `POST_HOC_DESCRIPTIVE`.

## Refusal rules (host-side, each carries its id)

```
RULE_PING                 PING fails or protocol != measure-v2 before the first set
RULE_CAPABILITY           capabilities do not advertise mode 2 (wrong image on the card)
RULE_MODE_NACK            SET_INSTRUMENTATION_MODE NACKed or applied != 2
RULE_RUN_TRANSPORT        RUN NACK / timeout / sequence error (campaign stops)
RULE_RECORD_SCHEMA        record_schema_version != 1 or field count != 102
RULE_CODES_ECHO           event_codes in record != codes sent
RULE_SET_COVERAGE         final ids covered != 171 (partial campaign is refused as a
                          complete record; archived as partial)
```

## Record schema (`evidence/pmu_events/<boot>/runs.csv`, one row per run per slot)

```
set_id,rep,slot,ev_type,name,in_trm110,event_value,event_valid,event_overflow,
run_rc,run_valid,invalid_reasons,window_cycles,cycle_valid,output_crc,valid_flags,
board_serial,fpga_image,build_id,app_sha256,vectors_sha256,ddr_sha256,
host_boot_index,captured_at_utc,authorization
```
`per_event.csv` (171 rows): verdict, three values, where/how, boot, digests.

## Ordering guards

UART is the runner link itself (no separate capture). REBOOT precedes the
session; the host verifies `PING` counters are all zero before the first set.
Card restore after the campaign follows the Tier A restore script; `USB_OFF`
only after the post-restore REBOOT.
