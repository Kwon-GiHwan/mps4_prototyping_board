#!/usr/bin/env python3
"""Figure 2: original (B0) vs serialized (B1) command streams of Stage 6E-X3 amendment C and the group measurement
windows (B2 G_V, B3 G_0, B4 G_R): KERNEL_WAIT n=0 completion barriers, PMU_MASK on/off, kernel groups.

Drawn from the measured DRWL command streams themselves (evidence/stage6ex3/workloads/x3_*.drwl), in command order —
the x axis is the order of commands, not time.

  python3 fig2_x3_stream.py <out dir>        (needs matplotlib)
"""
from __future__ import annotations

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import fig1_stage6c as F1  # noqa: E402
import cms  # noqa: E402
import drwl  # noqa: E402
import tflite_cop1 as T  # noqa: E402
import stage6ex3_workloads as W  # noqa: E402

plt = F1.plt
from matplotlib.patches import Rectangle  # noqa: E402

REPO = F1.REPO
WL = REPO / "evidence/stage6ex3/workloads"
OPMAP = REPO / "results/fi101_stage2_groups/vela_op_map"
KNAME = {2: "CONV", 3: "DW", 5: "POOL", 6: "ELEM", 7: "RESIZE"}
GCOL = {"G_V": F1.BLUE, "G_0": F1.ORANGE, "G_R": "#1baf7a"}     # validated categorical slots 1-3 (labels on boxes)
WIDTH = {"K": 1.7, "DMA_START": 0.75, "DMA_WAIT": 0.75, "KW": 0.4, "MASK": 0.55, "STOP": 0.7}
ROWS = [("B0", "원본 (PMU 전체 창, 장벽 없음)"), ("B1", "직렬 전체 (모든 커널 창 ON)"),
        ("B2", "G_V 창"), ("B3", "G_0 창"), ("B4", "G_R 창")]
BOOTS = {"kws_micronet_m": dict(B0=487, B1=488, B2=497, B3=498, B4=499),
         "ad_medium_int8": dict(B0=500, B1=501, B2=502, B3=503, B4=504)}


def stream(key: str) -> bytes:
    blob = (WL / f"{key}.drwl").read_bytes()
    h = drwl.parse(blob)
    return W._cms_of(T.cop1(blob[h["model_off"]:h["model_off"] + h["model_len"]]))


def commands(key: str) -> list[dict]:
    """Ordered command list (only control commands; register settings omitted)."""
    out, k = [], 0
    for _, w, c, op in cms.instructions(stream(key)):
        if c != 0:
            continue
        if op in KNAME:
            out.append(dict(t="K", kind=KNAME[op], k=k)); k += 1
        elif op == 16:
            out.append(dict(t="DMA_START"))
        elif op == 17:
            out.append(dict(t="DMA_WAIT"))
        elif op == 18:
            out.append(dict(t="KW", n=w >> 16))
        elif op == 19:
            out.append(dict(t="MASK", on=(w >> 16) & 1))
        elif op == 0:
            out.append(dict(t="STOP"))
    return out


def kernel_tflite(model: str) -> dict[int, int]:
    with (OPMAP / f"{model}.op_map.csv").open(newline="") as f:
        return {int(r["index"]): int(r["source_id"]) - 1 for r in csv.DictReader(f)}


def x_positions(cmds: list[dict]) -> list[float]:
    xs, x = [], 0.0
    for c in cmds:
        xs.append(x)
        x += WIDTH[c["t"]] + 0.12
    return xs


GNAME = {"G_V": "1×1 Conv (예측 검증 대상)", "G_0": "첫 Conv", "G_R": "나머지 연산"}
SEQ_ROWS = [("B0", "원본 실행"), ("B1", "직렬 실행\n(커널마다 완료 대기)"), ("B2", "측정 구간:\n1×1 Conv"),
            ("B3", "측정 구간:\n첫 Conv"), ("B4", "측정 구간:\n나머지 연산")]
OPS6D = REPO / "results/fi101_stage6d/operator_levels.csv"


def op_labels(model: str) -> dict[int, str]:
    out = {}
    for r in csv.DictReader(open(OPS6D)):
        if r["model"] != model or not r["kernel"]:
            continue
        t = {"CONV_2D": "Conv", "DEPTHWISE_CONV_2D": "DW", "AVERAGE_POOL_2D": "Pool"}.get(r["tflite_op"], r["tflite_op"])
        k = r["kernel"].replace("x", "×")
        st = "" if r["stride"] == "1x1" else " s2"
        out[int(r["op"])] = f"{t}\n{k}{st}" if t != "Pool" else "Pool"
    return out


def counted(cmds: list[dict]) -> dict[int, int]:
    """kernel -> 1 if the PMU window is on when it runs (last PMU_MASK before it)."""
    on, out = 1, {}
    for c in cmds:
        if c["t"] == "MASK":
            on = c["on"]
        elif c["t"] == "K":
            out[c["k"]] = on
    return out


