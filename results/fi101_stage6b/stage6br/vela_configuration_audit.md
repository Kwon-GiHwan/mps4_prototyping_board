# Vela 설정과 보드 조건 대조 (Phase 2, 지시 3.2)

## 출처

- **Vela:** 컨테이너 `benchmark-runner`의 `vela --version` = **5.0.0**, `pack_vela_workload.VELA_OPTIONS`, `/opt/arm/ml-embedded-evaluation-kit/scripts/vela/default_vela.ini`.
- **보드:** 6B-B boot 410–420의 `capabilities.json`이다. 펌웨어가 boot 때 읽은 값이고, 11개 boot 모두 같다. 해석에 쓴 자료는 다음과 같다.
  - `host/lib/pmwl.py` TA_PROFILES[1]
  - core driver의 `ethosu85_interface.h`(AXI_SRAM/AXI_EXT 필드)
  - `evidence/runner_gap/open_equivalence_items.md` E2

## Vela resolved 설정과 보드 대응

| 항목 | Vela | 보드 (FI101, TA profile 1) | 대조 |
| --- | --- | --- | --- |
| Vela version | 5.0.0 | — | 기록 |
| Accelerator | ethos-u85-1024 | NPU CONFIG macs 필드 10 (1024) | MATCH |
| System config | Ethos_U85_SYS_DRAM_Mid_1024 | MLEK `ta_config_u85_sys_dram_mid` 에뮬레이션 | 의도상 대응, 아래 항목별 |
| Memory mode | Dedicated_Sram: const·arena = Axi1, cache = Axi0 | A2 n_base 6, REGIONCFG 0x55F. region 0·1(가중치, arena) = 값 3, region 2 이상(fast scratch) = 값 1. 정의는 `stage4aoe` 상수 | 논리 대응 MATCH(정적). 물리 경로는 아래 참고 |
| Optimise | Performance | — | 기록 |
| SRAM 작업공간 | arena_cache_size 393,216 B | capabilities `fast_size` 393,216 | MATCH |
| core_clock | 1 GHz | NPU 클럭은 FPGA 값을 모름. 보드 수치는 NPU 사이클 단위 | 단위(NPU cycles)는 같음. 절대 클럭은 UNKNOWN(사이클 비교에는 영향 없음) |
| axi0_port / axi1_port | Sram / Dram | SRAM 포트(TA_SRAM 0x51102000) / EXT 포트(TA_EXT 0x51102400) | 논리 MATCH |
| Sram_clock_scale | 1.0 | TA_SRAM pulse_on 3999, pulse_off 1, bwcap 4000 | **UNKNOWN**. TA 대역폭 레지스터의 단위·의미를 확인하지 못함 |
| Sram read / write latency | 32 / 32 | TA_SRAM rlatency 32, wlatency 32 | MATCH(값). TA 지연의 클럭 기준은 UNKNOWN |
| Sram max reads / writes | 8 / 8 | TA_SRAM maxr 8, maxw 8. NPU AXI_SRAM outstanding 12 / 16 | MATCH(TA 값). 실제 제한은 min(TA, AXI)일 것으로 추정(미검증) |
| Sram burst length | 64 B | AXI_SRAM max_beats 필드 2 | **UNKNOWN**(필드 값과 바이트 길이의 대응을 확인하지 못함) |
| Sram ports used | 2 | U85 SRAM 포트 수는 TRM 확인 필요 | **UNKNOWN** |
| Dram_clock_scale | 0.75 | TA_EXT pulse_on 4000, pulse_off 1000, bwcap 3750 | **UNKNOWN**. 4000/(4000+1000)=0.8, 3750/4000≈0.94처럼 계산은 되지만 의미를 확인하지 못했다. 0.75와 같은지 판단할 수 없음 |
| Dram read / write latency | 500 / 250 | TA_EXT rlatency 500, wlatency 250 | MATCH(값). 클럭 기준 UNKNOWN |
| Dram max reads / writes | 64 / 32 | TA_EXT maxr 0, maxw 32. NPU AXI_EXT outstanding 64 / 32 | writes MATCH. reads: TA 0(E2 가설: 0 = 무제한)이면 AXI 64가 제한 → MATCH. **E2 미해결이므로 조건부** |
| Dram burst length | 128 B | AXI_EXT max_beats 필드 2 | **UNKNOWN** |
| Dram ports used | 2 | — | **UNKNOWN** |
| 물리 메모리 | Sram, Dram(모델) | SRAM 포트 → fast_base 0x31000000 영역, EXT 포트 → DDR(model_base 0x70000000) + TA 지연·대역폭 에뮬레이션 | 대응은 맞다. 물리 지연·대역폭이 Vela 모델과 같다는 증거는 없음 |

## 판정 (지시 3.5, 근거별)

- **`CONFIGURATION_MISMATCH_IDENTIFIED`: 해당 없음.**
  - 값을 확인한 항목(latency, outstanding, SRAM 작업공간, 포트 대응, MAC 수)은 모두 일치했다.
  - 불일치를 확인한 항목은 없다.
  - 대역폭·클럭 스케일·burst·포트 수는 UNKNOWN이다. 불일치가 없다는 증거로 쓰지 않는다.
- **`COST_MODEL_DISCREPANCY_OBSERVED`: 해당.** 같은 바이너리에서 Vela 비용 모델의 중간값이 보드 관측과 다르다(`vela_fidelity_analysis.csv`, README §Vela).
  - 바이트: SRAM write는 7/7 정확히 같다. SRAM read는 보드가 Vela의 65–80 %다. EXT read는 보드가 Vela보다 3–39 % 많다.
    EXT write는 보드가 Vela의 50–89 %다(G25 0.88, G09 0.50).
  - 사이클: NPU_ACTIVE ÷ Vela `cycles_npu`(compute 추정)가 1.98–3.33이다. Vela 비용 모델이 연산마다 compute와 memory 중 큰 값을 쓰는데도 그렇다(아래).
- **`CAUSE_UNRESOLVED`: 해당.** 오차의 원인 몫을 정할 근거가 없다.

## Vela 비용 모델 구성 (정적 검사, `stage6br_summary.json` `vela_cost_model_checks`)

- 커널이 있는 연산(30행)마다 `op_cycles` = max(`npu_cycles`, `sram_ac`, `dram_ac`)였다. 비용 성분을 더하지 않고 큰 값을 쓴다.
- 10개 컴파일 모두 `cycles_total` = Σ 연산 `op_cycles`였다. 연산 사이의 겹침은 모델에 없다.
- 7개 VALID 형상 모두에서 `cycles_total` ≥ `cycles_dram_access`다. 6개는 차이가 1 % 안이고 G12만 19 % 크다. Vela는 이 A2 그래프를 대부분 DRAM 접근이 지배하는 그래프로 추정한다.
- Vela 소스 코드에서 이 정의를 직접 확인하지는 않았다. 위 관계는 산출값에서 확인한 것이다.
- 설정을 보정한 가상의 예상값은 만들지 않았다(지시 3.5).
