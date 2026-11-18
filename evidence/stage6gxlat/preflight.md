# Stage 6G-X_LAT Preflight (2026-11-18, before boot 505) — **PASS**

동결 커밋 `d69168e`. 아래 항목은 모두 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 이미지 | 컨테이너에서 `f0baf8c` 소스(git archive)를 `build_driver_runner.sh`로 빌드했다. L500 재빌드는 X3와 같다(boot `3b4af743`, bram `9b1844a3`, images.txt `af688281`). L250 bram `4f5f54aa`, L1000 bram `7004c530`이다. 전수 바이트 비교 결과 bram 2바이트(0-based 638124–638125: `F4 01` → `FA 00` / `E8 03`)만 다르고, boot.bin·images.txt는 같다 | PASS |
| 2 | 보드 staging | `~/evsweep_xl250_img`·`~/evsweep_xl1000_img`: boot·bram·ddr(16 B 0, `374708ff`)·images.txt 해시가 동결값과 같다 | PASS |
| 3 | 워크로드 | DRWL 10개 + manifest sha256: Mac(`evidence/stage6ex3/workloads`) = 두 staging. 두 staging끼리도 같다 | PASS |
| 4 | TA 기준 | `~/evsweep_x3_ref/caps_14077be.json` = Mac 사본(`caps_14077be.json`). 기대 caps = 같고 `ta_ext_rlatency`만 L | PASS |
| 5 | 판정 코드 | 보드 `stage6gxlat.py`·`stage6ex3.py`·`drwl.py`·`record_v2.py` sha256 = Mac | PASS |
| 6 | Vela | L500 per-layer = X3. ad L250/L1000, kws L250 명령 스트림 = 측정 스트림. kws L1000은 비교 불가(계약 §4) | PASS |
| 7 | 테스트 | `test.sh` ALL PASS, `test_stage6gxlat` 22, mutation 51/51 KILLED | PASS |
| 8 | dry run | 보드: 측정 전 boot-check UNMEASURED(rc 1). X3 L500 run root를 L250 identity로 검사하면 CONFIG_MISMATCH(image bram, boot index, TA registers, TA EXT RLATENCY). Mac: X3 L500 boot는 X3 identity로 VALID | PASS |
| 9 | 보드 상태 | 최대 host_boot_index 504(505–516 미사용), 카드 마운트 0, /dev/sdb1 없음, `evidence_m6` 있음, xl 경로는 새로 만듦, 디스크 여유 2.3 GB | PASS |
| 10 | 세션 | `session.txt` sha256 `80805c7a…` = Mac. `sudo_session.sh --check` SESSION OK. deploy 7회, 매 deploy 전 USB_ON(E2B 방식), boot 12개, 매 boot 후 boot-check, 마지막 restore 후 postflight | PASS |
