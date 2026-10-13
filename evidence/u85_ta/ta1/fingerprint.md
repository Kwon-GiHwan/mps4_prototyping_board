| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | SCREENED | SCREENED | NOT_EXECUTABLE | NOT_EXECUTABLE |
| M1 npu_active (cycles) | 91,058 | 1,452,640 | 146,547 | N/A | N/A |
|     window (PMCCNTR, incl. staging) | 2,624,440 | 64,953,053 | 8,031,134 | N/A | N/A |
| M2 npu_active / window | 3.5% | 2.2% | 1.8% | N/A | N/A |
| M3 peak MAC efficiency | 16.7% | 20.2% | 41.5% | N/A | N/A |
|     MAC active-cycle efficiency | 26.9% | 51.1% | 65.0% | N/A | N/A |
| M4 MAC active ratio | 62.0% | 39.6% | 63.9% | N/A | N/A |
| M5 EXT beats / MAC | 0.0010 | 0.0012 | 0.0007 | N/A | N/A |
|     read beats / MAC | 0.0010 | 0.0010 | 0.0007 | N/A | N/A |
|     write beats / MAC | 0.0000 | 0.0002 | 0.0000 | N/A | N/A |
| M6 EXT read-req stall | 0.4% | 0.2% | 0.2% | N/A | N/A |
|     EXT write-req stall | 0.0% | 0.0% | 0.0% | N/A | N/A |
|     EXT write-data stall | 0.0% | 0.0% | 0.0% | N/A | N/A |
| M7 Vela signed error (cycles_total vs npu_active) | 12.3% | 62.4% | 1.2% | N/A | N/A |
| CV of npu_active | 1.0% | 0.1% | 0.6% | N/A | N/A |
