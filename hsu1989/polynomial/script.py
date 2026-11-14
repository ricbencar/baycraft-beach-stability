#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sixth-degree least-squares regression of Hsu & Evans (1989), Table 2.

The three tabulated series C0(beta), C1(beta), and C2(beta) are fitted
INDEPENDENTLY using the 15 published rows only.
No published polynomial regression coefficients are used as inputs.

Model for each series:
    C_i(beta) = sum(a_k * beta**k for k in range(7))
where beta is measured in degrees.

Numerical method: unweighted linear least squares in a scaled coordinate
(beta mapped from [10, 80] to [-1, 1]), using NumPy's Polynomial.fit.
The fitted polynomials are converted to ordinary powers of beta to report
the requested a0...a6 coefficients.

Requirements:
    pip install numpy

Run:
    python script.py

Output:
    output.txt (created in the same folder as this script)
    Tables cover beta = 10, 11, 12, ..., 80 degrees; observed values
    and residuals are reported only at actual measured/tabulated angles.
"""

from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial


# Hsu & Evans (1989), Table 2: beta [degrees], C0, C1, C2.
# The printed entry '-0.000' at beta=40 degrees is numerically zero.
DATA = np.array([
    [10,  0.036, 1.011, -0.047],
    [15,  0.050, 0.998, -0.049],
    [20,  0.055, 1.029, -0.088],
    [25,  0.054, 1.083, -0.142],
    [30,  0.045, 1.146, -0.194],
    [35,  0.029, 1.220, -0.253],
    [40,  0.000, 1.326, -0.332],
    [45, -0.039, 1.446, -0.412],
    [50, -0.088, 1.588, -0.507],
    [55, -0.151, 1.756, -0.611],
    [60, -0.227, 1.930, -0.706],
    [65, -0.315, 2.113, -0.800],
    [70, -0.409, 2.284, -0.873],
    [75, -0.505, 2.422, -0.909],
    [80, -0.600, 2.520, -0.906],
], dtype=float)

DEGREE = 6
SERIES_NAMES = ("C0", "C1", "C2")
OUTPUT_PATH = Path(__file__).resolve().with_name("output.txt")
TABLE_BETA_STEP = 1.0  # degree interval for output tables


def fit_series(beta: np.ndarray, values: np.ndarray) -> dict:
    """Fit one coefficient series, returning coefficients and fit metrics."""
    fit = Polynomial.fit(beta, values, DEGREE, domain=[beta.min(), beta.max()])
    coefficients = fit.convert().coef  # a0...a6 in ordinary beta degrees
    fitted = fit(beta)
    residuals = values - fitted
    sse = float(np.sum(residuals**2))
    sst = float(np.sum((values - values.mean())**2))
    return {
        "coefficients": coefficients,
        "polynomial": fit,
        "fitted": fitted,
        "residuals": residuals,
        "r2": 1.0 - sse / sst if sst > 0.0 else float("nan"),
        "rmse": float(np.sqrt(np.mean(residuals**2))),
        "mae": float(np.mean(np.abs(residuals))),
        "max_abs_error": float(np.max(np.abs(residuals))),
        "sse": sse,
    }


def polynomial_expression(name: str, a: np.ndarray) -> str:
    """Write the fitted sixth-degree expression with explicit signs."""
    parts = [f"{a[0]:.16e}"]
    for power in range(1, DEGREE + 1):
        sign = "+" if a[power] >= 0.0 else "-"
        beta_term = "beta" if power == 1 else f"beta^{power}"
        parts.append(f" {sign} {abs(a[power]):.16e}*{beta_term}")
    return f"{name}(beta) = " + "".join(parts)


def make_report(beta: np.ndarray, observations: np.ndarray, results: dict) -> str:
    lines = [
        "HSU & EVANS (1989) - TABLE 2: SIXTH-DEGREE POLYNOMIAL REGRESSION",
        "=" * 78,
        "",
        "DATA AND METHOD",
        "---------------",
        "Source: Hsu & Evans (1989), Table 2 (15 published beta/C0/C1/C2 rows).",
        "Input values are used as printed to three decimal places.",
        "Only the 15 published rows are used; all have equal weight.",
        "Each C-series is fitted separately; no coefficients from other studies",
        "are used in this calculation.",
        "Method: ordinary unweighted least squares, sixth-degree polynomial.",
        "Numerical fit uses a scaled beta coordinate for stability; output",
        "polynomials are transformed back to powers of beta in degrees.",
        f"Number of observations per series: {len(beta)}",
        f"Polynomial degree: {DEGREE}",
        f"Fitting beta range: {beta.min():.0f} to {beta.max():.0f} degrees",
        "",
        "FITTED MODEL",
        "------------",
        "C_i(beta) = a0 + a1*beta + a2*beta^2 + a3*beta^3 + a4*beta^4 + a5*beta^5 + a6*beta^6",
        "All angles beta are in DEGREES (not radians).",
        "",
        "POLYNOMIAL COEFFICIENTS (ordinary powers of beta)",
        "--------------------------------------------------",
        f"{'Term':<8} {'C0':>22} {'C1':>22} {'C2':>22}",
    ]
    for power in range(DEGREE + 1):
        vals = [results[name]["coefficients"][power] for name in SERIES_NAMES]
        lines.append(f"a{power:<7}" + "".join(f" {value:22.14e}" for value in vals))

    lines += ["", "EXPANDED SIXTH-DEGREE EQUATIONS", "--------------------------------"]
    for name in SERIES_NAMES:
        lines.append(polynomial_expression(name, results[name]["coefficients"]))
        lines.append("")

    lines += [
        "GOODNESS OF FIT",
        "---------------",
        f"Residual = observed - fitted; RMSE and MAE use all {len(beta)} rows.",
        f"{'Series':<8} {'R^2':>12} {'RMSE':>14} {'MAE':>14} {'Max |error|':>14} {'SSE':>14}",
    ]
    for name in SERIES_NAMES:
        r = results[name]
        lines.append(
            f"{name:<8} {r['r2']:12.9f} {r['rmse']:14.9f} "
            f"{r['mae']:14.9f} {r['max_abs_error']:14.9f} {r['sse']:14.9f}"
        )

    sample_beta = np.arange(beta.min(), beta.max() + TABLE_BETA_STEP / 2.0, TABLE_BETA_STEP)
    sample_fitted = {name: results[name]["polynomial"](sample_beta)
                     for name in SERIES_NAMES}

    lines += [
        "",
        "FITTED VALUES: BETA 10 TO 80 DEGREES (1-DEGREE INTERVAL)",
        "-------------------------------------------------------",
        f"{'beta_deg':>9} {'C0_fitted':>14} {'C1_fitted':>14} {'C2_fitted':>14}",
    ]
    for j, x in enumerate(sample_beta):
        lines.append(
            f"{x:9.0f}"
            + "".join(f" {sample_fitted[name][j]:14.6f}" for name in SERIES_NAMES)
        )

    lines += [
        "",
        "OBSERVED, FITTED, AND RESIDUAL VALUES: BETA 10 TO 80 DEGREES",
        "-----------------------------------------------------------",
        "A dash means no input observation exists at that beta; no residual",
        "can be calculated for interpolation-only angles.",
    ]
    for col, name in enumerate(SERIES_NAMES):
        lines.extend([
            "", f"{name}(beta)",
            f"{'beta_deg':>9} {'Observed':>14} {'Fitted':>14} {'Residual':>14}",
        ])
        observed_by_angle = {int(round(x)): float(y)
                             for x, y in zip(beta, observations[:, col])}
        for j, x in enumerate(sample_beta):
            fitted_val = float(sample_fitted[name][j])
            observed_val = observed_by_angle.get(int(round(x)))
            if observed_val is None:
                observed_text, residual_text = f"{'--':>14}", f"{'--':>14}"
            else:
                observed_text = f"{observed_val:14.6f}"
                residual_text = f"{observed_val - fitted_val:+14.6f}"
            lines.append(
                f"{x:9.0f} {observed_text} {fitted_val:14.6f} {residual_text}"
            )

    lines += [
        "",
        "NOTES",
        "-----",
        "1. Only the 15 published data points from beta=10 to 80 degrees",
        "   are included in each polynomial regression.",
        "2. Extrapolation beyond 10 to 80 degrees is not validated.",
        "3. Output tables list every integer beta from 10 through 80 degrees.",
        "   Blank observed/residual entries are interpolated rather than observed.",
        "4. Coefficients are printed with extra precision to preserve numerical",
        "   accuracy, especially for the highest-order polynomial terms.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    if DATA.shape != (15, 4) or not np.isfinite(DATA).all():
        raise ValueError("Expected 15 finite data rows: beta, C0, C1, C2.")
    beta = DATA[:, 0]
    if np.any(np.diff(beta) <= 0):
        raise ValueError("Input beta values must be strictly increasing.")

    observations = DATA[:, 1:]
    results = {
        name: fit_series(beta, observations[:, i])
        for i, name in enumerate(SERIES_NAMES)
    }
    report = make_report(beta, observations, results)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print("Hsu & Evans (1989), Table 2 - independent sixth-degree fits")
    for name in SERIES_NAMES:
        r = results[name]
        print(f"  {name}: R^2={r['r2']:.9f}, RMSE={r['rmse']:.9f}")
    print(f"Report written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
