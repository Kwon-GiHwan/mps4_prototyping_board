| workload | class | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | model | 15,556,352 | 91,517 | 170.0 | 16.6% | 61.7% | 26.9% | 0.0026 | 0.0010 | 0.442 | 0.173 | 0.82% |
| ad_medium_int8 | model | 62,346,720 | 146,324 | 426.1 | 41.6% | 64.0% | 65.0% | 0.0018 | 0.0007 | 0.768 | 0.301 | 0.69% |
| mobilenet_v2_1.0_224_INT8 | model | 300,775,552 | 1,449,436 | 207.5 | 20.3% | 39.7% | 51.1% | 0.0036 | 0.0012 | 0.741 | 0.241 | 0.07% |
| conv3x3 | isolated_operator | UNPROVEN |  |  |  |  |  |  |  |  |  |  |
| dw3x3 | isolated_operator | UNPROVEN |  |  |  |  |  |  |  |  |  |  |
| pw1x1 | isolated_operator | UNPROVEN |  |  |  |  |  |  |  |  |  |  |
| fc1024 | isolated_operator | UNPROVEN |  |  |  |  |  |  |  |  |  |  |
| vww4_128_128_INT8@x1 | model | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| wav2letter_pruned_int8@x1 | model | UNPROVEN |  |  |  |  |  |  |  |  |  |  |
| rnnoise_INT8@x1 | model | 86,952 | 50,713 | 1.7 | 0.2% | 1.1% | 15.5% | 0.0032 | 0.0906 | 0.005 | 0.155 | 0.65% |
| yolo-fastest_192_face_v4@x1 | model | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
