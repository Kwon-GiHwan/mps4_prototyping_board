# A7 — 입력 텐서 생성 방식·seed (REPORT 부록 B 미해소 항목)

**2026-09-14.** 부록 B의 `입력 tensor 생성 방식·seed: NOT_COLLECTED (해소 조건: 서버 runner 소스)`를
서버 read-only 확인으로 해소한다. 계약: 계획서 §3. 결과 집합
`DETERMINISTIC_DEFAULT_SEED / SEEDED_FROM_X / DYNAMIC_IFM / NOT_ESTABLISHED`.

## 결과: `DETERMINISTIC_DEFAULT_SEED`

## 근거 (세 가지, 서로 독립)

1. **러너 소스** — MLEK `b2c0bb2`,
   `source/app/use_case/inference_runner/src/UseCaseHandler.cc:37-61`:
   `DYNAMIC_IFM_BASE`가 정의되지 않으면 입력 텐서를 `std::rand() & 0xFF`로 채운다.
   MLEK `source/` 전체에 `srand` 호출이 없다 (grep 0건). libc의 `rand()`는 seed를 주지
   않으면 seed 1로 시작하므로, 같은 바이너리는 부팅마다 같은 바이트열을 만든다.
2. **캠페인 빌드 인자** — 캠페인·R1 재측정을 빌드한 하니스 `/tmp/xqbin/stage1.py:80-85`의
   cmake 명령에는 `DYNAMIC_IFM_BASE`가 없다. mps3/mps4 플랫폼 CMakeLists가 이 변수를
   CACHE STRING으로 정의하지만, `usecase.cmake:61`의 컴파일 정의 주입은 `if (DEFINED …)`
   평가 시점에 따라 달라지므로 소스만으로는 확정하지 못한다. 그래서 3번으로 확인했다.
3. **UART 증거** — 보존된 R1 UART 71개(`remeasure/uart/*.uart.txt`) 어디에도
   `DYNAMIC_IFM_BASE` 경로가 INFO 레벨로 찍는
   `"input tensor/s populated with … data read from 0x…"` 줄이 없다. 같은 로그에 다른
   INFO 줄(모델 텐서 정보, PMU 결과)은 전부 있으므로 로그 레벨 문제가 아니다. 따라서
   실행 바이너리는 `std::rand` 경로였다.

주의: `/tmp/closure4/*/CMakeCache.txt`(2026-08-24, closure 검증 빌드)에는
`DYNAMIC_IFM_BASE=0x92000000`이 캐시돼 있다. 이는 플랫폼 CMakeLists의 기본 정의가
캐시에 남은 것이며, 3번 증거가 보여 주듯 컴파일 정의로는 주입되지 않았다.
캠페인 빌드 루트 `/tmp/xq`는 서버에 남아 있지 않아 캐시를 직접 보지는 못했다.

## 의미

- M1=M2=M3(3회 반복 완전 일치) 74/74는 이 결정론의 결과이지 계측 일관성의 증거가 아니다
  (REPORT I4와 같은 종류의 주의).
- 입력값이 사이클에 미치는 영향은 이 실험에서 통제된 것이 아니라 고정된 것이다.
  Ethos-U는 입력값에 따라 연산을 건너뛰지 않으므로 사이클은 입력값에 둔감할 것으로
  기대되지만, 그것을 시험하지는 않았다(`NOT_ESTABLISHED`).
- 재현 조건에 "입력 = `std::rand()` seed 1 바이트열"을 추가해야 한다.
