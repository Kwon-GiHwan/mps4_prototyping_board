# Stage 4 보완 — conv_base IFM·OFM DRAM/SRAM 배치 비교 (동결 2026-11-14, boot 367–368 전)

Owner 승인(2026-11-14): `READY_FOR_BOARD_VALIDATION` 수용, 계약 동결, 최대 20 RUN 보드 검증. 이 문서는
`contract_draft.md`를 대체한다(초안은 이력으로 남긴다). 설계 `docs/plan/stage4_memory_placement_plan.md`, 구현·보드 없는 검증
`implementation_check.md`. 동결 뒤 규칙·허용폭은 바꾸지 않고, 바꿔야 하면 Amendment로 남긴다.

## 1. 고정 조건

| 항목 | 값 |
| --- | --- |
| 보드 | FI101 Ethos-U85 1024 MAC (MPS4), Cortex-M85, D-cache on, WAIT_WFE |
| TA | **profile 1** (MLEK sys_dram_mid가 부팅 때 설정; 이미지는 TA를 쓰지 않음). P0에서 Stage 4 값과 같음을 확인 |
| 이미지 (A·B 동일) | 커밋 `70090f1`의 driver runner. boot.bin `718c4562…ef59`, bram.bin `c80e77df…e99c`, ddr.bin `374708ff…37bb` (16 B 0, J11), images.txt `af688281…423f` |
| Vela 산출물 | Stage 4 conv_base 그대로 (모델 `fadf33d7…`, 명령 스트림 `596fe964…`, 가중치 4,032 B). 재컴파일 없음 |
| A workload | `s4p_conv_base_ddr.drwl` = Stage 4 blob `2681c566…f267` (word 7 = 0) |
| B workload | `s4p_conv_base_sram.drwl` `83034eb1…1de9` (word 7 = 1, byte 28만 다름; Gate B PASS) |
| A region 1 (IFM·OFM) | `0x700015C0`, DDR, EXT 포트, REGIONCFG 0x15F, TA_EXT |
| B region 1 | `0x310615C0`, ISRAM0, SRAM 포트, REGIONCFG 0x153, TA_SRAM |
| 그 밖 | region 0 (DDR, EXT), region 2 staging (`0x31000000`, SRAM), QCONFIG 3, fast scratch 384 KiB — A·B 동일 |
| PMU | Stage 4 pass A (35 48 51 53 55 64 80 81) / pass B (35 128 130 132 135 384 386 391), `ids.txt` |
| RUN | boot당 pass A 5 + pass B 5 (warm-up 1 + 측정 4), boot 2개, **최대 20 RUN**, 추가 반복 없음 |
| boot | 367 = A, 368 = B, 이 순서 고정 (순서 효과 미통제로 보고) |

**해석 범위.** B는 물리 메모리·NPU AXI 포트·그 포트의 TA를 함께 바꾸고, IFM·OFM이 가중치 staging과 SRAM 포트·TA_SRAM을
공유하게 된다. 결과는 **DRAM 접근 경로와 SRAM 접근 경로의 종합적인 차이**로만 읽는다. 물리 DRAM 지연만의 효과로 확정하지 않는다.

## 2. 실행 전 확인 (보드 전, 결과)

| 항목 | 근거 | 상태 |
| --- | --- | --- |
| SRAM 후보 주소와 다른 항목의 충돌 | 새 이미지: SRAM에는 `cache_arena`(0x31000000, 0x60000)뿐(빌드 gate, nm, objdump), 코드·데이터·heap BRAM, stack DTCM, staging DDR 0x90000000, images.txt가 SRAM에 아무것도 올리지 않음 | 정적 확인 |
| CPU의 SRAM 접근 가능 여부, 접근 권한·MPC | MLEK에 MPC/SAU 설정 코드가 없다(grep 0건); 보드의 MPC 상태는 모른다 | **보드에서 B load 때 확인** (P2-a). 실패하면 B RUN 없이 중단 |
| CPU/NPU 주소 매핑 | `ethosu_address_remap` identity (변경 없음, 바이트 동일); region 2가 같은 SRAM secure alias로 Stage 4에서 동작 | 정적 확인, NPU의 0x3106… 접근은 P2-b |
| SRAM 배치의 CPU 캐시 Clean/Invalidate | 필요하다. MLEK `ethosu_cpu_cache.c`가 주소와 무관하게 job 전 `SCB_CleanDCache`, job 뒤 `SCB_InvalidateDCache`(상태 플래그로 교대); 새 이미지에서 MLEK의 strong 정의(T)를 `ethosu_invoke_v3`/`ethosu_wait`가 호출. load 시 검사·오염·IFM 복사 뒤 runner가 `SCB_CleanInvalidateDCache` | 정적 확인. 일관성의 실측은 P2-b (오염된 첫 RUN 출력 일치) |
| Driver 캐시 경로가 B에도 적용되는지 | 위 함수는 base 주소를 보지 않으므로 A·B가 같은 코드·같은 동작 | 정적 확인 |
| 실패·응답 정지 시 복원 | `sudo_session.sh`: 실패한 단계에서 세션을 멈추고 이 세션이 올린 이미지를 `restore_mlek`로 복원; 끝에 `postflight.sh` (재부팅, PING, USB_OFF, 카드 분리 확인). 세션이 실패로 끝나면 postflight를 따로 실행 | 절차 확인 (`sudo_session.sh --check` OK) |

