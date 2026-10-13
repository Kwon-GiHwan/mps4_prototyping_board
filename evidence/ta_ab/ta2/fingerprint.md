| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | NOT_EXECUTABLE | SCREENED | NOT_EXECUTABLE | NOT_EXECUTABLE |
| M1 npu_active (cycles) | 61,071 | N/A | 111,878 | N/A | N/A |
|     window (PMCCNTR, incl. staging) | 2,594,448 | N/A | 7,996,346 | N/A | N/A |
| M2 npu_active / window | 2.4% | N/A | 1.4% | N/A | N/A |
| M3 peak MAC efficiency | 24.9% | N/A | 54.4% | N/A | N/A |
|     MAC active-cycle efficiency | 26.9% | N/A | 65.0% | N/A | N/A |
| M4 MAC active ratio | 92.4% | N/A | 83.7% | N/A | N/A |
| M5 EXT beats / MAC | 0.0010 | N/A | 0.0007 | N/A | N/A |
|     read beats / MAC | 0.0010 | N/A | 0.0007 | N/A | N/A |
|     write beats / MAC | 0.0000 | N/A | 0.0000 | N/A | N/A |
| M6 EXT read-req stall | 0.0% | N/A | 0.0% | N/A | N/A |
|     EXT write-req stall | 0.0% | N/A | 0.0% | N/A | N/A |
|     EXT write-data stall | 0.0% | N/A | 0.0% | N/A | N/A |
| M7 Vela signed error (cycles_total vs npu_active) | 67.4% | N/A | 32.6% | N/A | N/A |
| CV of npu_active | 0.0% | N/A | 0.0% | N/A | N/A |
