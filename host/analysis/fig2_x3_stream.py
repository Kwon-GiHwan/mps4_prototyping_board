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
SEQ_ROWS = [("B0", "① 원본 실행\n(완료 대기 없음)\n전체 계수"), ("B1", "② 직렬 실행\n(커널마다 완료 대기)\n전체 계수"), ("B2", "③ 직렬 실행\n1×1 Conv만 계수"),
            ("B3", "④ 직렬 실행\n첫 Conv만 계수"), ("B4", "⑤ 직렬 실행\n나머지 연산만 계수")]
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
    x3 = __import__("json").loads((REPO / "results/fi101_stage6ex3/stage6ex3_summary.json").read_text())["results"]
    npu = {c: x3[f"x3_{tag}_{c}"]["stats"]["1"]["35"] for c, _ in SEQ_ROWS}      # (median, range), pass A
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(15.5, 6.6), gridspec_kw=dict(width_ratios=[4.8, 1.1]))
    ax.grid(False)
    log = []
    for r, (cond, desc) in enumerate(SEQ_ROWS):
        y = r * 1.45
        if r:                                        # each row is a separate board run
            ax.plot([-3.2, 99], [y - 0.72] * 2, color=F1.GRID, linewidth=0.8, clip_on=False)
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
        ax.text(-0.25, y, f"{desc}\n(별도 실행, boot {BOOTS[model][cond]})", ha="right", va="center", fontsize=8,
                color=F1.INK)
    total = n * bw + (n + 1) * gap
    ax.set_xlim(-0.1, total + 0.1)
    # measured NPU_ACTIVE per run (right panel, same rows)
    vmax = max(v[0] for v in npu.values())
    for r, (cond, _) in enumerate(SEQ_ROWS):
        y = r * 1.45
        v, rg = npu[cond]
        bx.barh(y, v, height=0.62, color="#8d8c86" if cond in ("B0", "B1") else "#c9c8c2", edgecolor=F1.SURF)
        txt = f"{v:,.1f}" if v % 1 else f"{v:,.0f}"
        if cond == "B1":
            d = v - npu["B0"][0]
            txt += f"\n(①보다 +{d:,.0f}, +{d / npu['B0'][0]:.1%})"
        bx.text(v + vmax * 0.03, y, txt, va="center", ha="left", fontsize=7.5, color=F1.INK)
    bx.set_ylim(len(SEQ_ROWS) * 1.45 - 0.75, -0.75)
    bx.set_xlim(0, vmax * 2.45)
    bx.set_yticks([])
    bx.set_xticks([])
    bx.grid(False)
    for sp in ("left", "bottom"):
        bx.spines[sp].set_visible(False)
    bx.text(0, -0.68, "측정 NPU_ACTIVE (cycles)\n③–⑤는 직렬 조건의 그룹 구간 값", ha="left", va="bottom", fontsize=7.5,
            color=F1.INK2)
    ax.set_ylim(len(SEQ_ROWS) * 1.45 - 0.75, -0.75)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.annotate("", xy=(total, -0.62), xytext=(0, -0.62),
                arrowprops=dict(arrowstyle="->", color=F1.INK2, linewidth=0.9))
    ax.text(total / 2, -0.68, "한 실행 안의 커널 발행 순서 (시간 축 아님, 상자 폭은 실행시간과 무관)", ha="center", va="bottom", fontsize=7.5,
            color=F1.INK2)
    leg = [Rectangle((0, 0), 1, 1, facecolor=GCOL[g], edgecolor=GCOL[g]) for g in ("G_0", "G_V", "G_R")]
    leg += [Rectangle((0, 0), 1, 1, facecolor="#ecebe7", edgecolor="#c9c8c2"),
            plt.Line2D([0], [0], color=F1.INK, linewidth=1.1)]
    fig.legend(leg, [GNAME["G_0"], GNAME["G_V"], GNAME["G_R"], "측정에서 제외된 커널", "완료 대기 (앞 커널이 끝난 뒤 시작)"],
              frameon=False, ncol=5, fontsize=8, loc="upper left", bbox_to_anchor=(0.01, 0.935))
    name = {"kws_micronet_m": "KWS (micronet-m)", "ad_medium_int8": "AD (medium)"}[model]
    fig.text(0.01, 0.975, f"그림 2-{'A' if tag == 'kws' else 'B'}. {name}: 원본·직렬 실행의 커널 순서와 그룹별 PMU 측정 구간",
             ha="left", va="top", fontsize=11, color=F1.INK)
    fig.text(0.01, 0.015,
             "각 행은 같은 모델을 따로 실행한 별도 측정이다(동시에 도는 병렬 경로가 아니다). ③–⑤는 ②와 같은 명령 스트림이며 PMU를 켜는 커널만 다르다. "
             "①은 완료 대기가 없어 하드웨어가 다음 커널의 준비를 앞 커널 실행과 겹칠 수 있다. 겹침 자체는 측정하지 않았고, "
             "①·② 차이는 오른쪽의 총 NPU_ACTIVE로만 보인다(이 증가에는 완료 대기 자체의 비용도 섞여 있다).\n"
             "각주: 완료 대기는 커널 연산의 완료만 보장하며 메모리 간 DMA 전송의 완료는 보장하지 않는다. 따라서 그룹별 메모리 트래픽은 "
             "시간 귀속에 쓰지 않는다. 조건: TA profile 1 (EXT RLATENCY 500), placement 0.",
             fontsize=7, color=F1.INK2)
    fig.subplots_adjust(left=0.11, right=0.995, top=0.85, bottom=0.12, wspace=0.02)
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
