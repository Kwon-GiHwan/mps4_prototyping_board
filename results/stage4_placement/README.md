# Stage 4 보완 — conv_base IFM·OFM DRAM/SRAM 배치 비교 결과 (boot 367–368, 2026-11-14)

계약 `evidence/stage4_placement/contract.md`(동결 `a63e206`)에 따른 결과다.
- **측정 조건:** FI101 Ethos-U85 1024 MAC, **TA profile 1**, Driver Runner 이미지 `70090f1`(A·B 같은 이미지), Stage 4 conv_base Vela 산출물 그대로.
- **측정 규모:** 각 조건 pass A·B × (warm-up 1 + 측정 4), 합계 20 RUN.
- 원시 데이터는 `evidence/stage4_placement/raw/`, 분석 결과는 `stage4p_summary.json`(`host/analysis/stage4p.py analyse`)에 있다.

**해석 범위.** B는 다음 네 가지를 함께 바꾼다.
- 물리 메모리: DDR → ISRAM.
- NPU AXI 포트: EXT → SRAM.
- 그 포트의 timing adapter: TA_EXT → TA_SRAM.
- 자원 공유: IFM·OFM이 가중치 staging과 SRAM 포트를 함께 쓰게 된다.

따라서 아래 차이는 **DRAM 접근 경로와 SRAM 접근 경로의 종합적인 차이**이고, 물리 DRAM 지연만의 효과가 아니다.

## 1. 실행과 단계별 확인

| 단계 | 결과 |
| --- | --- |
| P0 | 배포 검증 완료(boot `718c4562…`, bram `c80e77df…`). 재부팅 마커 정상, PING IDLE. capabilities(TA 22개 레지스터·버전, AXI, MEM_ATTR, fast memory `0x31000000`/`0x60000`)가 Stage 4와 같음 |
| P1 (boot 367, A) | `p1-gate` PASS. MAC_ACTIVE 2,304, MAC_DPU 1,152, pass B beat 7종이 Stage 4와 같음. NPU_ACTIVE 21,086.5(Stage 4 21,207, 차이 −120.5, tol 617), 출력 CRC 2368219480(Stage 4와 같음) |
| P2 (boot 368, B) | LOAD_MODEL_END ACK(load_status 0, 0.41 s). 이 ACK로 arena 2 MiB `0x310615C0–0x312615C0` 패턴·보수 되읽기, OFM 오염, IFM 되읽기가 통과했다. RUN 10회 모두 같은 기록: placement 1, arena = base1 = `0x310615C0`, REGIONCFG 0x153, QCONFIG 3, base0 `0x700003B0`과 base2 `0x31000000`은 A와 같음, job OK, IRQ 1회, flag 0x7f |
| P3 | B 나머지 RUN 완료. 중단 없음(`--stop-on-invalid`, refusal 없음) |
| 종료 | 카드 복원(m6 복원 기준과 digest 같음), postflight 재부팅, PING state 1, 카드 분리 확인 |

**해석 전제(`stage4p.py`):** 모두 통과했고 결과는 `INTERPRETED`다.
- Gate B PASS.
- 배치 되읽기: A·B 모두 일치.
- A/B 불변 항목(base0·base2·크기·n_base·모델·capabilities) 일치.
- 오염된 첫 RUN의 출력이 A·B 모두 golden과 같음.
- Gate C: A·B 모두 `PASS_EXACT`.
- A와 B의 출력 CRC 동일.
- P1 PASS.
- 트래픽 `TRAFFIC_CONSISTENT`.

**OFM 오염 검증의 범위(계약 §5).**
- 오염된 OFM이 실제 출력으로 덮어써졌다는 직접 증거는 load 뒤 첫 RUN(set 1 rep 1)뿐이다. 이 RUN은 A·B 모두 ofm_mismatch 0이고 CRC 2368219480이다.
- 이후 모든 측정 RUN에서 확인한 것: CRC가 같고, 펌웨어 비교에서 불일치가 0이다.
- 보조 증거: B의 pass B 5 RUN 모두 SRAM wr beat 3,708, EXT wr beat 0이다(A: 252 / 3,456).
- 모든 RUN에서 OFM이 각각 독립적으로 덮어써졌다고 증명한 것은 아니다.

## 2. 결과 (측정 4회의 중앙값, 괄호는 RUN range; TA profile 1, 이미지 `70090f1`)

