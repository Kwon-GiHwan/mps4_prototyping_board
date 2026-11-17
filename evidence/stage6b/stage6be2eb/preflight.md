# Stage 6B-E2E-B Preflight (2026-11-17, before boot 458) — **PASS**

동결 `c7ddffe`(공유 identity 정정 `6614ce8`, 임시 디렉터리 정리 `338507d`). 모든 항목을 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 공유 identity 정정·회귀 | `6614ce8` 회귀 REGRESSION_PASS(판정 9개 출력 바이트 동일, 폴더 76개 중 예상 밖 차이 0). E2E-B 판정은 `stage6bb.identity_of`를 직접 쓴다. B3 픽스처에서 manifest placement를 0으로 바꾸면 공유 경로가 거부하고, 공유 모듈 mutation 2개가 E2E-B 테스트로 KILLED | PASS |
| 2 | boot 번호 | 보드 원시 자료 전체의 최대 host_boot_index는 457이다. 458–462는 쓰인 적이 없다 | PASS |
| 3 | 이미지 | `~/evsweep_s6be2eb_l500`·`_l1000`의 boot/bram/ddr/images.txt sha256이 manifest와 같다(L500 = `70090f1`, bram `c80e77df…`; L1000 bram `fd478e2d…`). E2D Amendment A staging에서 복사했다 | PASS (8/8) |
| 4 | DRWL | 두 staging의 `s4c2_conv_cin48`·`e2d_w1p1`·`e2eb_b3` sha256 = manifest(`6eb390be…`, `928296b1…`, `7b2cedd5…`) | PASS (6/6) |
| 5 | B0/B3 실행 구성 | 두 DRWL은 길이 304,080 B로 같고 offset 28(word 7) 한 바이트만 다르다. 동반 파일(cms, tflite_ofm, ifm, ref_ofm)도 바이트 동일, golden `b9341e6f…` | PASS |
| 6 | SRAM 배치 | B3 arena 기대값 `0x31076770`, 2 MiB 끝 `0x31276770` < `0x31400000`. fast memory `0x31000000–0x31060000`, 중간 텐서 `0x31000000–0x31024000`과 겹치지 않는다. 가중치·command stream은 DDR 모델 안에 있다. 판정에서 RUN마다 layout 6항목을 검사한다. B0 실데이터(boot 453)와 W0-P1 실데이터(boot 451, SRAM)에서 layout ok | PASS |
| 7 | IO staging·cache | RUN마다 측정창 전에 입력을 다시 복사한다(`runner.c run()`). load 때 arena 패턴·보수 되읽기와 출력 poison을 한다. 두 이미지 ELF에 MLEK `ethosu_flush_dcache`/`ethosu_invalidate_dcache`가 있다(`arm-none-eabi-nm`, `/work/driver_s4p_img`, `/work/s6be2b_img_l1000b`; image digest = staging). NPU_ACTIVE에는 CPU staging이 들어가지 않는다 | PASS |
| 8 | 판정 코드 | 보드 `~/evsweep/host/{analysis,lib}/*.py` 68개 sha256 = Mac(`stage6be2eb.py` `42a25b36…`). `sync.sh board`는 analysis를 보내지 않아 tar로 같은 경로에 복사했다. workloads 18개 = Mac(manifest `9fd8bed0…`) | PASS |
| 9 | 측정 전 상태 | 보드 boot-check B3-L500 = UNMEASURED, rc 1(세션이 멈추는 값) | PASS |
| 10 | 보드 dry run | 보드에서 boot 번호만 바꾼 임시 manifest로 E2D Amendment A 자료를 판정했다: repro-gate(boot 449 대 375) PASS, B0-L500(453)·B0-L1000(454) VALID | PASS |
| 11 | PMU·순서 | ids/conditions = E2D(pass A·B, WAIT_WFE). plan 5개 = 계약 순서(458 REF, 459 B0, 460 B3 L500; 461 B3, 462 B0 L1000) | PASS |
| 12 | 세션·복원 | `session.txt` `bdfbd590…` = Mac = 두 staging. `sudo_session.sh --check` OK(Mac·보드). 카드 마운트 0, `evidence_m6` 있음, run root·evidence root 없음. 보드 디스크 여유 2.5 GB(세션당 수 MB) | PASS |
| 13 | 테스트 | `test.sh` ALL PASS. E2E-B 43개, mutation 51/51. 유지보수 23개, mutation 21/21 | PASS |

## 기록할 사건 (판정 영향 없음)

- 첫 E2E-B mutation 실행 중 Mac 디스크가 찼다(ENOSPC). 원인은 테스트가 매번 원시 자료 사본을 임시 디렉터리에 만들고 지우지 않은 것이다.
- 이 단계의 테스트 픽스처로 식별되는 임시 디렉터리 3.6 GB만 지웠다. 다른 임시 파일은 두었다.
- 복원 쓰기가 실패해 `stage6bb.py`에 mutation 하나가 남았다. `git checkout`으로 `6614ce8` 내용으로 되돌리고 HEAD와 같음을 확인했다.
- `stage6be2eb.py`에는 남은 mutation이 없음을 확인했다(모든 mutation 원문 패턴이 정확히 1회).
- 테스트와 `regression.py`가 임시 디렉터리를 지우도록 고쳤다(`338507d`). 그 뒤 두 mutation 하네스를 다시 실행했다.
