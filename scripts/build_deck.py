"""Build the Round 1 slide deck (python-pptx, native charts) from report/deck/deck_data.json.

Run: python -I scripts/deck_data.py && python -I scripts/build_deck.py
Output (local only, git-ignored): report/deck/SupeRR_Selector_Round1.pptx
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "deck"
D = json.loads((OUT / "deck_data.json").read_text(encoding="utf-8"))

NAVY, BAT, BOWL = "0B1F4B", "254AA5", "D6156C"
INK, MUTED, LIGHT, GRID, WHITE = "1F2937", "6B7280", "EEF2F9", "D9DEE8", "FFFFFF"
GREY = "A7B0C0"
FONT = "Calibri"


def rgb(h):
    return RGBColor.from_string(h)


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(sl, x, y, w, h, runs, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         italic=False, name=None):
    """runs: str, or list of paragraphs, each a str or list of (text, {opts})."""
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        for t, o in ([(p, {})] if isinstance(p, str) else p):
            r = para.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = rgb(o.get("color", color))
        if i < len(paras) - 1:
            para.space_after = Pt(10)
    return tb


def box(sl, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE, line=None, radius=None):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def label_in(s, t, size=12, color=WHITE, bold=True, align=PP_ALIGN.CENTER):
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = t
    r.font.name, r.font.size, r.font.bold = FONT, Pt(size), bold
    r.font.color.rgb = rgb(color)


def line(sl, x1, y1, x2, y2, color=GRID, width=1.0, dash=False):
    c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    if dash:
        from pptx.enum.dml import MSO_LINE
        c.line.dash_style = MSO_LINE.DASH
    return c


def slide(title=None, sub=None, dark=False, notes=None):
    sl = prs.slides.add_slide(BLANK)
    bg = sl.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(NAVY if dark else WHITE)
    if title:
        text(sl, 0.6, 0.38, 12.1, 0.7, title, size=30, bold=True, color=WHITE if dark else NAVY, name="Title")
    if sub:
        text(sl, 0.6, 1.02, 12.1, 0.4, sub, size=15, color="C9D3EA" if dark else MUTED)
    if notes:
        sl.notes_slide.notes_text_frame.text = notes
    return sl


def footer(sl, t, dark=False):
    text(sl, 0.6, 7.02, 12.1, 0.3, t, size=10, color="9AA8C7" if dark else MUTED)


def style_chart(ch, colors, legend=True, size=12, num_fmt='0"%"', gap=60, overlap=-10, val_max=None,
                val_axis=True, val_min=0):
    ch.font.name, ch.font.size = FONT, Pt(size)
    ch.font.color.rgb = rgb(INK)
    ch.has_title = False
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.TOP
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(size)
    plot = ch.plots[0]
    plot.gap_width = gap
    plot.overlap = overlap
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = num_fmt, False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size, dl.font.color.rgb = Pt(size), rgb(INK)
    for s, c in zip(plot.series, colors):
        s.invert_if_negative = False
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = rgb(c)
    va, ca = ch.value_axis, ch.category_axis
    va.has_major_gridlines = False
    va.visible = val_axis
    va.tick_labels.font.size = Pt(size - 1)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    va.format.line.fill.background()
    if val_max is not None:
        va.maximum_scale = val_max
        va.minimum_scale = val_min
    ca.tick_labels.font.size = Pt(size)
    ca.tick_labels.font.color.rgb = rgb(INK)
    ca.format.line.color.rgb = rgb(GRID)
    ca.has_major_gridlines = False


ROB_STYLE = {"Robust": (NAVY, WHITE, None), "Moderate": ("C9D3EA", NAVY, None), "Fragile": (WHITE, MUTED, GREY)}


# ---------------------------------------------------------------- 1. title
sl = slide(dark=True, notes=(
    "Round 1 answer up front: the two top-10 lists follow on the next two slides; the rest of the deck shows "
    "how pressure was defined, how performance was measured, how comparisons were kept fair, and how "
    "reliable the rankings are. Every number comes from the supplied data pack and is reproducible with "
    "python -I src/run_pipeline.py."))
text(sl, 0.8, 1.2, 11.5, 0.5, "SupeRR Selector Season 2  ·  Round 1", size=18, color="F5A3C7", bold=True)
text(sl, 0.8, 1.8, 11.5, 1.8, ["Who delivers when", "the match is on the line?"], size=46, bold=True, color=WHITE)
text(sl, 0.8, 3.85, 11.0, 0.9,
     "A data-driven ranking of the 10 most reliable batters and 10 most reliable bowlers under pressure",
     size=20, color="C9D3EA")
stats = [(f"{200999:,}", "deliveries analysed"), ("867", "matches, IPL + T20I, 2022–26"),
         ("25% → 50%", "pressure balls → share of match swing"), (f"{D['pool_batting']} + {D['pool_bowling']}",
                                                                   "eligible batters + bowlers")]
for i, (big, small) in enumerate(stats):
    x = 0.8 + i * 3.0
    text(sl, x, 4.95, 2.8, 0.7, big, size=30, bold=True, color=WHITE)
    text(sl, x, 5.65, 2.7, 0.6, small, size=13, color="C9D3EA")
footer(sl, "Data: supplied data pack (Jan 2022 – Nov 2026). Analysis date 17 Nov 2026.", dark=True)


# ---------------------------------------------------------------- 2-3. the lists
def leaderboard(kind):
    rows = D[kind][:10]
    col = BAT if kind == "batting" else BOWL
    is_bat = kind == "batting"
    sl = slide(f"Top 10 {'batters' if is_bat else 'bowlers'} under pressure",
               sub=("Ranked by pressure-tested rating: runs " + ("added" if is_bat else "saved")
                    + " per ball versus an average player in the same match situation"),
               notes=None)
    # headers
    hy = 1.55
    hdr = [(0.6, 0.5, "#"), (1.25, 3.2, "Player"), (4.5, 1.6, "Role"),
           (6.15, 3.3, "Rating (runs/ball vs expected)"),
           (9.55, 1.2, "Pressure SR" if is_bat else "Pressure econ."),
           (10.75, 1.0, "Pressure balls"), (11.8, 1.0, "Robustness")]
    for x, w, t in hdr:
        text(sl, x, hy, w, 0.3, t, size=11, color=MUTED, bold=True,
             align=PP_ALIGN.LEFT if x < 9 else PP_ALIGN.CENTER)
    line(sl, 0.6, hy + 0.36, 12.75, hy + 0.36, GRID, 1)
    vmax = max(r["all_balls"] for r in rows)
    y0, step = 2.03, 0.485
    for i, r in enumerate(rows):
        y = y0 + i * step
        if i % 2 == 0:
            box(sl, 0.5, y - 0.04, 12.33, step - 0.02, "F6F8FC")
        c = box(sl, 0.62, y + 0.03, 0.36, 0.36, col if i < 3 else NAVY, MSO_SHAPE.OVAL)
        label_in(c, str(r["rank"]), size=13)
        nm = r["name"]
        text(sl, 1.25, y + 0.04, 3.2, 0.36, nm, size=16, bold=True, color=INK, anchor=MSO_ANCHOR.MIDDLE)
        text(sl, 4.5, y + 0.06, 1.6, 0.32, r["role"].capitalize(), size=12, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
        bw = 2.55 * r["all_balls"] / vmax
        box(sl, 6.15, y + 0.09, bw, 0.24, col)
        text(sl, 6.15 + bw + 0.08, y + 0.04, 0.7, 0.34, f"{r['all_balls']:+.2f}", size=12, color=INK,
             anchor=MSO_ANCHOR.MIDDLE)
        text(sl, 9.55, y + 0.04, 1.2, 0.34, f"{r['raw_rate']:.1f}", size=13, color=INK, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
        text(sl, 10.75, y + 0.04, 1.0, 0.34, f"{r['pressure_balls']}", size=13, color=INK, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
        f, tc, ln = ROB_STYLE.get(r["robustness"], (WHITE, MUTED, GREY))
        p = box(sl, 11.88, y + 0.06, 0.88, 0.3, f, MSO_SHAPE.ROUNDED_RECTANGLE, line=ln, radius=0.5)
        label_in(p, r["robustness"], size=10, color=tc)
    footer(sl, "Robustness = share of 17 alternative-assumption scenarios keeping the player in the top 10 "
               "(Robust ≥ 80%, Moderate 50–80%, Fragile < 50%). Pakistan nationals excluded (IPL-ineligible); "
               "lower ranks move up.")
    detail = "; ".join(f"{r['rank']}. {r['name']} — rating {r['all_balls']:+.3f}, {r['pressure_balls']} pressure "
                       f"balls, P(top-10) {r['p_top10']:.2f}, robust in {r['robust_share']:.0f}% of scenarios"
                       for r in rows)
    sl.notes_slide.notes_text_frame.text = (
        "Order = final rating (Empirical-Bayes, all balls in context, pressure balls included). No manual "
        "reordering. " + detail)


leaderboard("batting")
leaderboard("bowling")

# ---------------------------------------------------------------- 4. method at a glance
sl = slide("How we got there, in five steps",
           sub="Every step is measured from the data pack, not assumed",
           notes=("1) Rebuilt the match state for every delivery and validated it against official results "
                  "(99.7% / 99.8% of margins reproduce). 2) Fitted a win-probability model (chase AUC 0.91). "
                  "3) Leverage = how much the next ball can move win probability; top 25% = pressure. "
                  "4) Each ball valued against what an average player would do in the same situation, wickets "
                  "priced at their run value. 5) Empirical-Bayes shrinkage, tier credibility, and out-of-time "
                  "validation to choose the estimator."))
steps = [("1", "Rebuild every ball", "Score, wickets, balls left, target — validated against official results"),
         ("2", "Win probability", "Model fitted on the pack: who is winning before each ball"),
         ("3", "Pressure = leverage", "How far the next ball can swing the result. Top 25% = pressure"),
         ("4", "Value vs expected", "Runs added or saved versus an average player in the same spot"),
         ("5", "Test & rank", "Shrink small samples, weight competitions, pick the model that predicts")]
for i, (n, h, d) in enumerate(steps):
    x = 0.6 + i * 2.5
    card = box(sl, x, 2.0, 2.25, 3.9, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    c = box(sl, x + 0.75, 2.35, 0.75, 0.75, BOWL if i == 2 else BAT, MSO_SHAPE.OVAL)
    label_in(c, n, size=24)
    text(sl, x + 0.18, 3.35, 1.9, 0.8, h, size=18, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    text(sl, x + 0.2, 4.2, 1.85, 1.6, d, size=13, color=INK, align=PP_ALIGN.CENTER)
    if i < 4:
        a = box(sl, x + 2.28, 3.75, 0.2, 0.35, GREY, MSO_SHAPE.CHEVRON)
text(sl, 0.6, 6.25, 12.1, 0.5,
     [[("Output: ", {"bold": True, "color": NAVY}),
       ("one rating per player — measured on every ball in context, with pressure balls included as evidence "
        "and small samples pulled toward their role average.", {})]], size=15)

# ---------------------------------------------------------------- 5. what is pressure
sl = slide("Pressure = how much the next ball can change who wins",
           sub="We rank every delivery by its leverage on the result — High + Extreme leverage are the pressure balls",
           notes=("Leverage index = expected spread of win probability across the possible outcomes of the ball "
                  "(dot, 1, 2, 3, 4, 6, wicket), divided by the average ball's spread. Tiers on LI quantiles, "
                  "computed separately for IPL and T20I: Low < P50, Moderate P50–75, High P75–90, Extreme ≥ P90. "
                  "Extreme balls alone (10% of balls) carry 27.9% of all win-probability movement."))
cc = D["concentration"]
cd = CategoryChartData()
cd.categories = [f"{t} leverage" for t in cc["tiers"]]
cd.add_series("Share of balls", cc["balls"])
cd.add_series("Share of match swing (|Δ win probability|)", cc["wpa"])
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.6), Inches(8.3), Inches(5.3), cd)
style_chart(gf.chart, [GREY, BOWL], val_max=60, val_axis=False)
hi_b, hi_w = cc["balls"][2] + cc["balls"][3], cc["wpa"][2] + cc["wpa"][3]
card = box(sl, 9.2, 1.9, 3.6, 4.7, NAVY, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
text(sl, 9.5, 2.2, 3.0, 0.4, "Pressure balls", size=16, color="F5A3C7", bold=True)
text(sl, 9.5, 2.65, 3.0, 0.9, f"{hi_b:.0f}%", size=54, bold=True, color=WHITE)
text(sl, 9.5, 3.55, 3.0, 0.4, "of all deliveries…", size=15, color="C9D3EA")
text(sl, 9.5, 4.15, 3.0, 0.9, f"{hi_w:.0f}%", size=54, bold=True, color=WHITE)
text(sl, 9.5, 5.05, 3.0, 0.9, "…of all the swing in who wins", size=15, color="C9D3EA")
footer(sl, "Win-probability model fitted on the pack: chase AUC 0.91 (calibration slope 1.04), first innings AUC 0.71.")

# ---------------------------------------------------------------- 6. not death overs
sl = slide("Pressure is not the same as the death overs",
           sub="Share of balls that are pressure balls, by phase and innings",
           notes=(f"{D['death_low_pct']:.0f}% of death-over balls are Low leverage because the match is already "
                  "decided. In a chase, pressure is spread evenly across all phases. Batting first, the middle "
                  "overs are almost never high-leverage. A 'death overs = pressure' rule would mislabel both. "
                  "Crowd, rivalry and tournament stakes are not in the data and are not used."))
ph = D["phase"]
cd = CategoryChartData()
cd.categories = ph["phases"]
cd.add_series("Batting first", ph["inn1"])
cd.add_series("Chasing", ph["inn2"])
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.6), Inches(8.3), Inches(5.3), cd)
style_chart(gf.chart, [BAT, BOWL], val_max=55, val_axis=False)
for i, (big, small) in enumerate([(f"{D['death_low_pct']:.0f}%", "of death-over balls are LOW pressure — the "
                                                                   "match is already decided"),
                                  ("~40%", "of chase balls are pressure balls, in every phase — chases decide "
                                           "most matches")]):
    y = 1.9 + i * 2.45
    box(sl, 9.2, y, 3.6, 2.2, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    text(sl, 9.5, y + 0.2, 3.0, 0.8, big, size=44, bold=True, color=BOWL if i else NAVY)
    text(sl, 9.5, y + 1.1, 3.0, 1.0, small, size=14, color=INK)

# ---------------------------------------------------------------- 7. valuing a ball
sl = slide("Every ball is judged against the situation it was played in",
           sub="Value = what the player did minus what an average player does in the same spot",
           notes=("Context expectation = hierarchical cell means over innings × phase × wickets in hand × pressure "
                  "tier × pace/spin × competition tier × season, sparse cells shrunk toward broader ones. "
                  "Batting value: (runs − expected runs) − λ × (out − expected out). Bowling value: (expected "
                  "conceded − conceded) + λ × (wicket − expected wicket). λ = run value of a wicket at that "
                  "moment from a DLS-style expected-remaining-runs curve fitted on the pack."))
parts = [("What happened", "Runs scored or conceded, wicket or not", NAVY),
         ("−", None, None),
         ("What's expected", "Average player, same innings, phase, wickets, pressure, pace/spin, competition", BAT),
         ("=", None, None),
         ("Value of the ball", "Runs added (batting) or saved (bowling)", BOWL)]
x = 0.6
for t, d, c in parts:
    if d is None:
        text(sl, x, 2.55, 0.7, 1.0, t, size=54, bold=True, color=MUTED, align=PP_ALIGN.CENTER)
        x += 0.75
        continue
    box(sl, x, 2.0, 3.35, 2.2, c, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    text(sl, x + 0.25, 2.25, 2.85, 0.5, t, size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    text(sl, x + 0.25, 2.9, 2.85, 1.2, d, size=14, color=WHITE, align=PP_ALIGN.CENTER)
    x += 3.6
text(sl, 0.6, 4.65, 12.1, 0.4, "A wicket is priced at what it is worth at that moment", size=20, bold=True,
     color=NAVY)
for i, (big, small) in enumerate([("≈ 10 runs", "value of a wicket in the powerplay — lots of innings left to lose"),
                                  ("≈ 3 runs", "value of a wicket at the death — few balls left to use"),
                                  ("1 number", "strike rate and dismissals combined, so no separate 'average' "
                                               "vs 'SR' trade-off")]):
    x = 0.6 + i * 4.15
    text(sl, x, 5.2, 3.9, 0.7, big, size=34, bold=True, color=BOWL if i < 2 else BAT)
    text(sl, x, 5.95, 3.8, 0.8, small, size=14, color=INK)

# ---------------------------------------------------------------- 8. fair comparisons
sl = slide("Keeping the comparison fair",
           sub="Four guards so that rankings reflect ability, not sample size, role or competition",
           notes=("Eligibility: ≥120 pressure balls faced and ≥20 pressure innings (batters); ≥150 pressure legal "
                  "balls and ≥20 pressure matches (bowlers); and an appearance since 1 Jan 2025. Shrinkage: "
                  "Normal–normal Empirical Bayes with role-group priors and between-player variance estimated on "
                  "training data. Stabilisation point on pressure balls: 366 (batting), 776 (bowling). Competition "
                  "credibility: IPL 1.0, T20I between top-10 nations 0.9, other T20I and A-team 0.6. Recency "
                  "half-life 2 years."))
cards = [("Sample size", "Shrinkage", "3 great innings can't outrank 300 balls of evidence — small samples are "
          "pulled toward the role average", BAT),
         ("Role & situation", "Like-for-like", "Openers judged against openers' situations, finishers against "
          "finishers' — never raw strike rate", NAVY),
         ("Competition", "IPL 1.0 · top T20I 0.9 · other 0.6", "Weaker opposition counts for less; no top-10 pick "
          "relies mainly on it", BOWL),
         ("Eligibility", f"{D['pool_batting']} batters · {D['pool_bowling']} bowlers",
          "Enough pressure balls to judge, and active since 1 Jan 2025", "3A6B35")]
for i, (h, big, d, c) in enumerate(cards):
    x, y = 0.6 + (i % 2) * 6.15, 1.75 + (i // 2) * 2.6
    box(sl, x, y, 5.95, 2.35, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    dot = box(sl, x + 0.3, y + 0.3, 0.6, 0.6, c, MSO_SHAPE.OVAL)
    label_in(dot, str(i + 1), size=20)
    text(sl, x + 1.15, y + 0.25, 4.6, 0.4, h, size=14, color=MUTED, bold=True)
    text(sl, x + 1.15, y + 0.6, 4.6, 0.5, big, size=22, bold=True, color=NAVY)
    text(sl, x + 1.15, y + 1.25, 4.55, 1.0, d, size=14, color=INK)

# ---------------------------------------------------------------- 9. key finding
sl = slide("Key finding: pressure-only form barely repeats",
           sub="How well each measure agrees with itself on two random halves of the data (split-half reliability; 1 = perfectly)",
           notes=("Split-half reliability, full sample (Spearman-Brown). Pressure-ball value repeats weakly (0.29 "
                  "batting, 0.14 bowling) and the pressure-minus-usual difference does not repeat at all (-0.03 / "
                  "-0.21); season-to-season correlation is about zero. Raw strike rate and economy repeat strongly "
                  "mostly because they encode role and style (finishers score faster, death bowlers concede more). "
                  "So ranking players on a few dramatic pressure moments would largely rank luck."))
rb, rw = D["reliability"]["bat"], D["reliability"]["bowl"]
cats = ["Value on pressure balls only", "Pressure 'clutch' gap (pressure − usual)", "Raw strike rate / economy"]
cd = CategoryChartData()
cd.categories = cats
cd.add_series("Batting", [rb["rv_P"], rb["delta_rv"], rb["sr_P"]])
cd.add_series("Bowling", [rw["bv_P"], rw["delta_bv"], rw["econ_P"]])
gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.65), Inches(8.0), Inches(5.0), cd)
style_chart(gf.chart, [BAT, BOWL], num_fmt="0.00", val_max=0.8, val_min=-0.3, val_axis=False, gap=50)
gf.chart.category_axis.tick_label_position = __import__("pptx.enum.chart", fromlist=["x"]).XL_TICK_LABEL_POSITION.LOW
gf.chart.category_axis.reverse_order = True
gf.chart.legend.position = XL_LEGEND_POSITION.BOTTOM
box(sl, 8.9, 1.9, 3.9, 4.75, NAVY, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
text(sl, 9.2, 2.15, 3.3, 4.3,
     [[("The 'clutch gap' is ", {}), ("≤ 0", {"bold": True, "color": "F5A3C7"}),
       (f" (batting {rb['delta_rv']:+.2f}, bowling {rw['delta_bv']:+.2f}) — it is noise."
        .replace("-", "−"), {})],
      [("Raw rates repeat, but mostly because they reflect role, not skill.", {})],
      [("So we rank ", {}), ("underlying ability shown on every ball", {"bold": True, "color": "F5A3C7"}),
       (", with pressure balls included as evidence.", {})]],
     size=17, color=WHITE)
footer(sl, "Full-sample split-half reliability with Spearman-Brown correction.")

# ---------------------------------------------------------------- 10. model choice
sl = slide("We let the data choose the model",
           sub="Ratings built on 2022–24 only, checked against how players actually did under pressure in 2025–26 (correlation r)",
           notes=("Three estimators compared on held-out seasons: M1 pressure-only (Empirical-Bayes on pressure balls), "
                  "M2 all-balls (Empirical-Bayes on every ball, pressure balls included), M3 hybrid (baseline plus "
                  "shrunk pressure residual, weights learned out-of-sample). M2 selected. Bowling: r = 0.42 "
                  "[0.31, 0.53], beating economy-based and pressure-only predictors. Batting: r = 0.16 [-0.02, 0.32], "
                  "not distinguishable from overall strike rate (0.21) — disclosed, and the model was not changed "
                  "after seeing it because 2025–26 is the test set. Results are correlational."))
names = {"M2 all-balls EB (final)": "Our rating (all balls, shrunk)", "M1 pressure-only EB": "Pressure balls only",
         "raw pressure value (no shrinkage)": "Raw pressure value"}
for j, k in enumerate(("bat", "bowl")):
    rows = [r for r in D[f"oot_{k}"] if r["name"] in names]
    cd = CategoryChartData()
    cd.categories = [names[r["name"]] for r in rows]
    cd.add_series("r", [r["r"] for r in rows])
    x = 0.5 + j * 6.25
    text(sl, x + 0.1, 1.7, 5.8, 0.4, "Batting" if k == "bat" else "Bowling", size=20, bold=True,
         color=BAT if k == "bat" else BOWL)
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(2.1), Inches(6.0), Inches(3.0), cd)
    style_chart(gf.chart, [BAT if k == "bat" else BOWL], legend=False, num_fmt="0.00", val_max=0.5, val_min=-0.1,
                val_axis=False, gap=45)
    gf.chart.category_axis.tick_label_position = __import__("pptx.enum.chart", fromlist=["x"]).XL_TICK_LABEL_POSITION.LOW
    gf.chart.category_axis.reverse_order = True
    pts = gf.chart.plots[0].series[0].points
    for i in range(1, len(rows)):
        pts[i].format.fill.solid()
        pts[i].format.fill.fore_color.rgb = rgb(GREY)
box(sl, 0.6, 5.35, 5.95, 1.15, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
text(sl, 0.85, 5.5, 5.5, 1.2, [[("Weaker signal. ", {"bold": True, "color": BAT}),
                               ("r = 0.16, about the same as plain strike rate (0.21). We say so openly and keep "
                                "batting claims modest.", {})]], size=14)
box(sl, 6.85, 5.35, 5.95, 1.15, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
text(sl, 7.1, 5.5, 5.5, 1.2, [[("Strong signal. ", {"bold": True, "color": BOWL}),
                              ("r = 0.42 [0.31–0.53], 2–3× better than pressure-only measures and better than "
                               "economy.", {})]], size=14)
footer(sl, "Weighted Pearson r; 90% intervals from a match-cluster bootstrap. Results are correlational.")


# ---------------------------------------------------------------- 11. uncertainty
def ranges(sl, kind, x0, w):
    rows = D[kind][:10]
    col = BAT if kind == "batting" else BOWL
    text(sl, x0, 1.7, w, 0.4, "Batters" if kind == "batting" else "Bowlers", size=20, bold=True, color=col)
    name_w, ax_x0, ax_w, top, step, maxr = 2.35, x0 + 2.45, w - 2.95, 2.3, 0.4, 65
    sx = lambda r: ax_x0 + (r - 0.5) / maxr * ax_w  # noqa: E731
    box(sl, sx(0.5), top - 0.12, sx(10.5) - sx(0.5), step * 10 + 0.05, LIGHT)
    text(sl, sx(0.5), top + step * 10 - 0.02, sx(10.5) - sx(0.5), 0.3, "top 10", size=10, color=MUTED,
         align=PP_ALIGN.CENTER)
    for t in (1, 20, 40, 60):
        text(sl, sx(t) - 0.3, top + step * 10 + 0.28, 0.6, 0.25, str(t), size=10, color=MUTED, align=PP_ALIGN.CENTER)
    for i, r in enumerate(rows):
        y = top + i * step + 0.1
        text(sl, x0, y - 0.13, name_w, 0.28, f"{r['rank']}. {r['name']}", size=12, color=INK,
             anchor=MSO_ANCHOR.MIDDLE)
        line(sl, sx(r["p05"]), y, sx(r["p95"]), y, col, 3)
        d = 0.17
        box(sl, sx(r["rank"]) - d / 2, y - d / 2, d, d, col, MSO_SHAPE.OVAL)
        text(sl, sx(r["p95"]) + 0.08, y - 0.13, 0.5, 0.26, f"{r['p_top10']:.2f}", size=11, color=MUTED,
             anchor=MSO_ANCHOR.MIDDLE)


sl = slide("How sure are we? The top of each list is clear; 7–10 are close calls",
           sub="Dot = rank; line = 90% range of the rank when we re-sample the matches 300 times; number = chance of staying top 10",
           notes=("Match-cluster bootstrap (300 resamples) for rank intervals and P(top-10). The top three batters "
                  f"(P ≥ {min(r['p_top10'] for r in D['batting'][:3]):.2f}) and {D['bowling'][0]['name']} "
                  f"({D['bowling'][0]['p_top10']:.2f}) are clearly separated; positions 7–10 in both lists overlap "
                  f"with the next names (batting 11–12: {D['batting'][10]['name']}, {D['batting'][11]['name']}; "
                  f"bowling 11–12: {D['bowling'][10]['name']}, {D['bowling'][11]['name']}). Intervals and P(top-10) come from the full model run, before the IPL-eligibility "
                  "exclusion renumbered the lists."))
ranges(sl, "batting", 0.6, 6.0)
ranges(sl, "bowling", 6.85, 6.0)
footer(sl, "Rank axis 1–65. Bootstrap re-samples whole matches, so a player's good and bad days move together.")


# ---------------------------------------------------------------- 12. robustness
sl = slide("The lists survive when we change our own assumptions",
           sub="% of 17 alternative scenarios in which each player stays top 10",
           notes=("Scenarios: pressure threshold 15% / 35%, rule-based pressure index, IPL-only, no tier discount, "
                  "recency 1 year / none, no or weaker shrinkage, eligibility ×0.75 / ×1.5, no activity filter, "
                  "WPA-only, leverage-weighted all balls, pressure-only and hybrid estimators. On average the top 10 "
                  "keeps 7.8/10 batters and 8.0/10 bowlers."))
for j, kind in enumerate(("batting", "bowling")):
    rows = D[kind][:10]
    col = BAT if kind == "batting" else BOWL
    x = 0.5 + j * 6.25
    text(sl, x + 0.1, 1.65, 5.8, 0.4, ("Batters — keeps 7.8 of 10 on average" if j == 0
                                       else "Bowlers — keeps 8.0 of 10 on average"), size=18, bold=True, color=col)
    cd = CategoryChartData()
    cd.categories = [f"{r['rank']}. {r['name']}" for r in rows]
    cd.add_series("%", [r["robust_share"] for r in rows])
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(2.1), Inches(6.0), Inches(4.75), cd)
    style_chart(gf.chart, [col], legend=False, num_fmt='0"%"', val_max=115, val_axis=False, gap=35, size=11)
    gf.chart.category_axis.reverse_order = True
    pts = gf.chart.plots[0].series[0].points
    for i, r in enumerate(rows):
        if r["robust_share"] < 50:
            pts[i].format.fill.solid()
            pts[i].format.fill.fore_color.rgb = rgb(GREY)
footer(sl, "Grey bar = Fragile (< 50% of scenarios). Robust ≥ 80%, Moderate 50–80%.")

# ---------------------------------------------------------------- 13. limitations
sl = slide("What the data cannot tell us",
           sub="Stated up front so the rankings are read with the right confidence",
           notes=("Further limitations: the win-probability model has no team-strength, venue or toss terms; "
                  "first-innings WP is mildly over-confident in its top decile; competition credibility factors "
                  "are pre-registered judgement because the data-driven estimate was unstable; 31 knockout matches "
                  "are reported descriptively only."))
lim = [("Mind, not just match state", "Crowd, rivalry and stakes aren't in the data — pressure here is situational",
        NAVY),
       ("Partial T20I coverage", "No T20 World Cup in the pack; bilateral series and Asia Cups only", BAT),
       ("Batting signal is weaker", "Predicts later pressure form about as well as strike rate does", BOWL),
       ("Ranks 7–10 are close", "Wide rank ranges; next names are within the noise band", "3A6B35")]
for i, (h, d, c) in enumerate(lim):
    x = 0.6 + i * 3.1
    box(sl, x, 1.9, 2.85, 3.6, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    dot = box(sl, x + 0.3, 2.2, 0.7, 0.7, c, MSO_SHAPE.OVAL)
    label_in(dot, "!", size=26)
    text(sl, x + 0.3, 3.15, 2.3, 0.9, h, size=19, bold=True, color=NAVY)
    text(sl, x + 0.3, 4.15, 2.3, 1.9, d, size=14, color=INK)

# ---------------------------------------------------------------- 14. close
sl = slide(dark=True, notes=("Reproducibility: python -I src/run_pipeline.py rebuilds every number from the raw "
                             "data pack; every threshold is pre-registered in config.yaml. The final selections "
                             "and reasoning were reviewed and are owned by the participant."))
text(sl, 0.8, 1.5, 11.5, 0.5, "The takeaway", size=18, color="F5A3C7", bold=True)
text(sl, 0.8, 2.1, 11.6, 2.4,
     "Not the players who once produced an extraordinary pressure moment — the players whose underlying "
     "ability and demonstrated performance give the strongest evidence they will deliver when it matters.",
     size=30, bold=True, color=WHITE)
for i, (big, small) in enumerate([("Top 3", f"batters, plus {D['bowling'][0]['name'].split()[-1]}, are clear of the field"),
                                  ("0.42", "bowling ratings vs later pressure performance (r)"),
                                  ("~8 / 10", "names kept across 17 alternative assumptions")]):
    x = 0.8 + i * 4.0
    text(sl, x, 4.95, 3.7, 0.7, big, size=34, bold=True, color=WHITE)
    text(sl, x, 5.7, 3.6, 0.7, small, size=14, color="C9D3EA")
footer(sl, "Fully reproducible from the supplied data pack: python -I src/run_pipeline.py", dark=True)

dst = OUT / "SupeRR_Selector_Round1.pptx"
prs.save(dst)
print("saved", dst)
