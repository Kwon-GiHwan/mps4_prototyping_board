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


def draw(model: str, tag: str, out: pathlib.Path) -> list[dict]:
    man = __import__("json").loads((WL / W_MAN).read_text())
    groups = man[f"x3_{tag}_B2"]["groups"]
    g_of = {k: g for g, ks in groups.items() for k in ks}
    ktf = kernel_tflite(model)
    rows = {c: commands(f"x3_{tag}_{c}") for c, _ in ROWS}
    ser = rows["B1"]
    for c in ("B2", "B3", "B4"):                                  # same stream as B1 but the mask bits
        assert [(a["t"], a.get("k")) for a in rows[c]] == [(a["t"], a.get("k")) for a in ser], c
    xs = x_positions(ser)
    kx = {c["k"]: x for c, x in zip(ser, xs) if c["t"] == "K"}
    # B0: same kernel columns; its DMA commands are placed in their own order between the kernels
    b0 = rows["B0"]
    b0x, last = [], -1.0
    pend = []
    for c in b0:
        if c["t"] == "K":
            base = kx[c["k"]]
            for i, p in enumerate(reversed(pend)):
                b0x.append((p, base - (i + 1) * (WIDTH["DMA_START"] + 0.12)))
            pend = []
            b0x.append((c, base))
        elif c["t"] == "STOP":
            b0x.append((c, xs[-1]))
        else:
            pend.append(c)
    total = xs[-1] + WIDTH["STOP"]
    fig, ax = plt.subplots(figsize=(max(14, total * 0.33), 5.2))
    ax.grid(False)
    ax.set_xlim(-0.5, total + 0.5)
    ax.set_ylim(-0.6, len(ROWS) - 0.2)
    ax.invert_yaxis()
    log = []
    for r, (cond, desc) in enumerate(ROWS):
        y = r
        items = b0x if cond == "B0" else list(zip(rows[cond], xs))
        mask_on = 1 if cond == "B0" else 0
        for c, x in items:
            t = c["t"]
            if t == "K":
                g = g_of[c["k"]]
                on = mask_on == 1
                fc = GCOL[g] if on else F1.SURF
                ax.add_patch(Rectangle((x, y - 0.32), WIDTH["K"], 0.64, facecolor=fc, edgecolor=GCOL[g], linewidth=1.4))
                ax.text(x + WIDTH["K"] / 2, y, f"k{c['k']} {c['kind']}\nop{ktf[c['k']]} {g}", ha="center", va="center",
                        fontsize=6.2, color=F1.SURF if on else F1.INK)
                log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd="KERNEL", kernel=c["k"],
                                kind=c["kind"], tflite_op=ktf[c["k"]], group=g, counted=int(on)))
            elif t in ("DMA_START", "DMA_WAIT"):
                ax.add_patch(Rectangle((x, y - 0.2), WIDTH[t], 0.4, facecolor="#e9e8e4", edgecolor=F1.INK2, linewidth=0.6))
                ax.text(x + WIDTH[t] / 2, y, "DMA\nstart" if t == "DMA_START" else "DMA\nwait", ha="center",
                        va="center", fontsize=5.2, color=F1.INK2)
                log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd=t))
            elif t == "KW":
                ax.plot([x + 0.2, x + 0.2], [y - 0.42, y + 0.42], color=F1.INK, linewidth=1.6)
                log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd=f"KERNEL_WAIT n={c['n']}"))
            elif t == "MASK":
                mask_on = c["on"]
                ax.text(x + 0.27, y - 0.36, "ON" if c["on"] else "off", ha="center", va="bottom", fontsize=5.6,
                        color=F1.INK if c["on"] else F1.INK2, fontweight="bold" if c["on"] else "normal")
                ax.plot([x + 0.27], [y], marker="v" if c["on"] else "x", color=F1.INK if c["on"] else F1.INK2,
                        markersize=5)
                log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd=f"PMU_MASK {c['on']}"))
            elif t == "STOP":
                ax.text(x + 0.35, y, "STOP", ha="center", va="center", fontsize=6.5, color=F1.INK2)
                log.append(dict(model=model, cond=cond, boot=BOOTS[model][cond], cmd="STOP"))
        ax.text(-0.7, y, f"{cond} (boot {BOOTS[model][cond]})\n{desc}", ha="right", va="center", fontsize=8,
                color=F1.INK)
    ax.set_yticks([])
    ax.set_xticks([])
    for s in ("left", "bottom"):
        ax.spines[s].set_visible(False)
    leg = [Rectangle((0, 0), 1, 1, facecolor=GCOL[g], edgecolor=GCOL[g]) for g in GCOL]
    leg += [Rectangle((0, 0), 1, 1, facecolor=F1.SURF, edgecolor=F1.INK2),
            plt.Line2D([0], [0], color=F1.INK, linewidth=1.6),
            plt.Line2D([0], [0], marker="v", color=F1.INK, linestyle="none")]
    ax.legend(leg, ["G_V 커널 (계수 ON)", "G_0 커널 (계수 ON)", "G_R 커널 (계수 ON)", "계수 off인 커널 (테두리 = 그룹)",
                    "KERNEL_WAIT n=0 (완료 장벽)", "PMU_MASK (ON/off)"], frameon=False, ncol=6, fontsize=7.5,
              loc="upper left", bbox_to_anchor=(0, 1.13))
    name = {"kws_micronet_m": "KWS", "ad_medium_int8": "AD"}[model]
    ax.set_title(f"그림 2-{'A' if tag == 'kws' else 'B'}. {name}: 원본(B0)·직렬(B1) 명령 흐름과 그룹 PMU 측정창(B2–B4)",
                 loc="left", fontsize=11, color=F1.INK, pad=34)
    fig.text(0.01, 0.015,
             "가로축은 실제 DRWL 명령 순서(레지스터 설정 명령 생략)이며 시간이 아니다. 커널 상자 = k(스트림 커널 번호) 종류 / TFLite op·그룹. "
             "B0의 DMA는 B0 스트림의 순서대로 각 커널 앞에 둔다.\n"
             "각주: KERNEL_WAIT n=0은 앞선 커널 연산의 완료만 기다리며 mem2mem DMA의 완료는 보장하지 않는다. 따라서 그룹 창의 SRAM/EXT/AXI 계수는 "
             "시간 귀속 근거로 쓰지 않는다. 조건: image f0baf8c, TA profile 1 (EXT RLATENCY 500), placement 0.",
             fontsize=6.8, color=F1.INK2)
    fig.subplots_adjust(left=0.13, right=0.995, top=0.8, bottom=0.12)
    fig.savefig(out / f"fig2{'a' if tag == 'kws' else 'b'}_{tag}_command_stream.png", dpi=200)
    plt.close(fig)
    return log


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
