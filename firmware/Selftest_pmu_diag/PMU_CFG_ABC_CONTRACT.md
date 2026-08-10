# PMU_CFG A/B/C — frozen board procedure contract

**CHARACTERIZATION ONLY.** Nothing produced under this contract is latency,
T_npu, a performance number, a performance baseline, a Production GO, Gate 7,
or MLEK data. The `+514` identity observed in the Gate 1 fixed-image Q1
campaign is **not** generalized to these images. The single quantity collected
is `npu_pmu_window_cycles`, a PMU cycle-counter window over the vendor call,
for one case of one build.

This file is the frozen reference for the campaign. It is written **before** any
board work so that the deployment, the schedule and the evidence layout are
decided in advance and cannot be adjusted after seeing a number. Any change to
this document after the first boot invalidates the campaign.

---

## 1. What is being varied, and what is not

The three images are byte-identical apart from **one source action**, the
`PMCCNTR_CFG` case block:

| Case | Build ID | `PMCCNTR_CFG` action | Writes | Final register value |
|------|----------|----------------------|--------|----------------------|
| A | `0x31414350` (`PCA1`) | none at all | 0 | 0 |
| B | `0x31424350` (`PCB1`) | generated `START=CYCLE / STOP=NO_EVENT` | 1 | the generated value |
| C | `0x31434350` (`PCC1`) | generated explicit zero | 1 | 0 |

Held fixed across all three: the anchored `runner_pmu_diag_main.c`, Q1 H-PRINTF
behaviour (same callsite, same hook, same internal pre-release snapshot, same
disable/DSB/readback order), the vendor driver with `TEST_CPM=1` and its own
terminal `CMD=0xC` release, seam S1, the clean profile, the golden window, and
every compiler and linker flag. `check_pmu_cfg.py` proves this statically and
`matrix_check` proves it across the three manifests.

---

## 2. Frozen build identity

These digests were produced by `check_pmu_cfg.py` in the authoritative
container build and are frozen here. They are also embedded as constants in
`host/analyze_pmu_cfg.py` (`PMU_CFG_FROZEN`), which refuses any sample whose
archived manifest bytes or deployed BIN hashes are not these exact values.
**The two copies must agree; `host/tests/test_pmu_cfg_analyzer_unit.py` asserts
the analyzer's copy verbatim.**

### Case A — `PCA1`

```
manifest     49da8efc6ae30840b07ca93fa8d4723fae5429f8469daee9d1ae3a044bbafb00
APP.BIN      b9cbea463617264116f3e80eccb2517cc6322f93643a5d307fc209022234e789
VECTORS.BIN  5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9
DDR.BIN      81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
```

### Case B — `PCB1`

```
manifest     5e87cc018d2715acaaf5f4af41e297a7e162dd30232ab98e2873dece5488b082
APP.BIN      535809259bf1b2dc4ad521c2e38aba99abf826e1393d2ded210a6daf4a25fe36
VECTORS.BIN  c0cd22e5f88cd2f5de0572f222d8e0e0a658877507e39bdffa4da3b7088fee4f
DDR.BIN      81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
```

### Case C — `PCC1`

```
manifest     a0a39fa6cdc540100db599815c34b20c8abf83e24876a52597d38b51778715b4
APP.BIN      00b24f0d3b8c0dfec9c271ad5e216168b5b1c2c71726d911e8c3709e8a32cdbe
VECTORS.BIN  b498835ad63e18030799699868e0fed8e6c8395d5164181662b1c7535aba88d5
DDR.BIN      81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
```

`DDR.BIN` is deliberately identical in all three builds — it is the same model
payload. `APP.BIN` and `VECTORS.BIN` differ because each case is a separate
link. A campaign in which two cases carry the same `APP.BIN` did not vary the
single variable and is refused.

### ELF and .map digests — FROZEN

The `.elf` and `.map` files are not deployed-BIN JSON fields, so
`analyze_pmu_cfg.py` cannot check them from a board sample. They remain a human
review gate: the staged files and the authoritative container build were
re-hashed before the first boot and must retain these exact values.

