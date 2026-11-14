# Stage 4 보완 — conv_base IFM·OFM DRAM/SRAM 배치 비교: 계약 초안 (2026-11-14, **동결 전, 실행 전**)

> **대체됨(2026-11-14):** owner 승인 뒤 `contract.md`로 동결했다. 이 초안은 이력으로만 남긴다.

- 이 문서는 초안이다. 동결하지 않았고, 이 초안으로 보드를 실행하지 않았다.
- 동결과 보드 실행은 owner의 별도 결정 뒤에 한다.
- 설계: `docs/plan/stage4_memory_placement_plan.md`(`19adf32`).
- 구현과 보드 없는 검증: `evidence/stage4_placement/implementation_check.md`.

## 1. 질문과 조건

**질문.** 같은 1×1 Conv 명령 스트림에서 region 1(IFM·OFM)의 메모리 경로만 DDR/EXT에서 SRAM/SRAM 포트로 바꾸면, TA profile 1에서 실행 비용과 계산 활동이 달라지는가.

| 항목 | A (기준) | B (변경) |
| --- | --- | --- |
| workload | `evidence/stage4/workloads/s4_conv_base.drwl` (`2681c566…`, word 7 = 0, Stage 4 blob 그대로) | `evidence/stage4_placement/workloads/s4p_conv_base_sram.drwl` (`83034eb1…`, word 7 = 1, 나머지 바이트 동일) |
| region 1 (IFM·OFM) | `0x700015C0`, DDR, EXT 포트(REGIONCFG 0x15F), TA_EXT | `0x310615C0`, ISRAM0, SRAM 포트(REGIONCFG 0x153), TA_SRAM |
| region 0 / 2 / QBASE | DDR·EXT / `0x31000000`·SRAM / DDR·EXT | 동일 |
| 이미지 | **새 이미지 하나**(커밋 `70090f1` 이후 빌드, sha256은 동결 때 기록) | 같은 이미지 |
| 고정 조건 | TA profile 1, Vela 5.0.0 산출물 재사용, Dedicated_Sram, WAIT_WFE, D-cache on, Stage 4 pass A·B 이벤트 | 동일 |

- **함께 바뀌는 것.** B는 물리 메모리, NPU AXI 포트, 그 포트의 TA를 함께 바꾼다. 이 셋은 분리하지 않는다.
- 결과는 "TA profile 1에서 DRAM 경로와 SRAM 경로의 비교"로만 읽는다.
- TFLM arena의 나머지 2 MiB(CPU 전용 자료)도 함께 SRAM으로 간다. 끝이 `0x312615C0`이라 ISRAM1에 걸친다.

## 2. 프로토콜 (최대 20 RUN)

1. **사전 검증 P0** (보드 없음, 동결 전에 완료해야 함):
   - `sh test.sh` ALL PASS
   - `evidence/stage4_placement/mutate.py` 전부 KILLED, sha256 복원
   - 빌드 gate 통과
   - `stage4p.py gate-b` PASS
2. **배포**: owner 승인 세션 하나로 새 evidence root에 배포한다. restore 기준은 `~/evsweep/evidence_m6`이다.
3. **boot 1 = A**:
   ```
   run_driver_events.py --workload <A> --ids @<Stage 4 ids> --conditions @<"wfe 0 0 off 1,2"> --repeats 5 --outputs
   ```
   pass A 5 RUN + pass B 5 RUN(각 warm-up 1 + 측정 4). workload는 한 번만 올린다.
4. **boot 2 = B**: 같은 명령에 `--workload <B>`.
5. **순서.** 순서는 A → B로 고정한다. 반복이나 순서 교차는 하지 않고, 순서 효과는 통제하지 않았다고 보고한다.
6. 합계 20 RUN이다. "5 RUN 추가" trigger는 정하지 않는다.
7. **복원.** `restore.sh ~/evsweep/evidence_m6` 다음 `postflight.sh`를 실행한다.

