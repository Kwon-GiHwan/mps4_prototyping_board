# -*- coding: utf-8 -*-
"""3장 대안 -- 비용 구성을 연산 계열 5개로 묶은 판.

계측 단위(IRQ 서비스 창) 기준. 단위 하나가 한 계열만 담으면 그 계열로,
두 계열 이상을 담으면 '혼합'으로 센다. 네 범주 모두 사이클은 측정됐다;
혼합은 계열별 귀속만 불가능한 몫이다.

합성곱 중심으로 서술하지 않는다. RNNoise 는 '합성곱 없음'이 아니라
완전연결·원소별 모델이므로, 계열을 제 이름으로 놓고 센다.
"""
import csv, math
from collections import defaultdict

exec(open("v8_helpers.py", encoding="utf-8").read())

OUT = "EthosU_RQ_slide3_families.pptx"
PAPER = "../../paper"
UNITS_CSV = PAPER + "/mechanism/U85_ATTRIBUTION_UNITS.csv"
CYCLES_CSV = PAPER + "/raw_data_report/tables/3_3_cycles_by_mac.csv"

MUTED = RGBColor(0x8A, 0x97, 0xA6)
EYE = RGBColor(0xAE, 0xC2, 0xDE)

# 연산 종류 -> 계열. 영향이 미미한 계열(풀링·양자화·정규화·형상 이동)은 기타로 묶는다.
FAM = {"Conv2D": "합성곱", "DepthwiseConv2D": "합성곱",
       "FullyConnected": "완전연결",
       "Add": "원소별", "Mul": "원소별", "Sub": "원소별",
       "Pad": "기타", "Reshape": "기타", "Pack": "기타", "Concat": "기타",
       "ResizeNearestNeighbor": "기타", "AvgPool": "기타", "MaxPool": "기타",
       "Quantize": "기타", "Softmax": "기타"}
# 어느 모델에서든 차지하는 최대 비중 순 (전체 사이클 합은 Wav2Letter 하나에 눌린다)
CATS = [("합성곱", RGBColor(0x13, 0x36, 0x6B)),
        ("혼합", RGBColor(0xC2, 0x8A, 0x1E)),
        ("완전연결", RGBColor(0x2E, 0x7D, 0x4F)),
        ("원소별", RGBColor(0x4A, 0x7A, 0xB8)),
        ("기타", RGBColor(0x8A, 0x97, 0xA6))]
NAME = {"wav2letter_pruned_int8": "Wav2Letter", "mobilenet_v2_1.0_224_INT8": "MobileNetV2",
        "yolo-fastest_192_face_v4": "YOLO-Fastest", "ad_medium_int8": "AD MedNet",
        "vww4_128_128_INT8": "VWW4", "kws_micronet_m": "KWS MicroNet",
        "rnnoise_INT8": "RNNoise"}

S = defaultdict(lambda: defaultdict(int))
T = defaultdict(int)
MIX = defaultdict(lambda: defaultdict(int))
for r in csv.DictReader(open(UNITS_CSV, encoding="utf-8")):
    if r["binding"] != "256_Low":
        continue
    fams = {FAM[t] for t in r["op_types"].split() if t in FAM}
    c, w = int(r["ccnt"]), r["workload"]
    T[w] += c
    if len(fams) == 1:
        S[w][next(iter(fams))] += c
    else:
        S[w]["혼합"] += c
        MIX[w][" + ".join(sorted(fams))] += c
assert len(T) == 7, sorted(T)
for w in T:
    assert abs(sum(S[w][k] for k, _c in CATS) - T[w]) == 0, w

WHOLE = {r["workload"]: int(r["cycles"])
         for r in csv.DictReader(open(CYCLES_CSV, encoding="utf-8"))
         if r["platform"] == "SSE-320" and r["mac"] == "256" and r["cycles"]}
