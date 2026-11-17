"""T18 — Report figures (static PNG, light mode, validated two-colour palette).

Palette (dataviz reference, validated: CVD ΔE 24.7, normal 33.6): batting = slot 1 blue,
bowling = slot 2 orange; text in ink tokens, recessive grid, direct labels.

Aggregate figures (no names)  → outputs/figures/fig_*.png   (shareable)
Named figures (contain picks) → report/figures/fig_*.png    (local only, git-ignored)
"""
from __future__ import annotations

import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import ROOT, load_config, path  # noqa: E402

BAT, BOWL = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
TIERS = ["Low", "Moderate", "High", "Extreme"]


def style():
    plt.rcParams.update({
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.titlecolor": INK, "axes.titleweight": "bold", "axes.titlesize": 11,
        "axes.titlelocation": "left", "font.size": 9, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.fontsize": 8.5})


def save(fig, p):
    fig.tight_layout()
    fig.savefig(p, dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_pressure_concentration(d, out):
    x = d[d.is_legal & d.batting_side_won.notna()].copy()
    x["abs_wpa"] = x.wpa_bat.abs()
    balls = x.pressure_tier.value_counts(normalize=True).reindex(TIERS) * 100
    wpa = x.groupby("pressure_tier").abs_wpa.sum().reindex(TIERS) / x.abs_wpa.sum() * 100
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    i, w = np.arange(4), 0.36
    for off, vals, col, lab in ((-w / 2 - .01, balls, BAT, "Share of balls"),
                                (w / 2 + .01, wpa, BOWL, "Share of win-probability movement")):
        bars = ax.bar(i + off, vals, w, color=col, label=lab, zorder=3)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(i, [f"{t}\nleverage" for t in TIERS])
    ax.set_ylabel("% of total")
    ax.set_ylim(0, max(balls.max(), wpa.max()) * 1.18)
    ax.grid(axis="x", visible=False)
    ax.set_title("High + Extreme balls are 25% of deliveries but carry ~50% of match swing")
    ax.legend(loc="upper right")
    save(fig, out / "fig_pressure_concentration.png")


def fig_pressure_by_phase(d, out):
    x = d[d.is_legal & d.batting_side_won.notna()]
    sh = (x.groupby(["innings", "phase"]).is_pressure.mean() * 100).unstack(0).reindex(["PP", "MID", "DEATH"])
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    i, w = np.arange(3), 0.36
    for off, inn, col, lab in ((-w / 2 - .01, 1, BAT, "Batting first (innings 1)"),
                               (w / 2 + .01, 2, BOWL, "Chasing (innings 2)")):
        bars = ax.bar(i + off, sh[inn], w, color=col, label=lab, zorder=3)
        for b, v in zip(bars, sh[inn]):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(i, ["Powerplay (1–6)", "Middle (7–15)", "Death (16–20)"])
    ax.set_ylabel("% of balls that are High/Extreme leverage")
    ax.set_ylim(0, sh.max().max() * 1.4)
    ax.grid(axis="x", visible=False)
    ax.set_title("Pressure is not the same as 'death overs'")
    ax.legend(loc="upper center", ncol=2)
    save(fig, out / "fig_pressure_by_phase.png")


def fig_reliability(rel, out):
    labels = {"rv_P": "Pressure value", "bv_P": "Pressure value", "wpa_per100_P": "Pressure WPA",
              "delta_rv": "Pressure − usual level", "delta_bv": "Pressure − usual level",
              "consistency": "Consistency", "rv_N": "Non-pressure value", "bv_N": "Non-pressure value",
              "sr_P": "Raw SR / economy", "econ_P": "Raw SR / economy", "dot_pct_P": "Raw dot %",
              "bnd_pct_P": "Raw boundary %"}
    order = ["Pressure value", "Pressure WPA", "Pressure − usual level", "Consistency", "Non-pressure value",
             "Raw SR / economy", "Raw dot %", "Raw boundary %"]
    v = {k: rel[k]["split_half"].assign(lbl=lambda t: t.metric.map(labels)).set_index("lbl")
         .full_sample_reliability.reindex(order) for k in ("bat", "bowl")}
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    y, h = np.arange(len(order))[::-1], 0.36
    for off, k, col, lab in ((h / 2 + .01, "bat", BAT, "Batting"), (-h / 2 - .01, "bowl", BOWL, "Bowling")):
        ax.barh(y + off, v[k].clip(lower=0), h, color=col, label=lab, zorder=3)
        for yy, val in zip(y + off, v[k]):
            ax.text(max(val, 0) + .01, yy, f"{val:.2f}", va="center", fontsize=7.5, color=INK2)
    ax.axhline(3.5, color=MUTED, lw=.8, ls=":")
    ax.text(.98, 3.6, "context-adjusted skill metrics ↑   ·   raw rates (largely role/style) ↓",
            transform=ax.get_yaxis_transform(), ha="right", fontsize=7.5, color=MUTED)
    ax.set_yticks(y, order)
    ax.set_xlim(0, .85)
    ax.set_xlabel("Split-half reliability (full sample, Spearman-Brown)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Pressure-specific performance barely repeats")
    ax.legend(loc="upper right")
    save(fig, out / "fig_reliability.png")


def fig_out_of_time(vdir, out):
    fig, axs = plt.subplots(1, 2, figsize=(9.2, 3.6), sharex=True)
    for ax, k, col, ttl in ((axs[0], "bat", BAT, "Batting"), (axs[1], "bowl", BOWL, "Bowling")):
        t = pd.read_csv(vdir / f"out_of_time_{k}.csv")
        ci = t["r 90% CI"].str.strip("[]").str.split(",", expand=True).astype(float)
        y = np.arange(len(t))[::-1]
        names = (t["predictor (2022–24)"].str.replace(" (final)", "", regex=False)
                 .str.replace("naive: ", "", regex=False).str.replace(" (no shrinkage)", "", regex=False))
        for yy, (lo, hi), r, nm in zip(y, ci.to_numpy(), t["r_w vs pressure value"], t["predictor (2022–24)"]):
            final = "final" in nm
            c = col if final else MUTED
            ax.plot([lo, hi], [yy, yy], color=c, lw=2, solid_capstyle="round", zorder=2)
            ax.plot(r, yy, "o", ms=8 if final else 6, color=c, mec=SURF, mew=2, zorder=3)
            ax.text(hi + .02, yy, f"{r:.2f}", va="center", fontsize=7.5, color=INK if final else INK2,
                    fontweight="bold" if final else "normal")
        ax.axvline(0, color=INK2, lw=.8)
        ax.set_yticks(y, names)
        ax.set_title(f"{ttl} (n = {int(t.players.iloc[0])})")
        ax.grid(axis="y", visible=False)
    axs[0].set_xlabel("Weighted correlation r (90% CI)"); axs[1].set_xlabel("Weighted correlation r (90% CI)")
    fig.suptitle("Out-of-time check: ratings built on 2022–24 vs pressure performance in 2025–26",
                 x=.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    save(fig, out / "fig_out_of_time.png")


def fig_top15(kind, rk, out):
    col = BAT if kind == "batting" else BOWL
    t = rk.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    y = np.arange(len(t))
    ax.axvspan(.5, 10.5, color=GRID, alpha=.5, zorder=0)
    for yy, (_, r) in zip(y, t.iterrows()):
        ax.plot([r.rank_p05, r.rank_p95], [yy, yy], color=col, lw=2, alpha=.55, solid_capstyle="round", zorder=2)
        ax.plot(r["rank"], yy, "o", ms=7, color=col, mec=SURF, mew=2, zorder=3)
        ax.text(max(r.rank_p95, r["rank"]) + 1, yy, f"P(top-10) {r.p_top10:.2f}", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(y, [f"{int(r['rank'])}. {r.display_name}" for _, r in t.iterrows()])
    ax.set_xlim(0, max(70, t.rank_p95.max() + 14))
    ax.set_xlabel("Rank (dot = rating rank; line = 90% bootstrap rank interval; shaded = top 10)")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"{kind.capitalize()}: top 15 with rank uncertainty")
    save(fig, out / f"fig_top15_{kind}.png")


def fig_robustness(kind, rob, out):
    col = BAT if kind == "batting" else BOWL
    t = rob.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    y = np.arange(len(t))
    ax.barh(y, t.share_scenarios_top10 * 100, .55, color=col, zorder=3)
    for yy, v, lab in zip(y, t.share_scenarios_top10 * 100, t.robustness):
        ax.text(v + 1.5, yy, f"{v:.0f}% · {lab}", va="center", fontsize=7.5, color=INK2)
    for xv, ls in ((80, "--"), (50, ":")):
        ax.axvline(xv, color=MUTED, lw=.8, ls=ls, zorder=1)
    ax.set_yticks(y, [f"{int(r.main_rank)}. {r.display_name}" for _, r in t.iterrows()])
    ax.set_xlim(0, 125)
    ax.set_xlabel("% of 17 alternative scenarios in which the player stays top 10\n"
                  "(dashed 80% = Robust threshold, dotted 50% = Moderate threshold)")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"{kind.capitalize()}: robustness of the ranking")
    save(fig, out / f"fig_robustness_{kind}.png")


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    style()
    interim, outs = path(cfg, "interim"), path(cfg, "outputs")
    pub = outs / "figures"; pub.mkdir(exist_ok=True)
    loc = ROOT / "report" / "figures"; loc.mkdir(parents=True, exist_ok=True)
    d = pd.read_parquet(interim / "rating_balls.parquet")
    with open(interim / "reliability.pkl", "rb") as fh:
        rel = pickle.load(fh)
    fig_pressure_concentration(d, pub)
    fig_pressure_by_phase(d, pub)
    fig_reliability(rel, pub)
    fig_out_of_time(outs / "validation", pub)
    for kind in ("batting", "bowling"):
        rk = pd.read_csv(outs / "rankings" / f"{kind}_ratings.csv", index_col=0)
        rob = pd.read_csv(outs / "rankings" / f"{kind}_robustness.csv", index_col=0)
        fig_top15(kind, rk, loc)
        fig_robustness(kind, rob, loc)
    return ["figures written"]


if __name__ == "__main__":
    run()
