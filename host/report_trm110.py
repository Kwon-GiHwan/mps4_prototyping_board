"""Regenerate docs/ETHOS_U85_PMU_TRM110_MEASURED.md from the evidence tree.

Rows = the 110 EV_TYPE values the public TRM (102685 r0p0) names. Per row: the
TRM's own description, Tier A readback verdict (boot 1), Tier B counts from the
three repeats (boot 9) with the set/slot they came from, the closed verdict, and
a factual note class for zeros. Nothing here interprets a value.
"""
import ast, csv, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pmu_events_parse as E

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "docs/ethos_u85_pmu_sources"
A = REPO / "evidence/pmu_evsweep/boot1"
B = REPO / "evidence/pmu_events/boot9"
OUT = REPO / "docs/ETHOS_U85_PMU_TRM110_MEASURED.md"


def category(n):
    if n == "no_event": return "no_event"
    if re.match(r"(sram|ext)\d_", n): return "포트별 개별"
    if re.match(r"(sram|ext)_", n): return "포트 집계"
    if n.startswith("axi_latency"): return "AXI latency"
    if n.startswith("ecc_"): return "ECC"
    if n in ("cycle", "npu_idle", "npu_active"): return "NPU 실행 상태"
    if n.startswith(("mac_", "ao_")): return "MAC / AO"
    if n.startswith("wd_"): return "Weight decoder"
    return "기타"


def zero_note(n, verdict):
    """Factual class for a COUNTED_ZERO row -- sourced facts, not attribution."""
    if verdict != "COUNTED_ZERO": return ""
    if re.match(r"sram[23]_", n): return "1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트)"
    if n.startswith("ecc_"): return "ECC 구성 여부 문서·레지스터로 확인 불가"
    if n.startswith("ext") and "enabled_cycles" not in n: return "이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0)"
    return "이 워크로드·창에서 0"