캐시 일관성이나 접근 권한이 보드에서 확인되지 않으면 (P2-a/P2-b 실패) 성능 비교를 하지 않는다.

## 3. 단계 (세션 `board/session.txt`, 한 번의 owner 승인 세션)

| 단계 | 내용 | 자동 중단 |
| --- | --- | --- |
| P0 | 배포(`deploy_mlek`, 새 evidence root `evidence_s4p`), boot 367 재부팅 마커(CPUWAIT 해제), PING state IDLE, capabilities 저장. capabilities의 TA 22개 레지스터·버전, AXI limit, MEM_ATTR 0–3, fast memory가 Stage 4 conv_base(boot 330)와 같아야 한다 | PING 실패는 boot 거부; capabilities 불일치는 `p1-gate` FAIL |
| P1 | boot 367 = A 10 RUN (`STOP_ON_INVALID=1`: 무효 RUN이나 출력 불일치에서 boot 즉시 종료). 이어 `stage4p.py p1-gate`: A의 gate C(PASS_EXACT, 측정 4회 × 2 pass 유효), 배치 되읽기(schema 4, placement 0, arena 0x700015C0 = base1, REGIONCFG 0x15F, QCONFIG 3), 오염된 첫 RUN 출력 일치, **MAC_ACTIVE 2,304, MAC_DPU_ACTIVE 1,152, pass B beat 128/130/132/135/384/386/391 = 304/2,016/16/252/171/1,437/3,456**, NPU_ACTIVE pass A 중앙값 21,207 ± max(1 %, 367, A range), 출력 CRC 2368219480 | `p1-gate` exit 1 → 세션 중단, 카드 복원, **B 미실행** |
| P2 | boot 368 = B. (a) LOAD_MODEL_END: arena 2 MiB(0x310615C0–0x312615C0)에 패턴·보수 쓰기와 clean+invalidate 뒤 되읽기, OFM 0x5A 오염, IFM 되읽기 — NACK(0x600/0x701/0x702/0x800)·응답 없음이면 RUN 없이 boot 종료. (b) 첫 RUN(pass A warm-up, 오염된 OFM) 출력 일치, (c) RUN마다 placement 1, arena = base1 = 0x310615C0, REGIONCFG 0x153 / QCONFIG 3 (REGIONCFG_MATCH), job 완료·IRQ 1회·overflow 없음 | 불일치·무효·출력 불일치 → boot 즉시 종료 (`RULE_CAPABILITY` / `RULE_RECORD_SCHEMA` / `RULE_RUN_INVALID`), 남은 RUN 없음 |
| P3 | P2를 통과한 B의 나머지 RUN (같은 boot). 분석(Mac): `stage4p.py analyse` | 아래 §4 해석 전제 |
| 종료 | `restore_mlek` → `postflight.sh` (m6 이미지, PING, 카드 분리) | — |

예상 보드 시간: boot 2개 × (재부팅 + 70 KB 업로드 + load 검사 + 10 RUN + 출력 조회) ≈ 6–10분, 배포·복원·postflight ≈ 5분.

## 4. 판정 규칙 (`host/analysis/stage4p.py`, 이 커밋의 코드; 테스트 `test_stage4p.py`, mutation 38/38 KILLED)

