| workload | class | N_MAC | NPU cycles | MAC/cycle | peak MAC eff. | MAC active ratio | MAC active-cycle eff. | SRAM beat/MAC | EXT beat/MAC | SRAM beat/NPU cycle | EXT beat/NPU cycle | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | model | 15,556,352 | 90,930 | 171.1 | 16.7% | 62.1% | 26.9% | 0.0026 | 0.0010 | 0.445 | 0.174 | 0.82% |
| ad_medium_int8 | model | 62,346,720 | 146,412 | 425.8 | 41.6% | 64.0% | 65.0% | 0.0018 | 0.0007 | 0.768 | 0.301 | 0.57% |
| mobilenet_v2_1.0_224_INT8 | model | 300,775,552 | 1,448,582 | 207.6 | 20.3% | 39.7% | 51.1% | 0.0036 | 0.0012 | 0.742 | 0.241 | 0.10% |
| conv3x3 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| dw3x3 | isolated_operator | 3,612,672 | 144,225 | 25.0 | 2.4% | 19.6% | 12.5% | 0.0003 | 0.0147 | 0.009 | 0.368 | 0.25% |
| pw1x1 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| fc1024 | isolated_operator | BASELINE_FAIL |  |  |  |  |  |  |  |  |  |  |
| conv3x3@a2 | isolated_operator | 115,605,504 | 213,654 | 541.1 | 52.8% | 79.3% | 66.7% | 0.0004 | 0.0004 | 0.200 | 0.238 | 0.38% |
| pw1x1@a2 | isolated_operator | 25,690,112 | 158,742 | 161.8 | 15.8% | 19.8% | 80.0% | 0.0014 | 0.0020 | 0.220 | 0.321 | 0.28% |
| fc1024@a2 | isolated_operator | 1,048,576 | 127,044 | 8.3 | 0.8% | 3.2% | 25.0% | 0.0000 | 0.0633 | 0.000 | 0.522 | 0.34% |