| 지표 | A (DDR·EXT) | B (SRAM·SRAM 포트) | Δ (B − A) | tol | 판정 |
| --- | --- | --- | --- | --- | --- |
| NPU_ACTIVE, pass A | 21,086.5 (617) | 10,355.5 (332) | −10,731 (−50.9 %) | 617 | 밖 |
| NPU_ACTIVE, pass B | 21,192 (525) | 10,232 (417) | −10,960 (−51.7 %) | 525 | 밖 |
| **실행 비용** | | | | | **`B_LOWER`** |
| MAC_ACTIVE | 2,304 (0) | 2,304 (0) | 0 | 0 | |
| MAC_DPU_ACTIVE | 1,152 (0) | 1,152 (0) | 0 | 0 | |
| **계산 활동** | | | | | **`COMPUTE_SAME`** |
| 유효 MAC / MAC_ACTIVE 사이클 (884,736 / MAC_ACTIVE) | 384 | 384 | 0 | | |
| 유효 MAC / NPU_ACTIVE 사이클 | 41.96 | 85.44 | ×2.04 | | |
| MAC_ACTIVE / NPU_ACTIVE | 0.109 | 0.223 | | | |
| AO_ACTIVE | 3,535.5 (13) | 3,513 (3) | −22.5 | 35.4 | NOT_RESOLVED |
| WD_ACTIVE | 1,052 (70) | 1,048 (36) | −4 | 70 | NOT_RESOLVED |
| WD_STALLED | 6,583.5 (1,590) | 2,414 (18) | −4,169.5 | 1,590 | CHANGED |

**pass B 전송량(beat·transaction; RUN range는 모두 0).**

| 이벤트 | A | B | Δ | 사전 예측(설계 §6) |
| --- | --- | --- | --- | --- |
| 391 EXT wr beat | 3,456 | 0 | −3,456 | −3,456 |
| 386 EXT rd beat | 1,437 | 285 | −1,152 | −1,152 (IFM 576 × kernel 2) |
| 130 SRAM rd beat | 2,016 | 3,168 | +1,152 | +1,152 |
| 135 SRAM wr beat | 252 | 3,708 | +3,456 | +3,456 |
| 128 SRAM rd trans | 304 | 448 | +144 | (예측 없음) |
| 384 EXT rd trans | 171 | 27 | −144 | (예측 없음) |
| 132 SRAM wr trans | 16 | 3,472 | +3,456 | (예측 없음) |

- beat 이동은 사전 예측과 정확히 같다. IFM·OFM 트래픽만 EXT에서 SRAM으로 옮겨졌다는 배치 증거와 부합한다.
- 이 전송량 변화를 실행 지연의 인과적 기여로 환산하지 않는다.
- 이벤트 53·55(TRM 110 목록 밖, 보고만): A 0 / 5,600.5 → B 242 / 1,391. 결론의 근거로 쓰지 않는다.

## 3. 세 질문에 대한 답

1. **같은 Conv 명령 스트림에서 DRAM/SRAM 접근 경로를 바꿔도 MAC_ACTIVE와 유효 처리율은 유지되는가?**
   - 유지된다(`COMPUTE_SAME`). MAC_ACTIVE 2,304와 MAC_DPU_ACTIVE 1,152가 두 조건에서 같고, 두 조건 모두 RUN range가 0이다.
   - MAC_ACTIVE 사이클당 유효 MAC은 384로 같다.
   - 바뀐 것은 NPU_ACTIVE 사이클당 유효 MAC이다: 41.96 → 85.44. 전체 실행 시간이 줄었기 때문이다.
2. **NPU_ACTIVE는 얼마나 달라지는가?**
   - pass A: 21,086.5 → 10,355.5 (−10,731, −50.9 %).
   - pass B: 21,192 → 10,232 (−10,960, −51.7 %).
   - 두 pass 모두 허용폭(617 / 525) 밖이고 부호가 같으므로 `B_LOWER`다.
3. **계산부 활동 변화와 전체 실행 비용 변화가 일치하는가?**
   - 일치하지 않는다. 계산 활동(MAC_ACTIVE, MAC_DPU_ACTIVE)은 그대로인데 NPU_ACTIVE는 약 절반이 됐다.
   - 즉 비용 차이는 MAC 활동 사이클 밖에서 생겼다.
   - 함께 관측된 보조 지표:
     - WD_STALLED 감소(−4,169.5, `CHANGED`).
     - AO·WD_ACTIVE는 미판정.
   - 이 관측들로 원인을 배정하지 않는다. 특히 NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다.
   - 차이의 출처는 B에서 함께 바뀐 경로 전체다: 물리 메모리, AXI 포트, TA_EXT(rlat 500 / wlat 250) → TA_SRAM(rlat 32), staging과의 포트 공유.

## 4. 해석 한계

- 측정한 것은 조건 하나(conv_base 1×1, 24×24, Cin 16 → Cout 96)와 순서 하나(A → B)다. 순서 효과는 통제하지 않았다.
- Vela는 region 1을 DRAM으로 보고 스케줄을 골랐다. B는 SRAM에 맞춰 최적화한 구성이 아니라 같은 구성을 SRAM 경로에서 실행한 것이다.
- IFM 읽기와 OFM 쓰기의 몫은 나누지 않았다.
- 7개 모델로 일반화하지 않는다.
- 기존 이미지 `83398c7`의 수치는 P1 재현에만 썼다. 그 수치와 B를 직접 비교하지 않는다.
- FI101의 지연은 TA가 흉내 낸 것이다(profile 1). 결과는 실제 DRAM 장치의 지연을 측정한 것이 아니다.
