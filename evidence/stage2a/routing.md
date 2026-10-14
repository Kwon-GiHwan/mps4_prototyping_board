# Stage 2A routing — boots 75–77, TA profile 1

Routes follow the preregistered table in `contract.md` §9. They are the `routes` field of `summary.json`. Nothing here
starts an experiment: Stage 2B, FC1024 memory profiling, the AXI-latency pass and the shape sweep wait for the owner.

## dw3x3 → Stage 3

| route | from | reason |
| --- | --- | --- |
| Stage 3: IFM supply | H2 PARTIAL_SUPPORT † | The IB-stall excess (60.1 pp) is as large as the excess MAC-inactive share (59.7 pp), but the counter is driver-derived. Needs a TRM-documented event to confirm: IFM read request stall, outstanding, and AXI latency on the IFM read channel (`PMCAXI_CHAN` rd_ifm) |
| Stage 3: weight-stream supply | H1 PARTIAL_SUPPORT | WD stalled is HIGHER, but the excess is small (12.2 pp) and the reference is at 86 %. Split WD stall 83–85 (WD buffer vs weight stream) to separate supply from MAC back-pressure |
| Stage 3: output / write side | H4 PARTIAL_SUPPORT | AO active is 3.0× conv3x3's. Split AO stall 67–72 and add write request stall |

**Open item, outside the preregistered routes.** dw3x3's low active-cycle efficiency (12.5 %) was not routed to
Stage 4:
- H5 is `UNRESOLVED`: temporal stalls are present.
- H6 is `UNRESOLVED`: event 51 equals event 48.

Whether to add a Stage 4 shape sweep for dw3x3 anyway is an owner decision. It is not derived from these rules.

## pw1x1 → Stage 3

| route | from | reason |
| --- | --- | --- |
| Stage 3: output / write side | H4 PARTIAL_SUPPORT | AO active is 2.7× conv3x3's, the only TRM-documented counter that is HIGHER for pw1x1 |
| Stage 3: IFM supply | H2 CORRELATED_ONLY † | IB stall is 2.2× conv3x3's, but its excess (22.0 pp) is well below the gap (59.5 pp) |
| Stage 3: weight / accumulator buffer | H3b CORRELATED_ONLY † | W/ACC stall appears only in pw1x1 (14.8 %). Split 52 into 53 (weight buffer) and 54 (accumulator buffer) next to weight-supply counters |

pw1x1 is not routed to Stage 4: its active-cycle efficiency is higher than conv3x3's (H5 and H6 refuted).

## Not routed

- **H3 (dependency).** Event 33 was not measured. It waits for a semantics confirmation and a separate dependency
  analysis.
- **Pattern 6.** It applies to neither operator: both have component-level evidence at `PARTIAL_SUPPORT`.
