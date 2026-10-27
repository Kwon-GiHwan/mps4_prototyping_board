"""Stage 1 figures (default matplotlib style; model colours as in the old 3.3-C figure).
  python3 results/fi101_stage1/plot_stage1.py results/fi101_stage1"""
import csv, sys, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = pathlib.Path(sys.argv[1])
MODELS = [("ad_medium_int8", "ad_medium", "C0"), ("kws_micronet_m", "kws", "C1"),
          ("mobilenet_v2_1.0_224_INT8", "mobilenet", "C2"), ("rnnoise_INT8", "rnnoise", "C3"),
          ("vww4_128_128_INT8", "vww4", "C4"), ("wav2letter_pruned_int8", "wav2letter", "C5"),
          ("yolo-fastest_192_face_v4", "yolo", "C6")]
S1 = {r["model"]: r for r in csv.DictReader(open(D / "stage1.csv"))}
BF = {r["model"]: r for r in csv.DictReader(open(D / "vela_block_fill.csv"))}
NOTE = "FI101 U85-1024, TA profile 1, runner image 2bb04bfa, 8 measured RUNs per set; PROVISIONAL (Stage 0 pending)"


def grouped(ax, metrics, labels, src):
    n = len(MODELS); w = 0.8 / n
    for i, (m, name, c) in enumerate(MODELS):
        vals = [float(src[m][k]) * 100 for k in metrics]
        ax.bar([j + (i - n / 2 + 0.5) * w for j in range(len(metrics))], vals, w, color=c, label=name)
    ax.set_xticks(range(len(metrics)), labels)
    ax.grid(True, axis="y", alpha=0.3)


fig, ax = plt.subplots(figsize=(10, 4.2))
grouped(ax, ["mac_active_ratio", "dpu_active_ratio", "ao_active_ratio", "wd_active_ratio", "wd_stalled_ratio"],
        ["MAC active", "DPU active", "AO active", "WD active", "WD stalled"], S1)
ax.set_ylabel("% of npu_active"); ax.set_title("Stage 1  Unit activity / npu_active (same RUN, pass A)")
ax.legend(fontsize=7, ncol=7, loc="upper center", bbox_to_anchor=(0.5, -0.12))
fig.text(0.01, 0.01, NOTE, fontsize=7, color="0.4"); fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(D / "figures/stage1_unit_activity.png", dpi=150)

merged = {m: {**S1[m], **BF[m]} for m, _, _ in MODELS}
fig, ax = plt.subplots(figsize=(10, 4.2))
grouped(ax, ["peak_mac_eff", "mac_active_cycle_eff", "block_fill_mac_weighted", "ublock_fill_mac_weighted"],
        ["peak MAC eff.\nN_MAC/(1024*active)", "MAC active-cycle eff.\nN_MAC/(1024*mac_active)",
         "Vela OFM block fill\n(MAC-weighted, post hoc)", "Vela ublock fill\n(MAC-weighted, post hoc)"], merged)
ax.set_ylabel("%"); ax.set_title("Stage 1  Throughput efficiency vs Vela block fill")
ax.legend(fontsize=7, ncol=7, loc="upper center", bbox_to_anchor=(0.5, -0.2))
fig.text(0.01, 0.01, NOTE, fontsize=7, color="0.4"); fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(D / "figures/stage1_efficiency_block_fill.png", dpi=150)

fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
x = range(len(MODELS))
for i, (m, name, c) in enumerate(MODELS):
    axs[0].bar(i - 0.2, float(S1[m]["infer_cycles"]), 0.4, color=c)
    axs[0].bar(i + 0.2, float(S1[m]["active"]), 0.4, color=c, alpha=0.5)
    axs[1].bar(i, float(S1[m]["active_over_vela"]), 0.6, color=c)
axs[0].set_yscale("log"); axs[0].set_ylabel("cycles"); axs[0].set_xticks(list(x), [n for _, n, _ in MODELS], rotation=30)
axs[0].set_title("inference window (solid) and npu_active (light)")
axs[1].axhline(1.0, color="0.3", lw=0.8, ls="--"); axs[1].set_xticks(list(x), [n for _, n, _ in MODELS], rotation=30)
axs[1].set_ylabel("npu_active / Vela cycles_npu"); axs[1].set_title("board vs Vela estimate (whole model)")
for a in axs: a.grid(True, axis="y", alpha=0.3)
fig.suptitle("Stage 1  Inference cycles", fontsize=11)
fig.text(0.01, 0.01, NOTE, fontsize=7, color="0.4"); fig.tight_layout(rect=(0, 0.03, 1, 0.96))
fig.savefig(D / "figures/stage1_cycles_vela.png", dpi=150)