보드 시간 추정: boot 2개 × (reboot + 70 KB 업로드 + 10 RUN + 출력 조회) ≈ 6–10분, 배포·복원 ≈ 5분.

**측정 boot 안에서 확인하는 사전 검증 (RUN 추가 없음).**

| # | 내용 | 실패 시 |
| --- | --- | --- |
| P1 | **A 재현.** 새 이미지의 A를 Stage 4 conv_base(이미지 `83398c7`, boot 330, TA profile 1)와 비교한다. 다음이 모두 맞아야 한다: MAC_ACTIVE 2,304; MAC_DPU 1,152; pass B beat 128/130/132/135/384/386/391 = 304/2,016/16/252/171/1,437/3,456(Stage 4 range 0); NPU_ACTIVE pass A의 \|중앙값 − 21,207\| ≤ max(1 %, 367, A range); 출력 CRC 2368219480 | 새 이미지가 기준을 바꾼 것이다. B를 해석하지 않는다 |
| P2 | **B 적재.** LOAD_MODEL_END가 ACK(load_status 0)를 돌려줘야 한다. arena 2 MiB 쓰기·읽기 검사(보수 패턴 포함), OFM 0x5A 오염, IFM 되읽기가 포함된다 | NACK(0x600 SRAM 공간 없음, 0x701/0x702 메모리 검사, 0x800 IFM)나 응답 없음·fault가 나면 중단하고 보존·복원한다 |
| P3 | **배치 되읽기.** 매 RUN의 record schema 4에서 placement, arena_base = base1, REGIONCFG/QCONFIG at IRQ, REGIONCFG_MATCH를 확인한다. `run_driver_events.py`가 RUN마다 검사한다 | 불일치하면 그 boot를 즉시 중단한다(RULE_CAPABILITY / RULE_RECORD_SCHEMA). 그 RUN은 보존한다 |

## 3. 판정 규칙 (`host/analysis/stage4p.py`, 데이터 전에 고정)

**해석 전제(하나라도 실패하면 `NOT_INTERPRETED`).**
- gate B: 두 blob의 차이는 word 7뿐이다. A는 Stage 4 blob과 같다. 모델·명령 스트림·IFM·golden도 같다.
- 배치: 모든 측정 RUN이 아래 표와 맞아야 한다. A와 B 사이에서 n_base, model, arena_len, base0, base2, 크기가 같아야 하고, capabilities(MEM_ATTR 0–3, AXI, TA 22개 레지스터와 버전, fast memory)도 같아야 한다.

  | | A | B |
  | --- | --- | --- |
  | schema / placement | 4 / 0 | 4 / 1 |
  | arena_base = base1 | `0x700015C0` | `0x310615C0` |
  | base_size1 | 0xFC00 | 0xFC00 |
  | REGIONCFG / QCONFIG at IRQ | 0x15F / 3 | 0x153 / 3 |
- 오염: load 뒤 첫 RUN(set 1 rep 1)의 출력이 golden과 같아야 한다. OFM이 0x5A로 오염된 RUN은 이것 하나뿐이다.
- gate C: 출력 `PASS_EXACT`, 측정 RUN 모두 유효, pass마다 4회.
- A와 B의 출력 CRC가 같아야 한다.
- P1 통과.
- 트래픽: pass B 중앙값 기준으로 EXT wr(391)↓, EXT rd(386)↓, SRAM rd(130)↑, SRAM wr(135)↑가 모두 tol 밖이어야 `TRAFFIC_CONSISTENT`다.
  - 사전 예측값: −3,456, −1,152, +1,152, +3,456 beat.
  - `TRAFFIC_INCONSISTENT`면 해석을 중단한다.

**지표.** 측정 4회의 중앙값과 RUN range를 쓴다.
- 판정에 쓰는 지표: NPU_ACTIVE(35), MAC_ACTIVE(48), MAC_DPU_ACTIVE(51).
- 기록만 하는 보조 지표: AO_ACTIVE(64), WD_ACTIVE(80), WD_STALLED(81), pass B beat(128/130/132/135/384/386/391).

