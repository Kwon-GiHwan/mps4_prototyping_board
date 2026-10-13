# -*- coding: utf-8 -*-
"""RNNoise · U85 · 메모리 모드별 256->512 (P1-A).
델타는 MAC 두 배와 레퍼런스 프로파일 교체가 합쳐진 값이다 (256=Low, 512=Mid_512).
"""
import json
exec(open("v8_helpers.py", encoding="utf-8").read())

OUT = "EthosU_RQ_memmode.pptx"
PAPER = "../../paper"
MUTED = RGBColor(0x8A, 0x97, 0xA6)
EYE = RGBColor(0xAE, 0xC2, 0xDE)
GREEN = RGBColor(0x2E, 0x7D, 0x4F)

# Sram_Only / Shared_Sram 은 P1-A, Dedicated_Sram 은 P0 기준선(formal matrix)이다.
# P1-A 계획서: "T-DS (Dedicated_Sram = P0 baseline, reused)".
import csv
V, CFGOF = {}, {}
_d = json.load(open(PAPER + "/mechanism/U85_P1A_MATRIX.json", encoding="utf-8"))
for c in (_d if isinstance(_d, list) else list(_d.values())):
    if isinstance(c, dict) and "rnnoise" in str(c.get("cell", "")):
        V[(c["mode"], int(c["macs"]))] = int(c["total"])
        CFGOF[int(c["macs"])] = c["system_config"]
for r in csv.DictReader(open(PAPER + "/mechanism/U85_FORMAL_MATRIX.csv", encoding="utf-8")):
    if r["model"] == "rnnoise_INT8" and r["binding"] in ("256_Low", "512_Mid512"):
        V[("Dedicated_Sram", int(r["macs"]))] = int(r["clean_total"])
        assert CFGOF[int(r["macs"])] == r["system_config"], r["cell"]
SRC = {"Sram_Only": "P1-A", "Shared_Sram": "P1-A", "Dedicated_Sram": "P0 기준선"}
# default_vela.ini 의 Memory_Mode 정의 (Axi0 = SRAM, Axi1 = DRAM)
#   Sram_Only       const=Axi0 arena=Axi0
#   Shared_Sram     const=Axi1 arena=Axi0            DRAM 은 읽기 전용, SRAM 은 Cortex-M 과 공유
#   Dedicated_Sram  const=Axi1 arena=Axi1 cache=Axi0 arena_cache_size=393216 (NPU 전용)
MODES = [("Sram_Only", "가중치 · arena 모두 SRAM"),
         ("Shared_Sram", "가중치 DRAM · arena SRAM (Cortex-M 과 공유)"),
         ("Dedicated_Sram", "가중치 · arena 모두 DRAM · SRAM 384KB 는 NPU 전용 캐시")]
for m, _n in MODES:
    assert (m, 256) in V and (m, 512) in V, m
assert CFGOF[256].endswith("Low") and CFGOF[512].endswith("Mid_512"), CFGOF


def blank():
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


def fmt(n):
    return "{:,}".format(n)


for _sid in list(prs.slides._sldIdLst):
    prs.part.drop_rel(_sid.rId)
    prs.slides._sldIdLst.remove(_sid)

s = blank()
tb(s, 0.48, 0.26, 8.90, 0.66, "메모리 배치를 바꾸면 무엇이 달라지는가", size=26, bold=True,
   color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
tb(s, 9.45, 0.42, 3.40, 0.30, "RNNoise · U85", size=11.5, color=EYE, align=PP_ALIGN.RIGHT)
rect(s, 0.50, 1.24, 12.33, 0.84, LIGHT)
rect(s, 0.50, 1.24, 0.055, 0.84, NAVY)
_lo, _hi = min(V[(m, 256)] for m, _n in MODES), max(V[(m, 256)] for m, _n in MODES)
_dl = [V[(m, 512)] - V[(m, 256)] for m, _n in MODES]
tb(s, 0.74, 1.30, 11.90, 0.72,
   ["세 배치 모두에서 512가 더 느리다 — 방향은 배치와 무관하다.",
    "그러나 같은 모델의 비용이 배치에 따라 %.1f배, 역전 크기는 %.1f배 달라진다."
    % (_hi / _lo, max(_dl) / min(_dl))],
   size=15, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE, spacing=1.20)

# 가로폭은 슬라이드 본문 폭(12.33)의 2/5. 배치 설명은 첫 열 둘째 줄로 접는다.
TW = 12.33 * 0.4
WID = [TW * 0.415, TW * 0.200, TW * 0.200, TW * 0.185]
assert abs(sum(WID) - TW) < 1e-9

tb(s, 0.50, 2.40, TW, 0.26,
   "delta = TOTAL(512) − TOTAL(256) · 양수 = 느려짐", size=10, bold=True, color=NAVY)

rows = [["메모리 배치 Config", "256 MAC", "512 MAC", "delta"]]
for m, desc in MODES:
    a, b = V[(m, 256)], V[(m, 512)]
    rows.append([[(m, {"size": 11, "bold": True, "color": TEXT}),
                  (desc, {"size": 7, "color": GRAY})],
                 fmt(a), fmt(b), "+%s" % fmt(b - a)])
grid(s, 0.50, 2.74, WID, rows, header_h=0.44, row_h=0.78, size=11, header_size=9.5)

tb(s, 0.52, 6.40, 12.30, 0.44,
   ["세 행 모두 ARM 레퍼런스 사다리를 따른다(256 = SYS_DRAM_Low, 512 = SYS_DRAM_Mid_512) — "
    "delta 에는 MAC 두 배와 메모리 버스 조건 교체가 함께 들어 있다. 프로파일을 고정하면 부호가 뒤집힌다 "
    "(low −5,000 · mid −7,000).",
    "출처 U85_P1A_MATRIX.json (Sram_Only · Shared_Sram) · U85_FORMAL_MATRIX.csv (Dedicated_Sram, P0 기준선) · "
    "clean NPU TOTAL · 판정 delta>0 → REGRESSING, 임계값 없음"],
   size=9, color=MUTED, spacing=1.30)

prs.save(OUT)
print("wrote", OUT, "| 비용 %.1f배 · 역전 %.1f배" % (_hi / _lo, max(_dl) / min(_dl)))
