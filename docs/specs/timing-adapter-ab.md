# Timing adapter A/B — does the runner's untouched TA state cause its extra cycles? (contract)

Frozen 2026-10-12, **before the image is deployed and before any data of this run exists**. Authorization: owner,
2026-10-12 (runner-gap investigation guideline).

## Why

Every memory placement tried leaves the runner 3.7× (kws) – 7× (mobilenet) above MLEK's NPU ACTIVE on the same
command stream: DDR behind the SRAM port, DDR behind EXT (`fast_ext`), and — kws, partial at freezing time — on-chip
SRAM behind the SRAM port (on-chip campaign boots 43–44: 333,908 → 337,296). A slowdown independent of where the
data lives points at something in front of both NPU AXI ports. MLEK's board boot log shows
`Configured TA_SRAM @0x51102000` / `Configured TA_EXT @0x51102400`: FI101 has NPU timing adapters (TA_VERSION check
passed in MLEK's `ta_init`), MLEK programs them at boot (`ta_config_u85_sys_dram_mid`), and the runner never touches
them. TA `MODE` bits 11–4 are a frequency scale (0 = full speed … 255 = 1/256), and the TA also inserts latency and
outstanding/bandwidth limits — any non-trivial reset value would slow every path.

## Image change

`patch_pmu_events_source.py`: header word 27 = TA profile; OFF = untouched (all earlier runs); 1 = MLEK
`ta_config_u85_sys_dram_mid`, Dedicated_Sram branch (SRAM: MAXR 8, MAXW 8, MAXRW 0, RLAT 32, WLAT 32, PULSE_ON 3999,
PULSE_OFF 1, BWCAP 4000, PERFCTRL 0, MODE 1, HISTBIN 0; EXT: MAXR 64&0x3F=0, MAXW 32, MAXRW 0, RLAT 500, WLAT 250,
PULSE_ON 4000, PULSE_OFF 1000, BWCAP 3750, PERFCTRL 0, MODE 1, HISTBIN 0); 2 = pass-through (limits 0, latency 0,
PULSE_ON 0xFFFF, PULSE_OFF 0, BWCAP 0, MODE 1). Applied in `__wrap_test_u85` before the vendor run, every RUN.
Both TAs must report TA_VERSION 0x1117 and read back every written value, else the RUN is invalid
(`PMWL_KNOB_NOT_HONOURED`). Packer `--ta-profile`. Image APP `2c2fa435…` (also has the POWER_CTRL and on-chip
knobs, both OFF here). New evidence root `evidence_m9`; original-image restore reference stays `evidence_m6`.

## Protocol

Blobs: screening-2 settings; **ctrl** byte-identical to the screening-2 blob; **ta1** / **ta2** differ only in
header word 27. 35 RUNs, same 8 ids. Boots in order: kws ctrl, kws ta1, kws ta2, ad ctrl, ad ta1, ad ta2,
mobilenet ctrl, mobilenet ta1 (mobilenet ta2 not run: time).

## Outcome

Primary (preregistered): `host/power_ctrl_ab.py <ctrl root> <ta1 root>` unchanged — g = (C − T)/(C − M),
`SUPPORTED` ≥ 0.8, `PARTIAL_CONTRIBUTOR` 0.2–0.8, `REFUTED` < 0.2, `UNRESOLVED` per its rules; overall = kws if
ad_medium agrees. ta1 is the MLEK condition, so SUPPORTED means "the runner's untouched TA state accounts for the
gap". ta2 is reported descriptively (the same script on `<ctrl> <ta2>`), as the unthrottled reference.

## Not claimed

The TA reset values themselves are not read out (no wire field); the A/B attributes the gap to the TA state, not
to a specific TA register. Cycles only.
