# V15 formal campaign — 2026-08-23

Three fresh boots × ten consecutive runs. **30/30 formal samples.**

## Outcome: S1

A floor of **754 cycles reproduced identically in every boot**, with excursions
above it in each.

| boot | minimum | excursions | valid |
| --- | --- | --- | --- |
| boot1 | 754 | 7 | 10 |
| boot2 | 754 | 5 | 10 |
| boot3 | 754 | 8 | 10 |

`S1` is a preregistered outcome reached by the analyzer, not a description
written afterwards. The floor definition it applied is the frozen one: the same
value must be the minimum of **every boot taken separately**, pooling before
classification is prohibited, and an excursion is a sample above its own boot's
minimum.

`comparison_mode = Q_S5_EQUIVALENT`, so all six outcomes were available.

Poll count: `PRESENT_REFERENCE_MATCHED` / `NOT_ADMITTED_DUE_TO_LOOP_PERTURBATION`.
It did not reach the verdict, by contract (Amendment 1).

## How the samples were taken

Each boot: `REBOOT` → DDR self-test PASSED, CPUWAIT cleared, PING 3/3 from IDLE,
all seven protocol counters zero → prime to `INPUT_READY` → ten consecutive runs,
each frame compared against an independent re-read.

The run count is a literal in the runner. There is no top-up path and no retry:
a cell that lost a run would have ended the campaign rather than being made
whole. No cell needed it — 10/10 in all three boots, no abort.

Thirty distinct frame digests, all thirty classified valid through the
production path: parser → collector → normalized record → classifier → analyzer.

## Isolation

The live E2E qualification frame is **not** among the thirty. Its boot carries
the `not-a-campaign-boot` marker, the analyzer refuses any campaign containing
such a boot, and assembly asserts the qualification frame does not appear. The
campaign began from a fresh Boot 1 rather than continuing that boot.

Evidence was frozen as `v15-campaign-evidence-frozen` **before** the analyzer
ran, so the outcome could not influence what was recorded.

## Task 11 — closed

```
TASK11 = E2E_REQUALIFIED
```

Eight layers agreeing, with the mode carried from static image evidence through
the build manifest, the verified deployment context, the collector, the
normalized record and the classifier to the analyzer's verdict — on real frames.
It was held at `LIVE_PATH_VERIFIED_PENDING_CAMPAIGN` until this campaign closed
it, rather than being rounded up.

## Restore and postflight

| | on card | expected |
| --- | --- | --- |
| `APP.BIN` | `ffa3e5bd…` | `ffa3e5bd…` ✓ |
| `VECTORS.BIN` | `45e943c5…` | `45e943c5…` ✓ |
| `DDR.BIN` | `81d37a21…` | `81d37a21…` ✓ |

Original restored byte-exact, read back off the device after an unmount and
read-only remount. Then:

```
DDR self-test PASSED        CPUWAIT cleared
PING 3/3 from IDLE          protocol counters all zero
USB_OFF confirmed           /dev/sdb* absent
card mounts 0               UART holders 0/0/0/0, root-inclusive
```

## Wire contract in force

Schema 14, verified against the emitted firmware C at assembly time, with all
34 appendix slots checked in the firmware's own order and ten result enums
checked against the emitted vendor C (Amendment 4).
