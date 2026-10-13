# Reproducibility declaration — draft

**Requirement (SIGMETRICS 2027 CFP, verified 2026-09-04):** a reproducibility
declaration is mandatory at submission; authors specify what data, code and
artifacts will be released, and where they will be hosted.

**Nothing is published in SE1.** No repository is created, no DOI is minted, and
no availability is claimed that does not yet exist. This is a plan, stated as a
plan.

---

## Artifact inventory

| class | count | releasable | notes |
| --- | ---: | --- | --- |
| frozen analysis outputs (`docs/paper/analysis/`) | 34 | **YES** | CSV/JSON; every number in Sections 4–7 resolves to these |
| frozen campaign evidence (`docs/paper/evidence/`) | 97 | **YES** | per-stage JSON with hashes, sample counts, gate verdicts |
| mechanism study outputs (`docs/paper/mechanism/`) | 806 | **YES** | per-operation and per-group CSV/JSON for the U85 study |
| platform-sensitivity outputs (`docs/paper/platform_sensitivity/`) | 31 | **YES** | X0/X1/X3 contracts, analyzer, results, qualification table |
| host analysis and test scripts | 111 | **YES** | Python; includes the frozen analyzers and their mutation tests |
| firmware diagnostic sources, patches, Makefiles | 70 | **YES** | our own instrumentation code |
| manuscript checkers / validation suites | 7 | **YES** | the 6 suites (222 checks) that audit the paper itself |
| figure generator | 1 | **YES** | regenerates all five figures from the frozen CSVs |
| **Arm ML Embedded Evaluation Kit** | — | **NO** | third-party; obtainable by anyone from Arm's own repository. We release our patches against it, pinned to a commit |
| **Arm Vela compiler 5.0.0** | — | **NO** | third-party; publicly obtainable from Arm |
| **Arm Fast Models FVPs** (11.22.35 / 11.24.13 / 11.27.25 / 11.31.28) | — | **NO** | licensed vendor binaries; redistribution not permitted |
| **MPS4 / Corstone-320 FPGA board** | — | **NO** | physical hardware |
| `arm-none-eabi-gcc` toolchain | — | **NO** | third-party, publicly obtainable; version pinned in the release |

## Proposed declaration text

> **Data and artifact availability.** If the paper is accepted we will publicly
> release: all frozen analysis outputs and campaign evidence (CSV/JSON) from
> which every number in this paper is derived; the analysis and figure-generation
> scripts, including the mutation tests that prove each rejection rule can fire;
> our firmware instrumentation sources and the patches we apply to the Arm ML
> Embedded Evaluation Kit; the build configuration and pinned toolchain
> versions; and the manuscript-validation suites used to audit the paper's
> internal consistency. The archive will be deposited in a long-term public
> repository with a DOI (Zenodo), with a mirror in a public source repository.
>
> We cannot redistribute the third-party components the measurements depend on:
> the Arm Fast Models Fixed Virtual Platforms, the Vela compiler, the ML
> Embedded Evaluation Kit itself, and the Arm cross-compiler are obtained from
> Arm under their own terms, and the MPS4 FPGA board is physical hardware. We
> pin the exact version of each and release our diffs against them.
>
> Reproduction requirements differ by result class. The **simulated results**
> (Sections 4, 5, 7) are reproducible by any party holding the named Fast Models
> FVP versions and Vela 5.0.0: builds are byte-reproducible once
> `SOURCE_DATE_EPOCH` is pinned to the source-tree commit timestamp, and each
> cell's identity chain runs from model hash through Vela artifact hash and
> generated-source hash to linked-executable hash. The **physical-board results**
> (Section 6) additionally require an MPS4 board with a Corstone-320 / Ethos-U85
> image at 1024 MACs, and are therefore reproducible only by parties with that
> hardware. The **analysis and figures** are reproducible from the released
> frozen outputs alone, with no simulator, compiler or hardware required.

## Reproduction requirements by result class

| result class | sections | needs FVP | needs Vela | needs board | reproducible from released data alone |
| --- | --- | --- | --- | --- | --- |
| MAC scaling and saturation | 4 | yes | yes | no | analysis: **yes** |
| platform-sensitivity validation | 5 | yes | yes | no | analysis: **yes** |
| board ordering validation | 6 | no | yes | **yes** | analysis: **yes** |
| U85 operator-level mechanism | 7 | yes | yes | no | analysis: **yes** |
| all figures | 4–7 | no | no | no | **yes** |
| all manuscript consistency checks | — | no | no | no | **yes** |

The last two rows matter: a reader without an Arm licence or hardware can still
regenerate every figure and re-run every numerical audit in this paper from the
released frozen outputs.

## Open points

| item | status |
| --- | --- |
| Zenodo deposit | **not created.** Proposed only, consistent with the CFP; creation is deliberately deferred until acceptance |
| exact archive DOI | does not exist yet; must not be cited as if it did |
| whether the manager wants the public mirror to be the existing repository or a fresh anonymized one | `NEEDS_MANAGER_CONFIRMATION` — the existing repositories are author-identifying, so a fresh deposit is likely required |
| licence for the released code and data | `NEEDS_MANAGER_CONFIRMATION` |

## Status

```
REPRODUCIBILITY_DECLARATION: DRAFTED, NEEDS_MANAGER_CONFIRMATION
```

Two decisions are required before submission — the hosting target and the
licence. The declaration text above is written so that neither answer changes
its substance, only its final sentence.
