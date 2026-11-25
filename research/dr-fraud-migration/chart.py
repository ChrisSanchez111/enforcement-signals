import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"
BLUE = "#257de0"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, (a, b) = plt.subplots(2, 1, figsize=(10, 10.5), gridspec_kw={"height_ratios": [1, 1.05], "hspace": 0.38})
fig.patch.set_facecolor("white")

# Panel A: DR credit card fraud losses
yrs = ["2019", "2021", "2023", "2024"]; vals = [203, 420, 534, 496]
notes = ["Card\nterminals\nled", "", "E-commerce\n≈67%", "E-commerce\n≈75%"]
bars = a.bar(yrs, vals, width=0.5, color=BLUE, zorder=3)
for r in bars:  # rounded top look via thin edge
    r.set_linewidth(0)
for x, v, n in zip(yrs, vals, notes):
    a.text(x, v + 12, f"RD${v}M", ha="center", va="bottom", fontsize=11, color=INK, fontweight="bold")
    if n: a.text(x, v / 2, n, ha="center", va="center", fontsize=9.5, color="white")
a.set_ylim(0, 640); a.set_yticks([0, 200, 400, 600])
a.yaxis.grid(True, color=GRID, zorder=0); a.set_axisbelow(True)
for s in ["top", "right", "left"]: a.spines[s].set_visible(False)
a.spines["bottom"].set_color(GRID); a.tick_params(length=0)
a.set_ylabel("Net losses, RD$ millions")
a.set_title("A · Dominican banks: credit card fraud losses moved online", loc="left", fontsize=13, fontweight="bold", pad=22)
a.text(0, 1.03, "2022 and 2025 amounts not published in report text. Channel categories changed in 2023; earlier years restated.",
       transform=a.transAxes, fontsize=9, color=INK2)

# Panel B: US federal cases linked to DR
cats = {"Account takeover": ("#257de0", "o"), "Scams on elderly": ("#f47230", "s"),
        "Shell-company laundering": ("#00b894", "D"), "Card / ATM cash-out": ("#f2a600", "^")}
cases = [  # (year, row, label, cat)
    (2013, 0, "$45M prepaid debit cash-out\n(EDNY, NY crew)", "Card / ATM cash-out"),
    (2018, 1, "3,300+ phone accounts hijacked\n(SDNY, NY + DR)", "Account takeover"),
    (2019, 2, "Phone cloning ring, DR national\nextradited (SDFL)", "Account takeover"),
    (2020, 3, "AT&T iPhone ring leader\ncaught in DR (SDNY)", "Account takeover"),
    (2024.55, 4, "Santiago call-center scam,\n2 extradited (D.N.J.)", "Scams on elderly"),
    (2025.08, 5, "$60M+ email-scam laundering,\n1,000+ fake businesses (SDNY)", "Shell-company laundering"),
    (2025.75, 6, "~$5M from ~400 seniors,\n4 extradited (D. Mass.)", "Scams on elderly"),
    (2026.2, 7, "Launderer for same ring\nextradited (D. Mass.)", "Shell-company laundering"),
]
for yr, row, lab, cat in cases:
    c, m = cats[cat]
    b.plot([2012.5, yr], [row, row], color=GRID, lw=1, zorder=1)
    b.scatter(yr, row, s=90, color=c, marker=m, edgecolor="white", linewidth=2, zorder=3)
    left = yr > 2020.5
    b.text(yr + (-0.25 if left else 0.25), row, lab, va="center", ha="right" if left else "left", fontsize=9.3, color=INK)
b.set_xlim(2012.5, 2027); b.set_ylim(7.7, -0.7); b.set_yticks([])
b.set_xticks(range(2013, 2027, 2))
for s in ["top", "right", "left"]: b.spines[s].set_visible(False)
b.spines["bottom"].set_color(GRID); b.tick_params(length=0)
b.xaxis.grid(True, color=GRID, zorder=0)
b.set_title("B · US federal cases tied to DR-based fraud rings", loc="left", fontsize=13, fontweight="bold", pad=22)
b.text(0, 1.03, "Year = charge, arrest or extradition announced. A sample of prosecuted cases, not a full count.", transform=b.transAxes, fontsize=9, color=INK2)
h = [plt.Line2D([], [], color=c, marker=m, ls="", ms=9, markeredgecolor="white") for c, m in cats.values()]
b.legend(h, cats.keys(), loc="lower left", bbox_to_anchor=(0, -0.2), ncol=4, frameon=False, fontsize=9.5, handletextpad=0.3, columnspacing=1.2)
fig.text(0.125, 0.015, "Sources: Superintendencia de Bancos (RD) operational risk reports 2023–2025; U.S. DOJ press releases. Public records only.",
         fontsize=8.5, color=INK2)
fig.savefig("fraud-migration.png", dpi=160, bbox_inches="tight", facecolor="white")
