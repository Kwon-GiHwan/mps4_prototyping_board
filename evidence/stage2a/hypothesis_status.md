# Stage 2A hypothesis status — boots 75–77, TA profile 1

Statuses come from the preregistered rules in `contract.md` §8, computed by `host/analysis/stage2a.py`
(`summary.json` → `hypotheses`). Every comparison is against conv3x3 (boot 75).

`ΔI` is the excess MAC-inactive share against conv3x3: 59.7 pp for dw3x3 and 59.5 pp for pw1x1. "Excess" below is the
operator's median ratio minus conv3x3's. † marks a driver-derived counter, which can give at most `PARTIAL_SUPPORT`.

Correlation decides no cause. A status says only how the counters line up with each hypothesis.

## dw3x3 (boot 76)

| hypothesis | evidence | counter-evidence | status | next experiment |
| --- | --- | --- | --- | --- |
| H1 weight decoder / weight supply | WD stalled 98.4 % vs 86.2 %, HIGHER; excess 12.2 pp | Excess < ΔI. The reference itself is 86 % WD-stalled. The event also counts "no free WD buffer space" (MAC back-pressure). WD active is only 178 cycles (0.1 %) | PARTIAL_SUPPORT | Stage 3: WD stall split 83–85 and weight-read request stall |
| H2 input buffer / data supply † | IB stall 78.9 % vs 18.8 %, HIGHER; excess 60.1 pp ≥ ΔI 59.7 pp | Driver-derived only: event ↔ status-bit mapping unconfirmed. No TRM-documented input-supply event in this set | PARTIAL_SUPPORT (cap) | Stage 3: IFM read request stall / outstanding / AXI latency on the IFM channel, as TRM-documented confirmation |
| H3 command / pipeline dependency | — | Event 33 not measured (owner decision) | UNRESOLVED | Separate dependency analysis once event 33's meaning is confirmed |
| H3b weight / accumulator back-pressure † | — | W/ACC stall 0 in dw3x3 and conv3x3 | REFUTED | — |
| H4 output / activation side | AO active 17.6 % vs 5.9 %, HIGHER; excess 11.6 pp | Excess < ΔI. AO active is work, not a stall | PARTIAL_SUPPORT | Stage 3: AO stall split 67–72 and write request stall |
| H5 spatial packing / shape mapping (P5) | Active-cycle efficiency 12.5 % vs 66.7 %, LOWER; DPU / MAC-active not lower (1.000 = 1.000) | WD-stalled and IB-stall ratios are HIGHER, so temporal stalls are present as well | UNRESOLVED | — (see `routing.md`, open item) |
| H6 low active-cycle efficiency with DPU inactivity (question 2) | Active-cycle efficiency LOWER | `mac_dpu_active` == `mac_active` in every RUN, so event 51 cannot show DPU inactivity inside MAC-active cycles | UNRESOLVED | Needs a different observable than event 51 |

Component-level evidence for dw3x3's low MAC activity: **yes**. H1, H2 and H4 are at `PARTIAL_SUPPORT`, and none
reaches `SUPPORTED`.

## pw1x1 (boot 77)

| hypothesis | evidence | counter-evidence | status | next experiment |
| --- | --- | --- | --- | --- |
| H1 weight decoder / weight supply | — | WD stalled 59.8 % vs 86.2 %, LOWER | REFUTED | — |
| H2 input buffer / data supply † | IB stall 40.8 % vs 18.8 %, HIGHER | Excess 22.0 pp < ΔI 59.5 pp; driver-derived only; large run-to-run spread (POST_HOC) | CORRELATED_ONLY | Stage 3: IFM supply, TRM-documented confirmation |
| H3 command / pipeline dependency | — | Event 33 not measured | UNRESOLVED | Separate dependency analysis |
| H3b weight / accumulator back-pressure † | W/ACC stall 14.8 % vs 0 %, HIGHER | Excess 14.8 pp < ΔI; driver-derived only | CORRELATED_ONLY | Stage 3: split 52 into 53 (WB) / 54 (AB) with weight-supply counters |
| H4 output / activation side | AO active 16.3 % vs 5.9 %, HIGHER; excess 10.3 pp | Excess < ΔI | PARTIAL_SUPPORT | Stage 3: AO stall split 67–72 and write request stall |
| H5 spatial packing (P5) | — | Active-cycle efficiency 80.0 % vs 66.7 %, HIGHER: no low active-cycle efficiency | REFUTED | — |
| H6 DPU inactivity | — | Same precondition fails | REFUTED | — |

Component-level evidence for pw1x1's low MAC activity: **yes**, through H4 (`PARTIAL_SUPPORT`).
- H2 and H3b line up but stay at `CORRELATED_ONLY`.
- The weight decoder is less stalled than in conv3x3.

## Answers to the Stage 2A questions (within the limits above)

1. **MAC-inactive cycles.**
   - dw3x3's go with a large MAC IB-stall share † (78.9 %). That excess alone is as large as its excess MAC-inactive
     share. They also go with more WD stalling and more AO activity than conv3x3.
   - pw1x1's go with more IB stall † and with W/ACC stall †, which conv3x3 never shows, and with more AO activity. Its
     weight decoder stalls less than conv3x3's.
2. **DWConv's low active-cycle efficiency and DPU activity: not decidable with this set.** `mac_dpu_active` equals
   `mac_active` in every RUN, so "at least one DPU active" holds whenever the MAC is active.
3. **PWConv's short MAC-active interval:**
   - What goes with it: IB stall †, W/ACC stall † and AO activity.
   - No single counter can account for the whole 59.5 pp gap by itself. The highest is IB stall, at 22.0 pp.
   - Weight-decoder stalling does not go with it (H1 refuted).
4. **Largest difference from conv3x3:**
   - dw3x3: WD active (0.011×) and IB stall † (4.2×).
   - pw1x1: W/ACC stall † (0 → 14.8 %), then AO active (2.7×).
