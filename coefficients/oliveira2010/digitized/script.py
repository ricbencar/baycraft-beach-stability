#!/usr/bin/env python3
"""Oliveira & Barreiro (2010): parabolic model tables and Figure-4-style plots.

Source: Oliveira & Barreiro (2010), Coastal Engineering 57, 124-131,
Table 1, p. 127.

For every fitted parabola:
    theta_deg = alpha_deg
    R/R0 = C0 + C1*(beta/alpha) + C2*(beta/alpha)**2

Writes a tab-separated output.txt containing exactly:
    theta_deg  beta_deg  r_ratio

The default beta values are 0, 5, 10, ..., 80 degrees. All 49 fitted
curves are retained, including distinct curves with equal alpha, so the
output intentionally contains duplicate theta/beta combinations.

Creates two high-resolution Matplotlib PNG graphs:
    oliveira2010.png             beta=0..80 deg, R/R0=0..1, like Hsu Fig. 4
    oliveira2010_full_range.png  full R/R0 range, without clipping

Solid curve segments correspond to beta <= alpha. Dashed segments beyond
alpha are extrapolations of the given parabola, not validated predictions.
Neither beta=0 nor R/R0=0 is forced: C0 is the actual fitted intercept.

Dependencies: Python 3.9+ and Matplotlib (for plotting).
Install:     python -m pip install matplotlib
Run:         python oliveira2010.py
Options:     python oliveira2010.py --output output.txt --plot figure.png
             python oliveira2010.py --no-plots
             python oliveira2010.py --show
"""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

# (Beach number, Fit number, alpha [deg], C0, C1, C2)
# All numerical values are stored as decimal strings to preserve the
# published number of digits and avoid binary floating-point artifacts.
COEFFICIENTS = [
    ( 1, 1, "37.04", "0.02028", "1.25732", "-0.28112"),
    ( 2, 1, "38.57", "0.01158", "1.28983", "-0.30510"),
    ( 2, 2, "38.57", "0.01158", "1.28983", "-0.10908"),
    ( 3, 1, "55.01", "-0.15211", "1.76327", "-0.61216"),
    ( 4, 1, "42.82", "-0.01756", "1.39132", "-0.37676"),
    ( 5, 1, "39.43", "0.00642", "1.30918", "-0.31888"),
    ( 6, 1, "47.05", "-0.05603", "1.50898", "-0.45495"),
    ( 7, 1, "38.66", "0.01104", "1.29185", "-0.30656"),
    ( 8, 1, "45.18", "-0.03762", "1.45504", "-0.41983"),
    ( 9, 1, "58.63", "-0.20577", "1.88805", "-0.68329"),
    (10, 1, "30.71", "0.04423", "1.14665", "-0.19452"),
    (11, 1, "30.14", "0.04565", "1.13812", "-0.18769"),
    (12, 1, "63.94", "-0.29386", "2.07373", "-0.77986"),
    (13, 1, "88.29", "-0.75039", "2.76693", "-0.79021"),
    (13, 2, "87.35", "-0.73460", "2.74769", "-0.81310"),
    (14, 1, "61.74", "-0.25571", "1.99690", "-0.74132"),
    (15, 1, "45.32", "-0.03888", "1.45896", "-0.42242"),
    (15, 2, "25.38", "0.05262", "1.08211", "-0.13811"),
    (16, 1, "52.33", "-0.11629", "1.67306", "-0.55860"),
    (17, 1, "53.13", "-0.12669", "1.69985", "-0.57460"),
    (17, 2, "55.40", "-0.15760", "1.77660", "-0.62000"),
    (18, 1, "53.71", "-0.13423", "1.71929", "-0.58620"),
    (19, 1, "66.71", "-0.34414", "2.16879", "-0.82330"),
    (20, 1, "22.19", "0.05400", "1.05452", "-0.11052"),
    (21, 1, "71.57", "-0.43552", "2.32295", "-0.88343"),
    (22, 1, "45.83", "-0.04347", "1.47324", "-0.43186"),
    (23, 1, "48.16", "-0.06776", "1.54188", "-0.47612"),
    (24, 1, "50.08", "-0.08896", "1.60056", "-0.51360"),
    (25, 1, "39.96", "0.00318", "1.32133", "-0.32752"),
    (26, 1, "61.48", "-0.25142", "1.98780", "-0.73664"),
    (27, 1, "52.07", "-0.11291", "1.66435", "-0.55340"),
    (28, 1, "47.11", "-0.05666", "1.51075", "-0.45609"),
    (29, 1, "35.54", "0.02785", "1.22745", "-0.25853"),
    (30, 1, "34.56", "0.03176", "1.20936", "-0.24484"),
    (31, 1, "49.05", "-0.07755", "1.56903", "-0.49348"),
    (31, 2, "61.19", "-0.24662", "1.97762", "-0.73140"),
    (32, 1, "41.91", "-0.01037", "1.36784", "-0.36047"),
    (33, 1, "43.90", "-0.02620", "1.41940", "-0.39620"),
    (34, 1, "33.39", "0.03614", "1.18894", "-0.22877"),
    (34, 2, "22.62", "0.05400", "1.05796", "-0.11396"),
    (35, 1, "83.87", "-0.67300", "2.66850", "-0.87600"),
    (36, 1, "34.57", "0.03172", "1.20955", "-0.24498"),
    (37, 1, "36.87", "0.02122", "1.25383", "-0.27848"),
    (38, 1, "56.22", "-0.16930", "1.80459", "-0.63629"),
    (39, 1, "25.77", "0.05223", "1.08581", "-0.14181"),
    (40, 1, "25.38", "0.05262", "1.08211", "-0.13811"),
    (40, 2, "36.03", "0.02585", "1.23656", "-0.26542"),
    (41, 1, "28.88", "0.04824", "1.12114", "-0.17368"),
    (42, 1, "26.97", "0.05103", "1.09867", "-0.15370"),
]

