| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | SCREENED | SCREENED | NOT_EXECUTABLE | NOT_EXECUTABLE |
| M1 npu_active (cycles) | 337,296 | 10,122,562 | 951,946 | N/A | N/A |
|     window (PMCCNTR, incl. staging) | 2,869,592 | 73,622,446 | 8,835,279 | N/A | N/A |
| M2 npu_active / window | 11.8% | 13.7% | 10.8% | N/A | N/A |
| M3 peak MAC efficiency | 4.5% | 2.9% | 6.4% | N/A | N/A |
|     MAC active-cycle efficiency | 26.9% | 51.1% | 65.0% | N/A | N/A |
| M4 MAC active ratio | 16.7% | 5.7% | 9.8% | N/A | N/A |
| M5 EXT beats / MAC | 0.0010 | 0.0012 | 0.0007 | N/A | N/A |
|     read beats / MAC | 0.0010 | 0.0010 | 0.0007 | N/A | N/A |
|     write beats / MAC | 0.0000 | 0.0002 | 0.0000 | N/A | N/A |
| M6 EXT read-req stall | 2.3% | 2.2% | 1.1% | N/A | N/A |
|     EXT write-req stall | 0.0% | 0.1% | 0.0% | N/A | N/A |
|     EXT write-data stall | 0.0% | 0.1% | 0.0% | N/A | N/A |
| M7 Vela signed error (cycles_total vs npu_active) | -69.7% | -76.7% | -84.4% | N/A | N/A |
| CV of npu_active | 0.9% | 0.0% | 0.3% | N/A | N/A |
