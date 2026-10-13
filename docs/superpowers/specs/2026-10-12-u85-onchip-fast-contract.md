# On-chip fast scratch A/B — is DDR-backed fast scratch the cause of the runner's extra cycles? (contract)

Frozen 2026-10-12, **before the image is deployed and before any data of this run exists**. Authorization: owner,
2026-10-12 (runner-gap investigation guideline, "이거 보고 왜그런지 알아보자").

## Correction that motivates this run

`2026-10-12-u85-fast-scratch-ext-contract.md` moved fast scratch from DDR behind the SRAM port (`0x9012_xxxx`) to
DDR behind the EXT port (`0x7010_xxxx`). **Both are DDR.** Its `FAST_PATH_NOT_CAUSE` therefore refutes "the SRAM-port
path to DDR is slower than the EXT path", not "fast scratch in DDR instead of on-chip SRAM". MLEK places fast scratch
(`.bss.NoInit.ethos_u_cache`) in on-chip SRAM `0x3100_0000` (sse-320 gnu.ld `.sram`). That memory-type difference
has not been tested. (The fast_ext report and the screening-2 cause summary stated it more broadly; this contract
is the correction.)

## Image change

`patch_pmu_events_source.py`: header word 26 = absolute fast-scratch base. The runner refuses (`PMWL_REFUSED`) unless
region 2 is on the SRAM port, the base is 256-aligned, at or above `__StackTop` (runner image ends `0x3102_9DB8`),
and base + fast size ≤ `0x3140_0000`. Packer `--fast-base`. Default OFF = staging, unchanged.
Image APP `0cd28e1d…` (also contains the POWER_CTRL knob, left OFF = vendor 2 in both arms here).
Deployed with a new evidence root `evidence_m8`; the original-image restore reference stays `evidence_m6`.

## Protocol

Blobs: screening-2 settings. **control** = byte-identical to the screening-2 blob (fast in DDR staging via SRAM
port); **treatment** = same plus `--fast-base 0x31100000` (fast in on-chip SRAM via SRAM port; mobilenet uses up
to `0x3115_E3B0`). Only header word 26 differs. Same 8 ids, 35 RUNs (1–5 warm-up). Boots in order:
kws control, kws on-chip, ad control, ad on-chip, mobilenet control, mobilenet on-chip (numbers assigned after the
POWER_CTRL campaign, recorded in the report).

## Outcome

`host/power_ctrl_ab.py <ctrl root> <onchip root>` unchanged (its outcome logic is generic control vs treatment):
gap closure g = (C − T)/(C − M) with MLEK ACTIVE M; `SUPPORTED` g ≥ 0.8, `PARTIAL_CONTRIBUTOR` 0.2 ≤ g < 0.8,
`REFUTED` g < 0.2, `UNRESOLVED` if not SCREENED or mac_active / EXT rd / EXT wr move > 0.1 %, or C ≤ M.
Overall = kws outcome if ad_medium agrees, else `UNRESOLVED`. The image-neutrality column compares control with
screening 2 (±5 %).

## Not claimed

Cycles only. A SUPPORTED result attributes the gap to the memory behind fast scratch in this runner; it does not
measure SRAM vs DDR latency directly (no SRAM-side latency events in this set).
