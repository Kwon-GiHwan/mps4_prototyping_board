| operator | NPU cycles | MAC active ratio | DPU active ratio | DPU / MAC-active | AO active ratio | WD active ratio | WD stalled ratio | IB stall ratio † | W/ACC stall ratio † | CV(NPU active) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conv3x3 | 213,506 | 79.3% | 79.3% | 1.000 | 5.9% | 11.7% | 86.2% | 18.8% | 0.0% | 0.32% |
| dw3x3 | 144,200 | 19.6% | 19.6% | 1.000 | 17.6% | 0.1% | 98.4% | 78.9% | 0.0% | 0.27% |
| pw1x1 | 158,522 | 19.8% | 19.8% | 1.000 | 16.3% | 8.6% | 59.8% | 40.8% | 14.8% | 0.31% |

† driver-derived event (contract §2)