COV = [T[w] / WHOLE[w] for w in T]
assert 0.97 < min(COV) and max(COV) <= 1.0, COV
COVTXT = "%.1f–%.1f%%" % (100 * min(COV), 100 * max(COV))
assert S["rnnoise_INT8"]["합성곱"] == 0
# 최대 비중 순으로 실제 정렬돼 있는지 (범례 순서의 근거)
_mx = {k: max(S[w][k] / T[w] for w in T) for k, _c in CATS}
assert [k for k, _c in CATS] == sorted(_mx, key=lambda k: -_mx[k]), _mx


def blank():
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


for _sid in list(prs.slides._sldIdLst):
    prs.part.drop_rel(_sid.rId)
    prs.slides._sldIdLst.remove(_sid)

s = blank()
tb(s, 0.48, 0.26, 8.90, 0.66, "3. 실행 비용은 어떤 연산 계열에 분포하는가?", size=26,
   bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
tb(s, 9.45, 0.42, 3.40, 0.30, "RQ1 · 비용 구성", size=11.5, color=EYE, align=PP_ALIGN.RIGHT)
rect(s, 0.50, 1.24, 12.33, 0.84, LIGHT)
rect(s, 0.50, 1.24, 0.055, 0.84, NAVY)
tb(s, 0.74, 1.30, 11.90, 0.72,
   ["여섯 모델은 비용의 %.1f–%.1f%%가 합성곱 계열이다." % (
        100 * min(S[w]["합성곱"] / T[w] for w in T if S[w]["합성곱"]),
        100 * max(S[w]["합성곱"] / T[w] for w in T)),
    "RNNoise만 합성곱이 없고, 완전연결과 원소별 연산이 그 자리를 차지한다."],
   size=15, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE, spacing=1.20)
tb(s, 0.52, 6.44, 12.30, 0.44,
   ["다섯 계열 모두 사이클은 측정됐다. 혼합 = 한 계측 단위에 두 계열 이상이 함께 들어가 계열별 귀속만 안 되는 몫",
    "계측 단위(IRQ 서비스 창) 기준 · Corstone-320 · U85-256 의 256_Low 셀 단독 · "
    "계측 합계는 각 모델 TOTAL의 " + COVTXT + " · 기타 = 형상·이동 · 풀링 · 양자화 · 정규화"],
   size=9, color=MUTED, spacing=1.30)

lx = 2.30
for nm, colr in CATS:
    rect(s, lx, 2.48, 0.20, 0.12, colr)
    tb(s, lx + 0.28, 2.40, 1.30, 0.26, nm, size=10, color=GRAY, anchor=MSO_ANCHOR.MIDDLE)
    lx += 1.42
tb(s, 9.60, 2.40, 3.23, 0.26, "혼합의 주 내역", size=10, bold=True, color=NAVY,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

BX, BW_ = 2.30, 7.12
yy = 2.92
for w in sorted(T, key=lambda w: -S[w]["합성곱"] / T[w]):
    tb(s, 0.50, yy, 1.66, 0.44, NAME[w], size=11, bold=True, color=TEXT,
       align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    cx = BX
    for nm, colr in CATS:
        f = S[w][nm] / T[w]
        if f <= 0:
            continue
        rect(s, cx, yy + 0.05, BW_ * f, 0.34, colr)
        if f >= 0.085:
            tb(s, cx, yy + 0.05, BW_ * f, 0.34, "%.1f%%" % (100 * f), size=9.5,
               bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        cx += BW_ * f
    if MIX[w]:
        top = sorted(MIX[w].items(), key=lambda x: -x[1])
        txt = "%s  %.1f%%" % (top[0][0], 100 * top[0][1] / T[w])
        if len(top) > 1:
            txt += "  외 %d" % (len(top) - 1)
    else:
        txt = "—"
    tb(s, 9.60, yy, 3.23, 0.44, txt, size=9.5, color=NAVY if MIX[w] else MUTED,
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    yy += 0.47

prs.save(OUT)
print("wrote", OUT, "| 커버리지", COVTXT)
