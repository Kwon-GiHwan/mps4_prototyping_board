#!/usr/bin/env python3
"""Paper material from frozen results:
  x3_validation   — X3 amendment C measurement-validation raw data (kws/ad B0, B1, G_V/G_0/G_R) + table figure
  fig3            — Stage 6C F2 C8/C16: Vela Op Cycles vs FI101 NPU_ACTIVE normalised to C8 = 1, detail table
  model_fidelity  — Stage 6F-0 seven-model Vela fidelity (cycles_total official), Markdown for a Notion toggle

  python3 fig_tables_x3_f2_fidelity.py <out root>        (needs matplotlib)
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fig1_stage6c as F1  # noqa: E402

plt = F1.plt
RES = F1.REPO / "results"
X3_COND = "Stage 6E-X3 Amendment C, image f0baf8c, TA profile 1 (EXT RLATENCY 500), placement 0, pass A 측정 RUN 중앙값"
C6_COND = "Stage 6C, image 14077be, TA profile 1 (EXT RLATENCY 500), placement 0, 측정 RUN 중앙값"
BEAT_BYTES = 16          # 6C README: 23,040 beats = 368,640 B
EV = {"35": "NPU_ACTIVE", "48": "MAC_ACTIVE", "51": "MAC_DPU_ACTIVE", "64": "AO_ACTIVE", "80": "WD_ACTIVE"}
# predictions comparable to an isolated operator (contract: only those groups)
PRED = {("kws_micronet_m", "G_V"): (11700.0, "H1-UC (6B 단독 형상 검증 규칙)"),
        ("kws_micronet_m", "G_0"): (26090.0, "6C F5 단독 측정 (같은 형상·매핑)"),
        ("ad_medium_int8", "G_V"): (60480.0, "H1-UC (6B 단독 형상 검증 규칙)")}


def table_png(cells, cols, title, note, path, width=11.5):
    fig, ax = plt.subplots(figsize=(width, 0.3 * (len(cells) + 1) + 0.9))
    ax.axis("off")
    t = ax.table(cellText=cells, colLabels=cols, cellLoc="center", bbox=[0, 0, 1, 1])
    t.auto_set_font_size(False)
    t.set_fontsize(8)
    t.auto_set_column_width(list(range(len(cols))))
    for (i, _), c in t.get_celld().items():
        c.set_edgecolor(F1.GRID)
        c.set_facecolor("#efeeea" if i == 0 else F1.SURF)
    ax.set_title(title, loc="left", fontsize=11, color=F1.INK)
    fig.text(0.01, 0.01, note, fontsize=7, color=F1.INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def x3_validation(out: pathlib.Path) -> None:
    s = json.loads((RES / "fi101_stage6ex3/stage6ex3_summary.json").read_text())
    rows = []
    for m, tag in (("kws_micronet_m", "kws"), ("ad_medium_int8", "ad")):
        val = {c: {e: s["results"][f"x3_{tag}_{c}"]["stats"]["1"][e][0] for e in EV}
               for c in ("B0", "B1", "B2", "B3", "B4")}
        rng = {c: s["results"][f"x3_{tag}_{c}"]["stats"]["1"]["35"][1] for c in val}
        boot = {"kws_micronet_m": dict(B0=487, B1=488, B2=497, B3=498, B4=499),
                "ad_medium_int8": dict(B0=500, B1=501, B2=502, B3=503, B4=504)}[m]
        names = dict(B0="원본 B0 (비직렬, 전체)", B1="직렬 B1 (전체)", B2="G_V 창 (직렬)", B3="G_0 창 (직렬)", B4="G_R 창 (직렬)")
        for c in ("B0", "B1", "B2", "B3", "B4"):
            g = {"B2": "G_V", "B3": "G_0", "B4": "G_R"}.get(c)
            p = PRED.get((m, g)) if g else None
            rows.append(dict(model=m, row=names[c], boot=boot[c], **{EV[e]: val[c][e] for e in EV},
                             npu_range=rng[c], prediction_mac=p[0] if p else "", prediction_source=p[1] if p else "",
                             mac_error=(val[c]["48"] - p[0]) if p else "",
                             mac_error_rel=((val[c]["48"] - p[0]) / p[0]) if p else "",
                             note="NPU_ACTIVE는 직렬 실행 조건의 그룹 창 값" if g else ""))
        gs = {e: sum(val[c][e] for c in ("B2", "B3", "B4")) for e in EV}
        rows.append(dict(model=m, row="그룹 합 (G_V+G_0+G_R)", boot="", **{EV[e]: gs[e] for e in EV}, npu_range="",
                         prediction_mac="", prediction_source="", mac_error="", mac_error_rel="", note=""))
        rows.append(dict(model=m, row="그룹 합 - 직렬 B1 (상대)", boot="",
                         **{EV[e]: f"{gs[e] - val['B1'][e]:+,.1f} ({(gs[e] - val['B1'][e]) / val['B1'][e]:+.2%})" for e in EV},
                         npu_range="", prediction_mac="", prediction_source="", mac_error="", mac_error_rel="",
                         note="분모 = 직렬 B1"))
        d = val["B1"]["35"] - val["B0"]["35"]
        rows.append(dict(model=m, row="직렬화 증가 (B1 - B0)", boot="", NPU_ACTIVE=f"{d:+,.1f} ({d / val['B0']['35']:+.1%})",
                         MAC_ACTIVE=f"{val['B1']['48'] - val['B0']['48']:+,.0f}",
                         MAC_DPU_ACTIVE=f"{val['B1']['51'] - val['B0']['51']:+,.0f}",
                         AO_ACTIVE=f"{val['B1']['64'] - val['B0']['64']:+,.1f}",
                         WD_ACTIVE=f"{val['B1']['80'] - val['B0']['80']:+,.1f}", npu_range="", prediction_mac="",
                         prediction_source="", mac_error="", mac_error_rel="", note="분모 = 원본 B0"))
    with (out / "x3_validation_raw_data.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    fmt = lambda v: f"{v:,.1f}".replace(".0", "") if isinstance(v, float) else str(v)
    cells = [["KWS" if r["model"].startswith("kws") else "AD", r["row"], fmt(r["boot"]), fmt(r["NPU_ACTIVE"]),
              fmt(r["MAC_ACTIVE"]), fmt(r["MAC_DPU_ACTIVE"]), fmt(r["AO_ACTIVE"]), fmt(r["WD_ACTIVE"]),
              fmt(r["prediction_mac"]), (f"{r['mac_error']:+,.0f} ({r['mac_error_rel']:+.1%})" if r["mac_error"] != "" else "")]
             for r in rows]
    table_png(cells, ["모델", "항목", "boot", "NPU_ACTIVE", "MAC_ACTIVE", "MAC_DPU", "AO_ACTIVE", "WD_ACTIVE",
                      "예측 MAC (독립 연산 비교 가능)", "MAC 오차"],
              "X3 계측 검증 Raw Data (KWS·AD)",
              X3_COND + ". 그룹 NPU_ACTIVE는 직렬 실행 조건의 값이며 원본 실행의 연산별 시간이 아니다. "
              "예측은 독립 연산과 비교 가능한 그룹에만 둔다(AD G_0 외삽, G_R은 제외).",
              out / "x3_validation_table.png", width=13)


def fig3(out: pathlib.Path) -> None:
    s = json.loads((RES / "fi101_stage6c/stage6c_summary.json").read_text())
    keys = (("C 8 (대표, yolo op3)", "s6c_f2_rep"), ("C 16 (통제)", "s6c_f2_c16"))
    rows = []
    for label, k in keys:
        r, v = s["results"][k], s["shapes"][k]["vela"]
        m, t = r["metrics"], r["traffic"]
        terms = {"NPU": v["npu_cycles"], "SRAM": v["sram_ac"], "DRAM": v["dram_ac"]}
        rows.append(dict(shape=label, key=k, vela_npu_cycles=v["npu_cycles"], vela_mac_cycles=v["mac_cycles"],
                         vela_sram_cycles=v["sram_ac"], vela_dram_cycles=v["dram_ac"], vela_op_cycles=v["op_cycles"],
                         vela_dominant_term=max(terms, key=terms.get), npu_active=m["npu_active"],
                         npu_active_range=m["npu_active_range"], mac_active=m["mac_active"],
                         mac_dpu_active=m["mac_dpu_active"], ao_active=m["ao_active"], wd_active=m["wd_active"],
                         wd_stalled=m["wd_stalled"], sram_rd_bytes=t["sram_rd_beats"] * BEAT_BYTES,
                         sram_wr_bytes=t["sram_wr_beats"] * BEAT_BYTES, ext_rd_bytes=t["ext_rd_beats"] * BEAT_BYTES,
                         ext_wr_bytes=t["ext_wr_beats"] * BEAT_BYTES, sram_rd_trans=t["sram_rd_trans"],
                         ext_rd_trans=t["ext_rd_trans"], ext0_rd_trans=t["ext0_rd_trans"], ext0_rd_beats=t["ext0_rd_beats"],
                         ext1_rd_trans=t["ext1_rd_trans"], ext1_rd_beats=t["ext1_rd_beats"],
                         ext_rd_req_stalled=t["ext_rd_req_stalled"], condition=C6_COND))
    with (out / "fig3_f2_detail.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    v0, b0 = rows[0]["vela_op_cycles"], rows[0]["npu_active"]
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    w = 0.34
    for i, r in enumerate(rows):
        for x, val, raw, col, lab in ((i - w / 2, r["vela_op_cycles"] / v0, r["vela_op_cycles"], F1.BLUE, "Vela 예상 Op cycles"),
                                      (i + w / 2, r["npu_active"] / b0, r["npu_active"], F1.ORANGE, "FI101 NPU_ACTIVE")):
            ax.bar(x, val, w, color=col, edgecolor=F1.SURF, linewidth=2, label=lab if i == 0 else None)
            ax.text(x, val + 0.03, f"{val:.2f}\n({raw:,.0f} cycles)", ha="center", va="bottom", fontsize=8, color=F1.INK)
    ax.axhline(1, color=F1.INK2, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.set_xticks([0, 1], [r["shape"] for r in rows])
    ax.set_ylim(0, 2.15)
    ax.set_ylabel("C 8 = 1.00 로 정규화")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_title("그림 3. F2 Depthwise 3×3: 채널 8 → 16의 Vela 예상과 FI101 실측", loc="left", fontsize=11, color=F1.INK)
    fig.text(0.01, 0.01, C6_COND + ".\nVela 값은 컴파일러의 비용 추정이며 보드 실측과 별개의 값이다. "
             "차이의 원인 후보(예: C 8 NHWC의 DRAM burst 비용 추정)는 검증되지 않았다.", fontsize=6.8, color=F1.INK2)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out / "fig3_f2_vela_vs_board.png", dpi=200)
    plt.close(fig)


def model_fidelity(out: pathlib.Path) -> None:
    s = json.loads((RES / "fi101_stage6f0/stage6f0_summary.json").read_text())["models"]
    name = {"kws_micronet_m": "KWS", "ad_medium_int8": "AD", "mobilenet_v2_1.0_224_INT8": "MobileNetV2",
            "vww4_128_128_INT8": "VWW4", "rnnoise_INT8": "RNNoise", "yolo-fastest_192_face_v4": "YOLO-Fastest",
            "wav2letter_pruned_int8": "Wav2Letter"}
    rows = []
    for m, v in s.items():
        ve = v["vela"]
        rows.append(dict(model=name[m], board_npu_active=v["npu_active"], npu_range=v["npu_range"],
                         vela_cycles_npu=ve["cycles_npu"], vela_cycles_total=ve["cycles_total"],
                         board_over_cycles_total=ve["board_over_total"], rel_error_total=ve["rel_error"],
                         verdict_total=ve["cls_total"]))
    with (out / "model_fidelity.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    md = ["# 모델별 Vela Fidelity (Stage 6F-0)", "",
          "- 출처: Stage 6F-0 (`results/fi101_stage6f0/stage6f0_summary.json`). Board = driver runner `driver_m7`, "
          "TA profile 1 (EXT RLATENCY 500), pass A 측정 RUN 중앙값. Vela 5.0.0, `Ethos_U85_SYS_DRAM_Mid_1024`.",
          "- **공식 비교 기준은 cycles_total**(= Σ per-layer Op Cycles = Σ max(NPU, SRAM, DRAM))이다. "
          "cycles_npu(= Σ NPU 항)는 값만 함께 적고, 기존 cycles_npu 기반 비율은 이 표에서 쓰지 않는다.",
          "- 상대 오차 = (Board − cycles_total) / cycles_total. 판정: ratio < 0.9 OVER(과대예측), > 1.1 UNDER(과소예측), "
          "그 밖 AGREE. 경계 0.9·1.1 × cycles_total이 Board ± range 안이면 INSUFFICIENT_EVIDENCE.", "",
          "| 모델 | Board NPU_ACTIVE (range) | Vela cycles_npu | Vela cycles_total | Board / cycles_total | 상대 오차 | 판정 (cycles_total) |",
          "|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        md.append(f"| {r['model']} | {r['board_npu_active']:,.1f} ({r['npu_range']:,}) | {r['vela_cycles_npu']:,.0f} | "
                  f"{r['vela_cycles_total']:,.0f} | {r['board_over_cycles_total']:.3f} | {r['rel_error_total']:+.1%} | "
                  f"{r['verdict_total']} |")
    (out / "model_fidelity.md").write_text("\n".join(md) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = pathlib.Path(argv[1])
    F1.style()
    for sub, fn in (("04_add_x3_validation", x3_validation), ("05_fig3", fig3), ("06_add_model_fidelity", model_fidelity)):
        (root / sub).mkdir(parents=True, exist_ok=True)
        fn(root / sub)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