def build():
    trm = [(int(v), n, d) for v, n, d in json.loads((SRC / "trm_events_110.json").read_text())]
    a = {int(r["ev_type"]): r for r in csv.DictReader((A / "per_event.csv").open())}
    b = {int(r["ev_type"]): r for r in csv.DictReader((B / "per_event.csv").open())}
    raw = [r for r in json.loads((B / "raw_runs.json").read_text()) if "pmu" in r]
    hdr = json.loads((A / "header_decoded.json").read_text())
    summ_b = json.loads((B / "summary.json").read_text())
    loc = {}  # ev -> (set_id, slot)
    for set_id, codes in E.event_sets():
        for slot, ev in enumerate(codes): loc[ev] = (set_id, slot)
    # values straight from raw, keyed by (ev) -> [rep1, rep2, rep3]
    vals = {}
    for x in raw:
        for slot, ev in enumerate(x["pmu"]["event_codes"]):
            if ev is None: continue
            vals.setdefault(ev, {})[x["rep"]] = x["pmu"]["event_values"][slot]
    windows = {x["set_id"]: {x["rep"]: x["pmu"]["npu_pmu_window_cycles"] for x in raw if x["set_id"] == x["set_id"]} for x in raw}
    for x in raw: windows.setdefault(x["set_id"], {})[x["rep"]] = x["pmu"]["npu_pmu_window_cycles"]

    L = []
    w = L.append
    w("# 공개 TRM 110개 PMU 이벤트 — FI101 보드 실측 기록")
    w("")
    w("생성: `python3 host/report_trm110.py` (증거 트리에서 재생성; 손으로 편집하지 않는다). 2026-09-23.")
    w("")
    w("## 범위와 출처")
    w("")
    w("| 항목 | 값 |")
    w("| --- | --- |")
    w("| 대상 | Arm Ethos-U85 TRM 102685 r0p0 rev 0000-05, `PMEVTYPER<n>` *Table 2. Field EV_TYPE values* 의 명명된 110개 |")
    w("| 보드 | MPS4 FTDI-00FT46259002B, FI101-r1p0 (109762 v0100), NPU APB 0x50004000 |")
    w(f"| 구성(레지스터 실측) | CONFIG=`{hdr['config']['raw']}` → {hdr['config']['macs']} MAC, SRAM 포트 {hdr['config']['sram_ports']}, EXT 포트 {hdr['config']['ext_ports']}, WD {hdr['config']['weight_decoders']}; PMCR.num_event_cnt={hdr['pmcr']['num_event_cnt']} |")
    w(f"| Tier A (수용) | 부팅 1, 이미지 APP `{a[17]['app_sha256'][:16]}…`, EV_TYPE 0..1023 write→readback, P1(cnt_en=1) 슬롯 0 기준 |")
    w(f"| Tier B (카운트) | 부팅 9 (host-boot-index {summ_b['provenance']['host_boot_index']}), 이미지 APP `{summ_b['provenance']['app_sha256'][:16]}…`, 22세트×3회=66 RUN 전부 VALID |")
    w("| 워크로드 | 러너 내장 고정 `U85 Convolution test` (`apU85Conv_TEST`), 1회 추론/RUN |")
    w("| 측정 방법 | EVENTS 모드: `CMD=0` hold → guard → `PMCR=EN\\|RST` → guard → `PMCNTENSET=CYCLE\\|slots`, `PMEVTYPER[i]=id` → 추론 → 벤더 `\"Testing CPM signals\"` printf seam(`CMD=0xC` 직전)에서 PMCCNTR·PMEVCNTR 판독 |")
    w("| 승인 | 소유자 구두 2026-09-23 (사실만 기록) |")
    w("| 증거 | `evidence/pmu_evsweep/boot1/`, `evidence/pmu_events/boot9/{raw_runs.json,per_event.csv,summary.json,POST_HOC.md}` |")
    w("")
    w("판정(닫힌 집합, 3회 반복에서): `COUNTED_NONZERO` 3회 모두 >0 · `COUNTED_ZERO` 3회 모두 0 · `INCONSISTENT` 혼재 · `NOT_OBSERVED` 유효 RUN <3.")
    w("**0은 결과이지 부재의 증거가 아니다** — 아래 '비고'는 출처가 있는 사실 분류일 뿐 귀속이 아니다.")
    w("")
    # summary by category
    from collections import Counter, defaultdict
    cat_rows = defaultdict(list)
    for ev, n, d in trm: cat_rows[category(n)].append(ev)
    w("## 분류별 요약")
    w("")
    w("| 분류 | 개수 | NONZERO | ZERO | INCONSISTENT | NOT_OBSERVED |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    tot = Counter()
    for cat in ("NPU 실행 상태", "MAC / AO", "Weight decoder", "포트 집계", "AXI latency", "ECC", "포트별 개별", "no_event"):
        c = Counter(b[ev]["verdict"] for ev in cat_rows[cat])
        tot.update(c)
        w(f"| {cat} | {len(cat_rows[cat])} | {c['COUNTED_NONZERO']} | {c['COUNTED_ZERO']} | {c['INCONSISTENT']} | {c['NOT_OBSERVED']} |")
    w(f"| **합계** | **110** | **{tot['COUNTED_NONZERO']}** | **{tot['COUNTED_ZERO']}** | **{tot['INCONSISTENT']}** | **{tot['NOT_OBSERVED']}** |")
    w("")
    w("`no_event`(0)은 정의상 세지 않는 값이며 표에는 완전성을 위해 남긴다.")
    w("")
    w("## 창(PMCCNTR at seam), 세트별 3회")
    w("")
    w("| set | rep1 | rep2 | rep3 |")
    w("| --: | --: | --: | --: |")
    for s in sorted(windows): w(f"| {s} | {windows[s].get(1)} | {windows[s].get(2)} | {windows[s].get(3)} |")
    w("")
    w("## 110개 전체 — TRM 정의 · 수용 · 실측값")
    w("")
    w("값 열의 출처: `raw_runs.json` 의 `set_id`/`rep`/`event_values[slot]`; 위치 열이 그 좌표다.")
    w("")
    w("| EV_TYPE | 이름 | TRM 설명 | Tier A | rep1 | rep2 | rep3 | 판정 | 위치 (set/slot) | 비고 |")
    w("| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |")
    for ev, n, d in trm:
        rb = b[ev]; ra = a[ev]
        v = vals.get(ev, {})
        s_id, slot = loc[ev]
        note = zero_note(n, rb["verdict"]) if rb["verdict"] == "COUNTED_ZERO" else ("0/1 경계 혼재" if rb["verdict"] == "INCONSISTENT" else "")
        w(f"| {ev} | `{n}` | {d} | {ra['verdict_p1_slot0']} | {v.get(1)} | {v.get(2)} | {v.get(3)} | {rb['verdict']} | {s_id}/{slot} | {note} |")
    w("")
    w("## 레코드 안의 산술 관계 (POST_HOC_DESCRIPTIVE — 판정에 쓰이지 않음)")
    w("")
    def V(ev, rep=1): return vals[ev][rep]
    w(f"- 읽기 트랜잭션: `sram0_rd_trans_accepted` {V(512)} + `sram1_rd_trans_accepted` {V(528)} = {V(512)+V(528)} vs `sram_rd_trans_accepted` {V(128)}")
    w(f"- 읽기 비트: {V(514)} + {V(530)} = {V(514)+V(530)} vs `sram_rd_data_beat_received` {V(130)}")
    w(f"- 쓰기 비트: {V(519)} + {V(535)} = {V(519)+V(535)} vs `sram_wr_data_beat_written` {V(135)}")
    w(f"- `cycle`(17) − PMCCNTR 창: {[vals[17][r]-windows[loc[17][0]][r] for r in (1,2,3)]} (3회 상수; seam 판독 순서 지연 — 사전 등록 ±1 % 검사는 FAIL로 유지)")
    w(f"- `npu_active`(35) + `npu_idle`(32) vs 창: {[ (vals[35][r]+vals[32][r], windows[loc[35][0]][r]) for r in (1,2,3)]}")
    w("")
    w("## 이 문서가 말하지 않는 것")
    w("")
    w("값의 크기·비율·성능·효율. 워크로드 1개, 부팅 1회, 3회 반복. 다른 워크로드에서 어느 이벤트가 0이 아닐지는 다시 재야 안다.")
    w("TRM 밖의 61개(드라이버 전용 Reserved)는 `evidence/pmu_events/boot9/PER_EVENT.md` 에 있다.")
    OUT.write_text("\n".join(L) + "\n")
    return trm, vals


if __name__ == "__main__":
    trm, vals = build()
    print(f"wrote {OUT.relative_to(REPO)}: {len(trm)} rows")
