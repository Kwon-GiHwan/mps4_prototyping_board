# POWER_CTRL A/B — does the vendor's MAC power ramping cause the runner's extra non-MAC cycles? (contract)

Frozen 2026-10-12, **before the image is built and before any data of this run exists**. Authorization: owner,
2026-10-12, on the pasted "MLEK–Custom Runner 성능 차이 원인 규명 지침" ("이거 보고 왜그런지 알아보자").

## Why this variable first

Static comparison (`evidence/u85_runner_gap/register_diff.csv`, `control_flow_diff.md`): of the NPU registers whose
value differs between the vendor `test_u85` path and the MLEK core-driver path **during the job**, only one acts on
the MAC: `POWER_CTRL.mac_step_cycles` — vendor `MAC_RAMP_VAR = 2` (u85.c:285), driver
`NPU_MAC_PWR_RAMP_CYCLES = 0` = ramping disabled (ethosu_device_u85.c:246; MLEK does not override). The runner's
extra cycles are non-MAC-active (mac_active equal to MLEK's command stream count), which is where a MAC power ramp
would show.

## Image change (one variable made switchable, default unchanged)

- Vendor copy (`patch_u85_vendor_timeout.py`, change 3): `write_reg(NPU_REG_POWER_CTRL, u85_power_ctrl_value(MAC_RAMP_VAR))`
  with a weak default returning its argument.
- Runner (`patch_pmu_events_source.py`, MODEL branch): strong `u85_power_ctrl_value` returning blob header word 25
  when set, else the vendor value; POWER_CTRL read at the CPM seam (NPU still powered) and a run whose value differs
  from the requested one (or from 2 when not requested) returns `PMWL_KNOB_NOT_HONOURED` (run invalid).
- Gate `check_pmu_events.py` RULE_MODEL: vendor copy calls the hook, and the linked `u85_power_ctrl_value` is the
  strong (`T`) one. Packer `--power-ctrl` writes word 25 (header v3).
- New APP sha recorded at deploy. Deployed with a **new** evidence root (`evidence_m7`); the restore reference for
  the original board image stays `evidence_m6`.

## Protocol

Blobs: screening-2 settings (Vela profile `mlek`, ports `cmd=ext,const=ext,arena=ext,fast=sram`,
AXI `sram=0x20F0B,ext=0x21F3F`) — command stream identical to screening 2 and to MLEK's board run.
Two blobs per workload differing only in word 25: **control** = OFF (vendor 2), **treatment** = `--power-ctrl 0`.
Same 8 screening ids, 35 RUNs (1–5 warm-up). Boots 37–42, in this order:
kws control, kws treatment, ad_medium control, ad_medium treatment, mobilenet control, mobilenet treatment.
Analysis: `host/screening_metrics.py` on `evidence/u85_power_ctrl/{ctrl,treat}`, then `host/power_ctrl_ab.py`.

## Outcome per workload (closed set, `host/power_ctrl_ab.py`)

C, T = median npu_active (control, treatment); M = MLEK ACTIVE (median of B1–B3: kws 91,431; ad 145,976;
mobilenet 1,448,049). Gap closure g = (C − T) / (C − M).

- `UNRESOLVED`: either condition not SCREENED (< 30 valid, consistency failure, knob not honoured → invalid runs),
  or mac_active / EXT rd / EXT wr median moves by > 0.1 % (not a one-variable comparison), or C ≤ M.
- `SUPPORTED`: g ≥ 0.8. `PARTIAL_CONTRIBUTOR`: 0.2 ≤ g < 0.8. `REFUTED`: g < 0.2 (including worse).

**Overall**: the kws outcome if ad_medium has the same outcome (replication), else `UNRESOLVED`. mobilenet is
reported, does not decide.

Image neutrality (reported, no outcome depends on it): control median / screening-2 median; outside ±5 % is
flagged `IMAGE_CHANGED` and screening-2 comparisons are then not made.

## Not claimed

- Cycles only; no wall-clock, no ms (clock unverified). A SUPPORTED result says POWER_CTRL accounts for the gap
  in NPU cycles; whether wall time changes the same way is a separate step (CPU timer).
- No other register difference is tested here; a residual gap is reported as residual, not attributed.