def draw(model: str, tag: str, out: pathlib.Path) -> list[dict]:
    man = __import__("json").loads((WL / W_MAN).read_text())
    g_of = {k: g for g, ks in man[f"x3_{tag}_B2"]["groups"].items() for k in ks}
    ktf = kernel_tflite(model)
    lab = op_labels(model)
    rows = {c: commands(f"x3_{tag}_{c}") for c, _ in SEQ_ROWS}
    order = [c["k"] for c in rows["B1"] if c["t"] == "K"]
    assert order == [c["k"] for c in rows["B0"] if c["t"] == "K"], "kernel order differs B0/B1"
    for c in ("B2", "B3", "B4"):
        assert [x["k"] for x in rows[c] if x["t"] == "K"] == order, c
    split = {}                                     # an operator executed as several kernels -> "(i/n)"
    for k in order:
        split.setdefault(ktf[k], []).append(k)
    n = len(order)
    bw, gap = 1.0, 0.28
    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    ax.grid(False)
    log = []
    for r, (cond, desc) in enumerate(SEQ_ROWS):
        y = r * 1.25
        serial = cond != "B0"
        cnt = counted(rows[cond]) if serial else {k: 1 for k in order}
        x = 0.0
        if serial:                                   # the serial stream also waits before the first kernel
            ax.plot([gap / 2] * 2, [y - 0.5, y + 0.5], color=F1.INK, linewidth=1.1)
            x = gap
        for i, k in enumerate(order):
            g = g_of[k]
            on = cnt[k] == 1
            fc = GCOL[g] if on else "#ecebe7"
            ec = GCOL[g] if on else "#c9c8c2"
            ax.add_patch(Rectangle((x, y - 0.4), bw, 0.8, facecolor=fc, edgecolor=ec, linewidth=1.0))
            parts = split[ktf[k]]
            text = lab[ktf[k]] + (f"\n({parts.index(k) + 1}/{len(parts)})" if len(parts) > 1 else "")
            ax.text(x + bw / 2, y, text, ha="center", va="center", fontsize=6.6,
                    color=F1.SURF if on else F1.INK2)
            log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd="KERNEL", kernel=k,
                            kind=c_kind(rows[cond], k), tflite_op=ktf[k], group=g, counted=int(on)))
            x += bw
            if serial:
                ax.plot([x + gap / 2] * 2, [y - 0.5, y + 0.5], color=F1.INK, linewidth=1.1)
                x += gap
        ax.text(-0.25, y, desc, ha="right", va="center", fontsize=8.5, color=F1.INK)
    total = n * bw + (n + 1) * gap
    ax.set_xlim(-0.1, total + 0.1)
    ax.set_ylim(len(SEQ_ROWS) * 1.25 - 0.55, -0.75)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.annotate("", xy=(total, -0.62), xytext=(0, -0.62),
                arrowprops=dict(arrowstyle="->", color=F1.INK2, linewidth=0.9))
    ax.text(total / 2, -0.68, "실행 순서 (시간 축 아님, 상자 폭은 실행시간과 무관)", ha="center", va="bottom", fontsize=7.5,
            color=F1.INK2)
    leg = [Rectangle((0, 0), 1, 1, facecolor=GCOL[g], edgecolor=GCOL[g]) for g in ("G_0", "G_V", "G_R")]
    leg += [Rectangle((0, 0), 1, 1, facecolor="#ecebe7", edgecolor="#c9c8c2"),
            plt.Line2D([0], [0], color=F1.INK, linewidth=1.1)]
    ax.legend(leg, [GNAME["G_0"], GNAME["G_V"], GNAME["G_R"], "측정에서 제외된 커널", "완료 대기 (앞 커널이 끝난 뒤 시작)"],
              frameon=False, ncol=5, fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.16))
    name = {"kws_micronet_m": "KWS (micronet-m)", "ad_medium_int8": "AD (medium)"}[model]
    ax.set_title(f"그림 2-{'A' if tag == 'kws' else 'B'}. {name}: 원본·직렬 실행의 커널 순서와 그룹별 PMU 측정 구간",
                 loc="left", fontsize=11, color=F1.INK, pad=40)
    fig.text(0.01, 0.015,
             "측정 구간: 해당 그룹의 커널이 실행될 때만 PMU 계수를 켠다. 직렬 실행에서는 각 커널 앞에서 이전 커널의 완료를 기다린다.\n"
             "각주: 완료 대기는 커널 연산의 완료만 보장하며 메모리 간 DMA 전송의 완료는 보장하지 않는다. 따라서 그룹별 메모리 트래픽은 "
             "시간 귀속에 쓰지 않는다. 조건: TA profile 1 (EXT RLATENCY 500), placement 0.",
             fontsize=7, color=F1.INK2)
    fig.subplots_adjust(left=0.11, right=0.995, top=0.82, bottom=0.12)
    fig.savefig(out / f"fig2{'a' if tag == 'kws' else 'b'}_{tag}_command_stream.png", dpi=200)
    plt.close(fig)
    return log


def c_kind(cmds: list[dict], k: int) -> str:
    return next(c["kind"] for c in cmds if c["t"] == "K" and c["k"] == k)


W_MAN = "x3_manifest.json"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    F1.style()
    log = draw("kws_micronet_m", "kws", out) + draw("ad_medium_int8", "ad", out)
    keys = ["model", "cond", "boot", "cmd", "kernel", "kind", "tflite_op", "group", "counted"]
    with (out / "fig2_command_order.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(log)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
