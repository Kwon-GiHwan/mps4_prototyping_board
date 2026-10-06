# Step 2 diagnostic boot 17 — OFM vs reference (image MODEL=1 APP 919c2477…, mobilenet knobs OFF, 1 set × 3)

| run | vendor_rc | seam STATUS | QREAD | OFM mismatch count | max abs diff (int8) | first index |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 0xFFFF0020 | 17468 | 5 / 1001 | 4 | 491 |
| 2 | 2 | 0xFFFF0020 | 17468 | 5 / 1001 | 4 | 491 |
| 3 | 2 | 0xFFFF0020 | 17468 | 5 / 1001 | 4 | 491 |

Reading (descriptive): the NPU executes the full mobilenet stream and stops normally; the output equals the
tflite_runtime reference in 996 of 1001 bytes, deterministically, with |diff| ≤ 4. This is a numeric difference
between the Ethos-U/Vela implementation and the TFLite reference kernels, not a wrong or partial result.
step 1's kws matched byte for byte, so bit-exactness holds for some networks and not for this one.

Consequence: under the step-2 contract (correctness = vendor memcmp exact) every mobilenet run is INVALID, so no
step-2 event can be observed with this workload until the validity criterion is amended.