```
Case A  ELF 38ed9abc2e4470d7ab1253ed3cda1ce3674321adbe8c07863029606faca8df52
        MAP e13bc85d8a35af838432173b00f0d6ac8c7ce9c83ad31982943abb4533c6bd11
Case B  ELF 63bdf4a3db4bff8ccd71eff16b35e910e51c0a40042119800dc7f0441bbfd10e
        MAP 35e190f586cc8b32ebc18b3e90a1bbe259c6b0fe7b4b6c5f68eeedf8413dd256
Case C  ELF 153ef4eddaf4878802d0a5daf6aa889af5ed336acb5215332bf852bc331ff56d
        MAP e8e63415bafd04de75cfb2dc419f74283112466e6807c3c643fbea62d88c4097
```

Extract with:

```bash
docker exec benchmark-runner sh -c \
  'cd /work/selftest && for c in a b c; do \
     sha256sum build_pmu_cfg_$c/*.elf build_pmu_cfg_$c/*.map; done'
```

---

## 3. Pre-board staging — SATISFIED, re-verify before deployment

Initial read-only preflight found that the three builds existed only in the
`benchmark-runner` writable layer. They have now been copied to this host
evidence root without touching the board, SD card, or UART:

```
/home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging/build_pmu_cfg_a
/home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging/build_pmu_cfg_b
/home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging/build_pmu_cfg_c
```

Each source and destination tree contains 119 files. Full-tree rollups matched
after `docker cp` when sorting was explicitly pinned with `LC_ALL=C`:

```
A  6b5d210d836676a9ea8e966802c3c7454e613166929c358f72b5396b69be6e06
B  02d83d9be9e988693d4e0d3fb72ff6ebbac2b6bb5b69fc2df2044601b5225330
C  6244f804ae4649f72414bd7fa3e70bdbc69afc317464079d55ae99d22f71b21a
```

All 18 selected manifest/APP/VECTORS/DDR/ELF/map digests match the frozen digest
blocks in section 2. At staging time `/dev/sdb` was absent and nothing was mounted. The
container still has only `/models`, `/results`, and `/scripts` bind-mounted;
`/work/selftest` is not host-backed.

The exact host tools copied to
`/home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/host-tools/` are frozen as:

```
runner_proto.py     4c1cc3a524bf385734bdf093540cd175a98a7184bfa3de95fd0a1d228426288e
run_pmu_qual.py     704a768aa71c0ee06eaaccb9b10ca4ee2530af98b5d1a7436bd9f42ffe87583f
run_pmu_cfg.py      57af9385742228a85e1f5b876c2e13ad89b3e89011ee01cff545e7222ec6cb27
analyze_pmu_cfg.py  edf90b840fb8445de82d6ca7d8318aee31ea7a4ea88dd70022a1f930ac026837
```

> **Deleting or recreating the container destroys the only copy of these
> builds.** The campaign cannot be re-run against the same frozen digests if
> that happens.

Before **each** SD deployment, re-hash the staged case and compare it to
section 2. If the host staging root has disappeared, repeat the copy
and full-tree comparison; do not silently rebuild:

```bash
# 1. Use the frozen host staging root.
stage=/home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging

# 2. Copy each build tree out of the container.
test -d "$stage/build_pmu_cfg_a"
test -d "$stage/build_pmu_cfg_b"
test -d "$stage/build_pmu_cfg_c"

# 3. POST-COPY BYTE VERIFICATION. A copy is not evidence until it is verified.
for c in a b c; do
  ( cd "$stage/build_pmu_cfg_$c" && sha256sum APP.BIN VECTORS.BIN DDR.BIN \
      pmu_cfg_manifest.json *.elf *.map )
done
# Compare every line against section 2. A single mismatch STOPS the campaign.
```

If a full-tree source/destination rollup is repeated, both `find`/path sorting
pipelines must run with `LC_ALL=C`. The recorded rollups are locale-dependent
as text even though the 357 files are byte-identical; using the host default
`en_US.UTF-8` produces different rollup text and a false STOP.

Check free space before the campaign and preserve the staging root. Deleting or
recreating the container still destroys its writable-layer copy.

---

## 4. The balanced schedule — 9 cells, 9 fresh boots, 90 samples

| Round | Position 1 | Position 2 | Position 3 |
|-------|-----------|-----------|-----------|
| R1 | **A** | **B** | **C** |
| R2 | **B** | **C** | **A** |
| R3 | **C** | **A** | **B** |

Every case appears once per round and once in every position. That is what
prevents a position effect (warm-up, drift, thermal) from being confounded with
a case effect.

Rules, all enforced by `analyze_pmu_cfg.py`:

