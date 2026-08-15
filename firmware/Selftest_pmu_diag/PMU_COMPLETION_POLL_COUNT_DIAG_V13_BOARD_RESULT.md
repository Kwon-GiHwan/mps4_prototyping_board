# PMU_COMPLETION_POLL_COUNT_DIAG_V13 board result

Date: 2026-08-15

## Provenance

- Pre-board source/host anchor: `35e7e1900dfe35181be73f56deb97aab1d776211`
  (`pmu-completion-poll-count-v13-preboard`)
- Evidence root:
  `/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_20260815T061146Z/`
- `CAMPAIGN_ANALYSIS.json` SHA-256:
  `77bf48b77842284b20ac9f7593ee469ca29fc8670127fa214542d7bed17907f2`
- `SAMPLES.sha256` SHA-256:
  `643d32fb1ee9dff4d1afaa0493c20bea38e876fd0ebd5cf6afa6544f7eeb6e22`
- `FINAL_EVIDENCE.sha256` SHA-256:
  `add4c163327d952d3fab59b78121dcce014984a1c8ba74a2eeb4b0d854a5b0d5`

The fixed board candidate was not rebuilt or changed after pre-board
qualification. Its authoritative SHA-256 values were:

```text
APP.BIN     800130bf04719bd477a0e3c73268a9bf3aacda7bbb5ecf6e32c3b2f4d676e57a
VECTORS.BIN 50d8950cf6bc61124af19368b83e95dcd5cdb21a34eac2db656b51776fb227f1
DDR.BIN     81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
ELF         d12fc98510b63f5fa19b4fd4998d49479de3fc210a66dc4321ad734a7267fe11
manifest    fa648ca2c445b4e94fb0ed77478fe3281af4b97debb7e10c01ec12314af45ada
```

## Campaign

Three independent full boots each passed DDR self-test and CPUWAIT clear, then
produced run sequences 1 through 10. All 30 archives were valid, all 70
classifier terms were true for every sample, and no polling timeout occurred.
Raw COMPLETE and GET payloads were byte-identical; an independent audit
recomputed all archived payload hashes and rechecked the golden CRC, overflow,
boot/run sequence, and derived remaining/count identities.

```text
poll_iterations = 10001 - poll_remaining_at_success
  min / max       25 / 221
  median          56.5

poll_observation_cycles = u32(P1 - P0)
  min / max       716 / 5812
  median          1535
  hard floor      716, 7/30
  excursions      23/30

Spearman rho(iterations, poll cycles)    1.0
OLS poll cycles = alpha + beta*iterations
  alpha           66
  beta            26
  residual         0, 30/30
```

The same exact linear identity held in every boot:

```text
u32(P1 - P0) = 66 + 26 * poll_iterations
```

Therefore the V12 `P0 -> P1` variability is completely explained, for this
fixed V13 image and workload, by how many STATUS polling iterations occur
before completion is first observed. The observed per-iteration execution
cost did not introduce an independent residual in these 30 samples.

This does **not** separate NPU command completion from completion-bit
visibility. The remaining causal boundary is the point at which the stock
STATUS completion bit becomes observable to the polling CPU; V13 does not
show whether a longer run means later NPU completion or later STATUS
visibility.

## Interpretation limits

This campaign is diagnostic characterization only. Neither the observed
cycles nor the fitted coefficient is latency, `T_npu`, a performance baseline,
Production evidence, or MLEK data. The exact linear identity is specific to
this fixed image, compiler output, polling loop, workload, and instrumentation;
it is not a general Ethos-U85 constant. Production END_ONLY remains frozen.

## Restoration

The fresh pre-deployment backup matched the known-good hashes:

```text
APP.BIN     ffa3e5bd0363f791d61f9673074c625865f1e6a8f24e53ee303372c64ef3597d
VECTORS.BIN 45e943c577e3744104d53cf57c7d0afb369ff68a99e5e6906971d71503f06c92
DDR.BIN     81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
```

Those three files were restored byte-for-byte. The restored image passed DDR
self-test and CPUWAIT clear; runner PING was 3/3 IDLE with all seven protocol
error counters zero. Final state was USB_OFF, `/dev/sdb` absent, zero mounts,
and zero userspace holders, including root-owned processes, on all four FTDI
tty device nodes at the checked instant.

## State

```text
PMU_COMPLETION_POLL_COUNT_DIAG_V13  FROZEN / BOARD EVIDENCE COMPLETE
V13 poll-count characterization      COMPLETE
P0 -> P1 variability explanation     POLL ITERATION COUNT / EXACT IN DATASET
NPU completion vs STATUS visibility  UNRESOLVED
Production END_ONLY                  FROZEN
MLEK                                 BLOCKED
```