TEN_DECIMALS = Decimal("0.0000000001")


def format_number(value: Decimal) -> str:
    """Print a Decimal using exactly 10 digits after the decimal point."""
    rounded = value.quantize(TEN_DECIMALS, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.10f}"


def build_rows(beta_max: int = 80, beta_step: int = 5):
    """Yield (theta_deg, beta_deg, r_ratio) for all fitted curves."""
    if beta_step <= 0 or beta_max < 0 or beta_max % beta_step:
        raise ValueError("Require beta_step > 0 and beta_max >= 0, "
                         "with beta_max divisible by beta_step.")

    # Stable sorting preserves every fit, including duplicated alphas.
    curves = sorted(COEFFICIENTS, key=lambda r: (Decimal(r[2]), r[0], r[1]))

    with localcontext() as ctx:
        ctx.prec = 40
        for beach, fit, alpha_text, c0_text, c1_text, c2_text in curves:
            alpha = Decimal(alpha_text)
            c0, c1, c2 = map(Decimal, (c0_text, c1_text, c2_text))
            if alpha <= 0:
                raise ValueError(f"Invalid alpha for beach {beach}, fit {fit}")
            for beta_integer in range(0, beta_max + 1, beta_step):
                beta = Decimal(beta_integer)
                x = beta / alpha
                r_ratio = c0 + c1 * x + c2 * x * x
                yield alpha, beta, r_ratio


def _make_curves(beta_max: int, beta_step: int):
    """Return the fitted parabolas and their beta-grid ordinates for plotting."""
    from decimal import Decimal

    curves = []
    for beach, fit, alpha_text, c0_text, c1_text, c2_text in sorted(
        COEFFICIENTS, key=lambda r: (Decimal(r[2]), r[0], r[1])
    ):
        alpha, c0, c1, c2 = map(
            float, (alpha_text, c0_text, c1_text, c2_text)
        )
        betas = list(range(0, beta_max + 1, beta_step))
        values = [c0 + c1 * (b / alpha) + c2 * (b / alpha)**2 for b in betas]
        curves.append((beach, fit, alpha, c0, c1, c2, betas, values))
    return curves


