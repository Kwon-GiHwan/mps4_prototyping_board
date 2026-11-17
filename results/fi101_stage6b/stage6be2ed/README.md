# Stage 6B-E2E-D 결과 — Weight/Scale 배치(B3 대 B3w) × EXT 읽기 지연

- 계약 `9e02818`, preflight `8179475`, 펌웨어·공유 모듈 `14077be`.
- 보드 boot 463–467(2026-11-17), **TA profile 1**, 새 runner 이미지(L500 bram `ec0e8c3b…`, L1000 `ca7d2e49…`).
- 원시 자료 `evidence/stage6b/stage6be2ed/raw/`(54개, 보드와 sha256 일치), 세션 로그 `board/session.log`.
- 판정 2회 실행 결과가 바이트 동일하다(`stage6be2ed_summary.json`).
- 결과는 NPU 내부 실행시간(NPU_ACTIVE)이다. CPU staging과 가중치 복사는 측정창 밖이다.

## 판정

| 항목 | 결과 |
|---|---|
| Measurement Validity | **VALID**: REF 게이트 PASS, 5/5 VALID, MAC 20,736 |
| B3 동등성(새 이미지) | **B3_REPRODUCED**: 60,224.5 / 72,412.5 대 E2E-B 60,320 / 72,526.5, 전송량 정확히 같음 |
| Remap Validity | **WEIGHT_SCALE_REMAP_CONFIRMED** |
| Residual Latency | **WEIGHT_PATH_DOMINANT_RESPONSE** |
| Pipeline Mechanism | **MECHANISM_UNRESOLVED**(계약상 고정) |

## NPU_ACTIVE (pass A 중앙값, range; TA profile 1)

| 구성 | L500 | L1000 | LE | tol_LE |
|---|---|---|---|---|
| B3 (가중치·scale EXT) | 60,224.5 (300) | 72,412.5 (900) | **12,188** | 1,200 |
| B3w (가중치·scale SRAM 사본) | 64,064.5 (822) | 64,843 (793) | **778.5** | 1,615 |
| B3 − B3w | **−3,840**(tol 1,122) | **+7,569.5**(tol 1,693) | | |

- Residual_Ratio = 778.5 / 12,188 = **0.064**(잡음 구간 −0.06–0.22).
- Weight_Path_Removal_Effect = 11,409.5. 감소량이 허용폭 2,815를 넘고, B3w에 남은 반응(778.5)은 tol 1,615 안이다.
- command stream만 EXT에 남은 B3w에서는 EXT 지연 반응이 관측되지 않았다(`RESIDUAL_RESPONSE_NOT_OBSERVED`).
- **배치 효과는 한 방향이 아니다.** L500에서는 B3w가 3,840 느리고, L1000에서는 7,569.5 빠르다. 가중치를 SRAM으로 옮기면 EXT 지연 민감도는 사라지지만, L500 조건에서는 고정 비용이 늘었다.

## 처리부 활동과 전송량 (TA profile 1)

| 지표 | B3 L500 | B3w L500 | B3 L1000 | B3w L1000 |
|---|---|---|---|---|
| MAC / DPU | 20,736 / 20,736 | 20,736 / 20,736 | 20,736 / 20,736 | 20,736 / 20,736 |
| AO_ACTIVE | 14,918.5 | 14,927 | 14,920.5 | 14,927 |
| WD_ACTIVE | 5,912 | 6,286 | 3,579 | 6,286 |
| WD_STALLED | 21,146.5 | 24,344 | 34,641.5 | 24,344 |
| EXT read beat / 트랜잭션 | 11,322 / 793 | **40 / 11** | 11,322 / 793 | **40 / 11** |
| EXT write | 0 | 0 | 0 | 0 |
| SRAM read beat / 트랜잭션 | 40,832 / 11,192 | 52,114 / 11,974 | 40,832 / 11,192 | 52,114 / 11,974 |
| SRAM write beat / 트랜잭션 | 17,088 / 5,388 | 같음 | 같음 | 같음 |

- **remap 확인**:
  - BASEP0 = `0x31280420`(모든 RUN), REGIONCFG 0x550, 출력 PASS_EXACT.
  - EXT read는 40 beat(command stream 628 B → 640 B), 11 트랜잭션이다.
  - SRAM read는 +11,282 beat로 가중치·scale 정적 기대와 정확히 같다. read 합 52,154도 보존된다.
- MAC, DPU, AO는 변하지 않았다. 바뀐 것은 가중치 공급 경로, WD 활동, NPU_ACTIVE다.
- **B3w의 모든 카운터는 두 지연에서 같다**(WD_ACTIVE, WD_STALLED, 트래픽). EXT에 남은 command stream fetch 40 beat는 이 지연 범위에서 실행시간을 움직이지 않았다.
- WD_ACTIVE와 WD_STALLED 해석:
  - WD_ACTIVE는 B3w에서 6,286으로, B3 L500(5,912)보다 크다.
  - WD_STALLED는 B3에서 지연과 함께 커지고(21,146.5 → 34,641.5), B3w에서는 24,344로 일정하다.
  - 이 수치는 가중치 대기시간으로 치환하지 않는다.
- 가중치 읽기는 B3에서 EXT 큰 burst(평균 14.3 beat)였다. B3w에서는 SRAM 트랜잭션 782개(약 14.4 beat)로 SRAM 포트를 graph IO·중간 텐서 트래픽과 함께 쓴다. L500에서 B3w가 느린 이유 후보는 SRAM 포트 공유·TA_SRAM 설정·버퍼 의존성이며, 구분하지 않았다.

## 기존 결과와의 일관성

- **E2E-B**: B3 지연 효과 12,206.5. 새 이미지에서 12,188이 재현됐다.
- **E2E-C 예측**: H-R1(가중치·scale 공급)이면 LE(B3w) ≤ 0.25·LE(B3)이고 EXT read는 약 39 beat. 관측은 0.064와 40 beat로, 사전 예측과 일관된다.
- **E2D W0-P1**(Conv 단독, 가중치만 EXT): LE 13,545. 같은 가중치 경로를 지닌 B3와 비슷하다.
- 정리: EXT 읽기 지연 민감도는 graph IO 경로(E2E-B, 약 80 %)와 가중치·scale 경로(E2E-D, 남은 것의 약 94 %)로 거의 다 설명된다. command fetch의 지연 반응은 이 측정에서 tol 안이다.

## Vela 연결 (B3w는 NO_COMPARABLE_VELA_ESTIMATE)

- Vela A2 Conv의 DRAM 항(가중치)은 L500 16,409 → L1000 32,818로, 연산 비용은 24,290 → 32,818로 늘어난다(E2E-C 사실).
  - Vela는 가중치 경로의 지연 반응을 일부 표현한다(8,528).
  - 보드 B3는 12,188이다.
- 보드에서는 가중치를 SRAM으로 옮기면 L500에서 오히려 느려졌다. Vela의 max(npu, SRAM, DRAM) 모델은 같은 연산 안에서 SRAM 트래픽이 늘 때의 포트 공유나 의존성 비용을 따로 세지 않는다. 이것이 표현되지 않는 후보다(미검증).
- B3w에 Vela 값을 대입하거나 오차를 계산하지 않았다.

## 미해결

- L500에서 B3w가 3,840 느린 원인: SRAM 포트 경합, TA_SRAM(32 사이클 지연·bw cap) 조건, WD 버퍼 의존성 중 무엇인지 가르는 측정이 없다.
- 가중치와 scale/bias는 함께 옮겨져(region 0) 따로 보지 않았다.
- 조건마다 boot는 하나다. drift는 REF로만 확인했다.
