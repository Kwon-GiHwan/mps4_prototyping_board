# PMU EV_TYPE sweep (Tier A) — measurement contract

Frozen 2026-09-23, **before any data exists**. Amend by a new file; never edit.

## Question

Which 10-bit `EV_TYPE` encodings does the Ethos-U85 PMU in FI101 (109762 v0100,
1024 MAC) accept into `PMEVTYPER<n>`? "Accept" = the value read back equals the
value written. This is a register-level fact and needs no inference, no model,
no MLEK, and no change to any existing runner. END_ONLY is not touched.

It does NOT answer whether an accepted encoding *counts* anything. That is Tier B.

## Authorization

Board access for this step was granted verbally by the project owner on
2026-09-23. Only the fact of approval is recorded. No credential is handled by
the agent; the SD-card mount and REBOOT are performed by the operator.

## Procedure (target side, `Selftest_pmu_evsweep/runner_pmu_evsweep_main.c`)

Boot -> UART0 115200 -> print header -> sweeps -> footer -> idle forever.

```
HDR: build_id, PMCR, CONFIG (raw), PMCR.num_event_cnt
P0:  PMCR.cnt_en = 0.  slot 0:      for ev in 0..1023: write, DSB, readback
P1:  PMCR.cnt_en = 1.  slots 0..7:  for ev in 0..1023: write, DSB, readback
END: restore PMEVTYPER[0..7]=0, PMCNTENCLR=all, cnt_en=0. print footer.
```

Written value is `ev` only (bits [9:0]); D0..D3 and all other bits are 0.
Readback is recorded in full (32 bits) and compared on bits [9:0].

P0 exists because the TRM states PMU writes other than `PMCR.cnt_en` are not
guaranteed to take effect unless `cnt_en=1`. **P1 is the citable pass. P0 is a
control** whose only preregistered use is to confirm or refute that note.

## Wire format (UART0, ASCII, `\n` terminated)

```
EVSWEEP-HDR,<build_id_hex>,<pmcr_hex>,<config_hex>,<num_event_cnt>
EV,<pass>,<slot>,<ev>,<readback_hex>
...
EVSWEEP-END,<line_count>,<crc32_hex>
```

`line_count` = number of `EV,` lines. `crc32` = CRC-32 (IEEE, as zlib) over the
concatenation of every `EV,` line including its `\n`. Expected `line_count` =
1024 + 8*1024 = 9216. Any other count, or a CRC mismatch, refuses the record.

## Verdict per (pass, slot, ev) — closed set, assigned by the host

| verdict | condition |
| --- | --- |
| `ACCEPTED` | readback[9:0] == ev and readback[31:10] == 0 |
| `COERCED_TO_ZERO` | readback[9:0] == 0 and ev != 0 |
| `COERCED_OTHER` | readback[9:0] not in {ev, 0} |
| `UPPER_BITS_SET` | readback[9:0] == ev but readback[31:10] != 0 |

No other verdict may be written. A readback that fits none is a parser bug and
refuses the record (`RULE_VERDICT_UNCLASSIFIABLE`).

## Preregistered summaries (P1 only)

- accepted set per slot; the 8 sets must be identical, else `SLOT_DISAGREEMENT`.
- accepted ∩ TRM-110 named, accepted ∩ driver-61 reserved, accepted ∖ driver-171.
- P0 vs P1 accepted sets: EQUAL / P0_SUBSET / DIFFERENT.

Nothing else is computed from this data. Anything further is `POST_HOC_DESCRIPTIVE`.

## Refusal rules (each carries its id)

```
RULE_HDR_MISSING           no EVSWEEP-HDR before first EV line
RULE_END_MISSING           no EVSWEEP-END
RULE_LINE_COUNT            EV line count != END line_count or != 9216
RULE_CRC                   CRC32 over EV lines != END crc32
RULE_DUP_CELL              (pass,slot,ev) seen twice
RULE_VERDICT_UNCLASSIFIABLE readback fits no verdict
RULE_BUILD_ID              header build_id != 0x45565357 ("EVSW")
RULE_NUM_EVENT_CNT         header num_event_cnt != 8
```

## Record schema (per cell, `evidence/pmu_evsweep/<boot>/cells.csv`)

```
pass,slot,ev,written_hex,readback_hex,verdict,
board_serial,fpga_image,build_id,app_sha256,vectors_sha256,ddr_sha256,
uart_log_sha256,captured_at_utc,authorization
```

`authorization` is the literal string `owner-verbal-2026-09-23`.

## Ordering guards (operator-facing)

1. UART capture (`host/run_pmu_evsweep.py capture`) is running **before** REBOOT.
2. `USB_OFF` is issued only after the card is unmounted, and after REBOOT.
The capture refuses to write a record if the header arrives before the capture
timestamp (`RULE_HDR_MISSING` covers a late start; a stale header from a prior
boot is refused by `RULE_BUILD_ID` if the prior image differs, and is otherwise
indistinguishable — so the operator confirms REBOOT happened after capture start).