**해석 전제** — 하나라도 실패하면 `NOT_INTERPRETED`(성능 비교 안 함, 원시 데이터 보존, 재측정 없음):
gate B; 두 조건의 배치 되읽기(위 표 값, REGIONCFG_MATCH); A·B 사이 n_base·model·arena_len·base0·base2·크기 동일,
capabilities(MEM_ATTR, AXI, TA, fast memory) 동일; 오염된 첫 RUN 출력 일치(A·B); gate C (`PASS_EXACT`, 측정 RUN 유효,
pass당 4회); A·B 출력 CRC 동일; P1; 트래픽 방향 — pass B 중앙값에서 EXT wr(391)↓, EXT rd(386)↓, SRAM rd(130)↑,
SRAM wr(135)↑가 모두 tol 밖이면 `TRAFFIC_CONSISTENT`, 아니면 `TRAFFIC_INCONSISTENT`(중단).

**지표** (측정 4회 중앙값과 RUN range): NPU_ACTIVE, MAC_ACTIVE, MAC_DPU_ACTIVE, 활성 사이클당 유효 MAC
(884,736 / NPU_ACTIVE, 884,736 / MAC_ACTIVE), MAC_ACTIVE / NPU_ACTIVE, AO_ACTIVE, WD_ACTIVE, WD_STALLED (pass A),
SRAM/EXT 읽기·쓰기 beat (pass B), 출력 정합성, 기록된 region·포트 설정.

**규칙.**
- 실행 비용 (NPU_ACTIVE, 기존 Stage 4 허용폭과 pass 일관성): pass마다 tol = max(A 중앙값의 1 %, A range, B range);
  두 pass 모두 tol 밖이고 부호가 같으면 `B_LOWER` / `B_HIGHER`, 그 밖은 `UNRESOLVED`.
- 계산 활동: |ΔMAC_ACTIVE|, |ΔMAC_DPU_ACTIVE| (pass A) ≤ max(A range, B range) → `COMPUTE_SAME`, 아니면 `COMPUTE_CHANGED`.
- 보조 지표 (AO, WD, WD_STALLED, beat 7종): 같은 tol로 `CHANGED` / `NOT_RESOLVED`만, 원인 배정 없음.
- SRAM/EXT 전송량 변화를 실행 지연의 인과적 기여로 환산하지 않는다.

**최종 보고의 세 질문과 근거.**
1. MAC_ACTIVE와 유효 처리율이 유지되는가 → `compute` 판정 + 884,736 / MAC_ACTIVE (A·B).
2. NPU_ACTIVE가 얼마나 달라지는가 → `cost` 판정 + pass별 Δ, %, tol.
3. 계산부 활동 변화와 전체 비용 변화가 일치하는가 → `compute`와 `cost`를 나란히 (예: `COMPUTE_SAME` + `B_LOWER` = 계산
   활동은 같고 비용만 변함). NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다.

## 5. OFM 오염 검증의 범위 (owner 조건 4)

- 오염은 load 때 한 번(0x5A). 이를 직접 증명하는 것은 **load 뒤 첫 RUN**(set 1 rep 1)의 출력이 golden과 같다는 사실뿐이다
  — 오염된 OFM이 그 RUN에서 실제 출력으로 덮어써졌다.
- 이후 모든 측정 RUN: 출력 CRC가 첫 RUN·`output.bin`과 같고 펌웨어 비교(ofm_mismatch 0)가 일치함을 기록한다.
- pass B의 RUN별 SRAM wr beat(135)를 보조 증거로 쓴다.
- 모든 RUN에서 독립적으로 OFM이 덮어써졌다고 표현하지 않는다. 추가 오염·검증을 RUN이나 PMU 계측창에 넣지 않는다.

## 6. 종료 조건

A 재현(P0/P1) 실패, B SRAM 접근 오류(load NACK, fault, 응답 없음), 캐시 일관성 문제(오염된 첫 RUN 불일치), region 설정
불일치, 출력 불일치, NPU fault·timeout, PMU 카운터 이상(overflow, codes echo, arm/IRQ 횟수, job 결과) — 성능 비교를 중단하고
원인을 보고한다. 다른 주소·arena 크기·포트·메모리 모드·연산·채널로 바꿔 다시 하지 않는다. 측정 완료 또는 중단 뒤
m6 이미지로 복원하고 PING과 카드 분리를 확인한다.

## 7. 해석 금지

NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다; IFM 읽기와 OFM 쓰기의 몫을 나누지 않는다; Vela가 SRAM 전제로
골랐을 스케줄과 비교하지 않는다; 7개 모델로 일반화하지 않는다; 기존 이미지(`83398c7`)의 수치와 새 이미지의 B를 직접
비교하지 않는다(기존 이미지는 P1 재현에만).
