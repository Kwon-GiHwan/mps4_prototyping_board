# Stage 6B-E1-R Preflight (2026-11-16, before boot 428) — **PASS**

- 계약 `9daceaf`, 동결 `5094e74`, Phase 0 감사 `ab2e420`.
- 아래 항목은 모두 실제로 실행해서 확인했다.

| 항목 | 확인 | 결과 |
| --- | --- | --- |
| 이미지·Runner | staging digest가 `70090f1`(E1·6B-B와 같음)이다: boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…`. 판정 코드가 모든 RUN에서 provenance를 다시 대조한다 | PASS |
| TA profile 1 | 기준 capabilities는 E1과 같은 boot 375 사본이다(TA 레지스터 = `pmwl.TA_PROFILES[1]`, 6B-B Preflight에서 확인). boot-check가 boot마다 capabilities를 대조한다 | PASS |
| 컴파일러 digest | 컨테이너 Vela 5.0.0, 설치 파일 287개 묶음 digest `78d4c31d…`가 동결 기록(`facts/compiler.json`)과 같다 | PASS |
| 재컴파일 | 선정 6개를 컨테이너에서 다시 빌드했다. 다음이 6/6 동결값과 같다: tflite, IFM, reference, Vela 출력, command stream, DRWL, golden, debug 행, 커널 레지스터 | PASS |
| 같은 산출물(Mac = 보드) | staging 48개 파일 중 Mac에 원본이 있는 44개는 sha256이 같다. 나머지 4개는 위 이미지 파일이다. AppleDouble 0개. DRWL 7개 = manifest = predictions | PASS |
| 메모리·정체성 | 7개 모두 n_base 5, placement 0이다. 신규 6개는 Dram→Dram이다. fast_size 13,024–42,592, arena 248,944–514,752로 6B 한도 안이다 | PASS |
| PMU·pass | `ids.txt`, `conditions.txt`가 E1과 같다(Stage 4K pass A·B, `wfe 0 0 off 1,2`) | PASS |
| 입력·출력 reference | 신규 6개의 golden은 TFLite reference 커널 출력이다(`golden_sha256` = `ref_sha256`, 최적화 커널과 차이 0, 길이 H·W·Cout). 기준은 Stage 4K tflite_ofm이다 | PASS |
| 예측 동결 | `workloads/predictions.json`(H1-UC 정수 예측 + 경쟁 가설 8 + DPU 3)과 `results/fi101_stage6b/stage6be1r/predictions.md`가 `5094e74`에 있다 | PASS |
| 판정 코드 | 보드 `~/evsweep`의 `stage6bb.py`와 의존 모듈 11개 sha256이 Mac과 같다. `sync.sh check`에서 보드 쪽 불일치는 0이다 | PASS |
| 보드 dry run | (a) boot 375 자료 + manifest 사본(boot 375): `repro-gate` PASS. (b) 실제 manifest(boot 428): FAIL(`boot index`). (c) 측정 전 `boot-check`: UNMEASURED, rc 1 | PASS |
| boot 번호 | 보드 원시 자료의 `host_boot_index` 최대값은 427이다. 428–434는 쓰인 적이 없다. `evsweep_s6be1r_run`, `evidence_s6be1r`은 없다 | PASS |
| 복구 | `evidence_m6`이 있다. 세션은 restore_mlek → postflight 순서다. 카드는 마운트되어 있지 않다 | PASS |
| 세션 | `~/evsweep_s6be1r/session.txt`(sha256 `1f41712c…`) = Mac이다. `sudo_session.sh --check` 결과 `SESSION OK`. 구조는 E1 세션과 같고, 형상 이름·boot·경로만 다르다 | PASS |
| 테스트 | `sh test.sh` ALL PASS. E1-R mutation 31/31 KILLED. 공유하는 E1 판정 코드의 mutation도 다시 돌려 25/25 KILLED | PASS |

## 참고 (판정에 영향 없음)

- `sync.sh check`는 컨테이너 쪽에서 불일치 22개를 보고했다.
  - 위치는 `/work/mps4_host`(stage4–6 컨테이너 스크립트)와 `/work/selftest`(driver_runner 소스)다.
  - E1-R은 두 경로를 쓰지 않는다. 컴파일은 `/work/s6b_host`에서 했고, 그곳 스크립트 sha256 = Mac을 직접 확인했다. 보드 이미지는 이미 빌드된 `70090f1`이고 digest로 확인했다.
  - 컨테이너 사본은 고치지 않았다.
- 컨테이너로 처음 복사할 때 macOS tar가 AppleDouble 파일 2개(`._stage6be1r_models.py`, `._stage6be1_models.py`)를 만들었다. 컴파일 전에 지웠다. 이후 복사는 `COPYFILE_DISABLE=1`로 했다.
