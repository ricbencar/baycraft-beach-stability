#!/usr/bin/env python3
"""Compare Oliveira2010 and Hsu1989 coefficient regressions and explain agreement.

Python 3.10+; dependencies: numpy and matplotlib.

    python -m pip install numpy matplotlib
    python script.py
    python script.py --no-show
    python script.py --theta-max 150 --r0-m 100 --output-dir results

All coefficient values and the 15 Hsu source rows are embedded. No input
workbook or text file is needed. Outputs go beside this script by default;
--output-dir changes the destination. Existing generated files with the same
names are replaced. A single plot viewer opens after generation unless
--no-show is supplied. Use its buttons or the left/right arrow keys.

DISPLAY NOTATION: C1 + C2*q + C3*q**2, q = beta/theta.
SOURCE NOTATION:  C0 + C1*q + C2*q**2. These are the SAME three terms.
Beta and theta are in degrees. Only trigonometric plotting uses radians.

The degree-six polynomials are the regressions in the supplied files, not
polynomial equations originally published by Hsu or Oliveira. Calculations
never normalize their coefficients or force the endpoint radius to one.
Model differences are not errors against field observations. The Oliveira
source rows were not supplied, so no Oliveira row residuals are invented.

Outputs explicitly include a data-driven executive conclusion and numerical
support in the console, comparison_conclusions.txt, comparison_report.txt,
comparison_conclusions.csv, comparison_metadata.json, and first page of the
plots PDF (00_executive_conclusions.png). Percentages of R0 must not be
confused with percentages of an individual predicted radius.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

try:
    import matplotlib
    import numpy as np
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with: python -m pip install numpy matplotlib"
    ) from exc

if "--no-show" in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.widgets import Button


OLIVEIRA_POLYNOMIALS = (
    (8.9379927134888931e-02, -7.4010747230969986e-03,
     5.0128072495406347e-04, -1.3097394953416148e-05,
     1.1423122564951566e-07, -5.2045195736435901e-10,
     1.6282762116787805e-12),
    (8.8162348805414326e-01, 1.5146321651759101e-02,
     -6.9703159306350117e-04, 1.6757848070587428e-05,
     4.1151569864693824e-08, -2.8320953879636758e-09,
     1.5079413405730286e-11),
    (1.8740249891403760e-02, -7.3238336183188302e-03,
     2.6842398440550411e-04, -1.0866508661427859e-05,
     7.9276852802049855e-08, 9.9295446608229346e-11,
     -2.6583961939866272e-13),
)

HSU_POLYNOMIALS = (
    (-2.5948717948720286e-02, 9.4371469397480281e-03,
     -4.0811322978137366e-04, 1.0108930697786255e-05,
     -1.7860566448803580e-07, 1.1488449630866086e-09,
     -1.3026029125105853e-12),
    (1.3292717948718358e+00, -6.5720015956185304e-02,
     4.6454080433615905e-03, -1.5110565213940694e-04,
     2.7247346369948383e-06, -2.3730284988490486e-08,
     7.7202155716091587e-11),
    (-2.9170512820513572e-01, 5.4566218941018596e-02,
     -4.1688146498725922e-03, 1.4006101055807072e-04,
     -2.5540727510077560e-06, 2.2867190600936895e-08,
     -7.7541566334136543e-11),
)

HSU_TABLE = (
    (10., .036, 1.011, -.047),
    (15., .050, .998, -.049),
    (20., .055, 1.029, -.088),
    (25., .054, 1.083, -.142),
    (30., .045, 1.146, -.194),
    (35., .029, 1.220, -.253),
    (40., .000, 1.326, -.332),
    (45., -.039, 1.446, -.412),
    (50., -.088, 1.588, -.507),
    (55., -.151, 1.756, -.611),
    (60., -.227, 1.930, -.706),
    (65., -.315, 2.113, -.800),
    (70., -.409, 2.284, -.873),
    (75., -.505, 2.422, -.909),
    (80., -.600, 2.520, -.906),
)

# These Oliveira summaries are quoted, not recomputed without the source rows.
# Order: display C1, C2, C3 = source C0, C1, C2.
OLIVEIRA_REPORTED_FIT = (
    {"r_squared": .999998926818, "rmse": 2.038110568e-04,
     "mae": 1.459514537e-04, "max_abs": 5.235919291e-04,
     "sse": 1.993869450e-06},
    {"r_squared": .999996793023, "rmse": 7.881507772e-04,
     "mae": 5.147904176e-04, "max_abs": 3.901640958e-03,
     "sse": 2.981671908e-05},
    {"r_squared": .999999569897, "rmse": 1.492343932e-04,
     "mae": 1.109805834e-04, "max_abs": 4.697339625e-04,
     "sse": 1.069003398e-06},
)

@dataclass(frozen=True)
class Model:
    """Coefficient fits in ascending powers of beta, ordered constant to quadratic."""

    name: str
    polynomials: tuple[tuple[float, ...], ...]
    beta_min: float
    beta_max: float
    color: str
    linestyle: str

    def coefficients(self, beta: Any, derivative: int = 0) -> np.ndarray:
        """Return (..., 3) coefficients or analytical beta derivatives per degree."""
        beta = np.asarray(beta, dtype=float)
        if not isinstance(derivative, int) or derivative < 0:
            raise ValueError("derivative must be a nonnegative integer")
        if not np.all(np.isfinite(beta)):
            raise ValueError("beta must contain only finite numbers")
        if np.any(beta < self.beta_min - 1e-10) or np.any(beta > self.beta_max + 1e-10):
            raise ValueError(
                f"{self.name}: beta must be between {self.beta_min} and "
                f"{self.beta_max} degrees; coefficient extrapolation is disabled."
            )
        series = []
        for values in self.polynomials:
            values = np.polynomial.polynomial.polyder(values, m=derivative)
            # Ascending-power polyval uses Horner evaluation.
            series.append(np.polynomial.polynomial.polyval(beta, values))
        return np.stack(series, axis=-1)

    def radius(self, theta_deg: Any, beta_deg: Any) -> np.ndarray:
        """Return raw R/R0; the caller masks theta < beta for the curved branch."""
        theta, beta = np.broadcast_arrays(
            np.asarray(theta_deg, dtype=float), np.asarray(beta_deg, dtype=float)
        )
        if np.any(~np.isfinite(theta)) or np.any(theta <= 0):
            raise ValueError("theta must be positive and finite")
        c = self.coefficients(beta)
        q = beta / theta
        return c[..., 0] + q * (c[..., 1] + q * c[..., 2])

    def sensitivities(self, theta_deg: Any, beta_deg: Any) -> tuple[np.ndarray, np.ndarray]:
        """Partial derivatives (dr/dbeta at fixed theta, dr/dtheta at fixed beta)."""
        theta, beta = np.broadcast_arrays(
            np.asarray(theta_deg, dtype=float), np.asarray(beta_deg, dtype=float)
        )
        if np.any(~np.isfinite(theta)) or np.any(theta <= 0):
            raise ValueError("theta must be positive and finite")
        c = self.coefficients(beta)
        dc = self.coefficients(beta, derivative=1)
        q = beta / theta
        dr_dq = c[..., 1] + 2.0 * c[..., 2] * q
        dr_dbeta = dc[..., 0] + q * (dc[..., 1] + q * dc[..., 2]) + dr_dq / theta
        dr_dtheta = -beta * dr_dq / theta**2
        return dr_dbeta, dr_dtheta


MODELS = (
    Model("Oliveira2010", OLIVEIRA_POLYNOMIALS, 22.19, 88.29, "#00857D", "-"),
    Model("Hsu1989", HSU_POLYNOMIALS, 10., 80., "#D06B28", "--"),
)


@dataclass(frozen=True)
class Config:
    beta_min: float
    beta_max: float
    theta_max: float
    n_beta: int
    n_theta: int
    dpi: int
    r0_m: float | None
    output_dir: Path
    no_show: bool


def parse_arguments() -> Config:
    parser = argparse.ArgumentParser(
        description="Compare the supplied Oliveira2010 and Hsu1989 polynomial fits.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--beta-min", type=float, default=22.19, help="comparison beta lower bound [deg]")
    parser.add_argument("--beta-max", type=float, default=80., help="comparison beta upper bound [deg]")
    parser.add_argument("--theta-max", type=float, default=270., help="chosen angular extent [deg], not a validation limit")
    parser.add_argument("--n-beta", type=int, default=401, help="uniform beta grid size")
    parser.add_argument("--n-theta", type=int, default=481, help="uniform theta grid size")
    parser.add_argument("--dpi", type=int, default=300, help="PNG output resolution")
    parser.add_argument("--r0-m", type=float, default=None, help="optional R0 in metres for radial separation reporting")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent, help="output directory")
    parser.add_argument("--no-show", action="store_true", help="save outputs without opening the plot viewer")
    args = parser.parse_args()
    if not all(math.isfinite(x) for x in (args.beta_min, args.beta_max, args.theta_max)):
        parser.error("angle limits must be finite")
    if not 22.19 <= args.beta_min < args.beta_max <= 80.:
        parser.error("use 22.19 <= beta-min < beta-max <= 80; extrapolation is disabled")
    if not args.beta_max < args.theta_max <= 360.:
        parser.error("theta-max must exceed beta-max and be at most 360 degrees")
    if not 21 <= args.n_beta <= 2001 or not 21 <= args.n_theta <= 2001:
        parser.error("n-beta and n-theta must each be between 21 and 2001")
    if args.n_beta * args.n_theta > 2_000_000:
        parser.error("the rectangular grid may contain at most 2,000,000 nodes")
    if not 72 <= args.dpi <= 600:
        parser.error("dpi must be between 72 and 600")
    if args.r0_m is not None and (not math.isfinite(args.r0_m) or args.r0_m <= 0):
        parser.error("r0-m must be a positive finite length in metres")
    args.output_dir = args.output_dir.expanduser().resolve()
    return Config(**vars(args))


def calculate_data(config: Config) -> dict[str, Any]:
    beta = np.linspace(config.beta_min, config.beta_max, config.n_beta)
    theta = np.linspace(config.beta_min, config.theta_max, config.n_theta)
    B, T = np.meshgrid(beta, theta)
    branch = T >= B
    oliveira, hsu = MODELS
    O = np.where(branch, oliveira.radius(T, B), np.nan)
    H = np.where(branch, hsu.radius(T, B), np.nan)
    delta = O - H
    denominator = np.abs(O) + np.abs(H)
    symmetric = np.full_like(delta, np.nan)
    np.divide(200.0 * delta, denominator, out=symmetric, where=denominator >= 0.02)
    preferred = [25., 35., 45., 55., 65., 80.]
    profiles = [b for b in preferred if config.beta_min <= b <= config.beta_max]
    if len(profiles) < 4:
        profiles = list(np.linspace(config.beta_min, config.beta_max, 6))
    profiles_theta = [float(t) for t in range(30, 361, 30)
                      if config.beta_min < t <= config.theta_max]
    if len(profiles_theta) < 3:
        profiles_theta = list(np.linspace(config.beta_min, config.theta_max, 4)[1:])
    C_O, C_H = oliveira.coefficients(beta), hsu.coefficients(beta)
    return {
        "beta": beta, "theta": theta, "B": B, "T": T, "branch": branch,
        "O": O, "H": H, "delta": delta, "symmetric_percent": symmetric,
        "C_O": C_O, "C_H": C_H,
        "boundary_O": C_O.sum(axis=-1) - 1.,
        "boundary_H": C_H.sum(axis=-1) - 1.,
        "profiles_beta": profiles,
        "profiles_theta": profiles_theta,
    }


def descriptive_metrics(values: Any) -> dict[str, float | int]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not values.size:
        return {"count": 0}
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "rms": float(np.sqrt(np.mean(values**2))),
        "mean_abs": float(np.mean(np.abs(values))),
        "median": float(np.median(values)),
        "p95_abs": float(np.percentile(np.abs(values), 95)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "max_abs": float(np.max(np.abs(values))),
    }


def calculate_diagnostics(data: dict[str, Any], config: Config) -> dict[str, Any]:
    table = np.asarray(HSU_TABLE)
    beta, observed = table[:, 0], table[:, 1:]
    fitted = MODELS[1].coefficients(beta)
    residual = fitted - observed
    # A scaled Vandermonde matrix and QR give a stable hat-matrix diagonal.
    design = np.polynomial.polynomial.polyvander((beta - 45.) / 35., 6)
    Q, _ = np.linalg.qr(design, mode="reduced")
    leverage = np.sum(Q**2, axis=1)
    n, p = design.shape
    mse = np.sum(residual**2, axis=0) / (n - p)
    denominator = 1. - leverage[:, None]
    loo = residual / denominator
    standardized = residual / np.sqrt(mse * denominator)
    cooks = (residual**2 / (p * mse)) * leverage[:, None] / denominator**2
    normal = NormalDist()
    qq = np.array([normal.inv_cdf((i + .5) / n) for i in range(n)])
    fit_metrics = []
    for column in range(3):
        e = residual[:, column]
        sse = float(np.sum(e**2))
        sst = float(np.sum((observed[:, column] - observed[:, column].mean())**2))
        fit_metrics.append({
            "r_squared": 1. - sse / sst,
            "rmse": float(np.sqrt(np.mean(e**2))),
            "mae": float(np.mean(np.abs(e))),
            "max_abs": float(np.max(np.abs(e))),
            "sse": sse,
            "loo_rmse": float(np.sqrt(np.mean(loo[:, column]**2))),
        })
    return {
        "hsu_beta": beta, "hsu_observed": observed, "hsu_fitted": fitted,
        "hsu_residual": residual, "hsu_loo": loo, "leverage": leverage,
        "cooks": cooks, "standardized_residual": standardized,
        "qq_theoretical": qq, "hsu_fit_metrics": fit_metrics,
        "model_difference_metrics": descriptive_metrics(data["delta"]),
        "coefficient_difference_metrics": [
            descriptive_metrics(data["C_O"][:, j] - data["C_H"][:, j])
            for j in range(3)
        ],
        "sampled_envelope": difference_envelope(config),
    }


def calculate_conclusions(
    data: dict[str, Any], diag: dict[str, Any], config: Config,
) -> dict[str, Any]:
    """Build supported, domain-specific engineering conclusions.

    All percentages here use the nominal control radius R0 as denominator,
    rather than a local predicted radius. No field-error inference is made.
    """
    metrics = diag["model_difference_metrics"]
    extent = diag["sampled_envelope"]
    extreme_label = max(("minimum", "maximum"),
                        key=lambda name: abs(extent[name]["delta_r"]))
    extreme = extent[extreme_label]
    valid_differences = np.abs(data["delta"][np.isfinite(data["delta"])])
    fraction_1pct = float(np.mean(valid_differences <= 0.01))
    fraction_2pct = float(np.mean(valid_differences <= 0.02))
    beta_end = float(config.beta_max)
    endpoint_oliveira = float(np.sum(MODELS[0].coefficients(beta_end)))
    endpoint_hsu = float(np.sum(MODELS[1].coefficients(beta_end)))
    rms_percent_r0 = 100.0 * metrics["rms"]
    max_percent_r0 = 100.0 * abs(extreme["delta_r"])

    # A descriptive classification, not a scientific pass/fail acceptance rule.
    if rms_percent_r0 <= 1.0 and fraction_1pct >= 0.85:
        classification = "VERY SIMILAR"
        opening = ("Oliveira2010 and Hsu1989 predict very similar normalized "
                   "beach planforms under identical geometric controls across "
                   "the selected common comparison domain.")
    elif rms_percent_r0 <= 2.0:
        classification = "SIMILAR OVERALL"
        opening = ("Oliveira2010 and Hsu1989 predict similar normalized "
                   "beach planforms on average across the selected common domain, "
                   "with locally greater discrepancies.")
    else:
        classification = "MEANINGFUL MODEL DIFFERENCES"
        opening = ("The selected parameter domain shows appreciable differences "
                   "between the predicted normalized beach planforms.")

    lines = [
        f"OVERALL RESULT: {classification}. {opening}",
        (f"Average agreement: RMS difference {metrics['rms']:.8f} in R/R0 "
         f"({rms_percent_r0:.3f}% of the control radius R0); mean absolute "
         f"difference {metrics['mean_abs']:.8f} "
         f"({100.0 * metrics['mean_abs']:.3f}% of R0)."),
        (f"Extent of agreement: {100.0 * fraction_1pct:.2f}% of {metrics['count']:,} "
         f"valid grid pairs differ by no more than 0.01 in R/R0 (1% of R0); "
         f"{100.0 * fraction_2pct:.2f}% differ by no more than 2% of R0."),
        (f"Localized maximum: |difference| = {abs(extreme['delta_r']):.8f} "
         f"({max_percent_r0:.3f}% of R0), near "
         f"beta={extreme['beta_deg']:.4f} deg and "
         f"theta={extreme['theta_deg']:.4f} deg. This is an "
         "extrema check across 20,001 beta samples and analytic extrema in "
         "q=beta/theta, not a certified global optimum."),
        ("Individual fitted coefficients differ more than the combined "
         "predicted radial shapes: their constant, linear and quadratic "
         "contributions partly compensate in the parabolic equation."),
        (f"Endpoint qualification: at beta=theta={beta_end:.4f} deg, "
         f"Oliveira R/R0={endpoint_oliveira:.6f} and "
         f"Hsu R/R0={endpoint_hsu:.6f}; "
         f"their separation is {abs(endpoint_oliveira-endpoint_hsu):.6f} R0. "
         "These unconstrained polynomial fits are not snapped to the ideal "
         "endpoint value R/R0=1."),
    ]
    if config.r0_m is None:
        lines.append(
            f"Scale illustration only: if R0=100 m, the grid RMS radial "
            f"difference is {100.0 * metrics['rms']:.3f} m, while the largest "
            f"checked radial difference is {100.0 * abs(extreme['delta_r']):.3f} m."
        )
    else:
        lines.append(
            f"For the user-specified R0={config.r0_m:g} m: RMS radial "
            f"difference {config.r0_m * metrics['rms']:.3f} m; largest checked "
            f"radial difference {config.r0_m * abs(extreme['delta_r']):.3f} m."
        )
    lines.extend([
        ("Engineering relevance: uncertainty in choosing diffraction point H, "
         "downcoast control E and representative wave direction W may be "
         "more consequential than differences between these two coefficient "
         "sets, but that uncertainty was not quantified here."),
        ("IMPORTANT LIMITATION: near-agreement between the two equations "
         "does NOT establish predictive accuracy against a measured "
         "shoreline, nor does it prove that their source-data or field "
         "uncertainties are equivalent. A site-specific validation with "
         "observed shoreline and wave data is still required."),
        (f"Domain: {config.beta_min:g} <= beta <= {config.beta_max:g} deg, "
         f"beta <= theta <= {config.theta_max:g} deg. Statistics use valid "
         "uniform rectangular-grid samples, not independent observations."),
    ])
    return {
        "classification": classification,
        "executive_summary": opening,
        "rms_difference_r_ratio": float(metrics["rms"]),
        "rms_percent_of_R0": rms_percent_r0,
        "mean_absolute_difference_r_ratio": float(metrics["mean_abs"]),
        "p95_absolute_difference_r_ratio": float(metrics["p95_abs"]),
        "fraction_abs_delta_le_1percent_R0": fraction_1pct,
        "fraction_abs_delta_le_2percent_R0": fraction_2pct,
        "valid_grid_points": int(metrics["count"]),
        "maximum_checked_absolute_difference_r_ratio": abs(float(extreme["delta_r"])),
        "maximum_checked_percent_of_R0": max_percent_r0,
        "maximum_checked_beta_deg": float(extreme["beta_deg"]),
        "maximum_checked_theta_deg": float(extreme["theta_deg"]),
        "boundary_beta_deg": beta_end,
        "endpoint_oliveira_r_ratio": endpoint_oliveira,
        "endpoint_hsu_r_ratio": endpoint_hsu,
        "r0_m_used_for_illustration": 100.0 if config.r0_m is None else config.r0_m,
        "r0_is_illustrative": config.r0_m is None,
        "conclusions": lines,
        "classification_is_descriptive_not_acceptance_criterion": True,
        "source_model_field_validation_performed": False,
    }


def write_conclusions_text(summary: dict[str, Any], config: Config) -> Path:
    """Write a short, standalone readable conclusion file."""
    path = config.output_dir / "comparison_conclusions.txt"
    lines = [
        "OLIVEIRA2010 - HSU1989 | EXECUTIVE COMPARISON CONCLUSIONS",
        "=" * 70,
        "",
        *[f"{i:02d}. {sentence}" for i, sentence in enumerate(summary["conclusions"], 1)],
        "",
        "Percentages refer to the nominal control radius R0, not local R/R0.",
        "The 'VERY SIMILAR' assessment is descriptive, not a design tolerance.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def difference_envelope(config: Config) -> dict[str, Any]:
    """Sample beta densely; find exact quadratic-in-q extrema for each beta.

    This includes theta=beta exactly (the rectangular grid usually misses
    most diagonal points). It is a sampled-beta diagnostic, not a certified
    continuous global optimum.
    """
    beta = np.linspace(config.beta_min, config.beta_max, 20001)
    dc = MODELS[0].coefficients(beta) - MODELS[1].coefficients(beta)
    q_min = beta / config.theta_max
    stationary = np.full_like(beta, np.nan)
    np.divide(-dc[:, 1], 2. * dc[:, 2], out=stationary,
              where=np.abs(dc[:, 2]) > 1e-15)
    stationary = np.where((stationary >= q_min) & (stationary <= 1.), stationary, np.nan)
    q = np.column_stack((q_min, np.ones_like(beta), stationary))
    delta = dc[:, 0, None] + q * (dc[:, 1, None] + q * dc[:, 2, None])
    results: dict[str, Any] = {"beta_samples": int(beta.size)}
    for label, operation in (("minimum", np.nanargmin), ("maximum", np.nanargmax)):
        row, column = np.unravel_index(operation(delta), delta.shape)
        results[label] = {"delta_r": float(delta[row, column]),
                          "beta_deg": float(beta[row]),
                          "theta_deg": float(beta[row] / q[row, column])}
    return results


def write_csv(path: Path, header: list[str], rows: Iterable[Iterable[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows:
            writer.writerow([
                ("" if not np.isfinite(value) else format(float(value), ".16g"))
                if isinstance(value, (float, np.floating)) else value for value in row
            ])


def write_tables(data: dict[str, Any], diag: dict[str, Any], config: Config,
                 conclusions: dict[str, Any]) -> list[Path]:
    destination = config.output_dir
    paths: list[Path] = []

    def save(name: str, header: list[str], rows: Iterable[Iterable[Any]]) -> None:
        path = destination / name
        write_csv(path, header, rows)
        paths.append(path)

    save("comparison_conclusions.csv", ["indicator", "value", "unit", "interpretation"], [
        ("classification", conclusions["classification"], "descriptive", "Not a formal acceptance criterion"),
        ("rms_difference", conclusions["rms_difference_r_ratio"], "R/R0", "Grid RMS; model minus model"),
        ("rms_percent_of_R0", conclusions["rms_percent_of_R0"], "% of R0", "Not percentage of local modeled radius"),
        ("mean_absolute_difference", conclusions["mean_absolute_difference_r_ratio"], "R/R0", "Grid mean absolute difference"),
        ("p95_absolute_difference", conclusions["p95_absolute_difference_r_ratio"], "R/R0", "95th percentile on grid"),
        ("fraction_abs_difference_le_1percent_R0", conclusions["fraction_abs_delta_le_1percent_R0"], "fraction", "Threshold: abs(delta R/R0) <= 0.01"),
        ("fraction_abs_difference_le_2percent_R0", conclusions["fraction_abs_delta_le_2percent_R0"], "fraction", "Threshold: abs(delta R/R0) <= 0.02"),
        ("valid_grid_points", conclusions["valid_grid_points"], "points", "Not independent field observations"),
        ("largest_checked_abs_difference", conclusions["maximum_checked_absolute_difference_r_ratio"], "R/R0", "Sampled-beta extrema check; not certified global"),
        ("largest_checked_percent_of_R0", conclusions["maximum_checked_percent_of_R0"], "% of R0", "Sampled-beta extrema check"),
        ("largest_checked_beta", conclusions["maximum_checked_beta_deg"], "degrees", "Angle of maximum absolute difference"),
        ("largest_checked_theta", conclusions["maximum_checked_theta_deg"], "degrees", "Angle of maximum absolute difference"),
        ("endpoint_Oliveira", conclusions["endpoint_oliveira_r_ratio"], "R/R0", "At beta=theta=beta_max"),
        ("endpoint_Hsu", conclusions["endpoint_hsu_r_ratio"], "R/R0", "At beta=theta=beta_max"),
        ("reference_R0", conclusions["r0_m_used_for_illustration"], "m", "Illustrative value if --r0-m omitted"),
        ("field_validation_performed", False, "boolean", "Model agreement is not validation"),
    ])
    save("coefficient_polynomials.csv",
         ["model", "display_coefficient", "source_coefficient", "beta_power", "value"],
         ((model.name, f"C{i+1}", f"C{i}", power, value)
          for model in MODELS for i, series in enumerate(model.polynomials)
          for power, value in enumerate(series)))
    save("coefficient_comparison.csv",
         ["beta_deg"] + [f"{prefix}_C{j}" for prefix in ("Oliveira", "Hsu", "delta") for j in (1, 2, 3)],
         ((beta, *o, *h, *(o - h)) for beta, o, h in zip(data["beta"], data["C_O"], data["C_H"])))
    save("boundary_diagnostics.csv",
         ["beta_deg", "Oliveira_endpoint_ratio", "Hsu_endpoint_ratio",
          "Oliveira_sum_minus_1", "Hsu_sum_minus_1", "endpoint_delta_r"],
         ((b, 1. + o, 1. + h, o, h, o - h)
          for b, o, h in zip(data["beta"], data["boundary_O"], data["boundary_H"])))

    indices = np.where(data["branch"])
    dr_o = MODELS[0].sensitivities(data["T"], data["B"])
    dr_h = MODELS[1].sensitivities(data["T"], data["B"])
    grid_header = ["beta_deg", "theta_deg", "q", "Oliveira_r_ratio", "Hsu_r_ratio",
                   "delta_r_ratio", "abs_delta_r_ratio", "symmetric_difference_percent",
                   "Oliveira_dr_dbeta_per_deg", "Hsu_dr_dbeta_per_deg",
                   "Oliveira_dr_dtheta_per_deg", "Hsu_dr_dtheta_per_deg"]
    if config.r0_m is not None:
        grid_header.append("radial_separation_m")

    def grid_rows() -> Iterable[tuple[Any, ...]]:
        for row, column in zip(*indices):
            b, t = data["B"][row, column], data["T"][row, column]
            delta = data["delta"][row, column]
            values = (b, t, b / t, data["O"][row, column], data["H"][row, column],
                      delta, abs(delta), data["symmetric_percent"][row, column],
                      dr_o[0][row, column], dr_h[0][row, column],
                      dr_o[1][row, column], dr_h[1][row, column])
            if config.r0_m is not None:
                values += (config.r0_m * delta,)
            yield values

    save("model_comparison_grid.csv", grid_header, grid_rows())
    save("hsu_fit_residuals.csv",
         ["beta_deg", "display_coefficient", "source_coefficient", "observed", "fitted",
          "residual_fitted_minus_observed", "leverage", "standardized_residual",
          "cooks_distance", "leave_one_out_prediction_minus_observed"],
         ((b, f"C{j+1}", f"C{j}", diag["hsu_observed"][i, j], diag["hsu_fitted"][i, j],
           diag["hsu_residual"][i, j], diag["leverage"][i],
           diag["standardized_residual"][i, j], diag["cooks"][i, j], diag["hsu_loo"][i, j])
          for i, b in enumerate(diag["hsu_beta"]) for j in range(3)))
    save("fit_statistics.csv",
         ["model", "display_coefficient", "source_coefficient", "status", "n_rows",
          "r_squared", "rmse", "mae", "max_abs", "sse", "loo_rmse"],
         ((name, f"C{j+1}", f"C{j}", status, count,
           *[metric.get(k, "") for k in ("r_squared", "rmse", "mae", "max_abs", "sse", "loo_rmse")])
          for name, status, count, metrics in (
              ("Oliveira2010", "quoted from supplied fit report; raw rows unavailable", 48, OLIVEIRA_REPORTED_FIT),
              ("Hsu1989", "recomputed from 15 supplied table observations", 15, diag["hsu_fit_metrics"]))
          for j, metric in enumerate(metrics)))

    def by_axis_rows() -> Iterable[tuple[Any, ...]]:
        for label, angles, arrays in (("beta", data["beta"], data["delta"].T),
                                     ("theta", data["theta"], data["delta"])):
            for angle, values in zip(angles, arrays):
                metric = descriptive_metrics(values)
                yield (label, angle, *[metric.get(k, "") for k in
                                      ("count", "mean", "rms", "mean_abs", "p95_abs", "max_abs")])

    save("difference_statistics_by_angle.csv",
         ["conditioning_angle", "angle_deg", "grid_count", "mean_delta", "rms_delta",
          "mean_abs_delta", "p95_abs_delta", "max_abs_delta"], by_axis_rows())
    save("sampled_difference_extrema.csv",
         ["kind", "beta_deg", "theta_deg", "delta_r_ratio", "method"],
         ((kind, item["beta_deg"], item["theta_deg"], item["delta_r"],
           "20001 beta samples; analytic q extrema, including theta=beta")
          for kind, item in diag["sampled_envelope"].items() if isinstance(item, dict)))
    return paths


class FigureWriter:
    """Save every chart as a PNG and a page in a vector PDF, then release it."""

    def __init__(self, config: Config, pdf: PdfPages):
        self.config = config
        self.pdf = pdf
        self.figures: list[dict[str, str]] = []

    def save(self, figure: Any, stem: str, caption: str) -> None:
        path = self.config.output_dir / f"{stem}.png"
        figure.savefig(path, dpi=self.config.dpi, facecolor="white", bbox_inches="tight")
        self.pdf.savefig(figure, facecolor="white", bbox_inches="tight")
        self.figures.append({"filename": path.name, "caption": caption})
        plt.close(figure)
        print(f"  [{len(self.figures):02d}] {path.name}", flush=True)


def configure_plot_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.titlesize": 12, "axes.labelsize": 11,
        "figure.titlesize": 17, "legend.fontsize": 9.5,
        "xtick.labelsize": 10, "ytick.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": .22, "grid.linewidth": .7,
        "lines.linewidth": 2.1, "savefig.facecolor": "white",
        "figure.facecolor": "white", "axes.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42,
    })




# ---------------------------------------------------------------------------
# Plot suite
# ---------------------------------------------------------------------------


def _plot_grid(rows, columns, title, subtitle="", footer="", figsize=None):
    """Create a consistent, publication-friendly figure with reserved text bands."""
    if figsize is None:
        figsize = (14.6, 5.2 + 3.1 * (rows - 1))
    fig, axes = plt.subplots(rows, columns, figsize=figsize, squeeze=False)
    fig.subplots_adjust(left=0.075, right=0.965, top=0.79 if rows == 1 else 0.88,
                        bottom=0.16 if rows == 1 else 0.135,
                        hspace=0.43, wspace=0.33)
    fig.suptitle(title, x=0.075, y=0.975, ha="left", fontsize=19, fontweight="bold")
    if subtitle:
        fig.text(0.075, 0.905 if rows == 1 else 0.935, subtitle,
                 ha="left", va="top", fontsize=10.5, color="#425266")
    if footer:
        from textwrap import fill
        footer = fill(footer, width=max(95, int(figsize[0] * 13)), break_long_words=False)
        fig.text(0.075, 0.028, footer, ha="left", va="bottom", fontsize=9,
                 color="#536171")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(True, color="#DDE3E8", linewidth=0.65, alpha=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=9.5)
    return fig, axes


def _model_line(ax, model, x, y, **kwargs):
    return ax.plot(x, y, color=model.color, linestyle=model.linestyle,
                   linewidth=2.3, label=model.name, **kwargs)


def _coefficient_title(index):
    return rf"$C_{index + 1}$ (source $C_{index}$)"


def _symmetric_limit(values, floor=1e-12):
    finite = np.asarray(values)[np.isfinite(values)]
    return max(float(np.max(np.abs(finite))) if finite.size else floor, floor)


def _map_panel(fig, ax, data, values, title, cmap="viridis", norm=None,
               colorbar_label=r"$R/R_0$", vmin=None, vmax=None):
    artist = ax.pcolormesh(data["B"], data["T"], np.ma.masked_invalid(values),
                           shading="auto", cmap=cmap, norm=norm,
                           vmin=vmin, vmax=vmax, rasterized=True)
    ax.set(title=title, xlabel=r"$\beta$ (degrees)", ylabel=r"$\theta$ (degrees)")
    ax.grid(False)
    ax.plot(data["beta"], data["beta"], color="#596573", linewidth=0.8,
            linestyle=":")
    ax.set_xlim(float(data["beta"][0]), float(data["beta"][-1]))
    ax.set_ylim(float(data["theta"][0]), float(data["theta"][-1]))
    colorbar = fig.colorbar(artist, ax=ax, pad=0.025, fraction=0.048)
    colorbar.set_label(colorbar_label, fontsize=10)
    colorbar.ax.tick_params(labelsize=9)
    return artist


def _planform(ax, models, beta, theta_max, points=650, show_legend=True):
    theta = np.linspace(float(beta), float(theta_max), points)
    angle = np.deg2rad(theta - beta)
    coords = []
    for model in models:
        radius = model.radius(theta, beta)
        radius = np.where(radius >= 0.0, radius, np.nan)
        x, y = radius * np.cos(angle), radius * np.sin(angle)
        _model_line(ax, model, x, y)
        ax.scatter(x[0], y[0], s=35, facecolor=model.color, edgecolor="white",
                   linewidth=0.7, zorder=5)
        coords.append((x, y))
    ax.plot([0.0, 1.0], [0.0, 0.0], color="#8792A2", linestyle=":", linewidth=1.1)
    ax.scatter([0.0], [0.0], marker="+", s=70, color="#26384B", zorder=6)
    ax.scatter([1.0], [0.0], marker="x", s=43, color="#26384B", zorder=6)
    ax.annotate("H", (0.0, 0.0), xytext=(-12, -15), textcoords="offset points",
                fontsize=10, fontweight="bold")
    ax.annotate("E", (1.0, 0.0), xytext=(5, -15), textcoords="offset points",
                fontsize=10, fontweight="bold")
    ax.set(xlabel=r"$x/R_0$", ylabel=r"$y/R_0$")
    ax.set_aspect("equal", adjustable="box")
    if show_legend:
        ax.legend(fontsize=9, loc="best")
    return coords


def generate_executive_figure(
    summary: dict[str, Any], config: Config, writer: FigureWriter,
) -> None:
    """Put the engineering interpretation first in the PDF and plot viewer."""
    from matplotlib.patches import Rectangle
    from textwrap import fill

    fig = plt.figure(figsize=(14.6, 8.5), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    fig.text(.065, .945, "Oliveira2010 vs Hsu1989", fontsize=23,
             fontweight="bold", color="#172C39", va="top")
    fig.text(.065, .890, "EXECUTIVE COMPARISON | THE PREDICTED SHAPES ARE VERY SIMILAR"
             if summary["classification"] == "VERY SIMILAR"
             else f"EXECUTIVE COMPARISON | {summary['classification']}",
             fontsize=13.2, fontweight="bold", color="#00857D", va="top")
    fig.text(.065, .851,
             f"Shared fitted interval: {config.beta_min:g}–{config.beta_max:g}° in beta; "
             f"beta ≤ theta ≤ {config.theta_max:g}°. Raw polynomial coefficients; identical controls.",
             fontsize=10.5, color="#516272", va="top")

    panels = (
        ("GRID RMS DIFFERENCE", f"{summary['rms_percent_of_R0']:.2f}%",
         "of nominal control radius R0"),
        ("GRID PAIRS WITHIN 1%", f"{100*summary['fraction_abs_delta_le_1percent_R0']:.1f}%",
         "of valid angle pairs"),
        ("LARGEST CHECKED DIFFERENCE", f"{summary['maximum_checked_percent_of_R0']:.2f}%",
         "of R0; extrema over sampled angle domain"),
    )
    for i, (heading, large, small) in enumerate(panels):
        x = .065 + .302 * i
        ax.add_patch(Rectangle((x, .614), .281, .190, transform=ax.transAxes,
                               facecolor="#F4F8FA", edgecolor="#D8E2E8",
                               linewidth=1.05))
        fig.text(x + .018, .780, heading, fontsize=10.5, color="#41586B",
                 fontweight="bold", va="top")
        fig.text(x + .018, .735, large, fontsize=31, fontweight="bold",
                 color="#00857D" if i != 2 else "#BD6630", va="top")
        fig.text(x + .018, .655, small, fontsize=9.5, color="#516272", va="top")

    sections = [
        ("Interpretation", summary["executive_summary"]),
        ("Why coefficient differences matter less", "The three fitted coefficient "
         "differences partly compensate after weighting by q=beta/theta "
         "and q². The resulting predicted radial curves agree more closely "
         "than a comparison of individual coefficients might suggest."),
        ("Where caution is needed", "The greatest checked difference is "
         f"{summary['maximum_checked_absolute_difference_r_ratio']:.5f} in R/R0 "
         f"at beta={summary['maximum_checked_beta_deg']:.2f}°, "
         f"theta={summary['maximum_checked_theta_deg']:.2f}°. "
         "At high beta, the fitted endpoint radii depart from the ideal value 1."),
        ("Engineering limitations", "Shared predictions do not prove physical "
         "accuracy against a surveyed shoreline. Control-point and wave "
         "direction uncertainty may be more important, but it has not "
         "been quantified. Field observations are necessary for model ranking."),
    ]
    y = .571
    for heading, content in sections:
        fig.text(.065, y, heading, fontsize=12, color="#1B3948",
                 fontweight="bold", va="top")
        fig.text(.065, y - .030, fill(content, 125), fontsize=10.3,
                 color="#344A5C", linespacing=1.45, va="top")
        y -= .113

    fig.text(.065, .057,
             (f"ILLUSTRATION: R0 = {summary['r0_m_used_for_illustration']:g} m "
              f"{'(assumed)' if summary['r0_is_illustrative'] else '(specified)'}; "
              f"RMS radial difference = {summary['r0_m_used_for_illustration'] * summary['rms_difference_r_ratio']:.2f} m; "
              f"largest checked = {summary['r0_m_used_for_illustration'] * summary['maximum_checked_absolute_difference_r_ratio']:.2f} m. "),
             fontsize=10.1, color="#516272", va="center")
    fig.text(.065, .023, "Descriptive mathematical comparison, not a shoreline validation or design acceptance criterion.",
             fontsize=9.4, color="#7B4C42", va="center")
    writer.save(fig, "00_executive_conclusions", "Executive summary: strong agreement of predicted planforms, quantified differences, localized maximum, and field-validation caveats.")


def generate_figures(models, data, diagnostics, config, writer, conclusions):
    """Save 22 complementary comparison and numerical-diagnostic figures."""
    oliveira, hsu = models
    beta = data["beta"]
    delta_coeff = data["C_O"] - data["C_H"]
    difference_color = "#7254A3"
    coefficient_colors = ("#3B6FA6", "#A85C36", "#6B559A")
    mapping = "Displayed C1, C2, C3 correspond to source C0, C1, C2 (constant, linear, quadratic)."
    common = (f"Shared fitted beta interval: {config.beta_min:g} to {config.beta_max:g} degrees. "
              "Differences are Oliveira2010 minus Hsu1989.")
    domain = (r"Curved branch $\theta\geq\beta$; sampled mathematical domain, not field validation. "
              "White regions are excluded.")
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 11.5, "axes.labelsize": 10.5,
        "legend.frameon": True, "legend.framealpha": 0.94,
        "legend.edgecolor": "#DFE4EA", "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42,
    })

    # 01. Immediate model comparison at a representative beta.
    reference_beta = float(np.clip(45.0, config.beta_min, config.beta_max))
    theta = np.linspace(reference_beta, config.theta_max, 800)
    fig, axes = _plot_grid(1, 2, "Oliveira2010 and Hsu1989: the two model curves",
                          rf"Representative $\beta={reference_beta:g}^\circ$; "
                          r"$R/R_0=C_1+C_2q+C_3q^2$, $q=\beta/\theta$.",
                          (f"Model outputs are {conclusions['classification'].lower()} on this grid: RMS difference "
                           f"{conclusions['rms_percent_of_R0']:.2f}% of R0 on the comparison grid. "
                           "Both fits are unchanged; endpoints not snapped."),
                          figsize=(14.6, 6.2))
    fig.subplots_adjust(top=0.81, bottom=0.15)
    for model in models:
        _model_line(axes[0, 0], model, theta, model.radius(theta, reference_beta))
    axes[0, 0].set(xlabel=r"$\theta$ (degrees)", ylabel=r"$R/R_0$",
                   title="Radius along the curved branch")
    axes[0, 0].legend()
    _planform(axes[0, 1], models, reference_beta, config.theta_max)
    axes[0, 1].set_title("Normalized beach planform: identical controls")
    writer.save(fig, "01_model_comparison", "Direct radial and Cartesian comparison of both supplied models at a common beta.")

    # 02. Three coefficients over each source's own fitted coverage.
    fig, axes = _plot_grid(1, 3, "Coefficient functions over their fitted intervals",
                          "Supplied sixth-degree fits; dots: Hsu table rows; shading: common comparison range.", mapping)
    for index, ax in enumerate(axes.flat):
        ax.axvspan(config.beta_min, config.beta_max, color="#ECF2F6", zorder=0)
        for model in models:
            native_beta = np.linspace(model.beta_min, model.beta_max, 650)
            _model_line(ax, model, native_beta, model.coefficients(native_beta)[:, index])
        ax.scatter(diagnostics["hsu_beta"], diagnostics["hsu_observed"][:, index],
                   s=22, facecolors="white", edgecolors=hsu.color, linewidths=1,
                   zorder=5, label="Hsu source table")
        ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)", ylabel="Coefficient")
        if index == 0:
            ax.legend(fontsize=8.5)
    writer.save(fig, "02_coefficient_functions", "Coefficient functions on their own data coverage; pale shading identifies the common comparison interval.")

    # 03. Direct coefficient differences, without ratios across zero.
    fig, axes = _plot_grid(1, 3, "Coefficient differences on the common interval", common, mapping)
    for index, ax in enumerate(axes.flat):
        ax.plot(beta, delta_coeff[:, index], color=difference_color, linewidth=2.3)
        ax.fill_between(beta, 0, delta_coeff[:, index], color=difference_color, alpha=0.12)
        ax.axhline(0, color="#6B7683", linewidth=0.8)
        ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)",
               ylabel=rf"$\Delta C_{index + 1}$")
    writer.save(fig, "03_coefficient_differences", "Signed coefficient differences without unstable division by coefficients that cross zero.")

    # 04. Coefficient derivatives.
    fig, axes = _plot_grid(2, 3, "How quickly the coefficient functions change",
                          "Analytical derivatives of the supplied sixth-degree polynomials; angles remain in degrees.",
                          mapping, figsize=(14.6, 8.4))
    for derivative in (1, 2):
        for index, ax in enumerate(axes[derivative - 1]):
            for model in models:
                _model_line(ax, model, beta, model.coefficients(beta, derivative=derivative)[:, index])
            ax.axhline(0, color="#8B95A0", linewidth=0.7)
            ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)",
                   ylabel="First derivative (1/degree)" if derivative == 1 else "Second derivative (1/degree²)")
            if derivative == 1 and index == 0:
                ax.legend(fontsize=9)
    writer.save(fig, "04_coefficient_derivatives", "Analytical first and second derivatives reveal coefficient sensitivity and curvature.")

    # 05. Junction / endpoint closure.
    fig, axes = _plot_grid(1, 2, "Does the curve pass through the nominal control point?",
                          r"At $\theta=\beta$, $R/R_0=C_1+C_2+C_3$. The ideal control-point value is 1.",
                          "No coefficient normalization or endpoint snapping is applied. " + mapping,
                          figsize=(14.6, 5.2))
    for model, coefficients, boundary in (
        (oliveira, data["C_O"], data["boundary_O"]),
        (hsu, data["C_H"], data["boundary_H"]),
    ):
        _model_line(axes[0, 0], model, beta, np.sum(coefficients, axis=1))
        _model_line(axes[0, 1], model, beta, 100.0 * boundary)
    axes[0, 0].axhline(1, color="#687586", linestyle=":", linewidth=1.1)
    axes[0, 1].axhline(0, color="#687586", linestyle=":", linewidth=1.1)
    axes[0, 0].set(title="Calculated starting radius", xlabel=r"$\beta$ (degrees)",
                   ylabel=r"$R(\beta)/R_0$")
    axes[0, 1].set(title="Signed displacement from E", xlabel=r"$\beta$ (degrees)",
                   ylabel=r"$100\,[R(\beta)/R_0-1]$ (%)")
    axes[0, 0].legend()
    writer.save(fig, "05_endpoint_closure", "Departure from the nominal control radius caused by the unconstrained coefficient fits.")

    # 06. Radial profiles at selected beta values.
    selected_beta = list(data["profiles_beta"])
    columns = 3
    rows = max(1, int(np.ceil(len(selected_beta) / columns)))
    fig, axes = _plot_grid(rows, columns, "Radius profiles for selected bay obliquities",
                          common, r"Each profile begins at $\theta=\beta$. The curves use raw, unnormalized radii.",
                          figsize=(14.6, 4.2 + 3.0 * (rows - 1)))
    for index, ax in enumerate(axes.flat):
        if index >= len(selected_beta):
            ax.set_visible(False)
            continue
        b = float(selected_beta[index])
        t = np.linspace(b, config.theta_max, 650)
        for model in models:
            _model_line(ax, model, t, model.radius(t, b))
        ax.axhline(0, color="#8893A1", linewidth=0.7)
        ax.set(title=rf"$\beta={b:g}^\circ$", xlabel=r"$\theta$ (degrees)", ylabel=r"$R/R_0$")
        if index == 0:
            ax.legend(fontsize=9)
    writer.save(fig, "06_radius_profiles_by_beta", "Paired radius profiles for representative beta values in the common range.")

    # 07. Hsu Figure-4-style families in the beta direction.
    selected_theta = list(data["profiles_theta"])
    if not selected_theta:
        selected_theta = list(np.linspace(config.beta_min, config.theta_max, 4)[1:])
    columns = 3
    rows = max(1, int(np.ceil(len(selected_theta) / columns)))
    fig, axes = _plot_grid(rows, columns, "Model families at fixed shoreline angles",
                          r"$R/R_0$ versus $\beta$, with a separate panel for each $\theta$.",
                          r"Only the common beta interval and the curved branch $\beta\leq\theta$ are plotted.",
                          figsize=(14.6, 4.0 + 2.8 * (rows - 1)))
    for index, ax in enumerate(axes.flat):
        if index >= len(selected_theta):
            ax.set_visible(False)
            continue
        t = float(selected_theta[index])
        b = beta[beta <= t]
        for model in models:
            _model_line(ax, model, b, model.radius(t, b))
        ax.set(title=rf"$\theta={t:g}^\circ$", xlabel=r"$\beta$ (degrees)", ylabel=r"$R/R_0$")
        if index == 0:
            ax.legend(fontsize=8.5)
    writer.save(fig, "07_radius_profiles_by_theta", "Fixed-theta model families show variation with beta, restricted to the common curved-branch domain.")

    # 08. Planform comparisons with a common origin and reference orientation.
    columns = 3
    rows = max(1, int(np.ceil(len(selected_beta) / columns)))
    fig, axes = _plot_grid(rows, columns, "Normalized beach shapes under identical geometry",
                          r"$H=(0,0)$, nominal $E=(1,0)$; $\phi=\theta-\beta$, $x/R_0=r\cos\phi$, $y/R_0=r\sin\phi$.",
                          "Both models share the same controls and orientation. "
                          "Nonnegative radii only in this geometric view; endpoint values remain unmodified.",
                          figsize=(14.6, 4.8 + 3.7 * (rows - 1)))
    all_coords = []
    for index, ax in enumerate(axes.flat):
        if index >= len(selected_beta):
            ax.set_visible(False)
            continue
        b = float(selected_beta[index])
        all_coords.extend(_planform(ax, models, b, config.theta_max, show_legend=index == 0))
        ax.set_title(rf"$\beta={b:g}^\circ$")
    finite_x = np.concatenate([x[np.isfinite(x)] for x, _ in all_coords] + [np.array([0., 1.])])
    finite_y = np.concatenate([y[np.isfinite(y)] for _, y in all_coords] + [np.array([0.])])
    x_min, x_max = float(finite_x.min()), float(finite_x.max())
    y_min, y_max = float(finite_y.min()), float(finite_y.max())
    pad = 0.09 * max(x_max - x_min, y_max - y_min, 1.0)
    for ax in axes.flat:
        if ax.get_visible():
            ax.set_xlim(x_min - pad, x_max + pad)
            ax.set_ylim(y_min - pad, y_max + pad)
    writer.save(fig, "08_normalized_planforms", "Common-axis planform overlays use identical H, E, scale and orientation for both models.")

    # 09. Raw radii on the same color scale.
    fig, axes = _plot_grid(1, 2, "Both model surfaces on one color scale", common,
                          domain, figsize=(14.6, 6.7))
    radii = np.concatenate((data["O"][np.isfinite(data["O"])], data["H"][np.isfinite(data["H"])]))
    norm = Normalize(vmin=float(radii.min()), vmax=float(radii.max()))
    _map_panel(fig, axes[0, 0], data, data["O"], oliveira.name, norm=norm)
    _map_panel(fig, axes[0, 1], data, data["H"], hsu.name, norm=norm)
    writer.save(fig, "09_model_surfaces", "Radius surfaces share identical color limits to support direct comparison.")

    # 10. Absolute and signed radius differences.
    fig, axes = _plot_grid(1, 2, "Where the predicted radii differ", common,
                          domain + " These are between-model differences, not observed prediction errors.",
                          figsize=(14.6, 6.7))
    limit = _symmetric_limit(data["delta"])
    _map_panel(fig, axes[0, 0], data, data["delta"], "Signed difference",
               cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-limit, vcenter=0., vmax=limit),
               colorbar_label=r"$\Delta(R/R_0)$")
    _map_panel(fig, axes[0, 1], data, np.abs(data["delta"]), "Absolute difference",
               cmap="magma", vmin=0., vmax=limit, colorbar_label=r"$|\Delta(R/R_0)|$")
    writer.save(fig, "10_radius_difference_maps", "Signed and absolute radius-ratio differences over the common angle grid.")

    # 11. Relative difference with an explicit small-denominator rule.
    fig, axes = _plot_grid(1, 1, "Symmetric relative difference between models",
                          r"$200\,(r_O-r_H)/(|r_O|+|r_H|)$, with $r=R/R_0$; neither model is treated as truth.",
                          "Values are omitted where |rO| + |rH| < 0.02. " + domain,
                          figsize=(11.8, 6.8))
    limit = _symmetric_limit(data["symmetric_percent"])
    _map_panel(fig, axes[0, 0], data, data["symmetric_percent"], "Symmetric percentage difference",
               cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-limit, vcenter=0., vmax=limit),
               colorbar_label="Symmetric difference (%)")
    writer.save(fig, "11_symmetric_percentage_difference", "Symmetric relative differences use an explicit denominator threshold and no model as an accuracy reference.")

    # 12. Equality diagnostic using density rather than saturated scatter.
    valid = np.isfinite(data["O"]) & np.isfinite(data["H"])
    o = data["O"][valid]
    h = data["H"][valid]
    delta = o - h
    fig, axes = _plot_grid(1, 2, "Agreement diagnostics for the sampled model grid",
                          "Every valid angle-grid point is included. Density is the number of sampled parameter pairs.",
                          "Identity-line agreement is not validation against measured shorelines. "
                          "Grid density depends on the selected angle sampling.", figsize=(14.6, 6.0))
    ax = axes[0, 0]
    hb = ax.hexbin(h, o, gridsize=75, mincnt=1, bins="log", cmap="viridis", rasterized=True)
    low, high = min(h.min(), o.min()), max(h.max(), o.max())
    ax.plot([low, high], [low, high], color="#AB4B3B", linestyle=":", linewidth=1.5, label="Equality")
    ax.set(xlabel="Hsu1989: R/R0", ylabel="Oliveira2010: R/R0", title="Model against model")
    ax.legend(fontsize=9)
    ax.set_aspect("equal", adjustable="box")
    fig.colorbar(hb, ax=ax, label="Grid-point count (log scale)", pad=0.025, fraction=0.048)
    ax = axes[0, 1]
    hb = ax.hexbin((o + h) / 2., delta, gridsize=65, mincnt=1, bins="log", cmap="viridis", rasterized=True)
    ax.axhline(0., color="#AB4B3B", linestyle=":", linewidth=1.3)
    ax.set(xlabel="Mean radius ratio of both models", ylabel=r"$\Delta(R/R_0)$",
           title="Difference versus mean")
    fig.colorbar(hb, ax=ax, label="Grid-point count (log scale)", pad=0.025, fraction=0.048)
    writer.save(fig, "12_model_agreement", "Model equality and difference-versus-mean diagnostics, with grid-point densities and no inferential agreement limits.")

    # 13. Distribution diagnostics of deterministic differences.
    fig, axes = _plot_grid(1, 2, "Distribution of model differences across the sampled grid",
                          common, "These deterministic grid values are not independent observations. "
                          "The histogram and empirical distribution describe this sampling only.", figsize=(14.6, 5.4))
    axes[0, 0].hist(delta, bins=65, color=difference_color, alpha=0.85, edgecolor="white", linewidth=0.3)
    axes[0, 0].axvline(0., color="#3C495A", linestyle=":", linewidth=1.1)
    axes[0, 0].axvline(float(np.mean(delta)), color="#A9602B", linestyle="--", linewidth=1.3, label="Mean difference")
    axes[0, 0].set(xlabel=r"$\Delta(R/R_0)$", ylabel="Angle-grid points", title="Signed differences")
    axes[0, 0].legend(fontsize=9)
    absolute = np.sort(np.abs(delta))
    cumulative = np.arange(1, absolute.size + 1) / absolute.size
    axes[0, 1].plot(absolute, cumulative, color=difference_color, linewidth=2.2)
    axes[0, 1].axhline(0.95, color="#A9602B", linestyle=":", linewidth=1.2, label="95% of sampled points")
    axes[0, 1].set(xlabel=r"$|\Delta(R/R_0)|$", ylabel="Cumulative fraction", title="Absolute-difference distribution", ylim=(0, 1.02))
    axes[0, 1].legend(fontsize=9, loc="lower right")
    writer.save(fig, "13_difference_distributions", "Histogram and empirical cumulative distribution of deterministic model differences on the selected grid.")

    # 14. Metrics aggregated along parameter directions.
    fig, axes = _plot_grid(1, 2, "Difference magnitude by beta and theta",
                          "RMSE, mean absolute difference and maximum absolute difference are computed between the two models.",
                          "Unweighted summaries of valid samples only. Different beta/theta slices contain different numbers of samples.",
                          figsize=(14.6, 5.4))
    metric_styles = (("RMS difference", "#7154A5", "-"),
                     ("Mean absolute difference", "#3D7D83", "--"),
                     ("Maximum absolute difference", "#B36335", ":"))
    for ax, direction, x, xlabel in ((axes[0, 0], 0, beta, r"$\beta$ (degrees)"),
                                      (axes[0, 1], 1, data["theta"], r"$\theta$ (degrees)")):
        values = (np.sqrt(np.nanmean(data["delta"] ** 2, axis=direction)),
                  np.nanmean(np.abs(data["delta"]), axis=direction),
                  np.nanmax(np.abs(data["delta"]), axis=direction))
        for (label, color, style), y in zip(metric_styles, values):
            ax.plot(x, y, color=color, linestyle=style, linewidth=2.1, label=label)
        ax.set(xlabel=xlabel, ylabel="Radius-ratio difference", title="Grouped by beta" if direction == 0 else "Grouped by theta")
        ax.legend(fontsize=8.5)
    writer.save(fig, "14_difference_metrics_by_angle", "RMS, mean absolute and maximum absolute differences grouped by each sampled angle.")

    # 15. Beta sensitivity with theta held fixed.
    sensitivities = [model.sensitivities(data["T"], data["B"]) for model in models]
    fig, axes = _plot_grid(1, 2, "Sensitivity of the radius ratio to beta",
                          r"Analytical $\partial(R/R_0)/\partial\beta$ at fixed $\theta$; includes variation of coefficients and of $q$.",
                          "Units are per degree. This isolates equation sensitivity and does not represent moving H, E or W.",
                          figsize=(14.6, 6.7))
    values = [np.where(data["branch"], value[0], np.nan) for value in sensitivities]
    limit = max(_symmetric_limit(value) for value in values)
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0., vmax=limit)
    for ax, model, value in zip(axes.flat, models, values):
        _map_panel(fig, ax, data, value, model.name, cmap="RdBu_r", norm=norm,
                   colorbar_label=r"$\partial r/\partial\beta$ (1/degree)")
    writer.save(fig, "15_beta_sensitivity", "Analytical beta sensitivity of both coefficient-based models at fixed theta.")

    # 16. Theta sensitivity with beta fixed.
    fig, axes = _plot_grid(1, 2, "Sensitivity of the radius ratio to theta",
                          r"Analytical $\partial(R/R_0)/\partial\theta$ at fixed $\beta$.",
                          "Units are per degree. Identical color limits are used for both models; raw derivatives are retained.",
                          figsize=(14.6, 6.7))
    values = [np.where(data["branch"], value[1], np.nan) for value in sensitivities]
    low = min(float(np.nanmin(value)) for value in values)
    high = max(float(np.nanmax(value)) for value in values)
    norm = Normalize(vmin=low, vmax=high)
    for ax, model, value in zip(axes.flat, models, values):
        _map_panel(fig, ax, data, value, model.name, cmap="viridis", norm=norm,
                   colorbar_label=r"$\partial r/\partial\theta$ (1/degree)")
    writer.save(fig, "16_theta_sensitivity", "Analytical theta sensitivities on a common color scale.")

    # 17. Coefficient-wise contributions to the output discrepancy.
    fig, axes = _plot_grid(rows=max(1, int(np.ceil(len(selected_beta) / 3))), columns=3,
                          title="Which coefficients create the model difference?",
                          subtitle=r"$\Delta r=\Delta C_1+q\,\Delta C_2+q^2\,\Delta C_3$; the colored terms sum exactly to the black line.",
                          footer=mapping, figsize=(14.6, 7.8))
    for index, ax in enumerate(axes.flat):
        if index >= len(selected_beta):
            ax.set_visible(False)
            continue
        b = float(selected_beta[index])
        t = np.linspace(b, config.theta_max, 650)
        q = b / t
        dc = oliveira.coefficients(b) - hsu.coefficients(b)
        terms = (np.full_like(t, dc[0]), q * dc[1], q * q * dc[2])
        labels = (r"$\Delta C_1$", r"$q\,\Delta C_2$", r"$q^2\,\Delta C_3$")
        for term, color, label in zip(terms, coefficient_colors, labels):
            ax.plot(t, term, linewidth=1.6, color=color, label=label)
        ax.plot(t, sum(terms), color="#26384B", linewidth=2.3, label=r"Total $\Delta r$")
        ax.axhline(0., color="#8993A0", linewidth=0.7)
        ax.set(title=rf"$\beta={b:g}^\circ$", xlabel=r"$\theta$ (degrees)", ylabel="Contribution to radius difference")
        if index == 0:
            ax.legend(fontsize=8, ncols=2)
    writer.save(fig, "17_coefficient_contributions", "Exact decomposition of the model-output difference into constant, linear and quadratic coefficient contributions.")

    # 18. Genuine source-table residuals, Hsu only.
    hsu_beta = diagnostics["hsu_beta"]
    fig, axes = _plot_grid(1, 3, "Hsu1989: residuals against the supplied source table",
                          "Residual = supplied polynomial fit minus observed table coefficient; 15 source rows per coefficient.",
                          "Only Hsu table rows were supplied. Oliveira pointwise fit residuals cannot be reconstructed. " + mapping,
                          figsize=(14.6, 5.2))
    for index, ax in enumerate(axes.flat):
        residual = diagnostics["hsu_residual"][:, index]
        ax.axhline(0., color="#5D6A7A", linewidth=1.0)
        ax.vlines(hsu_beta, 0., residual, color=hsu.color, linewidth=1.4, alpha=0.75)
        ax.scatter(hsu_beta, residual, color=hsu.color, s=31, zorder=4)
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        ax.set(title=f"{_coefficient_title(index)}; RMSE = {rmse:.3g}", xlabel=r"$\beta$ (degrees)", ylabel="Fit minus observed")
    writer.save(fig, "18_hsu_table_residuals", "Recomputed Hsu fit residuals at the actual 15 supplied table rows; no invented Oliveira observations.")

    # 19. Source-table agreement and residual QQ view.
    fig, axes = _plot_grid(2, 3, "Hsu1989: fitted values and residual shape",
                          "Upper row: coefficients against their source observations. Lower row: standardized residual quantiles.",
                          "Q-Q panels are descriptive only: 15 rounded table entries are not a sample of independent shoreline measurements. " + mapping,
                          figsize=(14.6, 8.6))
    for index in range(3):
        observed = diagnostics["hsu_observed"][:, index]
        fitted = diagnostics["hsu_fitted"][:, index]
        ax = axes[0, index]
        low, high = min(observed.min(), fitted.min()), max(observed.max(), fitted.max())
        ax.plot([low, high], [low, high], linestyle=":", color="#6B7786", linewidth=1.1)
        ax.scatter(observed, fitted, color=hsu.color, s=36, edgecolor="white", linewidth=0.4)
        ax.set(title=_coefficient_title(index), xlabel="Observed table coefficient", ylabel="Supplied fit")
        ax = axes[1, index]
        theoretical = diagnostics["qq_theoretical"]
        standardized = np.sort(diagnostics["standardized_residual"][:, index])
        ax.plot(theoretical, theoretical, linestyle=":", color="#6B7786", linewidth=1.1, label="Standard-normal reference")
        ax.scatter(theoretical, standardized, color=hsu.color, s=31)
        ax.set(xlabel="Standard-normal quantile", ylabel="Standardized residual")
    writer.save(fig, "19_hsu_fit_and_qq", "Hsu observed-versus-fitted coefficients and descriptive standardized-residual Q-Q plots.")

    # 20. Regression leverage / influence.
    fig, axes = _plot_grid(2, 2, "Hsu1989: leverage and regression influence",
                          "Diagnostics of the degree-6 least-squares regression of 15 source rows (7 parameters per series).",
                          "Leverage depends on beta placement. Cook's distance is a descriptive influence measure, not a field-error probability.",
                          figsize=(14.6, 8.1))
    ax = axes[0, 0]
    ax.vlines(hsu_beta, 0., diagnostics["leverage"], color="#3E7299", linewidth=1.7)
    ax.scatter(hsu_beta, diagnostics["leverage"], color="#3E7299", s=30)
    ax.axhline(7. / 15., color="#7D8794", linestyle=":", linewidth=1.1, label="Mean leverage = 7/15")
    ax.set(title="Design leverage", xlabel=r"$\beta$ (degrees)", ylabel="Leverage", ylim=(0, 1.02))
    ax.legend(fontsize=9)
    for index, ax in enumerate(list(axes.flat)[1:]):
        values = diagnostics["cooks"][:, index]
        ax.vlines(hsu_beta, 0., values, color=hsu.color, linewidth=1.5)
        ax.scatter(hsu_beta, values, color=hsu.color, s=31)
        ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)", ylabel="Cook's distance")
    writer.save(fig, "20_hsu_leverage_influence", "Design leverage and per-coefficient Cook's distance for the Hsu source-table regression.")

    # 21. Leave-one-out diagnostic.
    fig, axes = _plot_grid(1, 3, "Hsu1989: leave-one-out prediction of source rows",
                          "Leave-one-out predictions are computed analytically for omitting each beta row in turn.",
                          "Endpoint omission requires extrapolation to that withheld endpoint. "
                          "LOO describes sensitivity to the table, not accuracy on real beaches. " + mapping,
                          figsize=(14.6, 5.3))
    for index, ax in enumerate(axes.flat):
        residual = diagnostics["hsu_residual"][:, index]
        omitted = diagnostics["hsu_loo"][:, index]
        ax.plot(hsu_beta, residual, color="#768799", linestyle="--", marker="o", markersize=4,
                linewidth=1.4, label="Full fit residual")
        ax.plot(hsu_beta, omitted, color=hsu.color, marker="s", markersize=4,
                linewidth=1.7, label="Leave-one-out error")
        ax.axhline(0., color="#586779", linewidth=0.8)
        ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)", ylabel="Prediction minus observed")
        if index == 0:
            ax.legend(fontsize=8.5)
    writer.save(fig, "21_hsu_leave_one_out", "Actual leave-one-out coefficient-prediction errors contrasted with in-sample residuals.")

    # 22. Separate interpolation choice from cross-model differences.
    fig, axes = _plot_grid(1, 3, "Hsu1989: polynomial versus table linear interpolation",
                          "Both curves use the same 15 supplied Hsu table rows. This diagnoses the software interpolation choice.",
                          "This figure is independent of Oliveira2010. Linear interpolation exactly reproduces the table rows. " + mapping,
                          figsize=(14.6, 5.3))
    native_beta = np.linspace(hsu.beta_min, hsu.beta_max, 701)
    fitted = hsu.coefficients(native_beta)
    for index, ax in enumerate(axes.flat):
        linear = np.interp(native_beta, hsu_beta, diagnostics["hsu_observed"][:, index])
        ax.plot(native_beta, fitted[:, index] - linear, color="#7254A3", linewidth=2.1)
        ax.scatter(hsu_beta, diagnostics["hsu_residual"][:, index], color=hsu.color, s=25, zorder=4,
                   label="At source rows")
        ax.axhline(0., color="#6D7989", linewidth=0.8)
        ax.set(title=_coefficient_title(index), xlabel=r"$\beta$ (degrees)",
               ylabel="Polynomial minus linear interpolation")
        if index == 0:
            ax.legend(fontsize=9)
    writer.save(fig, "22_hsu_interpolation_diagnostic", "Hsu sixth-degree polynomial versus piecewise-linear interpolation of the same table, without model conflation.")


def write_report(
    data: dict[str, Any], diag: dict[str, Any], config: Config,
    figures: list[dict[str, str]], tables: list[Path],
    conclusions: dict[str, Any],
) -> tuple[Path, Path]:
    """Record provenance, sampling, definitions and computed numerical results."""
    metrics = diag["model_difference_metrics"]
    envelope = diag["sampled_envelope"]
    lines = [
        "OLIVEIRA2010 AND HSU1989 - COEFFICIENT AND MODEL COMPARISON",
        "=" * 72,
        "",
        "EXECUTIVE CONCLUSIONS - DATA-DRIVEN MODEL AGREEMENT",
        "-" * 70,
        *[f"{i:02d}. {sentence}" for i, sentence in enumerate(conclusions["conclusions"], 1)],
        "",
        "The qualitative similarity label is descriptive, not a design",
        "acceptance criterion. All percentage-of-R0 figures use the nominal",
        "control radius, not an individual local predicted radius.",
        "",
        "1. NOTATION AND SOURCES",
        "Display: r = R/R0 = C1(beta) + C2(beta)*q + C3(beta)*q^2.",
        "q = beta/theta; beta and theta are in degrees.",
        "Display C1/C2/C3 correspond exactly to source C0/C1/C2.",
        "C1 is constant in q; C2 is linear in q; C3 is quadratic in q.",
        "There is no cubic term. Oliveira's alpha is denoted theta here.",
        "Each coefficient is a degree-six polynomial in beta in degrees.",
        "Coefficient arrays are stored in ascending powers and evaluated by Horner.",
        "",
        "These supplied polynomial fits are software-derived approximations to",
        "source coefficient tables, not polynomial equations from the original papers.",
        "No refitting, coefficient normalization or endpoint snapping is applied.",
        "",
        "2. COVERAGE AND CHOSEN COMPARISON GRID",
        "Oliveira coefficient data coverage: beta 22.19 to 88.29 degrees.",
        "Hsu coefficient data coverage: beta 10 to 80 degrees.",
        "Shared coefficient data coverage: beta 22.19 to 80 degrees.",
        f"Actual paired comparison: beta {config.beta_min:g} to {config.beta_max:g} degrees.",
        f"Rectangular grid: {config.n_beta} uniformly spaced beta nodes x "
        f"{config.n_theta} uniformly spaced theta nodes.",
        f"Theta grid: {config.beta_min:g} to {config.theta_max:g} degrees.",
        "Only theta >= beta is included in curved-branch comparisons.",
        f"Number of retained rectangular-grid points: {metrics['count']}.",
        "RMS, mean, percentiles and histogram counts weight these retained nodes equally.",
        "They depend on the chosen grid and angular extent, not on field sampling.",
        "Coefficient coverage is not independent physical validation of a beach model.",
        "The angular extent is a plotting choice. The supplied Baycraft README uses",
        "theta_max=150 degrees; run --theta-max 150 to use that extent instead.",
        "",
        "3. DIFFERENCE DEFINITIONS",
        "delta_r = r_Oliveira - r_Hsu (dimensionless).",
        "Fit residual everywhere in these new outputs = fitted - observed.",
        "This reverses the residual sign printed in the supplied Hsu output report.",
        "RMS difference = sqrt(mean(delta_r^2)); MAE difference = mean(abs(delta_r)).",
        "Symmetric percent difference = 200*delta_r/(abs(r_Oliveira)+abs(r_Hsu)).",
        "Percent values are omitted when the denominator is below 0.02.",
        "This percent is not a percent error with one model treated as ground truth.",
        "Radial separation at common beta/theta is R0*delta_r; it is not automatically",
        "the perpendicular or nearest-point separation between two shorelines.",
        "",
        "4. MODEL DIFFERENCES ON THE RETAINED RECTANGULAR GRID",
    ]
    for label, key in (("Mean signed difference", "mean"),
                       ("RMS difference", "rms"),
                       ("Mean absolute difference", "mean_abs"),
                       ("Median signed difference", "median"),
                       ("95th percentile absolute difference", "p95_abs"),
                       ("Maximum absolute sampled difference", "max_abs")):
        lines.append(f"{label:42s}: {metrics[key]:.12g}")
    lines += ["", "Extrema check including the theta=beta boundary exactly:",
              "20,001 beta samples; analytic quadratic extrema in q at each beta.",
              "This is not a certified continuous two-dimensional optimization."]
    for label in ("minimum", "maximum"):
        item = envelope[label]
        lines.append(
            f"{label.capitalize()} delta_r = {item['delta_r']:+.12g}; "
            f"beta = {item['beta_deg']:.8g} deg; theta = {item['theta_deg']:.8g} deg."
        )
    if config.r0_m is not None:
        maximum = max(abs(envelope[k]["delta_r"]) for k in ("minimum", "maximum"))
        lines += [f"Specified R0 = {config.r0_m:g} m.",
                  f"Largest absolute radial separation in the extrema check: "
                  f"{config.r0_m * maximum:.10g} m."]
    lines += ["", "5. COEFFICIENT DIFFERENCES ON THE COMPARISON BETA GRID",
              "Display   Source       Mean(O-H)          RMS(O-H)          Max abs(O-H)"]
    for j, item in enumerate(diag["coefficient_difference_metrics"]):
        lines.append(f"C{j+1:<8} C{j:<8} {item['mean']: .10e}   "
                     f"{item['rms']:.10e}   {item['max_abs']:.10e}")
    lines += ["", "6. ENDPOINT CLOSURE AND RADIAL BEHAVIOR",
              "At theta=beta, r = C1+C2+C3. The ideal control radius would give r=1.",
              "The displayed endpoint defect is C1+C2+C3-1; its sign is retained.",
              "Neither the polynomials nor plotted curves are renormalized."]
    for model, boundary_key, raw_key in zip(MODELS, ("boundary_O", "boundary_H"), ("O", "H")):
        boundary = data[boundary_key]
        raw = data[raw_key]
        finite = raw[np.isfinite(raw)]
        imin, imax = int(np.argmin(boundary)), int(np.argmax(boundary))
        lines += [
            f"{model.name} endpoint defect min {boundary[imin]:+.12g} at beta "
            f"{data['beta'][imin]:.8g} deg; max {boundary[imax]:+.12g} at beta "
            f"{data['beta'][imax]:.8g} deg.",
            f"{model.name} grid r range {finite.min():.12g} to {finite.max():.12g}; "
            f"{int(np.count_nonzero(finite < 0))} negative radii; "
            f"{int(np.count_nonzero(finite > 1))} radii greater than one.",
        ]
    lines += ["Negative raw radii, if requested with a longer angular extent, remain in",
              "the numerical data and diagnostics; Cartesian planforms omit them.",
              "A negative constant coefficient alone does not imply a negative radius.",
              "", "7. ANALYTICAL SENSITIVITIES", 
              "dr/dtheta = -beta/theta^2 * (C2+2*C3*q), at fixed beta.",
              "dr/dbeta = C1' + C2'*q + C3'*q^2 + (C2+2*C3*q)/theta, at fixed theta.",
              "All angular derivatives are per degree, with R0 held fixed.",
              "These local derivatives do not include changes in control-point location,",
              "R0, orientation, or a distribution of wave directions.",
              "", "8. HSU TABLE-FIT DIAGNOSTICS - RECOMPUTED",
              "The 15 rounded observations are the supplied Table 2 transcription.",
              "Residuals are fitted minus observed. RMSE divides SSE by 15.",
              "R_squared = 1-SSE/SST, using each coefficient's own source rows.",
              "Display Source       R_squared             RMSE          LOO RMSE"]
    for j, item in enumerate(diag["hsu_fit_metrics"]):
        lines.append(f"C{j+1:<6} C{j:<6} {item['r_squared']:.12f}   "
                     f"{item['rmse']:.10e}   {item['loo_rmse']:.10e}")
    lines += ["The degree-six design has p=7 parameters and n=15 observations (8 residual df).",
              "Leverage h_j is obtained from QR of scaled-beta Vandermonde columns.",
              "MSE = SSE/(n-p); standardized residual = e_j/sqrt(MSE*(1-h_j)).",
              "Cook's distance = e_j^2*h_j/[p*MSE*(1-h_j)^2].",
              "Leave-one-out prediction minus observation = e_j/(1-h_j).",
              "The analytic leave-one-out expression applies to this same unweighted",
              "degree-six linear least-squares fit, with one table row omitted in turn.",
              "The Q-Q and influence plots are descriptive checks on a small rounded table.",
              "No normality, independent field-error or confidence-band claim is made.",
              "Linear-interpolation comparisons use adjacent Hsu table rows only.",
              "", "9. OLIVEIRA FIT SUMMARIES - QUOTED FROM THE SUPPLIED FILE",
              "The 48 original coefficient rows are unavailable in this request.",
              "No Oliveira per-row residuals, leverage, Cook's distance or Q-Q plot is generated.",
              "Display Source       R_squared             RMSE             MAE"]
    for j, item in enumerate(OLIVEIRA_REPORTED_FIT):
        lines.append(f"C{j+1:<6} C{j:<6} {item['r_squared']:.12f}   "
                     f"{item['rmse']:.10e}   {item['mae']:.10e}")
    lines += ["The two models' training rows, coverage and rounding differ. These fit",
              "statistics do not rank their ability to predict real shoreline geometry.",
              "", "10. FIXED PLANFORM REFERENCE",
              "For every overlay: H=(0,0), nominal E=(1,0), R0=1.",
              "phi = (theta-beta)*pi/180; x/R0 = r*cos(phi); y/R0 = r*sin(phi).",
              "Axes have equal scale. Both models use the same origin, angle and length.",
              "The nominal E point stays fixed; each model keeps its actual starting radius.",
              "", "11. FIGURES"]
    for item in figures:
        lines.append(f"{item['filename']}: {item['caption']}")
    lines += ["", "12. DATA FILES"]
    lines.extend(path.name for path in tables)
    lines += ["comparison_conclusions.txt: standalone executive interpretation and limitations.",
              "comparison_metadata.json: coefficients, settings, results and figure inventory.",
              "comparison_plots.pdf: one figure per page; vector text and linework.",
              "PNG figures are saved at the requested DPI (default 300).",
              "", "13. REPRODUCIBILITY",
              f"Python {platform.python_version()}; NumPy {np.__version__}; Matplotlib {matplotlib.__version__}.",
              "Run: python script.py --no-show",
              "For the supplied README's angular extent: python script.py --theta-max 150",
              "For a physical scale: python script.py --r0-m 100",
              "For all options: python script.py --help",
              ""]
    report = config.output_dir / "comparison_report.txt"
    report.write_text("\n".join(lines), encoding="utf-8")
    settings = asdict(config)
    settings["output_dir"] = str(config.output_dir)
    metadata = {
        "settings": settings,
        "notation": {"C1": "source C0; constant", "C2": "source C1; linear in q",
                     "C3": "source C2; quadratic in q"},
        "models": [asdict(model) for model in MODELS],
        "hsu_observations_beta_C1_C2_C3": HSU_TABLE,
        "oliveira_fit_metrics_quoted": OLIVEIRA_REPORTED_FIT,
        "hsu_fit_metrics_recomputed": diag["hsu_fit_metrics"],
        "model_difference_grid_metrics": metrics,
        "coefficient_difference_grid_metrics": diag["coefficient_difference_metrics"],
        "difference_extrema_check": envelope,
        "engineering_conclusions": conclusions,
        "figures": figures,
        "tables": [path.name for path in tables],
        "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                    "matplotlib": matplotlib.__version__},
    }
    metadata_path = config.output_dir / "comparison_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report, metadata_path


def show_gallery(config: Config, figures: list[dict[str, str]]) -> None:
    """Browse the saved high-resolution figures in one Matplotlib window."""
    backend = matplotlib.get_backend().lower()
    if backend in {"agg", "pdf", "ps", "svg", "template", "cairo"} or "inline" in backend:
        print("No interactive Matplotlib backend is active. Open comparison_plots.pdf or the PNG files.")
        return
    figure = plt.figure(figsize=(12, 7))
    figure.canvas.manager.set_window_title("Oliveira2010 / Hsu1989 - Plot viewer")
    axes = figure.add_axes((.015, .12, .97, .82))
    axes.set_axis_off()
    title = figure.text(.025, .97, "", va="top", fontsize=12, weight="bold")
    figure.text(.025, .035, "Left / right arrows: previous / next    |    Home / End: first / last",
                fontsize=10, color="#475569")
    state = {"index": 0}
    artist = axes.imshow(plt.imread(config.output_dir / figures[0]["filename"]))

    def update(index: int) -> None:
        state["index"] = index % len(figures)
        item = figures[state["index"]]
        pixels = plt.imread(config.output_dir / item["filename"])
        artist.set_data(pixels)
        height, width = pixels.shape[:2]
        artist.set_extent((0, width, height, 0))
        axes.set_xlim(0, width)
        axes.set_ylim(height, 0)
        title.set_text(f"{state['index'] + 1:02d} / {len(figures):02d}   {item['filename']}")
        figure.canvas.draw_idle()

    previous = Button(figure.add_axes((.71, .025, .11, .045)), "Previous")
    following = Button(figure.add_axes((.84, .025, .11, .045)), "Next")
    previous.on_clicked(lambda event: update(state["index"] - 1))
    following.on_clicked(lambda event: update(state["index"] + 1))

    def on_key(event: Any) -> None:
        if event.key in ("right", "down", " "):
            update(state["index"] + 1)
        elif event.key in ("left", "up"):
            update(state["index"] - 1)
        elif event.key == "home":
            update(0)
        elif event.key == "end":
            update(len(figures) - 1)

    figure.canvas.mpl_connect("key_press_event", on_key)
    update(0)
    # Button references remain alive until the blocking viewer is closed.
    plt.show()


def main() -> int:
    config = parse_arguments()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    configure_plot_style()
    print("Oliveira2010 and Hsu1989 comparison", flush=True)
    print("Display C1/C2/C3 = source C0/C1/C2; coefficients are not normalized.")
    print(f"Comparison beta: {config.beta_min:g} to {config.beta_max:g} deg; "
          f"curved branch theta: beta to {config.theta_max:g} deg.")
    data = calculate_data(config)
    diagnostics = calculate_diagnostics(data, config)
    conclusions = calculate_conclusions(data, diagnostics, config)
    write_conclusions_text(conclusions, config)
    tables = write_tables(data, diagnostics, config, conclusions)
    pdf_path = config.output_dir / "comparison_plots.pdf"
    with PdfPages(pdf_path, metadata={
        "Title": "Oliveira2010 and Hsu1989 - Coefficients, models and diagnostics",
        "Author": "Coefficient comparison script",
        "Subject": "Comparison of supplied degree-six coefficient fits; source notation C0/C1/C2",
        "Keywords": "Oliveira2010, Hsu1989, parabolic bay, coefficients, diagnostics",
    }) as pdf:
        writer = FigureWriter(config, pdf)
        generate_executive_figure(conclusions, config, writer)
        generate_figures(MODELS, data, diagnostics, config, writer, conclusions)
    report, _ = write_report(data, diagnostics, config, writer.figures, tables, conclusions)
    metrics = diagnostics["model_difference_metrics"]
    maximum = diagnostics["sampled_envelope"]["maximum"]
    print(f"\nSaved {len(writer.figures)} PNG figures, one PDF, {len(tables)} CSV tables, "
          "a detailed report, executive conclusions and JSON metadata.")
    print(f"Output directory: {config.output_dir}")
    print("\nMODEL COMPARISON - ENGINEERING CONCLUSIONS")
    print("=" * 64)
    for statement in conclusions["conclusions"]:
        print("- " + statement)
    print(f"\nFull report: {report.name}")
    print("Summary: comparison_conclusions.txt, comparison_conclusions.csv")
    print("PDF conclusions: first page of comparison_plots.pdf")
    if not config.no_show:
        show_gallery(config, writer.figures)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("Interrupted.") from None