1. **One cell = one image deployment = one fresh boot = ten consecutive runs.**
2. The ten repeats come from **one** boot. Between repeats only the runner
   protocol state is reset and re-primed; the MCU is never rebooted and no
   power path is touched.
3. The target's `run_sequence` must read exactly **1, 2, … 10**. A first record
   that is not 1 means the boot was not fresh; a gap means a run was lost or a
   latch was re-served.
4. **Nine distinct `--host-boot-index` values**, one per cell.
5. Read in schedule order (R1P1, R1P2, R1P3, R2P1, …) the boot indices must be
   **strictly increasing**. Gaps are allowed — a failed or preflight boot
   legitimately consumes an index — but the order must match the declared
   schedule, or the cells were not run in the order the balance assumes.
6. Cells are executed **in schedule order**. Do not reorder to "get A out of
   the way".

Per cell:

```bash
/usr/bin/python3 /home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/host-tools/run_pmu_cfg.py \
  --case B --round 1 --position 2 --host-boot-index 23 \
  --bins-dir /home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging/build_pmu_cfg_b \
  --manifest /home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/staging/build_pmu_cfg_b/pmu_cfg_manifest.json \
  --out-dir /home/gihwan/mps4/PMU_CFG_V8_20260810T022525Z/results/cfg_campaign/cfg_R1P2_B
```

Use `/usr/bin/python3` on `gihwan`: it is Python 3.12.3 with pyserial 3.5. The
project venv currently lacks pyserial and is not an admissible collector
runtime. Boot 23 in the example is the nominal R1P2 allocation after R1P1 uses
22; if a failed/preflight boot consumes an index, bump it rather than reusing
an index.

The deploy / reboot mechanics (Standby, `USB_ON`, mount, file replacement,
`sync`, unmount, `USB_OFF`, `PBON`) are **not restated here**: follow
`PMU_QUAL_PROCEDURE.md`. In particular use `udisksctl mount -b /dev/sdb1`, and
its §8 `2-EXC` path only under explicit operator approval.

The frozen `DDR.BIN` is identical to the currently deployed and backed-up DDR
payload, so a CFG cell deployment replaces only `APP.BIN` and `VECTORS.BIN`.
Still re-hash all three destination files after deployment; equality is a gate,
not permission to skip verification.

---

## 5. Evidence layout

```
results/cfg_campaign/
  cfg_R1P1_A/  cfg_A_round1_pos1_boot<N>_repeat01.json … repeat10.json
  cfg_R1P2_B/  cfg_B_round1_pos2_boot<N>_repeat01.json … repeat10.json
  …
  cfg_R3P3_B/  cfg_B_round3_pos3_boot<N>_repeat01.json … repeat10.json
  boot_logs/
    boot<N>_uart.log        full UART capture for that boot
    boot<N>_ddr_selftest.txt
    boot<N>_cpuwait.txt
  campaign_report.json      written by analyze_pmu_cfg.py
```

One directory per cell. `run_pmu_cfg.py` refuses a non-empty output directory
and creates each sample file exclusively, so a re-run cannot overwrite
evidence.

### External gates — not in the JSON, still required

The **per-boot DDR self-test result** and the **CPUWAIT / reset proof** are not
schema-v8 fields and cannot be re-derived by the analyzer. They live in
`boot_logs/` and are a **board-procedure gate**: a campaign whose analyzer
passes but whose boot logs are missing or show a failed DDR self-test is **not
complete**. Capture them for every one of the nine boots, before the ten runs.

---

## 6. Raw preservation

- Every sample archives **both** wire payloads — the unsolicited
  `PMU_DIAG_COMPLETE` and the independent `GET` re-read — as hex, each with its
  own SHA-256, plus the exact manifest bytes and their digest.
- Those bytes are the evidence. Every parsed field in the archive is derivable
  from them and is re-derived by the analyzer; nothing in the file is trusted.
- **Never edit an archived sample.** A hand-edited file is refused, and a file
  edited *consistently* is still refused because it will not match the frozen
  digests in section 2.
- Keep the full UART capture per boot alongside the JSON.
- Archived samples are append-only. If a cell must be re-run, move the old
  directory aside under a new name; do not delete and do not overwrite.

---

## 7. STOP rules

Stop the campaign — do not continue to the next cell — when any of these occur:

