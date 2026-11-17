# Stage 6B-E2E-B 결과 — A2 graph I/O 배치(B0 DRAM / B3 SRAM) × EXT 읽기 지연

- 계약 `evidence/stage6b/stage6be2eb/contract.md`(동결 `c7ddffe`).
- preflight `b8fb580`.
- 공유 identity 정정 `6614ce8`(+ `338507d`).
- 보드 boot 458–462, 2026-11-17. **TA profile 1**, EXT RLATENCY 500 = 이미지 `70090f1`(bram `c80e77df…`), 1000 = L1000 이미지(bram `fd478e2d…`).
- 원시 자료 `evidence/stage6b/stage6be2eb/raw/`(54개, 보드와 sha256 일치), 세션 로그 `board/session.log`.
- 판정 `stage6be2eb.py judge`를 2회 실행했고 summary가 바이트 단위로 같다(`stage6be2eb_summary.json`).

## 판정

| 항목 | 결과 |
|---|---|
| Measurement Validity | **VALID**: REF 게이트 PASS, 5개 구성 모두 VALID, MAC_ACTIVE = H1-UC 20,736 |
| Graph I/O Placement | **IO_PLACEMENT_EFFECT_OBSERVED** |
| Latency Sensitivity | **IO_SENSITIVITY_REDUCED** |
| Residual EXT Path | **WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED** |
| Residual latency response (기술) | RESIDUAL_RESPONSE_OBSERVED |
| Pipeline Mechanism | **MECHANISM_UNRESOLVED**(계약상 고정) |

## NPU_ACTIVE (pass A 중앙값, range; TA profile 1)

| 구성 | L500 | L1000 | LE = L1000 − L500 | 비 |
|---|---|---|---|---|
| B0 (graph IO DDR) | 99,044 (326) | 159,122.5 (1,642) | 60,078.5 (tol 1,968) | 1.607 |
| B3 (graph IO SRAM) | 60,320 (1,197) | 72,526.5 (1,189) | 12,206.5 (tol 2,386) | 1.202 |
| IO_PE = B0 − B3 | 38,724 (tol 1,523) | 86,596 (tol 2,831) | | |

- Interaction = 60,078.5 − 12,206.5 = **47,872**(tol 4,354). B0의 지연 증가분 중 79.7 %가 graph IO를 옮기자 사라졌다.
- B3에도 지연 효과 12,206.5가 남는다(tol 2,386보다 큼). 원인은 배정하지 않는다.
- pass B NPU_ACTIVE: B0 99,718 / 160,173.5, B3 60,453.5 / 72,406(pass A와 일관).
- B0 재현: E2D 99,233.5 / 158,505 대비 −0.19 % / +0.39 %, 둘 다 재현으로 기록한다.
- REF(boot 458): 23,026.5, 게이트 PASS(boot 375 대비 `stage4k.reproduce`).

## 처리부 활동과 전송량 (TA profile 1)

| 지표 | B0 L500 | B3 L500 | B0 L1000 | B3 L1000 |
|---|---|---|---|---|
| MAC_ACTIVE / DPU | 20,736 / 20,736 | 20,736 / 20,736 | 20,736 / 20,736 | 20,736 / 20,736 |
| AO_ACTIVE | 14,974.5 | 14,921 | 14,921 | 14,922 |
| WD_ACTIVE | 5,900 | 5,882.5 | 3,571 | 3,581 |
| WD_STALLED | 23,662 | 21,348.5 | 42,774 | 34,884 |
| EXT read beat / 트랜잭션 | 27,066 / 10,417 | **11,322** / 793 | 27,066 / 10,417 | **11,322** / 793 |
| EXT write beat | 7,872 | **0** | 7,872 | **0** |
| SRAM read beat / 트랜잭션 | 25,088 / 1,568 | 40,832 / 11,192 | 같음 | 같음 |
| SRAM write beat / 트랜잭션 | 9,216 / 576 | 17,088 / 5,388 | 같음 | 같음 |

- MAC, DPU, AO, WD_ACTIVE는 배치에 따라 변하지 않는다. 바뀐 것은 메모리 경로와 NPU_ACTIVE다.
- 전송량 보존(사전 기술):
  - read 합 52,154 = 52,154, write 합 17,088 = 17,088.
  - EXT에서 빠진 read 15,744 beat와 9,624 트랜잭션이 SRAM read에 그대로 더해졌다.
  - EXT write 7,872 beat는 SRAM write로 옮겨 갔다.
- B3 EXT read 11,322 beat(181,152 B)는 정적 기대 11,321.25(가중치 174,752 + scale 5,760 + command stream 628 = 181,140 B)보다 12 B 많다(±1 % 안).
  - 두 지연에서 같고, EXT write는 0이다.
  - 따라서 남은 EXT 접근은 가중치·scale과 command stream으로 설명된다.
  - 읽기 트랜잭션 793개, 평균 14.3 beat(228 B)로 큰 burst다.
- 옮겨 간 FM 전송은 SRAM 포트에서 작은 트랜잭션이다. read는 15,744 beat / 9,624 트랜잭션(평균 1.64 beat), write는 7,872 beat / 4,812 트랜잭션이다. read 트랜잭션 수(9,624)는 B0 EXT read 트랜잭션 감소분과 같다. EXT write 트랜잭션은 pass에 없다.
- WD_STALLED는 B3에서 줄었지만(L1000 −7,890), 대기 총량으로 해석하지 않는다.

## Vela와의 연결 (B0만, B3는 NO_COMPARABLE_VELA_ESTIMATE)

- B0 board/Vela: 1.867(L500), 1.914(L1000). LE board 60,078.5 대 Vela 30,090.
- Vela A2 비용에서 DRAM 접근은 graph IO(FM read 141,312 B, write 141,312 B)와 가중치다.
- 보드에서 graph IO만 SRAM으로 옮기자 NPU_ACTIVE가 39 % / 54 % 줄었다. 지연 반응은 1/5로 줄었다.
- 즉 B0의 실행시간과 지연 민감도의 대부분은 graph IO의 EXT 접근(작은 트랜잭션 10,417개 중 9,624개)과 관련된다.
- Vela는 이 경로를 대역폭 기반 바이트 비용으로만 세고, 트랜잭션 수나 지연 중첩은 세지 않는다. 이것이 B0 과소예측과 일관된다.
- 이 연결은 관측된 상관이며 원인 확정이 아니다. 개별 트랜잭션 지연 비용은 측정하지 않았다.

## 미해결

- B3에 남은 지연 효과 12,206.5가 어디서 오는지는 아직 모른다. 후보는 가중치 공급, command stream fetch, 그리고 겹침·의존성이다. 가르는 측정이 없다.
- 입력 대 출력의 몫은 따로 보지 않았다(함께 옮김).
- 조건마다 boot가 하나뿐이다. drift는 시작 때 REF로만 확인했다.
- 배치를 바꾸면 물리 메모리, AXI 포트, TA(SRAM 대 EXT)가 함께 바뀐다.
