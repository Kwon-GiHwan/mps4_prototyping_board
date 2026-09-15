# H3-R 실행 에이전트 지시서 (Orca 워커용)

당신은 이 저장소에서 **H3-R 보강 실험**을 끝까지 수행하는 에이전트다. 매니저 GO 전문은
`docs/superpowers/plans/2026-09-15-h3r-verification-GO.md`이고, 그 문서가 최상위 규칙이다. 이 지시서는 GO를 실행하기
위해 필요한 저장소·서버 사실과 순서를 적은 것이다. GO와 이 지시서가 충돌하면 GO를 따른다.

프로젝트 규칙: 저장소 루트 `CLAUDE.md`(게이트는 돌연변이 검사, 규칙 id, tri-state, 사전 등록, 보고 시 검증 수준 명시)와
`docs/paper/raw_data_report/amendments/h13/` 의 기존 방식을 그대로 따른다. 기존 evidence·frozen 파일·H13 결과는 수정하지 않는다.

## 0. 먼저 읽을 것 (순서대로)

1. `docs/superpowers/plans/2026-09-15-h3r-verification-GO.md` — 전문.
2. `docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md` — H13 계획서. §0 게이트, §7 H3 판정식, A1(검증 빌드 패치), A5/A7(TOTAL 격자, EXT_PULSE_OFF=0 금지), A6(FetchContent 캐시).
3. `docs/paper/raw_data_report/amendments/h13/H13_RESULTS.md` §6, §6b′, §6c — 기존 H3 결과와 통제 한계.
4. 코드: `h13/h13_sweep.py`(서버 하니스), `h13/h13_analyze.py`(판정기, H3 부분), `h13/gen_h3_models.py`(기존 모델 생성 — 재사용 금지, 참고만),
   `h13/gen_h2b_model.py`(flatbuffer 절단 방식 — **이 방식을 형상 파생에 쓴다**), `h13/h3_blocks.py`, `h13/make_handoff.py`.
5. 데이터: `h13/h3_manifest.json`, `h13/h3_synthetic_cells.json`, `h13/results.jsonl`(기존 H3 base/relaxed 값), `h13/ta_parameters.csv`.

## 1. 환경 사실

- 빌드·FVP 실행은 원격 컨테이너에서만 가능하다: `ssh gihwan` → `docker exec benchmark-runner sh -lc "..."`. Mac에는 툴체인이 없다.
  (`gihwan-local`/`gihwan-web`는 다른 기계다. 쓰지 않는다.)
- 서버 작업 디렉터리: `/tmp/h13/` (하니스 `h13_sweep.py`, `ta_parameters.csv`, `synthetic_cells.json`, `models/`, `fc_cache/`, `orig/`, `verify_patch.py`).
  H3-R은 **새 디렉터리 `/tmp/h3r/`**를 만들어 쓴다(하니스 복사본에서 `OUT="/tmp/h3r"`). `/tmp/h13/`의 파일은 읽기만 한다.
- 디스크 여유 약 2.8 GB. 하니스는 arm마다 워크스페이스를 지운다. `stage1.FREE_GATE`(1 GB) 게이트가 있다.
- 기존 H3의 기준 INT8 모델(6×6 등 51개)은 서버 `/tmp/h13/models/h3_*.tflite`에 있다(로컬 저장소에는 없음). `docker cp`로 가져온다.
  기준 모델 SHA는 `h13/h3_manifest.json`의 `sha256`과 일치해야 한다.
- 로컬 Python: `/usr/bin/python3`(3.9, numpy 없음). TensorFlow는 `~/.local/bin/python3.12 -m venv <dir> && pip install tensorflow`로 venv를 만들어 쓴다
  (`tensorflow.lite.tools.flatbuffer_utils`로 flatbuffer 읽기/쓰기, `tf.lite.Interpreter`로 실행 확인). 컨테이너에는 TF가 없고 `tflite`/`flatbuffers`/vela 5.0.0가 있다.
- 검증(출력 덤프) 빌드: MLEK stock의 `VERIFY_TEST_OUTPUT`가 컴파일되지 않아 가드 안쪽만 고친 3파일 패치를 쓴다. 현재 서버 소스는 **원본으로 복원돼 있다**.
  H3-R 실행 전에 `docker exec benchmark-runner sh -lc "cd /tmp/h13 && python3 verify_patch.py"`로 다시 적용하고(원본은 `/tmp/h13/orig/`),
  **종료 후 `/tmp/h13/orig/`의 세 파일로 복원하고 `ORIGINAL.sha256`(저장소 `h13/verify_build/orig/`)와 다이제스트를 대조**한다.
  stock 빌드는 이 패치의 영향을 받지 않는다(가드 밖 코드 불변; 기존 캠페인에서 stock AXF = 동결 AXF로 확인).
