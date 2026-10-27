"""Generate every figure the Project-I report needs.

    python report/figures.py

Writes PNGs into report/figures/ at 200 dpi, sized for a Word page with
1-inch margins (6.5 in of usable width).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#0E1729"
NAVY = "#1F2A44"
SLATE = "#55617A"
TEAL = "#0E8C79"
AMBER = "#B8720A"
RED = "#C0392B"
CARD = "#EEF2F8"
RULE = "#D7DEE9"
WHITE = "#FFFFFF"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "figure.facecolor": WHITE,
    "savefig.facecolor": WHITE,
})


def save(fig, name):
    path = OUT / name
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    print(f"  wrote {path.name}")


def card(ax, x, y, w, h, *, fill=CARD, edge=RULE, accent=None, lw=0.9,
         radius=0.02, z=2):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=fill, zorder=z))
    if accent:
        ax.add_patch(mpatches.Rectangle((x, y + h - 0.012), w, 0.012,
                                        facecolor=accent, edgecolor="none",
                                        zorder=z + 1))


def node(ax, x, y, w, h, title, sub="", *, fill=CARD, edge=RULE, accent=None,
         title_size=8.2, sub_size=6.9):
    """A block whose title sits above its caption, never on top of it."""
    card(ax, x, y, w, h, fill=fill, edge=edge, accent=accent)
    if sub:
        ax.text(x + w / 2, y + h * 0.62, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color=NAVY, zorder=4)
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center",
                fontsize=sub_size, color=SLATE, zorder=4, linespacing=1.25)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color=NAVY, zorder=4)


def arrow(ax, p0, p1, *, color=TEAL, lw=1.2, rad=0.0, text="",
          text_off=(0, 0.016), dashed=False, ha="center"):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=10, linewidth=lw,
        color=color, connectionstyle=f"arc3,rad={rad}", zorder=1,
        linestyle="--" if dashed else "-"))
    if text:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ax.text(mx + text_off[0], my + text_off[1], text, ha=ha,
                va="bottom", fontsize=6.4, color=SLATE, style="italic",
                zorder=5)


def blank_axes(w_in, h_in):
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# ===========================================================================
# Fig. 1 - Gantt chart
# ===========================================================================
def fig_gantt():
    # 26 weeks, July to December 2026.  Review-2 falls on 4 September,
    # roughly week 9, so everything marked complete must sit to its left.
    tasks = [
        ("Literature survey and problem formulation", 0, 3, TEAL),
        ("IoT device simulation and edge gateway", 2, 2, TEAL),
        ("Holographic twin layer and forward model", 3, 2, TEAL),
        ("Counterfactual future generation", 4, 2, TEAL),
        ("Threat-detection model and feature pipeline", 4, 2, TEAL),
        ("Poisoning attack simulator", 5, 2, TEAL),
        ("Counterfactual validation and CCS gate", 6, 2, TEAL),
        ("Predictive immunization engine", 7, 2, TEAL),
        ("Quarantine, retraining and self-healing", 7, 2, TEAL),
        ("Review-2 documentation and demonstration", 8, 1, TEAL),
        ("Baseline re-implementation and benchmarking", 9, 4, AMBER),
        ("Poisoning-rate sweep and comparative study", 12, 4, AMBER),
        ("Cross-dataset validation", 15, 3, AMBER),
        ("Patent drafting and paper preparation", 17, 4, AMBER),
        ("Final report and Review-3", 20, 4, AMBER),
    ]
    months = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig, ax = plt.subplots(figsize=(6.5, 3.9))
    for i, (name, start, dur, colour) in enumerate(tasks):
        y = len(tasks) - i - 1
        ax.barh(y, dur, left=start, height=0.56, color=colour, alpha=0.90,
                edgecolor=NAVY, linewidth=0.4, zorder=3)
        ax.text(start + dur + 0.28, y, f"{dur}w", va="center", ha="left",
                fontsize=6.0, color=SLATE, zorder=4)

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t[0] for t in reversed(tasks)], fontsize=7.0,
                       color=NAVY)
    ax.set_xticks([0, 4.33, 8.67, 13.0, 17.33, 21.67, 26])
    ax.set_xticklabels(months + [""], fontsize=7.4, color=NAVY)
    ax.set_xlim(0, 26)
    ax.set_ylim(-0.7, len(tasks) - 0.25)
    ax.set_xlabel("Fall Semester 2026  (weeks)", fontsize=7.6, color=NAVY)
    ax.grid(axis="x", color=RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(length=0)

    ax.axvline(9.2, color=RED, linewidth=1.1, linestyle="--", zorder=5)
    ax.text(9.5, len(tasks) - 0.6, "Review-2\n04-09-2026", fontsize=6.4,
            color=RED, ha="left", va="top", fontweight="bold",
            linespacing=1.2)

    ax.legend(handles=[mpatches.Patch(color=TEAL, label="Completed"),
                       mpatches.Patch(color=AMBER, label="Planned")],
              loc="upper right", fontsize=6.8, frameon=False,
              bbox_to_anchor=(1.0, 0.72))
    save(fig, "fig1_gantt.png")


# ===========================================================================
# Fig. 2 - System architecture
# ===========================================================================
def fig_architecture():
    fig, ax = blank_axes(6.5, 4.4)
    ax.add_patch(mpatches.Rectangle((0.004, 0.004), 0.992, 0.992, fill=False,
                                    edgecolor=RULE, linewidth=0.8))

    # ---- device plane: title above the list, not over it ------------------
    card(ax, 0.02, 0.34, 0.17, 0.56, fill=WHITE, accent=TEAL)
    ax.text(0.105, 0.855, "DEVICE PLANE", ha="center", va="center",
            fontsize=7.0, fontweight="bold", color=TEAL, zorder=4)
    devices = ["Smart camera", "Smart bulb", "Smart plug",
               "Smart lock", "Temp. sensor", "Smart speaker"]
    for i, d in enumerate(devices):
        ax.text(0.105, 0.780 - i * 0.068, d, ha="center", va="center",
                fontsize=6.6, color=NAVY, zorder=4)
    ax.text(0.105, 0.285, "16 telemetry features\nper device per tick",
            ha="center", va="top", fontsize=6.2, color=SLATE,
            linespacing=1.3)

    arrow(ax, (0.195, 0.62), (0.245, 0.62), text="telemetry")

    # ---- edge gateway -----------------------------------------------------
    card(ax, 0.25, 0.14, 0.34, 0.79, fill=WHITE, edge=RULE, z=1)
    ax.text(0.42, 0.895, "EDGE GATEWAY  ·  ALL PROCESSING LOCAL",
            ha="center", fontsize=6.7, fontweight="bold", color=TEAL, zorder=4)

    gw = [("Telemetry Collector", "on-demand ticks only"),
          ("Holographic Twin Layer", "five behavioural planes"),
          ("Counterfactual Futures", "20 futures x 5 ticks"),
          ("Threat Detector", "7-class random forest"),
          ("CCS Validation Gate", "six weighted components")]
    gw_y = []
    for i, (t, sub) in enumerate(gw):
        y = 0.740 - i * 0.132
        gw_y.append(y)
        node(ax, 0.27, y, 0.30, 0.100, t, sub, accent=TEAL,
             title_size=7.1, sub_size=6.1)
        if i < len(gw) - 1:
            arrow(ax, (0.42, y), (0.42, y - 0.031), lw=1.0)

    arrow(ax, (0.595, 0.52), (0.645, 0.52), text="verdict")

    # ---- decision and recovery -------------------------------------------
    card(ax, 0.65, 0.14, 0.33, 0.79, fill=WHITE, edge=RULE, z=1)
    ax.text(0.815, 0.895, "DECISION AND RECOVERY", ha="center", fontsize=6.7,
            fontweight="bold", color=TEAL, zorder=4)

    node(ax, 0.668, 0.760, 0.140, 0.080, "SAFE", "safe pool", accent=TEAL,
         title_size=6.9, sub_size=5.9)
    node(ax, 0.822, 0.760, 0.140, 0.080, "SUSPICIOUS", "quarantine",
         accent=RED, title_size=6.9, sub_size=5.9)

    dec = [("Predictive Immunization", "vaccines from futures"),
           ("Secure Retraining", "four promotion gates"),
           ("Self-Healing Controller", "rollback and purge")]
    for i, (t, sub) in enumerate(dec):
        y = 0.608 - i * 0.132
        node(ax, 0.668, y, 0.294, 0.100, t, sub, accent=TEAL,
             title_size=7.1, sub_size=6.1)
        if i < len(dec) - 1:
            arrow(ax, (0.815, y), (0.815, y - 0.031), lw=1.0)

    ax.add_patch(mpatches.Rectangle((0.668, 0.170), 0.294, 0.052,
                                    facecolor=NAVY, edgecolor="none",
                                    zorder=3))
    ax.text(0.815, 0.196, "TRUSTED THREAT MODEL", ha="center", va="center",
            fontsize=6.8, fontweight="bold", color=WHITE, zorder=4)
    arrow(ax, (0.815, 0.313), (0.815, 0.226), lw=1.0)

    # ---- feedback loop: model returns to the detector ---------------------
    detector_y = gw_y[3] + 0.050          # centre of the Threat Detector box
    ax.plot([0.668, 0.615], [0.196, 0.196], color=SLATE, linewidth=1.0,
            linestyle="--", zorder=1)
    ax.plot([0.615, 0.615], [0.196, detector_y], color=SLATE, linewidth=1.0,
            linestyle="--", zorder=1)
    arrow(ax, (0.615, detector_y), (0.573, detector_y), color=SLATE, lw=1.0)
    ax.text(0.622, 0.108, "the promoted model returns to detection",
            ha="left", va="center", fontsize=6.1, color=SLATE, style="italic")

    save(fig, "fig2_architecture.png")


# ===========================================================================
# Fig. 3 - Data flow diagram
# ===========================================================================
def fig_dfd():
    fig, ax = blank_axes(6.5, 5.4)

    # ---------------------------------------------------------- Level 0 ---
    ax.text(0.5, 0.985, "Level 0  —  Context Diagram", ha="center",
            fontsize=8.4, fontweight="bold", color=NAVY)

    node(ax, 0.02, 0.855, 0.20, 0.072, "IoT Devices", "external entity",
         fill=WHITE, accent=TEAL, title_size=7.5, sub_size=6.1)
    node(ax, 0.02, 0.740, 0.20, 0.072, "Update Contributor",
         "device / hub / cloud", fill=WHITE, accent=AMBER, title_size=7.5,
         sub_size=6.1)
    node(ax, 0.78, 0.798, 0.20, 0.072, "Network Operator", "external entity",
         fill=WHITE, accent=TEAL, title_size=7.5, sub_size=6.1)

    ax.add_patch(mpatches.Circle((0.50, 0.836), 0.086, facecolor=CARD,
                                 edgecolor=TEAL, linewidth=1.2, zorder=2))
    ax.text(0.50, 0.868, "0", ha="center", va="center", fontsize=7.8,
            fontweight="bold", color=TEAL, zorder=3)
    ax.text(0.50, 0.822, "CIHDT\nFramework", ha="center", va="center",
            fontsize=6.8, fontweight="bold", color=NAVY, zorder=3,
            linespacing=1.2)

    arrow(ax, (0.225, 0.891), (0.415, 0.862), text="telemetry")
    arrow(ax, (0.225, 0.776), (0.415, 0.808), color=AMBER,
          text="model update", text_off=(0, -0.042))
    arrow(ax, (0.588, 0.848), (0.777, 0.848), text="alerts, verdicts")
    arrow(ax, (0.777, 0.812), (0.588, 0.812), text="step commands",
          text_off=(0, -0.040))

    ax.plot([0.02, 0.98], [0.703, 0.703], color=RULE, linewidth=0.8)

    # ---------------------------------------------------------- Level 1 ---
    ax.text(0.5, 0.668, "Level 1  —  Decomposition of the CIHDT Framework",
            ha="center", fontsize=8.4, fontweight="bold", color=NAVY)

    def process(tag, name, x, y):
        card(ax, x, y, 0.145, 0.100, fill=CARD, edge=TEAL, lw=1.0,
             radius=0.03)
        ax.text(x + 0.0725, y + 0.078, tag, ha="center", va="center",
                fontsize=6.5, fontweight="bold", color=TEAL, zorder=4)
        ax.text(x + 0.0725, y + 0.036, name, ha="center", va="center",
                fontsize=6.8, fontweight="bold", color=NAVY, zorder=4,
                linespacing=1.15)

    def store(x, y, tag, name):
        ax.add_patch(mpatches.Rectangle((x, y), 0.175, 0.050,
                                        facecolor=WHITE, edgecolor=NAVY,
                                        linewidth=0.8, zorder=2))
        ax.plot([x + 0.030, x + 0.030], [y, y + 0.050], color=NAVY,
                linewidth=0.8, zorder=3)
        ax.text(x + 0.015, y + 0.025, tag, ha="center", va="center",
                fontsize=6.1, fontweight="bold", color=NAVY, zorder=4)
        ax.text(x + 0.106, y + 0.025, name, ha="center", va="center",
                fontsize=6.3, color=SLATE, zorder=4)

    # top band: telemetry pipeline
    process("1.0", "Collect\nTelemetry", 0.075, 0.505)
    process("2.0", "Maintain\nTwins", 0.285, 0.505)
    process("3.0", "Generate\nFutures", 0.495, 0.505)
    process("4.0", "Detect\nThreats", 0.705, 0.505)

    node(ax, 0.075, 0.625, 0.145, 0.046, "IoT Devices", fill=WHITE,
         accent=TEAL, title_size=6.7)
    node(ax, 0.795, 0.625, 0.145, 0.046, "Operator", fill=WHITE, accent=TEAL,
         title_size=6.7)

    arrow(ax, (0.1475, 0.623), (0.1475, 0.607), lw=1.0)
    arrow(ax, (0.222, 0.555), (0.283, 0.555), lw=1.0)
    arrow(ax, (0.432, 0.555), (0.493, 0.555), lw=1.0)
    arrow(ax, (0.642, 0.555), (0.703, 0.555), lw=1.0)
    arrow(ax, (0.7775, 0.607), (0.8300, 0.623), lw=1.0, text="verdicts",
          text_off=(0.055, -0.004))

    store(0.260, 0.418, "D1", "Telemetry buffer")
    store(0.480, 0.418, "D2", "Future bank")
    arrow(ax, (0.3475, 0.503), (0.3475, 0.470), lw=1.0)
    arrow(ax, (0.5675, 0.503), (0.5675, 0.470), lw=1.0)

    # lower band: the validation and recovery path
    process("5.0", "Validate\nUpdate", 0.285, 0.245)
    process("6.0", "Immunize &\nRetrain", 0.520, 0.245)
    process("7.0", "Self-Heal\n& Rollback", 0.755, 0.245)

    node(ax, 0.045, 0.269, 0.150, 0.052, "Contributor", fill=WHITE,
         accent=AMBER, title_size=6.7)
    arrow(ax, (0.197, 0.295), (0.283, 0.295), color=AMBER, lw=1.0,
          text="update", text_off=(0, 0.010))

    # the future bank is what the update is scored against
    arrow(ax, (0.5675, 0.416), (0.400, 0.348), color=SLATE, lw=1.0,
          dashed=True, rad=0.14)
    ax.text(0.470, 0.372, "audit scenarios", ha="center", fontsize=6.2,
            color=SLATE, style="italic", zorder=5)

    store(0.145, 0.100, "D3", "Safe pool")
    store(0.375, 0.100, "D4", "Quarantine")
    store(0.630, 0.100, "D5", "Model registry")

    arrow(ax, (0.330, 0.243), (0.250, 0.152), lw=1.0)
    ax.text(0.238, 0.203, "accepted", ha="right", fontsize=6.2, color=TEAL,
            style="italic", zorder=5)
    arrow(ax, (0.395, 0.243), (0.448, 0.152), color=RED, lw=1.0)
    ax.text(0.470, 0.203, "quarantined", ha="left", fontsize=6.2, color=RED,
            style="italic", zorder=5)

    arrow(ax, (0.232, 0.126), (0.517, 0.262), lw=1.0, rad=-0.16)
    ax.text(0.300, 0.070, "validated rows feed retraining", ha="left",
            fontsize=6.2, color=SLATE, style="italic", zorder=5)
    arrow(ax, (0.667, 0.243), (0.700, 0.152), lw=1.0)
    arrow(ax, (0.753, 0.295), (0.667, 0.295), color=SLATE, lw=1.0,
          dashed=True)
    arrow(ax, (0.795, 0.243), (0.760, 0.152), color=SLATE, lw=1.0,
          dashed=True)
    ax.text(0.828, 0.196, "rollback", ha="left", fontsize=6.2, color=SLATE,
            style="italic", zorder=5)

    save(fig, "fig3_dfd.png")


# ===========================================================================
# Fig. 4 - Use case diagram
# ===========================================================================
def fig_usecase():
    fig, ax = blank_axes(6.5, 4.8)

    def actor(x, y, label, colour=NAVY):
        ax.add_patch(mpatches.Circle((x, y + 0.050), 0.016, fill=False,
                                     edgecolor=colour, linewidth=1.1))
        ax.plot([x, x], [y + 0.034, y - 0.010], color=colour, linewidth=1.1)
        ax.plot([x - 0.026, x + 0.026], [y + 0.021, y + 0.021], color=colour,
                linewidth=1.1)
        ax.plot([x, x - 0.020], [y - 0.010, y - 0.046], color=colour,
                linewidth=1.1)
        ax.plot([x, x + 0.020], [y - 0.010, y - 0.046], color=colour,
                linewidth=1.1)
        ax.text(x, y - 0.062, label, ha="center", va="top", fontsize=6.9,
                fontweight="bold", color=colour, linespacing=1.2)

    actor(0.085, 0.660, "Network\nOperator")
    actor(0.085, 0.250, "IoT Device\n(simulated)")
    actor(0.915, 0.500, "Update\nContributor\n(may be hostile)", colour=AMBER)

    card(ax, 0.235, 0.040, 0.53, 0.925, fill=WHITE, edge=NAVY, lw=1.0, z=1)
    ax.text(0.50, 0.925, "CIHDT  Edge  Security  Framework", ha="center",
            fontsize=8.2, fontweight="bold", color=NAVY, zorder=4)

    cases = [
        ("Deploy IoT devices and start gateway", 0.845, "op"),
        ("Collect telemetry on demand", 0.760, "both"),
        ("Build and feed holographic twins", 0.675, "op"),
        ("Commit counterfactual futures", 0.590, "op"),
        ("Train threat detector", 0.505, "op"),
        ("Monitor fleet and detect threats", 0.420, "both"),
        ("Submit model update", 0.335, "contrib"),
        ("Validate update against futures", 0.250, "op"),
        ("Apply or override the verdict", 0.165, "op"),
        ("Analyse quarantine and retrain", 0.085, "op"),
    ]
    for label, y, who in cases:
        ax.add_patch(mpatches.Ellipse((0.50, y), 0.42, 0.062,
                                      facecolor=CARD,
                                      edgecolor=AMBER if who == "contrib"
                                      else TEAL,
                                      linewidth=0.9, zorder=2))
        ax.text(0.50, y, label, ha="center", va="center", fontsize=6.9,
                color=NAVY, zorder=3)

    for label, y, who in cases:
        if who in ("op", "both"):
            ax.plot([0.112, 0.292], [0.645, y], color=SLATE, linewidth=0.55,
                    zorder=0)
        if who in ("both",):
            ax.plot([0.112, 0.292], [0.235, y], color=SLATE, linewidth=0.55,
                    zorder=0)
        if who == "contrib":
            ax.plot([0.888, 0.708], [0.485, y], color=AMBER, linewidth=0.7,
                    zorder=0)

    # relationships between use cases
    arrow(ax, (0.50, 0.303), (0.50, 0.283), color=SLATE, lw=0.9)
    ax.text(0.515, 0.293, "«triggers»", fontsize=6.0, color=SLATE,
            style="italic", va="center", zorder=5)
    arrow(ax, (0.50, 0.218), (0.50, 0.198), color=SLATE, lw=0.9)
    ax.text(0.515, 0.208, "«include»", fontsize=6.0, color=SLATE,
            style="italic", va="center", zorder=5)
    arrow(ax, (0.50, 0.117), (0.50, 0.133), color=RED, lw=0.9)
    ax.text(0.515, 0.125, "«extend»  only if quarantined", fontsize=6.0,
            color=RED, style="italic", va="center", zorder=5)

    save(fig, "fig4_usecase.png")


# ===========================================================================
# Fig. 5 - Sequence diagram
# ===========================================================================
def fig_sequence():
    fig, ax = blank_axes(6.5, 4.4)

    lanes = [("Operator", 0.075), ("Twin\nRegistry", 0.235),
             ("Future\nBank", 0.395), ("CCS\nValidator", 0.555),
             ("Safe Pool /\nQuarantine", 0.715), ("Model\nRegistry", 0.875)]
    for name, x in lanes:
        card(ax, x - 0.068, 0.895, 0.136, 0.072, fill=CARD, edge=RULE, z=3)
        ax.text(x, 0.931, name, ha="center", va="center", fontsize=6.8,
                fontweight="bold", color=NAVY, zorder=4, linespacing=1.15)
        ax.plot([x, x], [0.055, 0.893], color=RULE, linewidth=0.8,
                linestyle=(0, (3, 3)), zorder=0)

    X = {n.replace("\n", " "): x for n, x in lanes}
    steps = [
        (0.840, "Operator", "Twin Registry", "collect and feed telemetry",
         TEAL),
        (0.775, "Twin Registry", "Future Bank",
         "commit 20 futures x 5 ticks  (BEFORE the update exists)", TEAL),
        (0.710, "Future Bank", "Future Bank",
         "deform half by each attack class", SLATE),
        (0.630, "Operator", "CCS Validator", "submit incoming update", AMBER),
        (0.565, "CCS Validator", "Future Bank", "request audit scenarios",
         TEAL),
        (0.500, "Future Bank", "CCS Validator", "benign + attack futures",
         TEAL),
        (0.435, "CCS Validator", "CCS Validator",
         "train shadow model, score six components", SLATE),
        (0.355, "CCS Validator", "Operator",
         "report CCS against the calibrated threshold", TEAL),
        (0.290, "Operator", "Safe Pool / Quarantine",
         "apply the verdict, or override it", AMBER),
        (0.210, "Safe Pool / Quarantine", "Model Registry",
         "retrain on validated pool + vaccines", TEAL),
        (0.145, "Model Registry", "Model Registry",
         "four gates: promote or discard", SLATE),
        (0.080, "Model Registry", "Twin Registry",
         "the trusted model re-filters the bank", SLATE),
    ]
    for y, src, dst, label, colour in steps:
        x0, x1 = X[src], X[dst]
        if src == dst:
            # A self-call: loop back into the same lifeline.
            card(ax, x0, y - 0.016, 0.048, 0.032, fill=WHITE, edge=colour,
                 lw=0.9, radius=0.01, z=3)
            ax.annotate("", xy=(x0, y - 0.016),
                        xytext=(x0 + 0.048, y + 0.016),
                        arrowprops=dict(arrowstyle="-|>", color=colour,
                                        lw=0.9))
            # Label to the left when the lane is near the right edge.
            if x0 > 0.70:
                ax.text(x0 - 0.014, y, label, ha="right", va="center",
                        fontsize=6.3, color=SLATE, zorder=4)
            else:
                ax.text(x0 + 0.062, y, label, ha="left", va="center",
                        fontsize=6.3, color=SLATE, zorder=4)
        else:
            ax.annotate("", xy=(x1, y), xytext=(x0, y),
                        arrowprops=dict(arrowstyle="-|>", color=colour,
                                        lw=1.0))
            ax.text((x0 + x1) / 2, y + 0.015, label, ha="center",
                    va="bottom", fontsize=6.3, color=SLATE, zorder=4)

    ax.text(0.5, 0.018, "The ordering is the mechanism: futures are committed "
                        "before the update they will judge exists.",
            ha="center", fontsize=6.6, color=NAVY, style="italic")
    save(fig, "fig5_sequence.png")


def main():
    print("generating report figures...")
    fig_gantt()
    fig_architecture()
    fig_dfd()
    fig_usecase()
    fig_sequence()
    print("done.")


if __name__ == "__main__":
    main()
