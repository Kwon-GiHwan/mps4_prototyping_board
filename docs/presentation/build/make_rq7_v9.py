# -*- coding: utf-8 -*-
"""EthosU_RQ_v9 -- the 7-slide RQ deck, in the Corstone_Family v8 visual language
(v8_helpers.py).

Design spec:   ~/Downloads/EthosU_RQ_7slides_v9_overviews_screen.md
Revision pass: ~/Downloads/EthosU_RQ_v9_revision_plan.md  (2026-09-16)
Targeted pass: ~/Downloads/EthosU_RQ_v9_1_targeted_revision.md, with the author's
               later correction: the new cost-composition page summarises every
               model that has a group profile, not a pre-chosen KWS/RNNoise pair.

Slides 2 and 3 read their panel data out of the executability campaign archive at
build time: 133 cells, one harness, all six Corstone/NPU configurations. Its
SSE-300 and SSE-320 cells reproduce the 74 canonical cells of
3_3_cycles_by_mac.csv exactly, asserted below.

Numbers that come from elsewhere carry their source in a comment; each was
checked against the raw log rather than transcribed from a summary.
"""
import csv, json, math, os, tarfile
from collections import defaultdict

exec(open("v8_helpers.py", encoding="utf-8").read())
from pptx.enum.shapes import MSO_CONNECTOR

# 빌드 산출물은 항상 _build 접미사로만 쓴다. EthosU_RQ_v9.pptx 는 사람이 편집하는
# 파일이므로 빌더가 절대 덮어쓰지 않는다 (2026-09-16에 한 번 덮어써서 편집본을 잃었다).
OUT = "EthosU_RQ_v9_build.pptx"
PAPER = "../../paper"
CYCLES_CSV = PAPER + "/raw_data_report/tables/3_3_cycles_by_mac.csv"
EXEC_TAR = PAPER + "/evidence/executability-20260825/cells/per_cell_evidence.tar.gz"
GROUPS_CSV = PAPER + "/mechanism/U85_GROUP_DIFFERENTIAL.csv"

STEEL = RGBColor(0x4A, 0x7A, 0xB8)
PALE = RGBColor(0xF7, 0xF9, 0xFC)
LINEC = RGBColor(0xCB, 0xD6, 0xE3)
MUTED = RGBColor(0x8A, 0x97, 0xA6)
EYE = RGBColor(0xAE, 0xC2, 0xDE)
GREEN = RGBColor(0x2E, 0x7D, 0x4F)
MARK = RGBColor(0xDF, 0xE8, 0xF4)

MODELS = [
    ("wav2letter_pruned_int8", "Wav2Letter", RGBColor(0x13, 0x36, 0x6B)),
    ("mobilenet_v2_1.0_224_INT8", "MobileNetV2", RGBColor(0x4A, 0x7A, 0xB8)),
    ("yolo-fastest_192_face_v4", "YOLO-Fastest", RGBColor(0x83, 0xAB, 0xD6)),
    ("ad_medium_int8", "AD MedNet", RGBColor(0x2E, 0x7D, 0x4F)),
    ("vww4_128_128_INT8", "VWW4", RGBColor(0x8C, 0x9A, 0xA8)),
    ("kws_micronet_m", "KWS MicroNet", RGBColor(0xC2, 0x8A, 0x1E)),
    ("rnnoise_INT8", "RNNoise", RGBColor(0xA4, 0x0F, 0x16)),
]
HERO = "rnnoise_INT8"
PANELS = [
    ("Corstone-300 · U55", "SSE-300", "ethos-u55"),
    ("Corstone-300 · U65", "SSE-300", "ethos-u65"),
    ("Corstone-310 · U55", "SSE-310", "ethos-u55"),
    ("Corstone-310 · U65", "SSE-310", "ethos-u65"),
    ("Corstone-315 · U65", "SSE-315", "ethos-u65"),
    ("Corstone-320 · U85", "SSE-320", "ethos-u85"),
]

# ---------------------------------------------------------------- source data
CYC = {}
_tf = tarfile.open(EXEC_TAR)
for _m in _tf.getmembers():
    _n = os.path.basename(_m.name)
    if not _n.endswith(".json") or _n.startswith("_"):
        continue
    _d = json.load(_tf.extractfile(_m))
    _wl, _plat, _nm = _d["cell_id"].split("__")
    _npu, _mac = _nm.rsplit("-", 1)
    for _a in _d["attempts"]:
        _r = _a.get("run") or {}
        if _r.get("status") == "SUCCESS" and _r.get("npu_total_cycles") is not None:
            CYC[(_plat, _npu, _wl, int(_mac))] = _r["npu_total_cycles"]

_n = 0
for _r in csv.DictReader(open(CYCLES_CSV, encoding="utf-8")):
    if not _r["cycles"]:
        continue
    _k = (_r["platform"], _r["npu"], _r["workload"], int(_r["mac"]))
    assert CYC[_k] == int(_r["cycles"]), ("canonical mismatch", _k)
    _n += 1
