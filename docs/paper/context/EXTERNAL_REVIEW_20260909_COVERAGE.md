# 외부 리뷰 — workload/architecture coverage 누락 감사 (2026-09-09)

**원문 보존.** 검증 결과는 별도 문서.

핵심 주장: "8 models × 3 architectures"로 읽히지만 실제로는 subsection마다
`8 → 7 → 6 → 4 → 3 → 2 → 1 models`로 줄어든다.

## 빨간색 — 반드시 원 데이터에서 확인
1. ASR가 U65/U85에서 왜 통째로 빠졌는가 (IC는 `fvp_failed` 명시, ASR은 이유 없음)
2. §4.1 64 data points의 정확한 4개 모델이 누구인가 (본문에 이름 없음)
3. "4 U65 models" CPU fallback 검증 대상이 누구인가
4. Table 16의 DNN/OD per-op 분석을 재현하는 설정/원자료 위치
   (Appendix Table 26은 NR, VWW × U85-256/512만 커버 → reproduction mismatch)
5. U65/U85 삭제된 raw log 대신 현재 남은 evidence

## 노란색 — subset은 명시됐으나 claim scope 조절 필요
- direct stall counter: NR/KWS/AD 3개만 (VWW/IC/OD/DNN/ASR 직접 증거 없음)
- cross-generation traffic reproduction: NR/KWS 2개, U85 없음
  → "generational reproducibility" 표현이 강함
- chunk-boundary validation: NR/KWS/AD 3개만
- determinism cross-run: DNN@U55-256×5, KWS@U65-256×3 뿐
  determinism intra-run: AD 중심 + VWW 1 config
- output correctness: AD(4 configs×5) + VWW(1 config×5) 뿐
- CPU fallback: 64 configs + "4 U65 models" (이름 불명), U85 audit 없음
- memory-config robustness (4 configs 재현): NR 하나뿐
  (같은 boundary reversal 모델은 NR/DNN/VWW/OD 4개)
- Shared_Sram per-op: AD/VWW × U55-256만
- DWConv mechanism: VWW(17 DWConv) vs KWS(5) contrast, controlled isolation 아님
- small feature-map: AD/KWS/OD 중심
- low-compute/cycle floor: NR(87K)/DNN(79K) 2개
- IRQ perturbation validation: 7 models(ASR 없음),
  configs U55-128/U55-256/U65-256 — **U85 validation 없음**, 21 중 20 성공
  (VWW@U55-128 FVP timeout)
- §4.2.2 U85 transition prediction 6 models → per-op reversal decomposition 4개
  (KWS/AD는 monotonic이라 제외)

## 회색 — 실패 사유 명확
- IC U65/U85: `fvp_failed`
- VWW@U55-128 profiling: timeout
- ASR U55: default timeout 초과 → 900s로 재측정

## §4.1 관련 핵심 지적
headline은 "Vela prediction accuracy"로 일반적이나 핵심 수치
(MAPE 22.5%, Spearman 0.950, pairwise 99%, optimal config 93.8%)는 전부
**64 data points = 4 models × 4 MAC × 2 memory modes × 2 system configs**에서 나옴.
4 MAC = 32/64/128/256 이므로 사실상 U55 기반. 그 4개 모델 이름이 본문에 없음
→ 단순 측정 누락이 아니라 **dataset definition 누락**.

## 기타
- §3.1: DNN-S의 Vela summary 일부 없음 (명시됨)
- Appendix: original U65/U85 FVP execution logs deleted (명시됨)
  → U55 대비 U65/U85 raw-evidence quality 낮음
