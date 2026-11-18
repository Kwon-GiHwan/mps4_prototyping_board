#!/usr/bin/env python3
"""Figure 2: existing predictions vs X3 in-model group MAC_ACTIVE (kws/ad G_V H1-UC, kws G_0 6C F5, ad G_0 R_PK3
extrapolation), plus a raw-data CSV that separates in-model group measurement from isolated-operator evidence.

Inputs: results/fi101_stage6f0/stage6f0_summary.json (groups), results/fi101_stage6d/operator_levels.csv (per-op
prediction and level), results/fi101_stage6m/h1uc_operators.csv (isolated reference shape of each H1-UC operator),
results/fi101_stage6c/stage6c_summary.json (F5), results/fi101_stage6ex3/stage6ex3_summary.json (group boots).

  python3 fig_add_prediction_check.py <out dir>        (needs matplotlib)
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fig1_stage6c as F1  # noqa: E402  (style, colours, font)

plt = F1.plt
REPO = F1.REPO
RES = REPO / "results"
X3_COND = "X3 직렬 그룹 창(KERNEL_WAIT n=0 + PMU_MASK), image f0baf8c, TA profile 1 (EXT RLATENCY 500), placement 0"
F5_COND = "Stage 6C 단독 연산(graph IO DDR), image 14077be, TA profile 1 (EXT RLATENCY 500), placement 0, boot 476"
H1_COND = "Stage 6B 계열 단독 형상 보드 측정으로 검증한 H1-UC 규칙, TA profile 1"
X3_BOOT = {("kws_micronet_m", "G_V"): 497, ("kws_micronet_m", "G_0"): 498, ("ad_medium_int8", "G_V"): 502,
           ("ad_medium_int8", "G_0"): 503}
CASES = [  # label, model, group, prediction kind
    ("KWS G_V\n(op 2·4·6)", "kws_micronet_m", "G_V", "H1-UC (검증된 규칙)"),
    ("AD G_V\n(op 2·4·6·8)", "ad_medium_int8", "G_V", "H1-UC (검증된 규칙)"),
    ("KWS G_0\n(op0, Cin 1 10×4)", "kws_micronet_m", "G_0", "6C F5 단독 측정"),
    ("AD G_0\n(op0, Cin 1 3×3)", "ad_medium_int8", "G_0", "R_PK3 외삽 (Cin 1→16)"),
]


def load():
    s6f = json.loads((RES / "fi101_stage6f0/stage6f0_summary.json").read_text())
    ops = {(r["model"], int(r["op"])): r for r in csv.DictReader(open(RES / "fi101_stage6d/operator_levels.csv"))}
    h1 = {(r["model"], int(r["tflite_op_index"])): r for r in csv.DictReader(open(RES / "fi101_stage6m/h1uc_operators.csv"))}
    f5 = json.loads((RES / "fi101_stage6c/stage6c_summary.json").read_text())["results"]["s6c_f5_rep"]["metrics"]
    return s6f, ops, h1, f5


def raw_rows(s6f, ops, h1, f5) -> list[dict]:
    out = []
    for label, m, g, kind in CASES:
        gi = s6f["groups"][m][g]
        for op in gi["ops"]:
            o, h = ops[(m, op)], h1.get((m, op), {})
            p = float(o["p"] or o["p_ext"])
            if o["level"] == "EXACT_VALIDATED":
                iso_ref = f"6B 단독 형상 {h['measured_group']} (모델 연산과 다른 차원: {h['b_failed_dims']})"
                iso_val, iso_cond = "", H1_COND
            elif o["level"] == "CONFIGURATION_MATCHED":
                iso_ref, iso_val, iso_cond = "6C F5 대표 (같은 형상·매핑, graph IO만 DDR)", f5["mac_active"], F5_COND
            else:
                iso_ref, iso_val, iso_cond = "없음 (검증 범위 밖 규칙 연장: Cin 16–64 → Cin 1)", "", "측정 없음"
            out.append(dict(
                row="operator", model=m, group=g, tflite_op=op, family=o["family"], kernel=o["kernel"], cin=o["cin"],
                cout=o["cout"], ofm=o["ofm"], n_mac_tflite=int(o["n_mac"]), level_6d=o["level"], prediction_kind=kind,
                predicted_mac_active=p, isolated_reference=iso_ref, isolated_mac_active=iso_val,
                isolated_condition=iso_cond,
                in_model_mac_active=gi["mac"] if len(gi["ops"]) == 1 else "(그룹 단위로만 측정)", in_model_npu_active="",
                in_model_condition="", x3_boot="", predicted_over_measured="", group_status=""))
        out.append(dict(
            row="group (in-model)", model=m, group=g, tflite_op=" ".join(map(str, gi["ops"])), family="", kernel="",
            cin="", cout="", ofm="", n_mac_tflite=sum(r["n_mac_tflite"] for r in out if r["row"] == "operator"
                                                     and r["model"] == m and r["group"] == g),
            level_6d="", prediction_kind=kind, predicted_mac_active=gi["predicted"], isolated_reference="",
            isolated_mac_active="", isolated_condition="", in_model_mac_active=gi["mac"],
            in_model_npu_active=f"{gi['npu']} (range {gi['npu_range']})", in_model_condition=X3_COND,
            x3_boot=X3_BOOT[(m, g)], predicted_over_measured=gi["p_over_m"], group_status=gi["status"]))
    return out


def figure(s6f, out: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    w = 0.36
    for i, (label, m, g, kind) in enumerate(CASES):
        gi = s6f["groups"][m][g]
        ext = "외삽" in kind
        ax.bar(i - w / 2, gi["predicted"], w, color=F1.BLUE, edgecolor=F1.SURF, linewidth=2,
               hatch="////" if ext else None, label="기존 예측" if i == 0 else None)
        ax.bar(i + w / 2, gi["mac"], w, color=F1.ORANGE, edgecolor=F1.SURF, linewidth=2,
               label="X3 모델 내부 그룹 실측" if i == 0 else None)
        for x, v in ((i - w / 2, gi["predicted"]), (i + w / 2, gi["mac"])):
            ax.text(x, v + 700, f"{v:,.0f}", ha="center", va="bottom", fontsize=8.5, color=F1.INK)
        r = gi["p_over_m"]
        note = "일치 (예측/실측 1.000)" if gi["status"] == "PREDICTION_AGREES" else f"예측/실측 {r:.2f}× (외삽 반례)"
        ax.text(i, max(gi["predicted"], gi["mac"]) + 6500, note, ha="center", va="bottom", fontsize=8.5, color=F1.INK2)
    ax.set_xticks(range(len(CASES)), [f"{c[0]}\n{c[3]}" for c in CASES], fontsize=8.5)
    ax.set_ylim(0, 76000)
    ax.set_ylabel("MAC_ACTIVE (cycles)")
    ax.yaxis.set_major_formatter(F1.matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_title("추가 그림. 기존 예측과 모델 내부 그룹 MAC_ACTIVE (X3)", loc="left", fontsize=11, color=F1.INK)
    fig.text(0.01, 0.01, "실측: " + X3_COND + ".\n예측값은 X3 측정 전에 고정된 값(H1-UC: 6B 단독 형상 검증, F5: 6C 단독 측정). 빗금 = 검증 범위 밖 외삽(반례).",
             fontsize=7, color=F1.INK2)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "add_prediction_vs_inmodel.png", dpi=200)
    plt.close(fig)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    s6f, ops, h1, f5 = load()
    rows = raw_rows(s6f, ops, h1, f5)
    with (out / "add_prediction_raw_data.csv").open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    F1.style()
    figure(s6f, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
