# Stage 6B 근거 (보드 RUN 없음)

| 파일 | 내용 |
|---|---|
| `rules.md` | 그룹화·정적 재현·선정 규칙 (커밋 `b9f3824`, 후보 컴파일 전) |
| `candidates.json` | `stage6b.py candidates` 출력: 57개 그룹 중 모델별 상위 5개 → 26개 후보, 대표 연산 |
| `compiled/*.s6b.json`, `*.drwl.json` | 컨테이너 `stage6b_models.py` 출력: 형태별 Conv 행 (Stage 4 인벤토리 형식), 실행 가능 검사, 반복 컴파일 sha256, opt vs ref |
| `compile.log` | 같은 실행의 한 줄 요약 (컨테이너 `/work/s6b_compile`) |
| `workloads/` | 선정 구성 `s6b_g14_f_ctx` (tflite, DRWL, IFM, BUILTIN_REF golden), A1 `expected_identity.json` (G14 n_base 7, 기준 `s4c2_conv_cin48` n_base 5) |
| `post_hoc/` | **POST_HOC_DESCRIPTIVE**: 뒤쪽 연산 프로브 (`probe_post.*`: G25 G12 G09, add_self / abs / add_add), 26개 F_CTX_SELF (`probe_self.*`). 판정·선정에 쓰지 않음 |
| `contract_draft.md` | 보드 측정 계약 초안 (동결하지 않음) |
| `mutate.py`, `mutation.txt` | 규칙 mutation 18/18 KILLED |

- 원본 모델: 컨테이너의 MLEK `resources_downloaded/<usecase>/<model>.tflite`. 각 기록에 원본 sha256이 있다.
- 기준 재현 DRWL `s4c2_conv_cin48`: `evidence/stage4k/workloads`에 있다. sha256 `6eb390be…`이 4K boot 375 원시 데이터와 같다.
- 컨테이너 사본 경로: `/work/s6b_host` (host, config, docs/reference). 컴파일 결과는 `/work/s6b_compile`에 있다.