| Condition | Action |
|-----------|--------|
| A staged BIN or manifest hash does not match section 2 | **STOP.** Do not deploy. Re-stage from the container. |
| Preflight refuses (schedule cell, manifest identity, BIN hash, non-empty out-dir, non-positive boot index) | **STOP.** Fix the invocation; do not bypass. |
| `run_pmu_cfg.py` exits non-zero on an **invalid sample** | **STOP.** The invalid sample is archived with `npu_pmu_window_cycles: null`. Do not re-run the cell to "get a clean one" — investigate first. |
| Identity / CRC / re-read / sequence failure (no file written) | **STOP.** The record is not attributable to the cell. Investigate before any further boot. |
| DDR self-test fails or CPUWAIT proof is missing for a boot | **STOP.** That boot contributes nothing; the cell must be re-run on a new boot index. |
| `run_sequence` does not start at 1 | **STOP.** The boot was not fresh. |
| The analyzer reports an MMIO contract violation | **STOP.** Do not reinterpret or widen the contract — the images differ somewhere beyond the single variable. |
| Two cases resolve to the same artifacts | **STOP.** The single variable was not varied. |

A STOP is a result. Restarting until the tooling stops complaining is how a
campaign becomes unfalsifiable.

---

## 8. Predeclared MMIO contract

Declared here, from the case definitions, **before any data is read**. It is
falsifiable and it is not widened after the fact.

- **Within a case**, the whole-window MMIO read and write deltas are constant
  across all 30 samples.
- **B and C have identical totals** — both perform exactly one `PMCCNTR_CFG`
  write plus one immediate readback.
- **B and C are exactly `A + 1` read and `A + 1` write.** No other cross-case
  difference is permitted.
- **Hook-local counts are invariant across all 90 samples.** The hook is
  identical in all three images, so a variation means the seam itself moved.

If any relation fails the analyzer **rejects**; it never reinterprets.

---

## 9. Analysis

```bash
python3 host/analyze_pmu_cfg.py \
  --results-root results/cfg_campaign \
  --json-out results/cfg_campaign/campaign_report.json
```

The analyzer requires **exactly 90** samples and re-derives everything from the
archived bytes: payload and re-read digests and equality, payload CRC via
re-parsing, manifest bytes re-hashed and re-parsed, identity re-checked, the
verdict re-derived with `classify_pmu_cfg` and compared against the archived
one, the golden window `0x90020CC0 +0x100 CRC 0x27084C4C` on every sample, and
the frozen digests of section 2.

It also enforces the **functional freshness contract**: for each repeat index
1–10 the `(output_crc, poison_crc)` pair must be identical across all nine
cells, and the ten pairs must be mutually distinct. This is functional
evidence that each run was fresh rather than a re-served latch. It is **never**
a performance statistic.

### Statistics — and their limits

The experimental unit is the **boot**, so **n = 3 per case**. Ten repeats on one
boot are ten observations of one boot: they share a power-up, a DRAM training,
a cache state and a thermal point.

Reported: per-boot median, within-boot CV, between-boot spread over the three
boot medians, and pooled min / max / median / MAD / IQR / CV — with the pooled
block explicitly labelled as 30 observations of 3 boots, not 30 independent
samples.

**Every cross-case comparison is `INCONCLUSIVE`, by construction.** Three units
cannot support an equivalence claim, a difference claim, a tolerance or a
p-value. The analyzer reports whether the boot-median spans overlap as a
descriptive fact only: *overlap is not equivalence; separation is not
significance.* Neither becomes a claim without more independent boots, and that
judgement is a human one.

---

## 10. Prohibitions

Under this contract the campaign may **not**:

- be reported as latency, `T_npu`, throughput, or any performance number;
- be used as a performance baseline or a regression reference;
- promote Production `END_ONLY`, open Gate 7, or feed MLEK data collection;
- generalize the Gate 1 `+514` identity to these images;
- claim that two cases are equivalent, or that they differ significantly;
- introduce an equivalence tolerance or a p-value;
- invent a hook-instant `STATUS` value. Schema v8 records no such field. The
  two surrounding observations (`npu_status_after_power_request`,
  `npu_status_after_seam`) **bracket** it; the limitation is declared and
  archived with every sample and is never filled in;
- modify the v8 provenance anchor, Production `END_ONLY`, or the MLEK path;
- edit, regenerate or "clean up" an archived sample.

Structure and CFG semantics must be explained before any promotion is
discussed. Until then the H-PRINTF seam remains qualified for observability and
**UNDECIDED** as a production mechanism.
