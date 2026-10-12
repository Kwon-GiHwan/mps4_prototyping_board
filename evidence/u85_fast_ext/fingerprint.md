| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | SCREENED | SCREENED | NOT_EXECUTABLE | NOT_EXECUTABLE |
| M1 npu_active (cycles) | 463,586 | 11,618,418 | 1,257,692 | N/A | N/A |
|     window (PMCCNTR, incl. staging) | 2,995,948 | 75,137,540 | 9,141,280 | N/A | N/A |
| M2 npu_active / window | 15.5% | 15.5% | 13.8% | N/A | N/A |
| M3 peak MAC efficiency | 3.3% | 2.5% | 4.8% | N/A | N/A |
|     MAC active-cycle efficiency | 26.9% | 51.1% | 65.0% | N/A | N/A |
| M4 MAC active ratio | 12.2% | 4.9% | 7.4% | N/A | N/A |
| M5 EXT beats / MAC | 0.0036 | 0.0047 | 0.0025 | N/A | N/A |
|     read beats / MAC | 0.0025 | 0.0032 | 0.0018 | N/A | N/A |
|     write beats / MAC | 0.0011 | 0.0015 | 0.0007 | N/A | N/A |
| M6 EXT read-req stall | 10.7% | 11.5% | 10.9% | N/A | N/A |
|     EXT write-req stall | 6.3% | 5.8% | 4.1% | N/A | N/A |
|     EXT write-data stall | 6.2% | 5.8% | 4.1% | N/A | N/A |
| M7 Vela signed error (cycles_total vs npu_active) | -77.9% | -79.7% | -88.2% | N/A | N/A |
| CV of npu_active | 0.7% | 0.0% | 0.2% | N/A | N/A |
