# -*- coding: utf-8 -*-
"""3장 -- 비용 구성을 연산 계열 4개로 귀속한 판.

계측 단위(IRQ 서비스 창) 기준. 단위 하나에 두 계열 이상이 들어 있으면,
그 안에서 가장 무거운 계열로 귀속한다 (합성곱 > 완전연결 > 원소별 > 기타).
'혼합'은 연산 계열이 아니라 측정의 성질이므로 범례에서 뺀다.

귀속의 근거: RNNoise 에서 Add/Mul/Sub/Concat 만 든 단위는 연산이 1개든 4개든
거의 전부 1,015 사이클인 반면, FullyConnected 가 든 단위는 4,015~7,015 이다.
다만 단위 안의 사이클 분할은 측정된 적이 없으므로 이것은 '가정'이고,
가정으로 귀속한 몫을 오른쪽 열에 그대로 적는다. 가정을 빼면 그 계열의 하한이다.
"""
import csv
from collections import defaultdict

exec(open("v8_helpers.py", encoding="utf-8").read())

OUT = "EthosU_RQ_slide3_attrib6.pptx"
PAPER = "../../paper"
UNITS_CSV = PAPER + "/mechanism/U85_ATTRIBUTION_UNITS.csv"
CYCLES_CSV = PAPER + "/raw_data_report/tables/3_3_cycles_by_mac.csv"

MUTED = RGBColor(0x8A, 0x97, 0xA6)
EYE = RGBColor(0xAE, 0xC2, 0xDE)

FAM = {"Conv2D": "Conv2D", "DepthwiseConv2D": "DWConv",
       "FullyConnected": "완전연결",
       "Add": "원소별", "Mul": "원소별", "Sub": "원소별",
       "Pad": "형상·이동", "Reshape": "형상·이동", "Pack": "형상·이동",
       "Concat": "형상·이동", "ResizeNearestNeighbor": "형상·이동",
       "AvgPool": "기타", "MaxPool": "기타", "Quantize": "기타", "Softmax": "기타"}
CATS = [("Conv2D", RGBColor(0x13, 0x36, 0x6B)),
        ("DWConv", RGBColor(0x4A, 0x7A, 0xB8)),
        ("완전연결", RGBColor(0x2E, 0x7D, 0x4F)),
        ("원소별", RGBColor(0x83, 0xAB, 0xD6)),
        ("형상·이동", RGBColor(0xC2, 0x8A, 0x1E)),
        ("기타", RGBColor(0x8A, 0x97, 0xA6))]
PRIO = [k for k, _c in CATS]
NAME = {"wav2letter_pruned_int8": "Wav2Letter", "mobilenet_v2_1.0_224_INT8": "MobileNetV2",
        "yolo-fastest_192_face_v4": "YOLO-Fastest", "ad_medium_int8": "AD MedNet",
        "vww4_128_128_INT8": "VWW4", "kws_micronet_m": "KWS MicroNet",
        "rnnoise_INT8": "RNNoise"}

S = defaultdict(lambda: defaultdict(int))
LO = defaultdict(lambda: defaultdict(int))
T = defaultdict(int)
ASSUMED = defaultdict(int)
for r in csv.DictReader(open(UNITS_CSV, encoding="utf-8")):
    if r["binding"] != "256_Low":
        continue
    fams = {FAM[t] for t in r["op_types"].split() if t in FAM}
    c, w = int(r["ccnt"]), r["workload"]
    T[w] += c
    k = next(f for f in PRIO if f in fams)
    S[w][k] += c
    if len(fams) == 1:
        LO[w][k] += c
    else:
        ASSUMED[w] += c
assert len(T) == 7, sorted(T)
for w in T:
    assert sum(S[w][k] for k in PRIO) == T[w], w

WHOLE = {r["workload"]: int(r["cycles"])
         for r in csv.DictReader(open(CYCLES_CSV, encoding="utf-8"))
         if r["platform"] == "SSE-320" and r["mac"] == "256" and r["cycles"]}
