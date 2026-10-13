# Track recommendation — SIGMETRICS 2027

Track definitions taken from the official CFP (retrieved 2026-09-04); see
`SIGMETRICS_2027_REQUIREMENTS.md`.

## Recommendation

```
PRIMARY TRACK   Measurement & Applied Modeling
SECOND TRACK    NO
```

## Primary — Measurement & Applied Modeling

The CFP describes this track as covering **empirical contributions and modeling
tools**. That is what this paper is, on every axis:

| paper element | why it is measurement |
| --- | --- |
| 74-cell formal sweep, 222 samples, byte-level provenance | empirical characterization of a commercial NPU across its supported configurations |
| Vela estimate versus FVP observation (19/20 on two criteria) | evaluation of a **modeling tool's** predictive behaviour — the track's second half, almost literally |
| 21-sample physical-board validation | measurement methodology: what transfers from a cycle model to hardware |
| X1/X3 same-artifact platform-sensitivity study | measurement validity — whether the metrics survive a change of instrument |
| operator-level decomposition of the U85 256→512 reversal | empirical mechanism study, not a proposed design |

The paper proposes **no new system, algorithm, or theory**. It measures an
existing one and reports what the measurements can and cannot support. Its most
transferable contributions — a timing adapter silently changing what is
measured, a compiler backend silently changing which program is instrumented,
executability reported as a first-class result — are measurement-methodology
findings.

## Second track — recommended **NO**

The CFP states the optional second track is intended for **strongly
interdisciplinary** work. It is not a visibility mechanism, and selecting one
without that justification would misrepresent the paper.

**Systems** was evaluated as the candidate and rejected:

| argument for Systems | assessment |
| --- | --- |
| the paper concerns embedded ML accelerator deployment | the subject matter is a system, but the *contribution* is a measurement of it |
| it includes firmware instrumentation work | the instrumentation exists to enable measurement and is qualified as an instrument (Section 7.5), not offered as a system contribution |
| it reports a deployability limitation (6 non-executable cells) | reported as an empirical result, not as a system design lesson with a proposed remedy |

Against: the paper designs no system, proposes no mechanism, and evaluates no
implementation of its own beyond the instrumentation needed to observe. A
Systems reviewer would reasonably ask what was built and what it improves, and
this paper answers neither — by design. That is not interdisciplinarity; it is
a single-discipline measurement paper.

**Conclusion:** one track. Claiming two would weaken the submission rather than
broaden it.

## Suggested submission topics

Where the form asks for topic keywords, in decreasing order of fit:

1. performance measurement and characterization of hardware accelerators
2. validation of simulators and performance models against hardware
3. measurement methodology and experimental design
4. machine-learning systems / ML accelerator evaluation
5. embedded and edge computing systems

## Note for the submission form

The paper is **not** an Operational Systems Track candidate: it reports no
production deployment, and the CFP's allowance for revealing a deploying
organization in that track does not apply here. Standard double-anonymous rules
apply in full.