**규칙.**
- 실행 비용(NPU_ACTIVE):
  - pass마다 tol = max(A 중앙값의 1 %, A range, B range)를 정한다.
  - 두 pass가 모두 tol 밖이고 부호가 같으면 `B_LOWER` / `B_HIGHER`다.
  - 그 외에는 `UNRESOLVED`다.
- 계산 활동: \|ΔMAC_ACTIVE\|와 \|ΔMAC_DPU\|가 모두 max(A range, B range) 이하이면 `COMPUTE_SAME`, 아니면 `COMPUTE_CHANGED`다.
- 보조 지표는 같은 tol로 `CHANGED` / `NOT_RESOLVED`만 기록하고 원인을 배정하지 않는다.
- SRAM/EXT 전송량 변화를 실행 지연의 인과적 기여로 환산하지 않는다.
- 허용폭과 규칙은 동결 뒤 바꾸지 않는다. 결과를 보고 완화하지 않는다.

## 4. 해석 범위

| 결과 | 쓸 수 있는 문장 |
| --- | --- |
| `COMPUTE_SAME` + `B_LOWER`/`B_HIGHER` | 같은 계산 구성에서 region 1(IFM·OFM)의 메모리 경로(물리 메모리·포트·TA)를 바꾸면 전체 비용이 달라졌다. DRAM 지연 하나의 효과로 확정하지 않는다 |
| `COMPUTE_CHANGED` | 같은 명령 스트림에서 계산 활동이 바뀌었다. 함께 바뀐 실행·계측 조건을 보고하고, 메모리 위치 효과로 해석하지 않는다 |
| `UNRESOLVED` | 이번 조건에서 차이를 판정하지 못했다. 영향이 없다는 뜻이 아니다 |
| `NOT_INTERPRETED` | 성능을 해석하지 않는다. 원시 데이터를 보존하고 보고한다. 재측정하지 않는다 |

**해석 금지.**
- NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다.
- IFM 읽기와 OFM 쓰기의 몫을 나누지 않는다.
- Vela가 SRAM을 전제로 골랐을 스케줄과 비교하지 않는다.
- 7개 모델로 일반화하지 않는다.
- 기존 이미지(`83398c7`)의 수치와 새 이미지의 B를 직접 비교하지 않는다. 기존 이미지는 P1 재현에만 쓴다.

## 5. 중단 조건

- P0, P1, P2, P3 중 하나가 실패한 경우.
- boot가 RUN 전에 멈춘 경우.
- 위 어느 경우에도 다른 주소, arena 크기, 포트로 바꿔 다시 시도하지 않는다. 바꾸려면 Amendment와 승인이 필요하다.

## 6. 알려진 한계 (동결 전에 owner가 확인할 것)

- **오염 범위.**
  - OFM 오염은 load 때 한 번만 한다. 그래서 "이전 출력이 남아 통과"를 배제하는 것은 load 뒤 첫 RUN(pass A warm-up)뿐이다.
  - 나머지 RUN은 다음 근거로 판단한다: 출력 CRC가 같음, 작업 완료(IRQ 1회, job OK), pass B의 RUN별 SRAM/EXT write beat.
  - RUN마다 오염하면 RUN 경로에 CPU 작업이 들어간다. 지시에 따라 하지 않았다.
- **arena 위치.** B의 arena 2 MiB 중 CPU 전용 꼬리가 ISRAM1(`0x31200000` 이상)에 놓인다. NPU가 접근하는 region 1은 `0x310711C0`까지라 ISRAM0 안이다.
- **분리 불가 변경.** B에서는 region 1과 region 2(가중치 staging)가 같은 SRAM 포트·TA_SRAM을 함께 쓴다. 이 공유도 B 구성의 일부다.