assert _n == 74, _n

# RNNoise / U85 must sit at both ends of every panel for the slide 2 claim.
for _l, _p, _u in PANELS:
    _v = {m: CYC[(_p, _u, m, 256)] for m, _nm, _c in MODELS}
    assert min(_v, key=_v.get) == HERO and max(_v, key=_v.get) == "wav2letter_pruned_int8", _l


AMBER = RGBColor(0xC2, 0x8A, 0x1E)
# (집계 키, 화면 라벨, 색). 앞의 셋은 "분리 측정됨 + 연산 종류", 마지막 하나만
# "분리되지 않음"이라는 다른 축이므로 이름에서 드러나게 한다.
CATS = [("Conv2D", "Conv2D", RGBColor(0x13, 0x36, 0x6B)),
        ("DepthwiseConv2D", "DepthwiseConv2D", RGBColor(0x4A, 0x7A, 0xB8)),
        ("혼합 그룹", "미분해 (2종 이상)", AMBER),
        ("기타 단일 연산", "비합성곱 (단일)", RGBColor(0x8A, 0x97, 0xA6))]


def _cat(t):
    st = set(t.split())
    st.discard("KERNEL_WAIT")
    if st == {"Conv2D"}:
        return "Conv2D"
    if st == {"DepthwiseConv2D"}:
        return "DepthwiseConv2D"
    return "혼합 그룹" if len(st) > 1 else "기타 단일 연산"


GRP = defaultdict(lambda: defaultdict(int))
GTOT = defaultdict(int)
GMAX = {}
for _r in csv.DictReader(open(GROUPS_CSV, encoding="utf-8")):
    if _r["binding_pair"] != "B-frozen":
        continue
    _c, _w = int(_r["cycles_256"]), _r["workload"]
    GRP[_w][_cat(_r["member_types"])] += _c
    GTOT[_w] += _c
    if _w not in GMAX or _c > GMAX[_w]:
        GMAX[_w] = _c
# coverage of each model's whole-model TOTAL by the instrumented groups
COV = [GTOT[w] / CYC[("SSE-320", "ethos-u85", w, 256)] for w in GTOT]
assert 0.97 < min(COV) and max(COV) < 1.0, COV
COVTXT = "%.1f–%.1f%%" % (100 * min(COV), 100 * max(COV))
CONVSH = {w: GRP[w]["Conv2D"] / GTOT[w] for w in GTOT}
TOPW = max(CONVSH, key=CONVSH.get)
assert GRP["rnnoise_INT8"]["Conv2D"] == 0 and GRP["rnnoise_INT8"]["DepthwiseConv2D"] == 0


# --------------------------------------------------------------- draw helpers
def blank():
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


def head(s, eyebrow, title, answer, caption=None):
    tb(s, 0.48, 0.26, 8.90, 0.66, title, size=26, bold=True, color=WHITE,
       anchor=MSO_ANCHOR.MIDDLE)
    tb(s, 9.45, 0.42, 3.40, 0.30, eyebrow, size=11.5, color=EYE, align=PP_ALIGN.RIGHT)
    rect(s, 0.50, 1.24, 12.33, 0.84, LIGHT)
    rect(s, 0.50, 1.24, 0.055, 0.84, NAVY)
    tb(s, 0.74, 1.30, 11.90, 0.72, answer, size=15, bold=True, color=NAVY,
       anchor=MSO_ANCHOR.MIDDLE, spacing=1.20)
    if caption:
        tb(s, 0.52, 6.56, 12.30, 0.28, caption, size=9.5, color=MUTED)


def conn(s, x1, y1, x2, y2, color=LINEC, w=0.75, dash=None):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                               Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(w)
    if dash:
        ln = c.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:prstDash"), {"val": dash}))
    return c


def dot(s, cx, cy, d, color, ring=None):
    o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2),
                           Inches(d), Inches(d))
    o.fill.solid(); o.fill.fore_color.rgb = color
    if ring is None:
        o.line.fill.background()
    else:
        o.line.color.rgb = ring; o.line.width = Pt(1.0)
    o.shadow.inherit = False
    return o


def arrow(s, x, y, w, h, color=NAVY, shape=MSO_SHAPE.RIGHT_ARROW):
    a = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    a.fill.solid(); a.fill.fore_color.rgb = color
    a.line.fill.background(); a.shadow.inherit = False
    return a