- 하니스는 모든 빌드에 TA 16값을 `-D`로 넘기고 generated header를 판독한다. `EXT_MAXR`/`EXT_MAXW`의 **적용값**은 드라이버 마스크(`& 0x3F`)를 거친다:
  64 → 0(무제한). 근거: `h13/verify_build/`와 `H13_RESULTS.md` §2, 드라이버 발췌는 `H13_HANDOFF/evidence/timing_adapter_driver_excerpt.txt`(ZIP은 `~/Downloads/H13_HANDOFF.zip`).
  H3-R의 "설정 게이트"는 요청값·헤더값·적용값(마스크 적용) 세 열을 모두 기록하고 equalized에서 두 MAC의 적용값 16개가 전부 같아야 통과.
- 긴 실행은 `nohup ... &`로 컨테이너 안에서 띄우고 로그를 폴링한다(Bash 백그라운드 10분 제한 주의). 로그는 `/tmp/h3r/run_*.log`.
- GitHub archive 다운로드가 간헐적으로 504를 낸다 → 하니스의 `FETCHCONTENT_BASE_DIR=/tmp/h13/fc_cache` 설정을 그대로 쓴다(이미 채워짐). H3-R 하니스 사본에서도 같은 캐시를 가리키게 한다.
- `EXT_PULSE_OFF=0`은 FVP가 완주하지 못한다. 쓰지 않는다. pulse는 프로파일 값(4000/1000) 유지.
- 기존 H3 relaxed의 정확한 정의(bridge_legacy_relaxed에 그대로 재사용): `h13/gen_h3_models.py`의 `RELAXED = {"EXT_RLATENCY": 0, "EXT_WLATENCY": 0, "EXT_BWCAP": 0, "SRAM_RLATENCY": 0, "SRAM_WLATENCY": 0}`
  위에 MAC별 프로파일 기본값(256: low, 512: mid; `h13/ta_parameters.csv`)이 덮인 16값. `h13/results.jsonl`의 해당 arm `defines`가 최종 근거다.
- 발표 자료: 최신 덱은 `~/Downloads/Corstone_Family_v9.pptx`(36장). 빌드 스크립트 `docs/presentation/build/make_cf_v9.py` + `v8_helpers.py`.
  입력은 유저의 `~/Downloads/Corstone_Family_v5.pptx`를 `user_v5.pptx`로 복사해 쓴다. LibreOffice(`soffice --headless --convert-to pdf`)와 `pdftoppm`으로 렌더 확인.
  H3-R 반영본은 `make_cf_v10.py` → `~/Downloads/Corstone_Family_v10.pptx`로 만들고 v9는 보존한다. 형상·DW·ublock 관련 페이지(v9 기준 20장 4·5·7행, 22장, 25장, 26·27·28장, 부록)에 H3-R을 **기존 H3와 구분해 병기**한다.
- 매니저(ChatGPT 창) 브리지 `docs/paper/raw_data_report/amendments/manager_bridge.py`는 탭이 닫혀 있을 수 있다. 질문이 필요하면 유저에게 보고하고 진행 가능한 부분은 계속한다.

## 2. 수행 순서 (GO §0)

