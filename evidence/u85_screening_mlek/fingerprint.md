| metric (median of 30) | kws_micronet_m | mobilenet_v2_1.0_224_INT8 | ad_medium_int8 | conv3x3_56x56x64 | matmul_xxT |
| --- | --- | --- | --- | --- | --- |
| outcome | SCREENED | SCREENED | SCREENED | SCREENED | SCREENED |
| M1 npu_active (cycles) | 334,714 | 10,121,486 | 951,418 | 612,396 | 14,880 |
|     window (PMCCNTR, incl. staging) | 2,867,075 | 73,640,918 | 8,835,128 | 9,221,338 | 397,520 |
| M2 npu_active / window | 11.7% | 13.7% | 10.8% | 6.6% | 3.7% |
| M3 peak MAC efficiency | 4.5% | 2.9% | 6.4% | 18.4% | 6.9% |
|     MAC active-cycle efficiency | 26.9% | 51.1% | 65.0% | 66.7% | 100.0% |
| M4 MAC active ratio | 16.9% | 5.7% | 9.8% | 27.7% | 6.9% |
| M5 EXT beats / MAC | 0.0010 | 0.0012 | 0.0007 | 0.0004 | 0.0022 |
|     read beats / MAC | 0.0010 | 0.0010 | 0.0007 | 0.0003 | 0.0020 |
|     write beats / MAC | 0.0000 | 0.0002 | 0.0000 | 0.0001 | 0.0002 |
| M6 EXT read-req stall | 2.1% | 2.2% | 1.1% | 3.3% | 2.9% |
|     EXT write-req stall | 0.0% | 0.2% | 0.0% | 1.2% | 0.2% |
|     EXT write-data stall | 0.0% | 0.2% | 0.0% | 1.2% | 0.2% |
| M7 Vela signed error (cycles_total vs npu_active) | -69.5% | -76.7% | -84.4% | 14.3% | -66.4% |
| CV of npu_active | 1.2% | 0.0% | 0.3% | 0.5% | 18.9% |