COV = [T[w] / WHOLE[w] for w in T]
assert 0.97 < min(COV) and max(COV) <= 1.0, COV
COVTXT = "%.1f–%.1f%%" % (100 * min(COV), 100 * max(COV))
assert S["rnnoise_INT8"]["Conv2D"] == 0 and S["rnnoise_INT8"]["DWConv"] == 0
CONV = {w: (S[w]["Conv2D"] + S[w]["DWConv"]) / T[w] for w in T}
CONVMIN = min(v for v in CONV.values() if v)
RNFC = S["rnnoise_INT8"]["완전연결"] / T["rnnoise_INT8"]


def blank():
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


for _sid in list(prs.slides._sldIdLst):
    prs.part.drop_rel(_sid.rId)
    prs.slides._sldIdLst.remove(_sid)

s = blank()
tb(s, 0.48, 0.26, 8.90, 0.66, "3. 실행 비용은 어떤 연산 계열에 쓰이는가?", size=26,
   bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
tb(s, 9.45, 0.42, 3.40, 0.30, "RQ1 · 비용 구성", size=11.5, color=EYE, align=PP_ALIGN.RIGHT)
rect(s, 0.50, 1.24, 12.33, 0.84, LIGHT)
rect(s, 0.50, 1.24, 0.055, 0.84, NAVY)
tb(s, 0.74, 1.30, 11.90, 0.72,
   ["여섯 모델은 비용의 %.0f%% 이상이 합성곱(Conv2D + DWConv)이고, 두 계열의 비율은 모델마다 다르다."
    % (100 * CONVMIN),
    "RNNoise만 합성곱이 없고, 완전연결이 %.0f%%를 차지한다." % (100 * RNFC)],
   size=15, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE, spacing=1.20)
tb(s, 0.52, 6.40, 12.30, 0.50,
   ["한 계측 단위에 두 계열이 함께 들어간 경우 그 안에서 가장 무거운 계열로 귀속했다 "
    "(Conv2D > DWConv > 완전연결 > 원소별 > 형상·이동 > 기타). 그렇게 귀속한 몫이 오른쪽 열이고, 그만큼이 해당 계열의 상한·하한 차이다.",
    "계측 단위(IRQ 서비스 창) 기준 · Corstone-320 · U85-256 의 256_Low 셀 단독 · "
    "계측 합계는 각 모델 TOTAL의 " + COVTXT + " · 형상·이동 = Pad·Reshape·Pack·Concat·Resize · 기타 = 풀링·양자화·정규화"],
   size=9, color=MUTED, spacing=1.30)

lx = 2.44
for nm, colr in CATS:
    rect(s, lx, 2.48, 0.20, 0.12, colr)
    tb(s, lx + 0.26, 2.40, 1.20, 0.26, nm, size=10, color=GRAY, anchor=MSO_ANCHOR.MIDDLE)
    lx += 1.24
tb(s, 9.90, 2.40, 2.93, 0.26, "귀속 가정분", size=10.5, bold=True, color=NAVY,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

BX, BW_ = 2.44, 7.24
yy = 2.92
for w in sorted(T, key=lambda w: (-CONV[w], -S[w]["완전연결"] / T[w])):
    tb(s, 0.50, yy, 1.80, 0.44, NAME[w], size=11, bold=True, color=TEXT,
       align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    cx = BX
    for nm, colr in CATS:
        f = S[w][nm] / T[w]
        if f <= 0:
            continue
        rect(s, cx, yy + 0.05, BW_ * f, 0.34, colr)
        if f >= 0.075:
            tb(s, cx, yy + 0.05, BW_ * f, 0.34, "%.1f%%" % (100 * f), size=9.5,
               bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        cx += BW_ * f
    a = ASSUMED[w] / T[w]
    tb(s, 9.90, yy, 2.93, 0.44, ("%.1f%%" % (100 * a)) if a else "없음",
       size=11, bold=bool(a), color=RED if a >= 0.10 else (NAVY if a else MUTED),
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    yy += 0.47

prs.save(OUT)
print("wrote", OUT, "| 합성곱 최소 %.1f%% · RNNoise FC %.1f%%" % (100 * CONVMIN, 100 * RNFC))
for w in sorted(CONV, key=lambda w: -CONV[w]):
    print("   %-26s Conv2D %5.1f%% / DWConv %5.1f%%" % (NAME[w], 100*S[w]["Conv2D"]/T[w], 100*S[w]["DWConv"]/T[w]))