def make_figure(curves, beta_max: int, destination: Path,
                *, full_range: bool = False, dpi: int = 220) -> None:
    """Plot all 49 parabolas, with sample markers and Hsu-style axes."""
    try:
        import matplotlib
        # PNG generation must also work from a terminal without a display.
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable
        from matplotlib.lines import Line2D
        from matplotlib.ticker import MultipleLocator, FormatStrFormatter
    except ImportError as exc:
        raise SystemExit(
            "Matplotlib is required to generate the PNG figures. "
            "Install with: python -m pip install matplotlib"
        ) from exc

    import numpy as np

    fig, ax = plt.subplots(figsize=(13.5, 8.5), layout="constrained")
    alpha_vals = [curve[2] for curve in curves]
    norm = Normalize(vmin=min(alpha_vals), vmax=max(alpha_vals))
    cmap = plt.get_cmap("turbo")
    line_width = 1.25

    for beach, fit, alpha, c0, c1, c2, betas, values in curves:
        color = cmap(norm(alpha))

        def parabola(beta):
            x = beta / alpha
            return c0 + c1 * x + c2 * x * x

        valid_end = min(float(beta_max), alpha)
        valid_beta = np.linspace(0, valid_end, 201)
        ax.plot(valid_beta, parabola(valid_beta), color=color,
                lw=line_width, alpha=0.85, solid_capstyle="round", zorder=2)

        if float(beta_max) > alpha:
            extra_beta = np.linspace(alpha, beta_max, 151)
            ax.plot(extra_beta, parabola(extra_beta), color=color,
                    lw=line_width, ls=(0, (4, 3)), alpha=0.65, zorder=2)

        observed_beta = [b for b in betas if b <= alpha]
        observed_r = [v for b, v in zip(betas, values) if b <= alpha]
        extrap_beta = [b for b in betas if b > alpha]
        extrap_r = [v for b, v in zip(betas, values) if b > alpha]
        if observed_beta:
            ax.scatter(observed_beta, observed_r, s=10.5, facecolors="white",
                       edgecolors=[color], linewidths=0.65, alpha=0.8, zorder=3)
        if extrap_beta:
            ax.scatter(extrap_beta, extrap_r, s=9.5, marker="x",
                       color=[color], linewidths=0.6, alpha=0.65, zorder=3)

    ax.set_xlim(0, beta_max)
    ax.xaxis.set_major_locator(MultipleLocator(10))
    ax.xaxis.set_minor_locator(MultipleLocator(5))
    if full_range:
        numbers = [val for curve in curves for val in curve[7]]
        lower = min(numbers)
        upper = max(numbers)
        span = upper - lower
        pad = max(0.075, 0.04 * span)
        ax.set_ylim(lower-pad, upper+pad)
        ax.yaxis.set_major_locator(MultipleLocator(0.5))
        ax.yaxis.set_minor_locator(MultipleLocator(0.1))
        ax.set_title("Oliveira & Barreiro (2010) — all fitted parabolas and computed points",
                     fontsize=15, pad=14)
    else:
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_locator(MultipleLocator(0.1))
        ax.yaxis.set_minor_locator(MultipleLocator(0.05))
        ax.set_title("Oliveira & Barreiro (2010) — arc ratio vs obliquity",
                     fontsize=15, pad=14)
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.set_xlabel(r"Obliquity angle, $\beta$ (degrees)", fontsize=13)
    ax.set_ylabel(r"Arc ratio, $R/R_0$", fontsize=13)
    ax.grid(which="major", color="0.67", lw=0.7, zorder=0)
    ax.grid(which="minor", color="0.87", lw=0.45, zorder=0)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_axisbelow(True)

    mappable = ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    colorbar = fig.colorbar(mappable, ax=ax, fraction=0.035, pad=0.018)
    colorbar.set_label(r"Model $\theta = \alpha$ (degrees)", fontsize=11)

    proxy = [
        Line2D([0], [0], color="0.25", lw=1.7, label=r"Fitted curve, $\beta \leq \alpha$"),
        Line2D([0], [0], color="0.25", lw=1.7, ls=(0, (4, 3)),
               label=r"Extrapolation, $\beta > \alpha$"),
        Line2D([0], [0], marker="o", markerfacecolor="white", markeredgecolor="0.25",
               lw=0, markersize=5, label=r"Computed points, 5$^\circ$ spacing"),
    ]
    ax.legend(handles=proxy, loc="upper left", fontsize=9,
              frameon=True, facecolor="white", framealpha=0.90)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output.txt"),
                        help="Tab-separated table (default: output.txt)")
    parser.add_argument("--plot", type=Path, default=Path("oliveira2010.png"),
                        help="Hsu-style plot (default: oliveira2010.png)")
    parser.add_argument("--plot-full", type=Path,
                        default=Path("oliveira2010_full_range.png"),
                        help="Full ordinate range plot")
    parser.add_argument("--no-plots", action="store_true",
                        help="Produce only output.txt (requires no external packages)")
    parser.add_argument("--dpi", type=int, default=220,
                        help="Figure resolution in dots per inch (default: 220)")
    parser.add_argument("--beta-max", type=int, default=80)
    parser.add_argument("--beta-step", type=int, default=5)
    args = parser.parse_args()
    if args.dpi < 72:
        parser.error("--dpi must be >= 72")

    # Keep original Decimal-based table calculations unchanged.
    rows = list(build_rows(args.beta_max, args.beta_step))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        out.write("theta_deg\tbeta_deg\tr_ratio\n")
        for theta, beta, r_ratio in rows:
            out.write("\t".join(map(format_number, (theta, beta, r_ratio))) + "\n")
    print(f"Created {args.output} with {len(rows)} data rows "
          f"from {len(COEFFICIENTS)} fitted parabolic curves.")

    if not args.no_plots:
        curves = _make_curves(args.beta_max, args.beta_step)
        make_figure(curves, args.beta_max, args.plot,
                    full_range=False, dpi=args.dpi)
        make_figure(curves, args.beta_max, args.plot_full,
                    full_range=True, dpi=args.dpi)
        print(f"Created Hsu-style plot: {args.plot}")
        print(f"Created full-range plot: {args.plot_full}")


if __name__ == "__main__":
    main()
