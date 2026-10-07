# Step 2 diagnostic boots 15/16 — verdict (amendment 1: docs/superpowers/specs/2026-10-07-pmu-model-step2-amendment-1.md)

Image MODEL=1 (APP 84d4ecaf…) with the amendment-1 instrumentation. 1 set × 3 each.

| boot | blob | vendor_rc (3 runs) | seam STATUS | seam QREAD | reading |
| --- | --- | --- | --- | --- | --- |
| 15 | mobilenet, knobs OFF (all EXT/DRAM) | 2, 2, 2 | 0xFFFF0020 | 17468 (= cms_len) | **OUTPUT_MISMATCH** |
| 16 | mobilenet, split ports (as boot 14) | 2, 2, 2 | 0xFFFF0020 | 17468 | **OUTPUT_MISMATCH** |

Both fail the same way → per the amendment, the boot-14 failure belongs to the model, not to the
split-port placement. STATUS 0xFFFF0020 = `cmd_end_reached`, IRQ history 0xFFFF, no error bits; QREAD equals the
command-stream length: the NPU executed the whole stream and stopped normally. The vendor's memcmp found the OFM
different from the tflite_runtime reference. No IRQ timeout (vendor_rc has no +1).

## Correction to VERDICT_2a (boot 14)

VERDICT_2a's POST_HOC note says the NPU "sat idle until the vendor's IRQ wait gave up". That reading is not
supported: boots 15/16 show the same ~82 M idle cycles with **no** IRQ timeout. The long idle is the wrap copying
the 3.5 MB constants to DRAM inside the measured window (step 1's kws constants are 146 KB). Boot 14's vendor rc
was not recorded; by the same image path and identical traffic it is most likely 2, but that is not established.
The campaign verdict MODEL_FAILS stands.

Next (diagnostic): record the OFM mismatch count / max |diff| / first index to tell a ±1 reference difference
from a wrong result.