def panel(s, x, y, w, hh, h, label):
    rect(s, x, y, w, hh, NAVY)
    tb(s, x + 0.05, y, w - 0.10, hh, label, size=9.5, bold=True, color=WHITE,
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    rect(s, x, y + hh, w, h, PALE)
    return x, y + hh, w, h


def card(s, x, y, w, h, num, title, desc):
    rect(s, x, y, w, h, LIGHT)
    rect(s, x, y, w, 0.11, NAVY)
    cw = 0.62 if len(str(num)) < 2 else 0.98
    rect(s, x + 0.28, y + 0.36, cw, 0.62, NAVY)
    tb(s, x + 0.28, y + 0.36, cw, 0.62, str(num), size=21 if cw < 0.7 else 17, bold=True,
       color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    tb(s, x + 0.42 + cw, y + 0.36, w - 0.72 - cw, 0.62, title, size=18.5, bold=True, color=NAVY,
       anchor=MSO_ANCHOR.MIDDLE)
    tb(s, x + 0.28, y + 1.16, w - 0.56, h - 1.34, desc, size=13.5, color=GRAY,
       spacing=1.30)


def ntable(s, x, y, widths, header, rows, header_h=0.34, row_h=0.44, size=9.5,
           hsize=9.5, emph=None, bold_cells=()):
    cx = x
    for j, w in enumerate(widths):
        rect(s, cx, y, w, header_h, NAVY)
        tb(s, cx + 0.05, y, w - 0.10, header_h, header[j], size=hsize, bold=True,
           color=WHITE, align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER,
           anchor=MSO_ANCHOR.MIDDLE, spacing=1.12)
        cx += w
    cy = y + header_h
    for i, row in enumerate(rows):
        cx = x
        hl = (emph is not None and i == emph)
        for j, w in enumerate(widths):
            bc = (i, j) in bold_cells
            rect(s, cx, cy, w, row_h, MARK if bc else (LIGHT if i % 2 == 0 else WHITE))
            tb(s, cx + 0.07, cy, w - 0.14, row_h, row[j], size=size, bold=hl or bc,
               color=RED if hl else (NAVY if bc else TEXT),
               align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT,
               anchor=MSO_ANCHOR.MIDDLE)
            cx += w
        cy += row_h
    return cy


def fmt(n):
    return "{:,}".format(n)


for _sid in list(prs.slides._sldIdLst):
    prs.part.drop_rel(_sid.rId)
    prs.slides._sldIdLst.remove(_sid)

# =============================================================== 1 · RQ1 개요
s = blank()
head(s, "RQ1 · 개요", "1. 성능과 MAC 확장 특성",
     ["워크로드와 Ethos-U 구성에 따라",
      "추론 실행 비용과 MAC 확장 특성은 어떻게 달라지는가?"])
card(s, 1.15, 3.24, 4.75, 2.10, "2–3", "실행 비용과 구성",
     ["모델별 총비용 · 연산 그룹별 분포"])
card(s, 7.45, 3.24, 4.75, 2.10, 4, "MAC 확장 특성", ["확장 이득 · 평탄 · 역전"])
tb(s, 5.60, 3.80, 1.95, 0.26, "분석 순서", size=9.5, color=MUTED, align=PP_ALIGN.CENTER)
arrow(s, 6.03, 4.10, 1.10, 0.36)

# =============================================================== 2 · 실행 비용
s = blank()
head(s, "RQ1 · 실행 비용", "2. 모델별 실행 비용은 어떻게 다른가?",
     ["모델 간 비용 순위는 평가한 여섯 구성에서 모두 같다. 구성을 바꾼 변동은",
      "모델당 1.1–5.5배인 반면, 한 구성 안에서 모델 간 차이는 146–772배다."],
     "256 MAC · TOTAL cycles · 공통 로그축 · 각 행은 여섯 구성의 값과 그 범위   |   "
     "인접 모델 중 범위가 겹치는 쌍은 VWW4–AD MedNet 하나뿐이다 (음영) · "
     "Corstone-310·U65와 315·U65는 모든 모델에서 값이 같아 점이 겹친다")

CFG = [("Corstone-300 · U55", "SSE-300", "ethos-u55", RGBColor(0x13, 0x36, 0x6B)),
       ("Corstone-300 · U65", "SSE-300", "ethos-u65", RGBColor(0x4A, 0x7A, 0xB8)),
       ("Corstone-310 · U55", "SSE-310", "ethos-u55", RGBColor(0x2E, 0x7D, 0x4F)),
       ("Corstone-310 · U65", "SSE-310", "ethos-u65", RGBColor(0x7E, 0xAE, 0x92)),
       ("Corstone-315 · U65", "SSE-315", "ethos-u65", RGBColor(0xC2, 0x8A, 0x1E)),
       ("Corstone-320 · U85", "SSE-320", "ethos-u85", RGBColor(0xA4, 0x0F, 0x16))]
IX, IW = 2.36, 8.72
LO, HI = 4.13, 7.37
ROW0, ROWH = 2.88, 0.49


def cx_log(v):
    return IX + IW * (math.log10(v) - LO) / (HI - LO)


lx = 2.36
for nm, _p, _u, colr in CFG:
    dot(s, lx + 0.07, 2.44, 0.135, colr, WHITE)
    tb(s, lx + 0.22, 2.32, 1.22, 0.24, nm.replace("Corstone-", ""), size=9, color=GRAY,
       anchor=MSO_ANCHOR.MIDDLE)
    lx += 1.45
tb(s, 11.32, 2.32, 1.51, 0.24, "구성 간 변동폭", size=9, bold=True, color=NAVY,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

VAL = {mid: [CYC[(p_, u_, mid, 256)] for _n, p_, u_, _c in CFG] for mid, _n, _c in MODELS}
# the single overlapping neighbour pair, shaded behind the rows
_i = [m for m, _n, _c in MODELS].index("ad_medium_int8")
_lo, _hi = min(VAL["ad_medium_int8"]), max(VAL["vww4_128_128_INT8"])
assert _lo < _hi
rect(s, cx_log(_lo), ROW0 + _i * ROWH + 0.02, cx_log(_hi) - cx_log(_lo), 2 * ROWH - 0.04,
     RGBColor(0xFB, 0xF2, 0xE0))

for g in (1e5, 1e6, 1e7):
    conn(s, cx_log(g), ROW0, cx_log(g), ROW0 + 7 * ROWH, LINEC, 0.75, "sysDot")
    tb(s, cx_log(g) - 0.40, ROW0 + 7 * ROWH + 0.04, 0.80, 0.22,
       {1e5: "100K", 1e6: "1M", 1e7: "10M"}[g], size=9, color=MUTED, align=PP_ALIGN.CENTER)

for i, (mid, name, _c) in enumerate(MODELS):
    yy = ROW0 + i * ROWH
    cy = yy + ROWH / 2
    tb(s, 0.50, yy, 1.72, ROWH, name, size=11.5, bold=(mid == HERO),
       color=RED if mid == HERO else TEXT, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    vs = VAL[mid]
    conn(s, cx_log(min(vs)), cy, cx_log(max(vs)), cy, RGBColor(0xC2, 0xCD, 0xDA), 3.2)
    for v, (_n, _p, _u, colr) in zip(vs, CFG):
        dot(s, cx_log(v), cy, 0.145, colr, WHITE)
    tb(s, 11.32, yy, 1.51, ROWH, "%.2f×" % (max(vs) / min(vs)), size=11, bold=True,
       color=NAVY, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# =============================================================== 3 · 비용 구성
s = blank()
head(s, "RQ1 · 비용 구성", "3. 실행 비용은 어떤 연산 그룹에 분포하는가?",
     ["Conv 집중은 공통이 아니다 — Wav2Letter는 Conv 그룹이 %.1f%%인 반면," % (100 * CONVSH[TOPW]),
      "RNNoise는 Conv 그룹이 하나도 없고 비용이 전부 미분해·비합성곱 그룹에 있다."],
     "계측 그룹 합계 대비 % · 동일 조건 Corstone-320 · U85-256 · 계측 합계는 각 모델 TOTAL의 " + COVTXT + " · "
     "출처 mechanism/U85_GROUP_DIFFERENTIAL.csv")

lx = 2.36
for _k2, nm, colr in CATS:
    rect(s, lx, 2.48, 0.20, 0.12, colr)
    tb(s, lx + 0.28, 2.40, 1.86, 0.26, nm, size=9.5, color=GRAY, anchor=MSO_ANCHOR.MIDDLE)
    lx += 2.02
tb(s, 10.60, 2.40, 2.23, 0.26, "가장 큰 단일 그룹", size=9.5, bold=True, color=NAVY,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

BX, BW_ = 2.36, 8.06
MEASURED = sorted(GTOT, key=lambda w: -GRP[w]["Conv2D"] / GTOT[w])
UNMEASURED = [m for m, _n, _c in MODELS if m not in GTOT]
NAME = {m: n for m, n, _c in MODELS}
yy = 2.92
for w in MEASURED + UNMEASURED:
    tb(s, 0.50, yy, 1.72, 0.44, NAME[w], size=11, bold=True, color=TEXT,
       align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    if w in GTOT:
        cx = BX
        for key, _nm, colr in CATS:
            f = GRP[w][key] / GTOT[w]
            if f <= 0:
                continue
            rect(s, cx, yy + 0.05, BW_ * f, 0.34, colr)
            if f >= 0.10:
                tb(s, cx, yy + 0.05, BW_ * f, 0.34, "%.1f%%" % (100 * f), size=9.5,
                   bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            cx += BW_ * f
        tb(s, 10.60, yy, 2.23, 0.44, "%.1f%%" % (100 * GMAX[w] / GTOT[w]), size=11,
           bold=True, color=NAVY, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    else:
        rect(s, BX, yy + 0.05, BW_, 0.34, RGBColor(0xF1, 0xF3, 0xF5))
        tb(s, BX, yy + 0.05, BW_, 0.34, "그룹 프로파일 미계측", size=9.5, color=MUTED,
           align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        tb(s, 10.60, yy, 2.23, 0.44, "—", size=11, color=MUTED, align=PP_ALIGN.CENTER,
           anchor=MSO_ANCHOR.MIDDLE)
    yy += 0.47

# =============================================================== 4 · MAC 확장
s = blank()
head(s, "RQ1 · MAC 확장", "4. MAC 증가의 이득은 언제 줄거나 역전되는가?",
     ["MAC 확장 이득은 모델마다 다르며,",
      "RNNoise의 첫 역전에는 동반된 메모리 조건 변화가 기여한다."],
     "MAC Scale 별 사이클 변화 · 같은 NPU·모델의 최소 MAC 사이클을 1로 하여 정규화 · 가로축 MACs / cycle   |   "
     "교차표 출처 amendments/x4/run.log 캠페인 C")

MCOL = {"rnnoise_INT8": RGBColor(0xD1, 0x38, 0x3A),
        "kws_micronet_m": RGBColor(0x2E, 0x6F, 0xBA),
        "ad_medium_int8": RGBColor(0x2E, 0x9E, 0x8F),
        "vww4_128_128_INT8": RGBColor(0x8B, 0x6F, 0xC4),
        "yolo-fastest_192_face_v4": RGBColor(0xE0, 0xA3, 0x3E),
        "mobilenet_v2_1.0_224_INT8": RGBColor(0x7E, 0x93, 0xA8),
        "wav2letter_pruned_int8": RGBColor(0x1F, 0x38, 0x64)}
LEG = ["rnnoise_INT8", "kws_micronet_m", "ad_medium_int8", "vww4_128_128_INT8",
       "yolo-fastest_192_face_v4", "mobilenet_v2_1.0_224_INT8", "wav2letter_pruned_int8"]
SHORT = {"rnnoise_INT8": "RNNoise", "kws_micronet_m": "KWS",
         "ad_medium_int8": "AD Medium", "vww4_128_128_INT8": "VWW",
         "yolo-fastest_192_face_v4": "YOLO-Fastest",
         "mobilenet_v2_1.0_224_INT8": "MobileNetV2",
         "wav2letter_pruned_int8": "Wav2Letter"}
DASHC = RGBColor(0x33, 0x33, 0x33)

lx = 0.62
for mid in LEG:
    conn(s, lx, 2.29, lx + 0.30, 2.29, MCOL[mid], 2.2)
    dot(s, lx + 0.15, 2.29, 0.085, MCOL[mid])
    tb(s, lx + 0.38, 2.18, 1.28, 0.22, SHORT[mid], size=8.5, color=GRAY,
       anchor=MSO_ANCHOR.MIDDLE)
    lx += 1.62
conn(s, lx, 2.29, lx + 0.30, 2.29, DASHC, 1.2, "dash")
tb(s, lx + 0.38, 2.18, 2.30, 0.22, "MAC 비례 기준선", size=8.5, color=GRAY,
   anchor=MSO_ANCHOR.MIDDLE)

YMAX = 1.60
PW4 = 4.11
ROWY4 = [2.50, 4.02]
TTH, PH4 = 0.24, 1.02
for pi, (label, plat, npu) in enumerate(PANELS):
    cc, row = pi % 3, pi // 3
    px = 0.50 + cc * PW4
    macs = sorted({m for (p_, n_, _w, m) in CYC if p_ == plat and n_ == npu})
    m0 = macs[0]
    tb(s, px, ROWY4[row], PW4 - 0.16, TTH,
       "%s   ·   baseline %d MAC" % (label, m0), size=9, bold=True, color=NAVY,
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    py = ROWY4[row] + TTH + 0.02
    rect(s, px, py, PW4 - 0.16, PH4, WHITE)
    ix4 = px + (0.46 if cc == 0 else 0.22)
    iw4 = PW4 - 0.16 - (0.68 if cc == 0 else 0.44)
    iy4, ih4 = py + 0.06, PH4 - 0.12
    cyn = lambda r: iy4 + ih4 * (1 - r / YMAX)
    cxn = lambda k: ix4 + iw4 * k / max(len(macs) - 1, 1)
    for g in (0.0, 0.5, 1.0, 1.5):
        conn(s, ix4 - 0.06, cyn(g), ix4 + iw4 + 0.06, cyn(g), LINEC, 0.7)
        if cc == 0:
            tb(s, px + 0.02, cyn(g) - 0.09, 0.40, 0.18, "%.1f" % g, size=7,
               color=MUTED, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    conn(s, cxn(0), cyn(1.0), cxn(len(macs) - 1), cyn(m0 / macs[-1]), DASHC, 1.2, "dash")
    for mid, _nm, _c in MODELS:
        pts = [(k, CYC[(plat, npu, mid, m)] / CYC[(plat, npu, mid, m0)])
               for k, m in enumerate(macs)
               if (plat, npu, mid, m) in CYC and (plat, npu, mid, m0) in CYC]
        if not pts:
            continue
        colr, wide = MCOL[mid], mid == HERO
        for a, b in zip(pts, pts[1:]):
            conn(s, cxn(a[0]), cyn(a[1]), cxn(b[0]), cyn(b[1]), colr, 2.2 if wide else 1.5)
        for k, r in pts:
            dot(s, cxn(k), cyn(r), 0.085 if wide else 0.068, colr)
    for k, m in enumerate(macs):
        tb(s, cxn(k) - 0.30, py + PH4 + 0.01, 0.60, 0.18, str(m), size=7, color=MUTED,
           align=PP_ALIGN.CENTER)

tb(s, 0.50, 5.52, 2.44, 0.92, "RNNoise · U85 · TOTAL cycles", size=10.5, bold=True,
   color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
ntable(s, 2.96, 5.52, [1.30, 1.66, 1.66],
       ["MAC", "low 전체 프로파일", "mid 전체 프로파일"],
       [["256", "36,086", "62,086"], ["512", "31,086", "55,086"]],
       header_h=0.30, row_h=0.31, size=11, hsize=9, bold_cells={(0, 1), (1, 2)})
CHIP = [("low 열  ↓  -5,000", GREEN), ("512 행  →  +24,000", RED),
        ("기본 조합 차  +19,000", NAVY)]
cxp = 7.92
for i, (txt, colr) in enumerate(CHIP):
    if i:
        arrow(s, cxp - 0.30, 5.94, 0.24, 0.20, MUTED)
    rect(s, cxp, 5.76, 1.50, 0.56, LIGHT)
    tb(s, cxp, 5.76, 1.50, 0.56, txt, size=9.5, bold=True, color=colr,
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    cxp += 1.86

# =============================================================== 4 · RQ2 개요
s = blank()
head(s, "RQ2 · 개요", "5. 메모리·실행 조건의 영향",
     ["메모리 서비스 조건과 실행 구성에 따라",
      "추론 실행 비용과 MAC 확장 특성은 어떻게 달라지는가?"])
CW, GAP = 3.897, 0.32
XS = [0.50, 0.50 + CW + GAP, 0.50 + 2 * (CW + GAP)]
rect(s, XS[0], 2.72, CW, 0.42, NAVY)
tb(s, XS[0], 2.72, CW, 0.42, "메모리 서비스", size=12.5, bold=True, color=WHITE,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
rect(s, XS[1], 2.72, CW * 2 + GAP, 0.42, NAVY)
tb(s, XS[1], 2.72, CW * 2 + GAP, 0.42, "워크로드와 실행 구성", size=12.5, bold=True,
   color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
for x, n, t, d in ((XS[0], 6, "데이터 공급", "지연 · 동시성 · 대역폭"),
                   (XS[1], 7, "실행 구조", "형상 · block · 비용"),
                   (XS[2], 8, "데이터 배치", "접근 경로 · 전송 · 비용")):
    card(s, x, 3.36, CW, 1.98, n, t, [d])

# =============================================================== 5 · 데이터 공급
s = blank()
head(s, "RQ2 · 메모리 서비스", "6. 데이터 공급 조건은 실행 비용을 어떻게 바꾸는가?",
     ["U85에서는 요청 동시성이 읽기 지연 페널티를 줄였고,",
      "U55에서는 대역폭 완화 후 지연 개선 효과가 커졌다."])

LX, LW = 0.50, 7.10
tb(s, LX, 2.24, LW, 0.26, "RNNoise · U85", size=11.5, bold=True, color=NAVY)
bx, by, bw, bh = LX, 2.58, LW, 3.80
rect(s, bx, by, bw, bh, PALE)
ix, iw = bx + 0.80, bw - 1.08
iy, ih = by + 0.34, bh - 0.94
MAXR = [1, 4, 16, 63]
S256 = [944, 243, 103, 103]   # H13_RESULTS.md 2
S512 = [963, 245, 96, 89]
YL, YH = math.log10(70), math.log10(1200)


def cx_r(v):
    return ix + iw * math.log10(v) / math.log10(63)


def cy_s(v):
    return iy + ih - ih * (math.log10(v) - YL) / (YH - YL)


for g in (100, 300, 1000):
    gy = cy_s(g)
    conn(s, ix - 0.12, gy, ix + iw + 0.12, gy, LINEC, 0.75, "sysDot")
    tb(s, bx + 0.06, gy - 0.10, 0.64, 0.20, fmt(g), size=8.5, color=MUTED,
       align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
for series, colr in ((S256, STEEL), (S512, RED)):
    for a, b in zip(list(zip(MAXR, series)), list(zip(MAXR, series))[1:]):
        conn(s, cx_r(a[0]), cy_s(a[1]), cx_r(b[0]), cy_s(b[1]), colr, 2.2)
    for m, v in zip(MAXR, series):
        dot(s, cx_r(m), cy_s(v), 0.13, colr)
for m in MAXR:
    tb(s, cx_r(m) - 0.35, by + bh - 0.48, 0.70, 0.22, str(m), size=9.5, color=GRAY,
       align=PP_ALIGN.CENTER)
tb(s, bx, by + bh - 0.28, bw, 0.22, "MAXR", size=9.5, bold=True, color=NAVY,
   align=PP_ALIGN.CENTER)
tb(s, bx + 0.14, by + 0.08, 2.60, 0.24, "ΔTOTAL / ΔRead latency", size=9,
   color=MUTED)
tb(s, cx_r(1) - 0.08, cy_s(963) + 0.14, 1.00, 0.24, "963", size=11, bold=True, color=RED)
tb(s, cx_r(63) - 1.06, cy_s(89) - 0.04, 0.96, 0.24, "89", size=11, bold=True, color=RED,
   align=PP_ALIGN.RIGHT)
rect(s, bx + bw - 1.66, by + 0.16, 0.16, 0.08, STEEL)
tb(s, bx + bw - 1.44, by + 0.08, 1.30, 0.22, "256 MAC", size=9, color=GRAY)
rect(s, bx + bw - 1.66, by + 0.42, 0.16, 0.08, RED)
tb(s, bx + bw - 1.44, by + 0.34, 1.30, 0.22, "512 MAC", size=9, color=GRAY)

# amendments/x4/run.log, campaign B (bwcap50 / bwcap200, rlat64 base / rlat16)
RX, RW = 7.95, 4.88
tb(s, RX, 2.24, RW, 0.26, "RNNoise · U55-256 · TOTAL cycles", size=11.5, bold=True,
   color=NAVY)
ntable(s, RX, 2.58, [1.38, 1.22, 1.22, 1.06],
       ["EXT cap", "읽기 지연 64", "읽기 지연 16", "효과"],
       [["50", "105,059", "103,059", "-1.9%"],
        ["200", "77,059", "34,059", "-55.8%"]],
       header_h=0.62, row_h=0.88, size=13, hsize=10)

# =============================================================== 6 · 실행 구조
s = blank()
head(s, "RQ2 · 실행 구조", "7. 형상에 따른 비용 차이는 어느 MAC 구성에서 나타나는가?",
     ["36×1의 추가 비용 19,000 cycles는 256 구성에서 나타났고,",
      "512의 TOTAL은 두 형상에서 같았다."])

tb(s, 0.50, 2.24, 3.85, 0.26, "공간 형상 · H × W = 36", size=11.5, bold=True, color=NAVY)
PIT, CELL = 0.078, 0.072
tb(s, 0.72, 2.56, 1.70, 0.24, "H 6 × W 6", size=10.5, bold=True, color=STEEL)
for r in range(6):
    for c in range(6):
        rect(s, 0.76 + c * PIT, 2.86 + r * PIT, CELL, CELL, STEEL)
tb(s, 2.56, 2.56, 1.70, 0.24, "H 36 × W 1", size=10.5, bold=True, color=RED)
for r in range(36):
    rect(s, 2.60, 2.86 + r * PIT, CELL, CELL, RED)
tb(s, 0.72, 3.52, 1.70, 0.90,
   ["같은 면적 36", "같은 채널 수", "같은 3×3 커널"], size=10, color=GRAY, spacing=1.34)

RX, RW = 4.55, 8.28
tb(s, RX, 2.24, RW, 0.26, "3×3 Conv · U85 · TOTAL cycles", size=11.5, bold=True,
   color=NAVY)
BX, BW_ = RX + 1.62, 5.40
for i, (nm, v, colr) in enumerate((("6×6 · 256 MAC", 31068, STEEL),
                                   ("6×6 · 512 MAC", 29068, STEEL),
                                   ("36×1 · 256 MAC", 50068, RED),
                                   ("36×1 · 512 MAC", 29068, RED))):
    yy = 2.62 + i * 0.42
    tb(s, RX, yy, 1.52, 0.34, nm, size=10, color=GRAY, align=PP_ALIGN.RIGHT,
       anchor=MSO_ANCHOR.MIDDLE)
    rect(s, BX, yy + 0.05, BW_ * v / 50068, 0.24, colr)
    tb(s, BX + BW_ * v / 50068 + 0.10, yy, 1.10, 0.34, fmt(v), size=9.5, color=GRAY,
       anchor=MSO_ANCHOR.MIDDLE)

# H13_RESULTS.md 6, conv3x3 table, "block 256 -> 512" column
tb(s, RX, 4.52, RW, 0.26, "같은 실행의 Vela OFM block (H × W × C)", size=11.5,
   bold=True, color=NAVY)
ntable(s, RX, 4.86, [1.68, 3.30, 3.30],
       ["형상", "256 MAC", "512 MAC"],
       [["6 × 6", "6 × 6 × 48", "6 × 6 × 64"],
        ["36 × 1", "36 × 2 × 16", "36 × 2 × 48"]],
       header_h=0.34, row_h=0.40, size=11, hsize=9.5, bold_cells={(1, 1)})
# =============================================================== 7 · 데이터 배치
s = blank()
head(s, "RQ2 · 데이터 배치", "8. 데이터 배치는 어떤 이동과 비용을 바꾸는가?",
     ["Sram_Only와 Dedicated는 집계 전송량이 같지만,",
      "접근 경로와 실행 비용은 달랐다."],
     "대표 레이어 = Wav2Letter op 15 (7-tap 250→250 Conv2D) · U85-512 · 세 배치 모두 출력 바이트 동일 · "
     "OFM block·ublock 동일")

tb(s, 0.50, 2.24, 4.80, 0.26, "가중치와 arena가 놓이는 곳", size=11.5, bold=True, color=NAVY)
BOXW, BOXH = 1.16, 0.46
COLX = [0.62, 2.28, 3.94]
MODES = [
    ("Sram_Only", [False, True, True], ["", "가중치 + arena", ""], [(1, 2)]),
    ("Shared_Sram", [True, True, True], ["가중치", "staging + arena", ""], [(0, 1), (1, 2)]),
    ("Dedicated_Sram", [True, False, True], ["가중치 + arena", "", ""], [(0, 2)]),
]
for mi, (nm, live3, notes, links) in enumerate(MODES):
    yy = 2.70 + mi * 1.28
    tb(s, 0.50, yy, 2.40, 0.24, nm, size=10.5, bold=True, color=NAVY)
    for c, (lbl, on) in enumerate(zip(("DRAM / EXT", "SRAM", "NPU"), live3)):
        bxx = COLX[c]
        rect(s, bxx, yy + 0.30, BOXW, BOXH, NAVY if on else RGBColor(0xF1, 0xF3, 0xF5))
        tb(s, bxx, yy + 0.30, BOXW, BOXH, lbl, size=9, bold=True,
           color=WHITE if on else MUTED, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        if notes[c]:
            tb(s, bxx - 0.14, yy + 0.78, BOXW + 0.28, 0.22, notes[c], size=8,
               color=GRAY, align=PP_ALIGN.CENTER)
    for a, b in links:
        x1, x2 = COLX[a] + BOXW, COLX[b]
        if b - a == 1:
            arrow(s, x1 + 0.10, yy + 0.42, x2 - x1 - 0.20, 0.22, NAVY)
        else:
            conn(s, x1 + 0.06, yy + 0.66, x2 - 0.10, yy + 0.66, NAVY, 2.0)
            arrow(s, x2 - 0.24, yy + 0.55, 0.22, 0.22, NAVY)

# H13_RESULTS.md 7, 512 MAC rows
RX, RW = 5.60, 7.23
tb(s, RX, 2.24, RW, 0.26, "대표 레이어 · U85-512 · TOTAL cycles  (Shared_Sram 기준)",
   size=11.5, bold=True, color=NAVY)
BX, BW_ = RX + 1.62, 4.10
for i, (nm, v, delta, colr) in enumerate((("Sram_Only", 134068, "-10.1%", GREEN),
                                          ("Shared_Sram", 149068, "기준", NAVY),
                                          ("Dedicated_Sram", 167068, "+12.1%", RED))):
    yy = 2.62 + i * 0.50
    tb(s, RX, yy, 1.54, 0.40, nm, size=10, color=GRAY, align=PP_ALIGN.RIGHT,
       anchor=MSO_ANCHOR.MIDDLE)
    rect(s, BX, yy + 0.06, BW_ * v / 167068, 0.28, colr)
    tb(s, BX + BW_ * v / 167068 + 0.10, yy, 1.50, 0.40, fmt(v) + "   " + delta,
       size=9.5, bold=True, color=colr, anchor=MSO_ANCHOR.MIDDLE)
ntable(s, RX, 4.32, [1.86, 2.42, 2.42],
       ["배치", "EXT rd / wr beat", "SRAM rd / wr beat"],
       [["Sram_Only", "0 / 0", "56,343 / 4,377"],
        ["Shared_Sram", "17,260 / 0", "61,820 / 21,586"],
        ["Dedicated_Sram", "56,343 / 4,377", "0 / 0"]],
       header_h=0.38, row_h=0.38, size=10, hsize=9.5,
       bold_cells={(0, 2), (2, 1)})
tb(s, RX, 5.96, RW, 0.30,
   "Sram_Only의 SRAM R/W와 Dedicated의 EXT R/W 집계가 일치한다.",
   size=10, color=NAVY)

prs.save(OUT)
print("wrote", OUT, "slides:", len(prs.slides._sldIdLst))