1. **계획·판정 커밋**: 계획서 `2026-09-14-h1-h3-verification-plan.md` 끝에 **A8** 절을 추가한다 — 목적, 조건표(base/equalized/bridge_legacy_relaxed의 16값 전부), 게이트(G1, G1′, 설정, 반복, 실행, 출력, 보존), 판정식(§7 그대로, TOTAL·ACTIVE 병렬, METRIC_DEPENDENT), Q1–Q5 비교 계획, 승인 범위, 기준 커밋·도구 버전. 판정기 `h3r/h3r_analyze.py`(+unittest, 규칙 id, 돌연변이 검사 RED 확인)를 함께 커밋한다. **측정값이 생기기 전에 커밋.**
2. **모델 생성** `h3r/gen_h3r_models.py`: 연산 종류별 기준 = 기존 6×6 INT8 모델(`h3_conv1x1_6x6_c128`, `h3_conv3x3_6x6_c128`, `h3_dw3x3_6x6_c128`). `flatbuffer_utils.read_model`로 읽어 IFM/OFM 텐서의 `shape`(및 `shapeSignature`)만 9형상으로 바꿔 저장. 가중치·bias 버퍼, 양자화 레코드, 연산자 옵션은 손대지 않는다. 재calibration 금지.
3. **G1′ 검증** `h3r/check_g1prime.py`: 기준 vs 파생 27모델을 필드 단위 비교 — 최종 INT8 가중치 버퍼 SHA, bias 버퍼 SHA, 입력/출력/가중치/bias 양자화(scale·zero_point·quantized_dimension), opcode·version, builtin options(stride/dilation/padding/activation), 채널 수. 허용 차이는 IFM/OFM shape·shape_signature·오프셋뿐. 결과를 `h3r/model_manifest.csv`(+G1′ 결과 열)로 남긴다.
4. **기능 확인**: TF 인터프리터로 27모델 로드·실행·출력 크기 확인. 연산 종류별 공통 입력 벡터(고정 seed 4608바이트)를 각 H×W로 reshape해 사용, 입력 바이트 SHA 기록. NPU 출력 동일성은 서버의 검증 빌드로 따로 검사한다(같은 모델의 MAC·TA arm 간 출력 동일).
5. **셀 정의** `h3r/h3r_cells.json`: 27모델 × MAC{256,512} × arms — `base`(프로파일 기본, 오버라이드 없음), `equalized`(GO §3.1: EXT R/W 지연 0, EXT_BWCAP 0, SRAM R/W 지연 0, EXT_MAXR 0, EXT_MAXW 0; 나머지 값도 두 MAC에 동일하게 명시 — SRAM_MAXR/MAXW/MAXRW, SRAM_PULSE, SRAM_BWCAP, EXT_MAXRW, EXT_PULSE 4000/1000. 256 low와 512 mid는 SRAM_RLATENCY(16 vs 32)·SRAM_BWCAP은 같음·MAXR/MAXW 등이 다르므로 **16값을 전부 명시**해 동일하게 만든다), DW 9모델에만 `bridge_legacy_relaxed`(기존 relaxed 정의 그대로 = MAC별 프로파일 위에 RELAXED 5값만 덮음). Vela system_config는 기존과 동일(256 Low, 512 Mid_512). 총 126 arm. `verbose: true`로 `--verbose-schedule --verbose-performance` 덤프를 남긴다.
6. **서버 배치**: `/tmp/h3r/` 생성, 하니스 사본(`h3r_sweep.py`: `OUT="/tmp/h3r"`, `SYNTH="/tmp/h3r/cells.json"`, 캐시 경로는 `/tmp/h13/fc_cache` 유지), 모델 업로드(`docker cp`), `ta_parameters.csv` 복사, 검증 빌드 패치 적용.
7. **첫 셀 qualification**: 대표 셀(예: `h3r_conv1x1_6x6` 256 base)을 3회 + 검증 빌드로 먼저 실행해 게이트(반복 동일·헤더=요청·출력 덤프 존재·Vela 산출물 SHA)를 확인한 뒤 전체 실행. 기존 H3의 같은 조건(`h3_conv1x1_6x6_c128` 256 base, TOTAL 6,068)과 값이 같은지 **anchor 비교**로 기록한다(같아야 한다는 게이트는 아님 — 모델 바이트가 다를 수 있으므로 관측으로 기록).
8. **전체 실행**: 126 arm(378 stock 실행 + 검증 빌드). nohup + 로그 폴링. 실패는 원인·재시도 횟수 기록.
9. **회수·분석**: `h3r/collect.sh`로 `/tmp/h3r` 증거 회수 → `h3r_analyze.py`(TOTAL·ACTIVE 병렬 판정, METRIC_DEPENDENT 표시) → 표: `runs_all.csv`, `h3r_models_conditions_metrics.csv`(요청/적용 TA 16값 포함), `h3r_judgements_total_vs_active.csv`, `h3_vs_h3r_base.csv`(Q1), `base_vs_equalized.csv`(Q2), `dw_bridge_vs_equalized.csv`(Q3), block/traffic 표(Q5, `h3_blocks.py` 방식 재사용), 그래프 스크립트.
10. **보고서** `docs/paper/raw_data_report/amendments/h3r/H3R_RESULTS.md` — GO §10 순서(1 원래 통제 문제 → 6 유지·강화·수정·철회). 게이트 결과·arm/반복 수·실패/재시도 포함. "두 통제 문제를 제거한 뒤 무엇이 남고 무엇이 사라졌는가"에 답한다.
11. **발표 반영**: `make_cf_v10.py` → v10. 기존 H3와 H3-R 구분 병기. 렌더로 줄바꿈 확인. `~/Downloads/`에 pptx·pdf 저장.
12. **정리**: 검증 빌드 3파일 복원 + 다이제스트 확인, `h13/README.md`·amendments `README.md`에 h3r 인덱스 줄 추가, Obsidian `~/Documents/Obsidian Vault/npu_benchmark/project-context.md`에 H3-R 결과 요약 기록. 결과 반영 커밋(계획 커밋과 분리).

## 3. 하지 않는 것

- 기존 `h13/`, `x4/`, frozen evidence, `H13_RESULTS.md` 본문 수정(참조만). H3-R은 `amendments/h3r/`에 별도 저장.
- 재calibration, 양자화 재생성, 면적 64/256, MAC 1024/2048, S4 stall 계측, `EXT_PULSE_OFF=0`, 결과를 본 뒤 임계값 변경.
- `inference_runner` 코드 패치(검증 빌드의 기존 가드-안 패치 재적용만 허용).
- 매니저 GO 범위 밖 실험.

## 4. 보고 형식

마지막 보고에 반드시: 검증 수준(구문/단위/통합/E2E), 실제 실행한 것, 실행하지 않은 것, 게이트 통과/실패 수, arm·반복 수, 실패·재시도, 커밋 해시(계획 커밋·결과 커밋), 산출물 경로(보고서·CSV·덱), 그리고 Q1–Q5 각각에 대한 한 문단 답.
