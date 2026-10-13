| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | SCREENED | SCREENED | SCREENED | SCREENED |
| M1 npu_active (cycles) | 521,665 | 10,543,758 | 1,359,638 | 607,386 | 15,096 |
|     window (PMCCNTR, incl. staging) | 3,070,016 | 73,788,649 | 9,224,137 | 9,537,304 | 396,450 |
| M2 npu_active / window | 17.0% | 14.3% | 14.7% | 6.4% | 3.8% |
| M3 peak MAC efficiency | 2.9% | 2.8% | 4.5% | 18.6% | 6.8% |
|     MAC active-cycle efficiency | 26.9% | 49.5% | 62.0% | 66.7% | 100.0% |
| M4 MAC active ratio | 10.8% | 5.6% | 7.2% | 27.9% | 6.8% |
| M5 EXT beats / MAC | 0.0006 | 0.0008 | 0.0005 | 0.0004 | 0.0022 |
|     read beats / MAC | 0.0006 | 0.0008 | 0.0005 | 0.0003 | 0.0020 |
|     write beats / MAC | 0.0000 | 0.0000 | 0.0000 | 0.0001 | 0.0002 |
| M6 EXT read-req stall | 0.3% | 1.8% | 0.8% | 3.4% | 2.9% |
|     EXT write-req stall | 0.0% | 0.0% | 0.0% | 1.2% | 0.2% |
|     EXT write-data stall | 0.0% | 0.0% | 0.0% | 1.2% | 0.2% |
| M7 Vela signed error (cycles_total vs npu_active) | -80.1% | -74.1% | -86.5% | 92.1% | -44.8% |
| CV of npu_active | 0.6% | 0.1% | 0.2% | 0.5% | 19.1% |
